"""Deal hunting: the owner's shopping list → the cheapest sound listings per item across the used marketplaces, one document.

    "find me the best deals for this list … subito, vinted, wallapop … Facebook only if in Barletta"
    → for every item: the marketplaces' own search (their JSON, politely), cards filtered by the owner's limits,
      ranked by total price with a sanity check (accessories and bundles priced like the real thing are pushed down),
      the top listing opened for the seller's feedback, and one section per item in the document.

Sites: vinted + subito have deep readers (markets.py). wallapop / temu / shein / dhgate / banggood are tried through
their public search pages; when a site walls this machine (Cloudflare, login, 403) the section says so in one line
and the item still gets its deals from the sites that answered. Facebook Marketplace needs a login → never opened.
"""
import json
import re
import time
import urllib.parse

from . import config, markets
from .browser import BrowserError
from .library import Doc

# what a card must look like to be "the item" and not a part of it
ACCESSORY = re.compile(r"\b(custodi[ae]|cases?|cover|cavo|cavi|cables?|caricator[ei]|chargers?|alimentatore|adattator[ei]|adapters?|pellicol[ae]|screen protectors?|supporto|stand|dock|grip|"
                       r"filtr[oi]|filters?|spazzol[ae]|brush(es)?|testina|tubo|ricambi|compatibil[ei]|compatible|kit|set di|ricarica|hanger|gancio|staffa|wall mount|"
                       r"bocchetta|beccuccio|nozzle|attachment|accessorio|serbatoio|tank|motore|motor|scheda|board|display|schermo|screen|vetro|glass|"
                       r"controller|joy-?con|gioco|game|giochi|games|skin|sticker|manuale|scatola|box only|solo scatola|ricambio|parts?|pezzi|batteria|battery|"
                       r"borsa|bag|zaino|filtro|filter|spazzola|brush|accessori[oi]?|accessor(y|ies)|compatibile con|per nintendo|for nintendo|per iphone|for iphone)\b", re.I)
GAME_WORDS = re.compile(r"\b(zelda|mario|pok[eé]mon|kirby|splatoon|animal crossing|metroid|smash|fifa|fc ?2[0-9]|gta|call of duty|cod|minecraft|fortnite|luigi|donkey kong|"
                        r"just dance|ring fit|switch sports|gioco|giochi|game|games|videogioco|videogiochi|cartuccia|cartridge|edizione digitale|codice download|"
                        r"need for speed|hot pursuit|assassin|far cry|forza|halo|gears|battlefield|nba ?2k|f1 ?2[0-9]|pes|efootball|tekken|mortal kombat|resident evil|"
                        r"spider-?man|god of war|last of us|uncharted|horizon|elden ring|dark souls|sekiro|hogwarts|lego [a-z]|sonic|crash|spyro|rayman|skyrim|witcher|cyberpunk|red dead|"
                        r"per (?:xbox|ps[345]|playstation|switch|nintendo|wii)|for (?:xbox|ps[345]|playstation|switch|nintendo|wii)|(?:xbox|ps[345]|playstation|switch) (?:one )?(?:e|and|&|/) (?:xbox|ps[345]|series))\b", re.I)   # a game titled with the console's name
BROKEN = re.compile(r"\b(non funziona|not working|rott[oa]|broken|per ricambi|for parts|guast[oa]|difettos[oa]|faulty|da riparare|schermo rotto|cracked)\b", re.I)
KNOWN_SITES = ("vinted", "subito", "wallapop", "ebay", "temu", "shein", "dhgate", "banggood", "aliexpress", "amazon", "facebook marketplace")
USED_SITES = {"vinted", "subito", "wallapop", "facebook marketplace"}                  # private sellers, second-hand
NEW_SITES = {"temu", "shein", "dhgate", "banggood", "aliexpress", "amazon"}            # shops, new goods, shipped (often from China: 2–4 weeks, customs over € 150)
NO_LOGIN = {"facebook marketplace": "needs a Facebook login — I never log in by myself; open it on your phone with the city filter",
            "temu": "sends visitors to a login page before any search — nothing to read without an account"}


