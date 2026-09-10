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
                       r"filtr[oi]|filters?|spazzol[ae]|brush(es)?|testina|tubo|ricambi|compatibil[ei]|compatible|kit|set di|ricarica|hanger|gancio|staffa|wall mount|"
                       r"bocchetta|beccuccio|nozzle|attachment|accessorio|serbatoio|tank|motore|motor|scheda|board|display|schermo|screen|vetro|glass|"
                       r"controller|joy-?con|gioco|game|giochi|games|skin|sticker|manuale|scatola|box only|solo scatola|ricambio|parts?|pezzi|batteria|battery|"
                       r"borsa|bag|zaino|filtro|filter|spazzola|brush|accessori[oi]?|accessor(y|ies)|compatibile con|per nintendo|for nintendo|per iphone|for iphone)\b", re.I)
GAME_WORDS = re.compile(r"\b(zelda|mario|pok[eé]mon|kirby|splatoon|animal crossing|metroid|smash|fifa|fc ?2[0-9]|gta|call of duty|minecraft|fortnite|luigi|donkey kong|"
                        r"just dance|ring fit|switch sports|gioco|giochi|game|games|videogioco|cartuccia|cartridge|edizione digitale|codice download)\b", re.I)   # a game titled with the console's name
BROKEN = re.compile(r"\b(non funziona|not working|rott[oa]|broken|per ricambi|for parts|guast[oa]|difettos[oa]|faulty|da riparare|schermo rotto|cracked)\b", re.I)
KNOWN_SITES = ("vinted", "subito", "wallapop", "ebay", "temu", "shein", "dhgate", "banggood", "aliexpress", "amazon", "facebook marketplace")
USED_SITES = {"vinted", "subito", "wallapop", "facebook marketplace"}                  # private sellers, second-hand
NEW_SITES = {"temu", "shein", "dhgate", "banggood", "aliexpress", "amazon"}            # shops, new goods, shipped (often from China: 2–4 weeks, customs over € 150)
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


PLACEHOLDER_PRICES = (0, 1, 2, 3, 5, 10, 99, 100, 111, 123, 999, 1000, 1111, 1234, 9999)   # "€ 1" = "make me an offer", not a price


def price_is_placeholder(price, ref_price=None):
    """Sellers who don't want to name a price type 1 €, 10 €, 123 €, 999 € … — a real item never costs that, so such
    a card is never 'the best deal' (the doc still lists it, marked)."""
    if not isinstance(price, (int, float)):
        return True
    if price in PLACEHOLDER_PRICES and (ref_price is None or price < ref_price * 0.5 or price > ref_price * 4):
        return True
    return bool(ref_price) and price < ref_price * 0.15


