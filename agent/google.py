"""Google for the agent's OWN account (milestone 16/17): Drive as its library, Gmail to read its own verification codes.

Official APIs only, standard library only (no google-auth packages to install on the owner's PC).
  .secrets/google_client.json   — the OAuth "Desktop app" client the owner downloaded from Google Cloud (never in git)
  .secrets/google_token.json    — refresh token obtained once via the browser consent flow (never in git, never printed)

Connect once:  python3 -m agent.google connect     (prints a link; the owner opens it, clicks Allow, pastes nothing —
                                                   the flow uses a local loopback port, as Google requires for desktop apps)
The consent screen is in "testing" mode (private app), so Google throws the refresh token away after 7 days: every call that
fails with invalid_grant flips `needs_reconnect`, and core.py sends the owner a fresh link over Telegram.
"""
import base64
import email
import email.policy
import http.server
import html
import json
import pathlib
import mimetypes
import os
import re
import secrets
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import config

CLIENT_FILE = config.ROOT / ".secrets" / "google_client.json"
TOKEN_FILE = config.ROOT / ".secrets" / "google_token.json"
TOKEN_BACKUP = pathlib.Path.home() / ".bai_google_token.json"
PENDING_FILE = config.ROOT / ".secrets" / "google_pending.json"   # consent flow state: survives restarts
PENDING_BACKUP = pathlib.Path.home() / ".bai_google_pending.json"       # second copy outside the repo folder (sandbox resets wipe the repo's ignored files first)
SCOPES = ["https://www.googleapis.com/auth/drive.file",          # files the app created (its library folder)
          "https://www.googleapis.com/auth/gmail.readonly",     # read its own inbox for verification codes
          "https://www.googleapis.com/auth/gmail.send",        # send mail as itself (fallback channel)
          "https://www.googleapis.com/auth/gmail.modify"]       # mark read / archive what it handled (mastery, item 6)
LIBRARY_FOLDER = "Business AI library"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
DRIVE = "https://www.googleapis.com/drive/v3"
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"


class GoogleError(Exception):
    pass


