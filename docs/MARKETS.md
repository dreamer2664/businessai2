# Marketplace readers (Vinted + subito.it deep, Facebook waters-only)

When you name a marketplace ("find me cork slippers **on vinted**"), I search
that marketplace directly instead of going through a search engine — then read
each listing deeply: price, size, brand, condition, seller + feedback, shipping,
description. Everything is read-only: I never buy, bid, message sellers, or log in.

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

Offline proof: `python3 engine/scripts/score_markets.py` (17/17 anywhere,
20/20 where a browser is installed) · `timeout 280 python3 engine/scripts/score_sellers.py` (34/34, PC).
