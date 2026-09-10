"""Gmail as a tool (owner's item G): labels, sorting rules, tidy, archive-by-age, code fast path, owner commands.
Offline: a stubbed Google records the HTTP the real methods would send.  --live: real mailbox (labels created, one tidy,
then the test labels are left in place — they are the real ones).
Run:  rm -rf /tmp/bai_mailbox_state; python3 engine/scripts/score_mailbox.py [--live]"""
import os, sys, json, time, base64, email.message, shutil
os.environ["BAI_STATE"] = "/tmp/bai_mailbox_state"
shutil.rmtree("/tmp/bai_mailbox_state", ignore_errors=True)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from agent.google import Google, GMAIL          # noqa: E402
from agent import mailbox as MB                 # noqa: E402

ok = 0; tot = 0
def check(name, cond, got=""):
    global ok, tot
    tot += 1; ok += bool(cond); print(("✅" if cond else "❌"), name, "" if cond else f"→ {str(got)[:220]}")


def raw_mail(frm, subject, body, msgid="<x@y>"):
    m = email.message.EmailMessage()
    m["From"], m["To"], m["Subject"], m["Message-ID"] = frm, "bot@gmail.com", subject, msgid
    m.set_content(body)
    return base64.urlsafe_b64encode(m.as_bytes()).decode()


NOW_MS = int(time.time() * 1000)
H = 3600 * 1000
INBOX = [
    # id, from, subject, snippet, headers, labels, age_ms
    ("v1", "Vinted <no-reply@vinted.it>", "Il tuo codice di verifica", "Il tuo codice è 482913. Scade tra 10 minuti.", {}, ["INBOX", "UNREAD"], 0),
    ("v2", "Etsy <noreply@etsy.com>", "Confirm your email address", "Click to confirm your Etsy account", {}, ["INBOX", "UNREAD"], 30 * H),
    ("l1", "Marco Bianchi <marco@ceramicheverdi.it>", "Re: preventivo tazze in gres", "Buongiorno, il prezzo per 50 pezzi è 4,20 € cad., MOQ 50, consegna 2 settimane", {}, ["INBOX", "UNREAD"], 2 * H),
    ("a1", "Google <no-reply@accounts.google.com>", "Security alert", "New sign-in on Linux. Was this you?", {}, ["INBOX", "UNREAD"], 100 * H),
    ("n1", "Shopify <news@shopify.com>", "Weekly digest: 5 trends for September", "Unsubscribe here", {"List-Unsubscribe": "<mailto:u@shopify.com>"}, ["INBOX", "UNREAD"], 1 * H),
    ("o1", "Carlo <carlo.rella014@gmail.com>", "status", "how is it going?", {}, ["INBOX", "UNREAD"], 1 * H),
    ("a2", "Subito <notifications@subito.it>", "Il tuo annuncio è stato pubblicato", "Annuncio online", {}, ["INBOX"], 1 * H),
    ("l2", "Anna <anna.k@gmail.com>", "Question about the cork phone case", "Hi, is the cork case available for iPhone 15? Thanks, Anna", {}, ["INBOX", "UNREAD"], 5 * H),
]


class StubGoogle(Google):
    def __init__(self):
        super().__init__(log=lambda kind, **f: None)
        self.calls = []
        self.label_list = [{"name": "INBOX", "id": "INBOX"}, {"name": "Leads", "id": "Label_7"}]
        self.inbox = list(INBOX)

    def connected(self): self.client_disabled = False; self.needs_reconnect = False; return True   # a healthy Google, whatever token file this machine has
    def account(self): return "bot@gmail.com"

    def _req(self, url, method="GET", data=None, headers=None, raw=False, timeout=60):
        body = json.loads(data.decode()) if data else None
        self.calls.append((url, method, body))
        if url == f"{GMAIL}/labels" and method == "GET":
            return {"labels": list(self.label_list)}
        if url == f"{GMAIL}/labels" and method == "POST":
            lid = "Label_" + str(len(self.label_list) + 1)
            self.label_list.append({"name": body["name"], "id": lid})
            return {"id": lid, "name": body["name"]}
        if url.endswith("/modify"):
            return {}
        if url.startswith(f"{GMAIL}/messages?"):
            q = url.split("q=")[1].split("&")[0]
            if "label%3AVerification" in q or "label:Verification" in q:
                return {"messages": [{"id": "v1", "threadId": "t"}]}
            return {"messages": [{"id": r[0], "threadId": "t"} for r in self.inbox]}
        if "/messages/" in url and "format=metadata" in url:
            mid = url.rsplit("/messages/", 1)[1].split("?")[0]
            r = next(x for x in self.inbox if x[0] == mid)
            hd = dict({"From": r[1], "Subject": r[2], "Date": "x"}, **r[4])
            return {"id": mid, "threadId": "t", "labelIds": r[5], "snippet": r[3], "internalDate": str(NOW_MS - r[6]),
                    "payload": {"headers": [{"name": k, "value": v} for k, v in hd.items()]}}
        if "/messages/" in url and "format=raw" in url:
            mid = url.rsplit("/messages/", 1)[1].split("?")[0]
            r = next(x for x in self.inbox if x[0] == mid)
            return {"id": mid, "threadId": "t", "labelIds": r[5], "snippet": r[3], "raw": raw_mail(r[1], r[2], r[3])}
        raise AssertionError("unexpected " + url)


