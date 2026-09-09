"""Deep marketplace readers (marathon item 3): Vinted + subito.it, Facebook waters-only.

Two layers:

1. Pure parsers over page HTML (no browser needed, fully tested offline):
   parse_vinted_search / parse_vinted_item / parse_subito_search / parse_subito_item.
   Both sites embed their data as JSON inside <script> blobs (Next.js state,
   JSON-LD); the parsers walk those first and fall back to the visible text,
   so a markup restyle degrades instead of dying.
2. Polite crawling around the Browser: Throttle (per-host gap + exponential
   back-off), search_market / read_item, stealth + proxy helpers (env-gated,
   off unless the owner turns them on).

Facebook is waters-only ON PURPOSE: its marketplace needs a login and this
agent never logs in by itself. facebook_probe reads how deep the water is
(login wall / bot check / public / empty) and the caller stops at the shore
with an honest note. No bypass is attempted, ever.
"""
import json
import os
import random
import re
import time
import urllib.parse

from .browser import BrowserError

# ---- search URLs -----------------------------------------------------------------

def vinted_search_url(query, order="newest_first"):
    return "https://www.vinted.it/catalog?search_text=" + urllib.parse.quote_plus(query) + f"&order={order}"


def subito_search_url(query):
    return "https://www.subito.it/annunci-italia/vendita/usato/?q=" + urllib.parse.quote_plus(query)


# ---- JSON blob plumbing ------------------------------------------------------------

def _script_blobs(html):
    """Yield parsed JSON dicts from <script> blobs (Next.js state, JSON-LD, misc)."""
    for m in re.finditer(r"<script[^>]*>(.*?)</script>", html, re.S | re.I):
        txt = m.group(1).strip()
        if len(txt) < 20 or ("{" not in txt and "[" not in txt):
            continue
        if txt.startswith("{") or txt.startswith("["):
            try:
                yield json.loads(txt)
                continue
            except Exception:
                pass
        i = txt.find("{")
        if i >= 0:
            obj, _ = _balanced(txt, i)
            if obj is not None:
                yield obj


def _balanced(s, i):
    """Parse one JSON object starting at s[i] == '{'. Returns (obj, end) or (None, i)."""
    depth, instr, esc, start = 0, False, False, i
    for j in range(i, min(len(s), i + 500000)):
        c = s[j]
        if instr:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                instr = False
        elif c == '"':
            instr = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(s[start:j + 1]), j + 1
                except Exception:
                    return None, i
    return None, i


def _walk(obj, want, depth=0):
    """First dict under obj (max depth 8) containing any key in `want`. Breadth-ish, cheap."""
    if depth > 8 or isinstance(obj, str):
        return None
    if isinstance(obj, dict):
        if any(k in obj for k in want):
            return obj
        for v in obj.values():
            hit = _walk(v, want, depth + 1)
            if hit is not None:
                return hit
    elif isinstance(obj, list):
        for v in obj[:60]:
            hit = _walk(v, want, depth + 1)
            if hit is not None:
                return hit
    return None


def _money(x):
    """A JSON price (number, {'amount':..}, '€ 24,90') → float or None."""
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, dict):
        for k in ("amount", "value", "price"):
            v = _money(x.get(k))
            if v:
                return v
        return None
    if isinstance(x, str):
        m = re.search(r"(\d{1,4}(?:[.,]\d{3})*(?:[.,]\d{1,2})?)", x)
        if m:
            s = m.group(1)
            s = s.replace(".", "").replace(",", ".") if re.search(r"\d\.\d{3}(\D|$)", s) or (s.count(",") == 1 and s.count(".") == 0) else s.replace(",", "")
            try:
                return float(s)
            except ValueError:
                return None
    return None


def _text_of(html):
    import html as _h
    txt = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.S | re.I)
    txt = re.sub(r"<[^>]+>", " ", txt)
    return re.sub(r"\s+", " ", _h.unescape(txt).replace("\xa0", " ")).strip()


# ---- Vinted --------------------------------------------------------------------------

_CARD_TITLE = re.compile(r'<a[^>]+href="([^"]*/items/\d+[^"]*)"[^>]*\btitle="([^"]+)"', re.I)
_CARD_TITLE2 = re.compile(r'<a[^>]+\btitle="([^"]+)"[^>]*href="([^"]*/items/\d+[^"]*)"', re.I)


def _card_from_label(label):
    """'Zapatillas Nike, Brand: Nike Air, Condizioni: Ottime, Taglia: 42, 21.00 €, 22.75 €' → dict.
    Also the accessibility flavour: 'Nike AF1, brand: Nike, condizioni: Ottime, taglia: 43, €80.00, €84.70 include la Protezione acquisti'."""
    label = _html_unescape(label)
    d = {"title": label.split(",")[0].strip()[:120], "price": None, "total": None, "brand": "", "size": "", "condition": ""}
    m = re.search(r"\b(?:brand|marca)\s*:\s*([^,]+)", label, re.I)
    if m:
        d["brand"] = m.group(1).strip()[:60]
    m = re.search(r"\b(?:condizioni|condition|stato)\s*:\s*([^,]+)", label, re.I)
    if m:
        d["condition"] = vinted_condition(m.group(1).strip())
    m = re.search(r"\b(?:taglia|size)\s*:\s*([^,]+)", label, re.I)
    if m:
        d["size"] = m.group(1).strip()[:20]
    prices = [_money(x) for x in re.findall(r"(?:€\s?\d[\d.,]*|\d[\d.,]*\s?€)", label)]
    prices = [p for p in prices if p]
    if prices:
        d["price"] = prices[0]
        if len(prices) > 1 and prices[1] >= prices[0]:
            d["total"] = prices[1]
    return d


