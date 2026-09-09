"""The fuller listing card — what a product page states about itself in structured data, before any regex guessing.

Most shops (Shopify, WooCommerce, Magento, PrestaShop, Etsy, Amazon, eBay…) embed the product as JSON-LD
(<script type="application/ld+json"> with "@type": "Product") and/or Open Graph / product: meta tags. That block is
written by the shop itself, so it is the most trustworthy source on the page:

  price + currency (no more "Price: 75" read off an image width), availability (in stock / sold out / pre-order),
  brand, SKU / GTIN, condition, rating + review count, seller name, shipping cost / days / destination when the shop
  publishes them (OfferShippingDetails), return policy (MerchantReturnPolicy), colour / size / material, warranty
  and measurements when they stand in the description.

card(html, text, url) → facts dict in the same key language the seller check already uses ("Price", "_price",
"Shipping", "Delivery time", "Rating", "Reviews", "Seller", "Condition (as listed)", "Materials", "Ships from / origin")
plus the new ones ("Availability", "Brand", "SKU", "Currency", "Returns", "Warranty", "Size / measurements", "Colour",
"_source": "structured data"). Empty dict when the page has no product data — the caller falls back to the regexes.
Nothing here needs a browser: pure functions over the page HTML + visible text, fully testable offline.
"""
import html as _html
import json
import re

CUR = {"EUR": "€", "USD": "$", "GBP": "£", "CHF": "CHF", "PLN": "zł", "SEK": "kr", "DKK": "kr", "CZK": "Kč", "JPY": "¥", "CNY": "¥", "CAD": "C$", "AUD": "A$"}
AVAIL = {"instock": "in stock", "instoreonly": "in store only", "onlineonly": "online only", "limitedavailability": "limited availability",
         "preorder": "pre-order", "presale": "pre-order", "backorder": "back-order", "outofstock": "sold out", "soldout": "sold out", "discontinued": "discontinued"}
COND = {"newcondition": "new", "usedcondition": "used", "refurbishedcondition": "refurbished", "damagedcondition": "damaged"}


def _blobs(page_html):
    """Every JSON-LD script's parsed content (list; broken ones skipped)."""
    out = []
    for m in re.finditer(r'<script[^>]+type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>', page_html or "", re.S | re.I):
        raw = _html.unescape(m.group(1)).strip()
        if not raw:
            continue
        try:
            out.append(json.loads(raw))
        except Exception:
            try:
                out.append(json.loads(re.sub(r",\s*([}\]])", r"\1", raw)))     # trailing commas, the usual sin
            except Exception:
                continue
    return out


def _walk(o):
    """Yield every dict in a JSON-LD tree (incl. @graph and lists)."""
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from _walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v)


def _types(d):
    t = d.get("@type", "")
    return [t.lower()] if isinstance(t, str) else [str(x).lower() for x in t]


def product_nodes(page_html):
    """The Product dicts on the page (most complete first)."""
    prods = [d for b in _blobs(page_html) for d in _walk(b) if any(t in ("product", "productmodel", "individualproduct", "productgroup", "vehicle", "book") for t in _types(d))]
    prods.sort(key=lambda d: -len(json.dumps(d)))
    return prods


def _text(x):
    if isinstance(x, dict):
        return str(x.get("name") or x.get("@id") or x.get("value") or "").strip()
    if isinstance(x, list):
        return ", ".join(t for t in (_text(v) for v in x) if t)[:80]
    return str(x or "").strip()


def _num(x):
    try:
        return float(str(x).replace(",", ".").replace(" ", ""))
    except Exception:
        return None


def money(amount, currency):
    amount = _num(amount)
    if amount is None:
        return ""
    cur = (currency or "").upper()
    s = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")       # 1.234,50 — the owner reads Italian figures
    sym = CUR.get(cur, cur)
    return f"{sym} {s}" if sym in ("€", "$", "£", "CHF", "C$", "A$", "¥") else (f"{s} {sym}" if sym else s)


def _offer_of(p):
    """The first (cheapest) Offer dict of a Product, flattened from AggregateOffer / lists."""
    o = p.get("offers")
    if isinstance(o, list):
        o = sorted((x for x in o if isinstance(x, dict)), key=lambda x: _num(x.get("price") or x.get("lowPrice") or 1e12) or 1e12)
        o = o[0] if o else None
    if isinstance(o, dict) and any(t == "aggregateoffer" for t in _types(o)) and isinstance(o.get("offers"), list) and o["offers"]:
        inner = o["offers"][0] if isinstance(o["offers"][0], dict) else {}
        o = {**o, **inner}
    return o if isinstance(o, dict) else {}