class Google:
    def __init__(self, log=None):
        self.log = log or (lambda kind, **f: None)
        self._lock = threading.RLock()
        self.client = None
        self.token = {}
        self.access = None
        self.access_until = 0
        self.needs_reconnect = False
        self.client_disabled = False    # Google switched the OAuth client off (disabled_client): links are useless until it is re-enabled
        self.last_error = ""
        self._folder_id = None
        self._pending = None            # {"state", "verifier", "redirect", "server"} while a consent flow is open
        self._load()

    # ---- state ------------------------------------------------------------------
    def _load(self):
        try:
            if CLIENT_FILE.exists():
                d = json.loads(CLIENT_FILE.read_text())
                self.client = d.get("installed") or d.get("web") or {}
            if TOKEN_FILE.exists():
                self.token = json.loads(TOKEN_FILE.read_text())
            elif TOKEN_BACKUP.exists():
                self.token = json.loads(TOKEN_BACKUP.read_text())
                self._save_token()
        except Exception as e:
            self.last_error = f"could not read Google files: {e}"
        try:
            src = PENDING_FILE if PENDING_FILE.exists() else (PENDING_BACKUP if PENDING_BACKUP.exists() else None)
            if src is not None:
                p = json.loads(src.read_text())
                if time.time() - p.get("t", 0) < 900 and p.get("state") and p.get("verifier"):
                    self._pending = {"state": p["state"], "verifier": p["verifier"],
                                     "redirect": p.get("redirect", ""), "server": None, "t": p["t"]}
                else:
                    PENDING_FILE.unlink(missing_ok=True); PENDING_BACKUP.unlink(missing_ok=True)
        except Exception:
            pass

    def has_client(self):
        return bool(self.client and self.client.get("client_id") and self.client.get("client_secret"))

    def connected(self):
        return self.has_client() and bool(self.token.get("refresh_token")) and not self.needs_reconnect

    def account(self):
        return self.token.get("email", "")

    def status(self):
        if not self.has_client():
            return ("Google: not set up. Put the OAuth client file from Google Cloud at .secrets/google_client.json "
                    "(Console → Google Auth Platform → Clients → Desktop app → Download JSON).")
        if not self.token.get("refresh_token"):
            return "Google: key present, not connected yet — run `python3 -m agent.google connect` on my machine, or say 'connect google' and I send you the link."
        if self.client_disabled:
            return f"Google: OFF — {self.last_error}"
        if self.needs_reconnect:
            return f"Google: connection expired (private apps are cut after 7 days) — say 'connect google' and I send you a new link. Last error: {self.last_error}"
        return f"Google: connected as {self.account() or 'the app account'} · Drive folder “{LIBRARY_FOLDER}” · Gmail read + send"

    # ---- OAuth (desktop app, loopback redirect, PKCE) ---------------------------
    def connect_link(self, prefer_port=None):
        """Start a consent flow: returns the URL the owner must open. A tiny local server on the agent's machine catches
        the redirect. If the owner's browser is on another machine (WSL → Windows works via localhost), it still works."""
        if not self.has_client():
            raise GoogleError("no .secrets/google_client.json")
        self._close_pending()
        verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).decode().rstrip("=")
        import hashlib
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        state = secrets.token_urlsafe(16)
        srv = _Catcher(prefer_port)
        redirect = f"http://localhost:{srv.port}"
        params = {"client_id": self.client["client_id"], "redirect_uri": redirect, "response_type": "code",
                  "scope": " ".join(SCOPES), "access_type": "offline", "prompt": "consent", "state": state,
                  "code_challenge": challenge, "code_challenge_method": "S256"}
        url = self.client.get("auth_uri", "https://accounts.google.com/o/oauth2/auth") + "?" + urllib.parse.urlencode(params)
        self._pending = {"state": state, "verifier": verifier, "redirect": redirect, "server": srv, "t": time.time()}
        try:
            blob = json.dumps({k: self._pending[k] for k in ("state", "verifier", "redirect", "t")})
            PENDING_FILE.write_text(blob)
            try:
                PENDING_BACKUP.write_text(blob); PENDING_BACKUP.chmod(0o600)
            except Exception:
                pass
            PENDING_FILE.chmod(0o600)
        except Exception:
            pass
        threading.Thread(target=self._wait_code, daemon=True).start()
        self.log("google_connect_started", port=srv.port)
        return url

    def _wait_code(self):
        p = self._pending
        if not p:
            return
        code = p["server"].wait(600)
        if not code:
            self.last_error = "no answer from the browser within 10 minutes"
            return
        if code.get("state") != p["state"]:
            self.last_error = "state mismatch (someone else answered?)"
            return
        try:
            self._exchange(code["code"], p["verifier"], p["redirect"])
            self.needs_reconnect = False
            self.client_disabled = False
            self.last_error = ""
            self.log("google_connected", account=self.account())
        except Exception as e:
            self.last_error = f"token exchange failed: {e}"
            self.log("google_connect_failed", error=str(e)[:200])
        finally:
            self._close_pending()

    def wait_connected(self, timeout=600, stdin_fallback=False):
        """Blocking helper for the command line: True when the flow completed. With stdin_fallback the owner may paste the
        failed redirect URL into the terminal instead."""
        if stdin_fallback:
            def _reader():
                try:
                    import sys
                    for line in sys.stdin:
                        if "code=" in line:
                            print(self.finish_with_url(line), flush=True)
                            return
                except Exception:
                    pass
            threading.Thread(target=_reader, daemon=True).start()
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.connected() and self.token.get("refresh_token"):
                return True
            if self._pending is None and self.last_error:
                return False
            time.sleep(1)
        return False

    def _close_pending(self):
        if self._pending:
            try:
                self._pending["server"].close()
            except Exception:
                pass
        try:
            PENDING_FILE.unlink(missing_ok=True); PENDING_BACKUP.unlink(missing_ok=True)
        except Exception:
            pass
        self._pending = None

    def _exchange(self, code, verifier, redirect):
        body = {"code": code, "client_id": self.client["client_id"], "client_secret": self.client["client_secret"],
                "redirect_uri": redirect, "grant_type": "authorization_code", "code_verifier": verifier}
        d = _post_form(self.client.get("token_uri", "https://oauth2.googleapis.com/token"), body)
        if "refresh_token" not in d:
            raise GoogleError("Google did not return a refresh token (open the link again; it must say 'Allow')")
        self.token = {"refresh_token": d["refresh_token"], "scope": d.get("scope", ""), "t": int(time.time())}
        self.access, self.access_until = d["access_token"], time.time() + int(d.get("expires_in", 3600)) - 60
        try:
            info = self._get(f"{GMAIL}/profile")                      # gmail.readonly covers this; no extra "email" scope needed
            self.token["email"] = info.get("emailAddress", "")
        except Exception:
            pass
        self._save_token()

    def finish_with_url(self, pasted):
        """Fallback when the browser could not reach the local catcher: the owner pastes the failed address bar URL
        (http://localhost:8097/?state=…&code=…). Returns a human sentence."""
        p = self._pending
        if not p:
            return "I have no Google connection waiting — say 'connect google' first and I'll send a fresh link."
        q = urllib.parse.parse_qs(urllib.parse.urlparse(pasted.strip()).query)
        code, state = q.get("code", [""])[0], q.get("state", [""])[0]
        if not code:
            return "That address has no code in it — copy the whole address bar after clicking Allow (it starts with http://localhost)."
        if state != p["state"]:
            return "That link belongs to an older attempt — say 'connect google' again and use the new link."
        try:
            self._exchange(code, p["verifier"], p["redirect"])
            self.needs_reconnect = False
            self.client_disabled = False
            self.last_error = ""
            self.log("google_connected", account=self.account(), via="pasted")
            return f"✅ Connected to Google as {self.account() or 'the app account'}."
        except Exception as e:
            self.last_error = f"token exchange failed: {e}"
            return f"Google refused the code: {str(e)[:160]}. Say 'connect google' to try again."
        finally:
            self._close_pending()

    def _save_token(self):
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(json.dumps(self.token))
        os.chmod(TOKEN_FILE, 0o600)
        try:                                                    # second copy outside the repo folder (survives a wiped checkout)
            TOKEN_BACKUP.write_text(json.dumps(self.token)); TOKEN_BACKUP.chmod(0o600)
        except Exception:
            pass

    def _access_token(self):
        with self._lock:
            if self.access and time.time() < self.access_until:
                return self.access
            if not self.token.get("refresh_token"):
                raise GoogleError("not connected")
            body = {"client_id": self.client["client_id"], "client_secret": self.client["client_secret"],
                    "refresh_token": self.token["refresh_token"], "grant_type": "refresh_token"}
            try:
                d = _post_form(self.client.get("token_uri", "https://oauth2.googleapis.com/token"), body)
            except GoogleError as e:
                if "disabled_client" in str(e) or "deleted_client" in str(e):
                    # not the 7-day cut: the OAuth client is switched off in Google Cloud. A new link won't help until
                    # the owner re-enables it (or downloads a fresh client JSON) — say so instead of sending links.
                    self.needs_reconnect = True
                    self.client_disabled = True
                    self.last_error = ("Google disabled the app's OAuth client in the Cloud console (error disabled_client). A new link "
                                       "won't help: open console.cloud.google.com → Google Auth Platform → Clients, re-enable the client "
                                       "(or make a new Desktop-app client and give me its JSON), then say 'connect google'.")
                    self.log("google_client_disabled")
                elif "invalid_grant" in str(e) or "invalid_client" in str(e):
                    self.needs_reconnect = True
                    self.last_error = "Google dropped the connection (7-day limit for private apps)"
                    self.log("google_needs_reconnect")
                raise
            self.access, self.access_until = d["access_token"], time.time() + int(d.get("expires_in", 3600)) - 60
            return self.access

    # ---- HTTP -------------------------------------------------------------------
    def _req(self, url, method="GET", data=None, headers=None, raw=False, timeout=60):
        h = {"Authorization": f"Bearer {self._access_token()}"}
        h.update(headers or {})
        req = urllib.request.Request(url, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                b = r.read()
                return b if raw else (json.loads(b.decode()) if b else {})
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:300]
            if e.code == 401:
                self.access = None
            raise GoogleError(f"HTTP {e.code} {body}")

    def _get(self, url, **params):
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        return self._req(url)

    # ---- Drive: the library ------------------------------------------------------
    def folder_id(self):
        with self._lock:
            if self._folder_id:
                return self._folder_id
            q = f"name = '{LIBRARY_FOLDER}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            d = self._get(f"{DRIVE}/files", q=q, fields="files(id,name)", spaces="drive")
            if d.get("files"):
                self._folder_id = d["files"][0]["id"]
            else:
                d = self._req(f"{DRIVE}/files?fields=id", "POST", json.dumps({"name": LIBRARY_FOLDER, "mimeType": "application/vnd.google-apps.folder"}).encode(),
                              {"Content-Type": "application/json"})
                self._folder_id = d["id"]
            return self._folder_id

    def subfolder(self, name):
        parent = self.folder_id()
        q = f"name = '{name}' and '{parent}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        d = self._get(f"{DRIVE}/files", q=q, fields="files(id)")
        if d.get("files"):
            return d["files"][0]["id"]
        d = self._req(f"{DRIVE}/files?fields=id", "POST", json.dumps({"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent]}).encode(),
                      {"Content-Type": "application/json"})
        return d["id"]

    def upload(self, path, name=None, folder=None, mime=None, convert_to_doc=False):
        """Upload a local file into the library (or a subfolder name). Returns {id, name, link}.
        convert_to_doc=True turns an HTML file into a real Google Doc the owner can edit."""
        path = str(path)
        name = name or os.path.basename(path)
        mime = mime or mimetypes.guess_type(path)[0] or "application/octet-stream"
        parent = self.subfolder(folder) if folder else self.folder_id()
        meta = {"name": name, "parents": [parent]}
        if convert_to_doc:
            meta["mimeType"] = "application/vnd.google-apps.document"
        boundary = "bai" + secrets.token_hex(8)
        with open(path, "rb") as f:
            content = f.read()
        body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(meta)}\r\n"
                f"--{boundary}\r\nContent-Type: {mime}\r\n\r\n").encode() + content + f"\r\n--{boundary}--".encode()
        d = self._req(f"{UPLOAD}?uploadType=multipart&fields=id,name,webViewLink", "POST", body,
                      {"Content-Type": f"multipart/related; boundary={boundary}"}, timeout=300)
        self.log("drive_upload", name=name, size=len(content), doc=convert_to_doc)
        return {"id": d["id"], "name": d.get("name", name), "link": d.get("webViewLink", f"https://drive.google.com/file/d/{d['id']}/view")}

    def upload_bytes(self, data, name, folder=None, mime="application/octet-stream"):
        tmp = config.STATE_DIR / f"_up_{secrets.token_hex(4)}"
        tmp.write_bytes(data)
        try:
            return self.upload(tmp, name=name, folder=folder, mime=mime)
        finally:
            tmp.unlink(missing_ok=True)

    def upload_text(self, text, name, folder=None, mime="text/plain"):
        tmp = config.STATE_DIR / f"_up_{secrets.token_hex(4)}"
        tmp.write_text(text, encoding="utf-8")
        try:
            return self.upload(tmp, name=name, folder=folder, mime=mime, convert_to_doc=(mime == "text/html"))
        finally:
            tmp.unlink(missing_ok=True)

    def list_library(self, folder=None, limit=20):
        parent = self.subfolder(folder) if folder else self.folder_id()
        d = self._get(f"{DRIVE}/files", q=f"'{parent}' in parents and trashed = false", orderBy="modifiedTime desc",
                      pageSize=limit, fields="files(id,name,mimeType,modifiedTime,size,webViewLink)")
        return d.get("files", [])

    def folder_link(self):
        return f"https://drive.google.com/drive/folders/{self.folder_id()}"

    def download(self, file_id, to_path):
        b = self._req(f"{DRIVE}/files/{file_id}?alt=media", raw=True, timeout=300)
        with open(to_path, "wb") as f:
            f.write(b)
        return to_path

    def files_update(self, file_id, data, mime="text/html"):
        """Replace a Drive file's content in place (for converted Docs: pass the new HTML)."""
        if isinstance(data, (bytes, bytearray)):
            content = bytes(data)
        else:
            with open(data, "rb") as f:
                content = f.read()
        boundary = "bai" + secrets.token_hex(8)
        body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{{}}\r\n"
                f"--{boundary}\r\nContent-Type: {mime}\r\n\r\n").encode() + content + f"\r\n--{boundary}--".encode()
        d = self._req(f"{UPLOAD}/{file_id}?uploadType=multipart&fields=id,name,webViewLink", "PATCH", body,
                      {"Content-Type": f"multipart/related; boundary={boundary}"}, timeout=300)
        self.log("drive_update", id=file_id[:12], size=len(content))
        return {"id": d["id"], "name": d.get("name", ""), "link": d.get("webViewLink", "")}

    # ---- Gmail: read its own verification codes --------------------------------------
    def recent_mail(self, query="newer_than:1d", limit=10):
        """Latest messages matching a Gmail search; returns [{id, thread, msgid, labels, from, subject, date, snippet, text}]."""
        d = self._get(f"{GMAIL}/messages", q=query, maxResults=limit)
        out = []
        for m in d.get("messages", []):
            full = self._get(f"{GMAIL}/messages/{m['id']}", format="raw")
            raw = base64.urlsafe_b64decode(full["raw"] + "==")
            msg = email.message_from_bytes(raw, policy=email.policy.default)
            body = ""
            try:
                part = msg.get_body(preferencelist=("plain", "html"))
                if part is not None:
                    body = part.get_content()
                    if part.get_content_type() == "text/html":
                        body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", body, flags=re.S | re.I)
                        body = re.sub(r"<[^>]+>", " ", body)
                        body = re.sub(r"&nbsp;|&#160;", " ", body)
            except Exception:
                body = ""
            out.append({"id": m["id"], "thread": full.get("threadId", ""), "msgid": str(msg.get("Message-ID", "")),
                        "auth": str(msg.get("Authentication-Results", "")),          # Gmail's SPF/DKIM verdict: spoofed From headers fail here
                        "labels": full.get("labelIds", []), "from": str(msg.get("From", "")), "subject": str(msg.get("Subject", "")),
                        "date": str(msg.get("Date", "")), "snippet": full.get("snippet", ""), "text": re.sub(r"\s+", " ", body).strip()[:4000]})
        return out

    def send_mail(self, to, subject, body, html=None, thread_id=None, in_reply_to=None):
        """Send an email as the app account (fallback channel: reports + replies to the owner). Returns the sent id.
        thread_id + in_reply_to (the original Message-ID) turn it into a real threaded reply."""
        msg = email.message.EmailMessage(policy=email.policy.default)
        msg["To"] = to
        msg["From"] = self.account() or "me"
        msg["Subject"] = subject
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = in_reply_to
        if html:
            msg.set_content(body)
            msg.add_alternative(html, subtype="html")
        else:
            msg.set_content(body)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        payload = {"raw": raw}
        if thread_id:
            payload["threadId"] = thread_id
        try:
            d = self._req(f"{GMAIL}/messages/send", method="POST",
                          data=json.dumps(payload).encode(),
                          headers={"Content-Type": "application/json"})
        except GoogleError:
            if not (thread_id or in_reply_to):
                raise
            for h in ("In-Reply-To", "References"):      # threading rejected → plain send; the mail must go out
                try:
                    del msg[h]
                except KeyError:
                    pass
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            d = self._req(f"{GMAIL}/messages/send", method="POST",
                          data=json.dumps({"raw": raw}).encode(),
                          headers={"Content-Type": "application/json"})
            self.log("gmail_thread_fallback", to=str(to)[:60])
        self.log("gmail_sent", to=str(to)[:60], subject=str(subject)[:60])
        return d.get("id", "")

    def mark_read(self, mid):
        """Mark one message read (best-effort; needs gmail.modify — old tokens raise, callers swallow)."""
        self._req(f"{GMAIL}/messages/{mid}/modify", method="POST",
                  data=json.dumps({"removeLabelIds": ["UNREAD"]}).encode(),
                  headers={"Content-Type": "application/json"})

    def archive(self, mid):
        """Archive one message out of the inbox (same best-effort contract as mark_read)."""
        self._req(f"{GMAIL}/messages/{mid}/modify", method="POST",
                  data=json.dumps({"removeLabelIds": ["INBOX"]}).encode(),
                  headers={"Content-Type": "application/json"})

    # ---- Gmail as a tool (owner's item G): labels, light listing, modify ----------------------------------
    def labels(self):
        """All labels of the mailbox → {name: id} (system + user)."""
        d = self._get(f"{GMAIL}/labels")
        return {l["name"]: l["id"] for l in d.get("labels", []) if l.get("name") and l.get("id")}

    def ensure_label(self, name, existing=None):
        """The id of label `name`, created when missing (shown in the Gmail sidebar). Never deletes anything."""
        existing = existing if existing is not None else self.labels()
        if name in existing:
            return existing[name]
        d = self._req(f"{GMAIL}/labels", method="POST",
                      data=json.dumps({"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"}).encode(),
                      headers={"Content-Type": "application/json"})
        self.log("gmail_label_created", name=name)
        return d.get("id", "")

    def modify(self, mid, add=(), remove=()):
        """Add/remove label ids on one message (archive = remove INBOX, read = remove UNREAD). Nothing is ever deleted."""
        body = {}
        if add:
            body["addLabelIds"] = list(add)
        if remove:
            body["removeLabelIds"] = list(remove)
        if not body:
            return {}
        return self._req(f"{GMAIL}/messages/{mid}/modify", method="POST", data=json.dumps(body).encode(),
                         headers={"Content-Type": "application/json"})

    META_HEADERS = ("From", "To", "Subject", "Date", "List-Unsubscribe", "List-Id", "Precedence", "Auto-Submitted", "Authentication-Results")

    def list_mail_meta(self, query="newer_than:2d", limit=25):
        """Light listing (headers + snippet, no body): [{id, thread, labels, from, subject, date, snippet, internal_ms, headers}]."""
        d = self._get(f"{GMAIL}/messages", q=query, maxResults=limit)
        out = []
        for m in d.get("messages", []):
            url = f"{GMAIL}/messages/{m['id']}?format=metadata&" + "&".join("metadataHeaders=" + h for h in self.META_HEADERS)
            full = self._req(url)
            hd = {h.get("name", ""): h.get("value", "") for h in (full.get("payload") or {}).get("headers", [])}
            out.append({"id": m["id"], "thread": full.get("threadId", ""), "labels": full.get("labelIds", []),
                        "from": hd.get("From", ""), "to": hd.get("To", ""), "subject": hd.get("Subject", ""), "date": hd.get("Date", ""),
                        "snippet": html.unescape(full.get("snippet", "") or ""), "internal_ms": int(full.get("internalDate", 0) or 0), "headers": hd})
        return out

    CODE_RE = re.compile(r"(?<![\d-])(\d{4,8})(?![\d-])")

    @staticmethod
    def _from_query(hint):
        """A server-side from: clause when the hint is a safe single token, else ''."""
        hint = (hint or "").lower()
        if re.fullmatch(r"[a-z0-9][a-z0-9.\-]*", hint):
            return f" from:({hint})"
        return ""

    def find_code(self, sender_hint="", since_minutes=15, tries=6, wait=20):
        """Poll the inbox for a fresh verification code (4–8 digits) — optionally from a sender/subject containing sender_hint.
        Returns (code, mail) or (None, None). Waits `wait` s between tries so the mail has time to arrive."""
        hint = (sender_hint or "").lower()
        query = f"newer_than:{max(1, since_minutes // 60 + 1)}h" + self._from_query(hint)
        for _ in range(tries):
            mails = self.recent_mail(query, 10)
            for m in mails:
                blob = f"{m['from']} {m['subject']}".lower()
                if hint and hint not in blob and hint.split(".")[0] not in blob:
                    continue
                txt = f"{m['subject']} {m['text'] or m['snippet']}"
                if not re.search(r"\b(code|codice|verif|confirm|conferma|otp|pin|one-time|passcode)\w*", txt, re.I):
                    continue
                m2 = re.search(r"(?:code|codice|otp|pin|passcode)\D{0,40}?(\d[\d ]{2,10}\d)", txt, re.I) or self.CODE_RE.search(txt)
                if m2:
                    code = re.sub(r"\D", "", m2.group(1))
                    if 4 <= len(code) <= 8:
                        self.log("gmail_code_found", sender=m["from"][:60])
                        return code, m
            time.sleep(wait)
        return None, None

    def find_link(self, sender_hint="", pattern=r"(verify|confirm|activate|conferma|verifica)", since_minutes=15, tries=6, wait=20):
        """Poll for a confirmation link in a fresh mail."""
        hint = (sender_hint or "").lower()
        query = f"newer_than:{max(1, since_minutes // 60 + 1)}h" + self._from_query(hint)
        for _ in range(tries):
            for m in self.recent_mail(query, 10):
                if hint and hint not in f"{m['from']} {m['subject']}".lower():
                    continue
                full = self._get(f"{GMAIL}/messages/{m['id']}", format="raw")
                raw = base64.urlsafe_b64decode(full["raw"] + "==").decode(errors="replace")
                links = re.findall(r"https?://[^\s\"'<>]+", raw)
                links = [l.rstrip(".,)") for l in links if re.search(pattern, l, re.I)]
                if links:
                    return links[0], m
            time.sleep(wait)
        return None, None


    # ---- Google Docs: native reports (headings, tables, bullets) -------------------------
    DOCS = "https://docs.googleapis.com/v1/documents"

    def docs_create(self, title, folder=None, share=False):
        """Create a native Google Doc in the library folder. share=True → anyone-with-link can read."""
        d = self._req(self.DOCS, method="POST", data=json.dumps({"title": title}).encode(),
                      headers={"Content-Type": "application/json"})
        doc_id = d["documentId"]
        link = f"https://docs.google.com/document/d/{doc_id}/edit"
        try:
            parent = self.subfolder(folder) if folder else self.folder_id()
            self._req(f"{DRIVE}/files/{doc_id}?addParents={parent}&removeParents=root", method="PATCH")
        except Exception:
            pass
        if share:
            self.share_link(doc_id)
        self.log("docs_created", title=title[:60])
        return {"id": doc_id, "link": link}

    def share_link(self, file_id):
        """Anyone with the link can read (used for heartbeat/progress docs the owner reads)."""
        try:
            self._req(f"{DRIVE}/files/{file_id}/permissions", method="POST",
                      data=json.dumps({"role": "reader", "type": "anyone"}).encode(),
                      headers={"Content-Type": "application/json"})
        except Exception as e:
            self.log("share_failed", error=str(e)[:120])

    def docs_get(self, doc_id):
        return self._req(f"{self.DOCS}/{doc_id}?fields=body.content")

    def docs_update(self, doc_id, requests):
        if not requests:
            return {}
        return self._req(f"{self.DOCS}/{doc_id}:batchUpdate", method="POST",
                         data=json.dumps({"requests": requests}).encode(),
                         headers={"Content-Type": "application/json"})

    def _doc_end(self, doc_id):
        content = self.docs_get(doc_id).get("body", {}).get("content", [])
        return content[-1].get("endIndex", 2) - 1 if content else 1

    def docs_clear(self, doc_id):
        end = self._doc_end(doc_id)
        if end > 1:
            self.docs_update(doc_id, [{"deleteContentRange": {"range": {"startIndex": 1, "endIndex": end}}}])

    def _table_cells(self, doc_id, table_no=0):
        """startIndex of every cell's first paragraph (row-major) for the Nth table in the doc."""
        content = self.docs_get(doc_id).get("body", {}).get("content", [])
        tables = [el["table"] for el in content if "table" in el]
        if table_no >= len(tables):
            return []
        out = []
        for row in tables[table_no].get("tableRows", []):
            for cell in row.get("tableCells", []):
                for el in cell.get("content", []):
                    if "paragraph" in el:
                        out.append(el["startIndex"])
                        break
        return out

    def docs_write_blocks(self, doc_id, blocks):
        """blocks: ("h1"|"h2"|"p"|"bullet", text) or ("table", [[cell, ...], ...]). Appends at the end."""
        idx = self._doc_end(doc_id)
        pending = []

        def flush():
            nonlocal pending
            if pending:
                self.docs_update(doc_id, pending)
                pending = []

        for kind, payload in blocks:
            if kind == "table":
                flush()
                rows, cols = len(payload), max(len(r) for r in payload)
                existing = self.docs_get(doc_id).get("body", {}).get("content", [])
                ntables = sum(1 for el in existing if "table" in el)
                at = self._doc_end(doc_id)
                self.docs_update(doc_id, [{"insertTable": {"location": {"index": at},
                                                           "rows": rows, "columns": cols}}])
                cells = self._table_cells(doc_id, ntables)
                flat = [c for r in payload for c in (list(r) + [""] * (cols - len(r)))]
                reqs = [{"insertText": {"location": {"index": ci}, "text": str(txt)}}
                        for ci, txt in reversed(list(zip(cells, flat))) if txt]
                self.docs_update(doc_id, reqs)
                idx = self._doc_end(doc_id)
                continue
            text = str(payload) + "\n"
            n = _len16(text)                                   # Docs indexes count UTF-16 units: 📝 🔥 🛒 are 2 each, not 1
            pending.append({"insertText": {"location": {"index": idx}, "text": text}})
            for m in re.finditer(r"https?://[^\s)\]>\"']+", text):   # bare URLs become real links (the API never auto-links)
                a, b_ = idx + _len16(text[:m.start()]), idx + _len16(text[:m.end()])
                pending.append({"updateTextStyle": {"range": {"startIndex": a, "endIndex": b_}, "textStyle": {"link": {"url": m.group(0)}}, "fields": "link"}})
            if kind in ("h1", "h2"):
                pending.append({"updateParagraphStyle": {
                    "range": {"startIndex": idx, "endIndex": idx + n},
                    "paragraphStyle": {"namedStyleType": "HEADING_1" if kind == "h1" else "HEADING_2"},
                    "fields": "namedStyleType"}})
            elif kind == "bullet":
                pending.append({"createParagraphBullets": {
                    "range": {"startIndex": idx, "endIndex": idx + n},
                    "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"}})
            idx += n
        flush()