def _html_unescape(s):
    import html as _h
    return _h.unescape(s or "")


def vinted_condition(raw):
    """Vinted's condition words (it/en/fr/es/de) → the English scale the verdicts use."""
    c = (raw or "").strip().lower().rstrip(".")
    return _VINTED_COND.get(c, c[:40])


def parse_vinted_search(html, limit=12):
    """Catalog page → [{title, price, url, total, brand, size, condition}].
    Three layers: embedded JSON (old Next.js pages), the current DOM cards (title attribute carries
    brand / condition / size / price / total), then any bare /items/ link."""
    out, seen = [], set()
    for blob in _script_blobs(html):
        items = blob if isinstance(blob, list) else None
        if items is None:
            box = _walk(blob, ("items",))
            items = box.get("items") if isinstance(box, dict) else None
        if not isinstance(items, list):
            continue
        for it in items:
            if not isinstance(it, dict):
                continue
            title = str(it.get("title") or "").strip()
            url = str(it.get("url") or it.get("path") or "").strip()
            if url.startswith("/"):
                url = "https://www.vinted.it" + url
            price = _money(it.get("price"))
            if title and url and url not in seen:
                seen.add(url)
                out.append({"title": title[:120], "price": price, "url": url})
                if len(out) >= limit:
                    return out
    if out:
        return out
    for m in list(_CARD_TITLE.finditer(html)) + [None]:
        if m is None:
            break
        url, label = m.group(1), m.group(2)
        if not re.search(r"(brand|marca|condizioni|condition|taglia|size)\s*:", label, re.I) and "€" not in label:
            continue
        url = url if url.startswith("http") else "https://www.vinted.it" + url
        url = url.split("?")[0]
        if url in seen:
            continue
        seen.add(url)
        d = _card_from_label(label)
        d["url"] = url
        out.append(d)
        if len(out) >= limit:
            return out
    if out:
        return out
    for m in re.finditer(r'<a[^>]+href="((?:https://[\w.]*vinted\.\w+)?/items/[^"\']+)"[^>]*>(.*?)</a>', html, re.S | re.I):
        url = m.group(1) if m.group(1).startswith("http") else "https://www.vinted.it" + m.group(1)
        if url in seen:
            continue
        seen.add(url)
        card = _text_of(m.group(2))
        pm = re.search(r"(€\s?[\d.,]+|\d[\d.,]*\s?€)", card)
        title = re.sub(r"(€\s?[\d.,]+|\d[\d.,]*\s?€)", "", card).strip(" ·-,") or "Vinted item"
        out.append({"title": title[:120], "price": _money(pm.group(1)) if pm else None, "url": url})
        if len(out) >= limit:
            break
    return out


def parse_vinted_api(data, limit=12):
    """/api/v2/catalog/items JSON (what the catalog page itself loads) → the same card dicts, richer:
    seller login + id, total with buyer protection, brand, size, condition, favourites, views."""
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            return []
    items = (data or {}).get("items") if isinstance(data, dict) else None
    out = []
    for it in items or []:
        if not isinstance(it, dict) or not it.get("url"):
            continue
        u = it.get("user") or {}
        out.append({"title": str(it.get("title") or "")[:120], "price": _money(it.get("price")), "total": _money(it.get("total_item_price")),
                    "url": str(it["url"]).split("?")[0], "id": it.get("id"), "brand": str(it.get("brand_title") or "")[:60], "size": str(it.get("size_title") or "")[:20],
                    "condition": vinted_condition(it.get("status")), "seller": str(u.get("login") or "")[:40], "seller_id": u.get("id"),
                    "favourites": it.get("favourite_count"), "views": it.get("view_count")})
        if len(out) >= limit:
            break
    return out


_VINTED_COND = {"new with tags": "new with tags", "new without tags": "new without tags", "very good": "very good",
                "good": "good", "satisfactory": "satisfactory", "nuovo con cartellino": "new with tags",
                "nuovo senza cartellino": "new without tags", "ottime condizioni": "very good", "buone condizioni": "good",
                "ottime": "very good", "buone": "good", "discrete": "satisfactory", "nuovo": "new",
                "neuf avec étiquette": "new with tags", "neuf sans étiquette": "new without tags", "très bon état": "very good", "bon état": "good", "satisfaisant": "satisfactory",
                "nuevo con etiquetas": "new with tags", "nuevo sin etiquetas": "new without tags", "muy bueno": "very good", "bueno": "good", "aceptable": "satisfactory",
                "neu mit etikett": "new with tags", "neu ohne etikett": "new without tags", "sehr gut": "very good", "gut": "good", "zufriedenstellend": "satisfactory",
                "usato": "used", "used": "used"}


