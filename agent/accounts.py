"""The agent's own identity and accounts (milestone 16) + CAPTCHA attempts (milestone 15).

Identity: BAI_ACCOUNT_EMAIL / BAI_ACCOUNT_PASSWORD in .secrets/env (never in git, never logged). The agent uses them to sign
up on sites that need an account (marketplaces to read reviews, Canva-like tools, forums), remembers each account in
state/accounts.json (site, username, when, status) and fetches e-mail verification codes/links through its own Gmail (google.py).

Rules the owner set:
  • sign-ups are encouraged; the FIRST sign-up on any new site is announced (one line) — the owner can say stop.
  • never the owner's own accounts, never money, never a customer message: those stay owner-in-the-loop.
  • CAPTCHAs: try (simple checkbox / image-text via eyes / audio not attempted); if it fails twice, try another route
    (another site, another search engine) and, when the task really needs it, ask the owner for one tap.

Everything here drives the Browser through the numbered-item API (b.read/click/type) on the hands thread.
"""
import json
import os
import re
import urllib.parse
import time

from . import config

ACCOUNTS = config.STATE_DIR / "accounts.json"
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1", "0.0.0.0")   # fakes + rehearsal stages: always fine to practice on
NEVER_SIGN_UP = re.compile(r"paypal|stripe|bank|banca|revolut|wise\.com|coinbase|binance|amazon\.(?:com|it|de|fr|es|co\.uk)/ap/register|apple\.com|icloud|google\.com/accounts|accounts\.google|microsoft\.com|live\.com|facebook\.com/r\.php|instagram\.com/accounts/emailsignup|tiktok\.com/signup|x\.com/i/flow/signup", re.I)


class Identity:
    def __init__(self):
        self.email = os.environ.get("BAI_ACCOUNT_EMAIL", "").strip()
        self.password = os.environ.get("BAI_ACCOUNT_PASSWORD", "").strip()
        self.first_name = os.environ.get("BAI_ACCOUNT_FIRST", "Business")
        self.last_name = os.environ.get("BAI_ACCOUNT_LAST", "AI")
        self.username = os.environ.get("BAI_ACCOUNT_USERNAME", "") or (self.email.split("@")[0] if self.email else "")
        self.birthday = os.environ.get("BAI_ACCOUNT_BIRTHDAY", "1995-06-15")
        self.country = os.environ.get("BAI_ACCOUNT_COUNTRY", "Italy")
        self.city = os.environ.get("BAI_ACCOUNT_CITY", "Milano")

    def ready(self):
        return bool(self.email and self.password)

    def describe(self):
        if not self.ready():
            return "my own account: not set (add BAI_ACCOUNT_EMAIL and BAI_ACCOUNT_PASSWORD to .secrets/env)"
        return f"my own account: {self.email} (password kept in .secrets/env)"

    def value_for(self, label):
        """What to type into a sign-up field, from its label/placeholder/name."""
        l = (label or "").lower()
        if re.search(r"e-?mail|mail address|indirizzo", l):
            return self.email
        if re.search(r"confirm.*pass|repeat.*pass|ripeti|conferma.*pass|password again|re-?enter", l):
            return self.password
        if re.search(r"pass(word|code)?|parola", l):
            return self.password
        if re.search(r"user ?name|nickname|nome utente|handle|display name", l):
            return self.username
        if re.search(r"first ?name|given|nome\b|vorname|prénom", l) and "last" not in l and "full" not in l:
            return self.first_name
        if re.search(r"last ?name|surname|family|cognome|nachname", l):
            return self.last_name
        if re.search(r"full ?name|your name|nome e cognome|^name$|\bname\b", l):
            return f"{self.first_name} {self.last_name}"
        if re.search(r"birth|nascita|dob|age", l):
            return self.birthday
        if re.search(r"country|paese|nazione", l):
            return self.country
        if re.search(r"city|città|town", l):
            return self.city
        if re.search(r"phone|telefono|mobile|cellulare", l):
            return None                                             # no phone: skip; the owner decides if a site insists
        if re.search(r"company|azienda|business name|shop name|store name", l):
            return "Business AI"
        return None


SITE_CREDS = config.pathlib.Path(os.environ.get("BAI_SITES_FILE") or (config.ROOT / ".secrets" / "sites.json"))     # {"vinted.it": {"email", "password", "login"}} — the owner's hand-made accounts, never in git
LOGIN_URLS = {"vinted.it": "https://www.vinted.it/member/signup/select_type?ref_url=%2F", "vinted.com": "https://www.vinted.com/member/signup/select_type",
              "temu.com": "https://www.temu.com/it/login.html", "shein.com": "https://it.shein.com/user/auth/login", "subito.it": "https://areariservata.subito.it/login_form",
              "wallapop.com": "https://it.wallapop.com/login", "ebay.it": "https://signin.ebay.it/", "aliexpress.com": "https://login.aliexpress.com/",
              "banggood.com": "https://www.banggood.com/login.html", "dhgate.com": "https://www.dhgate.com/login.html", "amazon.it": "https://www.amazon.it/ap/signin",
              "etsy.com": "https://www.etsy.com/signin", "depop.com": "https://www.depop.com/login/"}


