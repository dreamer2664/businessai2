"""The agent's identity mailbox over plain IMAP — no Google API, no OAuth client, nothing a provider can "disable".

Why this exists (2026-09-10): the bot's first Gmail (busynessai001) was banned — a fresh account with a Cloud project
attached, API calls from two IPs, automated tidying every 15 minutes. The lesson is baked in here:
  • read-only: never deletes, never moves, never marks read (BODY.PEEK), never sends;
  • filter-only: looks at recent mail only, and only for verification codes / confirmation links from the site at hand;
  • gentle: one IMAP login per lookup, a few polls spaced out, never a background loop hammering the box;
  • any mailbox: Gmail with an app password, Libero, GMX, Outlook, a domain mailbox — IMAP_HOST decides.

Config (.secrets/env on the PC, never in git):
  BAI_ACCOUNT_EMAIL=spamcarlo019@gmail.com          the address the bot gives to sites
  BAI_MAIL_PASSWORD=<16-letter Gmail app password>  IMAP password (never falls back to the site password)
  BAI_MAIL_IMAP_HOST=imap.gmail.com                 optional: guessed from the address domain when missing
  BAI_MAIL_IMAP_PORT=993                            optional
  BAI_MAIL_ALIAS=                                   optional: an alias ("carlo+bot@gmail.com" / "bot@shop.it") the sites get;
                                                    only mail TO that alias is looked at (keeps the owner's own mail out)
"""
import email
import email.header
import email.utils
import imaplib
import os
import re
import time
from html import unescape

GUESS_HOST = {"gmail.com": "imap.gmail.com", "googlemail.com": "imap.gmail.com", "libero.it": "imapmail.libero.it", "gmx.com": "imap.gmx.com",
              "gmx.net": "imap.gmx.net", "gmx.de": "imap.gmx.net", "mail.com": "imap.mail.com", "outlook.com": "outlook.office365.com",
              "hotmail.com": "outlook.office365.com", "live.com": "outlook.office365.com", "icloud.com": "imap.mail.me.com", "me.com": "imap.mail.me.com",
              "yahoo.com": "imap.mail.yahoo.com", "yahoo.it": "imap.mail.yahoo.com", "aruba.it": "imaps.aruba.it", "pec.it": "imaps.pec.aruba.it",
              "tiscali.it": "imap.tiscali.it", "virgilio.it": "in.virgilio.it", "alice.it": "in.alice.it", "tin.it": "in.alice.it", "fastwebnet.it": "imap.fastwebnet.it",
              "protonmail.com": "127.0.0.1", "proton.me": "127.0.0.1"}     # proton needs Bridge → local

CODE_RE = re.compile(r"(?<![\d-])(\d{4,8})(?![\d-])")
CODE_NEAR = re.compile(r"(?:code|codice|otp|pin|passcode|verification|verifica)\D{0,40}?(\d[\d ]{2,10}\d)", re.I)
CODE_WORDS = re.compile(r"\b(code|codice|verif|confirm|conferma|otp|pin|one-time|passcode|attiva|activate)\w*", re.I)
SERVICE_FROM = re.compile(r"no-?reply|noreply|do-?not-?reply|notification|verify|verification|account|security|support|service|team|info@|hello@|mailer|auth|login|signup|register|welcome", re.I)
VERIFY_SUBJECT = re.compile(r"verif|conferma|confirm|codice|code|otp|password|one-time|passcode|sign ?in|accesso|login|attiva|activate|register|registrazione|welcome|benvenut", re.I)


def looks_like_verification(mail):
    """This is the OWNER's inbox: only mail that looks like a service's verification mail may be read for a code —
    a person's message ('codice porta 5544') never is."""
    frm = mail.get("from", "")
    return bool(SERVICE_FROM.search(frm) and VERIFY_SUBJECT.search(mail.get("subject", "") + " " + frm))


