"""Deal hunter (agent/deals.py): matching, ranking, placeholder prices, the list flow, the watcher, per-site notes.
Offline part always runs; the live part (Vinted + Subito real searches, marketplace probe) runs when a browser is there.
Run: python3 engine/scripts/score_deals.py [--offline]"""
import os, sys, time
os.environ["BAI_STATE"] = "/tmp/bai_deals_state"
sys.path.insert(0, ".")
import shutil; shutil.rmtree("/tmp/bai_deals_state", ignore_errors=True)
from agent import deals as D
from agent.brief import Brief, parse_pace
from agent import brief as B

ok = tot = 0
def check(name, cond, got=""):
    global ok, tot
    tot += 1; ok += bool(cond); print(("✅" if cond else "❌"), name, "" if cond else f"→ {str(got)[:200]}")

# ---- matching --------------------------------------------------------------------------------------------------
check("novel never matches a console", not D.matches({"title": "City - Alessandro Baricco"}, "nintendo switch"))
check("'Nintendo Switch Lite' matches", D.matches({"title": "Nintendo Switch Lite"}, "nintendo switch"))
check("3-word item tolerates one missing word", D.matches({"title": "Dyson V8 aspirapolvere"}, "dyson v8 absolute"))
check("numbers must match: 'ps5 controller' ≠ 'ps4 controller'", not D.matches({"title": "Controller PS5 DualSense"}, "ps4 controller"))
check("'iphone 12' ≠ 'iphone 13'", not D.matches({"title": "iPhone 13 128GB"}, "iphone 12"))
check("details are soft: 'iphone 13 128gb' matches 'iPhone 13 Pro'", D.matches({"title": "iPhone 13 Pro"}, "iphone 13 128gb"))
check("size is soft: 'bici da corsa taglia 54' matches a tg 56 road bike", D.matches({"title": "Bici da corsa Bianchi tg 56"}, "bici da corsa taglia 54"))
check("synonyms: 'bicicletta corsa' matches 'bici da corsa'", D.matches({"title": "Bicicletta corsa Pinarello"}, "bici da corsa taglia 54"))
check("'nike air max 90' ≠ 'Air Max 97'", not D.matches({"title": "Nike Air Max 97"}, "nike air max 90"))
check("vague items are spotted: iphone, dyson, tv — not 'iphone 12' / 'dyson v8'", [n for n, _ in D.vague_items([{"name": "iphone"}, {"name": "iphone 12"}, {"name": "dyson v8"}, {"name": "dyson"}, {"name": "bici usata"}, {"name": "tv"}])] == ["iphone", "dyson", "bici usata", "tv"])

# ---- ranking ---------------------------------------------------------------------------------------------------
cards = [{"title": "Nintendo Switch", "price": 1.0}, {"title": "Nintendo Switch Lite", "price": 74.2, "total": 74.2}, {"title": "Nintendo Switch 1", "price": 100.45, "total": 100.45},
         {"title": "Nintendo Switch completa", "price": 120}, {"title": "Custodia Nintendo Switch", "price": 5}, {"title": "Nintendo switch oled", "price": 220}, {"title": "Nintendo Switch non funziona", "price": 30}]
ref = D.typical_price(cards, "nintendo switch")
check("typical price ignores € 1 placeholders, cases, Lite and broken", ref and 100 <= ref <= 130, ref)
order = [c["title"] for c in sorted(cards, key=lambda c: D.rank_key(c, "nintendo switch", ref))]
check("cheapest real console first", order[0] == "Nintendo Switch 1", order)
check("Lite after every plain model", order.index("Nintendo Switch Lite") > order.index("Nintendo switch oled"), order)
check("€ 1 'make an offer' and the case go last", set(order[-2:]) == {"Nintendo Switch", "Custodia Nintendo Switch"} or order[-1] in ("Nintendo Switch", "Custodia Nintendo Switch"), order)
check("broken unit after the real ones", order.index("Nintendo Switch non funziona") > order.index("Nintendo Switch completa"), order)
check("'Nintendo switch zelda' € 30 is a game, not the cheapest console", D.rank_key({"title": "Nintendo switch zelda", "price": 30}, "nintendo switch", 105)[0] >= 2)
check("'Nintendo switch' € 40, bare title, far below typical → not the top pick", D.rank_key({"title": "Nintendo switch", "price": 40.6}, "nintendo switch", 105)[0] >= 1)
check("'Nintendo Switch Completa!' € 104 stays clean", D.rank_key({"title": "Nintendo Switch Completa!", "price": 104.65}, "nintendo switch", 105)[0] == 0)
check("'Stray Xbox series X one S' € 27 is a game (two console families + below the floor)", D.rank_key({"title": "Stray Xbox series X one S", "price": 26.95}, "xbox series x", None)[0] >= 2)
check("'Xbox series x come nuova' € 30 is below any real Series X → penalised", D.rank_key({"title": "Xbox series x come nuova", "price": 30}, "xbox series x", None)[0] >= 2)
check("'Xbox Series X + 2 controller bundle' € 320 is the console (bundle, not an accessory)", D.rank_key({"title": "Xbox Series X + 2 controller bundle", "price": 320}, "xbox series x", None)[0] == 0)
check("'PS5 con 2 giochi' € 350 is the console", D.rank_key({"title": "PS5 con 2 giochi", "price": 350}, "ps5", None)[0] == 0)
check("'FIFA 23 PS4 e PS5' € 15 is a game", D.rank_key({"title": "FIFA 23 PS4 e PS5", "price": 15}, "ps5", None)[0] >= 2)
check("€ 1–3 is always a placeholder, even with no typical price", D.price_is_placeholder(1.0) and D.price_is_placeholder(3) and not D.price_is_placeholder(25))
dy = [{"title": "Dyson v8 Cyclone Hanger", "price": 11.2}, {"title": "Dyson v8", "price": 42.7}, {"title": "Dyson V8 Absolute", "price": 99}, {"title": "Filtri Dyson V8", "price": 16}]
refd = D.typical_price(dy, "dyson v8")
best = min(dy, key=lambda c: D.rank_key(c, "dyson v8", refd))
check("a € 11 'hanger' is never the best Dyson", best["title"] == "Dyson v8", best)
check("placeholder: € 1 yes, € 42.70 no, € 999 yes", D.price_is_placeholder(1, 100) and not D.price_is_placeholder(42.7, 100) and D.price_is_placeholder(999, 100))
check("city filter: Barletta card passes, Milano card fails", D.city_ok({"location": "Barletta (BT)"}, "Barletta") and not D.city_ok({"location": "Milano (MI)"}, "Barletta"))

