"""Score the extra places research looks when time is left (agent/sources.py). Offline — no network. 18 checks."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent import sources
from agent.browser import Browser

CHECKS = []


def check(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


SHOP = "https://www.howcork.com/collections/cork-phone-cases"
LINKS = [{"text": "Skip to content", "href": SHOP + "#main"},
         {"text": "BRANDS", "href": "https://www.howcork.com/pages/brands"},
         {"text": "Log in", "href": "https://www.howcork.com/customer_authentication/redirect"},
         {"text": "Cart", "href": "https://www.howcork.com/cart"},
         {"text": "Shipping & Tracking", "href": "https://www.howcork.com/pages/shipping-and-tracking"},
         {"text": "FAQ", "href": "https://www.howcork.com/pages/faq-page"},
         {"text": "Returns & Refunds", "href": "https://www.howcork.com/pages/refund-policy"},
         {"text": "ABOUT US", "href": "https://www.howcork.com/pages/about-us"},
         {"text": "Instagram", "href": "https://instagram.com/howcork"},
         {"text": "Wholesale prices", "href": "https://other-shop.com/wholesale"},
         {"text": "Ningbo Kaxite Sealing Materials Co., Ltd. cork sheet manufacturer", "href": "https://www.howcork.com/"},
         {"text": "Home", "href": "https://www.howcork.com/"},
         {"text": "Catalogue PDF", "href": "https://www.howcork.com/files/catalogue.pdf"}]


@check("deep_links: shipping first, then FAQ/returns, about last")
def _():
    out = sources.deep_links(LINKS, SHOP, limit=4)
    urls = [u for _, u in out]
    assert urls[0].endswith("/pages/shipping-and-tracking"), out
    assert urls[1:3] == ["https://www.howcork.com/pages/faq-page", "https://www.howcork.com/pages/refund-policy"], out
    assert urls[3].endswith("/pages/about-us"), out


@check("deep_links: login, cart, social, other site, pdf, home page and long company names are skipped")
def _():
    urls = [u for _, u in sources.deep_links(LINKS, SHOP, limit=20)]
    bad = [u for u in urls if any(x in u for x in ("customer_authentication", "/cart", "instagram", "other-shop", ".pdf"))]
    assert not bad and "https://www.howcork.com" not in urls and "https://www.howcork.com/" not in urls, urls


@check("deep_links: same-site only, limit honoured, labels kept")
def _():
    out = sources.deep_links(LINKS, SHOP, limit=2)
    assert len(out) == 2 and out[0][0] == "Shipping & Tracking", out


@check("deep_links: no links / no host → []")
def _():
    assert sources.deep_links([], SHOP) == [] and sources.deep_links(LINKS, "file:///tmp/x.html") == []


@check("deep_links: italian menu words work (spedizioni, prezzi, ingrosso)")
def _():
    ls = [{"text": "Spedizioni e resi", "href": "https://negozio.it/spedizioni"}, {"text": "Listino ingrosso", "href": "https://negozio.it/ingrosso"},
          {"text": "Chi siamo", "href": "https://negozio.it/chi-siamo"}, {"text": "Privacy", "href": "https://negozio.it/privacy"}]
    out = sources.deep_links(ls, "https://negozio.it/prodotti/cover", limit=3)
    assert [u for _, u in out] == ["https://negozio.it/ingrosso", "https://negozio.it/spedizioni", "https://negozio.it/chi-siamo"], out


@check("related: real matches (plural, glued words, initials)")
def _():
    assert sources.related("Lamp", "cheap lamps")
    assert sources.related("Drop shipping", "dropshipping")
    assert sources.related("Import One-Stop Shop", "IOSS registration italy")
    assert sources.related("Toothbrush", "bamboo toothbrush supplier")


@check("related: lookalikes rejected (Carphone Warehouse, Casetify, Temu, LAMPS)")
def _():
    assert not sources.related("Carphone Warehouse", "cork phone case wholesale europe")
    assert not sources.related("Casetify", "phone case")
    assert not sources.related("Temu", "vinted vs subito")
    assert not sources.related("Light Airborne Multi-Purpose System", "cheap lamps")
    assert sources.related("Import One-Stop Shop", "ioss registration")


@check("wiki queries: whole topic, then without shop words, then first words")
def _():
    assert sources._wiki_queries("print on demand t-shirt suppliers europe") == ["print on demand t-shirt suppliers europe", "print on demand t-shirt", "print on demand"]
    assert sources._wiki_queries("dropshipping") == ["dropshipping"]
    assert sources._wiki_queries("migliori fornitori dropshipping italia")[1] == "dropshipping"


@check("rank titles: exact topic beats stray articles; disambiguation-looking and place titles dropped")
def _():
    r = sources._rank_titles(["Nachiarkoil lamp", "Neon lamp", "Lamp", "Cork (city)"], "cheap lamps")
    assert r == ["Lamp"], r
    r = sources._rank_titles(["Print on demand", "Out of print", "Printify"], "print on demand")
    assert r[0] == "Print on demand", r


@check("transcript_sentences: topic chunks with a number/cue, capitalised, ellipsis when cut")
def _():
    text = ("so today we test cheap lamps and the first one costs 19 euros which is really cheap lamps for the money and it broke after "
            "two weeks so cheap lamps are not always the best deal and now something completely different about my cat")
    out = sources.transcript_sentences(text, "cheap lamps", limit=3)
    assert out and out[0].startswith("So today") and "19 euros" in out[0] and out[0].endswith("…"), out
    assert all("lamps" in x for x in out) and len(out) <= 3, out


@check("transcript_sentences: empty / off-topic → []")
def _():
    assert sources.transcript_sentences("", "lamps") == []
    assert sources.transcript_sentences("the weather in Rome is nice today and tomorrow it rains a lot more than usual for september", "cheap lamps") == []


@check("views_text: italian thousands")
def _():
    assert sources.views_text(120000) == "120.000" and sources.views_text(0) == "0" and sources.views_text(None) == "0"


@check("wikipedia: offline → None, never raises")
def _():
    real = sources._get_json
    sources._get_json = lambda *a, **k: (_ for _ in ()).throw(OSError("no network"))
    try:
        assert sources.wikipedia("dropshipping") is None
    finally:
        sources._get_json = real


@check("wikipedia: candidates filtered + best picked + disambiguation skipped (canned answers)")
def _():
    real = sources._get_json
    calls = []

    def fake(url, timeout=8):
        calls.append(url)
        if "list=search" in url:
            return {"query": {"search": [{"title": "IOSS"}, {"title": "Import One-Stop Shop"}, {"title": "Operational security"}]}}
        if "/summary/IOSS" in url:
            return {"type": "disambiguation", "title": "IOSS", "extract": "IOSS can refer to: Import One-Stop Shop, an electronic portal…" * 3}
        return {"type": "standard", "title": "Import One-Stop Shop", "extract": "Import One-Stop Shop is an electronic one-stop shop for VAT on goods imported into the EU, worth up to 150 euros.",
                "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Import_One-Stop_Shop"}}}
    sources._get_json = fake
    try:
        r = sources.wikipedia("IOSS")
        assert r and r["title"] == "Wikipedia: Import One-Stop Shop" and r["url"].endswith("Import_One-Stop_Shop"), r
        assert not any("Operational" in c for c in calls), calls
    finally:
        sources._get_json = real


@check("wikipedia: nothing related → None without a summary call")
def _():
    real = sources._get_json
    calls = []
    sources._get_json = lambda url, timeout=8: (calls.append(url) or {"query": {"search": [{"title": "John Gilligan (criminal)"}, {"title": "Smart Telecom"}]}})
    try:
        assert sources.wikipedia("cork phone case wholesale europe") is None
        assert calls and all("list=search" in c for c in calls), calls              # only searches, never a summary of a lookalike
    finally:
        sources._get_json = real


@check("youtube: picks the most-watched, falls back to all-time when the year is thin, no transcript → text ''")
def _():
    from agent import video
    real_s, real_t = video.search_videos, video.transcript
    calls = []

    def fake_search(q, n=10, sort="relevance", period=None):
        calls.append((sort, period))
        if period == "year":
            return [{"id": "aaaaaaaaaaa", "title": "tiny", "channel": "x", "views": 12, "seconds": 300, "url": "https://www.youtube.com/watch?v=aaaaaaaaaaa"}]
        return [{"id": "bbbbbbbbbbb", "title": "Big one", "channel": "Chan", "views": 250000, "seconds": 600, "url": "https://www.youtube.com/watch?v=bbbbbbbbbbb"},
                {"id": "ccccccccccc", "title": "3 hour stream", "channel": "Chan", "views": 900000, "seconds": 3 * 3600, "url": "https://www.youtube.com/watch?v=ccccccccccc"}]
    video.search_videos = fake_search
    video.transcript = lambda vid, prefer=None: (_ for _ in ()).throw(RuntimeError("no captions"))
    try:
        y = sources.youtube("cheap lamps")
        assert y and y["url"].endswith("bbbbbbbbbbb") and "250.000 views" in y["title"] and y["text"] == "", y
        assert ("views", "year") in calls and ("views", None) in calls, calls
    finally:
        video.search_videos, video.transcript = real_s, real_t


@check("youtube: search failure → None")
def _():
    from agent import video
    real_s = video.search_videos
    video.search_videos = lambda *a, **k: (_ for _ in ()).throw(OSError("offline"))
    try:
        assert sources.youtube("cheap lamps") is None
    finally:
        video.search_videos = real_s


@check("browser.unwrap: bing /ck/a and yahoo RU= give the real URL; plain URLs untouched")
def _():
    assert Browser.unwrap("https://www.bing.com/ck/a?!&&p=abc&u=a1aHR0cHM6Ly93d3cuY29yay1zaGVldC5jb20vY29yay1pcGhvbmUtY2FzZQ&ntb=1") == "https://www.cork-sheet.com/cork-iphone-case"
    assert Browser.unwrap("https://r.search.yahoo.com/_ylt=Aw/RV=2/RE=1/RO=10/RU=https%3a%2f%2fwww.howcork.com%2fcollections%2fcork/RK=2/RS=abc-") == "https://www.howcork.com/collections/cork"
    assert Browser.unwrap("https://example.com/x?y=1") == "https://example.com/x?y=1"
    assert Browser.unwrap("") == "" and Browser.unwrap("https://www.bing.com/ck/a?u=zz") == "https://www.bing.com/ck/a?u=zz"


def main():
    ok = 0
    for name, fn in CHECKS:
        try:
            fn()
            print(f"OK   {name}")
            ok += 1
        except Exception as e:
            print(f"FAIL {name}: {e!r}")
    print(f"SOURCES SCORE: {ok}/{len(CHECKS)} (offline)")
    return 0 if ok == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