class IdMail:
    def __init__(self, log=None):
        self.log = log or (lambda kind, **f: None)
        self.email = os.environ.get("BAI_ACCOUNT_EMAIL", "").strip()
        self.password = os.environ.get("BAI_MAIL_PASSWORD", "").strip().replace(" ", "")   # ONLY the mailbox's own (app) password — never the site password (a wrong-password storm on the owner's Gmail is the one thing we must never do)
        self.alias = os.environ.get("BAI_MAIL_ALIAS", "").strip().lower()
        dom = self.email.split("@")[-1].lower() if "@" in self.email else ""
        self.host = os.environ.get("BAI_MAIL_IMAP_HOST", "").strip() or GUESS_HOST.get(dom, f"imap.{dom}" if dom else "")
        self.port = int(os.environ.get("BAI_MAIL_IMAP_PORT", "993") or 993)
        self.last_error = ""

    # ---- status ------------------------------------------------------------------------------------------
    def configured(self):
        return bool(self.email and self.password and self.host)

    def address(self):
        """What the bot types into sign-up forms: the alias when there is one, else the mailbox itself."""
        return self.alias or self.email

    def describe(self):
        if not self.configured():
            return "identity mailbox: not set (BAI_ACCOUNT_EMAIL + BAI_MAIL_PASSWORD in .secrets/env)"
        return f"identity mailbox: {self.address()} via IMAP {self.host} (read-only; app password in .secrets/env)"

    def check(self):
        """One login + one folder select → (ok, note). Used by selfcheck / doctor; never reads mail."""
        if not self.configured():
            return False, "not configured"
        try:
            with self._conn() as c:
                typ, data = c.select("INBOX", readonly=True)
                n = int(data[0]) if typ == "OK" and data and data[0] else 0
            return True, f"login ok, {n} message(s) in INBOX"
        except Exception as e:
            self.last_error = str(e)[:160]
            return False, self._explain(e)

    def _explain(self, e):
        s = str(e)
        if re.search(r"Application-specific password required|AUTHENTICATIONFAILED.*app|Invalid credentials", s, re.I) and "gmail" in self.host:
            return "Gmail refuses the login: it needs an APP PASSWORD (myaccount.google.com/apppasswords, after 2-Step Verification), not the account password"
        if re.search(r"AUTHENTICATIONFAILED|LOGIN failed|Invalid credentials|authentication failed", s, re.I):
            return "the mailbox refused the password (for GMX: enable IMAP in Settings → POP3 & IMAP first)"
        if re.search(r"getaddrinfo|Name or service|timed out|Connection refused", s, re.I):
            return f"could not reach {self.host}:{self.port} (host wrong, or no network)"
        return s[:160]

    # ---- reading ----------------------------------------------------------------------------------------
    def _conn(self):
        return _Conn(self)

    def recent(self, minutes=30, limit=15, hint=""):
        """The newest messages (headers + text), optionally only those whose From/Subject mention `hint` and — when an
        alias is set — only those addressed to the alias. Read-only (BODY.PEEK): nothing is marked as read."""
        out = []
        if not self.configured():
            return out
        since = time.strftime("%d-%b-%Y", time.gmtime(time.time() - 86400))          # IMAP SINCE is day-granular; we filter by Date after
        try:
            with self._conn() as c:
                c.select("INBOX", readonly=True)
                crit = f'(SINCE {since})'
                if self.alias:
                    crit = f'(SINCE {since} TO "{self.alias}")'
                typ, data = c.search(None, crit)
                ids = data[0].split() if typ == "OK" and data and data[0] else []
                for mid in reversed(ids[-60:]):
                    typ, msg = c.fetch(mid, "(BODY.PEEK[])")
                    if typ != "OK" or not msg or not msg[0]:
                        continue
                    raw = msg[0][1] if isinstance(msg[0], tuple) else b""
                    m = email.message_from_bytes(raw)
                    ts = email.utils.parsedate_to_datetime(m.get("Date")) if m.get("Date") else None
                    age_min = (time.time() - ts.timestamp()) / 60 if ts else 0
                    if age_min > minutes:
                        continue
                    frm = self._hdr(m.get("From")); sub = self._hdr(m.get("Subject")); to = self._hdr(m.get("To")).lower()
                    if self.alias and self.alias not in to:
                        continue
                    if hint and hint.lower() not in f"{frm} {sub}".lower():
                        continue
                    out.append({"from": frm, "subject": sub, "to": to, "date": m.get("Date", ""), "text": self._text(m)[:4000], "snippet": ""})
                    if len(out) >= limit:
                        break
        except Exception as e:
            self.last_error = str(e)[:160]
            self.log("idmail_error", error=self._explain(e))
        return out

    @staticmethod
    def _hdr(v):
        if not v:
            return ""
        parts = email.header.decode_header(v)
        return "".join(p.decode(enc or "utf-8", "replace") if isinstance(p, bytes) else p for p, enc in parts)

    @staticmethod
    def _text(m):
        plain, html_ = "", ""
        for part in (m.walk() if m.is_multipart() else [m]):
            ct = part.get_content_type()
            if ct not in ("text/plain", "text/html") or part.get("Content-Disposition", "").startswith("attachment"):
                continue
            try:
                body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
            except Exception:
                continue
            if ct == "text/plain" and not plain:
                plain = body
            elif ct == "text/html" and not html_:
                html_ = body
        if plain.strip():
            return plain
        t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html_, flags=re.S | re.I)
        t = re.sub(r"<a [^>]*href=\"([^\"]+)\"[^>]*>", r" \1 ", t, flags=re.I)             # keep links as text: confirmation urls
        t = re.sub(r"<[^>]+>", " ", t)
        return re.sub(r"\s+", " ", unescape(t))

    # ---- the two things the sign-up skill needs --------------------------------------------------------
    def find_code(self, sender_hint="", since_minutes=15, tries=6, wait=20):
        """Poll (spaced) for a fresh 4–8 digit verification code, preferably from a mail mentioning sender_hint.
        Returns (code, mail) or (None, None)."""
        hint = (sender_hint or "").lower().split(".")[0]
        for i in range(tries):
            for m in self.recent(minutes=since_minutes, hint=hint):
                if not looks_like_verification(m):
                    continue
                txt = f"{m['subject']} {m['text']}"
                if not CODE_WORDS.search(txt):
                    continue
                m2 = CODE_NEAR.search(txt) or CODE_RE.search(txt)
                if m2:
                    code = re.sub(r"\D", "", m2.group(1))
                    if 4 <= len(code) <= 8:
                        self.log("idmail_code_found", sender=m["from"][:60])
                        return code, m
            if i < tries - 1:
                time.sleep(wait)
        return None, None

    def find_link(self, sender_hint="", pattern=r"(verify|confirm|activate|conferma|verifica|attiva)", since_minutes=15, tries=6, wait=20):
        """Poll for a confirmation link in a fresh mail. Returns (url, mail) or (None, None)."""
        hint = (sender_hint or "").lower().split(".")[0]
        for i in range(tries):
            for m in self.recent(minutes=since_minutes, hint=hint):
                if not looks_like_verification(m):
                    continue
                for url in re.findall(r"https?://[^\s\"'<>\)\]]+", m["text"]):
                    if re.search(pattern, url, re.I) or re.search(pattern, m["subject"], re.I):
                        if re.search(r"unsubscribe|disiscriv|privacy|terms|facebook\.com|instagram\.com|twitter\.com", url, re.I):
                            continue
                        self.log("idmail_link_found", sender=m["from"][:60])
                        return url.rstrip(".,;"), m
            if i < tries - 1:
                time.sleep(wait)
        return None, None


class _Conn:
    """One IMAP login for one lookup; always logged out."""
    def __init__(self, outer):
        self.o = outer
    def __enter__(self):
        self.c = imaplib.IMAP4_SSL(self.o.host, self.o.port, timeout=30)
        self.c.login(self.o.email, self.o.password)
        return self.c
    def __exit__(self, *a):
        try:
            self.c.logout()
        except Exception:
            pass
