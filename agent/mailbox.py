"""Gmail as a tool (owner's item G) — ONLY when a Google account is connected (optional since 2026-09-10; the bot's
identity mailbox is agent/idmail.py over IMAP). The connected Gmail sorted into labels, kept tidy,
and used — verification codes fetched from the right pile, leads noticed, alerts summarised.

Labels (created once, shown in the Gmail sidebar):
  Verification  — codes, confirm links, password resets, "welcome" mails from sign-ups   → read, then archived after 1 day
  Leads         — real people writing to us (suppliers answering, customers, the owner)   → stays in the inbox, flagged
  Alerts        — order/shipping/payment/security notices from platforms                   → archived after 3 days
  Newsletters   — list mail, promotions, digests                                           → archived at once, read
The owner's own addresses are never touched here (the fallback channel answers them).

Nothing is ever deleted or sent from here: labels + archive (remove INBOX) + mark read only. Official Gmail API,
scope gmail.modify (already granted). Every action is logged; `/mail` shows the counts and the last tidy.

    M = Mailbox(google, log)
    M.classify(meta)            -> "verification" | "leads" | "alerts" | "newsletters" | ""   (pure rules, testable offline)
    M.tidy(limit=40)            -> {"labelled": n, "archived": n, "by": {...}, "leads": [..]}  (never raises)
    M.due()                     -> every TIDY_EVERY seconds when Google is connected
    M.code(hint, since_minutes) -> (code, mail) from the Verification pile first (fast path), else Google.find_code
    M.status()                  -> one line
    M.summary(days=1)           -> a short text: leads waiting, alerts seen, codes fetched
"""
import email.utils
import json
import re
import time

from . import config

STATE = config.STATE_DIR / "mailbox.json"
TIDY_EVERY = 900              # 15 min between tidies (a few API calls each)
LABELS = {"verification": "Verification", "leads": "Leads", "alerts": "Alerts", "newsletters": "Newsletters"}
ARCHIVE_AFTER_H = {"verification": 24, "alerts": 72, "newsletters": 0}     # leads are never archived automatically

_VERIF_SUBJ = re.compile(r"\b(verif\w*|confirm\w*|conferm\w*|activat\w*|attiva\w*|one[- ]time|otp|passcode|security code|codice|"
                         r"your code|login code|sign[- ]in code|reset (your )?password|password reset|reimposta|welcome to|benvenut\w*|"
                         r"complete your (registration|sign ?up)|finish (setting up|signing up)|magic link|2fa|two[- ]factor)\b", re.I)
_VERIF_BODY = re.compile(r"\b(code|codice|otp|pin)\b\D{0,30}\d{4,8}\b|\b\d{4,8}\b\D{0,30}\b(code|codice|otp|pin)\b|\b(verify|confirm|activate|conferma|verifica) (your )?(email|e-mail|account|address|indirizzo)\b", re.I)
_ALERT_SUBJ = re.compile(r"\b(order|ordine|shipped|spedito|spedizione|delivery|consegna|payment|pagamento|invoice|fattura|receipt|ricevuta|refund|rimborso|"
                         r"new (sign[- ]in|login|device)|nuovo accesso|security alert|avviso di sicurezza|suspicious|storage|quota|policy|terms|privacy|"
                         r"subscription|abbonamento|expir\w+|scad\w+|reminder|promemoria|statement|estratto)\b", re.I)
_NEWS_SUBJ = re.compile(r"\b(newsletter|digest|weekly|settimanale|roundup|% off|sale|saldi|offerta|offer|deal|promo\w*|unsubscribe|webinar|"
                        r"tips|trends?|what'?s new|novità|black friday|coupon|sconto)\b", re.I)
