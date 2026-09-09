"""Score item 2: query planner + multi-source + synthesis. Offline (fake browser). 19 checks."""
import contextlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent.browser import BrowserError
from agent.tasks import Tasks

CHECKS = []


def check(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


TEXTS = {
    "https://shop-a.com/lamp": ("Cheap Lamps at Shop A",
        "Cheap lamps are the easiest win for a rental flat, and every home needs at least two of them. These cheap lamps cost only 19 euros each, which is half the usual price of 39 euros for similar lamps."),
    "https://shop-a.com/other": ("More Lamps",
        "Our full range of cheap lamps ships in 48 hours and every lamp is tested for 100 hours before packing, so cheap lamps from us last for years."),
    "https://shop-a.com/third": ("Even More Lamps",
        "A third page of cheap lamps with 7 colours in stock and prices from 21 euros, because cheap lamps should fit every room of the house."),
    "https://shop-b.com/lamp": ("Shop B", "lamps lamps lamps"),
    "https://price-c.com/compare": ("Lamp Prices Compared",
        "We compared cheap lamps across 12 shops and the average price is 24 euros, with the cheapest lamps at 15 euros in the sale."),
    "https://blog-d.com/rev": ("Lamp Review",
        "Cheap lamps are the easiest win for a rental flat, and every home needs at least two of them. I tested 5 cheap lamps and 3 of them broke within a month, so check reviews."),
    "https://extra-e.com/de": ("German Prices",
        "Cheap lamps in germany cost around 29 euros, so prices in germany are higher than the 19 euros we pay at home."),
}

RESULTS = {
    "cheap lamps": ["https://shop-a.com/lamp", "https://shop-b.com/lamp", "https://reddit.com/r/x"],
    "cheap lamps price": ["https://shop-b.com/lamp", "https://price-c.com/compare"],
    "cheap lamps review": ["https://shop-a.com/lamp", "https://shop-a.com/other",
                            "https://shop-a.com/third", "https://blog-d.com/rev"],
}


class FakeB:
    def __init__(self):
        self.queries = []
        self.opened = []
        self.cur = ""
        self.page = self
        self.fail = False

    def title(self):
        return TEXTS.get(self.cur, ("", ""))[0]

    def search_results(self, q, n):
        self.queries.append(q)
        if self.fail:
            raise BrowserError("down")
        if "germany" in q.lower():
            return [{"url": "https://extra-e.com/de"}]
        return [{"url": u} for u in RESULTS.get(q, [])[:n]]

    def open(self, url):
        self.cur = url
        self.opened.append(url)

    def status(self):
        return "ok"

    def extract_text(self):
        return TEXTS.get(self.cur, ("", "nothing here"))[1]


class FakeMem:
    def __init__(self):
        self.notes = []

    def note(self, kind, topic, text, urls):
        self.notes.append((kind, topic, text, urls))


class FakePace:
    def __init__(self, hurry=False, over=False):
        self._hurry, self._over = hurry, over

    def hurry(self):
        return self._hurry

    def over_budget(self):
        return self._over

    def should_stop(self):
        return False


class RT(Tasks):
    def __init__(self, fake, **kw):
        super().__init__(log=lambda k, **f: None, **kw)
        self._fake = fake

    def _session(self):
        return contextlib.nullcontext(self._fake)


def fresh(**kw):
    fb = FakeB()
    mem = FakeMem()
    return RT(fb, memory=mem, **kw), fb, mem


@check("planner: 3 angles, base first, distinct")
def _():
    t, _, _ = fresh()
    qs = t.plan_queries("cheap lamps")
    assert len(qs) == 3 and qs[0] == "cheap lamps" and len(set(qs)) == 3, qs


@check("planner: fast is 1 query")
def _():
    t, _, _ = fresh()
    assert t.plan_queries("cheap lamps", fast=True) == ["cheap lamps"]


@check("planner: italian aspects in italian")
def _():
    t, _, _ = fresh()
    qs = t.plan_queries("migliori cover sughero")
    assert any("confronto" in q for q in qs) and not any(" review" in q or " guide" in q for q in qs), qs


@check("planner: what-is asks for explanations")
def _():
    t, _, _ = fresh()
    assert t.plan_queries("what is OSS") == ["OSS", "OSS explained", "OSS examples"]


@check("planner: no aspect echoes")
def _():
    t, _, _ = fresh()
    for topic in ("Vinted vs subito", "chef knives review", "best cork cases"):
        for q in t.plan_queries(topic):
            words = q.lower().split()
            assert len(words) == len(set(words)), (topic, q)


@check("multi: pages come from 2+ angles")
def _():
    t, fb, _ = fresh()
    out = t.research("cheap lamps")
    assert "price-c.com" in out and "shop-a.com/lamp" in out, out[:300]
    assert "3 search angles" in out


@check("dedupe: same url opened once")
def _():
    t, fb, _ = fresh()
    t.research("cheap lamps")
    assert fb.opened.count("https://shop-a.com/lamp") == 1, fb.opened


@check("domain cap: max 2 pages per domain")
def _():
    t, fb, _ = fresh()
    t.research("cheap lamps", n_pages=5)
    a = [u for u in fb.opened if "shop-a.com" in u]
    assert len(a) == 2 and "https://shop-a.com/third" not in fb.opened, fb.opened


@check("forums still skipped")
def _():
    t, fb, _ = fresh()
    out = t.research("cheap lamps")
    assert "reddit" not in out and "reddit.com/r/x" not in fb.opened


@check("synthesis: agreement flagged")
def _():
    t, _, _ = fresh()
    out = t.research("cheap lamps", n_pages=4)
    assert "agreed by 2 sources" in out, out[:600]


@check("synthesis: header + per-page bullets kept")
def _():
    t, _, _ = fresh()
    out = t.research("cheap lamps")
    assert "Across the" in out and "• " in out and "https://shop-a.com/lamp" in out


@check("report shape kept")
def _():
    t, _, _ = fresh()
    out = t.research("cheap lamps")
    assert out.startswith("Research: cheap lamps") and "pages read in" in out


@check("memory note carries urls")
def _():
    t, _, mem = fresh()
    t.research("cheap lamps")
    assert mem.notes and mem.notes[0][0] == "research" and any("shop-a.com" in u for u in mem.notes[0][3])


@check("all searches failing says so")
def _():
    t, fb, _ = fresh()
    fb.fail = True
    assert "(web search failed" in t.research("cheap lamps")


@check("owner change adds pages + is reported")
def _():
    t, fb, _ = fresh()
    t.owner_change = "also prices in germany"
    out = t.research("cheap lamps")
    assert "You added" in out and "extra-e.com" in out, out[-400:]
    assert any("germany" in q for q in fb.queries)


@check("hurry: 1 angle, fewer pages")
def _():
    t, fb, _ = fresh(pace=FakePace(hurry=True))
    out = t.research("cheap lamps")
    assert "search angles" not in out and len(fb.queries) == 1, fb.queries
    assert len([u for u in fb.opened if "shop-a.com/lamp" in u or "price" in u]) <= 2


@check("budget expiring mid-run stops + says so")
def _():
    class TripPace(FakePace):
        def __init__(self):
            super().__init__()
            self.n = 0

        def over_budget(self):
            self.n += 1
            return self.n > 4

    t, fb, _ = fresh(pace=TripPace())
    out = t.research("cheap lamps")
    assert "budget ran out" in out, out[-300:]


@check("synthesize: empty in, empty out")
def _():
    assert Tasks._synthesize([]) == []


@check("synthesize: dupes collapse")
def _():
    s = "Cheap lamps are the easiest win for a rental flat, and this sentence is long enough to survive any filter we apply."
    lines = Tasks._synthesize([("t", "https://a.com/1", [s, s]), ("t", "https://b.com/2", [s])])
    assert sum(1 for ln in lines if "easiest win" in ln) == 1, lines


def main():
    ok = 0
    for name, fn in CHECKS:
        try:
            fn()
            print(f"OK   {name}")
            ok += 1
        except Exception as e:
            print(f"FAIL {name}: {e!r}")
    print(f"RESEARCH SCORE: {ok}/{len(CHECKS)} (offline)")
    return 0 if ok == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
