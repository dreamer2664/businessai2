"""Score item D: progress in Google Docs (day log + job log + heartbeat) and the native Doc templates.

  python3 engine/scripts/score_progress.py           # offline: a fake Google records every block
  python3 engine/scripts/score_progress.py --live    # also: real day doc + job doc, written and read back (Google connected)
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("BAI_STATE", os.path.join("state", "test_progress"))

from agent import progress as P  # noqa: E402
from agent.progress import Progress, Templates  # noqa: E402

ok = total = 0


def check(name, cond, detail=""):
    global ok, total
    total += 1
    ok += bool(cond)
    print(f"{'OK  ' if cond else 'MISS'} {name}" + (f"  — {detail}" if detail and not cond else ""), flush=True)


class FakeGoogle:
    def __init__(self, connected=True):
        self._c = connected
        self.docs = {}          # id → [blocks]
        self.created = []       # (title, folder, share)
        self.n = 0

    def connected(self):
        return self._c

    def docs_create(self, title, folder=None, share=False):
        self.n += 1
        did = f"doc{self.n}"
        self.docs[did] = []
        self.created.append((title, folder, share))
        return {"id": did, "link": f"https://docs.google.com/document/d/{did}/edit"}

    def docs_write_blocks(self, doc_id, blocks):
        self.docs[doc_id].extend(blocks)


class FakePace:
    def __init__(self, mode="normal", floor=None, budget=None, deadline=None):
        self.mode = mode
        self.started = time.time()
        self.floor_until = self.started + floor * 60 if floor else None
        self.budget_until = self.started + budget * 60 if budget else None
        self.deadline_min = deadline


if os.path.exists(str(P.STATE)):
    os.unlink(str(P.STATE))
P.FLUSH_EVERY = 0.2

# ---- day log + short job ----------------------------------------------------------------------
g = FakeGoogle()
pr = Progress(google=g, log=lambda k, **f: None)
link = pr.begin("find cork slippers on vinted", "seller_check", ["search vinted", "read 4 listings", "write the document"], pace=FakePace())
pr.flush()
check("day doc created on first job, shared, in Progress folder; short job gets no own doc", link is None and len(g.created) == 1
      and g.created[0][1] == "Progress" and g.created[0][2] is True and g.created[0][0].startswith("Business AI — "), str(g.created))
day = "doc1"
txt = " | ".join(b[1] if isinstance(b[1], str) else "TABLE" for b in g.docs[day])
check("day log: title, start line with goal + kind, plan bullets", "▶ find cork slippers on vinted (seller_check)" in txt and "search vinted" in txt
      and g.docs[day][0][0] == "h1" and any(b[0] == "bullet" for b in g.docs[day]), txt[:200])
pr.on_event("plan_step", {"n": 1, "text": "search vinted"})
pr.on_event("browser_open", {"url": "https://www.vinted.it/catalog?search_text=cork"})
pr.on_event("seller_check", {"name": "luca_milano"})
pr.on_event("market_search_note", {"site": "subito", "note": "captcha wall — backed off"})
pr.change("only italian sellers")
for i in range(7):
    pr.step(f"reading listing {i}")
pr.flush()
txt = " | ".join(b[1] for b in g.docs[day] if isinstance(b[1], str))
check("day log: steps from the screen's events (first 3 + every 5th), snags ⚠️, changes ✏️", "step 1: search vinted" in txt and "reading https://www.vinted.it" in txt
      and "checking seller luca_milano" in txt and "⚠️ subito: captcha wall" not in txt and "reading listing 6" not in txt
      and ("reading listing 4" in txt or "reading listing 3" in txt or "reading listing 5" in txt), txt[-400:])
r = pr.finish("Best bet: luca_milano (€ 18,50)", doc_link="https://docs.google.com/document/d/x/edit", delivered=True)
pr.flush()
txt = " | ".join(b[1] for b in g.docs[day] if isinstance(b[1], str))
check("day log: result line ✅ with the document link and the time taken; finish returns no job link for a short job",
      r is None and "✅ Best bet: luca_milano" in txt and "document: https://docs.google.com/document/d/x/edit" in txt and "min" in txt.split("✅")[-1], txt[-200:])
check("second day_doc() call reuses today's doc (state on disk)", pr.day_doc() == (day, "https://docs.google.com/document/d/doc1/edit") and Progress(google=g).day_doc()[0] == day, str(pr.day_doc()))

# ---- long job → own doc, heartbeat --------------------------------------------------------------
g2 = FakeGoogle()
if os.path.exists(str(P.STATE)):
    os.unlink(str(P.STATE))
pr2 = Progress(google=g2, log=lambda k, **f: None)
link2 = pr2.begin("research cork sandal suppliers in europe", "research", ["search", "read 8 pages", "write"], pace=FakePace(mode="slow", floor=180))
pr2.flush()
job = [d for d in g2.docs if d != "doc1"][0]
jtxt = " | ".join(b[1] for b in g2.docs[job] if isinstance(b[1], str))
dtxt = " | ".join(b[1] for b in g2.docs["doc1"] if isinstance(b[1], str))
check("slow / 'at least N h' job → its own job doc: title = goal, plan, 'As it happens'; day log links to it; begin returns the link",
      link2 and link2.endswith(f"{job}/edit") and g2.created[1][0].startswith("Job log — research cork sandal") and "Plan" in jtxt and "As it happens" in jtxt
      and "at least 180 min, as you asked" in jtxt and f"follow this job here: {link2}" in dtxt, f"{link2} {jtxt[:200]}")
pr2.step("reading https://example.com/a")
pr2.flush()
pr2.last_flush[job] = time.time() - 9 * 60
pr2.heartbeat("research: cork sandals")
pr2.flush()
jtxt = " | ".join(b[1] for b in g2.docs[job] if isinstance(b[1], str))
check("job doc: every step lands; heartbeat writes 'still on it' after 8 quiet minutes", "reading https://example.com/a" in jtxt and "still on it: research: cork sandals" in jtxt, jtxt[-200:])
n_before = len(g2.docs[job])
pr2.heartbeat("research: cork sandals")
pr2.flush()
check("heartbeat is quiet right after a write (no spam)", len(g2.docs[job]) == n_before)
r2 = pr2.finish("8 pages read, document ready", doc_link="https://docs.google.com/document/d/y/edit")
pr2.flush()
jtxt = " | ".join(b[1] for b in g2.docs[job] if isinstance(b[1], str))
check("job doc: Result heading + ✅ line + document link; finish returns the job link for the final message",
      r2 == link2 and "Result" in jtxt and "✅ 8 pages read" in jtxt and "document: https://docs.google.com/document/d/y/edit" in jtxt, jtxt[-200:])

# ---- promotion of a job that runs long -----------------------------------------------------------
g3 = FakeGoogle()
if os.path.exists(str(P.STATE)):
    os.unlink(str(P.STATE))
pr3 = Progress(google=g3, log=lambda k, **f: None)
pr3.begin("compare prices", "compare", [], pace=FakePace())
pr3.job["started"] -= P.JOB_DOC_AFTER + 5
pr3.step("still reading")
pr3.flush()
check("a normal job that runs past 20 min is promoted to its own doc ('running long')", pr3.job and pr3.job.get("doc") and any("running long" in (b[1] if isinstance(b[1], str) else "") for b in g3.docs[pr3.job["doc"]]), str(g3.created))
pr3.finish("done")

# ---- Google off / failures never raise -------------------------------------------------------------
g4 = FakeGoogle(connected=False)
pr4 = Progress(google=g4, log=lambda k, **f: None)
l4 = pr4.begin("x", "research", ["a"], pace=FakePace(mode="slow"))
pr4.step("y"); pr4.heartbeat("z"); pr4.on_event("plan_step", {"n": 1, "text": "a"})
r4 = pr4.finish("done")
check("Google not connected: silent no-ops, nothing created, no exception", l4 is None and r4 is None and g4.created == [])


class BrokenGoogle(FakeGoogle):
    def docs_write_blocks(self, doc_id, blocks):
        raise RuntimeError("quota")


g5 = BrokenGoogle()
if os.path.exists(str(P.STATE)):
    os.unlink(str(P.STATE))
errs = []
pr5 = Progress(google=g5, log=lambda k, **f: errs.append(k))
pr5.begin("x", "research", ["a"], pace=FakePace(mode="slow"))
pr5.step("y"); pr5.flush(); pr5.finish("done"); pr5.flush()
check("Docs API failing: logged, never raised, the job goes on", "progress_write_failed" in errs)

# ---- templates -----------------------------------------------------------------------------------
tb = Templates.research("cork sandals", "Two makers in Portugal ship to Italy.", [{"title": "Corkway", "url": "https://corkway.pt", "points": ["ships EU in 5 days", "MOQ 10"]},
                                                                                {"title": "Sole cork", "url": "https://solecork.com", "points": ["from € 12"]}], sources=["https://extra.example"])
kinds = [b[0] for b in tb]
tables = [b[1] for b in tb if b[0] == "table"]
check("research template: h1, In short, side-by-side table (3 rows incl. header), per-page h2 + url + bullets, sources", kinds[0] == "h1" and "In short" in [b[1] for b in tb if b[0] == "h2"]
      and len(tables) == 1 and len(tables[0]) == 3 and tables[0][1][1] == "Corkway" and ("bullet", "ships EU in 5 days") in tb and ("p", "https://corkway.pt") in tb
      and ("bullet", "https://extra.example") in tb and ("bullet", "https://corkway.pt") in tb, str(tb)[:300])
vids = [{"title": "Video A", "url": "https://youtu.be/a", "channel": "Ch", "views": 1234567, "published": "2 days ago", "length": "10:01", "top_comment": {"author": "bob", "likes": 1200, "text": "great"}},
        {"title": "Video B", "url": "https://youtu.be/b", "channel": "Ch2", "views": None, "published": "", "length": "", "top_comment": None}]
tt = Templates.trending("YouTube — hot this week: dropshipping", "trending is hidden from visitors; this is most-watched of the week", vids)
tab = [b[1] for b in tt if b[0] == "table"][0]
check("trending template: table with #/Video/Channel/Views/Uploaded/Length, formatted views, top comment bullet or honest 'not readable'",
      tab[0] == ["#", "Video", "Channel", "Views", "Uploaded", "Length"] and tab[1][3] == "1,234,567" and tab[2][3] == ""
      and any(b[0] == "bullet" and "bob (1,200 ♥): great" in b[1] for b in tt) and any(b[0] == "bullet" and "not readable" in b[1] for b in tt), str(tab))
opts = [{"seller": "luca_milano", "url": "https://www.vinted.it/items/1", "grade": "good", "verdict": "Looks reliable.", "facts": {"Price": "€ 18,50", "Shipping": "from € 2,29", "Ships from / origin": "Italia", "_price": 18.5, "Feedback": "47 feedback, 98% positive"}, "pros": ["98% positive feedback"], "cons": []},
        {"seller": "shopx", "url": "https://shopx.example", "grade": "bad", "verdict": "I would not trust this one.", "facts": {"Price": "€ 9,00"}, "pros": [], "cons": ["few reviews (2)", "no social media page found"]}]
ts = Templates.seller_check("cork slippers", "Best bet: luca_milano.", opts, conditions="max € 20")
tab = [b[1] for b in ts if b[0] == "table"]
check("seller-check template: side-by-side table with verdict marks, per-option facts table without _private keys, pros/cons bullets, 'How I judged'",
      tab[0][0] == ["Seller", "Price", "Shipping", "From", "Verdict"] and tab[0][1][4] == "👍 good" and tab[0][2][4] == "👎 avoid"
      and all("_price" not in str(row) for t in tab[1:] for row in t) and any("Feedback" in str(row) for row in tab[1])
      and any(b[0] == "bullet" and b[1].startswith("👎 few reviews") for b in ts) and ("h2", "How I judged") in ts and "your conditions: max € 20" in ts[1][1], str(ts)[:400])
tn = Templates.note("Line check", ["All good."], ["telegram ok", "gmail ok"])
tsr = Templates.site_report("Forno Bianchi", "https://drive/x", ["index.html", "menu.html"], notes=["checked in my browser"], langs=["it", "en"])
check("note + site templates: h1 first, paragraphs/bullets kept, long cells cut with an ellipsis", tn[0] == ("h1", "Line check") and ("bullet", "gmail ok") in tn
      and tsr[0][1] == "Website: Forno Bianchi" and ("bullet", "menu.html") in tsr and "it, en" in tsr[1][1] and P._cell("x" * 500, 100).endswith("…") and len(P._cell("x" * 500, 100)) == 100)

# ---- live (optional) ------------------------------------------------------------------------------------
if "--live" in sys.argv:
    from agent.google import Google
    G = Google()
    if G.connected():
        if os.path.exists(str(P.STATE)):
            os.unlink(str(P.STATE))
        prl = Progress(google=G, log=lambda k, **f: print("   log:", k, f))
        lk = prl.begin("score_progress live check", "test", ["write a line", "finish"], pace=FakePace(mode="slow", floor=60))
        prl.step("writing a line")
        prl.finish("live check done", doc_link="https://example.com/doc")
        prl.flush()
        time.sleep(2)
        body = G.docs_get(prl.state["day"]["id"]).get("body", {}).get("content", [])
        text = "".join(e.get("textRun", {}).get("content", "") for c in body for e in c.get("paragraph", {}).get("elements", []))
        check("LIVE: day doc written and read back (start + result lines)", "score_progress live check" in text and "live check done" in text, text[-300:])
        print("   day log:", prl.state["day"]["link"], "\n   job log:", lk)
    else:
        print("SKIP live (Google not connected)")

print(f"PROGRESS SCORE: {ok}/{total}")