def _len16(text):
    """Length in UTF-16 code units — what the Docs API means by 'index'."""
    return len(text.encode("utf-16-le")) // 2


class _Catcher:
    """One-shot local HTTP server that receives Google's redirect (http://localhost:PORT/?code=…&state=…)."""

    def __init__(self, prefer_port=None):
        self.result = None
        self.done = threading.Event()
        catcher = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                ok = "code" in q
                catcher.result = {"code": q.get("code", [""])[0], "state": q.get("state", [""])[0], "error": q.get("error", [""])[0]}
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(("<html><body style='font-family:sans-serif;text-align:center;padding:60px'><h2>"
                                  + ("✅ Business AI is connected to Google. You can close this tab." if ok else "❌ Google said no: " + catcher.result["error"])
                                  + "</h2></body></html>").encode())
                catcher.done.set()

        port = prefer_port or 0
        for p in ([port] if port else []) + [0]:
            try:
                self.srv = http.server.HTTPServer(("0.0.0.0", p), H)      # all interfaces: under WSL, Windows reaches it as localhost
                break
            except OSError:
                continue
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def wait(self, timeout):
        self.done.wait(timeout)
        return self.result

    def close(self):
        try:
            self.srv.shutdown()
            self.srv.server_close()
        except Exception:
            pass