_MACHINE_FROM = re.compile(r"(no-?reply|do-?not-?reply|noreply|mailer-daemon|postmaster|notifications?@|newsletter|bounce|auto-?mail|info@|news@|hello@|team@|support@|updates?@|alerts?@|security@|account@|accounts@)", re.I)
_LEAD_WORDS = re.compile(r"\b(quote|quotation|preventivo|price list|listino|moq|minimum order|sample|campione|wholesale|ingrosso|supplier|fornitore|"
                         r"order|ordine|collaboration|collaborazione|partnership|interested|interessat\w+|inquiry|enquiry|richiesta|question|domanda|"
                         r"available|disponibil\w+|catalog\w*|catalogo|invoice request|re:|r:)\b", re.I)


def _addr(frm):
    return (email.utils.parseaddr(frm or "")[1] or "").lower()


class Mailbox:
    def __init__(self, google=None, log=None, owner_addresses=None):
        self.google = google
        self.log = log or (lambda kind, **f: None)
        self.owner_addresses = owner_addresses or (lambda: set())
        self.state = {"last_tidy": 0, "labels": {}, "seen": {}, "counts": {k: 0 for k in LABELS}, "archived": 0, "codes": 0, "leads": [], "history": []}
        self._load()

    # ---- state ------------------------------------------------------------------------------
    def _load(self):
        try:
            if STATE.exists():
                d = json.loads(STATE.read_text(encoding="utf-8"))
                if isinstance(d, dict):
                    self.state.update(d)
        except Exception as e:
            self.log("mailbox_load_failed", error=str(e)[:100])

    def _save(self):
        try:
            config.ensure_dirs()
            if len(self.state["seen"]) > 2000:                                   # keep the memory small: newest 1000 ids
                keep = sorted(self.state["seen"].items(), key=lambda kv: kv[1], reverse=True)[:1000]
                self.state["seen"] = dict(keep)
            self.state["history"] = self.state["history"][-30:]
            self.state["leads"] = self.state["leads"][-50:]
            STATE.write_text(json.dumps(self.state), encoding="utf-8")
        except Exception as e:
            self.log("mailbox_save_failed", error=str(e)[:100])

    def connected(self):
        try:
            return bool(self.google and self.google.connected())
        except Exception:
            return False

    def due(self):
        return self.connected() and time.time() - self.state.get("last_tidy", 0) >= TIDY_EVERY

    # ---- classification (rules; offline-testable) --------------------------------------------
    def classify(self, m):
        """One mail's metadata → pile name or '' (leave alone). The owner's own mail is always ''."""
        frm = m.get("from", "") or ""
        addr = _addr(frm)
        me = ""
        try:
            me = (self.google.account() or "").lower() if self.google else ""
        except Exception:
            pass
        if addr and (addr in self.owner_addresses() or (me and addr == me)):
            return ""
        subj = m.get("subject", "") or ""
        snip = m.get("snippet", "") or ""
        hd = m.get("headers", {}) or {}
        blob = f"{subj} {snip}"
        is_list = bool(hd.get("List-Unsubscribe") or hd.get("List-Id") or (hd.get("Precedence", "").lower() in ("bulk", "list")))
        machine = bool(_MACHINE_FROM.search(addr) or _MACHINE_FROM.search(frm)) or (hd.get("Auto-Submitted", "no").lower() != "no")
        if _VERIF_SUBJ.search(subj) or _VERIF_BODY.search(blob):
            return "verification"
        if is_list or _NEWS_SUBJ.search(subj):
            return "newsletters"
        if machine and _ALERT_SUBJ.search(blob):
            return "alerts"
        if not machine and (_LEAD_WORDS.search(blob) or len(snip) > 40):
            return "leads"
        if machine:
            return "alerts"
        return "leads"

    # ---- the tidy ---------------------------------------------------------------------------
    def _label_ids(self, refresh=False):
        ids = dict(self.state.get("labels") or {})
        if all(k in ids for k in LABELS) and not refresh:
            return ids
        existing = self.google.labels()
        ids = {k: self.google.ensure_label(name, existing) for k, name in LABELS.items()}
        self.state["labels"] = ids
        self._save()
        return ids

    def _modify(self, mid, pile=None, remove=()):
        """modify with one retry after a label refresh: a label deleted by hand in Gmail must not break the tidy forever."""
        ids = self._label_ids()
        add = [ids[pile]] if pile else []
        try:
            return self.google.modify(mid, add=add, remove=remove)
        except Exception as e:
            if "labelId not found" not in str(e) or not pile:
                raise
            ids = self._label_ids(refresh=True)
            self.log("mailbox_labels_refreshed")
            return self.google.modify(mid, add=[ids[pile]], remove=remove)

    def tidy(self, limit=40, query="newer_than:7d in:inbox"):
        """Label what is new, archive what is old enough. Returns the counts; never raises (logs instead)."""
        out = {"labelled": 0, "archived": 0, "by": {k: 0 for k in LABELS}, "leads": [], "error": ""}
        if not self.connected():
            out["error"] = "google off"
            return out
        self.state["last_tidy"] = time.time()
        try:
            ids = self._label_ids()
            mails = self.google.list_mail_meta(query, limit)
            now_ms = int(time.time() * 1000)
            for m in mails:
                mid = m["id"]
                pile = self.state["seen"].get(mid, {}).get("pile") if isinstance(self.state["seen"].get(mid), dict) else None
                if pile is None:
                    pile = self.classify(m)
                    if pile:
                        try:
                            rem = ["UNREAD"] if pile in ("newsletters", "alerts") else []
                            if ARCHIVE_AFTER_H.get(pile) == 0:
                                rem.append("INBOX")
                            self._modify(mid, pile=pile, remove=rem)
                            out["labelled"] += 1
                            out["by"][pile] += 1
                            self.state["counts"][pile] = self.state["counts"].get(pile, 0) + 1
                            if "INBOX" in rem:
                                out["archived"] += 1
                                self.state["archived"] += 1
                            if pile == "leads":
                                lead = {"t": time.time(), "from": m["from"][:80], "subject": m["subject"][:100], "id": mid}
                                out["leads"].append(lead)
                                self.state["leads"].append(lead)
                        except Exception as e:
                            self.log("mailbox_modify_failed", id=mid, error=str(e)[:100])
                            continue
                    self.state["seen"][mid] = {"pile": pile, "t": time.time(), "ms": m.get("internal_ms", 0)}
                # archive by age (labelled earlier, still in the inbox)
                hours = ARCHIVE_AFTER_H.get(pile or "", None)
                if pile and hours and "INBOX" in (m.get("labels") or []) and m.get("internal_ms") and now_ms - m["internal_ms"] > hours * 3600 * 1000:
                    try:
                        self._modify(mid, remove=["INBOX", "UNREAD"])
                        out["archived"] += 1
                        self.state["archived"] += 1
                    except Exception as e:
                        self.log("mailbox_archive_failed", id=mid, error=str(e)[:100])
            self.state["history"].append({"t": time.time(), "labelled": out["labelled"], "archived": out["archived"], "leads": len(out["leads"])})
            self._save()
            self.log("mailbox_tidy", labelled=out["labelled"], archived=out["archived"], leads=len(out["leads"]))
        except Exception as e:
            out["error"] = str(e)[:160]
            self.log("mailbox_tidy_failed", error=str(e)[:160])
            self._save()
        return out

    # ---- codes: the Verification pile first ---------------------------------------------------
    def code(self, hint="", since_minutes=30, tries=6, wait=20):
        """A fresh verification code: look in the Verification label first (one cheap query), then the general search."""
        if not self.connected():
            return None, None
        try:
            ids = self._label_ids()
            q = f"label:{LABELS['verification']} newer_than:{max(1, since_minutes // 60 + 1)}h" + self.google._from_query(hint)
            for m in self.google.recent_mail(q, 5):
                blob = f"{m['from']} {m['subject']}".lower()
                if hint and hint.lower() not in blob and hint.lower().split(".")[0] not in blob:
                    continue
                txt = f"{m['subject']} {m['text'] or m['snippet']}"
                m2 = re.search(r"(?:code|codice|otp|pin|passcode)\D{0,40}?(\d[\d ]{2,10}\d)", txt, re.I) or self.google.CODE_RE.search(txt)
                if m2:
                    code = re.sub(r"\D", "", m2.group(1))
                    if 4 <= len(code) <= 8:
                        self.state["codes"] = self.state.get("codes", 0) + 1
                        self._save()
                        try:
                            self.google.modify(m["id"], add=[ids["verification"]], remove=["UNREAD"])
                        except Exception:
                            pass
                        self.log("mailbox_code_fast", sender=m["from"][:60])
                        return code, m
        except Exception as e:
            self.log("mailbox_code_fast_failed", error=str(e)[:100])
        code, m = self.google.find_code(hint, since_minutes=since_minutes, tries=tries, wait=wait)
        if code:
            self.state["codes"] = self.state.get("codes", 0) + 1
            self._save()
            try:
                ids = self._label_ids()
                self.google.modify(m["id"], add=[ids["verification"]], remove=["UNREAD"])
            except Exception:
                pass
        return code, m

    # ---- telling -------------------------------------------------------------------------------
    def status(self):
        if not self.connected():
            return "mail: Google off"
        c = self.state.get("counts", {})
        last = self.state.get("last_tidy", 0)
        ago = f"{int((time.time() - last) // 60)} min ago" if last else "never"
        return (f"mail: sorted {sum(c.values())} (verification {c.get('verification', 0)} · leads {c.get('leads', 0)} · alerts {c.get('alerts', 0)} · "
                f"newsletters {c.get('newsletters', 0)}) · archived {self.state.get('archived', 0)} · codes fetched {self.state.get('codes', 0)} · last tidy {ago}")

    def summary(self, days=1):
        cut = time.time() - days * 86400
        leads = [l for l in self.state.get("leads", []) if l["t"] >= cut]
        hist = [h for h in self.state.get("history", []) if h["t"] >= cut]
        lines = [self.status()]
        if leads:
            lines.append(f"📩 {len(leads)} lead(s) waiting in the inbox — I never answer these myself:")
            lines += [f"• {l['from']} — {l['subject']}" for l in leads[-6:]]
        else:
            lines.append("No new leads (real people writing to us) in the period.")
        if hist:
            lines.append(f"Tidies: {len(hist)} · labelled {sum(h['labelled'] for h in hist)} · archived {sum(h['archived'] for h in hist)}.")
        lines.append("Rules: Verification → read, archived after a day · Alerts → after 3 days · Newsletters → archived at once · Leads → stay, flagged for you. Nothing is deleted or answered from here.")
        return "\n".join(lines)


