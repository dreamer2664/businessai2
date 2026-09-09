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

## dropship.kdw (pack #3, night marathon item 8) — SEED (build on PC)

| source | bulk in | kept | what |
|---|---|---|---|
| 37 dropshipping guides (dodropshipping, Shopify blog, Zendrop, AutoDS, Spocket, CJ, SaleHoo, Doba, Dropship.io, europa.eu VAT) | 0.85 M chars | 69 % | starting out, suppliers compared, winning products, margins & taxes, TikTok/FB ads, private label & POD, mistakes |
| **total** | **0.85 M chars (~190 pages)** | **0.59 M chars, 2,181 passages** | |

Seed verified in the sandbox (fetch+trim work, 36/36 questions grounded in the passages);
the `.kdw` needs the C engine, so it builds on the PC:

```sh
python3 packs/web_fetch.py packs/sources/web_urls_dropship.tsv ~/.cache/bai/web3/web.tsv
python3 packs/trim.py ~/.cache/bai/web3/web.tsv ~/.cache/bai/ext_dropship
python3 packs/build_pack.py ~/.cache/bai/ext_dropship release/packs/dropship.kdw
python3 engine/scripts/score_pack.py tests/dropship.txt release/packs/dropship.kdw
```

Growing it across sessions (the feed): `python3 packs/feed_add.py packs/sources/web_urls_dropship.tsv <ext_dir> <url>... [--topic suppliers]`
fetches + trims + appends (renumbered aids) and extends the TSV; rebuild after. Offline proof:
`python3 engine/scripts/score_dropship.py` (list + question + grounding + feed checks). Browser-only
candidates for later feeds (403/thin for the plain fetcher): help.shopify.com IOSS/OSS pages,
usadrop winning-product guide, easync beginner platforms, bigbuy.eu guides.