def _ship(o):
    """OfferShippingDetails → (cost text, days text, destination)."""
    sd = o.get("shippingDetails")
    if isinstance(sd, list):
        sd = sd[0] if sd else None
    if not isinstance(sd, dict):
        return "", "", ""
    rate = sd.get("shippingRate") or {}
    cost = ""
    if isinstance(rate, dict):
        v = _num(rate.get("value"))
        cost = "free" if v == 0 else (money(v, rate.get("currency")) if v is not None else "")
    dt = sd.get("deliveryTime") or {}
    days = ""
    if isinstance(dt, dict):
        parts = []
        for k, lab in (("handlingTime", "handling"), ("transitTime", "transit")):
            q = dt.get(k) or {}
            if isinstance(q, dict) and (q.get("minValue") is not None or q.get("maxValue") is not None):
                lo, hi = q.get("minValue"), q.get("maxValue")
                parts.append((f"{int(lo)}–{int(hi)}" if lo is not None and hi is not None and lo != hi else f"{int(hi if hi is not None else lo)}") + f" days {lab}")
        days = ", ".join(parts)
    dest = sd.get("shippingDestination") or {}
    if isinstance(dest, list):
        dest = dest[0] if dest else {}
    dest = _text(dest.get("addressCountry")) if isinstance(dest, dict) else ""
    return cost, days, dest


def _returns(o, p):
    r = o.get("hasMerchantReturnPolicy") or p.get("hasMerchantReturnPolicy") or {}
    if isinstance(r, list):
        r = r[0] if r else {}
    if not isinstance(r, dict):
        return ""
    cat = str(r.get("returnPolicyCategory") or "").lower()
    if "notpermitted" in cat or "nonreturnable" in cat:
        return "no returns"
    days = r.get("merchantReturnDays")
    fees = str(r.get("returnFees") or "").lower()
    bits = []
    if days is not None:
        bits.append(f"{int(_num(days) or 0)} days to return")
    elif "unlimited" in cat:
        bits.append("unlimited return window")
    elif "finite" in cat:
        bits.append("returns accepted")
    if "freereturn" in fees:
        bits.append("free returns")
    elif "returnshippingfees" in fees or "customerresponsibility" in fees:
        bits.append("buyer pays return shipping")
    return ", ".join(bits)


def _desc_facts(desc):
    """Warranty / measurements / designed-in lines that shops put in the description text."""
    f = {}
    d = re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", desc or "")))
    m = re.search(r"\b((?:\d+|one|two|three|four|five|ten|lifetime)[- ](?:year|yr|month|anno|anni|mes[ei])s?\s+(?:limited\s+)?(?:warranty|guarantee|garanzia)|"
                  r"(?:warranty|guarantee|garanzia)\s*(?:di|of|:)?\s*(?:\d+|one|two|three|four|five|ten|lifetime|a vita)\s*(?:year|yr|month|anno|anni|mes[ei])?s?|lifetime warranty|garanzia a vita)\b", d, re.I)
    if m:
        f["Warranty"] = m.group(1)
    m = re.search(r"\b(?:measurements?|dimensions?|size|misure|dimensioni)\s*:?\s*((?:\d+(?:[.,]\d+)?\s?(?:x|×|by)\s?){1,2}\d+(?:[.,]\d+)?\s?(?:cm|mm|in|inch|inches|\"))", d, re.I)
    if m:
        f["Size / measurements"] = m.group(1)
    m = re.search(r"\b(?:designed|made|handmade|crafted|prodotto|fatto|realizzato)\s+(?:in|a)\s+([A-Z][A-Za-z]+(?:,\s*[A-Z][A-Za-z]+)?)\b", d, re.I)
    if m:
        f["Ships from / origin"] = m.group(1)
    return f


def og_tags(page_html):
    """Open Graph / product: meta tags → dict (property → content); the first occurrence wins, attribute order irrelevant."""
    out = {}
    for tag in re.findall(r"<meta\s[^>]*>", page_html or "", re.I):
        pm = re.search(r'(?:property|name)\s*=\s*["\']((?:og|product|twitter):[^"\']+)["\']', tag, re.I)
        cm = re.search(r'content\s*=\s*["\']([^"\']*)["\']', tag, re.I)
        if pm and cm:
            out.setdefault(pm.group(1).lower(), _html.unescape(cm.group(1)))
    return out


