"""Score customer replies that need the shop's own pages: python3 engine/scripts/score_shopfacts.py [--show] [--nofacts]
--nofacts drafts WITHOUT the shop facts (baseline) so the gain is visible."""
import os, re, sys, time
sys.path.insert(0, ".")
os.environ.pop("DISPLAY", None)
from agent.planner import Planner
from agent.brain import Brain
from agent.inbox import Inbox
from agent.tasks import Tasks
from agent.shopfacts import ShopFacts
show = "--show" in sys.argv; nofacts = "--nofacts" in sys.argv
only = next((a.lower() for a in sys.argv[1:] if not a.startswith("--")), "")      # e.g. "product" = rows under the "## Product" heading
rows, block = [], ""
for line in open("tests/shopfacts.txt", encoding="utf-8"):
    line = line.rstrip("\n")
    if line.startswith("## "): block = line[3:].lower(); continue
    if not line or line.startswith("#") or "\t" not in line: continue
    if only and only not in block and only not in line.lower(): continue
    rows.append((line.split("\t") + ["", ""])[:3])
P = Planner(); T = Tasks(planner=P)
S = ShopFacts(tasks=T, log=lambda k, **f: None)
if nofacts:
    S.forget(); S = None
else:
    rep = S.learn("file://" + os.path.abspath("tests/pages/shop.html"))
    if rep.startswith("I couldn't read") or rep.startswith("I have no browser"):
        print("this test needs a browser (playwright): " + rep + " (counts as SKIP in the battery)")
        sys.exit(2)
    print(rep.splitlines()[1], flush=True)
    T.on_hands(T.close_browser, timeout=30)                      # Playwright lives on the hands thread
I = Inbox(planner=P, brain=Brain(), shopfacts=S)
ok = 0; t0 = time.time(); notes = []
try:
    for msg, must, mustnot in rows:
        t1 = time.time()
        d = I.draft({"id": "t", "from": "tester@example.com", "text": msg})
        low = d["text"].lower()
        must_ok = all(any(a.strip().lower() in low for a in grp.split("|")) for grp in must.split(";") if grp.strip())
        not_ok = not (mustnot and re.search(mustnot, low))
        flags_ok = not d["checks"]
        good = must_ok and not_ok and flags_ok; ok += good
        why = [] if good else [w for w, v in (("missing must", not must_ok), ("has must-not", not not_ok), ("flags:" + ";".join(d["checks"]), not flags_ok)) if v]
        print(f"{'OK  ' if good else 'MISS'} {time.time()-t1:4.0f}s {d['kind']:17s} facts={d.get('shop_facts', 0)} {msg[:60]}", flush=True)
        if show or not good: notes.append(f"    {why} -> {d['text'][:420]!r}" + (f"\n      (model draft rejected: {d['rejected']['checks']} -> {d['rejected']['text'][:300]!r})" if d.get("rejected") else ""))
        if show or not good: print(notes[-1], flush=True)
    print(f"SHOPFACTS SCORE: {ok}/{len(rows)}  ({time.time()-t0:.0f}s){'  [no facts — baseline]' if nofacts else ''}")
finally:
    P.stop()