g = StubGoogle()
M = MB.Mailbox(google=g, log=lambda k, **f: None, owner_addresses=lambda: {"carlo.rella014@gmail.com"})

# ---- rules --------------------------------------------------------------------------------
def meta(r):
    return {"id": r[0], "from": r[1], "subject": r[2], "snippet": r[3], "headers": r[4], "labels": r[5]}
exp = {"v1": "verification", "v2": "verification", "l1": "leads", "a1": "alerts", "n1": "newsletters", "o1": "", "a2": "alerts", "l2": "leads"}
for r in INBOX:
    check(f"classify {r[0]} → {exp[r[0]] or 'owner (untouched)'}", M.classify(meta(r)) == exp[r[0]], M.classify(meta(r)))
check("google's own address untouched", M.classify({"from": "bot@gmail.com", "subject": "x", "snippet": "y" * 50}) == "")

# ---- google helpers -----------------------------------------------------------------------
labels = g.labels()
check("labels() → name→id map", labels.get("Leads") == "Label_7" and "INBOX" in labels, labels)
vid = g.ensure_label("Verification", labels)
check("ensure_label creates a missing one (POST with sidebar visibility)", vid.startswith("Label_") and any(c[1] == "POST" and c[2].get("name") == "Verification" and c[2].get("labelListVisibility") == "labelShow" for c in g.calls))
check("ensure_label reuses an existing one (no POST)", g.ensure_label("Leads", g.labels()) == "Label_7" and sum(1 for c in g.calls if c[1] == "POST" and c[2] and c[2].get("name") == "Leads") == 0)
g.calls.clear()
g.modify("m9", add=["L1"], remove=["INBOX"])
check("modify sends add+remove, never delete", g.calls[-1][0].endswith("/m9/modify") and g.calls[-1][2] == {"addLabelIds": ["L1"], "removeLabelIds": ["INBOX"]} and not any("DELETE" == c[1] for c in g.calls))
lm = g.list_mail_meta("newer_than:2d", 3)
check("list_mail_meta: headers + snippet + internal ms, no raw body fetched", len(lm) == 8 and lm[0]["from"].startswith("Vinted") and lm[0]["internal_ms"] and all("format=metadata" in c[0] for c in g.calls if "/messages/" in c[0] and c[1] == "GET"))

