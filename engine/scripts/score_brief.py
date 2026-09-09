"""Understanding score: plain sentences → brief (kind, deliverable, pace, deadline/budget, topic, counterfeit flag) and the
amend step. Pure rules (no model) so it must hold on any PC.
Run:  python3 engine/scripts/score_brief.py --show | tail -40"""
import os
import sys
import time

os.environ.setdefault("BAI_STATE", "/tmp/bai_brief_state")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent.brief import Brief, parse_pace, topic_of   # noqa: E402

SHOW = "--show" in sys.argv
checks = []


def check(name, ok, note=""):
    checks.append((name, bool(ok)))
    if SHOW or not ok:
        print(("✅" if ok else "❌"), name, ("— " + str(note)[:110]) if note else "")


B = Brief(planner=None, log=lambda k, **f: None)
t0 = time.time()

# (message, expected fields)
CASES = [
    ("hey, real quick find me some good cheap reps for nike slippers",
     dict(kind="seller_check", deliverable="document", pace="quick", deadline_min=10, counterfeit=True, topic_has="slippers", topic_not="nike")),
    ("make it quick, i need it in 10 minutes: what's a good margin for dropshipping?",
     dict(kind="ask", pace="quick", deadline_min=10)),
    ("i'm going to work for 5 hours, take it real slow: find me reliable suppliers of bamboo toothbrushes in europe",
     dict(kind="seller_check", pace="slow", budget_min=300, topic_starts="suppliers of bamboo")),
    ("build a website for a small bakery in bergamo", dict(kind="build_site", deliverable="website")),
    ("watch https://youtu.be/vo6aDcnPzCU and tell me the business ideas", dict(kind="watch", deliverable="list", topic="https://youtu.be/vo6aDcnPzCU")),
    ("compare aliexpress vs cj dropshipping for shipping times to italy, write me a document", dict(kind="compare", deliverable="document")),
    ("https://www.shopify.com/blog/dropshipping-guide", dict(kind="summarize")),
    ("thanks!", dict(kind="chat")),
    ("how does epacket work", dict(kind_in=("research", "ask"), deliverable="answer")),
    ("find me a trustworthy vinted seller for used adidas sambas size 42, i'm out for 3 hours", dict(kind="seller_check", pace="slow", budget_min=180, counterfeit=False)),
    ("can you look for suppliers of cork phone cases, no rush", dict(pace="slow", topic="suppliers of cork phone cases")),
    ("look into these two videos https://youtu.be/vo6aDcnPzCU and https://youtu.be/DNdBJ5tgyjI and jot down the ideas", dict(kind="watch")),
    ("i'll be asleep for 8 hours, research the best print on demand platforms for europe and make me a doc with links",
     dict(kind_in=("research", "compare"), deliverable="document", pace="slow", budget_min=480)),
    ("ciao! trovami dei fornitori affidabili di tazze in ceramica, con calma", dict(pace="slow", kind="seller_check")),
    ("post on instagram that we have a summer sale", dict(kind="post")),
    ("make a tiktok post about our mugs", dict(kind="post", deliverable="post")),
    ("write a tiktok caption for the lamp", dict(kind="post")),
    ("draft an instagram story for the launch", dict(kind="post")),
    ("watch this tiktok about dropshipping", dict(kind="watch")),
    ("is this seller ok? https://www.vinted.it/member/12345", dict(kind_in=("seller_check", "visit", "summarize"))),
    ("get me the top 5 trending videos on youtube right now, google doc with links and the top comment for each", dict(kind="trending", deliverable="document", topic="")),
    ("what's trending on youtube about dropshipping?", dict(kind="trending", deliverable="list", topic="dropshipping")),
    ("top 3 most viewed youtube videos about bamboo toothbrushes this week", dict(kind="trending", topic="bamboo toothbrushes")),
    ("youtube trends on home decor, write me a doc", dict(kind="trending", deliverable="document", topic="home decor")),
    ("what are the trending products on tiktok", dict(kind_in=("research", "ask"))),
]
for msg, exp in CASES:
    b = B.make(msg)
    p = b["pace"]
    problems = []
    if "kind" in exp and b["kind"] != exp["kind"]:
        problems.append(f"kind={b['kind']}≠{exp['kind']}")
    if "kind_in" in exp and b["kind"] not in exp["kind_in"]:
        problems.append(f"kind={b['kind']}∉{exp['kind_in']}")
    if "deliverable" in exp and b["deliverable"] != exp["deliverable"]:
        problems.append(f"deliverable={b['deliverable']}")
    if "pace" in exp and p["pace"] != exp["pace"]:
        problems.append(f"pace={p['pace']}")
    if "deadline_min" in exp and p.get("deadline_min") != exp["deadline_min"]:
        problems.append(f"deadline={p.get('deadline_min')}")
    if "budget_min" in exp and p.get("budget_min") != exp["budget_min"]:
        problems.append(f"budget={p.get('budget_min')}")
    if "counterfeit" in exp and bool(b.get("counterfeit")) != exp["counterfeit"]:
        problems.append(f"counterfeit={b.get('counterfeit')}")
    t = (b.get("topic") or "").lower()
    if "topic" in exp and t != exp["topic"].lower():
        problems.append(f"topic={t!r}")
    if "topic_has" in exp and exp["topic_has"] not in t:
        problems.append(f"topic={t!r}")
    if "topic_not" in exp and exp["topic_not"] in t:
        problems.append(f"topic={t!r} (brand kept)")
    if "topic_starts" in exp and not t.startswith(exp["topic_starts"]):
        problems.append(f"topic={t!r}")
    if b["kind"] not in ("chat",) and (not b.get("steps") or len(b["steps"]) < 2 and b["kind"] not in ("ask", "summarize")):
        problems.append("no steps")
    check(msg[:70], not problems, "; ".join(problems) or f"{b['kind']}/{b['deliverable']}/{p['pace']}")