def _fmt_eur(p):
    return f"€ {p:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _rsc_stream(html):
    """Next.js app-router pages ship their data as JS string literals in self.__next_f.push([1,"…"]).
    Join the chunks back into one text (only the ones that can hold item data — the rest is markup)."""
    parts = []
    for m in re.finditer(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', html, re.S):
        raw = m.group(1)
        if "plugins" not in raw and "feedback_reputation" not in raw and "item_id" not in raw:
            continue
        try:
            parts.append(json.loads('"' + raw + '"'))
        except Exception:
            try:
                parts.append(raw.encode("utf-8", "replace").decode("unicode_escape", "replace"))
            except Exception:
                pass
    return "".join(parts)


def _plugins(html):
    """The item page's plugin list (summary, attributes, description, user_info_header, …) or []."""
    s = _rsc_stream(html)
    i = s.find('{"plugins":[')
    if i < 0:
        return []
    obj, _ = _balanced(s, i)
    pl = (obj or {}).get("plugins") if isinstance(obj, dict) else None
    return [p for p in pl or [] if isinstance(p, dict) and isinstance(p.get("data"), dict)]


_RELATIVE_AGE = re.compile(r"^(?:caricato|uploaded|ajouté|subido|hochgeladen)\s+", re.I)


def parse_vinted_item(html):
    """Item page → facts dict (Price, Total with buyer protection, Condition, Size, Brand, Colour, Seller,
    Feedback, Listed, Shipping, Description, Availability).

    Layers, in order: the current app-router page (plugins in the RSC stream + JSON-LD), the old
    __NEXT_DATA__ item blob, then the visible text. Every value is a quote from the page."""
    facts = {}
    plugins = _plugins(html)
    by_name = {}
    for p in plugins:
        by_name.setdefault(p.get("name"), p["data"])
    if plugins:
        d = by_name.get("attributes") or {}
        for a in d.get("attributes") or []:
            code, dat = a.get("code"), a.get("data") or {}
            val = str(dat.get("value") or "").strip()
            if not val:
                continue
            if code == "brand":
                facts["Brand"] = val[:60]
            elif code == "size":
                facts["Size"] = val[:20]
            elif code == "status":
                facts["Condition (as listed)"] = vinted_condition(val)
            elif code == "color":
                facts["Colour"] = val[:60]
            elif code == "upload_date":
                facts["Listed"] = val[:40]
            elif code in ("material",):
                facts["Materials"] = val[:60]
        d = by_name.get("description") or {}
        if d.get("description"):
            facts["Description"] = str(d["description"])[:400]
        d = by_name.get("user_info_header") or {}
        if d.get("name"):
            facts["Seller"] = str(d["name"])[:40]
            fb, rep = d.get("feedback_count"), d.get("feedback_reputation")
            if isinstance(fb, (int, float)):
                facts["Feedback"] = (f"{int(fb)} feedback" + (f", {float(rep) * 100:.0f}% positive" if isinstance(rep, (int, float)) and fb else "")) if fb else "no feedback yet"
                if fb and isinstance(rep, (int, float)):
                    facts["Rating"] = f"{float(rep) * 100:.0f}% positive"
                facts["Reviews"] = f"{int(fb)} feedback"
            if d.get("business"):
                facts["Seller type"] = "business"
        for p in plugins:                                                  # price sits in the make_offer / buy plugin data
            pd = p["data"]
            pr = _money(pd.get("price")) if isinstance(pd.get("price"), dict) else None
            if pr and "Price" not in facts:
                facts["Price"] = _fmt_eur(pr)
                facts["_price"] = pr
            if pd.get("seller_id") and "_seller_id" not in facts:
                facts["_seller_id"] = str(pd["seller_id"])
            if pd.get("item_id") and "_item_id" not in facts:
                facts["_item_id"] = str(pd["item_id"])
            if p.get("name") == "ask_seller":
                if pd.get("is_reserved"):
                    facts["Availability"] = "reserved"
                elif pd.get("is_hidden"):
                    facts["Availability"] = "hidden / sold"
                elif pd.get("can_buy") is True:
                    facts["Availability"] = "available"
        d = by_name.get("summary") or {}
        for line in d.get("lines") or []:
            for el in line.get("elements") or []:
                v = str(el.get("value") or "")
                if _RELATIVE_AGE.match(v) and "Listed" not in facts:
                    facts["Listed"] = _RELATIVE_AGE.sub("", v)[:40]
    for blob in _script_blobs(html):                                       # JSON-LD Product (price, brand, description, condition)
        if isinstance(blob, dict) and blob.get("@type") == "Product":
            offers = blob.get("offers") or {}
            pr = _money(offers.get("price")) if isinstance(offers, dict) else None
            if pr and "Price" not in facts:
                facts["Price"] = _fmt_eur(pr)
                facts["_price"] = pr
            if blob.get("description") and "Description" not in facts:
                facts["Description"] = str(blob["description"])[:400]
            br = blob.get("brand")
            br = br.get("name") if isinstance(br, dict) else br
            if br and "Brand" not in facts:
                facts["Brand"] = str(br)[:60]
            if isinstance(offers, dict) and offers.get("availability") and "Availability" not in facts:
                facts["Availability"] = "available" if "InStock" in str(offers["availability"]) else "not available"
            break
    if not facts.get("_price") or "Seller" not in facts:                   # old Next.js pages: one item blob
        for blob in _script_blobs(html):
            item = blob.get("item") if isinstance(blob, dict) and isinstance(blob.get("item"), dict) else None
            if item is None:
                item = _walk(blob, ("seller", "size", "brand_title")) if isinstance(blob, (dict, list)) else None
                if not isinstance(item, dict) or "title" not in item:
                    continue
            price = _money(item.get("price", {}).get("amount") if isinstance(item.get("price"), dict) else item.get("price"))
            if price and "Price" not in facts:
                facts["Price"] = _fmt_eur(price)
                facts["_price"] = price
            for k, label in (("size_title", "Size"), ("size", "Size"), ("brand_title", "Brand"), ("brand", "Brand")):
                if item.get(k) and label not in facts:
                    facts[label] = str(item[k])[:60]
            cond = str(item.get("status") or item.get("condition") or "").lower().strip()
            if cond and "Condition (as listed)" not in facts:
                facts["Condition (as listed)"] = vinted_condition(cond)
            user = item.get("user") or item.get("seller") or {}
            if isinstance(user, dict):
                if user.get("login") and "Seller" not in facts:
                    facts["Seller"] = str(user["login"])[:40]
                fb = user.get("feedback_count", user.get("feedbacks"))
                rep = user.get("feedback_reputation") or user.get("reputation")
                if (fb or rep) and "Feedback" not in facts:
                    facts["Feedback"] = f"{fb or '?'} feedback" + (f", {float(rep) * 100:.0f}% positive" if isinstance(rep, (int, float)) else (f", {rep}" if rep else ""))
            desc = str(item.get("description") or "")[:400]
            if desc and "Description" not in facts:
                facts["Description"] = desc
            if facts:
                break
    txt = _text_of(html)
    if not facts.get("_price"):
        from .sellers import price_of
        p = price_of(txt)
        if p:
            facts["Price"] = _fmt_eur(p)
            facts["_price"] = p
    if "Size" not in facts or "Brand" not in facts:
        for label, pat in (("Size", r"\b(?:size|taglia|size\s+eu)\s*:?\s*([A-Z0-9/]{1,8})\b"),
                           ("Brand", r"\b(?:brand|marca)\s*:?\s*([A-Z][A-Za-z0-9 .&'\-]{1,30}?)(?=\s+(?:Menu|Taglia|Size|Condizioni|Condition)\b|[.,·]|$)")):
            m = re.search(pat, txt, re.I)
            if m and label not in facts:
                facts[label] = m.group(1).strip()
    if facts.get("_price"):
        m = re.search(r"(\d[\d.,]*)\s?€\s*(?:include la protezione acquisti|includes? buyer protection|incl\.)", txt, re.I)
        tot = _money(m.group(1)) if m else None
        if tot and tot >= facts["_price"]:
            facts["Total with buyer protection"] = _fmt_eur(tot)
    ship = re.search(r"(vinted (?:go|shipping)[^.\n]{0,50}|spedizione (?:tracciata|standard)[^.\n]{0,50}|shipping:\s*[^.]{2,60}|spedizione da\s*\d[\d.,]*\s?€|shipping from\s*€?\s?\d[\d.,]*\s?€?)", txt, re.I)
    if ship and "Shipping" not in facts:
        facts["Shipping"] = ship.group(1).strip()[:80]
    return facts


# ---- subito.it ---------------------------------------------------------------------------

def _subito_feature(ad, key):
    f = (ad.get("features") or {}).get(key) or {}
    vals = f.get("values") or []
    return str(vals[0].get("value") or "") if vals and isinstance(vals[0], dict) else ""


def _subito_ad_card(ad):
    """One AdItem from the 2026 __NEXT_DATA__ list → card dict (title, price, url, location, condition, size, brand, shipping, listed, seller)."""
    title = str(ad.get("subject") or ad.get("title") or "").strip()
    urls = ad.get("urls") or {}
    url = str(urls.get("default") or ad.get("url") or ad.get("link") or "").strip()
    if not (title and url):
        return None
    geo = ad.get("geo") or {}
    town = (geo.get("town") or {}).get("value") if isinstance(geo.get("town"), dict) else ""
    city = (geo.get("city") or {}).get("shortName") if isinstance(geo.get("city"), dict) else ""
    region = (geo.get("region") or {}).get("value") if isinstance(geo.get("region"), dict) else ""
    loc = (f"{town} ({city})" if town and city and town != city else town or city or region or "")
    adv = ad.get("advertiser") or {}
    card = {"title": title[:120], "price": _money(_subito_feature(ad, "/price")), "url": url, "location": str(loc)[:60],
            "condition": subito_condition(_subito_feature(ad, "/item_condition")), "size": _subito_feature(ad, "/fashion/size")[:20], "brand": _subito_feature(ad, "/fashion/brand")[:40] or _subito_feature(ad, "/brand")[:40],
            "shipping": "TuttoSubito" if _subito_feature(ad, "/item_shippable") in ("Sì", "1", "true") else "", "listed": str(ad.get("date") or "")[:10],
            "seller": str(adv.get("name") or "")[:40], "seller_type": "company" if adv.get("company") else "private"}
    cost = _subito_feature(ad, "/item_shipping_cost_tuttosubito")
    if cost and card["shipping"]:
        card["shipping"] = f"TuttoSubito from {cost}"
    return card


def parse_subito_search(html, limit=12):
    """Search page → [{title, price, url, location, …}]. 2026 __NEXT_DATA__ (initialState.items.originalList) first,
    older embedded lists next, then listing links from the DOM (only real ad pages: /<category>/<slug>-<id>.htm)."""
    out, seen = [], set()
    for blob in _script_blobs(html):
        lst = _walk(blob, ("originalList",))
        ads = lst.get("originalList") if isinstance(lst, dict) else None
        if not isinstance(ads, list):
            box = _walk(blob, ("adverts", "ads", "listings", "results"))
            if isinstance(box, dict):
                for k in ("adverts", "ads", "listings", "results"):
                    if isinstance(box.get(k), list):
                        ads = box[k]
                        break
        for ad in ads or []:
            if not isinstance(ad, dict):
                continue
            if ad.get("kind") and ad.get("kind") != "AdItem":
                continue
            if ad.get("kind") == "AdItem" or "features" in ad:
                card = _subito_ad_card(ad)
            else:
                title = str(ad.get("title") or ad.get("subject") or "").strip()
                url = str(ad.get("url") or ad.get("link") or "").strip()
                if url.startswith("/"):
                    url = "https://www.subito.it" + url
                card = {"title": title[:120], "price": _money(ad.get("price")), "url": url,
                        "location": str(ad.get("location") or ad.get("city") or "")[:60]} if title and url else None
            if not card or card["url"] in seen or "subito.it" not in card["url"]:
                continue
            seen.add(card["url"])
            out.append(card)
            if len(out) >= limit:
                return out
    if out:
        return out
    for m in re.finditer(r'<a[^>]+href="((?:https://www\.subito\.it)?/[a-z0-9-]+/[a-z0-9-]+-\d{3,}\.htm[^"\']*)"[^>]*>(.*?)</a>', html, re.S | re.I):
        url = m.group(1) if m.group(1).startswith("http") else "https://www.subito.it" + m.group(1)
        if url in seen:
            continue
        seen.add(url)
        card = _text_of(m.group(2))
        lab = re.search(r'aria-label="([^"]+)"', m.group(0))
        pm = re.search(r"(€\s?[\d.,]+|\d[\d.,]*\s?€|EUR\s?[\d.,]+)", card)
        title = re.sub(r"(€\s?[\d.,]+|\d[\d.,]*\s?€|EUR\s?[\d.,]+)", "", card).strip(" ·-,") or (_html_unescape(lab.group(1)) if lab else "") or "Subito item"
        out.append({"title": title[:120], "price": _money(pm.group(1)) if pm else None, "url": url, "location": ""})
        if len(out) >= limit:
            break
    return out


_SUBITO_COND = {"nuovo - mai usato in confezione originale": "new with tags", "nuovo - mai usato": "new", "ottimo - come nuovo": "very good", "ottimo": "very good",
                "come nuovo - perfetto o ricondizionato": "like new", "come nuovo": "like new",
                "buono - lievi segni di usura": "good", "buono": "good", "discreto - segni di usura evidenti": "satisfactory", "discreto": "satisfactory",
                "da riparare - non funzionante": "for parts", "ricondizionato": "refurbished"}


def subito_condition(raw):
    c = (raw or "").strip().lower()
    return _SUBITO_COND.get(c, c[:40])


def parse_subito_item(html):
    """Item page → facts dict (Price, Location, Seller, Seller type, Rating, Shipping, Delivery time, Condition, Size, Brand, Listed, Description).
    Layers: JSON-LD Product + old __NEXT_DATA__ advert blob, then the labelled text of the 2026 page ('Dati Principali', 'Modalità di consegna')."""
    facts = {}
    for blob in _script_blobs(html):
        if isinstance(blob, dict) and blob.get("@type") in ("Product", "Offer", "ClassifiedAd"):
            offers = blob.get("offers") or {}
            price = _money(offers.get("price") if isinstance(offers, dict) else None) or _money(blob.get("price"))
            if price:
                facts["Price"] = _fmt_eur(price)
                facts["_price"] = price
            if blob.get("description") and "Description" not in facts:
                facts["Description"] = _html_unescape(str(blob["description"]))[:400]
            if isinstance(offers, dict) and offers.get("availability") and "Availability" not in facts:
                facts["Availability"] = "available" if "InStock" in str(offers["availability"]) else "not available"
        ad = blob.get("advert") or blob.get("ad") if isinstance(blob, dict) else None
        if ad is None:
            ad = _walk(blob, ("seller_type", "ship_enabled", "ad_id")) if isinstance(blob, (dict, list)) else None
        if not isinstance(ad, dict):
            continue
        price = _money(ad.get("price"))
        if price and "Price" not in facts:
            facts["Price"] = _fmt_eur(price)
            facts["_price"] = price
        loc = ad.get("location") or ad.get("city") or ((ad.get("geo") or {}) if isinstance(ad.get("geo"), dict) else {})
        loc = loc.get("city") if isinstance(loc, dict) else loc
        if loc:
            facts["Location"] = str(loc)[:60]
        st = str(ad.get("seller_type") or ad.get("account_type") or "").lower()
        if st:
            facts["Seller type"] = "company" if any(w in st for w in ("compan", "business", "azienda", "pro")) else ("private" if any(w in st for w in ("privat", "particular")) else st[:30])
        if ad.get("ship_enabled") or ad.get("shippable"):
            facts["Shipping"] = "ships (TuttoSubito)"[:80]
        if ad.get("description") and "Description" not in facts:
            facts["Description"] = str(ad["description"])[:400]
        if ad.get("date") or ad.get("published"):
            facts["Listed"] = str(ad.get("date") or ad.get("published"))[:30]
        if facts.get("_price"):
            break
    txt = _text_of(html)
    if "Price" not in facts:                                            # "… Gavardo (BS) 4 € Spedizione …" — the price sits right after the town; never a random € from the ads around
        m = re.search(r"\([A-Z]{2}\)\s+(\d[\d.,]*)\s?€", txt)
        p = _money(m.group(1)) if m else None
        if p is None and not re.search(r"\([A-Z]{2}\)\s+(?:Contatta|Spedizione)", txt) and not any(isinstance(b_, dict) and b_.get("@type") == "Product" for b_ in _script_blobs(html)):
            from .sellers import price_of
            p = price_of(txt)
        if p:
            facts["Price"] = _fmt_eur(p)
            facts["_price"] = p
    # 2026 page: the visible labels are stable ('Dati Principali', 'Modalità di consegna', 'Valutazione: 4,5 su 5', 'Pubblica da …')
    if "Location" not in facts:                                        # "… Gavardo (BS) 4 € Spedizione …": the town right before the price
        m = re.search(r"([A-ZÀ-Ü][\w'À-ÿ]+(?:\s(?:[A-ZÀ-Ü][\w'À-ÿ]+|di|del|della|sul|in|al|a))*)\s\(([A-Z]{2})\)\s+(?:\d[\d.,]*\s?€|Contatta|Spedizione)", txt)
        if m:
            facts["Location"] = f"{m.group(1)} ({m.group(2)})"[:60]
    m = re.search(r"\b(?:Condizione|Condizioni)\s+(Nuovo - mai usato in confezione originale|Nuovo - mai usato|Come nuovo - perfetto o ricondizionato|Ottimo - come nuovo|Buono - lievi segni di usura|Discreto - segni di usura evidenti|Da riparare - non funzionante|Ricondizionato|Come nuovo|Nuovo|Ottimo|Buono|Discreto|Usato)\b", txt)
    if m and "Condition (as listed)" not in facts:
        facts["Condition (as listed)"] = _SUBITO_COND.get(m.group(1).lower(), m.group(1).lower())
    m = re.search(r"\bTaglia\s+([A-Z0-9/.,]{1,8})\b", txt)
    if m and "Size" not in facts:
        facts["Size"] = m.group(1)
    m = re.search(r"\bMarca\s+([A-ZÀ-Üa-z0-9][\w'À-ÿ&.-]{1,30}(?:\s[A-Z][\w'À-ÿ&.-]{1,20})?)(?=\s+(?:Modalità|Materiale|Colore|Genere|Tipologia|Descrizione|$))", txt)
    if m and "Brand" not in facts:
        facts["Brand"] = m.group(1).strip()[:40]
    m = re.search(r"\bValutazione:\s*(\d(?:[.,]\d)?)\s*su\s*5", txt)
    if m:
        facts["Rating"] = m.group(1).replace(",", ".") + "/5"
        pre = txt[max(0, m.start() - 80):m.start()]
        n = re.search(r"([A-ZÀ-Ü][\w'À-ÿ.-]{1,30}(?:\s[A-ZÀ-Ü][\w'À-ÿ.-]{1,30})?)\s+\d(?:[.,]\d)?\s*$", pre)
        if n and "Seller" not in facts:
            facts["Seller"] = n.group(1).strip()[:40]
    m = re.search(r"\bPubblica da\s+([a-zà-ù]+\s+\d{4})", txt)
    if m:
        facts["Seller since"] = m.group(1)
    if re.search(r"\bScrive molte recensioni\b", txt):
        facts["Seller note"] = "writes many reviews"
    if "Seller type" not in facts:
        facts["Seller type"] = "company" if re.search(r"\b(Azienda|Negozio|Partita IVA|Rivenditore)\b", txt[:20000]) and not re.search(r"\bPrivato\b", txt[:20000]) else "private"
    m = re.search(r"\bSpedizione da\s*(\d[\d.,]*)\s?€", txt)
    if m:
        facts["Shipping"] = f"TuttoSubito from {_fmt_eur(_money(m.group(1)))}"
    elif re.search(r"\bSpedizione disponibile\b|\bTuttoSubito\b", txt) and "Shipping" not in facts:
        facts["Shipping"] = "ships (TuttoSubito)"
    elif re.search(r"\bSolo ritiro a mano\b|\bRitiro a mano\b", txt) and "Shipping" not in facts:
        facts["Shipping"] = "pickup only"
    m = re.search(r"\bConsegna prevista entro\s+(\d{1,2}\s*-\s*\d{1,2}\s+giorni lavorativi)", txt)
    if m and "Delivery time" not in facts:
        facts["Delivery time"] = m.group(1)
    m = re.search(r"\b(\d{1,2}\s+(?:gen|feb|mar|apr|mag|giu|lug|ago|set|ott|nov|dic)\w*)\s+alle\s+\d{1,2}:\d{2}\b", txt)
    if m and "Listed" not in facts:
        facts["Listed"] = m.group(1)
    if "Location" in facts:
        facts.setdefault("Ships from / origin", "Italy")
    if re.search(r"Il venditore dichiara che il bene .{0,40} è originale", txt):
        facts["Seller declares"] = "genuine article"
    facts["_marketplace"] = "subito"
    return facts


# ---- Facebook: waters-only -----------------------------------------------------------------

FB_LOGIN = re.compile(r"log in to continue|create an account to|you must log in|accedi per continuare|iscriviti per continuare", re.I)
FB_BLOCK = re.compile(r"this content (isn't available|is unavailable)|contenuto non (disponibile|trovato)|temporarily blocked|bloccato temporaneamente", re.I)


def facebook_probe(html, status="ok"):
    """How deep is the water? → (verdict, note). Never attempts a login or a bypass.

    verdicts: 'login' (stopped at the shore — needs the owner's own login),
    'captcha' (bot check — back off), 'empty' (nothing readable), 'ok' (a rare
    public page — may be quoted with its URL)."""
    if status == "captcha":
        return "captcha", "Facebook shows a bot check — backing off, nothing attempted."
    if status == "login" or FB_LOGIN.search(html or ""):
        return "login", "Facebook wants a login first — I stopped at the shore (waters-only). Send me the listing text or log in on my live screen and I'll read it with you."
    txt = _text_of(html or "")
    if FB_BLOCK.search(txt):
        return "empty", "That Facebook page isn't available (removed or private)."
    if len(txt) < 200:
        return "empty", "Facebook gave me an almost-empty page — nothing I can honestly quote."
    return "ok", "public page"


# ---- politeness: throttle --------------------------------------------------------------------

class Throttle:
    """Per-host politeness: a gap between hits, exponential back-off after walls.

    wait(url) sleeps what is needed, then records the hit. punish(host) starts /
    lengthens a ban after a 429/captcha/empty; returns False when the host has
    failed too often and should be left alone. sleep/clock injectable for tests.
    """

    def __init__(self, gap=4.0, backoff_base=30.0, backoff_max=600.0, max_punish=3,
                 sleep=None, clock=None, jitter=None):
        self.gap = gap
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max
        self.max_punish = max_punish
        self._sleep = sleep or time.sleep
        self._clock = clock or time.time
        self._jitter = jitter or (lambda: random.uniform(0, 5))
        self.hits = {}
        self.bans = {}
        self._n = {}

    @staticmethod
    def host_of(url):
        try:
            return (urllib.parse.urlparse(url).hostname or "").lower()
        except Exception:
            return ""

    def wait(self, url):
        host = self.host_of(url)
        now = self._clock()
        due = max(self.hits.get(host, 0) + self.gap, self.bans.get(host, 0))
        if due > now:
            self._sleep(due - now)
            now = self._clock()
        self.hits[host] = now

    def punish(self, host):
        host = self.host_of(host) if "://" in host else host.lower()
        n = self._n.get(host, 0) + 1
        self._n[host] = n
        wait = min(self.backoff_base * 2 ** (n - 1) + self._jitter(), self.backoff_max)
        self.bans[host] = self._clock() + wait
        return n <= self.max_punish

    def failures(self, host):
        return self._n.get(self.host_of(host) if "://" in host else host.lower(), 0)


# ---- stealth + proxy (env-gated; off unless the owner opts in) ---------------------------------

UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36 Edg/126.0",
]

