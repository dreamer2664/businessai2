# Knowledge packs

A pack is one file (`release/packs/<name>.kdw`) the brain searches when asked a question:
compressed passages + tiny numeric fingerprints for search. Built with the trim-and-pack
pipeline in `packs/`; the raw sources never ship, only the trimmed passages.

## business.kdw (milestone 1) — 5.7 MB, 17,908 passages, 751 documents

| source | bulk in | kept | what |
|---|---|---|---|
| OpenStax *Introduction to Business* (CC BY 4.0) | 1.12 M chars | 61 % | economics, ownership forms, management, finance, marketing basics |
| OpenStax *Principles of Marketing* (CC BY 4.0) | 1.23 M chars | 72 % | segmentation, 4 Ps, pricing, promotion, channels, research, digital |
| OpenStax *Entrepreneurship* (CC BY 4.0) | 1.25 M chars | 60 % | opportunity, business plans, funding, launching |
| OpenStax *Principles of Management* (CC BY 4.0) | 1.08 M chars | 49 % | planning, strategy, decisions, motivation |
| OpenStax key-term glossaries (4 books) | 0.30 M chars | 100 % | 2,239 one-line definitions (densest material) |
| Shopify blog — 213 guides (dropshipping, suppliers, pricing, metrics, ads, social, SEO, email, shipping, taxes, returns, fraud, legal) | 3.78 M chars | 66 % | practical e-commerce & dropshipping how-to |
| **total** | **8.75 M chars (~1,900 pages)** | **5.26 M chars (60 %)** | |

Everything is fetched as clean HTML text — no PDFs, no images, no page furniture. Dropped on purpose:
tables of contents, prefaces, indexes, exercises, case studies, anecdotes/stories, "in this chapter you will…",
link lists, product plugs, image captions, teaser lines, duplicates, and paragraphs with a low share of
informative words (definitions, numbers, mechanisms, steps are kept). Density threshold 5.5 (`packs/trim.py`).

### Scores
- `tests/business.txt` (55 questions, 4 blocks): **52/55** — basics 10/11, marketing 15/16, metrics & pricing 13/14, dropshipping & operations 14/14.
  Misses: law of supply & demand (textbook explains it without the phrase), product life cycle (definition found but lacks stage names), friendly fraud (answer buried in a stats paragraph).
- Coverage probe on the 440-question OpenStax marketing MCQ bank (`engine/scripts/coverage.py`, 100-question sample): the correct answer is present in the retrieved passages **77 %** of the time — that is the ceiling for the exam it will sit later.
- Engine setting: `KDR_WIKI_READK=3` (read the 3 best passages instead of 8): +3 questions, 2.5× faster (0.4 s per answer on 2 cores).

## operations.kdw (knowledge pack #2, 2026-09-07) — 1.7 MB, 4,303 passages, 113 documents

| source | bulk in | kept | what |
|---|---|---|---|
| Shopify blog — 99 guides on customer service, returns/refunds/chargebacks, shipping & fulfillment, inventory, pricing & payments, metrics, checkout, reviews, loyalty | 1.62 M chars | 68 % | how a store is actually run day to day |
| Your Europe (europa.eu) — 14 pages: consumer guarantees & withdrawal right, contract information, GDPR, VAT rules & cross-border VAT, CE marking, selling products in the EU, customs declarations | 0.09 M chars | 70 % | the rules an EU (Italian) online seller must follow |
| **total** | **1.71 M chars (~380 pages)** | **1.14 M chars (67 %)** | |

Same trim pipeline as pack #1 (`packs/trim.py`, density 5.5); sources listed in `packs/sources/web_urls_ops.tsv`.
`web_fetch.py` now falls back to `<main>` when a page has no `<article>` (europa.eu) and accepts shorter eu-law pages.

### Scores
- `tests/operations.txt` (41 questions, 5 blocks): **39/41** on the pack alone — customer service 10/10, returns & disputes 6/7,
  shipping & fulfillment 10/11, pricing/payments/metrics 7/7, EU rules 6/6. Misses: "how to prevent chargebacks" (answer is a list,
  reader returns the heading) and Incoterms/DDP (reader picks the neighbouring DAP term).
- With **both packs** loaded the brain picks the better pack per question by reader confidence × meaning match of the best passage
  (`Brain._quality`; confidence alone let a confident span from an off-topic passage win): business 52/55 (unchanged), operations 38/41.
- Size: +1.7 MB for ~380 pages of material; both packs together 7.4 MB.