# ---- the tidy -------------------------------------------------------------------------------
g.calls.clear()
r = M.tidy()
mods = {c[0].rsplit("/messages/", 1)[1].split("/")[0]: c[2] for c in g.calls if c[0].endswith("/modify")}
check("tidy: no error, 7 labelled (owner mail skipped)", not r["error"] and r["labelled"] == 7 and "o1" not in mods, (r, list(mods)))
check("tidy: all four labels exist afterwards", set(MB.LABELS.values()) <= set(g.labels()))
lab = {k: v for k, v in M.state["labels"].items()}
check("verification v1 labelled, kept unread + in inbox (fresh)", mods["v1"]["addLabelIds"] == [lab["verification"]] and "INBOX" not in mods["v1"].get("removeLabelIds", []) and "UNREAD" not in mods["v1"].get("removeLabelIds", []), mods["v1"])
check("verification v2 (30 h old) archived by age", any(c[0].endswith("/v2/modify") and "INBOX" in (c[2].get("removeLabelIds") or []) for c in g.calls), [c for c in g.calls if "/v2/" in c[0]])
check("newsletter n1 archived at once + read", set(mods["n1"]["removeLabelIds"]) == {"UNREAD", "INBOX"} and mods["n1"]["addLabelIds"] == [lab["newsletters"]], mods["n1"])
check("alert a1 (100 h) read + archived by age; a2 (1 h) read, still in inbox", any(c[0].endswith("/a1/modify") and "INBOX" in (c[2].get("removeLabelIds") or []) for c in g.calls) and "INBOX" not in mods["a2"].get("removeLabelIds", []), [c for c in g.calls if "/a" in c[0]])
check("leads l1/l2 labelled, never archived, stay unread", mods["l1"]["addLabelIds"] == [lab["leads"]] and not mods["l1"].get("removeLabelIds") and not mods["l2"].get("removeLabelIds"), (mods["l1"], mods["l2"]))
check("tidy returns the leads for the owner", [l["id"] for l in r["leads"]] == ["l1", "l2"] and "preventivo" in r["leads"][0]["subject"], r["leads"])
check("nothing deleted, nothing sent", not any("/send" in c[0] or c[1] == "DELETE" or "/trash" in c[0] for c in g.calls))
g.calls.clear()
r2 = M.tidy()
check("second tidy: already-seen mail not relabelled (idempotent)", r2["labelled"] == 0 and not any(c[0].endswith("/l1/modify") for c in g.calls), (r2, g.calls[:3]))
check("state persisted (labels ids, counts, leads)", json.loads(MB.STATE.read_text())["counts"]["leads"] == 2 and json.loads(MB.STATE.read_text())["labels"]["leads"] == lab["leads"])
check("due(): not before 15 min", not M.due())
st = M.status()
check("status line: sorted counts, archived, last tidy", "sorted 7" in st and "leads 2" in st and "archived" in st and "last tidy 0 min ago" in st, st)
sm = M.summary()
check("summary lists the leads and the rules, says I never answer them", "2 lead(s)" in sm and "Marco Bianchi" in sm and "never answer" in sm and "Nothing is deleted" in sm, sm)

# ---- code fast path ----------------------------------------------------------------------------
g.calls.clear()
code, mail = M.code("vinted", since_minutes=30, tries=1, wait=0)
check("code(): from the Verification pile, one query, 482913", code == "482913" and mail["id"] == "v1" and any("label" in c[0] and "Verification" in c[0] for c in g.calls if c[1] == "GET"), (code, [c[0][-80:] for c in g.calls][:3]))
check("code(): the mail is marked read + labelled after use", any(c[0].endswith("/v1/modify") and "UNREAD" in (c[2].get("removeLabelIds") or []) for c in g.calls))
g.calls.clear()
code2, _ = M.code("nonesuch", since_minutes=30, tries=1, wait=0)
check("code(): unknown sender → falls back to the general search (find_code), None without a match", code2 is None and any("from%3A%28nonesuch%29" in c[0] or "from:(nonesuch)" in c[0] for c in g.calls), [c[0][-90:] for c in g.calls][:3])

# ---- owner commands -----------------------------------------------------------------------------
ran = []
rt = lambda: ran.append(1)
check("'/mail' → summary", MB.command(M, "/mail", rt).startswith("mail: sorted"))
check("'tidy the inbox' → runs the tidy in the background", "Tidying" in MB.command(M, "tidy the inbox", rt) and ran == [1])
check("'any leads?' → the leads", "Marco Bianchi" in MB.command(M, "any leads?", rt))
check("'/mail labels' → the four names", all(n in MB.command(M, "/mail labels", rt) for n in MB.LABELS.values()))
check("unrelated → None", MB.command(M, "mail the supplier about the mugs", rt) is None and MB.command(M, "what is a good inbox zero routine", rt) is None)
M2 = MB.Mailbox(google=None, log=lambda k, **f: None)
check("google off → tidy says so, never raises; command says connect", M2.tidy()["error"] == "google off" and "connect" in MB.command(M2, "/mail", rt))