CMD = re.compile(r"^(?:/mail(?:box)?(?:\s+(tidy|now|status|leads|summary|labels))?|(?:tidy|clean|sort)\s+(?:up\s+)?(?:the\s+|your\s+|my\s+)?(?:inbox|mailbox|e-?mail)|"
                 r"(?:how(?:'s| is) (?:the|your) (?:inbox|mailbox|mail))|(?:any|new) leads\??|(?:show|list)(?: me)? (?:the )?leads)\W*$", re.I)


def command(M, text, run_tidy):
    """Owner phrasing → reply, or None. run_tidy(fn) runs the tidy in the background and reports."""
    t = text.strip()
    m = CMD.match(t)
    if not m:
        return None
    low = t.lower()
    arg = (m.group(1) or "").lower()
    if not M.connected():
        return "My Google isn't connected here, so I can't touch the mailbox — /google connect first."
    if arg in ("tidy", "now") or re.search(r"\b(tidy|clean|sort)\b", low):
        run_tidy()
        return "Tidying my inbox now (labels Verification / Leads / Alerts / Newsletters, old notices archived, nothing deleted) — one line when it's done."
    if arg in ("leads",) or "lead" in low:
        return M.summary(days=7)
    if arg == "labels":
        return "Labels I keep: " + " · ".join(LABELS.values()) + " (created in my Gmail the first time I tidy)."
    return M.summary(days=1)