STEALTH_ARGS = ["--disable-blink-features=AutomationControlled"]

STEALTH_INIT = """() => {
  try { Object.defineProperty(navigator, 'webdriver', {get: () => undefined}); } catch (e) {}
  try { Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]}); } catch (e) {}
  try { window.chrome = window.chrome || {runtime: {}}; } catch (e) {}
}"""


def stealth_enabled():
    return os.environ.get("BAI_STEALTH", "").lower() in ("1", "true", "yes")


def pick_ua(i=None):
    """Rotated user agent: pick_ua() random, pick_ua(i) deterministic round-robin (for tests)."""
    if i is not None:
        return UAS[i % len(UAS)]
    return random.choice(UAS)


def proxy_config():
    """BAI_PROXY=http://[user:pass@]host:port → playwright proxy dict, or None when unset/invalid."""
    raw = (os.environ.get("BAI_PROXY", "") or "").strip()
    if not raw:
        return None
    if "://" not in raw:
        raw = "http://" + raw
    try:
        u = urllib.parse.urlparse(raw)
        if not u.hostname or not u.port:
            return None
        d = {"server": f"{u.scheme or 'http'}://{u.hostname}:{u.port}"}
        if u.username:
            d["username"] = urllib.parse.unquote(u.username)
        if u.password:
            d["password"] = urllib.parse.unquote(u.password)
        return d
    except Exception:
        return None


