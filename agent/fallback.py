"""Fallback contact (marathon item 1): reach the owner when Telegram fails, and be reachable.

Two independent lines, both optional, both tested offline (engine/scripts/score_fallback.py):

1. Gmail two-way — polls the bot's own mailbox for mail FROM the owner's addresses,
   runs each through the normal responder, and emails the answer back. Strangers and
   the bot's own sent mail are silently skipped (no loops, no spam-back).
2. Backup Telegram bot — a second bot token used for critical alerts (e.g. "main line
   down") and for answering /status + quick questions, text-only, never buttons.

Setup (with the owner, once): /fallback status · /fallback allow <email> ·
/fallback forget <email> · /fallback test · /fallback test send · /fallback check on|off|now (daily morning "line alive" mail)
Secrets (.secrets/env): OWNER_EMAILS=a@b.com,c@d.com · FALLBACK_BOT_TOKEN=123:ABC
"""
import email.utils
import json
import os
import re
import time

from . import config

STATE_FILE = config.STATE_DIR / "fallback.json"
REPLY_PREFIX = "Re: [BusinessAI]"
MAX_BODY = 4000


def _addr(from_header):
    return (email.utils.parseaddr(from_header or "")[1] or "").lower().strip()


def authenticated(auth_header):
    """Gmail's own SPF/DKIM verdict for an incoming mail. True when either passed; False when both failed;
    None when the header is missing (local fakes, very old mail) — callers treat None as 'unknown'."""
    a = (auth_header or "").lower()
    if not a:
        return None
    if re.search(r"\b(dkim|spf)=pass\b", a):
        return True
    if re.search(r"\b(dkim|spf)=(fail|softfail|permerror|temperror|none)\b", a):
        return False
    return None


def strip_quotes(text):
    """Drop quoted history, 'On ... wrote:' blocks and signatures from an email body."""
    lines = (text or "").replace("\r", "").split("\n")
    out = []
    for ln in lines:
        s = ln.strip()
        if s == "--" or s.startswith("---"):
            break
        if s.startswith(">"):
            continue
        if re.match(r"^On .{5,80} wrote:$", s):
            break
        out.append(ln)
    return "\n".join(out).strip()


class BackupBot:
    """The second Telegram bot: alerts out, /status + quick answers back (text only)."""

    def __init__(self, token=None, owner_id_fn=None, log=None):
        from .telegram import Bot
        self.token = token if token is not None else os.environ.get("FALLBACK_BOT_TOKEN", "")
        self.owner_id_fn = owner_id_fn or (lambda: 0)
        self.log = log or (lambda kind, **f: None)
        self.bot = Bot(token=self.token, timeout=20) if self.token else None

    def configured(self):
        return bool(self.bot)

    def send(self, text):
        """Send the owner a plain-text alert through the backup bot. Never raises."""
        if not self.bot or not self.owner_id_fn():
            return False
        try:
            self.bot.send(self.owner_id_fn(), text)
            self.log("fallback_backup_sent", chars=len(text))
            return True
        except Exception as e:
            self.log("fallback_backup_failed", error=str(e)[:160])
            return False


