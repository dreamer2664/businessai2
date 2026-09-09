"""Seller / listing research (milestone 14): "find me good cheap X" → a document with pictures, links and a verdict per option.

For each candidate listing the agent reads the page itself (price, condition, shipping, origin, materials, seller name,
rating/review counts), grabs the main picture, reads what buyers wrote (review pages, complaints), looks for the seller's
social page and judges reliability with explicit reasons. It is read-only: no logins, no purchases.

Everything is grounded in page text; the thinking model only turns extracted facts into a short verdict. When the model
is missing, verdicts are rule-based (still explicit about why).
"""
import os
import re
import time
import urllib.parse

from .browser import BrowserError
from . import library
from . import markets

MARKETPLACES = re.compile(r"amazon\.|ebay\.|etsy\.|vinted\.|aliexpress\.|temu\.|wish\.|subito\.it|zalando\.|asos\.|shein\.|alibaba\.|dhgate\.|walmart\.|bol\.com|cdiscount\.|manomano\.|leroymerlin\.|ikea\.", re.I)
FORUM = re.compile(r"reddit\.com|quora\.com|youtube\.com|tiktok\.com|instagram\.com|pinterest\.|x\.com|twitter\.com|facebook\.com|linkedin\.com|wikipedia\.org|wikihow", re.I)
SOCIAL = re.compile(r"https?://(?:www\.)?(instagram\.com|facebook\.com|tiktok\.com|x\.com|twitter\.com|youtube\.com|pinterest\.[a-z.]+|linkedin\.com|trustpilot\.com)/([^/?#\s\"']+)", re.I)
REVIEW_SITES = ["trustpilot.com", "reviews.io", "sitejabber.com", "feefo.com", "google.com/maps"]

PRICE = re.compile(r"(?:€|EUR|\$|USD|£|GBP)\s?(\d{1,4}(?:[.,]\d{3})*(?:[.,]\d{1,2})?)|(\d{1,4}(?:[.,]\d{1,2})?)\s?(?:€|EUR)", re.I)
SHIP_TIME = re.compile(r"\b(\d{1,2}\s?(?:-|–|to|a)\s?\d{1,2}|\d{1,2})\s?(?:business |working |lavorativi )?(?:days?|giorni|gg)\b", re.I)
SHIP_COST = re.compile(r"(?:shipping|delivery|spedizione|consegna)[^.\n€$£]{0,40}?(free|gratis|gratuita|(?:€|\$|£)\s?\d+(?:[.,]\d+)?|\d+(?:[.,]\d+)?\s?€)", re.I)
ORIGIN = re.compile(r"(?:ships? from|shipped from|dispatched from|spedito da|spedisce da|sold by|location|made in|prodotto in|country of origin|from)\s*:?\s*([A-Z][A-Za-z .'-]{2,40}?)(?:[.,\n)]|$)", re.M)
MATERIAL = re.compile(r"(?:material[s]?|materiale|composition|composizione|made (?:of|from)|fabric|upper|sole|outer)\s*:?\s*([A-Za-z0-9 ,%/-]{3,60}?)(?:[.\n;]|$)", re.I)
CONDITION = re.compile(r"\b(new with tags|new without tags|brand new|new|like new|very good|good|satisfactory|fair|used|pre-owned|nuovo con cartellino|nuovo|ottime condizioni|buone condizioni|usato)\b", re.I)
RATING = re.compile(r"(\d(?:[.,]\d)?)\s*(?:/\s*5|out of 5|su 5|stars?|stelle)|(\d{2,3})\s?%\s?(?:positive|positivi|positive feedback)", re.I)
REVIEW_COUNT = re.compile(r"(\d{1,3}(?:[.,]\d{3})*|\d+)\s?(?:reviews?|ratings?|recensioni|valutazioni|feedback)", re.I)
COMPLAINT = re.compile(r"\b(scam|fake|counterfeit|never (?:arrived|received)|not as described|refund(?:ed)? never|no refund|broke|broken|damaged|poor quality|cheap quality|smell|rip-?off|avoid|worst|terrible|awful|truffa|mai arrivato|non conforme|rotto|pessim[oa])\b", re.I)
PRAISE = re.compile(r"\b(fast (?:shipping|delivery)|arrived quickly|as described|great quality|good quality|recommend|excellent|perfect|love it|well packed|ottimo|consigliato|perfetto|veloce)\b", re.I)

_JS_MAIN_IMAGE = r"""
async () => {
  await new Promise(r => setTimeout(r, 300));
  const area = (i) => { const r = i.getBoundingClientRect(); return Math.max(r.width * r.height, (i.naturalWidth || 0) * (i.naturalHeight || 0) / 4, (i.width || 0) * (i.height || 0)); };
  const bad = /logo|icon|sprite|badge|flag|avatar|banner|pixel|tracking|spacer/i;
  const imgs = Array.from(document.images).filter(i => (i.currentSrc || i.src) && !bad.test(i.src + ' ' + (i.alt || '') + ' ' + (i.className || '')) && area(i) >= 200 * 200 * 0.5);
  imgs.sort((a, b) => area(b) - area(a));
  const og = document.querySelector('meta[property="og:image"], meta[name="og:image"], meta[name="twitter:image"]');
  const abs = (u) => { try { return new URL(u, document.baseURI).href; } catch (e) { return u; } };
  return {big: imgs.length ? abs(imgs[0].currentSrc || imgs[0].src) : null, og: og ? abs(og.content) : null};
}
"""