def card(page_html, text="", url=""):
    """Facts a product page states about itself (JSON-LD Product first, Open Graph second). {} when there is none."""
    f = {}
    prods = product_nodes(page_html)
    p = prods[0] if prods else {}
    o = _offer_of(p) if p else {}
    price = o.get("price") if o else None
    if price is None and o:
        price = o.get("lowPrice")
    cur = o.get("priceCurrency") if o else None
    if price is None or _num(price) is None:
        og = og_tags(page_html)
        price = og.get("product:price:amount") or og.get("og:price:amount")
        cur = cur or og.get("product:price:currency") or og.get("og:price:currency")
        if price is not None and _num(price) is not None:
            f["Price"] = money(price, cur); f["_price"] = _num(price); f["_source"] = "structured data"
        if og.get("og:availability") or og.get("product:availability"):
            f["Availability"] = AVAIL.get(re.sub(r"[^a-z]", "", (og.get("og:availability") or og.get("product:availability")).lower()), og.get("og:availability") or og.get("product:availability"))
        if og.get("product:brand"):
            f["Brand"] = og["product:brand"][:40]
        if og.get("product:condition"):
            f["Condition (as listed)"] = og["product:condition"][:30]
        if cur and "Price" in f:
            f["Currency"] = str(cur).upper()
        if not p:
            return f
    else:
        f["Price"] = money(price, cur); f["_price"] = _num(price); f["_source"] = "structured data"
        if cur:
            f["Currency"] = str(cur).upper()
    if o:
        av = re.sub(r"[^a-z]", "", str(o.get("availability") or "").lower().split("/")[-1])
        if av:
            f["Availability"] = AVAIL.get(av, av)
        cond = re.sub(r"[^a-z]", "", str(o.get("itemCondition") or p.get("itemCondition") or "").lower().split("/")[-1])
        if cond:
            f["Condition (as listed)"] = COND.get(cond, cond)
        seller = _text(o.get("seller") or o.get("offeredBy"))
        if seller:
            f["Seller"] = seller[:40]
        cost, days, dest = _ship(o)
        if cost:
            f["Shipping"] = cost + (f" to {dest}" if dest else "")
        if days:
            f["Delivery time"] = days
        ret = _returns(o, p)
        if ret:
            f["Returns"] = ret
        if o.get("priceValidUntil"):
            f["Price valid until"] = str(o["priceValidUntil"])[:10]
    brand = _text(p.get("brand") or p.get("manufacturer"))
    if brand:
        f["Brand"] = brand[:40]
    for k in ("sku", "gtin13", "gtin", "gtin12", "mpn"):
        if p.get(k):
            f["SKU"] = f"{k.upper()} {str(p[k])[:30]}" if k != "sku" else str(p[k])[:30]
            break
    agg = p.get("aggregateRating") or {}
    if isinstance(agg, dict):
        rv, best = _num(agg.get("ratingValue")), _num(agg.get("bestRating")) or 5
        if rv is not None:
            f["Rating"] = f"{rv:g}/{best:g}"
        cnt = agg.get("reviewCount") or agg.get("ratingCount")
        if cnt is not None and _num(cnt) is not None:
            f["Reviews"] = f"{int(_num(cnt))} reviews"
    mat = _text(p.get("material"))
    if mat:
        f["Materials"] = mat[:60]
    col = _text(p.get("color"))
    if col:
        f["Colour"] = col[:40]
    size = _text(p.get("size"))
    if size:
        f["Size / measurements"] = size[:40]
    for prop in p.get("additionalProperty") or []:
        if isinstance(prop, dict) and prop.get("name") and prop.get("value") is not None:
            name = str(prop["name"]).strip()
            if re.search(r"warrant|garanz", name, re.I):
                f.setdefault("Warranty", _text(prop["value"])[:40])
            elif re.search(r"material|materiale", name, re.I):
                f.setdefault("Materials", _text(prop["value"])[:60])
    for k, v in _desc_facts(str(p.get("description") or "")).items():
        f.setdefault(k, v)
    if p.get("name") and not f.get("_title"):
        f["_title"] = str(p["name"])[:120]
    return f


def merge(regex_facts, structured):
    """Structured facts win; the regex pass only fills what the shop did not state. The odd 'Price 75' from an image width goes."""
    if not structured:
        return dict(regex_facts or {})
    out = dict(regex_facts or {})
    if "_price" in structured:
        for k in ("Price", "_price", "Currency"):
            out.pop(k, None)
    out.update({k: v for k, v in structured.items() if v not in ("", None)})
    return out


def card_line(facts):
    """One short line for the chat: '€ 46,00 · in stock · brand 15:21 · ships free, 3–5 days · 4.8/5 (120 reviews)'."""
    bits = []
    if facts.get("Price"):
        bits.append(facts["Price"])
    if facts.get("Availability"):
        bits.append(facts["Availability"])
    if facts.get("Brand"):
        bits.append(f"brand {facts['Brand']}")
    ship = " ".join(x for x in (facts.get("Shipping", ""), facts.get("Delivery time", "")) if x)
    if ship:
        bits.append("ships " + ship if not ship.startswith(("free", "€", "$", "£")) else "shipping " + ship)
    if facts.get("Rating"):
        bits.append(facts["Rating"] + (f" ({facts['Reviews']})" if facts.get("Reviews") else ""))
    if facts.get("Returns"):
        bits.append(facts["Returns"])
    return " · ".join(bits)
