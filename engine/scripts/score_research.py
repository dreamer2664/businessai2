"""Score item 2: query planner + multi-source + synthesis + widening when time is left. Offline (fake browser). 30 checks."""
import contextlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent import sources
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

TEXTS.update({
    "https://shop-a.com/shipping": ("Shipping — Shop A",
        "Shipping for cheap lamps is free above 50 euros and every lamp order leaves within 2 days, so cheap lamps arrive in 3 to 5 days."),
    "https://bing-only.com/lamps": ("Lamps Bing Found",
        "Cheap lamps sold here are 22 euros and the cheap lamps ship from Poland in 4 days, which is typical for the EU."),
})
RESULTS_BING = {"cheap lamps": ["https://bing-only.com/lamps", "https://shop-a.com/lamp", "https://shop-b.com/lamp"]}
LINKS = {"https://shop-a.com/lamp": [{"text": "Shipping & delivery", "href": "https://shop-a.com/shipping"},
                                     {"text": "Login", "href": "https://shop-a.com/login"},
                                     {"text": "Facebook", "href": "https://facebook.com/shopa"},
                                     {"text": "Prices", "href": "https://other-site.com/prices"}]}

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

    engine_used = "brave"

    def other_engines(self):
        return ["bing", "duckduckgo"]

    def links(self, limit=60):
        return LINKS.get(self.cur, [])[:limit]

    def search_results(self, q, n, engine=None):
        self.queries.append((q, engine) if engine else q)
        if self.fail:
            raise BrowserError("down")
        if engine == "bing":
            return [{"url": u} for u in RESULTS_BING.get(q, [])[:n]]
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
    def __init__(self, hurry=False, over=False, mode="normal", floor=False, budget=None):
        self._hurry, self._over, self.mode, self._floor, self._budget = hurry, over, mode, floor, budget

    def hurry(self):
        return self._hurry

    def over_budget(self):
        return self._over

    def should_stop(self):
        return False

    def under_floor(self):
        return self._floor

    def budget_left(self):
        return self._budget


class NoNet:
    """Wikipedia/YouTube answers without the network (the real helpers are exercised by score_sources)."""
    def __init__(self, wiki=True, yt=True):
        self.calls = []
        self.wiki, self.yt = wiki, yt

    def __enter__(self):
        self._w, self._y = sources.wikipedia, sources.youtube
        sources.wikipedia = lambda t, lang="en", timeout=8: (self.calls.append(("wiki", t, lang)) or
            ({"title": "Wikipedia: Lamp", "url": "https://en.wikipedia.org/wiki/Lamp",
              "text": "A lamp is a device that produces light. Cheap lamps are usually made of plastic and cost less than 30 euros."} if self.wiki else None))
        sources.youtube = lambda t, with_transcript=True: (self.calls.append(("yt", t)) or
            ({"title": "YouTube: Best cheap lamps 2026 (LampGuy, 120.000 views)", "url": "https://www.youtube.com/watch?v=abcdefghijk",
              "text": "so today we test cheap lamps and the first one costs 19 euros which is really cheap lamps for the money and it broke after two weeks so cheap lamps are not always the best deal",
              "views": 120000, "channel": "LampGuy"} if self.yt else None))
        return self

    def __exit__(self, *a):
        sources.wikipedia, sources.youtube = self._w, self._y


class RT(Tasks):
    def __init__(self, fake, **kw):
        super().__init__(log=lambda k, **f: None, **kw)
        self._fake = fake
        import pathlib, tempfile
        from agent.walls import WallMemory
        self.walls = WallMemory(path=pathlib.Path(tempfile.mkdtemp()) / "walls.json")     # never the real state file

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


# ---- widening when time is left (owner: "more places to search when time is left") ------------------------------

@check("widen: normal pace does NOT widen (no second engine, no wiki/yt calls)")
def _():
    with NoNet() as nn:
        t, fb, _ = fresh(pace=FakePace())
        out = t.research("cheap lamps")
    assert not nn.calls and not any(isinstance(q, tuple) for q in fb.queries) and "Widened" not in out, (nn.calls, fb.queries)


@check("widen: slow pace → second engine asked the base question")
def _():
    with NoNet():
        t, fb, _ = fresh(pace=FakePace(mode="slow"))
        out = t.research("cheap lamps")
    assert ("cheap lamps", "bing") in fb.queries, fb.queries
    assert "bing-only.com" in out and "second opinion from bing (1 page)" in out, out[-500:]