# ---- polite marketplace crawling (runs on the hands thread) --------------------------------------

THROTTLE = Throttle()

SEARCH = {"vinted": (vinted_search_url, parse_vinted_search), "subito": (subito_search_url, parse_subito_search)}
ITEM = {"vinted": parse_vinted_item, "subito": parse_subito_item}


def search_market(b, site, query, limit=8, throttle=None, price_to=None):
    """Open the marketplace's own search and parse its cards. Returns (cards, note).

    Never raises for site behaviour (walls, empties → ([], note)); BrowserError
    only for transport failures the caller should know about."""
    if site not in SEARCH:
        raise ValueError(f"unknown marketplace: {site}")
    th = throttle or THROTTLE
    url, parse = SEARCH[site][0](query), SEARCH[site][1]
    if price_to and site == "vinted":
        url += f"&price_to={float(price_to):g}&currency=EUR"
    th.wait(url)
    try:
        b.open(url)
    except BrowserError:
        raise
    try:
        b.dismiss_banner()
    except Exception:
        pass
    st = b.status()
    if st != "ok":
        host = Throttle.host_of(url)
        keep_going = th.punish(host)
        return [], f"{site}: {st} wall — backed off" + ("" if keep_going else "; leaving it alone for now")
    if site == "vinted":                                              # the page's own JSON is richer (seller, total, condition)
        cards = vinted_search_api(b, query, limit, price_to=price_to, throttle=th)
        if cards:
            return cards, ""
    try:
        html = b.page.content()
    except Exception:
        return [], f"{site}: could not read the results page"
    cards = parse(html, limit)
    if not cards:
        th.punish(Throttle.host_of(url))
        return [], f"{site}: no cards parsed (layout changed or empty results)"
    return cards, ""


