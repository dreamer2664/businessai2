"""Deal hunting: the owner's shopping list → the cheapest sound listings per item across the used marketplaces, one document.

    "find me the best deals for this list … subito, vinted, wallapop … Facebook only if in Barletta"
    → for every item: the marketplaces' own search (their JSON, politely), cards filtered by the owner's limits,
      ranked by total price with a sanity check (accessories and bundles priced like the real thing are pushed down),
      the top listing opened for the seller's feedback, and one section per item in the document.

Sites: vinted + subito have deep readers (markets.py). wallapop / temu / shein / dhgate / banggood are tried through
their public search pages; when a site walls this machine (Cloudflare, login, 403) the section says so in one line
and the item still gets its deals from the sites that answered. Facebook Marketplace needs a login → never opened.
"""
import re
import time
import urllib.parse

from . import markets
from .browser import BrowserError
from .library import Doc

# what a card must look like to be "the item" and not a part of it
ACCESSORY = re.compile(r"\b(custodi[ae]|cases?|cover|cavo|cavi|cables?|caricator[ei]|chargers?|alimentatore|adattator[ei]|adapters?|pellicol[ae]|screen protectors?|supporto|stand|dock|grip|"
                       r"filtr[oi]|filters?|spazzol[ae]|brush(es)?|testina|tubo|ricambi|compatibil[ei]|compatible|kit|set di|ricarica|"
                       r"controller|joy-?con|gioco|game|giochi|games|skin|sticker|manuale|scatola|box only|solo scatola|ricambio|parts?|pezzi|batteria|battery|"
                       r"borsa|bag|zaino|filtro|filter|spazzola|brush|accessori[oi]?|accessor(y|ies)|compatibile con|per nintendo|for nintendo|per iphone|for iphone)\b", re.I)
BROKEN = re.compile(r"\b(non funziona|not working|rott[oa]|broken|per ricambi|for parts|guast[oa]|difettos[oa]|faulty|da riparare|schermo rotto|cracked)\b", re.I)
KNOWN_SITES = ("vinted", "subito", "wallapop", "ebay", "temu", "shein", "dhgate", "banggood", "aliexpress", "amazon", "facebook marketplace")
NO_LOGIN = {"facebook marketplace": "needs a Facebook login — I never log in by myself; open it on your phone with the city filter",
            "temu": "sends visitors to a login page before any search — nothing to read without an account"}


def item_words(name):
    return [w for w in re.findall(r"[a-z0-9]+", name.lower()) if len(w) > 1 and w not in ("the", "and", "con", "per", "for", "with", "usato", "used")]


