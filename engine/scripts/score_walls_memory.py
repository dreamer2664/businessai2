"""Score the wall memory (agent/walls.py) + its hooks in research / sellers / browser search order. Offline. 18 checks."""
import contextlib
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent.walls import WallMemory, host_of

CHECKS = []


def check(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def fresh(t=1_000_000.0):
    d = tempfile.mkdtemp()
    c = Clock(t)
    return WallMemory(path=pathlib.Path(d) / "walls.json", clock=c), c


@check("host_of: url, bare host, www stripped")
def _():
    assert host_of("https://www.etsy.com/uk/market/x") == "etsy.com" and host_of("Etsy.com") == "etsy.com" and host_of("") == ""


@check("one wall: remembered, ordered last, NOT skipped")
def _():
    w, c = fresh()
    w.hit("https://www.etsy.com/market/cork", "captcha")
    assert w.recent("etsy.com") == 1 and not w.skip("https://etsy.com/x")
    items = [{"url": "https://etsy.com/a"}, {"url": "https://shop.com/b"}]
    assert [i["url"] for i in w.order(items)] == ["https://shop.com/b", "https://etsy.com/a"]


@check("two walls in 2 h → skipped; two walls 3 h apart → not")
def _():
    w, c = fresh()
    w.hit("https://a.com/1"); c.t += 600; w.hit("https://a.com/2")
    assert w.skip("https://a.com/3")
    w2, c2 = fresh()
    w2.hit("https://b.com/1"); c2.t += 3 * 3600; w2.hit("https://b.com/2")
    assert not w2.skip("https://b.com/3")


@check("four walls in 24 h → skipped even when spread out")
def _():
    w, c = fresh()
    for _ in range(4):
        w.hit("https://c.com/x"); c.t += 5 * 3600
    assert w.skip("https://c.com/y")


@check("a clean read forgives: out of skip, count halved")
def _():
    w, c = fresh()
    w.hit("https://a.com/1"); w.hit("https://a.com/2")
    assert w.skip("https://a.com/3")
    c.t += 60
    w.clear("https://a.com/3")
    assert not w.skip("https://a.com/4") and w.recent("a.com") <= 1


@check("persists across instances; entries older than 7 days dropped")
def _():
    w, c = fresh()
    w.hit("https://old.com/1"); c.t += 3 * 86400; w.hit("https://new.com/1")
    w2 = WallMemory(path=w.path, clock=c)
    assert w2.recent("new.com") == 1 and "old.com" in w2.hosts
    c.t += 5 * 86400
    w3 = WallMemory(path=w.path, clock=c)
    assert "old.com" not in w3.hosts and "new.com" in w3.hosts, w3.hosts


@check("engine_order: the engine that walled in the last 6 h goes last, older walls keep the order")
def _():
    w, c = fresh()
    hosts = {"brave": "https://search.brave.com/search?q={q}", "yahoo": "https://search.yahoo.com/search?p={q}", "bing": "https://www.bing.com/search?q={q}"}
    w.hit(hosts["brave"], "captcha")
    assert w.engine_order(["brave", "yahoo", "bing"], hosts) == ["yahoo", "bing", "brave"]
    c.t += 7 * 3600
    assert w.engine_order(["brave", "yahoo", "bing"], hosts) == ["brave", "yahoo", "bing"]


@check("forget one / all")
def _():
    w, c = fresh()
    w.hit("https://a.com/1"); w.hit("https://b.com/1")
    w.forget("a.com")
    assert "a.com" not in w.hosts and "b.com" in w.hosts
    w.forget()
    assert not w.hosts


@check("text: empty line, then hosts with counts / skipping / clean read; forget hint")
def _():
    w, c = fresh()
    assert "No walls remembered" in w.text()
    w.hit("https://a.com/1"); w.hit("https://a.com/2")
    t = w.text()
    assert "a.com — 2× in 24 h (captcha)" in t and "skipping for now" in t and "/walls forget" in t, t


@check("broken file → empty memory, no crash; unwritable path → hit() still returns")
def _():
    d = pathlib.Path(tempfile.mkdtemp()) / "walls.json"
    d.write_text("{not json", encoding="utf-8")
    w = WallMemory(path=d)
    assert w.hosts == {}
    w2 = WallMemory(path=pathlib.Path("/proc/nope/walls.json"))
    w2.hit("https://a.com/1")
    assert w2.recent("a.com") == 1


# ---- hooks -------------------------------------------------------------------------------------------------------

def _research_rig():
    import importlib.util
    spec = importlib.util.spec_from_file_location("sr", os.path.join(os.path.dirname(__file__), "score_research.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


@check("research: a wall on a site is remembered in the wall memory; a clean page clears")
def _():
    m = _research_rig()
    t, fb, _ = m.fresh()
    t.walls, c = fresh()
    fb.status = lambda: "captcha" if fb.cur == "https://shop-b.com/lamp" else "ok"
    t.pass_wall = lambda b, url, essential=False: False
    t.research("cheap lamps")
    assert t.walls.recent("shop-b.com") == 1 and t.walls.recent("shop-a.com") == 0, t.walls.hosts


@check("research: a site that walled twice lately is not opened at all (wall_skipped logged)")
def _():
    m = _research_rig()
    t, fb, _ = m.fresh()
    logs = []
    t.log = lambda k, **f: logs.append((k, f))
    t.walls, c = fresh()
    t.walls.hit("https://shop-a.com/x"); t.walls.hit("https://shop-a.com/y")
    t.research("cheap lamps", n_pages=5)
    assert not any("shop-a.com" in u for u in fb.opened), fb.opened
    assert any(k == "wall_skipped" for k, _ in logs), logs[:5]


@check("research: walled-lately sites are read LAST, clean sites first")
def _():
    m = _research_rig()
    t, fb, _ = m.fresh()
    t.walls, c = fresh()
    t.walls.hit("https://shop-a.com/x")                      # one wall: still read, but after the others
    t.research("cheap lamps", n_pages=2)
    first = [u for u in fb.opened if "reddit" not in u][:2]
    assert first[0] == "https://shop-b.com/lamp" and "shop-a.com" in first[1], fb.opened


@check("browser.search: engine order comes from the wall memory when set")
def _():
    from agent.browser import Browser
    calls = []

    class B(Browser):
        def __init__(self):
            self.log = lambda k, **f: None
            self.walls, self.c = fresh()
            self.walls.hit(self.ENGINES["brave"], "captcha")

        def open(self, url):
            calls.append(url); return "page"

        def status(self):
            return "ok"

        def _organic(self, limit=10):
            return [{"url": "https://x.com"}] * 3
    b = B()
    b.search("lamps")
    assert "yahoo.com" in calls[0] and b.engine_used == "yahoo", calls
    assert b.walls.recent(b.ENGINES["yahoo"]) == 0
    calls.clear()
    b.search("lamps", engine="brave")                       # an explicit engine is honoured regardless
    assert "brave.com" in calls[0]


@check("browser.search: a walled engine is recorded, a working one clears its record")
def _():
    from agent.browser import Browser
    calls = []

    class B(Browser):
        def __init__(self):
            self.log = lambda k, **f: None
            self.walls, self.c = fresh()

        def open(self, url):
            calls.append(url); self.cur = url; return "page"

        def status(self):
            return "captcha" if "brave" in self.cur else "ok"

        def _organic(self, limit=10):
            return [] if "brave" in self.cur else [{"url": "https://x.com"}] * 3
    b = B()
    b.search("lamps")
    assert b.walls.recent(b.ENGINES["brave"]) == 1 and b.engine_used == "yahoo"
    b.c.t += 60
    b.search("lamps")
    assert "yahoo.com" in calls[-1] and len([u for u in calls if "brave" in u]) == 1, calls   # brave now last → not even tried after yahoo answered


@check("sellers.candidates: walled-twice shop skipped, walled-once shop last")
def _():
    from agent.sellers import SellerCheck

    class FakeT:
        def __init__(self):
            self.walls, self.c = fresh()
    T = FakeT()
    T.walls.hit("https://bad.com/p"); T.walls.hit("https://bad.com/q")
    T.walls.hit("https://meh.com/p")
    sc = SellerCheck(T)

    class FB:
        def search_results(self, q, n):
            return [{"url": "https://bad.com/lamp", "title": "Bad lamp"}, {"url": "https://meh.com/lamp", "title": "Meh lamp"}, {"url": "https://good.com/lamp", "title": "Good lamp"}]
    out = sc.candidates(FB(), "lamp", n=3)
    urls = [o["url"] for o in out]
    assert urls == ["https://good.com/lamp", "https://meh.com/lamp"], urls


@check("sellers.read_listing: a wall is remembered; the owner's own link is essential (solver may ask the owner)")
def _():
    from agent.sellers import SellerCheck
    asked = []

    class FakeT:
        def __init__(self):
            self.walls, self.c = fresh()

        def pass_wall(self, b, url, essential=False, site=None):
            asked.append(essential); return False
    T = FakeT()
    sc = SellerCheck(T)

    class FB:
        def open(self, url): pass
        def status(self): return "captcha"
    r = sc.read_listing(FB(), "https://shop.com/item", essential=True)
    assert r.get("wall") == "captcha" and asked == [True] and T.walls.recent("shop.com") == 1


@check("agent /walls command text + forget (core wiring)")
def _():
    import re
    from agent import core
    src = open(core.__file__, encoding="utf-8").read()
    assert 'low.startswith("/walls")' in src and "self.tasks.walls.forget" in src and "self.tasks.walls.text()" in src
    assert "/walls" in src.split("/lessons —")[1][:400]


def main():
    ok = 0
    for name, fn in CHECKS:
        try:
            fn()
            print(f"OK   {name}")
            ok += 1
        except Exception as e:
            print(f"FAIL {name}: {e!r}")
    print(f"WALLS MEMORY SCORE: {ok}/{len(CHECKS)} (offline)")
    return 0 if ok == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