def read_item(b, site, url, throttle=None):
    """Open one listing and pull its deep facts. Returns (facts, note); {} + note on walls."""
    if site not in ITEM:
        raise ValueError(f"unknown marketplace: {site}")
    th = throttle or THROTTLE
    th.wait(url)
    try:
        b.open(url)
    except BrowserError:
        raise
    st = b.status()
    if st != "ok":
        keep_going = th.punish(Throttle.host_of(url))
        return {}, f"{st} wall — backed off" + ("" if keep_going else "; leaving it alone for now")
    try:
        b.dismiss_banner()
    except Exception:
        pass
    try:
        return ITEM[site](b.page.content()), ""
    except Exception as e:
        return {}, f"parse failed: {str(e)[:80]}"


# ---- Vinted's own JSON (what the page loads for itself; same cookies, same politeness) --------------

VINTED_API = "https://www.vinted.it/api/v2"


def vinted_api(b, path, params=None, throttle=None):
    """GET one Vinted API path through the browser context (it holds the anonymous access cookie the
    catalog page set). Read-only, throttled like a page hit. Returns parsed JSON or None — never raises.
    401/403/429 count as a wall (back-off), so a cranky site is left alone quickly."""
    th = throttle or THROTTLE
    url = VINTED_API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    th.wait(url)
    try:
        req = getattr(getattr(b, "page", None), "request", None) or getattr(getattr(b, "_ctx", None), "request", None)
        if req is None:
            return None
        r = req.get(url, headers={"Accept": "application/json"}, timeout=20000)
        if r.status != 200:
            if r.status in (401, 403, 429):
                th.punish(Throttle.host_of(url))
            return None
        return r.json()
    except Exception:
        return None