# ---- the list flow (brief) -------------------------------------------------------------------------------------
Bf = Brief()
b = Bf.make("find me the best deals for nintendo switch and ps4 controller on vinted and subito")
check("'best deals for X and Y on vinted and subito' → items straight away", [i["name"] for i in (b.get("items") or [])] == ["nintendo switch", "ps4 controller"] and b["kind"] == "research", b.get("items"))
b = Bf.make("I want the best deals for the list I'm about to send, on vinted, subito, banggood and dhgate. Take around 4-5 minutes.")
check("'the list I'm about to send' with minutes → waits, floor 4 min, budget 5", b.get("needs_list") and b["pace"]["floor_min"] == 4 and b["pace"]["budget_min"] == 5, (b.get("needs_list"), b["pace"]))
check("sites include banggood + dhgate", {"banggood", "dhgate"} <= set(b["sites"]), b["sites"])
items = Brief.list_items("1. nintendo switch — max 150\n2) ps4 controller (under 25)\n3. dyson v8")
check("numbered list with (under 25) parses", [(i["name"], i["max"]) for i in items] == [("nintendo switch", 150), ("ps4 controller", 25), ("dyson v8", None)], items)
b2 = Brief.with_items(b, items)
check("with_items → runnable brief", b2.get("items") and not b2.get("needs_list") and b2["kind"] == "research", b2.get("goal"))

# ---- notes / summary -------------------------------------------------------------------------------------------
class _T:                                # a Tasks stand-in: no browser
    def _session(self):
        import contextlib
        @contextlib.contextmanager
        def cm(): yield None
        return cm()
    def _release_page(self): pass
    notify = staticmethod(lambda t: None)
H = D.DealHunter(_T())
res = [{"item": {"name": "dyson v8", "max": None}, "best": [dict(dy[1], site="vinted", seller="anna", condition="good", url="https://www.vinted.it/items/1")], "n_found": 4, "ref": refd},
       {"item": {"name": "xbox one", "max": 50}, "best": [], "n_found": 0, "ref": None}]
txt = H.summary(res, {"wallapop": "wallapop: blocks this machine (an error page instead of results) — it may work from your PC"}, ["vinted", "wallapop"], 95)
check("summary: one line per item, best deal with price + site", "• dyson v8: best Dyson v8 — € 42.70 · good · seller anna (vinted)" in txt, txt)
check("summary: an item with nothing says so with the cap and why", "xbox one: nothing under € 50: no listing with those words on vinted" in txt and "wallapop could not be searched" in txt, txt)
check("summary: blocked sites are named honestly", "Not searched properly: wallapop" in txt, txt)
path = H.document(res, {}, ["vinted", "banggood"], "Barletta")
html = open(path, encoding="utf-8").read()
check("document: glance cards + used-vs-new note + kind per listing", "At a glance" in html and 'class=glance' in html and "Used vs new" in html and "second-hand, private seller" in html, path)
check("document: the listing title links to the listing, short readable url", 'open the listing → vinted.it/items/1' in html, path)
check("document: the empty item explains why and what to do", "nothing under € 50" in html and ("watch it" in html or "Try" in html), path)
nl = H.nothing_line({"name": "xbox series x", "max": 30, "_seen": 5, "_near": True, "_min_clean": 280}, ["vinted", "subito"], {}, long=True)
check("nothing_line: look-alikes + 'real ones start around € 280' + watch tip", "look-alikes" in nl and "€ 280" in nl and "watch it" in nl, nl)
nl = H.nothing_line({"name": "xbox one", "max": 50, "_seen": 0}, ["vinted", "wallapop"], {"wallapop": "wallapop: blocks this machine"}, long=True)
check("nothing_line: no listing at all → says which sites answered and which could not be searched", "no listing with those words on vinted" in nl and "wallapop could not be searched" in nl, nl)