class Accounts:
    LOST_IDENTITIES = ("busynessai001@gmail.com",)   # mailboxes we no longer have (banned 2026-09-10): accounts made with them are unreachable
    notify_photo = None             # set by core: (jpeg_bytes, caption) → the owner's phone

    def __init__(self, google=None, log=None, notify=None, ask=None):
        self.id = Identity()
        self.google = google
        self.log = log or (lambda kind, **f: None)
        self.notify = notify or (lambda t: None)
        self.ask = ask                                              # callable(question, options, timeout) -> label|None
        self.data = self._load()
        from .idmail import IdMail
        self.mail = IdMail(log=self.log)                            # plain IMAP, read-only: where verification codes arrive
        self._retire_lost()

    # ---- the owner's own hand-made accounts (site → e-mail + password) ----------------------------
    @staticmethod
    def _norm_site(site):
        return re.sub(r"^(www|it|m)\.", "", re.sub(r"^https?://", "", (site or "").strip().lower()).split("/")[0])

    def site_creds(self, url_or_site):
        """Credentials the owner gave for this site (.secrets/sites.json), or None → the identity defaults."""
        site = self._norm_site(url_or_site)
        try:
            d = json.loads(SITE_CREDS.read_text()) if SITE_CREDS.exists() else {}
        except Exception:
            d = {}
        for k, v in d.items():
            if site == k or site.endswith("." + k) or k.endswith("." + site.split(".")[0] + "." + site.split(".")[-1]) or site.split(".")[0] == k.split(".")[0]:
                return v
        return None

    def set_site_creds(self, site, email, password, login_url=None):
        """'/accounts set vinted.it me@x.com pass' — the owner signed up by hand; I only log in from now on."""
        site = self._norm_site(site)
        if not site or "." not in site:
            site = {"vinted": "vinted.it", "temu": "temu.com", "shein": "shein.com", "subito": "subito.it", "wallapop": "wallapop.com", "ebay": "ebay.it",
                    "aliexpress": "aliexpress.com", "banggood": "banggood.com", "dhgate": "dhgate.com", "amazon": "amazon.it", "etsy": "etsy.com", "depop": "depop.com"}.get(site, site)
        if not (re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}(?::\d+)?", site) or re.fullmatch(r"(?:localhost|\d{1,3}(?:\.\d{1,3}){3})(?::\d+)?", site)):
            return None
        try:
            d = json.loads(SITE_CREDS.read_text()) if SITE_CREDS.exists() else {}
        except Exception:
            d = {}
        d[site] = {"email": email.strip(), "password": password, "login": login_url or LOGIN_URLS.get(site, ""), "t": time.strftime("%Y-%m-%d %H:%M"), "by": "owner"}
        SITE_CREDS.parent.mkdir(parents=True, exist_ok=True)
        SITE_CREDS.write_text(json.dumps(d, ensure_ascii=False, indent=1))
        try:
            os.chmod(SITE_CREDS, 0o600)
        except Exception:
            pass
        # the account book: this site is now "active, made by the owner" — never a sign-up attempt again
        a = next((x for x in self.data["accounts"] if x["site"] == site), None)
        rec = {"site": site, "email": email.strip(), "status": "active", "note": "account made by the owner — I only log in", "t": time.strftime("%Y-%m-%d %H:%M")}
        if a:
            a.update(rec)
        else:
            self.data["accounts"].append(rec)
        self._save()
        return site

    def forget_site_creds(self, site):
        site = self._norm_site(site)
        try:
            d = json.loads(SITE_CREDS.read_text()) if SITE_CREDS.exists() else {}
        except Exception:
            d = {}
        hit = [k for k in d if k == site or k.split(".")[0] == site.split(".")[0]]
        for k in hit:
            d.pop(k, None)
        SITE_CREDS.write_text(json.dumps(d, ensure_ascii=False, indent=1))
        return bool(hit)

    def creds_text(self):
        try:
            d = json.loads(SITE_CREDS.read_text()) if SITE_CREDS.exists() else {}
        except Exception:
            d = {}
        if not d:
            return "No hand-made site logins yet. Give me one with: /accounts set <site> <email> <password> (kept in .secrets/sites.json on this machine, never in git)."
        return "Site logins you gave me (passwords never shown):\n" + "\n".join(f"• {k}: {v.get('email', '?')} (since {v.get('t', '?')[:10]})" for k, v in d.items())

    def _retire_lost(self):
        """Accounts created with a mailbox we lost are marked so they are never logged into or re-used."""
        changed = False
        for a in self.data.get("accounts", []):
            if a.get("email") in self.LOST_IDENTITIES and a.get("status") != "lost":
                a["status"] = "lost"; a["note"] = "mailbox banned — account unreachable; a new one is made with the current identity"; changed = True
        if changed:
            self._save()

    def mail_ok(self):
        """Can I receive verification codes right now? IMAP mailbox first, the old Google path only if it still works."""
        if self.mail.configured():
            return True
        return bool(self.google and self.google.connected())

    def _find_code(self, hint, tries=8, wait=15):
        local = self.is_local(f"http://{hint}/") or hint in ("127", "localhost")
        if local:                                                   # my own practice stages: their codes come through the stage's fake mail, never the real mailbox
            mb = getattr(self, "mailbox", None)
            if mb:
                return mb.code(hint, tries=2, wait=1)
            if self.google and self.google.connected():
                return self.google.find_code(sender_hint=hint, tries=2, wait=1)
            return None, None
        if self.mail.configured():
            return self.mail.find_code(sender_hint=hint, tries=tries, wait=wait)
        mb = getattr(self, "mailbox", None)
        if mb:
            return mb.code(hint, tries=tries, wait=wait)
        if self.google and self.google.connected():
            return self.google.find_code(sender_hint=hint, tries=tries, wait=wait)
        return None, None

    def _find_link(self, hint, tries=3, wait=15):
        if self.is_local(f"http://{hint}/") or hint in ("127", "localhost"):
            if self.google and self.google.connected():
                return self.google.find_link(sender_hint=hint, tries=1, wait=0)
            return None, None
        if self.mail.configured():
            return self.mail.find_link(sender_hint=hint, tries=tries, wait=wait)
        if self.google and self.google.connected():
            return self.google.find_link(sender_hint=hint, tries=tries, wait=wait)
        return None, None

    # ---- memory of accounts -----------------------------------------------------------
    def _load(self):
        try:
            d = json.loads(ACCOUNTS.read_text())
        except Exception:
            d = {}
        d.setdefault("accounts", [])
        d.setdefault("approved", [])        # owner-approved real sites (item 6: real sign-ups need approval)
        d.setdefault("refused", [])         # owner said never
        return d

    def _save(self):
        ACCOUNTS.parent.mkdir(parents=True, exist_ok=True)
        ACCOUNTS.write_text(json.dumps(self.data, indent=1))

    def site_of(self, url):
        return re.sub(r"^www\.", "", re.sub(r"^https?://", "", url).split("/")[0]).lower()

    @staticmethod
    def _base(url):
        m = re.match(r"^(https?://[^/]+)", url)
        return m.group(1) if m else "https://" + url.split("/")[0]

    def known(self, url):
        site = self.site_of(url)
        a = next((a for a in self.data["accounts"] if a["site"] == site and a.get("status") != "lost"), None)
        if a is None:
            c = self.site_creds(url)
            if c:
                a = {"site": site, "email": c.get("email", ""), "status": "active", "note": "account made by the owner", "t": c.get("t", "")}
        return a

    # ---- safe sign-up: fakes first, real sites only when approved (item 6) --------------------------
    def is_local(self, url):
        u = urllib.parse.urlparse(url)
        if u.scheme == "file" or not u.hostname:      # my own stage / local files: always fine to practice on
            return True
        host = u.hostname.lower()
        return host in LOCAL_HOSTS or host.endswith(".localhost")

    OWNER_APPROVED = ("temu.com",)      # the owner asked for these accounts in so many words (2026-09-10) — no question needed

    def approved(self, url):
        site = self.site_of(url)
        return site in self.data.setdefault("approved", []) or any(site == o or site.endswith("." + o) for o in self.OWNER_APPROVED)

    def allow_site(self, site):
        """Owner approves a real site for sign-up. Returns the normalized site, or None if it is not a site."""
        site = re.sub(r"^www\.", "", re.sub(r"^https?://", "", (site or "").strip().lower()).split("/")[0])
        if not re.fullmatch(r"[a-z0-9.\-]+\.[a-z]{2,}(?::\d+)?", site):
            return None
        if NEVER_SIGN_UP.search(site):
            return None                                             # money / big-platform logins: never approvable
        if site not in self.data.setdefault("approved", []):
            self.data["approved"].append(site)
            self._save()
        return site

    def forget_site(self, site):
        site = re.sub(r"^www\.", "", re.sub(r"^https?://", "", (site or "").strip().lower()).split("/")[0])
        if site in self.data.setdefault("approved", []):
            self.data["approved"].remove(site)
            self._save()
            return True
        return False

    def _gate(self, url):
        """Pre-check before any sign-up attempt: (True, 'ok') | (False, 'never-sign-up'|'refused') | (None, 'ask')."""
        if NEVER_SIGN_UP.search(url):
            return False, "never-sign-up"
        site = self.site_of(url)
        if site in self.data.setdefault("refused", []):
            return False, "refused"
        if self.is_local(url) or self.approved(url):
            return True, "ok"
        return None, "ask"

    def remember(self, url, status, note=""):
        site = self.site_of(url)
        a = self.known(url)
        if a:
            a.update(status=status, note=note[:200], t=time.strftime("%Y-%m-%d %H:%M"))
        else:
            creds = self.site_creds(url) or {}
            self.data["accounts"].append({"site": site, "email": creds.get("email") or self.id.email, "status": status, "note": note[:200], "t": time.strftime("%Y-%m-%d %H:%M")})
        self._save()
        self.log("account", site=site, status=status)

    def list_text(self):
        head = self.id.describe() + "\n" + self.mail.describe()
        if not self.data["accounts"]:
            return head + "\nNo site accounts yet — I create them when a task needs one (you get one line when I do)."
        rows = "\n".join(f"• {a['site']} — {a['status']} ({a['t']})" + (f" · {a['note']}" if a.get("note") else "") for a in self.data["accounts"][-20:])
        out = f"{head}\nSites where I have an account:\n{rows}"
        if self.data.get("approved"):
            out += "\nApproved for sign-up: " + ", ".join(self.data["approved"])
        return out

    # ---- the sign-up / login skill (runs on the hands thread with a Browser) --------------------
    SIGNUP_WORDS = re.compile(r"\b(sign ?up|create (?:an |your )?account|register|registrati|crea (?:un )?account|iscriviti|join (?:free|now)|get started)\b", re.I)
    LOGIN_WORDS = re.compile(r"\b(log ?in|sign ?in|accedi|entra|login)\b", re.I)
    SUBMIT_WORDS = re.compile(r"^(sign ?up|create (?:my )?account|register|registrati|crea account|continue|continua|next|avanti|submit|join|get started|agree (?:and|&) (?:continue|join)|log ?in|sign ?in|accedi|verify|verifica|confirm|conferma)$", re.I)
    CODE_WORDS = re.compile(r"\b(verification code|codice di verifica|enter (?:the )?code|inserisci il codice|we sent (?:you )?(?:a|an) (?:code|e-?mail)|check your (?:e-?mail|inbox)|confirm your e-?mail|6-digit|one-time)\b", re.I)

    def ensure_account(self, b, url, why="", allow_signup=True, quiet=None):
        """Make sure the agent is logged in on the site of `url`. Returns (ok, note). quiet: no owner line (default: quiet on my own stages)."""
        self._quiet = bool(quiet)                      # callers that own the site (my rehearsal stage) pass quiet=True
        if not self.id.ready():
            return False, "I have no account credentials of my own (BAI_ACCOUNT_EMAIL/PASSWORD missing)."
        if NEVER_SIGN_UP.search(url):
            return False, "that site is on my never-sign-up list (money, big platforms with strict robot bans)."
        a = self.known(url)
        if a and a["status"] in ("blocked", "pending", "failed") and a.get("email") == self.id.email and not self.site_creds(url):
            a = None                                                    # an earlier try stopped at a puzzle / a code: not final — try again now
        if a and a["status"] == "active":
            told = getattr(self, "_login_told", set())
            if self.site_creds(url) and not getattr(self, "_quiet", False) and a["site"] not in told and not self.is_local(url):
                told.add(a["site"]); self._login_told = told                 # once per site per run, never on my practice stages
                self.notify(f"🔑 Logging in to {a['site']} with the account you gave me ({a.get('email') or self.id.email}).")
            ok, note = self.login(b, url)
            if ok:
                return True, "logged in"
            self.log("login_failed", site=a["site"], note=note[:80])
            if self.site_creds(url):
                if re.search(r"puzzle|captcha|security check", note, re.I):
                    return False, f"{a['site']}: your login is fine, but the site shows a picture puzzle before letting me in — {note}. One tap from you on the live screen / Chrome window and I keep the session."
                if re.search(r"rejected|incorrect|wrong password|did not work", note, re.I):
                    return False, f"{a['site']}: the site rejected the login you gave me ({note}). Check the e-mail/password with /accounts set {a['site']} … (I never sign up there myself)."
                return False, f"{a['site']}: could not log in with your login — {note}"
            return False, f"I have an account on {a['site']} but could not log in: {note}"
        if not allow_signup:
            return False, "no account there and sign-up not allowed for this task"
        gate, why_gate = self._gate(url)
        site = self.site_of(url)
        if gate is False:
            if why_gate == "refused":
                return False, f"you told me never to sign up on {site}."
            return False, "that site is on my never-sign-up list (money, big platforms with strict robot bans)."
        if gate is None:
            if not self.ask:
                return False, f"{site} is new to me — say '/accounts allow {site}' first and I'll sign up."
            ans = self.ask(f"\U0001F195 Sign up on {site} with my own e-mail ({self.id.email}){' — ' + why if why else ''}?",
                           ["Allow once", "Always allow", "Never"], 300)
            if ans == "Always allow":
                self.allow_site(site)
            elif ans == "Never":
                self.data.setdefault("refused", []).append(site)
                self._save()
                return False, f"noted — I won't sign up on {site}."
            elif ans != "Allow once":
                return False, f"sign-up on {site} needs your tap first ('/accounts allow {site}')."
        if not a:
            if not getattr(self, "_quiet", False):
                self.notify(f"🆕 I'm creating an account on {self.site_of(url)} with my own e-mail ({self.id.email}){' — ' + why if why else ''}. Say 'stop' if you don't want that.")
        return self.signup(b, url)

    def _fill_visible_form(self, b, max_fields=8):
        """Type identity values into the visible form fields by label. Returns (filled labels, unknown labels).
        On a site whose account the owner made by hand, that e-mail/password is used instead of the identity defaults."""
        b.read()
        filled, unknown = [], []
        creds = None
        try:
            creds = self.site_creds(b.page.url)
        except Exception:
            creds = None
        for it in b.items:
            if it["role"] not in ("textbox", "input", "email", "password", "tel", "combobox", "select") or len(filled) >= max_fields:
                continue
            label = it.get("label") or ""
            v = self.id.value_for(label)
            if creds and v is not None:
                if v == self.id.email and creds.get("email"):
                    v = creds["email"]
                elif v == self.id.password and creds.get("password"):
                    v = creds["password"]
            if v is None:
                if label and not re.search(r"search|cerca|promo|coupon|referral", label, re.I):
                    unknown.append(label[:30])
                continue
            try:
                b.type(it["n"], v)
                filled.append(label[:30])
            except Exception as e:
                self.log("signup_type_failed", label=label[:30], error=str(e)[:60])
        # tick consent boxes (terms), never marketing boxes
        for it in b.items:
            if it["role"] == "checkbox" and re.search(r"terms|conditions|privacy|agree|accetto|condizioni|age|18", it.get("label") or "", re.I) and not re.search(r"newsletter|marketing|offers|promo", it.get("label") or "", re.I):
                try:
                    b.click(it["n"])
                except Exception:
                    pass
        return filled, unknown

    def _submit(self, b):
        b.read()
        for it in b.items:
            if it["role"] in ("button", "submit") and self.SUBMIT_WORDS.match((it.get("label") or "").strip()):
                b.click(it["n"])
                return it.get("label")
        for it in b.items:                                                   # Enter in the last field as a fallback
            if it["role"] in ("textbox", "input", "password", "email"):
                last = it
        try:
            b.page.keyboard.press("Enter")
            return "Enter"
        except Exception:
            return None

    def _open_signup(self, b, url):
        b.open(url)
        b.read()
        # a combined "Accedi / Registrati" page (Temu, many shops): one e-mail box that starts both flows → this IS the form
        has_mail_box = any(it["role"] in ("textbox", "input", "email") and re.search(r"e-?mail|telefono|phone", it.get("label") or "", re.I) for it in b.items)
        if has_mail_box and re.search(r"accedi\s*/\s*registrati|sign in\s*/\s*(?:sign up|register|join)|log in or (?:sign up|register)|registrati o accedi|continue with e-?mail", b.extract_text()[:4000], re.I):
            return True
        for it in b.items:
            if it["role"] in ("link", "button") and self.SIGNUP_WORDS.search(it.get("label") or ""):
                b.click(it["n"])
                return True
        for path in ("/signup", "/register", "/sign-up", "/account/register", "/users/sign_up", "/registrati"):
            try:
                b.open(f"{self._base(url)}{path}")
                if b.status() == "ok" and re.search(r"password", b.extract_text(), re.I):
                    return True
            except Exception:
                continue
        return False

    def signup(self, b, url):
        site = self.site_of(url)
        t0 = time.time()
        try:
            if not self._open_signup(b, url):
                self.remember(url, "failed", "no sign-up form found")
                return False, f"I couldn't find a sign-up form on {site}."
            st = b.status()
            if st == "captcha" or self._puzzle_shown(b):
                if not self._pass_puzzle(b, site, url):
                    self.remember(url, "blocked", "captcha at sign-up")
                    return False, f"{site} showed a picture puzzle at sign-up that was not passed."
            filled, unknown = self._fill_visible_form(b)
            if not any(re.search(r"mail", f, re.I) for f in filled) and not any(re.search(r"pass", f, re.I) for f in filled):
                self.remember(url, "failed", "form fields not recognised: " + ", ".join(unknown[:4]))
                return False, f"the sign-up form on {site} has fields I don't recognise ({', '.join(unknown[:4]) or 'none visible'})."
            pressed = self._submit(b)
            time.sleep(2)
            for _round in range(4):                                          # multi-step forms: more fields, code, captcha
                st = b.status()
                text = b.extract_text()[:4000]
                if (st == "captcha" or self._puzzle_shown(b)) and not self._pass_puzzle(b, site, url):
                    self.remember(url, "blocked", "captcha after submit")
                    return False, f"{site} asked for a picture puzzle that was not passed."
                if self.CODE_WORDS.search(text):
                    if not self.enter_code(b, site):
                        self.remember(url, "pending", "verification code not found in my mailbox")
                        return False, f"{site} sent a verification code but I couldn't find it in my mailbox."
                    time.sleep(2)
                    continue
                if re.search(r"already (?:registered|exists|in use|taken)|già registrat|esiste già", text, re.I):
                    self.remember(url, "active", "already existed → logging in")
                    return self.login(b, url)
                more, _ = self._fill_visible_form(b)
                if more:
                    self._submit(b)
                    time.sleep(2)
                    continue
                break
            text = b.extract_text()[:3000]
            if re.search(r"\b(error|invalid|non valido|errore|try again|riprova)\b", text, re.I) and re.search(r"password|e-?mail", text, re.I):
                self.remember(url, "failed", "site rejected the form")
                return False, f"{site} rejected my details."
            self.remember(url, "active", f"signed up in {time.time() - t0:.0f}s")
            self.check_confirmation_mail(b, site)
            return True, f"signed up on {site} as {self.id.email}"
        except Exception as e:
            self.log("signup_error", site=site, error=str(e)[:120])
            self.remember(url, "failed", str(e)[:80])
            return False, f"sign-up on {site} failed: {str(e)[:80]}"

    def login(self, b, url):
        site = self.site_of(url)
        recent = getattr(self, "_login_recent", {}).get(site)
        if recent and time.time() - recent[0] < 1800 and not recent[1]:
            return False, recent[2] + " (not retried — same job, same answer; I try again on the next job)"
        ok, note = self._login(b, url, site)
        self._login_recent = getattr(self, "_login_recent", {})
        self._login_recent[site] = (time.time(), ok, note)
        return ok, note

    def _login(self, b, url, site):
        try:
            creds = self.site_creds(url) or {}
            start = creds.get("login") or LOGIN_URLS.get(site) or LOGIN_URLS.get(re.sub(r"^(www|it|m)\.", "", site)) or url
            b.open(start)
            b.read()
            for it in b.items:
                if it["role"] in ("link", "button") and self.LOGIN_WORDS.search(it.get("label") or "") and not self.SIGNUP_WORDS.search(it.get("label") or ""):
                    b.click(it["n"])
                    break
            filled, _ = self._fill_visible_form(b, max_fields=3)
            if filled and not any(re.search(r"pass", f, re.I) for f in filled) and any(re.search(r"mail|telefono|phone", f, re.I) for f in filled):
                pass                                                         # an e-mail-first login (Temu, Shein): submit and the password step follows
            elif not any(re.search(r"pass", f, re.I) for f in filled):
                for path in ("/login", "/signin", "/sign-in", "/account/login", "/users/sign_in", "/accedi"):
                    try:
                        b.open(f"{self._base(url)}{path}")
                        filled, _ = self._fill_visible_form(b, max_fields=3)
                        if filled:
                            break
                    except Exception:
                        continue
            if not filled:
                return False, f"no login form found on {site}"
            self._submit(b)
            time.sleep(2)
            for _round in range(3):                                          # e-mail first → puzzle → password / code (Temu-style)
                text = b.extract_text()[:3000]
                if (b.status() == "captcha" or self._puzzle_shown(b)) and not self._pass_puzzle(b, site, url):
                    return False, f"{site} wants a picture puzzle at login that was not passed"
                if self.CODE_WORDS.search(text) and not self.enter_code(b, site):
                    return False, f"{site} asked for a login code I couldn't find"
                more, _ = self._fill_visible_form(b, max_fields=3)
                if more:
                    self._submit(b)
                    time.sleep(2)
                    continue
                break
            text = b.extract_text()[:3000]
            if re.search(r"incorrect|wrong password|invalid|non valid|errat", text, re.I):
                self.remember(url, "failed", "login rejected")
                return False, f"{site} rejected my password"
            self.remember(url, "active", "logged in")
            return True, "logged in"
        except Exception as e:
            return False, f"login on {site} failed: {str(e)[:80]}"

    # ---- e-mail codes / links --------------------------------------------------------------------
    def enter_code(self, b, site):
        """Fetch the fresh code from my mailbox (IMAP) and type it in; True on success."""
        if not self.mail_ok():
            self.log("code_needed_no_mailbox", site=site)
            return False
        hint = site.split(".")[0]
        code, mail = self._find_code(hint, tries=8, wait=15)
        if not code:
            link, mail = self._find_link(hint, tries=2, wait=10)
            if link:
                b.open(link)
                return True
            return False
        b.read()
        boxes = [it for it in b.items if it["role"] in ("textbox", "input", "tel", "number") and re.search(r"code|codice|otp|digit|verif", (it.get("label") or "") + " " + (it.get("name") or ""), re.I)]
        if not boxes:
            boxes = [it for it in b.items if it["role"] in ("textbox", "input", "tel", "number")]
        if len(boxes) >= len(code) and all(len(bx.get("value") or "") <= 1 for bx in boxes[:len(code)]):
            for bx, ch in zip(boxes[:len(code)], code):                       # one box per digit
                b.type(bx["n"], ch)
        elif boxes:
            b.type(boxes[0]["n"], code)
        else:
            return False
        self._submit(b)
        self.log("code_entered", site=site)
        return True

    def check_confirmation_mail(self, b, site):
        """After a sign-up, open the confirmation link if one arrives (does not block long)."""
        if not self.mail_ok():
            return False
        link, mail = self._find_link(site.split(".")[0], tries=2, wait=10)
        if link:
            try:
                b.open(link)
                self.log("confirmation_link_opened", site=site)
                return True
            except Exception:
                pass
        return False

    # ---- CAPTCHA attempts --------------------------------------------------------------------------
    def solve_captcha(self, b, site, eyes=None):
        """Try the simple kinds: a checkbox ("I'm not a robot"), a text-in-image with the eyes, a 'press and hold'.
        Two failed attempts → give up (the caller picks another route or asks the owner)."""
        eyes = eyes or getattr(self, "eyes", None)
        try:
            texts = [b.page.inner_text("body")[:6000]]
            for fr in b.page.frames:
                if fr is not b.page.main_frame:
                    try:
                        texts.append(fr.evaluate("() => document.body ? document.body.innerText.slice(0, 3000) : ''"))
                    except Exception:
                        pass
            if any(re.search(r"clicca su tutti|select all|seleziona tutte|click all|oggetti duplicati|immagini corrispondenti|drag the slider|trascina il cursore", t, re.I) for t in texts):
                self.log("captcha_image_grid", site=site)
                return False                                                # an image-grid / slider puzzle: not for a blind click — the owner's tap
        except Exception:
            pass
        for attempt in range(2):
            try:
                b.read()
                box = next((it for it in b.items if it["role"] == "checkbox" or re.search(r"not a robot|non sono un robot|verify you are human|human", it.get("label") or "", re.I)), None)
                if box:
                    b.click(box["n"])
                    time.sleep(2)
                    if b.status() == "captcha":
                        self._submit(b)
                        time.sleep(3)
                    if b.status() != "captcha":
                        self.log("captcha_passed", site=site, how="checkbox")
                        return True
                # frames: reCAPTCHA / hCaptcha / Turnstile render the checkbox inside an iframe
                for fr in b.page.frames:
                    try:
                        if re.search(r"recaptcha|hcaptcha|turnstile|challenges\.cloudflare", fr.url or "", re.I):
                            el = fr.query_selector("#recaptcha-anchor, .recaptcha-checkbox, #checkbox, input[type=checkbox], .ctp-checkbox-label, label")
                            if el:
                                el.click(timeout=4000)
                                time.sleep(4)
                                if b.status() != "captcha":
                                    self.log("captcha_passed", site=site, how="frame-checkbox")
                                    return True
                    except Exception:
                        continue
                # text-in-image captcha: read it with the eyes
                if eyes and getattr(eyes, "ready", lambda: False)():
                    img = next((it for it in b.items if it["role"] == "img" and re.search(r"captcha|code|verify", (it.get("label") or "") + (it.get("href") or ""), re.I)), None)
                    field = next((it for it in b.items if it["role"] in ("textbox", "input") and re.search(r"captcha|code|characters|text", it.get("label") or "", re.I)), None)
                    if img and field:
                        shot = b.screenshot()
                        txt = eyes.look(shot, "Read the distorted characters in the CAPTCHA image exactly. Reply with the characters only.", max_tokens=12) or ""
                        txt = re.sub(r"[^A-Za-z0-9]", "", txt)
                        if 3 <= len(txt) <= 8:
                            b.type(field["n"], txt)
                            self._submit(b)
                            time.sleep(3)
                            if b.status() != "captcha":
                                self.log("captcha_passed", site=site, how="eyes")
                                return True
                # press-and-hold buttons
                hold = next((it for it in b.items if re.search(r"press (?:and|&) hold|tieni premuto", it.get("label") or "", re.I)), None)
                if hold:
                    el = b._el(hold["n"])
                    box_ = el.bounding_box()
                    if box_:
                        b.page.mouse.move(box_["x"] + box_["width"] / 2, box_["y"] + box_["height"] / 2)
                        b.page.mouse.down(); time.sleep(6); b.page.mouse.up()
                        time.sleep(3)
                        if b.status() != "captcha":
                            self.log("captcha_passed", site=site, how="hold")
                            return True
            except Exception as e:
                self.log("captcha_attempt_error", site=site, error=str(e)[:80])
            time.sleep(2)
        self.log("captcha_failed", site=site)
        return False

    PUZZLE_WORDS = re.compile(r"verifica di sicurezza|security verification|clicca su tutti|select all|seleziona tutte le immagini|click all|drag the slider|trascina|sono umano|i am human|i'm not a robot|non sono un robot|completa la verifica|complete the verification", re.I)

    PUZZLE_FRAMES = re.compile(r"verification|verify|captcha|challenge|risk|geetest|recaptcha|hcaptcha|turnstile|arkose|funcaptcha|px-captcha", re.I)

    def _puzzle_shown(self, b):
        """A picture/slider puzzle inside the page (Temu, Shein) that status() may not count as a wall — in the page or in a frame."""
        try:
            if self.PUZZLE_WORDS.search(b.page.inner_text("body")[:6000]):
                return True
            for fr in b.page.frames:
                if fr is b.page.main_frame:
                    continue
                try:
                    if self.PUZZLE_FRAMES.search(fr.url or "") or self.PUZZLE_WORDS.search(fr.evaluate("() => document.body ? document.body.innerText.slice(0, 3000) : ''")):
                        return True
                except Exception:
                    continue
        except Exception:
            return False
        return False

    def _pass_puzzle(self, b, site, url):
        """Simple solvers, then the owner's one tap (with a picture), within the daily budget. True when the puzzle is gone."""
        if self.captcha_budget(site) <= 0:
            return False
        passed = False
        try:
            passed = self.solve_captcha(b, site)
        except Exception:
            passed = False
        if not passed:
            shot = None
            try:
                shot = b.page.screenshot(type="jpeg", quality=70, timeout=6000)
            except Exception:
                pass
            if self.captcha_fallback(site, url, timeout=150, b=b, screenshot=shot):
                time.sleep(1.5)
                passed = b.status() != "captcha" and not self._puzzle_shown(b)
        self.captcha_spent(site, passed)
        if passed:
            try:
                b.save_session()
            except Exception:
                pass
        return passed

    CAPTCHA_DAILY_MAX = 5           # owner's rule: after the 5th failed attempt on a site in a day, leave it alone until tomorrow

    def captcha_budget(self, site):
        """How many attempts are left today on this site (owner taps count as attempts too)."""
        day = time.strftime("%Y-%m-%d")
        rec = self.data.setdefault("captcha_tries", {}).get(site) or {}
        if rec.get("day") != day:
            return self.CAPTCHA_DAILY_MAX
        return max(0, self.CAPTCHA_DAILY_MAX - int(rec.get("n", 0)))

    def captcha_spent(self, site, passed):
        if not passed and site in getattr(self, "_skipped_today", set()):
            self._skipped_today.discard(site)
            return                                                       # the owner chose to skip: no attempt was spent
        day = time.strftime("%Y-%m-%d")
        tries = self.data.setdefault("captcha_tries", {})
        rec = tries.get(site) or {}
        if rec.get("day") != day:
            rec = {"day": day, "n": 0, "passed": 0}
        rec["n"] = int(rec.get("n", 0)) + 1
        rec["passed"] = int(rec.get("passed", 0)) + (1 if passed else 0)
        tries[site] = rec
        self._save()

    def captcha_fallback(self, site, url, timeout=180, b=None, screenshot=None):
        """The task truly needs this page and the simple solvers failed: one tap from the owner — with a picture of the puzzle
        and the live-screen address — then the page is re-checked. Never more than CAPTCHA_DAILY_MAX attempts per site per day."""
        if not self.ask:
            return False
        left = self.captcha_budget(site)
        if left <= 0:
            self.notify(f"🧩 {site}: {self.CAPTCHA_DAILY_MAX} security checks failed today — I leave it alone until tomorrow and use the other sites.")
            return False
        if screenshot and self.notify_photo:
            try:
                self.notify_photo(screenshot, f"🧩 {site} — the security check it shows me right now")
            except Exception:
                pass
        view = os.environ.get("BAI_VIEW_URL") or f"http://localhost:{os.environ.get('BAI_VIEW_PORT', '8765')}"
        ans = self.ask(f"🧩 {site} shows a picture puzzle before letting me in (a one-time thing per session: {left} tap(s) left today). "
                       f"Please solve it in the Chrome window on the PC (or my live screen {view}), then tap Done — I keep the session so it should not come back for a while. "
                       f"Skip it = I leave {site} out of this job. (No answer in {timeout // 60} min = skip.)",
                       ["Done", "Skip it"], timeout)
        if ans != "Done":
            self._skipped_today = getattr(self, "_skipped_today", set()) | {site}
        return ans == "Done"
