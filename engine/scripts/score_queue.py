"""Score item 7: priority queue + duration parsing + budget enforcement. Offline. 19 checks."""
import os
import pathlib
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent import mind as mindmod
from agent.brief import parse_duration, parse_pace
from agent.mind import Mind
from agent.pace import Pace
from agent.tasks import Tasks

mindmod.QUEUE_FILE = pathlib.Path(tempfile.mkdtemp(prefix="q_")) / "queue.json"

CHECKS = []


def check(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


def fresh():
    try:
        mindmod.QUEUE_FILE.unlink()
    except Exception:
        pass
    return Mind()


@check("classify: research is scrape/high")
def _():
    m = fresh()
    assert m.q_classify("research cheap lamps on Vinted") == ("scrape", 0)
    assert m.q_classify("compare suppliers for mugs") == ("scrape", 0)
    assert m.q_classify("visit thesun.com") == ("scrape", 0)


@check("classify: plain jobs stay high")
def _():
    m = fresh()
    assert m.q_classify("/do the thing") == ("job", 0)
    assert m.q_classify("order 20 more lamps") == ("job", 0)
    assert m.q_classify({"goal": "build my site", "steps": []}) == ("job", 0)


@check("classify: memory writes are log/medium")
def _():
    m = fresh()
    assert m.q_classify("remember the mug supplier is Terra") == ("log", 1)
    assert m.q_classify("note: call the supplier tomorrow") == ("log", 1)


@check("classify: brainstorming is low")
def _():
    m = fresh()
    assert m.q_classify("brainstorm names for the shop") == ("brainstorm", 2)
    assert m.q_classify("which product should I push?") == ("brainstorm", 2)


@check("drain order: high, med, low")
def _():
    m = fresh()
    m.q_add("brainstorm ideas")
    m.q_add("research lamps")
    m.q_add("remember the mayor")
    assert [m.q_next()["item"] for _ in range(3)] == ["research lamps", "remember the mayor", "brainstorm ideas"]
    assert m.q_next() is None


@check("FIFO inside a priority")
def _():
    m = fresh()
    m.q_add("first job")
    m.q_add("second job")
    assert m.q_next()["item"] == "first job"
    assert m.q_next()["item"] == "second job"


@check("peek sees the next without popping")
def _():
    m = fresh()
    assert m.q_peek() is None
    m.q_add("brainstorm ideas")
    m.q_add("research lamps")
    assert m.q_peek()["item"] == "research lamps"
    assert len(m.queue) == 2


@check("positions are 1-based")
def _():
    m = fresh()
    assert (m.q_add("a"), m.q_add("b")) == (1, 2)


@check("reprioritize jumps the queue")
def _():
    m = fresh()
    m.q_add("brainstorm ideas")                  # low, shown as #2
    m.q_add("remember the mayor")                # med, shown as #1
    assert m.q_set(2, 0) is not None             # brainstorm -> high
    got = [m.q_next()["item"] for _ in range(2)]
    assert got == ["brainstorm ideas", "remember the mayor"], got


@check("reprioritize bad number")
def _():
    m = fresh()
    m.q_add("only one")
    assert m.q_set(5, 0) is None


@check("clear counts")
def _():
    m = fresh()
    m.q_add("a")
    m.q_add("b")
    assert m.q_clear() == 2 and m.q_list().startswith("Queue's empty")


@check("queue survives restart")
def _():
    m = fresh()
    m.q_add("brainstorm ideas")
    m.q_add("research lamps")
    m2 = Mind()
    assert len(m2.queue) == 2
    assert m2.q_next()["item"] == "research lamps"


@check("brief dicts survive + list shows goals")
def _():
    m = fresh()
    m.q_add({"goal": "build my site", "steps": ["a"]})
    m2 = Mind()
    assert m2.queue[0]["item"]["goal"] == "build my site"
    assert "build my site" in m2.q_list() and "HIGH" in m2.q_list()


@check("list numbers follow priority order")
def _():
    m = fresh()
    m.q_add("brainstorm ideas")
    m.q_add("research lamps")
    lst = m.q_list()
    assert lst.index("research lamps") < lst.index("brainstorm ideas"), lst


@check("english durations")
def _():
    cases = {"in 10 minutes": 10, "within 2 hours": 120, "in an hour": 60,
             "in half an hour": 30, "a 45 minute timer": 45, "in seven hours": 420,
             "in forty minutes": 40, "in a minute": 1}
    for t, want in cases.items():
        assert parse_duration(t) == want, (t, parse_duration(t))


@check("italian durations")
def _():
    cases = {"tra due ore": 120, "fra 30 minuti": 30, "in mezz'ora": 30, "mezz'ora": 30,
             "un'ora": 60, "tra dieci minuti": 10, "torno tra un'ora": 60}
    for t, want in cases.items():
        assert parse_duration(t) == want, (t, parse_duration(t))


@check("duration traps stay silent")
def _():
    assert parse_duration("I need this in a hurry") is None
    assert parse_duration("no duration here") is None
    assert parse_duration("in a hurry, quick") is None


@check("pace: away is budget, need-by is deadline")
def _():
    assert parse_pace("I'm away for 5 hours, take it slow")["budget_min"] == 300
    assert parse_pace("torno fra due ore")["budget_min"] == 120
    assert parse_pace("torno in mezz'ora")["budget_min"] == 30
    assert parse_pace("research this, I need it in 10 minutes")["deadline_min"] == 10


@check("over_budget true/false/unset")
def _():
    p = Pace()
    assert p.over_budget() is False
    p.budget_until = time.time() + 3600
    assert p.over_budget() is False
    p.budget_until = time.time() - 1
    assert p.over_budget() is True


@check("tasks sees the budget (and survives no pace)")
def _():
    p = Pace()
    p.budget_until = time.time() - 1
    assert Tasks(pace=p)._over_budget() is True
    p.budget_until = time.time() + 3600
    assert Tasks(pace=p)._over_budget() is False
    assert Tasks()._over_budget() is False


def main():
    ok = 0
    for name, fn in CHECKS:
        try:
            fn()
            print(f"OK   {name}")
            ok += 1
        except Exception as e:
            print(f"FAIL {name}: {e!r}")
    print(f"QUEUE SCORE: {ok}/{len(CHECKS)} (offline)")
    return 0 if ok == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