# an item name that alone gives useless results: a whole family (which model? which size?) — one question per list, not per item
VAGUE = {
    "iphone": "which model (e.g. iPhone 12, 13, 15 Pro) and storage?", "samsung": "which model (e.g. Galaxy S23, A54)?", "galaxy": "which Galaxy model?",
    "phone": "which brand and model?", "telefono": "quale marca e modello?", "smartphone": "which brand and model?", "cellulare": "quale marca e modello?",
    "laptop": "which brand/model, or at least screen size and budget?", "notebook": "which brand/model, or at least screen size and budget?", "pc": "desktop or laptop, which specs or budget?", "computer": "desktop or laptop, which specs or budget?",
    "macbook": "Air or Pro, which year/size?", "ipad": "which iPad (Air, Pro, mini) and size?", "tablet": "which brand/model or size?",
    "tv": "which size (inches) and budget?", "televisore": "quanti pollici e che budget?", "monitor": "which size and use (gaming/office)?",
    "bike": "city, road, mountain or e-bike, and frame size?", "bici": "città, corsa, mountain bike o elettrica, e che taglia?", "bicicletta": "città, corsa, mountain bike o elettrica, e che taglia?",
    "scooter": "electric kick scooter or a moped, which model?", "monopattino": "quale modello o budget?",
    "console": "which console (PS5, Switch, Xbox)?", "playstation": "which PlayStation (4, 4 Pro, 5)?", "xbox": "which Xbox (One, Series S, Series X)?", "nintendo": "which Nintendo (Switch, Switch Lite, OLED)?",
    "camera": "which brand/model or type (mirrorless, compact, action)?", "fotocamera": "quale marca/modello o tipo?", "drone": "which model or budget?",
    "watch": "which brand/model?", "orologio": "quale marca/modello?", "smartwatch": "which one (Apple Watch series, Galaxy Watch…)?", "airpods": "which AirPods (2, 3, Pro, Pro 2)?", "cuffie": "quale marca/modello?", "headphones": "which brand/model?",
    "shoes": "which brand/model and size?", "scarpe": "quale marca/modello e numero?", "sneakers": "which model and size?", "jacket": "which brand, size?", "giacca": "quale marca, taglia?",
    "car": "I only search used-goods marketplaces — for cars say make, model, year and budget", "auto": "cerco solo sui marketplace dell'usato — per le auto dimmi marca, modello, anno e budget", "macchina": "marca, modello, anno e budget?",
    "sofa": "which size (2/3 seats, corner) and budget?", "divano": "quanti posti e che budget?", "fridge": "which size/type and budget?", "frigo": "che dimensioni e budget?", "washing machine": "which load (kg) and budget?", "lavatrice": "quanti kg e che budget?",
    "dyson": "which Dyson (V8, V11, V15, Airwrap…)?", "gopro": "which GoPro (Hero 9, 10, 11, 12)?", "kindle": "which Kindle (basic, Paperwhite, Oasis)?", "lego": "which set (number or name)?",
}


def vague_items(items):
    """Items whose name is only a family word → [(name, question)]; specific names pass ('iphone 12', 'dyson v8')."""
    out = []
    for it in items:
        w = item_words(it["name"])
        key = " ".join(w)
        if key in VAGUE or (len(w) == 1 and w[0] in VAGUE):
            out.append((it["name"], VAGUE.get(key) or VAGUE[w[0]]))
        elif len(w) == 2 and w[0] in VAGUE and w[1] in ("usato", "used", "nuovo", "new", "economico", "cheap"):
            out.append((it["name"], VAGUE[w[0]]))
    return out


def item_words(name):
    return [w for w in re.findall(r"[a-z0-9]+", name.lower()) if len(w) > 1 and w not in ("the", "and", "con", "per", "for", "with", "usato", "usata", "used", "un", "una", "uno")]


SOFT = re.compile(r"^(\d{2,4}gb|\d{1,2}tb|\d{2,3}cm|\d{2}|taglia|size|tg|colore|colou?r|nero|bianco|black|white|blu|blue|rosso|red|verde|green|grigio|grey|gray|"
                  r"da|di|a|il|la|le|lo|gli|of|in|corsa|città|city|mtb|elettrica|electric|usato|usata|used|nuovo|nuova|new|ottimo|buono)$", re.I)   # details, not the identity