def _num(s):
    s = s.replace(".", "").replace(",", ".") if re.search(r"\d\.\d{3}(?:\D|$)", s) or (s.count(",") == 1 and s.count(".") == 0) else s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def price_of(text):
    """Most plausible listing price: the most frequent price in the top of the page, else the first."""
    vals = []
    for m in PRICE.finditer(text[:6000]):
        v = _num(m.group(1) or m.group(2) or "")
        if v and 0.5 <= v <= 20000:
            vals.append(v)
    if not vals:
        return None
    return sorted(vals, key=lambda v: (-vals.count(v), vals.index(v)))[0]


def extract_facts(text, url):
    """Grounded facts from a listing page (every value is a quote from the page)."""
    f = {}
    p = price_of(text)
    if p is not None:
        f["Price"] = f"€ {p:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if "€" in text or "EUR" in text else f"{p:g}"
        f["_price"] = p
    m = SHIP_COST.search(text)
    if m:
        f["Shipping"] = m.group(1).strip()
    m = SHIP_TIME.search(text)
    if m:
        f["Delivery time"] = m.group(0).strip()
    m = ORIGIN.search(text)
    if m and len(m.group(1).split()) <= 4:
        f["Ships from / origin"] = m.group(1).strip()
    m = MATERIAL.search(text)
    if m:
        f["Materials"] = m.group(1).strip()
    m = re.search(r"\bcondition\s*[:\-–]?\s*(new with tags|new without tags|brand new|like new|very good|good|satisfactory|fair|used|pre-owned|new|nuovo con cartellino|nuovo|ottime condizioni|buone condizioni|usato)\b", text[:6000], re.I)
    second_hand = re.search(r"vinted|ebay|subito|depop|wallapop|leboncoin|kleinanzeigen", url + " " + text[:300], re.I)
    if m:                                                    # an explicit "Condition: …" line is trustworthy anywhere
        f["Condition (as listed)"] = m.group(1)
    elif second_hand:
        m = CONDITION.search(text[:4000])
        if m:
            f["Condition (as listed)"] = m.group(1)
    m = RATING.search(text)
    if m:
        f["Rating"] = (m.group(1) + "/5") if m.group(1) else (m.group(2) + "% positive")
    m = REVIEW_COUNT.search(text)
    if m:
        f["Reviews"] = m.group(0).strip()
    return f


def seller_name(text, url, title):
    m = re.search(r"(?:sold by|seller|venditore|venduto da|shop|negozio|by)\s*:?\s*([A-Za-z][\w .&'-]{2,40}?)(?:\s{2,}|\n|\s·|[.,(]|$)", text[:5000])
    if m and not re.match(r"(the|a|an|our|your|il|la|le|i)\b", m.group(1), re.I):
        return m.group(1).strip()
    host = urllib.parse.urlparse(url).netloc.replace("www.", "")
    if host and not MARKETPLACES.search(host):
        return host.split(".")[0].capitalize()
    t = re.split(r" [-–|•] ", title or "")
    name = (t[-1] if len(t) > 1 and MARKETPLACES.search(host or "") else t[0]).strip()
    return (name or host or "unknown seller")[:40]