class Stale(StubGoogle):
    """Label ids in state point at labels that no longer exist (deleted by hand): modify → 400 labelId not found."""
    def _req(self, url, method="GET", data=None, headers=None, raw=False, timeout=60):
        body = json.loads(data.decode()) if data else None
        if url.endswith("/modify") and body and any(a.startswith("OLD_") for a in body.get("addLabelIds", [])):
            self.calls.append((url, method, body))
            from agent.google import GoogleError
            raise GoogleError('HTTP 400 {"error": {"code": 400, "message": "labelId not found"}}')
        return super()._req(url, method, data, headers, raw, timeout)
gs = Stale()
M4 = MB.Mailbox(google=gs, log=lambda k, **f: None, owner_addresses=lambda: {"carlo.rella014@gmail.com"})
M4.state["labels"] = {k: "OLD_" + k for k in MB.LABELS}; M4.state["seen"] = {}
r4 = M4.tidy()
fresh = {v for v in M4.state["labels"].values()}
check("stale label ids (label deleted by hand) → refreshed once, mail still labelled with the new ids", r4["labelled"] == 7 and not any(v.startswith("OLD_") for v in fresh)
      and all(c[2]["addLabelIds"][0] in fresh for c in gs.calls if c[0].endswith("/modify") and c[2] and c[2].get("addLabelIds") and not c[2]["addLabelIds"][0].startswith("OLD_")), (r4, M4.state["labels"], gs.calls[-2:]))

class Broken(StubGoogle):
    def _req(self, url, method="GET", data=None, headers=None, raw=False, timeout=60):
        raise RuntimeError("HTTP 500 boom")
M3 = MB.Mailbox(google=Broken(), log=lambda k, **f: None)
r3 = M3.tidy()
check("API failing → tidy returns the error, never raises", "boom" in r3["error"])

# ---- the agent: /mail, code fetch through the mailbox, status line -----------------------------
from agent import core                          # noqa: E402
class FakeBot:
    def __init__(self): self.sent = []
    def get_me(self): return {"username": "fake"}
    def send(self, chat, text, buttons=None, **k): self.sent.append(text); return {"message_id": 1}
    def __getattr__(self, n): return lambda *a, **k: None
core.Bot = lambda *a, **k: FakeBot()
os.environ["BAI_STORE_PORT"] = "8193"
os.environ.pop("BAI_MAIL_PASSWORD", None)                      # this suite tests the Google mailbox path: no IMAP identity here
A = core.Agent(); A.owner_id = 1
A.planner.available = lambda: False; A.planner.installed = lambda: False
A.log = lambda *a, **k: None
A.google = g; A.mailbox = MB.Mailbox(google=g, log=lambda k, **f: None, owner_addresses=lambda: {"carlo.rella014@gmail.com"})
check("agent has the mailbox; accounts share it", A.accounts.mailbox is not None)
r = A.respond("check my email for the vinted code")
time.sleep(1.5)
check("'check my email for the vinted code' → code pasted, via the mailbox", isinstance(r, str) and r.startswith("Looking in ") and any("📧 Code: 482913" in x for x in A.bot.sent), (r, A.bot.sent))
A.bot.sent.clear()
r = A.respond("tidy the inbox")
time.sleep(1.5)
check("'tidy the inbox' → one report line, nothing deleted", "Tidying" in r and any(x.startswith("📧 Inbox tidied") and "Nothing deleted" in x for x in A.bot.sent), A.bot.sent)
check("/status shows the mail line", "mail: sorted" in A.status_text())

if "--live" in sys.argv:
    print("---- live: the real mailbox")
    os.environ["BAI_STATE"] = "/tmp/bai_mailbox_live"; shutil.rmtree("/tmp/bai_mailbox_live", ignore_errors=True)
    import importlib; from agent import config as _cfg; importlib.reload(_cfg); importlib.reload(MB)     # fresh state, not the stub's ids
    G = Google()
    if not G.connected():
        print("SKIP live (Google not connected)")
    else:
        L = MB.Mailbox(google=G, log=lambda k, **f: print(json.dumps({"k": k, **{a: str(b)[:80] for a, b in f.items()}})))
        r = L.tidy(limit=15)
        labs = G.labels()
        check("live: the four labels exist in Gmail", all(n in labs for n in MB.LABELS.values()), list(labs))
        check("live: tidy ran without error", not r["error"], r)
        print("live tidy:", {k: v for k, v in r.items() if k != "leads"}, "leads:", [(l["from"], l["subject"]) for l in r["leads"]])
        print(L.summary())
print(f"MAILBOX SCORE: {ok}/{tot}")