SYNONYMS = {"bici": ("bicicletta", "bike", "mtb"), "bicicletta": ("bici", "bike"), "bike": ("bici", "bicicletta"), "tv": ("televisore", "televisione", "smart tv"),
            "televisore": ("tv",), "frigo": ("frigorifero",), "lavatrice": ("lavabiancheria",), "pc": ("computer", "desktop"), "portatile": ("laptop", "notebook"),
            "laptop": ("portatile", "notebook"), "cuffie": ("headphones", "auricolari"), "scarpe": ("sneakers", "shoes"), "orologio": ("watch",), "cellulare": ("smartphone", "telefono"),
            "telefono": ("smartphone", "cellulare"), "zaino": ("backpack",), "divano": ("sofa", "sofà"), "giacca": ("jacket", "giubbotto"), "controller": ("joystick", "pad", "dualshock", "dualsense", "gamepad"),
            "aspirapolvere": ("scopa elettrica", "vacuum"), "monopattino": ("scooter",), "macchina fotografica": ("fotocamera",), "fotocamera": ("camera", "macchina fotografica")}


def _has(word, title):
    if re.search(r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9])", title):
        return True
    return any(re.search(r"(?<![a-z0-9])" + re.escape(syn) + r"(?![a-z0-9])", title) for syn in SYNONYMS.get(word, ()))


def matches(card, name):
    """The card is about the item: the identity words of the item's name appear in the title (model numbers exactly);
    details like storage, size, colour, 'da corsa' are soft — they help ranking, never exclude."""
    title = (card.get("title") or "").lower()
    words = item_words(name)
    if not words:
        return True
    core_w = []
    for i, w in enumerate(words):
        prev = words[i - 1] if i else ""
        if re.fullmatch(r"\d{2}", w) and prev in ("taglia", "size", "tg", "numero", "n", "eu", "cm") or (SOFT.match(w) and not re.fullmatch(r"\d{1,2}", w)):
            continue                                                  # "taglia 54" is a detail; a bare "13" after "iphone" is the model
        core_w.append(w)
    core_w = core_w or words[:2]
    hit = sum(1 for w in core_w if _has(w, title))
    # a model number in the name must be in the title ("iphone 13" never matches "iPhone 12"), whatever the other words
    for w in core_w:
        if re.fullmatch(r"\d{1,2}[a-z]?|[a-z]\d{1,2}", w) and not re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", title):
            return False
    return hit >= max(1, len(core_w) - (1 if len(core_w) >= 3 else 0))


VARIANT = re.compile(r"\b(lite|mini|go|nano|se|compact|junior|kids?|slim|pocket|air|neo|core)\b", re.I)   # a cheaper sibling model


PLACEHOLDER_PRICES = (0, 1, 2, 3, 5, 10, 99, 100, 111, 123, 999, 1000, 1111, 1234, 9999)   # "€ 1" = "make me an offer", not a price


def price_is_placeholder(price, ref_price=None):
    """Sellers who don't want to name a price type 1 €, 10 €, 123 €, 999 € … — a real item never costs that, so such
    a card is never 'the best deal' (the doc still lists it, marked)."""
    if not isinstance(price, (int, float)):
        return True
    if price <= 3:                                                    # € 1–3 is never a price, whatever the item
        return True
    if price in PLACEHOLDER_PRICES and (ref_price is None or price < ref_price * 0.5 or price > ref_price * 4):
        return True
    return bool(ref_price) and price < ref_price * 0.15