@check("widen: floor (at least N hours) and quiet budget > 10 min also widen; 5-min budget does not")
def _():
    with NoNet():
        t1, fb1, _ = fresh(pace=FakePace(floor=True)); t1.research("cheap lamps")
        t2, fb2, _ = fresh(pace=FakePace(budget=30 * 60)); t2.research("cheap lamps")
        t3, fb3, _ = fresh(pace=FakePace(budget=5 * 60)); t3.research("cheap lamps")
    assert ("cheap lamps", "bing") in fb1.queries and ("cheap lamps", "bing") in fb2.queries, (fb1.queries, fb2.queries)
    assert ("cheap lamps", "bing") not in fb3.queries, fb3.queries


@check("widen: follows the shipping link inside a good site, skips login/social/other-site links")
def _():
    with NoNet():
        t, fb, _ = fresh(pace=FakePace(mode="slow"))
        out = t.research("cheap lamps")
    assert "https://shop-a.com/shipping" in fb.opened and "Shipping & delivery › Shipping — Shop A" in out, (fb.opened, out[-600:])
    assert "https://shop-a.com/login" not in fb.opened and "https://other-site.com/prices" not in fb.opened, fb.opened
    assert "1 page inside the sites" in out, out[-400:]


@check("widen: Wikipedia + YouTube lines appear with their own key sentences")
def _():
    with NoNet() as nn:
        t, fb, _ = fresh(pace=FakePace(mode="slow"))
        out = t.research("cheap lamps")
    assert ("wiki", "cheap lamps", "en") in nn.calls and ("yt", "cheap lamps") in nn.calls, nn.calls
    assert "Wikipedia: Lamp" in out and "en.wikipedia.org/wiki/Lamp" in out and "less than 30 euros" in out, out[-900:]
    assert "YouTube: Best cheap lamps" in out and "19 euros" in out, out[-900:]
    assert "Wikipedia" in out.split("Widened because")[1] and "YouTube" in out.split("Widened because")[1]


@check("widen: italian topic asks it.wikipedia")
def _():
    with NoNet() as nn:
        t, fb, _ = fresh(pace=FakePace(mode="slow"))
        t.research("migliori lampade economiche")
    assert any(c[0] == "wiki" and c[2] == "it" for c in nn.calls), nn.calls


@check("widen: nothing found anywhere → honest line, no crash")
def _():
    with NoNet(wiki=False, yt=False):
        t, fb, _ = fresh(pace=FakePace(mode="slow"))
        fb.other_engines = lambda: []
        out = t.research("cheap lamps price")             # no deep links on these pages
    assert "Widened because there was time: tried a second engine and the inside pages — nothing new." in out, out[-300:]


@check("widen: hurry beats slow (no widening when the owner said hurry)")
def _():
    with NoNet() as nn:
        t, fb, _ = fresh(pace=FakePace(mode="slow", hurry=True))
        out = t.research("cheap lamps")
    assert not nn.calls and "Widened" not in out


@check("widen: second-engine failure is logged, the rest still runs")
def _():
    with NoNet() as nn:
        t, fb, _ = fresh(pace=FakePace(mode="slow"))
        real = fb.search_results
        def sr(q, n, engine=None):
            if engine:
                raise BrowserError("bing down")
            return real(q, n)
        fb.search_results = sr
        out = t.research("cheap lamps")
    assert nn.calls and "Wikipedia" in out and "second opinion from bing (0 pages)" in out, out[-400:]


@check("widen: memory note carries the extra sources too")
def _():
    with NoNet():
        t, fb, mem = fresh(pace=FakePace(mode="slow"))
        t.research("cheap lamps")
    urls = mem.notes[0][3]
    assert any("wikipedia" in u for u in urls) and any("bing-only" in u for u in urls), urls


@check("walls: a site is skipped only after two walls in the same job (one walled path must not hide the rest of the site)")
def _():
    t, fb, _ = fresh()
    fb.walls = {"https://shop-a.com/lamp": "captcha"}
    real_status = fb.status
    fb.status = lambda: fb.walls.get(fb.cur, "ok")
    t.pass_wall = lambda b, url, essential=False: False
    out = t.research("cheap lamps", n_pages=5)
    assert "https://shop-a.com/other" in fb.opened, fb.opened            # one wall → the site's other page still read
    fb2 = FakeB(); t2 = RT(fb2, memory=FakeMem())
    fb2.status = lambda: "captcha" if fb2.cur in ("https://shop-a.com/lamp", "https://shop-a.com/other") else "ok"
    t2.pass_wall = lambda b, url, essential=False: False
    t2.research("cheap lamps", n_pages=5)
    assert "https://shop-a.com/third" not in fb2.opened, fb2.opened      # two walls → the third page is not knocked


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
