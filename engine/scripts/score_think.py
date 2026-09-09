"""Score item 9: thinking panel (owner viewer + agent API). Offline. 12 checks."""
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
    assert set(s) == {"why", "status", "lessons", "queue"}, s


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