### Rebuild
```sh
python3 packs/openstax_fetch.py packs/openstax_books.json ~/.cache/bai/txt     # textbooks → clean TSV
python3 packs/web_fetch.py packs/sources/web_urls.tsv ~/.cache/bai/web/web.tsv         # web guides → TSV
python3 packs/trim.py ~/.cache/bai/txt/*.tsv ~/.cache/bai/web/web.tsv ~/.cache/bai/ext_final
python3 packs/build_pack.py ~/.cache/bai/ext_final release/packs/business.kdw   # embeds new passages, packs
python3 engine/scripts/score_pack.py tests/business.txt release/packs/business.kdw
# pack #2
python3 packs/web_fetch.py packs/sources/web_urls_ops.tsv ~/.cache/bai/web2/web.tsv
python3 packs/trim.py ~/.cache/bai/web2/web.tsv ~/.cache/bai/ext_ops
python3 packs/build_pack.py ~/.cache/bai/ext_ops release/packs/operations.kdw
python3 engine/scripts/score_pack.py tests/operations.txt release/packs/operations.kdw
```

## dropship.kdw (knowledge pack #3, 2026-09-09) — 2.7 MB, 8,313 passages, 176 guides

| source | bulk in | kept | what |
|---|---|---|---|
| dodropshipping.com — 108 guides | | | starting out, suppliers compared (AliExpress, CJ, Zendrop, Spocket, Syncee, SaleHoo, Doba, agents, 3PLs), winning products & niches, margins/markups, TikTok/Facebook ads, print on demand, private/white label, mistakes |
| crosslist.com/blog — 47 guides | | | **used goods & marketplaces**: Vinted, eBay, Etsy, Depop, Poshmark, Mercari, Whatnot, Facebook Marketplace — fees, relisting, cross-listing, photos, pricing from sold listings, reseller taxes |
| Shopify blog — 15 guides | | | high-ticket dropshipping, TikTok Shop, Facebook Marketplace fees, Etsy vs Amazon Handmade, reselling |
| Zendrop, AutoDS, Spocket, CJ, SaleHoo, Doba, Dropship.io — 6 pages | | | supplier platforms in their own words |
| Your Europe (europa.eu) — 6 pages | | | VAT e-commerce, withdrawal right, legal guarantee, CE marking, selling in the EU |
| **total (177 fetched, 176 kept)** | **5.36 M chars** | **1.97 M chars (37 %)** | trim density raised (MAX 600 / MIN 80 chars, filler regex) so 5× the seed material fits in 2.7 MB |

Sources: `packs/sources/web_urls_dropship.tsv` (177 rows; the 9 Shopify slugs that returned 404 and 2 thin europa pages were dropped from the list).
Built **in the sandbox** with the C engine (`release/kdr-brain-lite … embed`: 8,313 passages in 6 min on 2 cores — the seed note
"needs the PC" was wrong, the binary had just lost its executable bit: `chmod +x release/kdr-brain-lite`).

### Scores
- `tests/dropship.txt` (59 questions, 9 blocks — starting out, suppliers, products, money & EU tax, marketing, brand & scale,
  **used goods & reselling, marketplace fees, EU rules**): see docs/SCORES.md for the current figure. The score is honest in one
  specific way: several seed-era questions were rewritten to what the sources actually answer (e.g. "what markup?" → the guides
  say 2.5–3× and a $15–20 floor; "what margin?" → 20–30 % after costs), not loosened.
- With **all three packs** loaded (`Brain.ask`, best pack per question by confidence × meaning match): business 52/55 and
  operations 38/41 — unchanged from the two-pack figures, so the new pack steals no answers.
- Size: business 5.7 + operations 1.7 + dropship 2.7 = 10.1 MB on disk.

### Ship
`dropship.kdw` is an asset on the GitHub Release `latest`; `agent/brain.py RELEASE_PACKS` and `scripts/get_brain.sh` list it, so the PC
downloads it on the next start (`Brain.fetch_missing`, verified byte-identical) — nothing to do by hand.

### Rebuild
```sh
python3 packs/web_fetch.py packs/sources/web_urls_dropship.tsv ~/.cache/bai/web3/web.tsv   # ~4 min, prints "fetched N"
python3 packs/trim.py ~/.cache/bai/web3/web.tsv ~/.cache/bai/ext_dropship
python3 packs/build_pack.py ~/.cache/bai/ext_dropship release/packs/dropship.kdw           # ~6 min
python3 engine/scripts/score_pack.py tests/dropship.txt release/packs/dropship.kdw
python3 engine/scripts/score_dropship.py                                                    # offline: list, questions, grounding, feed
```
Term index for the grounding check: `packs/sources/dropship_terms.txt` (11,012 terms from the trimmed passages; regenerate after a rebuild).

Growing it across sessions (the feed): `python3 packs/feed_add.py packs/sources/web_urls_dropship.tsv <ext_dir> <url>... [--topic suppliers]`
fetches + trims + appends (renumbered aids) and extends the TSV; rebuild after. Browser-only candidates for later feeds
(403/thin/404 for the plain fetcher): help.shopify.com IOSS/OSS pages, usadrop, easync, bigbuy.eu, ebay sellercenter,
etsy seller handbook, wallapop, spocket sitemap, autods post-sitemap (times out).