def vinted_search_api(b, query, limit=8, price_to=None, order="relevance", throttle=None):
    """Catalog search via the page's own JSON: richer cards (seller, total, condition, size). [] when unavailable."""
    params = {"search_text": query, "order": order, "per_page": min(max(limit, 1), 40), "page": 1, "currency": "EUR"}
    if price_to:
        params["price_to"] = f"{float(price_to):g}"
    data = vinted_api(b, "/catalog/items", params, throttle)
    return parse_vinted_api(data, limit) if data else []


def vinted_user_facts(user):
    """/users/{id} JSON → facts the verdict can quote (location, feedback split, activity, verification)."""
    u = (user or {}).get("user") if isinstance(user, dict) and "user" in user else user
    if not isinstance(u, dict):
        return {}
    f = {}
    city, country = str(u.get("city") or "").strip(), str(u.get("country_title") or "").strip()
    if city or country:
        f["Seller location"] = ", ".join(x for x in (city, country) if x)[:60]
    if country:
        f["Ships from / origin"] = country[:40]
    fb = u.get("feedback_count")
    if isinstance(fb, (int, float)):
        fb = int(fb)
        rep = u.get("feedback_reputation")
        pos, neg = u.get("positive_feedback_count"), u.get("negative_feedback_count")
        if fb:
            f["Feedback"] = f"{fb} feedback" + (f", {float(rep) * 100:.0f}% positive" if isinstance(rep, (int, float)) else "") + (f" ({pos} 👍 / {neg} 👎)" if isinstance(pos, int) and isinstance(neg, int) else "")
            if isinstance(rep, (int, float)):
                f["Rating"] = f"{float(rep) * 100:.0f}% positive"
        else:
            f["Feedback"] = "no feedback yet"
        f["Reviews"] = f"{fb} feedback"
    if isinstance(u.get("item_count"), int):
        f["Items for sale"] = str(u["item_count"])
    if u.get("last_loged_on_ts"):
        f["Last active"] = str(u["last_loged_on_ts"])[:10]
    if u.get("business"):
        f["Seller type"] = "business (Vinted Pro)"
    ver = u.get("verification") or {}
    if isinstance(ver, dict):
        ok = [k for k, v in ver.items() if isinstance(v, dict) and v.get("valid")]
        if ok:
            f["Verified"] = ", ".join(sorted(ok))[:60]
    if u.get("is_on_holiday"):
        f["Availability note"] = "seller on holiday"
    return f