# ---- depth from the pace ---------------------------------------------------------------------------------------
from agent.pace import Pace
P = Pace(); H2 = D.DealHunter(_T(), pace=P)
P.set({"pace": "quick", "deadline_min": None, "budget_min": None, "floor_min": None, "why": ""}, "x"); check("quick → depth 1", H2.depth() == 1, H2.depth())
P.set({"pace": "normal", "deadline_min": None, "budget_min": None, "floor_min": None, "why": ""}, "x"); check("normal → depth 2", H2.depth() == 2, H2.depth())
P.set(parse_pace("take around 5-6 hours"), "x"); check("slow / floor → depth 3", H2.depth() == 3, H2.depth())

# ---- watcher (offline: a fake market) ---------------------------------------------------------------------------
from agent import markets
_calls = {"n": 0}
def fake_search(b, site, query, limit=8, throttle=None, price_to=None, order=None, page=1):
    _calls["n"] += 1
    if _calls["n"] <= 2:                       # round 1 = two passes (newest + price) → old card only; from round 2 the new one appears
        return [{"title": "Dyson v8", "price": 60, "url": "https://x/1"}], ""
    return [{"title": "Dyson v8 absolute", "price": 52, "url": "https://x/2"}, {"title": "Dyson v8", "price": 60, "url": "https://x/1"}], ""
_orig = markets.search_market; markets.search_market = fake_search
W = H.watcher([{"name": "dyson v8", "max": None}], ["vinted"], [{"item": {"name": "dyson v8", "max": None}, "best": [{"title": "Dyson v8", "price": 60, "url": "https://x/1", "site": "vinted"}], "n_found": 1, "ref": 60}])
better, line = W.round()
check("watch round 1: nothing new → silent", better == [] and "0 better" in line, (better, line))
better, line = W.round()
check("watch round 2: a cheaper real listing → one 🔔 message with the link", len(better) == 1 and better[0].startswith("🔔 Better deal for dyson v8") and "https://x/2" in better[0], better)
check("a € 35 'Dyson V8' is below what a working one costs → never the best", D.rank_key({"title": "Dyson v8", "price": 35}, "dyson v8", 60)[0] >= 2)
better, line = W.round()
check("watch round 3: the same listing is not announced twice", better == [], better)
markets.search_market = _orig
# persistence: a watch survives a restart
W.until = time.time() + 3600; W.save()
W2 = D.Watcher.load(H)
check("watcher saved and reloaded (items, best, seen, rounds)", W2 is not None and W2.items == W.items and W2.rounds == 3 and "https://x/2" in W2.seen and W2.best["dyson v8"]["url"] == "https://x/2", W2 and W2.__dict__)
check("watcher status line", W2.status().startswith("👀 Watching vinted for dyson v8") and "3 round(s)" in W2.status(), W2.status())
W.until = time.time() - 5; W.save()
check("an expired watch is not reloaded", D.Watcher.load(H) is None)
D.Watcher.clear()

# ---- live part -------------------------------------------------------------------------------------------------
if "--offline" not in sys.argv:
    try:
        from agent.tasks import Tasks
        T = Tasks(log=lambda k, **f: None)
        HL = D.DealHunter(T, log=T.log)
        t0 = time.time()
        path, summary, results = T.on_hands(HL.run, [{"name": "nintendo switch", "max": 150}], ["vinted", "subito"], None, 3, True, timeout=400)
        r = results[0] if results else {}
        check("LIVE vinted+subito: listings found for 'nintendo switch' ≤ 150", r.get("n_found", 0) >= 3, summary)
        b0 = (r.get("best") or [{}])[0]
        check("LIVE best is a real console (no placeholder, no case)", b0 and D.rank_key(b0, "nintendo switch", r.get("ref"))[0] == 0 and (b0.get("total") or b0.get("price")) >= 40, b0.get("title"))
        check("LIVE best listing has seller facts or a picture", bool(b0.get("facts")) or bool(b0.get("image")), list((b0.get("facts") or {}).keys()))
        check("LIVE document written", path and os.path.exists(path), path)
        print(f"   (live run {time.time() - t0:.0f} s: {summary.splitlines()[1][:120] if summary else ''})")
        T.close_browser()
    except Exception as e:
        for n in ("LIVE vinted+subito", "LIVE best is a real console", "LIVE best listing facts", "LIVE document written"):
            check(n + " (browser unavailable)", False, e)

print(f"DEALS SCORE: {ok}/{tot}")