class Fallback:
    def __init__(self, google=None, log=None):
        self.google = google
        self.log = log or (lambda kind, **f: None)
        self.interval = int(os.environ.get("FALLBACK_INTERVAL", "300") or 300)
        self.owner_id_fn = lambda: 0
        self.backup = BackupBot(log=self.log)
        self.backup.owner_id_fn = lambda: self.owner_id_fn()
        self.state = self._load()

    # ---- state -----------------------------------------------------------
    def _load(self):
        try:
            d = json.loads(STATE_FILE.read_text())
            return {"seen": d.get("seen", [])[-200:], "allowed": d.get("allowed", []),
                    "last_poll": d.get("last_poll", 0), "tg_down": d.get("tg_down", False),
                    "tg_offset": d.get("tg_offset", 0), "daily": d.get("daily", False),
                    "last_check_day": d.get("last_check_day", "")}
        except Exception:
            return {"seen": [], "allowed": [], "last_poll": 0, "tg_down": False, "tg_offset": 0, "daily": False, "last_check_day": ""}

    def _save(self):
        try:
            config.STATE_DIR.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(json.dumps(self.state))
        except Exception:
            pass

    # ---- config ----------------------------------------------------------
    def owner_addresses(self):
        env = [a.strip().lower() for a in os.environ.get("OWNER_EMAILS", "").split(",") if a.strip()]
        return set(env) | {a.lower() for a in self.state["allowed"]}

    def gmail_ready(self):
        return bool(self.google and self.google.connected() and self.owner_addresses())

    def due(self):
        return self.gmail_ready() and time.time() - self.state["last_poll"] >= self.interval

    def allow(self, address):
        address = (address or "").strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", address):
            return None
        if address not in self.state["allowed"]:
            self.state["allowed"].append(address)
            self._save()
        return address

    def forget(self, address):
        address = (address or "").strip().lower()
        if address in self.state["allowed"]:
            self.state["allowed"].remove(address)
            self._save()
            return True
        return False

    # ---- Gmail two-way ---------------------------------------------------
    def poll(self, respond):
        """Answer new owner mail. respond(text) -> str|None (the normal responder).
        Returns [(from, subject, chars_sent)]. Never raises."""
        if not self.gmail_ready():
            return []
        self.state["last_poll"] = time.time()
        self._save()
        try:
            mails = self.google.recent_mail("newer_than:1d", 10)
        except Exception as e:
            self.log("fallback_poll_failed", error=str(e)[:160])
            return []
        handled = []
        me = (self.google.account() or "").lower()
        for m in mails:
            mid = m.get("id", "")
            if not mid or mid in self.state["seen"]:
                continue
            self.state["seen"].append(mid)
            self.state["seen"] = self.state["seen"][-200:]
            self._save()
            sender = _addr(m.get("from", ""))
            subject = (m.get("subject") or "").strip()
            if not sender or sender == me or subject.startswith(REPLY_PREFIX):
                continue                                            # own mail or own reply: never loop
            if sender not in self.owner_addresses():
                self.log("fallback_stranger", sender=sender[:60], subject=subject[:60])
                continue
            if authenticated(m.get("auth")) is False:                       # From says the owner, Gmail says it did not come from there
                self.log("fallback_spoofed", sender=sender[:60], subject=subject[:60])
                continue
            text = strip_quotes(m.get("text") or "") or subject
            text = re.sub(r"\s+", " ", text).strip()[:MAX_BODY]
            if not text:
                continue
            self.log("fallback_in", sender=sender[:60], chars=len(text))
            try:
                out = respond(text)
            except Exception as e:
                out = f"I hit an error on that one: {str(e)[:200]}"
            body = (out.strip() if isinstance(out, str) and out.strip() else
                    "(sent to Telegram — tap there to continue)") + \
                "\n\n— sent by the fallback channel. If Telegram is down, just reply to this mail."
            try:
                self.google.send_mail(sender, f"{REPLY_PREFIX} {subject[:60] or 'hello'}", body,
                                      thread_id=m.get("thread") or None, in_reply_to=m.get("msgid") or None)
                handled.append((sender, subject[:60], len(body)))
                self.log("fallback_out", sender=sender[:60], chars=len(body))
                for tidy in ("mark_read", "archive"):      # answered mail leaves no unread trace (best-effort)
                    try:
                        fn = getattr(self.google, tidy, None)
                        if fn:
                            fn(mid)
                    except Exception:
                        pass
            except Exception as e:
                self.log("fallback_send_failed", error=str(e)[:160])
        return handled

    # ---- Telegram-line watchdog ------------------------------------------
    def telegram_down(self, reason):
        """Called when the main Telegram line looks dead ( auth failures). Alerts once per outage."""
        if self.state["tg_down"]:
            return False
        self.state["tg_down"] = True
        self._save()
        body = (f"⚠️ The main Telegram line looks down ({reason}).\n\n"
                f"I'm still here: reply to this mail and I'll do what I can by email, "
                f"or check the backup bot.")
        addrs = sorted(self.owner_addresses())
        if self.gmail_ready() and addrs:
            try:
                self.google.send_mail(addrs[0], f"{REPLY_PREFIX} main Telegram line down", body)
            except Exception as e:
                self.log("fallback_send_failed", error=str(e)[:160])
        self.backup.send(f"⚠️ Main Telegram line down ({reason}). I'm the backup bot — /status works here.")
        self.log("fallback_tg_down", reason=str(reason)[:120])
        return True

    def telegram_back(self):
        if not self.state["tg_down"]:
            return False
        self.state["tg_down"] = False
        self._save()
        addrs = sorted(self.owner_addresses())
        if self.gmail_ready() and addrs:
            try:
                self.google.send_mail(addrs[0], f"{REPLY_PREFIX} Telegram is back",
                                      "✅ The main Telegram line works again. Talk to me there.")
            except Exception:
                pass
        self.log("fallback_tg_back")
        return True

    # ---- backup bot polling ----------------------------------------------
    def poll_backup(self, respond_simple):
        """Answer /status + quick text on the backup bot. Returns handled count. Never raises."""
        if not self.backup.configured() or not self.owner_id_fn():
            return 0
        try:
            updates = self.backup.bot.get_updates(offset=self.state["tg_offset"] or None, timeout=2)
        except Exception as e:
            self.log("fallback_backup_poll_failed", error=str(e)[:120])
            return 0
        n = 0
        for u in updates:
            self.state["tg_offset"] = u.get("update_id", 0) + 1
            self._save()
            msg = u.get("message") or {}
            user = msg.get("from") or {}
            text = (msg.get("text") or "").strip()
            if user.get("id") != self.owner_id_fn() or not text:
                continue
            try:
                out = respond_simple(text)
            except Exception as e:
                out = f"Error: {str(e)[:160]}"
            if out:
                try:
                    self.backup.bot.send(user["id"], str(out)[:3500])
                    n += 1
                except Exception:
                    pass
        return n

    # ---- daily line check ------------------------------------------------
    def line_check_due(self, hour, today):
        """Once a day, in the morning (08–11), when the owner switched it on (/fallback check on)."""
        return bool(self.state.get("daily")) and 8 <= hour < 11 and self.state.get("last_check_day") != today

    def line_check(self, today, status_line=""):
        """Send the daily 'line is alive' mail. Returns True when sent."""
        addrs = sorted(self.owner_addresses())
        if not (self.gmail_ready() and addrs):
            return False
        self.state["last_check_day"] = today
        self._save()
        try:
            self.google.send_mail(addrs[0], f"{REPLY_PREFIX} morning line check {today}",
                                  "\u2705 Both lines are alive: Telegram and this mailbox.\n"
                                  + (status_line + "\n" if status_line else "")
                                  + "\nReply to this mail with any request if Telegram ever stops answering.")
            self.log("fallback_line_check", to=addrs[0][:60])
            return True
        except Exception as e:
            self.log("fallback_send_failed", error=str(e)[:160])
            return False

    def set_daily(self, on):
        self.state["daily"] = bool(on)
        self._save()

    # ---- status ----------------------------------------------------------
    def status(self):
        g = "on" if self.gmail_ready() else ("waiting for Google" if not (self.google and self.google.connected()) else "needs /fallback allow <your email>")
        addrs = ", ".join(sorted(self.owner_addresses())) or "none yet"
        b = "on" if self.backup.configured() else "needs FALLBACK_BOT_TOKEN in .secrets/env"
        last = (time.strftime("%H:%M", time.localtime(self.state["last_poll"])) if self.state["last_poll"] else "never")
        daily = ("on (08–11, last " + (self.state.get("last_check_day") or "never") + ")") if self.state.get("daily") else "off (/fallback check on)"
        return (f"📧 Fallback contact — Gmail: {g} · backup bot: {b}\n"
                f"owner mail: {addrs} · last mail check: {last} · mails answered: {len(self.state['seen'])} · morning line check: {daily}\n"
                f"{'⚠️ main Telegram line currently DOWN' if self.state['tg_down'] else 'main Telegram line: ok'}\n"
                f"/fallback allow <email> · /fallback forget <email> · /fallback test · /fallback test send · /fallback check on|off|now")