_MONTHS = {m: i + 1 for i, m in enumerate(["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"])}
_MONTHS.update({m: i + 1 for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"])})


def _months_since(text, now=None):
    """'febbraio 2018' / 'march 2026' → months elapsed, or None."""
    m = re.match(r"\s*([a-zà-ù]+)\s+(\d{4})\s*$", (text or "").lower())
    if not m or m.group(1) not in _MONTHS:
        return None
    now = now or time.localtime()
    return (now.tm_year - int(m.group(2))) * 12 + (now.tm_mon - _MONTHS[m.group(1)])


def reliability(facts, reviews_text, social_hits, age_hint=""):
    """(grade, verdict, pros, cons) from what was read. good | ok | bad, with reasons the owner can check."""
    pros, cons = [], []
    txt = reviews_text or ""
    n_bad = len(COMPLAINT.findall(txt))
    n_good = len(PRAISE.findall(txt))
    r = facts.get("Rating", "")
    rv = re.match(r"(\d(?:[.,]\d)?)/5", r)
    pct = re.match(r"(\d{2,3})%", r)
    if rv and float(rv.group(1).replace(",", ".")) >= 4.3:
        pros.append(f"rating {r}")
    elif rv and float(rv.group(1).replace(",", ".")) < 3.8:
        cons.append(f"low rating {r}")
    if pct and int(pct.group(1)) >= 97:
        pros.append(f"{r} feedback")
    elif pct and int(pct.group(1)) < 93:
        cons.append(f"only {r} feedback")
    rc = facts.get("Reviews", "")
    mrc = re.match(r"(\d[\d.,]*)", rc)
    if mrc:
        n = int(re.sub(r"\D", "", mrc.group(1)) or 0)
        enough = 20 if facts.get("_marketplace") else 50               # a private second-hand seller with 20+ feedbacks is seasoned
        (pros if n >= enough else cons).append(f"{n} reviews" if n >= enough else f"few reviews ({n})")
    if n_bad >= 3 and n_bad > n_good:
        cons.append(f"{n_bad} complaint words in what buyers wrote (quality, delivery, refunds)")
    elif n_good >= 3:
        pros.append(f"buyers mention: {', '.join(dict.fromkeys(m.lower() for m in PRAISE.findall(txt)[:3]))}")
    marketplace = bool(facts.get("_marketplace"))
    if social_hits:
        pros.append("has a public social page: " + ", ".join(sorted({h['platform'] for h in social_hits})))
    elif not marketplace:                                              # a private Vinted seller has no shop Instagram — not a mark against them
        cons.append("no social media page found")
    if "Ships from / origin" not in facts:
        cons.append("shipping origin not stated")
    if "Materials" not in facts and not marketplace:
        cons.append("materials not stated")
    if marketplace:
        if facts.get("Feedback") == "no feedback yet":
            cons.append("brand-new seller, no feedback yet")
        since = _months_since(facts.get("Seller since", ""))
        if since is not None and since < 6:
            cons.append(f"new on the site (since {facts['Seller since']})")
        elif since is not None and since >= 24:
            pros.append(f"on the site since {facts['Seller since']}")
        if facts.get("Price") == "not stated":
            cons.append("price not stated in the listing")
        if "Verified" in facts and len(facts["Verified"].split(",")) >= 2:
            pros.append(f"verified via {facts['Verified']}")
        if facts.get("Availability") in ("reserved", "hidden / sold"):
            cons.append(f"listing is {facts['Availability']}")
    if facts.get("Shipping", "").lower() in ("free", "gratis", "gratuita"):
        pros.append("free shipping")
    if age_hint:
        pros.append(age_hint)
    score = len(pros) - len(cons) - (2 if n_bad >= 3 and n_bad > n_good else 0)
    grade = "good" if score >= 2 else "bad" if score <= -2 else "ok"
    verdict = {"good": "Looks reliable — I'd shortlist it.", "ok": "Usable, but check the points below before buying or listing.",
               "bad": "I would not trust this one."}[grade]
    return grade, verdict, pros[:4], cons[:4]


EYES_QUESTION = "In one sentence, what signs of use or damage (if any) does the item in this photo show? If it looks brand new, say so."
_NEWISH = re.compile(r"\b(new|never worn|like new|unused|mint|sealed|brand new|nuovo|mai (?:indossat|usat)\w*|neu|neuf)\b", re.I)
_WEAR = re.compile(r"\b(worn|wear|scuff\w*|scratch\w*|stain\w*|dirt\w*|holes?|torn|fray\w*|dents?|crack\w*|damage\w*|broken|peel\w*|faded|ripped|used)\b", re.I)
_STRONG = re.compile(r"\b(holes?|torn|broken|crack\w*|ripped|damaged|missing)\b", re.I)
_CLEAN = re.compile(r"\b(brand new|no (?:visible |obvious |apparent )?(?:signs?|defects?|damage|wear)|unused|pristine|new and unused|looks new|appears? (?:to be )?new)\b", re.I)


def photo_is_graphic(data, flat_share=0.7):
    """True for flat graphics (placeholders, icons, logos): the 8 most common colours cover most of the image, or it is tiny.
    Measured: drawn placeholders 0.77–0.93, a product shot on white 0.41, real photos ~0.1."""
    try:
        from PIL import Image
        import io
        im = Image.open(io.BytesIO(data)).convert("RGB")
        if im.width < 80 or im.height < 80:
            return True
        im.thumbnail((160, 160))
        cols = sorted(im.quantize(256).getcolors(), reverse=True)
        return sum(c for c, _ in cols[:8]) / float(im.width * im.height) >= flat_share
    except Exception:
        return False


def photo_verdict(answer, condition=""):
    """Turn the eyes' one-sentence description into a flag ('👁 …') or '' — flag wear on items listed as new, and real damage on anything."""
    a = (answer or "").strip().split("\n")[0].strip()
    if not a:
        return ""
    strong = bool(_STRONG.search(a))
    clean = bool(_CLEAN.search(a)) and not strong
    worn = bool(_WEAR.search(a)) and not clean
    if not worn:
        return ""
    if strong or (condition and _NEWISH.search(condition)) or (not condition and re.search(r"\bworn\b|signs of (?:use|wear)", a, re.I) and _STRONG.search(a)):
        return "👁 " + a[:220]
    return ""


class SellerCheck:
    def __init__(self, tasks, planner=None, log=None, viewer=None, pace=None, eyes=None):
        self.T = tasks
        self.planner = planner
        self.log = log or (lambda kind, **f: None)
        self.viewer = viewer
        self.pace = pace
        self.eyes = eyes
        self.live_change = ""            # the owner's mid-job words ("only sellers that ship from italy") — read before judging
        self.throttle = markets.Throttle()   # one polite pace for every marketplace (item 3)

    # ---- steps ---------------------------------------------------------------------
    def _step(self, i, note=""):
        if self.viewer:
            self.viewer.plan_step(i, note)

    def candidates(self, b, product, n=5, extra_queries=(), sites=(), price_to=None):
        """Search results that look like listings/shops (not articles/forums).
        sites (from the brief: the owner named them) are searched directly first, politely."""
        queries = [f"{product} buy", f"{product} price shipping", *extra_queries]
        if re.search(r"\b(used|second ?hand|usato|vinted)\b", product, re.I):
            queries.insert(0, f"{product} vinted OR ebay OR subito")
        seen, out = set(), []
        for s in sites or ():
            if s in ("vinted", "subito") and len(out) < n:
                q = re.sub(r"\s+(on|su)\s+(vinted|subito(?:\.it)?|ebay(?:\.it)?|amazon(?:\.it)?|etsy|wallapop|depop|aliexpress|temu|facebook marketplace|zalando|kleinanzeigen|leboncoin)(\s*(,|and|e|or|o)\s*(vinted|subito(?:\.it)?|ebay(?:\.it)?|amazon(?:\.it)?|etsy|wallapop|depop|aliexpress|temu|facebook marketplace|zalando|kleinanzeigen|leboncoin))*\b", " ", product).strip()
                try:
                    cards, note = markets.search_market(b, s, q or product, n - len(out), self.throttle, price_to=price_to)
                except BrowserError as e:
                    self.log("market_search_failed", site=s, error=str(e)[:80])
                    continue
                if note:
                    self.log("market_search_note", site=s, note=note[:100])
                for c in cards:
                    if c["url"] not in seen:
                        seen.add(c["url"])
                        out.append({"url": c["url"], "title": c["title"]})
            elif s not in ("vinted", "subito"):
                self.log("market_skipped", site=s, reason="waters-only" if "facebook" in s else "no deep reader yet")
        for q in queries:
            if len(out) >= n:
                break
            try:
                results = b.search_results(q, 12)
            except BrowserError as e:
                self.log("search_failed", query=q, error=str(e)[:80])
                continue
            for r in results:
                u = r["url"]
                host = urllib.parse.urlparse(u).netloc.replace("www.", "")
                hosts_taken = {urllib.parse.urlparse(x["url"]).netloc.replace("www.", "") for x in out}
                one_per_host = bool(host) and not MARKETPLACES.search(host)          # a shop = one listing; a marketplace holds many sellers
                if u in seen or FORUM.search(u) or (one_per_host and host in hosts_taken):
                    continue
                if re.search(r"/(blog|news|article|guide|how-to|wiki|forum|category/blog)/", u, re.I) or re.search(r"\b(best|top \d+|review of|vs\.?)\b", r["title"], re.I) and not MARKETPLACES.search(u):
                    continue
                if re.search(r"trustpilot|reviews\.io|sitejabber|feefo|yelp\.|/reviews?\b|recensioni", u, re.I) or re.search(r"\b(reviews?|recensioni|opinioni)\b", r["title"], re.I):
                    continue                                           # review pages are read later, per seller — not listings
                seen.add(u)
                out.append(r)
                if len(out) >= n:
                    break
        return out[:n]

    def read_listing(self, b, url):
        """Open a listing and pull grounded facts + the main picture (+ what the eyes see, if available)."""
        b.open(url)
        st = b.status()
        if st == "captcha" and hasattr(self.T, "pass_wall") and self.T.pass_wall(b, url):
            st = b.status()
        if st != "ok":
            return {"url": url, "wall": st}
        try:
            b.dismiss_banner()
        except Exception:
            pass
        text = b.extract_text()
        title = (b.page.title() or "")[:120]
        facts = extract_facts(text, url)
        host = urllib.parse.urlparse(url).netloc.lower()
        if "facebook.com" in host:                                    # waters-only: probe, never wade in
            verdict, note = markets.facebook_probe(b.page.content(), st)
            if verdict != "ok":
                return {"url": url, "wall": "login" if verdict == "login" else verdict, "note": note}
        elif "vinted." in host or "subito.it" in host:                # the marketplace reader is authoritative; the regex pass only fills gaps
            try:
                deep = (markets.parse_vinted_item if "vinted." in host else markets.parse_subito_item)(b.page.content())
                for k in ("Price", "_price", "Materials", "Rating", "Reviews", "Shipping", "Seller", "Condition (as listed)", "Ships from / origin"):
                    facts.pop(k, None)                                  # a marketplace page is full of other ads and menus — the generic guess is noise here
                facts.update(deep)
                if "_price" not in facts:
                    facts["Price"] = "not stated"
                if "vinted." in host:
                    buyers = markets.vinted_enrich(b, facts, self.throttle)
                    if buyers:
                        facts["_buyers"] = buyers
                facts.setdefault("_marketplace", "vinted" if "vinted." in host else "subito")
            except Exception as e:
                self.log("deep_facts_failed", error=str(e)[:80])
        img = None
        try:
            d = b.page.evaluate(_JS_MAIN_IMAGE) or {}
            src = d.get("og") if (d.get("og") and not d.get("big")) else (d.get("big") or d.get("og"))
            if src:
                img = self._fetch_image(b, src)
        except Exception as e:
            self.log("image_failed", error=str(e)[:80])
        socials = [] if facts.get("_marketplace") else [{"platform": m.group(1).split(".")[0].lower(), "url": m.group(0)} for m in SOCIAL.finditer(b.page.content()[:400000])]   # a marketplace's footer icons are not the seller's
        socials = [s for s in socials if not re.search(r"/(sharer|share|intent|dialog|plugins|widgets|embed)", s["url"], re.I)]
        seen = set()
        socials = [s for s in socials if not (s["platform"] in seen or seen.add(s["platform"]))][:4]
        return {"url": url, "title": title, "text": text[:12000], "facts": facts, "image": img, "seller": facts.get("Seller") or seller_name(text, url, title), "socials": socials}

    def _fetch_image(self, b, src, max_bytes=250000):
        """Download the picture through the browser (same cookies), shrink it to ≤ 480 px JPEG when Pillow is around."""
        data = None
        try:
            if src.startswith("file://"):
                with open(urllib.parse.unquote(src[7:]), "rb") as f:
                    data = f.read()
            else:
                r = b.page.request.get(src, timeout=15000)
                data = r.body()
        except Exception:
            try:                                                        # fallback: let the page itself fetch it (same origin, blobs, lazy CDNs)
                b64 = b.page.evaluate("""async (u) => { const r = await fetch(u); const bl = await r.blob();
                    return await new Promise(res => { const fr = new FileReader(); fr.onload = () => res(fr.result.split(',')[1]); fr.readAsDataURL(bl); }); }""", src)
                import base64
                data = base64.b64decode(b64) if b64 else None
            except Exception:
                return None
        if not data or len(data) < 2000:
            return None
        try:
            from PIL import Image
            import io
            im = Image.open(io.BytesIO(data)).convert("RGB")
            im.thumbnail((480, 480))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=80, optimize=True)
            return buf.getvalue()
        except Exception:
            return data if len(data) <= max_bytes else None

    def read_reviews(self, b, listing, product):
        """What buyers say: review pages on the same site if reachable, else a search for '<seller> reviews'. Returns text."""
        seller = listing.get("seller", "")
        chunks = []
        txt = listing.get("text", "")
        i = re.search(r"(customer reviews|recensioni|reviews \(|ratings and reviews|feedback|\breviews\b)", txt, re.I)
        if i:
            chunks.append(txt[i.start():i.start() + 3000])
        if seller and len(seller) > 2:
            try:
                res = b.search_results(f'"{seller}" reviews OR recensioni OR complaints', 8)
            except BrowserError:
                res = []
            for r in res[:3]:
                if FORUM.search(r["url"]) and "reddit" not in r["url"]:
                    continue
                if r["url"] == listing["url"] or not re.search(r"review|recension|trustpilot|complaint|reclam|opinion|feedback|reddit", (r["title"] + " " + r["url"]), re.I):
                    continue                                           # a review page, not another listing
                try:
                    b.open(r["url"])
                    if b.status() != "ok":
                        continue
                    t = b.extract_text()
                    key = re.sub(r"\b(lda|ltd|srl|gmbh|inc|llc|sas|bv|shop|store)\b\.?", "", seller, flags=re.I).strip()
                    j = re.search(re.escape(key.split()[0]), t, re.I) if key else None
                    if not j:
                        continue                                           # the page is about someone else — never attribute it to this seller
                    chunks.append(t[max(0, j.start() - 500):j.start() + 2500])
                    listing.setdefault("review_sources", []).append(r["url"])
                except BrowserError:
                    continue
        return "\n".join(chunks)[:6000]

    def read_social(self, b, listing):
        """Open the seller's social page (public view only) and read followers / recent comments, no login."""
        for s in listing.get("socials", [])[:2]:
            try:
                b.open(s["url"])
                if b.status() != "ok":
                    s["note"] = f"{s['platform']}: page behind a {b.status()} wall (could not read it)"
                    continue
                t = b.extract_text()[:3000]
                m = re.search(r"([\d.,]+\s?[KkMm]?)\s?(followers|follower|seguaci|abonnés|subscribers|likes)", t, re.I)
                bad = len(COMPLAINT.findall(t))
                s["note"] = f"{s['platform']}: " + (f"{m.group(1)} {m.group(2)}" if m else "public page found") + (f", {bad} complaint words in visible comments" if bad else "")
                s["followers"] = m.group(0) if m else ""
            except BrowserError:
                s["note"] = f"{s['platform']}: could not open"
        return listing.get("socials", [])

    def look(self, b, listing, product):
        """Eyes on the listing picture: does the photo contradict the text (damage, wear on a 'new' item)? '' when no eyes / nothing wrong.
        Lessons from testing with real photos: never ask the small vision model yes/no (it answers 'no damage' to everything);
        ask it to describe signs of use and judge the words here. Flat graphics (placeholders, icons) make it hallucinate → skipped."""
        if not self.eyes or not listing.get("image"):
            return ""
        try:
            if photo_is_graphic(listing["image"]):
                return ""
            import tempfile, os
            fd, path = tempfile.mkstemp(suffix=".jpg")
            os.write(fd, listing["image"]); os.close(fd)
            try:
                ans = self.eyes.look(path, EYES_QUESTION, max_tokens=70)
            finally:
                os.unlink(path)
            cond = listing["facts"].get("Condition (as listed)", "")
            return photo_verdict(ans, cond)
        except Exception as e:
            self.log("look_failed", error=str(e)[:80])
            return ""

    def verdict_text(self, product, listing, grade, verdict, pros, cons):
        """One or two plain sentences; the model may rephrase but only from the facts given."""
        if not (self.planner and self.planner.installed()):
            return verdict
        try:
            facts = "; ".join(f"{k}: {v}" for k, v in listing["facts"].items() if not k.startswith("_"))
            out = self.planner.chat("You write one honest sentence (max 30 words) judging an online seller for a shop owner. Use only the facts given; no new claims.",
                                    f"Product: {product}\nSeller: {listing.get('seller')}\nFacts: {facts}\nGood signs: {', '.join(pros) or 'none'}\nBad signs: {', '.join(cons) or 'none'}\nGrade: {grade}\nSentence:",
                                    max_tokens=60, timeout=90)
            out = out.strip().split("\n")[0].strip(' "')
            if 15 < len(out) < 240 and not re.search(r"\b(I will|I'll|as an ai)\b", out, re.I):
                return out
        except Exception as e:
            self.log("verdict_model_error", error=str(e)[:80])
        return verdict

    # ---- the whole job -----------------------------------------------------------------
    COUNTRY_WORDS = {"italy": ("ital",), "italia": ("ital",), "europe": ("ital", "german", "france", "franc", "spain", "spagn", "portug", "netherl", "olanda", "belg", "austria", "poland", "polon", "eu ", "europe"),
                     "europa": ("ital", "german", "france", "spain", "portug", "europe"), "eu": ("ital", "german", "france", "spain", "portug", "netherl", "europe", "eu "),
                     "germany": ("german", "deutsch"), "spain": ("spain", "spagn", "españ"), "france": ("france", "franc"), "uk": ("uk", "united kingdom", "britain", "england"), "usa": ("usa", "united states", "u.s."), "china": ("china", "cina", "cn")}

    def parse_constraints(self, product):
        """'cork sandals (max € 30; only italian sellers; ships from italy)' → (clean product, {"max": 30.0, "from": "italy", "words": [...]})."""
        c = {"max": None, "from": None, "words": []}
        m = re.search(r"\s*\(([^()]*)\)\s*$", product)
        if not m:
            return product, c
        for part in re.split(r"\s*;\s*", m.group(1)):
            low = part.lower().strip()
            mm = re.match(r"max\s*€?\s*(\d+(?:[.,]\d+)?)", low)
            if mm:
                c["max"] = float(mm.group(1).replace(",", "."))
                continue
            mm = re.match(r"(?:ships from|ship from|shipping from|from|only|solo)\s+([a-z]+)", low)
            adj = {"italian": "italy", "italiani": "italy", "italiano": "italy", "german": "germany", "tedeschi": "germany", "spanish": "spain", "french": "france", "european": "europe", "europei": "europe",
                   "chinese": "china", "cinesi": "china", "british": "uk", "american": "usa", "italia": "italy", "europa": "europe"}
            if mm and (mm.group(1) in self.COUNTRY_WORDS or mm.group(1) in adj):
                c["from"] = adj.get(mm.group(1), mm.group(1))
                continue
            if low and not re.match(r"\d+ options?|no social media check", low):
                c["words"].append(part.strip())
        return product[:m.start()].strip(), c

    @staticmethod
    def live_change_to_condition(text):
        """Owner's mid-job sentence → the '(…; …)' condition syntax the planner uses."""
        low = text.lower()
        parts = []
        m = re.search(r"\b(?:max|under|below|less than|no more than|massimo|sotto|entro)\s*(?:€|eur)?\s*(\d+(?:[.,]\d+)?)", low)
        if m:
            parts.append(f"max € {m.group(1)}")
        m = re.search(r"\b(?:from|in|da|ship(?:ping|s)? from|based in)\s+(italy|italia|europe|europa|eu|germany|spain|france|uk|usa|china)\b", low)
        if m:
            parts.append(f"ships from {m.group(1)}")
        m = re.search(r"\b(?:only|solo)\s+(italian|german|spanish|french|european|chinese|british|american|italiani|europei|cinesi)\b", low)
        if m:
            parts.append(f"only {m.group(1)}")
        if not parts:
            parts.append(text.strip())
        return "; ".join(parts)

    def apply_constraints(self, L, c):
        """Owner's conditions become part of the verdict: over budget or from the wrong place → 'bad' with the reason."""
        cons = []
        p = L["facts"].get("_price")
        if c.get("max") and p and p > c["max"]:
            cons.append(f"over your € {c['max']:g} limit ({L['facts'].get('Price')})")
        if c.get("from"):
            origin = (L["facts"].get("Ships from / origin") or "").lower()
            words = self.COUNTRY_WORDS.get(c["from"], (c["from"],))
            if origin and not any(w in origin for w in words):
                cons.append(f"ships from {L['facts'].get('Ships from / origin')}, you wanted {c['from']}")
            elif not origin:
                cons.append(f"origin not stated — you wanted {c['from']}")
        return cons

    def run(self, product, n=4, want_doc=True, counterfeit_note="", sites=()):
        """Returns (document path, summary text, options list). Runs on the hands thread (caller uses T.on_hands)."""
        t0 = time.time()
        options = []
        product, constraints = self.parse_constraints(product)
        with self.T._session() as b:
            n_eff = max(2, n - 1) if (self.pace and self.pace.hurry()) else n
            urls = re.findall(r"(?:https?|file)://[^\s<>\"']+", product)
            if urls:                                                          # "is this shop legit? <link>" → that page IS the candidate
                self._step(0, f"opening the link you gave me")
                cands = [{"url": u.rstrip(".,;)"), "title": urllib.parse.urlparse(u).netloc.replace("www.", "")} for u in urls[:n_eff]]
                product = re.sub(r"(?:https?|file)://\S+", "", product)
                product = re.sub(r"\b(is|are|this|that|the|a|an|seller|shop|store|site|website|listing|ok|okay|legit|safe|good|fine|trustworthy|reliable|serious|real|check|if|can you|could you|please|\?)\b", " ", product, flags=re.I)
                product = re.sub(r"\s{2,}", " ", product).strip(" ,.?!-—")
                if len(product) < 3:
                    host = cands[0]["title"] or ""
                    product = host if (host and not host.startswith(("127.", "localhost")) and "." in host) else (os.path.basename(urllib.parse.urlparse(cands[0]["url"]).path).rsplit(".", 1)[0] or "the shop you sent")
            else:
                self._step(0, f"searching for {product}")
                cands = self.candidates(b, product, n_eff, sites=sites, price_to=constraints.get("max"))
            if not cands:
                return None, f"I couldn't find listings for {product} (search engines walled or nothing matched).", []
            for i, c in enumerate(cands):
                if self.pace and self.pace.should_stop() and options:
                    self.log("seller_check_stopped", read=len(options))
                    break
                self._step(1, f"reading listing {i + 1}/{len(cands)}: {c['title'][:50]}")
                self.log("seller_check", name=c["title"][:60])
                try:
                    L = self.read_listing(b, c["url"])
                except BrowserError as e:
                    self.log("listing_failed", url=c["url"], error=str(e)[:80])
                    continue
                if L.get("wall"):
                    L.update(title=c["title"], facts={}, seller=urllib.parse.urlparse(c["url"]).netloc, socials=[], text="",
                             note=L.get("note") or f"page behind a {L['wall']} wall — could not read it")
                    options.append(L)
                    continue
                if L["facts"].get("_buyers"):                              # marketplace feedback already read from the site's own data
                    self._step(2, f"reading {L['seller']}'s feedback")
                    L["reviews"] = L["facts"]["_buyers"]
                    L.setdefault("review_sources", []).append("Vinted feedback on the seller's profile")
                elif L["facts"].get("_marketplace"):                        # a private seller's first name is not searchable — never pin strangers' reviews on them
                    L["reviews"] = ""
                elif not (self.pace and self.pace.hurry()):
                    self._step(2, f"reading what buyers say about {L['seller']}")
                    L["reviews"] = self.read_reviews(b, L, product)
                    if L.get("socials"):
                        self._step(2, f"looking at {L['seller']}'s social page")
                        self.read_social(b, L)
                else:
                    L["reviews"] = L["text"]
                L["eyes"] = self.look(b, L, product)
                options.append(L)
                if self.pace:
                    r = self.pace.tick()
                    if r:
                        self.T.notify(r)
        self.T._release_page()
        self._step(3, "judging reliability")
        if self.live_change:                                             # what the owner said while I was reading → same rules as a planned condition
            _, late = self.parse_constraints(f"x ({self.live_change_to_condition(self.live_change)})")
            for k in ("max", "from"):
                constraints[k] = late[k] or constraints.get(k)
            constraints["words"] = constraints.get("words", []) + late["words"]
            self.live_change = ""
        for L in options:
            if L.get("note"):
                L.update(grade="bad", verdict=L["note"], pros=[], cons=["could not be read"])
                continue
            grade, verdict, pros, cons = reliability(L["facts"], L.get("reviews", ""), [s for s in L.get("socials", []) if s.get("note") and "could not" not in s["note"]])
            if L.get("eyes"):
                cons.insert(0, "the photo contradicts the listing: " + L["eyes"][2:])
                grade = "bad" if grade != "good" else "ok"
            owner_cons = self.apply_constraints(L, constraints)
            if owner_cons:                                                 # the owner's conditions outrank my own reading
                cons = owner_cons + cons
                grade = "bad" if any("over your" in x or "you wanted" in x and "not stated" not in x for x in owner_cons) else ("ok" if grade == "good" else grade)
                verdict = owner_cons[0][0].upper() + owner_cons[0][1:] + ". " + verdict
            L.update(grade=grade, verdict=self.verdict_text(product, L, grade, verdict, pros, cons), pros=pros, cons=cons)
        order = {"good": 0, "ok": 1, "bad": 2}
        options.sort(key=lambda L: (order[L["grade"]], L["facts"].get("_price", 1e9)))
        # ---- document -----------------------------------------------------------------
        self._step(4, "writing the document")
        cond = "; ".join(([f"max € {constraints['max']:g}"] if constraints.get("max") else []) + ([f"from {constraints['from']}"] if constraints.get("from") else []) + constraints.get("words", []))
        doc = library.Doc(f"{product} — seller check", f"{len(options)} options researched · read-only, nothing bought or contacted" + (f" · your conditions: {cond}" if cond else ""), kind="seller_check")
        best = [L for L in options if L["grade"] == "good"] or [L for L in options if L["grade"] == "ok"]
        if urls and len(options) == 1:                                   # one link from the owner → a verdict on that shop, not a ranking
            L = options[0]
            word = {"good": "looks trustworthy", "ok": "is so-so", "bad": "I would NOT buy from"}[L["grade"]]
            summary = (f"I checked the shop you sent ({product}): {L['seller']} {word} — {L['verdict']} "
                       f"Price {L['facts'].get('Price', 'n/a')}, shipping {L['facts'].get('Shipping', 'n/a')}, from {L['facts'].get('Ships from / origin', 'n/a')}. " + (counterfeit_note or ""))
        else:
            summary = ((f"I looked at the {len(options)} listing(s) you sent ({product}). " if urls else f"I looked at {len(options)} listings for {product}. ") +
                       (f"Best bet: {best[0]['seller']} ({best[0]['facts'].get('Price', 'price n/a')}) — {best[0]['verdict']} " if best else "None of them convinced me. ") +
                       (f"Skip: {', '.join(L['seller'] for L in options if L['grade'] == 'bad')}. " if any(L['grade'] == 'bad' for L in options) else "") +
                       (f"Your conditions ({cond}) are applied in the verdicts. " if cond else "") +
                       (counterfeit_note or ""))
        doc.summary(summary)
        doc.table("Side by side", [[L["seller"], L["facts"].get("Price", "-"), L["facts"].get("Shipping", "-"), L["facts"].get("Delivery time", "-"),
                                    L["facts"].get("Ships from / origin", "-"), {"good": "👍 good", "ok": "🤔 ok", "bad": "👎 avoid"}[L["grade"]]] for L in options],
                  header=["Seller", "Price", "Shipping", "Delivery", "From", "Verdict"])
        for L in options:
            facts = {k: v for k, v in L["facts"].items() if not k.startswith("_")}
            if L.get("socials"):
                facts["Social"] = " · ".join(s.get("note") or f"{s['platform']}: {s['url']}" for s in L["socials"])
            note = ""
            if L.get("eyes"):
                note = L["eyes"]
            if L.get("review_sources"):
                note += ("\n" if note else "") + "Reviews read at: " + ", ".join(L["review_sources"][:2])
            doc.option(L.get("seller") or L.get("title", "?"), L["url"], price=L["facts"].get("Price", ""), image=L.get("image"), verdict=L["verdict"], grade=L["grade"],
                       facts=facts, pros=L.get("pros"), cons=L.get("cons"), note=note)
        doc.section("How I judged", ("On Vinted the seller's location, feedback split and the last feedback lines come from the seller's own public profile. " if any(L["facts"].get("_marketplace") == "vinted" for L in options) else "") +
                                    "Price, shipping and origin are quoted from each listing page. Reliability comes from the rating and review counts on the page, "
                                    "complaint/praise words in what buyers wrote, whether the seller has a public social page, and (when my eyes are on) whether the photo "
                                    "matches the description. Nothing was bought, no account was used.")
        path = doc.save(f"{product}-sellers")
        self.log("doc_saved", title=doc.title, options=len(options), path=str(path))
        self._step(5, "done" if not want_doc else "document ready")
        summary += f" ({len(options)} listings, {time.time() - t0:.0f}s)"
        return path, summary, options