def typical_price(cards, name):
    """What the item really costs: the median of the *clean* matches (no accessory/broken/variant words, no placeholder
    numbers), so a page of € 1 hangers cannot drag it down."""
    clean = [(c.get("total") or c.get("price")) for c in cards
             if isinstance(c.get("price"), (int, float)) and not ACCESSORY.search(c.get("title") or "") and not BROKEN.search(c.get("title") or "") and not GAME_WORDS.search(c.get("title") or "")
             and not (VARIANT.search(c.get("title") or "") and not VARIANT.search(name)) and not price_is_placeholder(c.get("total") or c.get("price"))]
    fl = floor_price(name)
    clean = sorted(x for x in clean if x and (not fl or x >= fl))
    if not clean:
        return None
    return clean[len(clean) // 2]


# what a working unit of these can't realistically be sold for second-hand (below = a game, a box, an accessory or broken)
FLOOR_PRICE = [(r"\bxbox series x\b", 200), (r"\bxbox series s\b", 120), (r"\bxbox one\b", 60), (r"\bps5\b|\bplaystation 5\b", 250), (r"\bps4 pro\b", 120), (r"\bps4\b|\bplaystation 4\b", 80),
               (r"\bnintendo switch oled\b", 150), (r"\bnintendo switch lite\b", 70), (r"\bnintendo switch\b|\bswitch\b", 90), (r"\bsteam deck\b", 200),
               (r"\biphone 1[5-6]\b", 300), (r"\biphone 1[3-4]\b", 200), (r"\biphone 1[1-2]\b", 120), (r"\bmacbook\b", 200), (r"\bipad pro\b", 200), (r"\bipad\b", 80),
               (r"\bdyson v1[0-5]\b", 120), (r"\bdyson v[6-8]\b", 50), (r"\bairpods pro\b", 60), (r"\bgopro\b", 60), (r"\bkindle\b", 40), (r"\bthermomix\b|\bbimby\b", 300)]
MULTI_CONSOLE = re.compile(r"\b(xbox|ps[345]|playstation|switch|nintendo|series [sx]|one [sx]?)\b.*\b(xbox|ps[345]|playstation|switch|nintendo|series [sx]|one [sx]?)\b", re.I)


def floor_price(name):
    low = name.lower()
    for pat, fl in FLOOR_PRICE:
        if re.search(pat, low):
            return fl
    return None


def rank_key(card, name, ref_price=None):
    """Cheaper first, but accessories, bundles-of-parts and broken items go after the real thing; a cheaper sibling
    model the owner did not name ('Switch Lite' for 'nintendo switch') goes after the plain model; placeholder prices
    (€ 1 'make an offer') go last of all."""
    total = card.get("total") or card.get("price") or 1e9
    title = card.get("title") or ""
    penalty = 0
    if price_is_placeholder(card.get("total") or card.get("price"), ref_price):
        penalty += 4
    bundle = bool(re.search(r"\bbundle|lotto|completa|completo|con \d|\+ ?\d|\+ (?:\d+ )?(?:giochi|games|controller|joy)|set completo|in scatola|boxata", title, re.I))
    if ACCESSORY.search(title) and not ACCESSORY.search(name) and not (bundle and _has(item_words(name)[0], title.lower()) if item_words(name) else False):
        penalty += 2                                                  # "Xbox + 2 controller bundle" is the console with extras, not a controller
    if GAME_WORDS.search(title) and not GAME_WORDS.search(name) and re.search(r"\b(switch|ps[345]|playstation|xbox|wii|3ds|nintendo)\b", name, re.I) \
            and not (bundle and re.search(r"\bcon \d+ (?:giochi|games)|\+ ?\d+ (?:giochi|games)|with \d+ games", title, re.I)):
        penalty += 2                                                  # "Nintendo switch zelda" at € 30 is the game, not the console; "PS5 con 2 giochi" is the console
    fl = floor_price(name)
    if fl and isinstance(total, (int, float)) and total < fl:
        penalty += 2                                                  # a working Xbox Series X is never € 27: a game or a part, whatever the title
    tw = title.lower()
    fams = set()
    for fam, pat in (("xbox", r"\bxbox\b|\bseries [sx]\b"), ("ps", r"\bps[345]\b|\bplaystation\b"), ("switch", r"\bswitch\b|\bnintendo\b"), ("pc", r"\bpc\b|\bsteam\b")):
        if re.search(pat, tw):
            fams.add(fam)
    if re.search(r"\b(xbox|ps[345]|playstation|switch|nintendo)\b", name, re.I) and len(fams) >= 2 and not bundle:
        penalty += 2                                                  # "Stray Xbox series X one S / PS5" names two families: a game that runs on both
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
                it["_seen"], it["_min"] = 0, None
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
                        it["_seen"] += 1
                        pr = c.get("total") or c.get("price") or 0
                        if pr and (it["_min"] is None or pr < it["_min"]):
                            it["_min"] = pr
                        if it.get("max") and pr > it["max"]:
                            if rank_key(c, it["name"], None)[0] == 0 and not price_is_placeholder(pr):
                                it.setdefault("_over_cap", []).append(pr)                 # real ones over the cap: the owner wants to know where they start
                            continue
                        if s == "facebook marketplace" and not city_ok(c, city):
                            continue
                        found.append(c)
                ref = typical_price(found, it["name"])                                  # what the item really costs used (clean matches only)
                found.sort(key=lambda c: rank_key(c, it["name"], ref))
                clean = [c for c in found if rank_key(c, it["name"], ref)[0] == 0]
                near = [c for c in found if rank_key(c, it["name"], ref)[0] in (1, 2)][:3]   # a variant / accessory / game: shown apart, never as 'best'
                best = clean[:per_item]
                it["_near"] = bool(near) and not clean
                over = sorted(it.get("_over_cap") or [])
                if over:                                                                 # "starts around": the cheapest real one, but not a lone outlier — the second-cheapest when there are several
                    it["_min_clean"] = over[0] if len(over) < 3 else over[1]
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
                results.append({"item": it, "best": best, "near": near, "n_found": len(found), "n_clean": len(clean), "ref": ref})
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

    @staticmethod
    def nothing_line(it, sites, notes, long=False):
        """Why an item came back empty, in words the owner can act on — never a bare 'nothing found'."""
        answered = [s for s in sites if s not in notes]
        blocked = [s for s in sites if s in notes]
        cap = f" under € {it['max']}" if it.get("max") else ""
        seen = it.get("_seen", 0)
        if it.get("_near"):
            why = f"only look-alikes on {', '.join(answered)} — games, accessories or a different model (listed below as “close, but not it”)" + (f"; real ones start around € {it['_min_clean']:.0f}" if it.get("_min_clean") else "")
            return f"nothing{cap}: {why}." + (f" Say “watch it” and I tell you when a real one appears{cap}." if long else "")
        if not answered:
            why = "none of the sites answered (" + "; ".join(f"{s}: {notes[s].split(': ', 1)[-1][:60]}" for s in blocked) + ")"
        elif seen and it.get("max"):
            why = f"{seen} listing(s) matched but all cost more than € {it['max']} on {', '.join(answered)}" + (f"; real ones start around € {it['_min_clean']:.0f}" if it.get("_min_clean") else "")
        elif seen:
            why = f"{seen} listing(s) had the words but none looked like the real item (accessories, games or parts) on {', '.join(answered)}"
        else:
            why = f"no listing with those words on {', '.join(answered)}" + (f" ({', '.join(blocked)} could not be searched)" if blocked else "")
        tip = ""
        if long:
            if it.get("max") and seen:
                tip = f" Try a higher limit, or say “watch it” and I tell you when one appears{cap}."
            elif len(item_words(it["name"])) >= 3:
                tip = " Try fewer words (the model name only), or a synonym — private sellers write titles their own way."
            else:
                tip = " It may simply not be for sale second-hand right now — say “watch it” and I check every 15 minutes."
        return f"nothing{cap}: {why}." + tip

    def summary(self, results, notes, sites, secs):
        out = []
        for r in results:
            it = r["item"]
            if not r["best"]:
                out.append(f"• {it['name']}: " + self.nothing_line(it, sites, notes))
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
                sym = {"USD": "$", "GBP": "£"}.get(b0.get("currency") or "EUR", "€")
                where = " · ".join(x for x in (b0["site"], b0.get("condition") or "", b0.get("location") or "", ("new, from a shop" if b0["site"] in NEW_SITES else "")) if x)
                rows.append((it["name"], f"{sym} {p:.2f}" if isinstance(p, (int, float)) else "—", where, b0.get("url", "")))
            else:
                rows.append((it["name"], "—", self.nothing_line(it, sites, notes), ""))
        d.glance("At a glance — best price per item", rows)
        if any(s_ in NEW_SITES for s_ in sites) and any(s_ in USED_SITES for s_ in sites):
            d.section("Used vs new", "Vinted / Subito / Wallapop / Facebook = private sellers, second-hand. AliExpress / Banggood / DHgate / Temu / Shein = shops, new, "
                      "usually shipped from China (1–4 weeks; customs above € 150). Each card says which.")
        for r in results:
            it = r["item"]
            d.section(it["name"] + (f" (max € {it['max']})" if it.get("max") else ""),
                      f"{r['n_found']} matching listing(s) seen; typical used price around € {r['ref']:.0f}." if r["ref"] else self.nothing_line(it, sites, notes, long=True))
            cards = [(c, False) for c in r["best"]] + [(c, True) for c in (r.get("near") or [])]
            near_header_done = False
            for c, is_near in cards:
                if is_near and not near_header_done:
                    near_header_done = True
                    d.section("Close, but not it", "Same words, different thing — a game, an accessory or another model. Here so you can judge; never counted as the best.")
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
WATCH_FILE = config.STATE_DIR / "watch.json"


class Watcher:
    """Re-checks the marketplaces for the owner's items: newest listings + cheapest-first, remembers what it has seen,
    and speaks only when a new listing beats the current best for an item (same rules: match, cap, penalties).
    Saved to state/watch.json after every round, so a restart of the bot resumes the watch instead of forgetting it."""

    def __init__(self, hunter, items, sites, results=None, until=None):
        self.h = hunter
        self.items = items
        self.sites = [s for s in (sites or ("vinted", "subito")) if s in markets.SEARCH] or ["vinted", "subito"]
        self.best = {}
        self.seen = set()
        self.until = until
        self.started = time.time()
        for r in results or []:
            if r.get("best"):
                self.best[r["item"]["name"]] = r["best"][0]
            for c in r.get("best") or []:
                self.seen.add(c["url"])
        self.rounds = 0
        self.found = 0

    # ---- persistence -----------------------------------------------------------------
    def save(self):
        try:
            WATCH_FILE.parent.mkdir(parents=True, exist_ok=True)
            best = {k: {kk: vv for kk, vv in v.items() if kk not in ("image", "facts")} for k, v in self.best.items()}
            items = [{k: v for k, v in it.items() if not k.startswith("_")} for it in self.items]
            WATCH_FILE.write_text(json.dumps({"items": items, "sites": self.sites, "best": best, "seen": sorted(self.seen)[-2000:],
                                              "until": self.until, "started": self.started, "rounds": self.rounds, "found": self.found}, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    @classmethod
    def load(cls, hunter):
        """The saved watch, or None when there is none / it is over."""
        try:
            d = json.loads(WATCH_FILE.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not d.get("items") or not d.get("until") or d["until"] <= time.time():
            return None
        w = cls(hunter, d["items"], d.get("sites"), until=d["until"])
        w.best = d.get("best") or {}
        w.seen = set(d.get("seen") or [])
        w.started = d.get("started") or time.time()
        w.rounds = int(d.get("rounds") or 0)
        w.found = int(d.get("found") or 0)
        return w

    @staticmethod
    def clear():
        try:
            WATCH_FILE.unlink()
        except Exception:
            pass

    def left(self):
        return max(0, int((self.until or 0) - time.time()))

    def status(self):
        names = ", ".join(i["name"] for i in self.items)
        return (f"👀 Watching {', '.join(self.sites)} for {names} — {self.left() // 3600} h {self.left() % 3600 // 60} min left, "
                f"{self.rounds} round(s) so far, {self.found} better deal(s) found. Say 'stop watching' to end it.")

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
                            if cur is None and key[0] == 0:
                                self.best[it["name"]] = c
                                better.append(f"🔔 First real listing for {it['name']}: {DealHunter._line(c)}\n{c['url']}")
                            elif cur is not None and key < rank_key(cur, it["name"], ref):
                                self.best[it["name"]] = c
                                better.append(f"🔔 Better deal for {it['name']}: {DealHunter._line(c)}\n{c['url']}")
        self.h.T._release_page()
        self.found += len(better)
        self.save()
        line = f"watch round {self.rounds}: {checked} result page(s) re-checked, {len(better)} better deal(s)"
        return better, line


DealHunter.WATCH_EVERY = 900          # seconds between watch rounds (15 min): polite to the sites, fresh enough for used goods


def _watcher(self, items, sites, results=None, until=None):
    w = Watcher(self, items, sites, results, until=until)
    w.save()
    return w


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