def typical_price(cards, name):
    """What the item really costs: the median of the *clean* matches (no accessory/broken/variant words, no placeholder
    numbers), so a page of € 1 hangers cannot drag it down."""
    clean = [(c.get("total") or c.get("price")) for c in cards
             if isinstance(c.get("price"), (int, float)) and not ACCESSORY.search(c.get("title") or "") and not BROKEN.search(c.get("title") or "") and not GAME_WORDS.search(c.get("title") or "")
             and not (VARIANT.search(c.get("title") or "") and not VARIANT.search(name)) and (c.get("total") or c.get("price")) not in PLACEHOLDER_PRICES]
    clean = sorted(x for x in clean if x)
    if not clean:
        return None
    return clean[len(clean) // 2]


def rank_key(card, name, ref_price=None):
    """Cheaper first, but accessories, bundles-of-parts and broken items go after the real thing; a cheaper sibling
    model the owner did not name ('Switch Lite' for 'nintendo switch') goes after the plain model; placeholder prices
    (€ 1 'make an offer') go last of all."""
    total = card.get("total") or card.get("price") or 1e9
    title = card.get("title") or ""
    penalty = 0
    if price_is_placeholder(card.get("total") or card.get("price"), ref_price):
        penalty += 4
    if ACCESSORY.search(title) and not ACCESSORY.search(name):
        penalty += 2
    if GAME_WORDS.search(title) and not GAME_WORDS.search(name) and re.search(r"\b(switch|ps[345]|playstation|xbox|wii|3ds|nintendo)\b", name, re.I):
        penalty += 2                                                  # "Nintendo switch zelda" at € 30 is the game, not the console
    if VARIANT.search(title) and not VARIANT.search(name):
        penalty += 1
    if ref_price and total < ref_price * 0.4 and len(title.split()) <= 3 and total < 45:
        penalty += 1                                                  # "Nintendo switch" at € 40 with no words: usually a game, a box or a broken one — never the top pick without a look
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

    def depth(self):
        """How deep per item: 1 = one results page per site (quick), 2 = cheapest-first + relevance (normal),
        3 = + a second page and more listings verified (slow / a time floor)."""
        if not self.pace:
            return 2
        try:
            if self.pace.hurry():
                return 1
            if self.pace.mode == "slow" or self.pace.under_floor():
                return 3
        except Exception:
            pass
        return 2

    # cookies that make a shop show euro prices / the Italian site (set once per browser, before the first search)
    SITE_COOKIES = {"banggood": [{"name": "currency", "value": "EUR", "domain": ".banggood.com", "path": "/"}],
                    "dhgate": [{"name": "currency", "value": "EUR", "domain": ".dhgate.com", "path": "/"}],
                    "aliexpress": [{"name": "aep_usuc_f", "value": "site=glo&c_tp=EUR&region=IT&b_locale=it_IT", "domain": ".aliexpress.com", "path": "/"}]}

    def _site_prefs(self, b, site):
        done = getattr(b, "_prefs_done", set())
        if site in done or site not in self.SITE_COOKIES:
            return
        try:
            b._ctx.add_cookies(self.SITE_COOKIES[site])
        except Exception:
            pass
        done.add(site)
        b._prefs_done = done

    # ---- one item on one site ------------------------------------------------------
    def search_site(self, b, site, item, limit=8, depth=2):
        """→ (cards, note). Cards carry 'site'. Never raises for site behaviour.
        depth ≥ 2 also reads the site's cheapest-first order; depth 3 adds a second page of it."""
        name, mx = item["name"], item.get("max")
        if site in markets.SEARCH:
            passes = [(None, 1)] if depth <= 1 else ([("price", 1), (None, 1)] if depth == 2 else [("price", 1), ("price", 2), (None, 1)])
            out, note, seen = [], "", set()
            for order, page in passes:
                if self._stopped():
                    break
                try:
                    cards, n = markets.search_market(b, site, name, limit if page == 1 else limit, self.throttle, price_to=mx, order=order, page=page)
                except BrowserError as e:
                    note = note or f"{site}: {str(e)[:60]}"
                    continue
                note = note or n
                for c in cards:
                    if c["url"] not in seen:
                        seen.add(c["url"]); c["site"] = site; out.append(c)
            return out, ("" if out else note)
        if site in NO_LOGIN:
            return [], f"{site}: {NO_LOGIN[site]}"
        url = SEARCH_URLS.get(site)
        if not url:
            return [], f"{site}: I have no reader for this site yet"
        url = url.format(q=urllib.parse.quote_plus(name))
        self._site_prefs(b, site)
        self.throttle.wait(url)
        try:
            b.open(url)
        except BrowserError as e:
            return [], f"{site}: {str(e)[:60]}"
        st = b.status()
        if st == "captcha":                                                # Cloudflare's "Just a moment…" often clears by itself: wait once, politely
            try:
                b.page.wait_for_function("() => !/just a moment|un momento|security verification/i.test(document.title + ' ' + (document.body && document.body.innerText || '').slice(0, 300))", timeout=9000)
                time.sleep(1.0)
                st = b.status()
            except Exception:
                pass
        cur = ""
        try:
            cur = b.page.url
            title = b.page.title()
        except Exception:
            title = ""
        if re.search(r"/risk/challenge|captcha_type=|/challenge\?", cur, re.I):
            self.throttle.punish(url)
            return [], f"{site}: shows a security check (CAPTCHA) to this browser — I don't try to pass those; it may open normally from your PC"
        if re.search(r"/login\b|/signin\b|login\.html", cur, re.I) and cur != url:
            self.throttle.punish(url)
            return [], f"{site}: sends visitors to a login page before showing results — I never log in by myself"
        if st != "ok":
            self.throttle.punish(url)
            return [], f"{site}: {st} wall on this machine"
        if re.search(r"error page|access denied|request blocked|could not be satisfied|403|not available in your|ci dispiace|si è verificato un errore|something went wrong|sorry[,!]? (we|something)", title + " " + b.page.inner_text("body")[:300], re.I):
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
        depth = self.depth()
        self.log("deals_start", items=len(items), sites=sites, depth=depth)
        with self.T._session() as b:
            for i, it in enumerate(items):
                if self._stopped():
                    break
                self._step(1, f"item {i + 1}/{len(items)}: {it['name']} — searching {', '.join(sites)}" + (" (deep)" if depth == 3 else ""))
                found = []
                for s in sites:
                    if self._stopped():
                        break
                    cards, note = self.search_site(b, s, it, depth=depth)
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
                ref = typical_price(found, it["name"])                                  # what the item really costs used (clean matches only)
                found.sort(key=lambda c: rank_key(c, it["name"], ref))
                best = found[:per_item]
                # the top listing(s): open for the seller's feedback (Vinted/subito deep reader); deeper = more of them
                verify = {1: 1, 2: 1, 3: min(3, len(best))}[depth]
                for k, c in enumerate(best[:verify]):
                    if c["site"] not in markets.ITEM or self._stopped():
                        continue
                    self._step(2, f"{it['name']}: reading listing {k + 1}/{verify} ({c['site']})")
                    try:
                        facts, note = markets.read_item(b, c["site"], c["url"], self.throttle)
                        if facts and c["site"] == "vinted":
                            markets.vinted_enrich(b, facts, self.throttle)
                        c["facts"] = {k2: v for k2, v in (facts or {}).items() if not k2.startswith("_")}
                        c["image"] = self._picture(b)
                        if not facts and note:
                            c["note"] = note
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
                tag = " (⚠ not a clean match — see the document)"
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
                rows.append([it["name"], f"€ {p:.2f}" if isinstance(p, (int, float)) else "—", b0["site"], (b0.get("location") or b0.get("condition") or ""), f"{b0['title'][:40]}\n{b0.get('url', '')}"])
            else:
                rows.append([it["name"], "—", "—", "nothing matched" + (f" under € {it['max']}" if it.get("max") else ""), ""])
        d.table("At a glance — best price per item", rows, header=["Item", "Best price", "Where", "Where it is / condition", "Listing"])
        if any(s_ in NEW_SITES for s_ in sites) and any(s_ in USED_SITES for s_ in sites):
            d.section("Used vs new", "Vinted, Subito, Wallapop and Facebook are private sellers (second-hand, often pick-up or tracked shipping in Italy). "
                      "AliExpress, Banggood, DHgate, Temu and Shein are shops selling new goods, mostly shipped from China: 1–4 weeks, and orders over € 150 pay customs. "
                      "Each listing below says which it is.")
        for r in results:
            it = r["item"]
            d.section(it["name"] + (f" (max € {it['max']})" if it.get("max") else ""),
                      f"{r['n_found']} matching listing(s) seen; typical used price around € {r['ref']:.0f}." if r["ref"] else "No matching listing on the sites that answered.")
            for c in r["best"]:
                p = c.get("total") or c.get("price")
                sym = {"USD": "$", "GBP": "£"}.get(c.get("currency") or "EUR", "€")
                facts = {"Price": f"{sym} {p:.2f}" if isinstance(p, (int, float)) else "", "Condition": c.get("condition", ""), "Where": c.get("location", ""),
                         "Seller": c.get("seller", ""), "Shipping": c.get("shipping", ""),
                         "Kind": ("new, from a shop (usually shipped from China, 1–4 weeks)" if c["site"] in NEW_SITES else "second-hand, private seller")}
                facts.update({k: v for k, v in (c.get("facts") or {}).items() if k in ("Feedback", "Rating", "Seller location", "Items for sale", "Last active", "Verified")})
                pen = rank_key(c, it["name"], r["ref"])[0]
                grade = "good" if not pen else ("ok" if pen == 1 else "bad")
                verdict = "" if grade == "good" else ("A different (usually cheaper) model than the one you named — fine if that's ok for you." if pen == 1 else
                                                     "The price is a placeholder ('make me an offer') — the real price is whatever the seller says in chat." if price_is_placeholder(c.get("total") or c.get("price"), r["ref"]) else
                                                     "Looks like an accessory, a part, a bundle piece or a broken unit — check the photos before you pay.")
                d.option(c["title"][:80], c.get("url", ""), price=facts["Price"], image=c.get("image"), facts=facts, grade=grade, verdict=verdict)
        if notes:
            d.bullets("Sites I could not search properly", [f"{s}: {n}" for s, n in notes.items()])
        d.section("How I ranked", "Cheapest total first (price + buyer protection where the site shows it). Listings whose title says accessory, game, case, "
                  "broken or 'for parts', and listings far below the typical price, go after the real thing. Nothing was bought or messaged.")
        return d.save()


# ---- watching (the time floor on a shopping list) ---------------------------------------------------------------
class Watcher:
    """Re-checks the marketplaces for the owner's items: newest listings + cheapest-first, remembers what it has seen,
    and speaks only when a new listing beats the current best for an item (same rules: match, cap, penalties)."""

    def __init__(self, hunter, items, sites, results=None):
        self.h = hunter
        self.items = items
        self.sites = [s for s in (sites or ("vinted", "subito")) if s in markets.SEARCH] or ["vinted", "subito"]
        self.best = {}
        self.seen = set()
        for r in results or []:
            if r.get("best"):
                self.best[r["item"]["name"]] = r["best"][0]
            for c in r.get("best") or []:
                self.seen.add(c["url"])
        self.rounds = 0

    def round(self):
        """One pass over items × sites. Returns (messages for the owner, one log line)."""
        self.rounds += 1
        better, checked = [], 0
        with self.h.T._session() as b:
            for it in self.items:
                if self.h._stopped():
                    break
                ref = (self.best.get(it["name"]) or {}).get("total") or (self.best.get(it["name"]) or {}).get("price")
                for s in self.sites:
                    if self.h._stopped():
                        break
                    for order in ("newest", "price"):
                        try:
                            cards, _ = markets.search_market(b, s, it["name"], 10, self.h.throttle, price_to=it.get("max"), order=order)
                        except BrowserError:
                            continue
                        checked += 1
                        for c in cards:
                            c["site"] = s
                            if c["url"] in self.seen or not matches(c, it["name"]):
                                continue
                            self.seen.add(c["url"])
                            if it.get("max") and (c.get("total") or c.get("price") or 0) > it["max"]:
                                continue
                            key = rank_key(c, it["name"], ref)
                            cur = self.best.get(it["name"])
                            if cur is None or key < rank_key(cur, it["name"], ref):
                                self.best[it["name"]] = c
                                better.append(f"🔔 Better deal for {it['name']}: {DealHunter._line(c)}\n{c['url']}")
        self.h.T._release_page()
        line = f"watch round {self.rounds}: {checked} result page(s) re-checked, {len(better)} better deal(s)"
        return better, line


DealHunter.WATCH_EVERY = 900          # seconds between watch rounds (15 min): polite to the sites, fresh enough for used goods


def _watcher(self, items, sites, results=None):
    return Watcher(self, items, sites, results)


DealHunter.watcher = _watcher


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


# ---- /markets: which marketplaces this machine can read right now ---------------------------------------------
PROBE_ITEM = {"name": "nintendo switch", "max": None}


def probe_sites(hunter, sites=("vinted", "subito", "wallapop", "ebay", "banggood", "dhgate", "shein", "temu", "aliexpress", "amazon", "facebook marketplace")):
    """Try one real search per site (read-only) and say what happened, in the owner's words. Runs on the hands thread."""
    lines = []
    with hunter.T._session() as b:
        for s in sites:
            t = time.time()
            try:
                cards, note = hunter.search_site(b, s, PROBE_ITEM, limit=5, depth=1)
            except Exception as e:
                cards, note = [], f"{s}: {type(e).__name__}: {str(e)[:60]}"
            secs = time.time() - t
            if cards:
                p = [c.get("total") or c.get("price") for c in cards if c.get("price")]
                lines.append(f"✅ {s}: {len(cards)} listings read in {secs:.0f} s (from € {min(p):.0f})" if p else f"✅ {s}: {len(cards)} listings read in {secs:.0f} s")
            else:
                lines.append(f"❌ {note[len(s) + 2:] if note.startswith(s + ':') else note}".replace("❌ ", f"❌ {s}: ", 1))
    hunter.T._release_page()
    return "🛒 Marketplaces from this machine, right now:\n" + "\n".join(lines) + "\n(✅ = I can search it for you; ❌ = the site blocks this browser or needs a login — the reason is the site's, not a bug.)"