def vinted_feedback_text(data, limit=12):
    """/user_feedbacks JSON → what buyers wrote, one line each ('5/5: fast, as described'); system lines skipped."""
    rows = (data or {}).get("user_feedbacks") if isinstance(data, dict) else None
    out = []
    for r in rows or []:
        if not isinstance(r, dict) or r.get("system_feedback") or r.get("is_system_comment"):
            continue
        txt = str(r.get("feedback") or "").strip()
        rating = r.get("rating")
        if txt or rating:
            out.append((f"{rating}/5: " if rating else "") + txt[:200])
        if len(out) >= limit:
            break
    return "\n".join(out)


def vinted_shipping_facts(data):
    d = (data or {}).get("shipping_details") if isinstance(data, dict) else None
    if not isinstance(d, dict):
        return {}
    if d.get("pickup_only"):
        return {"Shipping": "pickup only"}
    if d.get("free_shipping"):
        return {"Shipping": "free"}
    p = _money(d.get("price"))
    return {"Shipping": f"from {_fmt_eur(p)}"} if p else {}


def vinted_seller(b, seller_id, throttle=None):
    """The seller behind a listing, from Vinted's own data: (facts, feedback text). Both empty when the API is shy."""
    if not seller_id:
        return {}, ""
    facts = vinted_user_facts(vinted_api(b, f"/users/{seller_id}", throttle=throttle))
    text = vinted_feedback_text(vinted_api(b, "/user_feedbacks", {"user_id": seller_id, "per_page": 12, "page": 1}, throttle)) if facts else ""
    return facts, text


def vinted_enrich(b, facts, throttle=None):
    """After parse_vinted_item: add seller + shipping facts from the API, return the buyers' words for the verdict."""
    extra, text = vinted_seller(b, facts.get("_seller_id"), throttle)
    for k, v in extra.items():
        if k in ("Feedback", "Rating", "Reviews") or k not in facts:
            facts[k] = v
    if facts.get("_item_id") and ("Shipping" not in facts or re.search(r"\b0[.,]00\b", facts["Shipping"])):   # "da 0,00 €" is the logged-out placeholder
        facts.update(vinted_shipping_facts(vinted_api(b, f"/items/{facts['_item_id']}/shipping_details", throttle=throttle)))
    facts["_marketplace"] = "vinted"
    return text
