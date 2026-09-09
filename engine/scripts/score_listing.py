"""Score the fuller listing card (agent/listing.py) + its use in the seller check. Offline. 20 checks."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent import listing
from agent.sellers import reliability

CHECKS = []


def check(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


SHOPIFY = '''<html><head><meta property="og:type" content="product"><meta property="og:price:amount" content="46.00"><meta property="og:price:currency" content="USD">
<script type="application/ld+json">{"@context":"http://schema.org/","@type":"Product","name":"15:21 iPhone 11 Cork Case",
"description":"Details:\\n\\nHandcrafted\\nMeasurements: 10x16 cm\\nDesigned in Stockholm, Sweden by 15:21\\nBacked by a four-year warranty\\n",
"sku":"iphone-11-cork-case","brand":{"@type":"Brand","name":"15:21"},
"offers":[{"@type":"Offer","sku":"iphone-11-cork-case","availability":"http://schema.org/InStock","price":46.0,"priceCurrency":"USD","url":"x"}]}</script>
</head><body>Cork case <img width="75"> 75 Day</body></html>'''

WOO = '''<html><head><script type="application/ld+json">{"@context":"https://schema.org/","@graph":[{"@type":"BreadcrumbList"},
{"@type":"Product","@id":"#p","name":"Bamboo toothbrush 4-pack","brand":"GreenBrush","material":"moso bamboo, nylon-4 bristles","color":"natural",
"aggregateRating":{"@type":"AggregateRating","ratingValue":"4.7","reviewCount":"212","bestRating":"5"},
"offers":{"@type":"Offer","price":"12,90","priceCurrency":"EUR","availability":"https://schema.org/OutOfStock","itemCondition":"https://schema.org/NewCondition",
"seller":{"@type":"Organization","name":"GreenBrush Srl"},
"shippingDetails":{"@type":"OfferShippingDetails","shippingRate":{"@type":"MonetaryAmount","value":"0","currency":"EUR"},
"shippingDestination":{"@type":"DefinedRegion","addressCountry":"IT"},
"deliveryTime":{"@type":"ShippingDeliveryTime","handlingTime":{"@type":"QuantitativeValue","minValue":0,"maxValue":1,"unitCode":"DAY"},"transitTime":{"@type":"QuantitativeValue","minValue":2,"maxValue":4,"unitCode":"DAY"}}},
"hasMerchantReturnPolicy":{"@type":"MerchantReturnPolicy","returnPolicyCategory":"https://schema.org/MerchantReturnFiniteReturnWindow","merchantReturnDays":30,"returnFees":"https://schema.org/FreeReturn"}}}]}</script></head><body></body></html>'''

OG_ONLY = '''<html><head><meta property="og:title" content="Cork wallet"><meta property="product:price:amount" content="1299.50"><meta property="product:price:currency" content="EUR">
<meta property="product:availability" content="out of stock"><meta property="product:brand" content="Corkor"><meta property="product:condition" content="new"></head><body>x</body></html>'''

AGG = '''<html><head><script type="application/ld+json">{"@type":"Product","name":"Lamp","offers":{"@type":"AggregateOffer","lowPrice":"19.00","highPrice":"39.00","priceCurrency":"EUR","offerCount":3,
"offers":[{"@type":"Offer","price":"19.00","availability":"InStock","seller":{"@type":"Person","name":"Lampshop"}}]}}</script></head><body></body></html>'''

BROKEN = '''<html><head><script type="application/ld+json">{"@type":"Product","name":"x",</script>
<script type="application/ld+json">{"@type":"Product","name":"Trailing","offers":{"@type":"Offer","price":"5","priceCurrency":"GBP",},}</script></head><body></body></html>'''

NOTHING = "<html><head><title>Category</title></head><body>75 x 200 image</body></html>"


@check("shopify: price + currency, stock, brand, SKU, warranty, measurements, origin from description")
def _():
    f = listing.card(SHOPIFY)
    assert f["Price"] == "$ 46,00" and f["_price"] == 46.0 and f["Currency"] == "USD", f
    assert f["Availability"] == "in stock" and f["Brand"] == "15:21" and f["SKU"] == "iphone-11-cork-case", f
    assert f["Warranty"] == "four-year warranty" and f["Size / measurements"] == "10x16 cm" and f["Ships from / origin"] == "Stockholm, Sweden", f
    assert f["_source"] == "structured data" and f["_title"].startswith("15:21")


@check("woocommerce @graph: comma decimal price, sold out, condition, seller, materials, colour, rating + reviews")
def _():
    f = listing.card(WOO)
    assert f["Price"] == "€ 12,90" and f["_price"] == 12.9 and f["Availability"] == "sold out", f
    assert f["Condition (as listed)"] == "new" and f["Seller"] == "GreenBrush Srl" and f["Brand"] == "GreenBrush", f
    assert f["Materials"].startswith("moso bamboo") and f["Colour"] == "natural" and f["Rating"] == "4.7/5" and f["Reviews"] == "212 reviews", f


@check("woocommerce: shipping cost/destination, delivery days, return policy")
def _():
    f = listing.card(WOO)
    assert f["Shipping"] == "free to IT", f
    assert f["Delivery time"] == "0–1 days handling, 2–4 days transit", f
    assert f["Returns"] == "30 days to return, free returns", f


@check("open graph only: price, availability, brand, condition — no JSON-LD needed")
def _():
    f = listing.card(OG_ONLY)
    assert f["Price"] == "€ 1.299,50" and f["_price"] == 1299.5 and f["Availability"] == "sold out" and f["Brand"] == "Corkor" and f["Condition (as listed)"] == "new", f


@check("aggregate offer: low price + inner offer's seller/availability")
def _():
    f = listing.card(AGG)
    assert f["Price"] == "€ 19,00" and f["Seller"] == "Lampshop" and f["Availability"] == "in stock", f


@check("broken JSON-LD: first blob skipped, trailing commas repaired")
def _():
    f = listing.card(BROKEN)
    assert f.get("Price") == "£ 5,00" and f["_title"] == "Trailing", f


@check("no product data → {} (the regex pass stays in charge)")
def _():
    assert listing.card(NOTHING) == {} and listing.card("") == {} and listing.card(None) == {}


@check("money: currencies + italian figures")
def _():
    assert listing.money("1234.5", "EUR") == "€ 1.234,50" and listing.money(9, "GBP") == "£ 9,00" and listing.money("12,90", "PLN") == "12,90 zł" and listing.money("x", "EUR") == ""


@check("merge: structured price replaces the regex guess, other regex facts kept")
def _():
    out = listing.merge({"Price": "75", "_price": 75.0, "Delivery time": "90 Day", "Materials": "cork"}, listing.card(SHOPIFY))
    assert out["Price"] == "$ 46,00" and out["_price"] == 46.0 and out["Materials"] == "cork" and out["Delivery time"] == "90 Day", out
    assert listing.merge({"Price": "3"}, {}) == {"Price": "3"}


@check("card_line: compact chat line")
def _():
    line = listing.card_line(listing.card(WOO))
    assert line.startswith("€ 12,90 · sold out · brand GreenBrush · shipping free to IT 0–1 days handling, 2–4 days transit · 4.7/5 (212 reviews) · 30 days to return, free returns"), line
    assert listing.card_line({}) == ""


@check("og_tags: both attribute orders, first value wins")
def _():
    t = listing.og_tags('<meta content="1" property="og:a"><meta property="og:a" content="2"><meta property="og:b" content="&amp;x">')
    assert t == {"og:a": "1", "og:b": "&x"}, t


@check("product_nodes: nested @graph / lists found, largest first")
def _():
    nodes = listing.product_nodes(WOO + SHOPIFY)
    assert len(nodes) == 2 and nodes[0]["name"].startswith("Bamboo"), [n["name"] for n in nodes]


@check("reliability: sold out is the first con; foreign currency + returns + warranty noted")
def _():
    f = listing.card(WOO)
    f["Ships from / origin"] = "Italy"
    g, v, pros, cons = reliability(f, "great quality recommend fast shipping arrived quickly as described", [{"platform": "instagram"}])
    assert cons[0] == "listing is sold out", cons
    assert any(p.startswith("returns: 30 days") for p in pros) and "free shipping" in pros, pros
    f2 = listing.card(SHOPIFY); f2["Materials"] = "cork"
    g2, v2, pros2, cons2 = reliability(f2, "", [])
    assert any("USD" in c for c in cons2) and "four-year warranty" in pros2, (pros2, cons2)


@check("reliability: 'no returns' is a con; a marketplace listing is not judged by these shop rules")
def _():
    g, v, pros, cons = reliability({"Returns": "no returns", "Availability": "sold out"}, "", [])
    assert "no returns accepted" in cons and "listing is sold out" in cons
    g, v, pros, cons = reliability({"Returns": "no returns", "Availability": "sold out", "_marketplace": "vinted"}, "", [])
    assert "no returns accepted" not in cons


@check("read_listing: card merged into facts, logged; regex-only when the page has none")
def _():
    from agent.sellers import SellerCheck
    logs = []

    class FakeT:
        walls = None
    sc = SellerCheck(FakeT(), log=lambda k, **f: logs.append((k, f)))

    class FB:
        def __init__(self, html, text):
            self.h, self.t = html, text
            self.page = self

        def open(self, url): pass
        def status(self): return "ok"
        def dismiss_banner(self): pass
        def extract_text(self): return self.t
        def title(self): return "Cork case"
        def content(self): return self.h
        def evaluate(self, js): return {}
        @property
        def url(self): return "https://shop.com/p"
    L = sc.read_listing(FB(SHOPIFY, "Cork case for sale. Price 75 image width. Shipping: free. Ships from Sweden."), "https://shop.com/p")
    assert L["facts"]["Price"] == "$ 46,00" and L["facts"]["Availability"] == "in stock" and L["facts"]["Shipping"] == "free", L["facts"]
    assert any(k == "listing_card" for k, _ in logs)
    L2 = sc.read_listing(FB(NOTHING, "Plain page. Price € 12,00. Shipping: free."), "https://shop.com/q")
    assert L2["facts"].get("_source") is None and L2["facts"]["Price"].startswith("€ 12"), L2["facts"]


@check("document table has Stock + Returns columns; 'How I judged' mentions the shop's own data (source text)")
def _():
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "agent", "sellers.py"), encoding="utf-8").read()
    assert 'header=["Seller", "Price", "Stock", "Shipping", "Delivery", "From", "Returns", "Verdict"]' in src
    assert "JSON-LD / Open Graph" in src and "_listing.card_line(best[0]['facts'])" in src


@check("desc facts: italian + english warranty / measurements / made in")
def _():
    f = listing._desc_facts("Garanzia 2 anni. Dimensioni: 20 x 30 cm. Prodotto in Italia.")
    assert f["Warranty"].lower().startswith("garanzia 2 anni") and f["Size / measurements"] == "20 x 30 cm" and f["Ships from / origin"] == "Italia", f
    f = listing._desc_facts("<p>Made in Portugal</p><p>Lifetime warranty</p>")
    assert f["Ships from / origin"] == "Portugal" and f["Warranty"] == "Lifetime warranty", f


@check("availability + condition words normalised from schema URLs and plain words")
def _():
    h = '<script type="application/ld+json">{"@type":"Product","name":"x","offers":{"@type":"Offer","price":"1","priceCurrency":"EUR","availability":"PreOrder","itemCondition":"https://schema.org/UsedCondition"}}</script>'
    f = listing.card(h)
    assert f["Availability"] == "pre-order" and f["Condition (as listed)"] == "used", f


@check("price valid until + GTIN fallback for SKU")
def _():
    h = '<script type="application/ld+json">{"@type":"Product","name":"x","gtin13":"4006381333931","offers":{"@type":"Offer","price":"1","priceCurrency":"EUR","priceValidUntil":"2026-12-31T00:00"}}</script>'
    f = listing.card(h)
    assert f["SKU"] == "GTIN13 4006381333931" and f["Price valid until"] == "2026-12-31", f


@check("returns: not permitted / unlimited / buyer pays")
def _():
    mk = lambda pol: listing.card('<script type="application/ld+json">{"@type":"Product","name":"x","offers":{"@type":"Offer","price":"1","priceCurrency":"EUR","hasMerchantReturnPolicy":' + pol + '}}</script>')["Returns"]
    assert mk('{"returnPolicyCategory":"https://schema.org/MerchantReturnNotPermitted"}') == "no returns"
    assert mk('{"returnPolicyCategory":"https://schema.org/MerchantReturnUnlimitedWindow"}') == "unlimited return window"
    assert mk('{"merchantReturnDays":14,"returnFees":"https://schema.org/ReturnShippingFees"}') == "14 days to return, buyer pays return shipping"


def main():
    ok = 0
    for name, fn in CHECKS:
        try:
            fn()
            print(f"OK   {name}")
            ok += 1
        except Exception as e:
            print(f"FAIL {name}: {e!r}")
    print(f"LISTING SCORE: {ok}/{len(CHECKS)} (offline)")
    return 0 if ok == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
