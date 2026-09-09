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
    txt = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.S | re.I)
    txt = re.sub(r"<[^>]+>", " ", txt)
    return re.sub(r"\s+", " ", txt).strip()


# ---- Vinted --------------------------------------------------------------------------

def parse_vinted_search(html, limit=12):
    """Catalog page → [{title, price, url}]. JSON blobs first, card markup fallback."""
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


_VINTED_COND = {"new with tags": "new with tags", "new without tags": "new without tags", "very good": "very good",
                "good": "good", "satisfactory": "satisfactory", "nuovo con cartellino": "new with tags",
                "nuovo senza cartellino": "new without tags", "ottime condizioni": "very good", "buone condizioni": "good",
                "usato": "used", "used": "used"}


def parse_vinted_item(html):
    """Item page → facts dict (Price, Condition, Size, Brand, Seller, Feedback, Shipping, Description)."""
    facts = {}
    for blob in _script_blobs(html):
        item = blob.get("item") if isinstance(blob, dict) and isinstance(blob.get("item"), dict) else None
        if item is None:
            item = _walk(blob, ("seller", "size", "brand_title")) if isinstance(blob, (dict, list)) else None
            if not isinstance(item, dict) or "title" not in item:
                continue
        price = _money(item.get("price", {}).get("amount") if isinstance(item.get("price"), dict) else item.get("price"))
        if price:
            facts["Price"] = f"€ {price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            facts["_price"] = price
        for k, label in (("size_title", "Size"), ("size", "Size"), ("brand_title", "Brand"), ("brand", "Brand")):
            if item.get(k) and label not in facts:
                facts[label] = str(item[k])[:60]
        cond = str(item.get("status") or item.get("condition") or "").lower().strip()
        if cond and "Condition (as listed)" not in facts:
            facts["Condition (as listed)"] = _VINTED_COND.get(cond, cond[:40])
        user = item.get("user") or item.get("seller") or {}
        if isinstance(user, dict):
            if user.get("login"):
                facts["Seller"] = str(user["login"])[:40]
            fb = user.get("feedback_count", user.get("feedbacks"))
            rep = user.get("feedback_reputation") or user.get("reputation")
            if fb or rep:
                facts["Feedback"] = f"{fb or '?'} feedback" + (f", {float(rep) * 100:.0f}% positive" if isinstance(rep, (int, float)) else (f", {rep}" if rep else ""))
        desc = str(item.get("description") or "")[:400]
        if desc:
            facts["Description"] = desc
        if facts:
            break
    if not facts:
        txt = _text_of(html)
        from .sellers import price_of
        p = price_of(txt)
        if p:
            facts["Price"] = f"€ {p:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            facts["_price"] = p
        for label, pat in (("Size", r"\b(?:size|taglia|size\s+eu)\s*:?\s*([A-Z0-9/]{1,8})"),
                           ("Brand", r"\b(?:brand|marca)\s*:?\s*([A-Z][A-Za-z0-9 .&'\-]{1,30})")):
            m = re.search(pat, txt, re.I)
            if m:
                facts[label] = m.group(1).strip()
    ship = re.search(r"(vinted (?:go|shipping)[^.\n]{0,50}|spedizione (?:tracciata|standard)[^.\n]{0,50}|shipping:\s*[^.]{2,60})", _text_of(html), re.I)
    if ship and "Shipping" not in facts:
        facts["Shipping"] = ship.group(1).strip()[:80]
    return facts


# ---- subito.it ---------------------------------------------------------------------------

def parse_subito_search(html, limit=12):
    """Search page → [{title, price, url, location}]."""
    out, seen = [], set()
    for blob in _script_blobs(html):
        box = _walk(blob, ("adverts", "ads", "listings", "results"))
        ads = None
        if isinstance(box, dict):
            for k in ("adverts", "ads", "listings", "results"):
                if isinstance(box.get(k), list):
                    ads = box[k]
                    break
        for ad in ads or []:
            if not isinstance(ad, dict):
                continue
            title = str(ad.get("title") or ad.get("subject") or "").strip()
            url = str(ad.get("url") or ad.get("link") or "").strip()
            if url.startswith("/"):
                url = "https://www.subito.it" + url
            if not (title and url) or url in seen or "subito.it" not in url:
                continue
            seen.add(url)
            out.append({"title": title[:120], "price": _money(ad.get("price")), "url": url,
                        "location": str(ad.get("location") or ad.get("city") or "")[:60]})
            if len(out) >= limit:
                return out
    if out:
        return out
    for m in re.finditer(r'<a[^>]+href="((?:https://[\w.]*subito\.it)?/[^"\']*?\.htm[^"\']*)"[^>]*>(.*?)</a>', html, re.S | re.I):
        url = m.group(1) if m.group(1).startswith("http") else "https://www.subito.it" + m.group(1)
        if url in seen:
            continue
        seen.add(url)
        card = _text_of(m.group(2))
        pm = re.search(r"(€\s?[\d.,]+|\d[\d.,]*\s?€|EUR\s?[\d.,]+)", card)
        title = re.sub(r"(€\s?[\d.,]+|\d[\d.,]*\s?€|EUR\s?[\d.,]+)", "", card).strip(" ·-,") or "Subito item"
        out.append({"title": title[:120], "price": _money(pm.group(1)) if pm else None, "url": url, "location": ""})
        if len(out) >= limit:
            break
    return out


def parse_subito_item(html):
    """Item page → facts dict (Price, Location, Seller type, Shipping, Description, Date)."""
    facts = {}
    for blob in _script_blobs(html):
        if isinstance(blob, dict) and blob.get("@type") in ("Product", "Offer", "ClassifiedAd"):
            offers = blob.get("offers") or {}
            price = _money(offers.get("price") if isinstance(offers, dict) else None) or _money(blob.get("price"))
            if price:
                facts["Price"] = f"€ {price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                facts["_price"] = price
            if blob.get("description") and "Description" not in facts:
                facts["Description"] = str(blob["description"])[:400]
        ad = blob.get("advert") or blob.get("ad") if isinstance(blob, dict) else None
        if ad is None:
            ad = _walk(blob, ("seller_type", "ship_enabled", "ad_id")) if isinstance(blob, (dict, list)) else None
        if not isinstance(ad, dict):
            continue
        price = _money(ad.get("price"))
        if price and "Price" not in facts:
            facts["Price"] = f"€ {price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
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
        if facts:
            break
    if "Price" not in facts:
        from .sellers import price_of
        p = price_of(_text_of(html))
        if p:
            facts["Price"] = f"€ {p:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            facts["_price"] = p
    if "Shipping" not in facts:
        ship = re.search(r"(tuttosubito|spedizione (?:disponibile|inclusa|tracciata))", _text_of(html), re.I)
        if ship:
            facts["Shipping"] = ship.group(1).strip()[:80]
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


def search_market(b, site, query, limit=8, throttle=None):
    """Open the marketplace's own search and parse its cards. Returns (cards, note).

    Never raises for site behaviour (walls, empties → ([], note)); BrowserError
    only for transport failures the caller should know about."""
    if site not in SEARCH:
        raise ValueError(f"unknown marketplace: {site}")
    th = throttle or THROTTLE
    url, parse = SEARCH[site][0](query), SEARCH[site][1]
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
