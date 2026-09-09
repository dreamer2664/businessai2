# Marketplace readers (Vinted + subito.it deep, Facebook waters-only)

When you name a marketplace ("find me cork slippers **on vinted**"), I search
that marketplace directly instead of going through a search engine — then read
each listing deeply: price, size, brand, condition, seller + feedback, shipping,
description. Everything is read-only: I never buy, bid, message sellers, or log in.

## Vinted: confident coverage (measured live 2026-09-09)

What I measured, politely (4 s gaps, ~10 hits total): Vinted serves its catalog and item
pages to a plain visitor (200, DataDome present but not challenging a normal headless
Chromium), and the page loads its own JSON (`/api/v2/catalog/items`, `/users/{id}`,
`/user_feedbacks`, `/items/{id}/shipping_details`) with the anonymous cookie the first
page-view sets. Their robots.txt allows `/` and `/items` for everyone; `ai-input=yes`,
`ai-train=no` — I read, quote and link, I never train on it.

So a Vinted job now reads, in order:

1. **Search** — the catalog page opens in the browser (status check for walls), then the
   same search through the page's own JSON: title, price, **total with buyer protection**,
   brand, size, condition, seller login. Your `max € N` goes into the search itself.
   If the JSON is shy (401/403/429 → back-off), the 2026 DOM cards are parsed instead
   (the `title` attribute carries brand / condition / size / prices); old-layout JSON and
   bare links remain as the last fallbacks.
2. **Item** — the app-router page (`self.__next_f.push` stream) → attributes (brand, size,
   condition, colour, material, upload age), description, seller name + feedback count,
   price, availability (reserved / hidden), plus JSON-LD; text fallback for everything.
3. **Seller** — `/users/{id}`: city + country (**ships from**), feedback split (👍/👎,
   % positive), items for sale, last active, verified via (email/google/facebook), holiday,
   Pro/business flag. Then the last 12 feedback lines, which become "what buyers say".
4. **Shipping** — `/items/{id}/shipping_details` when the page shows the logged-out
   placeholder ("da 0,00 €").

Verdicts know it is a marketplace: a private seller gets no "no social page" / "no
materials" penalty, 20+ feedbacks count as seasoned, "no feedback yet" and
reserved/sold listings are flagged. Condition words in it/en/fr/es/de map to one scale.

Live result (sandbox, 40 s, 3 listings): every fact above filled for all three sellers,
buyers' words quoted, the € 20 limit applied. Fixtures for the tests are the real pages
captured that day with sellers anonymised (`tests/market/vinted_*_live.html`, `vinted_*.json`).

## subito.it: same treatment (measured live 2026-09-09)

Search pages open fine for a plain visitor and carry `__NEXT_DATA__` with the whole ad
list (title, price, town + province, condition, size, brand, TuttoSubito cost, date,
private/company). Item pages are JS-rendered (plain HTTP → 403; the browser is fine):
JSON-LD gives price + description, the visible labels give the rest — *Dati Principali*
(condition, size, brand), the seller card (first name, rating x/5, "Pubblica da <month year>"),
*Modalità di consegna* (TuttoSubito from € N, delivery 2–6 working days), "Il venditore
dichiara che il bene è originale". A listing without a price stays "not stated" — the
€ figures of the banners around it are never borrowed. Private sellers show only a first
name, so I never search the web for "reviews" of them (that would pin strangers' words on
them); the rating and the account age carry the verdict.

Live result (sandbox, 36 s, 3 listings): all facts filled, the € 20 limit applied.

## Politeness (always on)

- At least **4 seconds** between hits on the same site.
- After a bot check / block: back off **30 s → 1 min → 2 min** … up to 10 min,
  then leave the site alone. I never hammer, never retry through a wall.

## Stealth + proxy (optional, off by default)

In `.secrets/env`:

- `BAI_STEALTH=1` — rotate the browser's user agent, hide the automation flags
  sites check for. Plain reading, just less obviously a bot.
- `BAI_PROXY=http://user:pass@host:port` — route the browser through your
  proxy (rarely needed; only if a site rate-limits your home IP).

## Facebook: waters-only, on purpose

Facebook Marketplace needs a login, and I never log in by myself. When a job
touches Facebook I stop at the shore and tell you: send me the listing text,
or log in on my live screen and I'll read it with you. No bypass is ever attempted.

## Limits

- Sites restyle their pages; my readers use the embedded data first and the
  visible text as fallback, so a restyle degrades instead of dying — and the
  tests below catch it.
- eBay/Amazon/Etsy/depop/wallapop: generic reading only (no deep reader yet).

Offline proof: `python3 engine/scripts/score_markets.py` (37/37 anywhere,
40/40 where a browser is installed) · `timeout 280 python3 engine/scripts/score_sellers.py` (34/34, PC).

## Walls and the listing card (2026-09-10)
- `state/walls.json` — who walled me lately. `/walls` to see it; `/walls forget [site]` to reset. Walled hosts go last, twice-walled hosts are skipped for a while, a clean read forgives.
- `agent/listing.py` — the product page's own JSON-LD / Open Graph data is the first source of the card; regexes only fill the gaps.