def _post_form(url, fields):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode(), headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:300]
        raise GoogleError(f"HTTP {e.code} {body}")


# ---- command line: python3 -m agent.google connect | status | ls | mail | up <file> -------------------------------
if __name__ == "__main__":
    import sys
    G = Google(log=lambda k, **f: None)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "connect":
        url = G.connect_link(prefer_port=8097)
        print("\nOpen this link in your browser (same account: the AI's Gmail), click Advanced → Go to businessai → Allow:\n")
        print(url, "\n")
        print("Waiting for Google (up to 10 minutes)… If the browser ends on a page it cannot reach, paste that page's address here.", flush=True)
        if G.wait_connected(600, stdin_fallback=True):
            print(f"✅ Connected as {G.account() or 'the app account'}. Library folder: {G.folder_link()}")
            sys.exit(0)
        print("❌ Not connected:", G.last_error or "no answer")
        sys.exit(1)
    if cmd == "status":
        print(G.status())
    elif cmd == "ls":
        for f in G.list_library():
            print(f"{f['modifiedTime'][:16]}  {f.get('size', '-'):>8}  {f['name']}  {f.get('webViewLink', '')}")
        print("folder:", G.folder_link())
    elif cmd == "mail":
        for m in G.recent_mail("newer_than:7d", 5):
            print(f"{m['date'][:22]} | {m['from'][:40]} | {m['subject'][:60]}")
    elif cmd == "up":
        print(G.upload(sys.argv[2], convert_to_doc=sys.argv[2].endswith(".html")))
    else:
        print("usage: python3 -m agent.google connect|status|ls|mail|up <file>")
