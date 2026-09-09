"""Score item 9 + I: thinking panel (owner viewer + agent API) and the plan → act → critique cycle per step. Offline."""
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent import mind as mindmod
from agent.mind import Mind
from agent.viewer import Viewer, PAGE

TMP = tempfile.mkdtemp(prefix="think_")
mindmod.LESSONS = pathlib.Path(TMP) / "lessons.jsonl"
mindmod.QUEUE_FILE = pathlib.Path(TMP) / "queue.json"

CHECKS = []


def check(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


def fresh():
    for f in ("lessons.jsonl", "queue.json"):
        try:
            (pathlib.Path(TMP) / f).unlink()
        except Exception:
            pass
    return Mind()


@check("snapshot has why/status/lessons/queue")
def _():
    s = fresh().think_snapshot()
    assert set(s) == {"why", "status", "lessons", "queue", "cycle"}, s


@check("idle snapshot is honest")
def _():
    s = fresh().think_snapshot()
    assert "Nothing running" in s["why"] and "free" in s["status"] and s["queue"] == "empty"


@check("why follows the job")
def _():
    m = fresh()
    m.begin("compare cork cases", kind="research", steps=["search", "read"], why="owner asked why")
    assert m.think_snapshot()["why"] == "owner asked why"


@check("status follows the doing")
def _():
    m = fresh()
    m.begin("compare cork cases", kind="research", steps=["search", "read"])
    m.doing("reading reviews of CorkStep")
    s = m.think_snapshot()["status"]
    assert "compare cork cases" in s and "reading reviews" in s, s


@check("reflect lands a lesson in the snapshot")
def _():
    m = fresh()
    m.begin("compare cork cases", kind="research", steps=["search"])
    m.reflect("handed over a comparison", delivered=True)
    s = m.think_snapshot()["lessons"]
    assert len(s) == 1 and len(s[0]) > 10, s


@check("lessons capped at 3, newest readable")
def _():
    m = fresh()
    for i in range(5):
        m.begin(f"job {i}", kind="research", steps=["s"])
        m.reflect(f"outcome {i}", delivered=True)
    assert len(m.think_snapshot()["lessons"]) == 3


@check("queue summary counts + highs")
def _():
    m = fresh()
    m.q_add("brainstorm ideas")
    m.q_add("research lamps")
    assert m.think_snapshot()["queue"] == "2 waiting (1 HIGH)", m.think_snapshot()["queue"]


@check("thinking_text has all sections")
def _():
    m = fresh()
    m.begin("compare cork cases", kind="research", steps=["search"])
    m.q_add("research lamps")
    t = m.thinking_text()
    assert "🧠" in t and "Why:" in t and "Queue:" in t and "compare cork cases" in t, t


@check("viewer state has no think until wired")
def _():
    assert Viewer().state()["think"] is None


@check("wired viewer serves the snapshot")
def _():
    m = fresh()
    m.begin("compare cork cases", kind="research", steps=["search"])
    v = Viewer()
    v.thinker = m
    assert v.state()["think"]["why"].startswith("Because you asked"), v.state()["think"]


@check("viewer survives a broken thinker")
def _():
    class Bad:
        def think_snapshot(self):
            raise RuntimeError("boom")

    v = Viewer()
    v.thinker = Bad()
    assert v.state()["think"] is None and v.state()["idle"] is True


@check("page renders the panel escaped")
def _():
    assert 'id="think"' in PAGE and "renderThink(s.think)" in PAGE
    i = PAGE.find("function renderThink")
    assert i > 0 and PAGE[i:i + 900].count("esc(") >= 4


# ---- item I: plan → act → critique, per step, in the agent's own words -------------------------------------------
def _job():
    m = fresh()
    m.begin("find reliable suppliers of bamboo toothbrushes", "seller_check",
            ["Search for candidates", "Open each listing", "Read reviews", "Judge", "Write the document"])
    m.on_event("browser_open", {"url": "https://duckduckgo.com/?q=bamboo+toothbrush"})
    m.on_event("plan_step", {"n": 2, "text": "reading listing 1/4: EcoBrush"})
    m.on_event("browser_open", {"url": "https://ecobrush.example/listing"})
    m.on_event("task_wall", {"url": "https://www.etsy.com/x", "wall": "captcha"})
    m.on_event("browser_open", {"url": "https://www.amazon.it/dp/x"})
    m.on_event("plan_step", {"n": 3, "text": "Read reviews"})
    m.on_event("task_wall", {"url": "https://trustpilot.com/x", "wall": "captcha"})
    return m


@check("cycle: every step has plan (what + why), acts, and a critique once the next step starts")
def _():
    c = _job().cycle()
    assert [x["n"] for x in c] == [1, 2, 3], c
    assert all(" — " in x["plan"] for x in c), [x["plan"] for x in c]
    assert c[0]["critique"] and c[1]["critique"] and c[2]["critique"] == "…still on it", c
    assert c[2]["verdict"] == "doing"


@check("cycle: a search engine page is a search, not a source — the search step is not judged thin")
def _():
    c = _job().cycle()[0]
    assert c["acts"] == ["searched duckduckgo.com"], c["acts"]
    assert c["verdict"] == "ok" and "results in hand" in c["critique"], c


@check("cycle: the reading step names hosts, counts the wall, judges 'enough'")
def _():
    c = _job().cycle()[1]
    assert "reading ecobrush.example" in c["acts"] and "etsy.com: captcha wall" in c["acts"] and "reading amazon.it" in c["acts"], c["acts"]
    assert c["verdict"] == "ok" and "2 page(s) read, 1 blocked" in c["critique"] and "go last next time" in c["critique"], c


@check("cycle: a step that hit only walls is judged 'redo' with a change of angle, not a retry")
def _():
    m = _job()
    m.on_event("plan_step", {"n": 5, "text": "Write the document"})
    c = m.cycle()[2]
    assert c["verdict"] == "redo" and "nothing readable" in c["critique"] and "instead of retrying" in c["critique"], c


@check("cycle: the same step announced twice stays one record; a written document closes as 'ok'")
def _():
    m = _job()
    m.on_event("plan_step", {"n": 5, "text": "Write the document"})
    m.on_event("plan_step", {"n": 5, "text": "Write the document"})
    m.on_event("doc_saved", {"title": "Seller check: bamboo toothbrushes"})
    assert len(m.cycle()) == 4, [x["n"] for x in m.cycle()]
    rec = m.reflect("document sent", delivered=True)
    assert rec["cycle"][-1]["verdict"] == "ok" and "deliverable exists" in rec["cycle"][-1]["critique"], rec["cycle"][-1]


@check("reflection in own words: the lesson names the weak step and what really happened there (no stock sentence)")
def _():
    m = _job()
    m.on_event("plan_step", {"n": 5, "text": "Write the document"})
    rec = m.reflect("document sent", delivered=True)
    l = rec["lesson"]
    assert l.startswith("seller_check: step 3 (Read reviews) was the weak point") and "trustpilot.com" in l, l
    assert "keep the same order" not in l and "went fine" not in l, l
    assert m.advice("seller_check") == [l.split(": ", 1)[1]]


@check("reflection in own words: a clean job names its sources and time instead of 'went fine'")
def _():
    m = fresh()
    m.begin("research cork phone cases", "research", ["Read 3–5 solid pages", "Keep the facts", "Write a short report"])
    m.on_event("browser_open", {"url": "https://www.bing.com/search?q=cork"})
    m.on_event("browser_open", {"url": "https://corkway.com/cases"})
    m.on_event("browser_open", {"url": "https://www.shopify.com/blog/cork"})
    m.on_event("plan_step", {"n": 3, "text": "Write a short report"})
    rec = m.reflect("report sent", delivered=True)
    l = rec["lesson"]
    assert "2 source(s) did the work (corkway.com, shopify.com)" in l and "start from those next time" in l, l
    assert m.advice("research") == [], m.advice("research")      # a good run is not advice for the next plan


@check("thinking_text and status_line carry the step-by-step check")
def _():
    m = _job()
    t = m.thinking_text()
    assert "Step by step:" in t and "1. plan: Search for candidates" in t and "did: searched duckduckgo.com" in t and "check:" in t, t
    assert "Last check (step 2)" in m.status_line(), m.status_line()


@check("viewer state ships the cycle to the page and the page renders it")
def _():
    v = Viewer()
    v.thinker = _job()
    st = v.state()["think"]
    assert st["cycle"] and st["cycle"][1]["acts"], st
    assert "t.cycle" in PAGE and "plan:" in PAGE and "check:" in PAGE


def main():
    ok = 0
    for name, fn in CHECKS:
        try:
            fn()
            print(f"OK   {name}")
            ok += 1
        except Exception as e:
            print(f"FAIL {name}: {e!r}")
    print(f"THINK SCORE: {ok}/{len(CHECKS)} (offline)")
    return 0 if ok == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
