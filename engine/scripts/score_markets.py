"""Score item 3: deep Vinted/subito readers, Facebook waters-only, throttle, stealth/proxy.

17 checks run anywhere (parsers over fixtures + a fake browser for the wiring);
3 need a real browser (PC). No live marketplace is ever touched by the tests.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent import markets as M
from agent.markets import Throttle
from agent.sellers import SellerCheck

BASE = os.path.join("tests", "market") + os.sep

ok = total = 0


def check(name, cond, detail=""):
    global ok, total
    total += 1
    ok += bool(cond)
    print(f"{'OK  ' if cond else 'MISS'} {name}" + (f"  — {detail}" if detail and not cond else ""), flush=True)


def fix(name):
    with open(BASE + name, encoding="utf-8") as f:
        return f.read()


def nojson(html):
    return re.sub(r"<script.*?</script>", "", html, flags=re.S)


# ---- pure: Vinted ------------------------------------------------------------------
cards = M.parse_vinted_search(fix("vinted_search.html"))
check("vinted search: 3 cards with title/price/url", len(cards) == 3 and cards[0]["price"] == 18.5
      and cards[0]["url"].startswith("https://www.vinted.it/items/123"), str(cards[:1]))
cards_fb = M.parse_vinted_search(nojson(fix("vinted_search.html")))
check("vinted search: DOM fallback without JSON", len(cards_fb) == 3 and cards_fb[1]["price"] == 12.0, str(cards_fb[:1]))
vi = M.parse_vinted_item(fix("vinted_item.html"))
check("vinted item: deep facts", vi.get("_price") == 18.5 and vi.get("Size") == "42" and vi.get("Brand") == "CorkStep"
      and vi.get("Condition (as listed)") == "like new" and vi.get("Seller") == "luca_milano"
      and "47" in vi.get("Feedback", "") and "Vinted Go" in vi.get("Shipping", ""), str(vi))
vi_fb = M.parse_vinted_item(nojson(fix("vinted_item.html")))
check("vinted item: text fallback", vi_fb.get("_price") == 18.5 and vi_fb.get("Size") == "42"
      and vi_fb.get("Brand") == "CorkStep", str(vi_fb))

# ---- pure: subito ------------------------------------------------------------------
scards = M.parse_subito_search(fix("subito_search.html"))
check("subito search: 2 cards with location", len(scards) == 2 and scards[0]["price"] == 15.0
      and scards[0]["location"] == "Milano" and scards[0]["url"].endswith(".htm"), str(scards[:1]))
scards_fb = M.parse_subito_search(nojson(fix("subito_search.html")))
check("subito search: DOM fallback without JSON", len(scards_fb) == 2 and scards_fb[1]["price"] == 10.0, str(scards_fb[:1]))
si = M.parse_subito_item(fix("subito_item.html"))
check("subito item: deep facts", si.get("_price") == 15.0 and si.get("Location") == "Milano"
      and si.get("Seller type") == "private" and "TuttoSubito" in si.get("Shipping", "")
      and si.get("Listed") == "2026-09-08", str(si))
si_fb = M.parse_subito_item(nojson(fix("subito_item.html")))
check("subito item: fallback keeps price+shipping", si_fb.get("_price") == 15.0 and "Shipping" in si_fb, str(si_fb))

# ---- pure: facebook waters-only ------------------------------------------------------
v_login, n_login = M.facebook_probe(fix("fb_wall.html"))
v_cap, _ = M.facebook_probe("<html>checking your browser</html>", status="captcha")
v_empty, _ = M.facebook_probe("<html><body>hi</body></html>")
v_ok, _ = M.facebook_probe("<html><body>" + "public community page with events and posts. " * 20 + "</body></html>")
check("facebook probe: login/captcha/empty/ok", v_login == "login" and "shore" in n_login
      and v_cap == "captcha" and v_empty == "empty" and v_ok == "ok", f"{v_login} {v_cap} {v_empty} {v_ok}")

# ---- pure: throttle --------------------------------------------------------------------
clock = [1000.0]
slept = []


def _sleep(s):
    slept.append(round(s, 3))
    clock[0] += s


th = Throttle(gap=4.0, backoff_base=30.0, backoff_max=600.0, max_punish=2,
              sleep=_sleep, clock=lambda: clock[0], jitter=lambda: 0)
th.wait("https://www.vinted.it/a")
th.wait("https://www.vinted.it/b")
th.wait("https://www.subito.it/a")
check("throttle: 4s gap per host, other hosts free", slept == [4.0], str(slept))
r1, r2, r3 = th.punish("www.vinted.it"), th.punish("www.vinted.it"), th.punish("www.vinted.it")
th.wait("https://www.vinted.it/c")
check("throttle: backoff grows (30→60→120), gives up after max", (r1, r2, r3) == (True, True, False)
      and slept[-1] == 120.0 and th.failures("https://www.vinted.it/x") == 3, str(slept))

# ---- pure: proxy / stealth / urls ----------------------------------------------------------
old_proxy, old_stealth = os.environ.get("BAI_PROXY"), os.environ.get("BAI_STEALTH")
try:
    os.environ.pop("BAI_PROXY", None)
    p_none = M.proxy_config()
    os.environ["BAI_PROXY"] = "not a proxy"
    p_junk = M.proxy_config()
    os.environ["BAI_PROXY"] = "http://127.0.0.1:8080"
    p_bare = M.proxy_config()
    os.environ["BAI_PROXY"] = "http://me:s3cret@proxy.test:3128"
    p_auth = M.proxy_config()
finally:
    if old_proxy is None:
        os.environ.pop("BAI_PROXY", None)
    else:
        os.environ["BAI_PROXY"] = old_proxy
check("proxy: unset/junk/bare/auth", p_none is None and p_junk is None
      and p_bare == {"server": "http://127.0.0.1:8080"}
      and p_auth == {"server": "http://proxy.test:3128", "username": "me", "password": "s3cret"},
      f"{p_none} {p_junk} {p_bare} {p_auth}")
try:
    os.environ.pop("BAI_STEALTH", None)
    s_off = M.stealth_enabled()
    os.environ["BAI_STEALTH"] = "1"
    s_on = M.stealth_enabled()
finally:
    if old_stealth is None:
        os.environ.pop("BAI_STEALTH", None)
    else:
        os.environ["BAI_STEALTH"] = old_stealth
uas = {M.pick_ua(i) for i in range(5)}
check("stealth: flag + 5 rotating UAs + webdriver hidden", s_off is False and s_on is True and len(uas) == 5
      and "webdriver" in M.STEALTH_INIT and "AutomationControlled" in M.STEALTH_ARGS[0], f"{s_off} {s_on} {len(uas)}")
check("search URLs carry the query", "search_text=cork+slippers" in M.vinted_search_url("cork slippers")
      and "q=ciabatte" in M.subito_search_url("ciabatte"), "")


# ---- wiring through a fake browser (no playwright) -------------------------------------------
class FakeBrowser:
    def __init__(self, status="ok"):
        self._status = status
        self.opened = []
        self.html = ""

    def open(self, url):
        self.opened.append(url)
        if "vinted.it/catalog" in url:
            self.html = fix("vinted_search.html")
        elif "vinted.it/items" in url:
            self.html = fix("vinted_item.html")
        elif "subito.it/annunci" in url:
            self.html = fix("subito_search.html")
        elif "facebook.com" in url:
            self.html = fix("fb_wall.html")
        else:
            self.html = ""
        return "opened"

    def status(self):
        return self._status

    def dismiss_banner(self):
        return ""

    def extract_text(self):
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", self.html)).strip()

    @property
    def page(self):
        return self

    def title(self):
        return "Fake"

    def content(self):
        return self.html

    def evaluate(self, *a):
        return {}

    def search_results(self, query, limit=10):
        return []


S = SellerCheck(tasks=None, log=lambda kind, **f: None)
S.throttle = Throttle(gap=0, sleep=lambda s: None)
fb = FakeBrowser()
cands = S.candidates(fb, "cork slippers on vinted", n=4, sites=["vinted"])
check("sellers: named site searched directly, politely", len(cands) == 3
      and all("vinted.it/items" in c["url"] for c in cands)
      and any("vinted.it/catalog" in u for u in fb.opened)
      and "www.vinted.it" in S.throttle.hits, f"{len(cands)} {fb.opened[:1]}")
fb2 = FakeBrowser()
L = S.read_listing(fb2, "https://www.vinted.it/items/123-cork-slippers-42-like-new")
check("sellers: deep facts merged on vinted pages", L.get("facts", {}).get("Size") == "42"
      and L.get("facts", {}).get("Brand") == "CorkStep" and "47" in L.get("facts", {}).get("Feedback", ""), str(L.get("facts")))
fb3 = FakeBrowser()
Lf = S.read_listing(fb3, "https://www.facebook.com/marketplace/item/1")
walled = FakeBrowser(status="captcha")
wcards, wnote = M.search_market(walled, "subito", "ciabatte", throttle=Throttle(gap=0, sleep=lambda s: None))
check("sellers: facebook stops at the shore, walls back off", Lf.get("wall") == "login" and "shore" in Lf.get("note", "")
      and wcards == [] and "backed off" in wnote, f"{Lf.get('wall')} {wnote}")

# ---- real browser (PC; skipped where playwright is missing) ----------------------------------
try:
    import playwright  # noqa: F401
    from agent.tasks import Tasks
    HAS_PW = True
except Exception:
    HAS_PW = False

if HAS_PW:
    from agent.browser import Browser
    T = Tasks(log=lambda kind, **f: None)

    def run_browser():
        b = T.browser()
        out = {}
        for name in ("vinted_search.html", "vinted_item.html", "subito_search.html", "subito_item.html"):
            b.open("file://" + os.path.abspath(BASE + name))
            out[name] = b.page.content()
        stealth_ok = True
        try:
            os.environ["BAI_STEALTH"] = "1"
            b2 = Browser(log=lambda kind, **f: None)
            b2.open("file://" + os.path.abspath(BASE + "vinted_item.html"))
            stealth_ok = "Cork slippers" in b2.extract_text()
            b2.close()
        finally:
            if old_stealth is None:
                os.environ.pop("BAI_STEALTH", None)
            else:
                os.environ["BAI_STEALTH"] = old_stealth
        return out, stealth_ok

    pages, stealth_ok = T.on_hands(run_browser, timeout=180)
    T.on_hands(T.close_browser, timeout=30)
    bc = M.parse_vinted_search(pages["vinted_search.html"])
    bi = M.parse_vinted_item(pages["vinted_item.html"])
    check("browser: vinted fixtures parse live", len(bc) == 3 and bi.get("Seller") == "luca_milano", f"{len(bc)} {bi.get('Seller')}")
    bs = M.parse_subito_search(pages["subito_search.html"])
    bsi = M.parse_subito_item(pages["subito_item.html"])
    check("browser: subito fixtures parse live", len(bs) == 2 and bsi.get("Location") == "Milano", f"{len(bs)} {bsi.get('Location')}")
    check("browser: stealth mode opens pages fine", stealth_ok)
else:
    print("SKIP browser part (no playwright here — runs on the PC)")

print(f"MARKETS SCORE: {ok}/{total}  ({'with' if HAS_PW else 'no'} browser)")