# pace parsing alone
for msg, exp in [("i need it in 10 minutes", ("quick", 10, None)), ("i'm at work for 5 hours, take it real slow", ("slow", None, 300)),
                 ("in half an hour", ("normal", 30, None)), ("no rush", ("slow", None, None)), ("entro 20 minuti", ("normal", 20, None)),
                 ("sono fuori per 2 ore", ("slow", None, 120)), ("asap", ("quick", None, None))]:
    p = parse_pace(msg)
    got = (p["pace"], p.get("deadline_min"), p.get("budget_min"))
    check(f"pace: {msg}", got == exp, got)

# topic cleaning
for msg, exp in [("hey, real quick find me some good cheap reps for nike slippers, i'm out for 3 hours", "reps for nike slippers"),
                 ("can you look for suppliers of cork phone cases, no rush", "suppliers of cork phone cases"),
                 ("please compare aliexpress vs cj dropshipping for shipping times to italy", "aliexpress vs cj dropshipping for shipping times to italy")]:
    t = topic_of(msg)
    check(f"topic: {msg[:50]}", t.lower().strip(" .,") == exp, t)

# amend: change of mind while the plan is pending
b = B.make("find me reliable suppliers of bamboo toothbrushes in europe, take your time")
b2 = B.amend(b, "actually make it quick, i need it in 15 minutes")
check("amend: pace changes to quick/15", b2["pace"]["pace"] == "quick" and b2["pace"]["deadline_min"] == 15, b2["pace"])
b3 = B.amend(b, "and write it as a document with pictures")
check("amend: deliverable becomes document", b3["deliverable"] == "document", b3["deliverable"])
b4 = B.amend(b, "only italy, not all of europe")
check("amend: goal keeps the new constraint", "italy" in Brief.text(b4).lower(), Brief.text(b4)[:120])
txt = Brief.text(b)
check("text: plan shows goal, steps and pace", all(x in txt.lower() for x in ("plan", "1.", "slow")) or ("1." in txt and "slow" in txt.lower()), txt[:160].replace("\n", " | "))

ok = sum(1 for _, o in checks if o)
print(f"\nSCORE brief {ok}/{len(checks)}  ({time.time() - t0:.1f}s)")
sys.exit(0 if ok == len(checks) else 1)