def matches(card, name):
    """The card is about the item: every word of the item's name appears in the title (numbers must match exactly)."""
    title = (card.get("title") or "").lower()
    words = item_words(name)
    if not words:
        return True
    hit = sum(1 for w in words if re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", title))
    return hit >= max(1, len(words) - (1 if len(words) >= 3 else 0))


VARIANT = re.compile(r"\b(lite|mini|go|nano|se|compact|junior|kids?|slim|pocket|air|neo|core)\b", re.I)   # a cheaper sibling model


def rank_key(card, name, ref_price=None):
    """Cheaper first, but accessories, bundles-of-parts and broken items go after the real thing; a cheaper sibling
    model the owner did not name ('Switch Lite' for 'nintendo switch') goes after the plain model."""
    total = card.get("total") or card.get("price") or 1e9
    title = card.get("title") or ""
    penalty = 0
    if ACCESSORY.search(title) and not ACCESSORY.search(name):
        penalty += 2
    if VARIANT.search(title) and not VARIANT.search(name):
        penalty += 1
    if BROKEN.search(title):
        penalty += 3
    if ref_price and total < ref_price * 0.25:                    # a "Nintendo Switch" at € 9 is a game or a case, whatever the title says
        penalty += 2
    return (penalty, total)


def city_ok(card, city):
    if not city:
        return True
    loc = (card.get("location") or "") + " " + (card.get("seller_location") or "")
    return bool(re.search(re.escape(city), loc, re.I))


class DealHunter:
    def __init__(self, tasks, log=None, viewer=None, pace=None):
        self.T = tasks
        self.log = log or (lambda kind, **f: None)
        self.viewer = viewer
        self.pace = pace
        self.throttle = markets.Throttle()

    def _step(self, i, note=""):
        if self.viewer:
            try:
                self.viewer.plan_step(i, note)
            except Exception:
                pass

    def _stopped(self):
        return bool(self.pace and self.pace.should_stop())

    # ---- one item on one site ------------------------------------------------------
    def search_site(self, b, site, item, limit=8):
        """→ (cards, note). Cards carry 'site'. Never raises for site behaviour."""
        name, mx = item["name"], item.get("max")
        if site in markets.SEARCH:
            try:
                cards, note = markets.search_market(b, site, name, limit, self.throttle, price_to=mx)
            except BrowserError as e:
                return [], f"{site}: {str(e)[:60]}"
            for c in cards:
                c["site"] = site
            return cards, note
        if site in NO_LOGIN:
            return [], f"{site}: {NO_LOGIN[site]}"
        url = SEARCH_URLS.get(site)
        if not url:
            return [], f"{site}: I have no reader for this site yet"
        url = url.format(q=urllib.parse.quote_plus(name))
        self.throttle.wait(url)
        try:
            b.open(url)
        except BrowserError as e:
            return [], f"{site}: {str(e)[:60]}"
        st = b.status()
        if st != "ok":
            self.throttle.punish(url)
            return [], f"{site}: {st} wall on this machine"
        try:
            title = b.page.title()
        except Exception:
            title = ""
        if re.search(r"error page|access denied|request blocked|could not be satisfied|403|not available in your", title + " " + b.page.inner_text("body")[:300], re.I):
            self.throttle.punish(url)
            return [], f"{site}: blocks this machine (an error page instead of results) — it may work from your PC"
        try:
            cards = generic_cards(b, site, limit)
        except Exception as e:
            return [], f"{site}: could not read the results ({str(e)[:40]})"
        if not cards:
            return [], f"{site}: no listings I could read (blocked or a layout I don't know yet)"
        return cards, ""

    # ---- the whole list ------------------------------------------------------------
    def run(self, items, sites=(), city=None, per_item=4, want_doc=True):
        """items: [{'name', 'max'}]; sites: the owner's list (unknown → skipped with a note); city: for Facebook-only-if-local.
        Returns (doc path or None, summary text, per-item results)."""
        t0 = time.time()
        sites = [s for s in (sites or ("vinted", "subito")) if s in KNOWN_SITES] or ["vinted", "subito"]
        results = []
        notes = {}
        with self.T._session() as b:
            for i, it in enumerate(items):
                if self._stopped():
                    break
                self._step(1, f"item {i + 1}/{len(items)}: {it['name']} — searching {', '.join(sites)}")
                found = []
                for s in sites:
                    if self._stopped():
                        break
                    cards, note = self.search_site(b, s, it)
                    if note:
                        notes[s] = note
                        self.log("deal_site_note", site=s, item=it["name"], note=note[:100])
                    for c in cards:
                        if not matches(c, it["name"]):
                            continue
                        if it.get("max") and (c.get("total") or c.get("price") or 0) > it["max"]:
                            continue
                        if s == "facebook marketplace" and not city_ok(c, city):
                            continue
                        found.append(c)
                prices = sorted(x.get("total") or x.get("price") for x in found if x.get("price"))
                ref = prices[len(prices) // 2] if prices else None                       # the median: what the item really costs used
                found.sort(key=lambda c: rank_key(c, it["name"], ref))
                best = found[:per_item]
                # the top listing: open it for the seller's feedback (Vinted/subito deep reader)
                if best and best[0]["site"] in markets.ITEM and not self._stopped():
                    self._step(2, f"{it['name']}: reading the best listing ({best[0]['site']})")
                    try:
                        facts, note = markets.read_item(b, best[0]["site"], best[0]["url"], self.throttle)
                        if facts and best[0]["site"] == "vinted":
                            markets.vinted_enrich(b, facts, self.throttle)
                        best[0]["facts"] = {k: v for k, v in (facts or {}).items() if not k.startswith("_")}
                        best[0]["image"] = self._picture(b)
                    except Exception as e:
                        self.log("deal_read_failed", error=str(e)[:80])
                for c in best:                                                  # a small picture for every card shown, from the card's own thumbnail
                    if not c.get("image") and c.get("image_url") and not self._stopped():
                        try:
                            from .sellers import SellerCheck
                            c["image"] = SellerCheck._fetch_image(None, b, c["image_url"], max_bytes=120000)
                        except Exception:
                            pass
                results.append({"item": it, "best": best, "n_found": len(found), "ref": ref})
                if self.pace:
                    try:
                        r = self.pace.tick()
                        if r:
                            self.T.notify(r)
                    except Exception:
                        pass
        self.T._release_page()
        self._step(3, "writing the document")
        summary = self.summary(results, notes, sites, time.time() - t0)
        path = self.document(results, notes, sites, city) if want_doc else None
        return path, summary, results

    def _picture(self, b):
        """The listing's main photo (og:image or the biggest image), shrunk — through the seller check's fetcher."""
        try:
            src = b.page.evaluate("""() => { const og = document.querySelector('meta[property="og:image"]'); if (og && og.content) return og.content;
                const imgs = [...document.images].filter(i => i.naturalWidth > 200).sort((a, b) => b.naturalWidth * b.naturalHeight - a.naturalWidth * a.naturalHeight); return imgs.length ? imgs[0].src : ''; }""")
            if not src:
                return None
            from .sellers import SellerCheck
            return SellerCheck._fetch_image(None, b, src)
        except Exception:
            return None

    # ---- words ---------------------------------------------------------------------
    @staticmethod
    def _line(c):
        price = c.get("total") or c.get("price")
        sym = {"USD": "$", "GBP": "£"}.get(c.get("currency") or "EUR", "€")
        bits = [f"{sym} {price:,.2f}".replace(",", " ") if isinstance(price, (int, float)) else "price n/a", c.get("condition") or "", c.get("location") or "",
                (f"seller {c['seller']}" if c.get("seller") else ""), c.get("shipping") or ""]
        fb = (c.get("facts") or {}).get("Feedback")
        if fb:
            bits.append(fb)
        return f"{c['title'][:60]} — " + " · ".join(x for x in bits if x) + f" ({c['site']})"

    def summary(self, results, notes, sites, secs):
        out = []
        for r in results:
            it = r["item"]
            if not r["best"]:
                out.append(f"• {it['name']}: nothing that matched" + (f" under € {it['max']}" if it.get("max") else "") + f" on {', '.join(sites)}.")
                continue
            b0 = r["best"][0]
            tag = ""
            if rank_key(b0, it["name"], r["ref"])[0]:
                tag = " (not the exact model / an accessory — the exact thing was not listed cheaper)"
            out.append(f"• {it['name']}: best {self._line(b0)}{tag}" + (f" — {r['n_found']} matching listings seen" if r["n_found"] > 1 else ""))
        skipped = [f"{s}: {n}" for s, n in notes.items()]
        head = f"Deals for {len(results)} item(s) in {int(secs // 60)} min {int(secs % 60)} s."
        return head + "\n" + "\n".join(out) + ("\n\nNot searched properly: " + "; ".join(skipped) if skipped else "")

    def document(self, results, notes, sites, city):
        d = Doc(f"Best deals — {len(results)} items", f"searched {', '.join(sites)}" + (f" · Facebook only in {city}" if city else ""), kind="deals")
        rows = []
        for r in results:
            it = r["item"]
            if r["best"]:
                b0 = r["best"][0]
                p = b0.get("total") or b0.get("price")
                rows.append([it["name"], f"€ {p:.2f}" if isinstance(p, (int, float)) else "—", b0["site"], (b0.get("location") or b0.get("condition") or ""), f"{b0['title'][:40]}\n{b0['url']}"])
            else:
                rows.append([it["name"], "—", "—", "nothing matched" + (f" under € {it['max']}" if it.get("max") else ""), ""])
        d.table("At a glance — best price per item", rows, header=["Item", "Best price", "Where", "Where it is / condition", "Listing"])
        for r in results:
            it = r["item"]
            d.section(it["name"] + (f" (max € {it['max']})" if it.get("max") else ""),
                      f"{r['n_found']} matching listing(s) seen; typical used price around € {r['ref']:.0f}." if r["ref"] else "No matching listing on the sites that answered.")
            for c in r["best"]:
                p = c.get("total") or c.get("price")
                facts = {"Price": f"€ {p:.2f}" if isinstance(p, (int, float)) else "", "Condition": c.get("condition", ""), "Where": c.get("location", ""),
                         "Seller": c.get("seller", ""), "Shipping": c.get("shipping", "")}
                facts.update({k: v for k, v in (c.get("facts") or {}).items() if k in ("Feedback", "Rating", "Seller location", "Items for sale", "Last active", "Verified")})
                pen = rank_key(c, it["name"], r["ref"])[0]
                grade = "good" if not pen else ("ok" if pen == 1 else "bad")
                verdict = "" if grade == "good" else ("A different (usually cheaper) model than the one you named — fine if that's ok for you." if pen == 1 else
                                                     "Looks like an accessory, a part, a bundle piece or a broken unit — check the photos before you pay.")
                d.option(c["title"][:80], c["url"], price=facts["Price"], image=c.get("image"), facts=facts, grade=grade, verdict=verdict)
        if notes:
            d.bullets("Sites I could not search properly", [f"{s}: {n}" for s, n in notes.items()])
        d.section("How I ranked", "Cheapest total first (price + buyer protection where the site shows it). Listings whose title says accessory, game, case, "
                  "broken or 'for parts', and listings far below the typical price, go after the real thing. Nothing was bought or messaged.")
        return d.save()


# ---- generic readers for sites without a deep parser (best effort, read-only) --------------------------------
SEARCH_URLS = {"wallapop": "https://it.wallapop.com/app/search?keywords={q}&order_by=price_low_to_high",
               "ebay": "https://www.ebay.it/sch/i.html?_nkw={q}&_sop=15&LH_PrefLoc=1",
               "banggood": "https://www.banggood.com/search/{q}.html",
               "dhgate": "https://www.dhgate.com/wholesale/search.do?searchkey={q}",
               "shein": "https://it.shein.com/pdsearch/{q}/",
               "aliexpress": "https://www.aliexpress.com/w/wholesale-{q}.html",
               "amazon": "https://www.amazon.it/s?k={q}"}

_JS_CARDS = r"""
(limit) => {
  // Generic result cards: a link to a product/listing page that has a price near it. Works on most shop grids.
  const money = /(?:€|eur|\$|us\$|£)\s?\d{1,5}(?:[.,]\d{1,3})?|\d{1,5}(?:[.,]\d{2})\s?(?:€|eur)/i;
  const seen = new Set(); const out = [];
  const anchors = Array.from(document.querySelectorAll('a[href]'));
  for (const a of anchors) {
    const href = a.href; if (!href || !/^https?:/.test(href)) continue;
    const key = href.split('?')[0]; if (seen.has(key)) continue;
    if (!/\/(item|items|itm|p|product|products|dp|products?-|goods|detail|annunci|listing|i)\/|-p-\d|\.html/i.test(href)) continue;
    let box = a; let txt = ''; let hops = 0;
    while (box && hops < 4) { txt = (box.innerText || '').trim(); if (money.test(txt) && txt.length > 15) break; box = box.parentElement; hops++; }
    if (!box || !money.test(txt)) continue;
    const m = txt.match(money); const priceRaw = m ? m[0] : '';
    const title = (a.getAttribute('title') || a.getAttribute('aria-label') || (a.innerText || '').trim().split('\n')[0] || (box.querySelector('h2,h3,h4,[class*=title i]') || {}).innerText || '').trim().slice(0, 120);
    if (title.length < 4 || /^\d+\s*(reviews?|recensioni|sold|venduti|orders?)$/i.test(title) || money.test(title)) continue;   // "1 review" / "€ 3,09" are not titles
    const img = (box.querySelector('img') || {}).src || '';
    seen.add(key); out.push({title, url: key, priceRaw, img: img.startsWith('http') ? img : ''});
    if (out.length >= limit * 3) break;
  }
  return out;
}
"""


def _price_of(raw):
    m = re.search(r"(\d{1,5}(?:[.,]\d{1,3})?)", raw or "")
    if not m:
        return None
    v = m.group(1).replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return None


def generic_cards(b, site, limit=8):
    raw = b.page.evaluate(_JS_CARDS, limit)
    out = []
    for r in raw or []:
        p = _price_of(r.get("priceRaw"))
        if p is None:
            continue
        cur = "USD" if re.search(r"\$|US\$|USD", r.get("priceRaw") or "") else ("GBP" if "£" in (r.get("priceRaw") or "") else "EUR")
        out.append({"title": r["title"], "price": p, "url": r["url"], "site": site, "image_url": r.get("img") or "", "currency": cur,
                    "condition": "new" if site in ("banggood", "dhgate", "shein", "temu", "aliexpress", "amazon") else "", "location": "", "seller": "", "shipping": ""})
        if len(out) >= limit:
            break
    return out
