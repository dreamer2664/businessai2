# Business AI — project plan (v0, 2026-09-06)

Goal: an AI that runs an online (dropshipping) store end to end — researches
products and suppliers, sets up and maintains listings, handles customer
messages and social media, reports to the owner and asks questions via phone.

## Principles (carried over from kdr-brain)
- Score-driven: every capability has a test set; nothing ships that lowers a score.
- Frugal: every knowledge pack and model has a size budget — bulk in, filler out.
- Restorable: GitHub is the source of truth; one script rebuilds everything.
- Owner in the loop: money, public posts and customer-facing messages need
  approval until scores earn autonomy.
- Never defeats CAPTCHAs/logins (those go to the owner's phone); uses official
  platform connections (APIs) where they exist — puppet browsers get store and
  social accounts banned.

## Architecture — three parts
1. Library — knowledge packs (KDRW format + wiki_pack pipeline from kdr-brain):
   e-commerce & dropshipping, marketing & copywriting, platform manuals
   (Shopify / WooCommerce / Etsy / Meta / TikTok), customer service, EU/Italian
   consumer rules. Each pack ≤ ~100 MB, scored with 50 questions.
2. Planner — the "thinking" model. Default: hybrid (local model for knowledge
   and routine + paid online model for hard planning steps), swappable like
   composer.gguf. Fully-local option needs a machine with 8–16 GB RAM.
3. Hands — tools: controlled browser (open tabs, read page as text, click/type
   by element name, screenshot on demand), files/notes, task list & memory,
   Telegram bot (two-way phone line), store platform connection; later:
   vision + desktop/cursor control.

## Milestones (one per session; each has a score set and a size budget)
0. ✅ Home & skeleton — new repo, install script, Telegram line. (runs on the owner's Windows PC via WSL)
1. ✅ Knowledge pack #1 — business.kdw 5.7 MB, 52/55 on tests/business.txt; hard test banks collected in tests/banks/ (to be sat alone once it has a browser).
2. ✅ Eyes & hands v1 — own headless browser (agent/browser.py: tabs, numbered page text, click/type,
   screenshots, CAPTCHA/login walls detected and never passed, buy/pay/post clicks refused); read-only tasks
   /research /compare /summarize (tests/browse.txt 18/19); offline exam solver (agent/mcq.py) 57–60 % on the
   440-question marketing bank, 87 % on the half it is confident about.
   + Live screen (agent/viewer.py): local web page with screenshot + plain-words step log, /screen & /watch on Telegram,
   visible Chrome window where a display exists (BAI_HEADED).
3. ✅ Memory & a thinking model — local llama.cpp + Qwen2.5-1.5B (agent/planner.py, starts/stops itself, ~1.3 GB RAM
   only while thinking); plain-language understanding (ask / research / summarize / compare / chat); answers written in
   its own words from evidence with sources; agent/memory.py: notes (state/notes.jsonl), to-do, learning goals with
   self-study when idle (≤6 runs/day), daily report at 20:00. Exam: 27/30 = 90 % (retrieval alone 18/30). Warm-up ladder (visit/find/refuse/watch/ask) 14/14.
   Video 'watching' = captions → summary (agent/video.py). Static llama-server on the Release; 3B model on ≥ 6 GB RAM.
   Bulk-feed → trim → pack (agent/learn.py): notes are digested into one-sentence facts (quality gate, de-dup), folded
   into release/packs/learned.kdw (~40 KB / 100 facts, cap 5000) which the brain searches alongside business.kdw.
4. ✅ Social posts (practice) — agent/social.py: /post <platform> <topic> drafts a post within the platform's caps,
   owner taps Approve / Edit / Redo / Reject; nothing is ever published by itself (no channel connected yet).
5. ✅ (practice channel) Customer messages — agent/inbox.py: every message is classified (11 kinds), answered with a
   draft that obeys the store policy (state/policy.json, edit with /policy), checked by hard rules (no invented
   numbers, no status/tracking claims, no discounts, no promises, defer product/shipping facts the policy does not
   contain, escalate legal/chargeback/injury/data/press), and sent to the owner's phone with Approve / Edit / Reject.
   Approved or edited text goes to state/outbox.jsonl — nothing is ever sent by itself. Score: tests/inbox.txt 22/23.
   Channel "owner": forwarded/pasted customer messages → draft → tap → copyable final text. Edits teach greeting, length
   and sign-off (style.json), never the facts of another customer; /stats tracks approval per type.
   Still to do later: real channels through official APIs (shop e-mail, Instagram/Facebook messaging) and automatic
   sending of a message type only after the owner's approval rate for that type stays ≥ 90 % over 30 replies.
6. ✅ Eyes — agent/eyes.py: a small vision model (LFM2-VL-450M, 310 MB, downloaded once with /eyes install; same
   llama-server, ~550 MB RAM only while looking) answers plain questions about any screenshot; OCR (tesseract, three
   views: normal, white-on-colour buttons, borderless) gives every word its pixel position, menu items split into
   separate targets. /look, photos sent to the bot, thin pages seen through the eyes. Score: tests/eyes.txt 16/16.
7. ✅ Desktop hands — agent/desktop.py: its own virtual screen (Xvfb) or the real one, screenshot → OCR → click on words
   (xdotool), type, keys, scroll; the same danger guard as the browser (money/publish/sign-in clicks need the owner's
   tap), before/after comparison after every click, passwords never typed. Installed by scripts/install_desktop.sh.
8. ✅ Operator — agent/operator.py, command /do <goal>: the see → think → act → check loop that works a screen by itself.
   Browser mode (page elements, exact and fast) and desktop mode (pixels + OCR, any window). Question goals are read
   first (answers only from the screen, figures checked against it), action goals are verified by what newly appeared
   (a "buy" needs an order confirmation, not just "added to cart"); rule-based first moves for search/open goals;
   never repeats a failed click; at most 2 questions to the owner, 12 steps, 15 minutes per goal; refuses login,
   payment and password goals up front; stops at captcha/login walls. Score: tests/operator.txt 10/10 (browser);
   desktop live test 4/4 (price, add to cart with approval, cart count, second product's price).
9. ✅ Bigger tasks on the operator — multi-page goals (`/do <url1> <url2> … | question`: the same fact question per page,
   figures copied exactly incl. price tiers, cheapest/lowest/fastest/… ranked in code, other comparisons summarised and
   checked against the findings), form filling for approval (`fill in the form: name = …, email = …` — typed, never sent),
   cookie banners closed before every look (page + consent iframes; reject preferred), wrong-click recovery (back when a page
   is off-goal; follows the most goal-related link when the thinker names something that is not on the page), rule-based
   first moves (add to cart / buy now / search) so simple goals take 4–17 s. Score: tests/operator.txt 15/15 in 321 s;
   live banners: theguardian.com ("Do not sell or share…"), wired.com ("Close"). A live-site score set is still to do
   (sites change; kept for milestone 10 when the real channels arrive).
10. ✅ Real channels — agent/channels.py: shop e-mail (IMAP/SMTP, any provider) and Facebook Page / Instagram messages
   (Meta Graph API, polled, no public server) feed the same inbox; drafts arrive with **Approve & send / Edit / Reject**
   and the reply leaves through the channel only after the tap (e-mail threaded with the original quoted). Machine mail
   (newsletters, auto-replies, bounces, no-reply) filtered; ledger of seen ids → nothing drafted twice; secrets redacted.
   /channels [check|now]. Score: engine/scripts/score_channels.py 36/36 against a local fake mail server + fake Graph API
   (no account needed). Setup guide: docs/CHANNELS.md.
11. ✅ Practice store — `agent/store.py`: a small shop that really works, served by the agent on the owner's machine
   (127.0.0.1:8095; `/store open`): catalogue of 5 eco home-goods with options, cart, checkout with a *practice* payment
   button, order pages, help pages (shipping table, returns, FAQ, contact form → inbox), and an admin panel (basic-auth,
   `/store admin`) with orders, stock, prices, page texts and a change log. Ledger `state/store/store.json`. `/store day`
   lets a practice day pass: simulated visits, orders (stock reserved, shipping by country, no shipping outside the EU),
   deliveries, and 1–2 customer messages that land in the normal inbox as channel "store" and get drafted replies from the
   store's own pages (the agent reads its own shop with the same `/shop` reader). `/store review` makes the agent propose
   what a careful shopkeeper would do — ship paid orders, reorder sold-out / low stock, reprice thin margins (< 55 % gross
   once shipping and fees are counted) — as **proposals**: nothing changes until the owner taps Apply. `/store numbers`:
   visits, conversion, revenue − goods − shipping − fees = profit, best sellers, low stock. Score:
   `python3 engine/scripts/score_store.py [--model]` 27/27 (shop mechanics, ledger, days, proposals, apply/leave,
   restart, own-page reading, operator on the store front, 5 store-customer replies from its pages).
12. Real store — owner handles accounts, payments, legal; AI operates with approval gates on money and public posts.

## Phase 2 — "an assistant you talk to" (owner's brief, 2026-09-08)
The owner's words, condensed: no more relying on commands — understand what I wrote, make a to-do list to fulfil it, then
do it; hand me a finished document (links, pictures, a walk-through of each option), not a page dump; research sellers
properly (their page, reviews, social media, complaints, shipping, origin, materials) and offer to add good ones to the
shop; be prepared on social media before it goes live; respect my pace ("I need it in 10 minutes" → a visible timer and
a reminder, not a stop; "I'm away 5 hours, take it slow" → use the time, then study, brainstorm, troubleshoot); look at the
screen, not only the text (a "never worn" listing whose photo shows damage); try CAPTCHAs before giving up and if stuck
try something else; sign up where useful with its own account (credentials in the secrets file, never in git or logs;
fetch verification codes from its own mailbox by itself); keep its library in its own Google Drive (PDFs it found, trimmed
to the information-dense ones; business ideas from short-form video); learn to build websites by itself and auto-train by
picking random places on Google Maps and building them a site, with a short notification per site; and above all think
better — "it doesn't even know what it's doing".

Ground rules that do not change: everything free; the owner is in the loop for money, public posts, customer messages,
account creation the first time on a platform, and anything a CAPTCHA blocks twice; official APIs for Google/Meta (robot
logins to Google get the account locked); counterfeit goods ("reps") are never sourced or listed — the *research skill* is
trained on genuine products.

Milestones (one per session, each with a score set; earlier scores must not drop):
13. Understanding & planning — free text → intent + a written to-do list the owner sees and can edit ("plan first, then
    do"); pace words ("quick", "10 minutes", "take it slow", "I'm away 5 hours") set a deadline/budget shown on the live
    screen and in /status; the AI narrates what it is doing and why in plain words (no more "robotic" one-liners).
14. Deliverables — research produces a document (HTML/Markdown with pictures and links, per-option walk-through, sources)
    saved to its library and sent as a file; "seller check" skill (page + reviews + social + shipping + origin + materials
    → reliability verdict); with the store open: "add this to the shop?" proposal with price and shipping.
15. Eyes on listings — the vision model judges photos, not only text (condition, damage, mismatch with the description);
    CAPTCHA attempts (checkbox, simple text/image puzzles, retry with a fresh page) with a one-tap fallback to the owner.
16. Own accounts — sign-up flow with its own e-mail (secrets), verification codes fetched from the mailbox (IMAP), a
    credential vault (encrypted at rest, never logged), owner confirms the first sign-up per platform.
17. Own library — Google Drive via the official API (owner does a 10-minute one-time setup): upload research docs, PDFs,
    websites; long idle time = read PDFs, keep the dense ones, note business ideas from videos (incl. the two the owner sent).
18. Social media readiness — dry runs on each platform's real posting screen (practice account), interface maps, scores.
19. Website builder — brief → complete static site (pages, copy, images, contact form) scored by a rubric; auto-training on
    random Google Maps places; each site saved to Drive + one-line notification.
20. Smarter thinking — a reflection loop (what am I doing, what do I know, what is missing, what next), self-critique
    before delivering, and a bigger local model when the machine allows.


## Defaults chosen (override anytime)
- Engine: hybrid (local + paid model for hard steps), swappable.
- Autonomy: automatic for research and drafts; ask for money, public posts,
  customer messages.
- Store platform: decided at milestone 4 (a Shopify development store is free
  for practice; WooCommerce is free software on own hosting).

## Needed from the owner before session 0
- New GitHub repo name + token (same setup as kdr-brain).
- A Telegram account (for the bot).
- Where it lives 24/7: spare PC (ideally ≥ 8 GB RAM) or a small rented server
  (~€5–15/month). The sandbox used for development is wiped between sessions.
- Monthly budget for the paid thinking model (€0 = fully local: slower, bigger
  machine needed).

## What moves over from kdr-brain
- C engine (brain.c, wiki.c, chat.c, main.c), web chat UI, scoring scripts
  (score.py / eval_*.py), pack builders (pack.py, wiki_pack.py), CI/release
  scripts (push_to_github.sh, upload_release.sh, restore.sh).
- Not the Kingdom facts (data/passages.json, tests/kingdom.txt).

## Feeding log (bulk in → trimmed → kept; the brain must not get "stupider": all earlier scores re-run)
- 2026-09-07 pack #2 `operations.kdw`: 113 docs, 1.71 M chars in → 1.14 M kept (67 %), 1.7 MB. Customer service, returns &
  chargebacks, shipping & inventory, pricing/payments/metrics, EU seller rules. tests/operations.txt 39/41; business.txt still 52/55.

## Hardening log (abilities, not knowledge — the scores above must not drop)
- 2026-09-07 `/do` on real shops. What broke and what was changed (all in `agent/operator.py` + `agent/browser.py`):
  bot-check walls (DataDome, Cloudflare Turnstile) and site error pages are recognised and reported in seconds, never attempted;
  an expired/redirected product link is reported instead of guessed; the product search box is chosen by meaning (not the
  store-locator / newsletter box); cookie walls closed in it/de/fr/es/nl (reject-all preferred); a click that changes nothing
  opens the link's own address; a question's page with a link named for the goal (Returns, Diritto di recesso, About us) is
  followed without a model call and never counted as a wrong turn; goal words are translated for page excerpts and link
  matching (returns → resi/recesso, shipping → spedizione/consegna …); an English answer read from an Italian page is accepted
  when its figures are on the page; a figure taken from a "maximum / from / free above" sentence is reported with the page's
  exact words. Small machines: lean Chromium (one renderer, no images/fonts) and both cores for the thinking model.
  Operator test set still 15/15 (now 170 s instead of 321 s); new live set tests/live.txt 10/10.
- 2026-09-07 **Customer replies from the shop's own pages** (`agent/shopfacts.py`, `/shop <address>`). The browser reads the
  shop's start page and follows its help / shipping / returns / contact / FAQ links (same site, ≤ 7 pages; usual addresses
  such as /faq, /shipping, /pages/returns are tried when the start page links to none), keeps every sentence that states a
  customer-relevant fact (delivery times, costs, destinations, return rules, contact ways, payment, where the shop is) word
  for word with its page, and stores the sheet in `state/shopfacts.json` (re-read by itself once a week when idle). No model
  is involved in reading. Drafts get the matching sentences as "facts from the shop's own website"; the safety checks accept
  figures, time spans and destinations that stand on those pages (a reply may say "4–6 business days to Germany" when the
  shipping table says so) and still flag everything else. New score set tests/shopfacts.txt (8 questions only the shop's
  pages can answer; run `python3 engine/scripts/score_shopfacts.py`, `--nofacts` shows the baseline without the pages).
- 2026-09-07 **Product questions from the product pages** (same `/shop` read). From the start page and its "Shop / all
  products" listing the browser opens up to 12 product pages and keeps, per product: name, price, availability, the option
  lists (colours, models), and the detail/spec lines word for word (tables become "Battery: 2000 mAh, up to 8 hours…").
  A customer message is matched to a product by its name words ("the lamp", "cork phone case"; "phone number" is not the
  phone case). The reply writer gets that product page; the rules then check every figure and measurement against the page,
  catch a "yes" where the page says no ("no iPhone 15 Pro Max version", "no power adapter included"), and catch any claim
  about a thing the page never mentions (oven-safe?) — only "I will check with the owner" passes. When the model's draft
  fails, the safe template quotes the page's own line(s). Shop facts also take precedence over the generic policy defaults
  (no more "7-15 business days" when the shipping table exists), and "yes we ship to the UK" is caught when the shop says
  not yet. tests/shopfacts.txt grew to 16 (8 product questions incl. two traps); practice pages catalogue.html,
  product_mug.html, product_lamp.html, product_case.html.
- 2026-09-07 **Milestone 11 shipped** (see above). Design choices: the practice store is *served by the agent itself*
  (no account, no third-party sandbox, works offline, restorable from the JSON ledger); customers are simulated
  deterministically per day so scores are repeatable; the AI's actions are all proposals with a why-line, applied only by
  a tap — the same gate the real store will use; the agent reads its own shop through the browser like any other shop, so
  the customer-reply path is exactly the real one.
- 2026-09-07 **Practice weeks** (`engine/scripts/practice_week.py [days] [--fresh]`: a whole week of simulated customers,
  every reply drafted by the thinking model and judged by rules, the "owner" applying proposals). What the first week
  broke and what changed:
  * *"Where is order 51002?"* → the AI wrote "I will check and send the tracking within one business day" although it
    runs the order system. Now `Store.order_facts()` puts the real ledger status in front of the writer (paid / shipped +
    tracking / delivered / cancelled), the safety checks flag "shipped" claims on unshipped orders, invented delivery
    dates, missing tracking numbers and "I will check the order", and the fallback templates answer from the ledger.
  * An order that is still unshipped after 2+ days gets an apology + "the owner has been asked to ship it today" and a
    *ship* proposal is opened for the owner at once; a cancel request on an unshipped order opens a *cancel* proposal
    (reply: "will be cancelled and refunded in full — the owner confirms"); on a shipped order the reply says it cannot be
    cancelled any more (return within 30 days, € 4,90). A damage report on a shipped/delivered order opens a *refund*
    proposal. Nothing changes until the owner taps.
  * A stranger asking about someone else's order number gets nothing but "write from the address used for the order".
  * "Is X in stock?" is answered from the shop's live stock (units, or sold out → "I will ask the owner when it is
    back"); "in stock" claims about sold-out items are flagged.
  * Bug: two proposals created in the same millisecond shared one id, so the owner's second tap said "no longer open".
  * False flag: a compliment ("Love the case") was flagged for the word "love" not being on the product page.
  * Week 2–3 findings: a customer writing without an order number is matched by e-mail address (one live order → answered
    for it; several → "which one?"; none → "send me the number, it starts with 51"); a mistyped number → "cannot find
    it"; "change the colour / address before it ships" is a change (possible while unshipped, owner does it), not a
    cancellation; "cancel — I ordered the wrong model" is a cancellation, not a damage report; "one piece is missing" is
    a damage report; the model's second-person echo of the question ("Can you still return…?") is stripped; refunds and
    cancellations now cost real money in the numbers (fee kept by the gateway; a refunded parcel also loses goods + postage);
    reorder quantities follow last week's sales; a price proposal the owner rejected is not repeated; approved replies are
    filed on the order. Practice week score: 10/10 replies judged good (`state/week3.log`).
  Score: `score_store.py` 40 model-free checks + 8 model replies (**41/41** with `--model`, ~6.5 min).

### Phase 2 status (2026-09-08)
| milestone | state | score |
|---|---|---|
| 13 understanding & planning (brief, pace, plan → Go/Change/Cancel) | ✅ | brief 30/30 |
| 14 deliverables + deep seller check (document with pictures/links, store proposal); 'is this shop legit? <link>' checks that shop; the owner's conditions (max €, only Italian, ships from …) — planned or said mid-job — decide the verdicts | ✅ | sellers 34/34 |
| 15 eyes on listings (real photos, describe-then-judge) + CAPTCHAs in everyday work (try → skip → one tap) | ✅ | eyes on listings 26/26 · walls 14/14 |
| 16 own accounts / credential vault / mail codes | ✅ | accounts 12/12 |
| 17 Drive library: PDF density judge, video ideas, long courses in chapters (lesson picker keeps rules, drops brags), brainstorm, quiet-time loop | ✅ | study 20/20 |
| 18 social readiness: practice network + rehearsals (limits, photos, comments, replies) | ✅ | rehearsal 19/19 |
| 19 website builder + auto-training (OpenStreetMap places) + Drive "Websites"; the owner's own words (since 1962, sourdough, delivery to offices) drive the copy; unknown kinds keep their label; Italian and English sites ("in italiano", "bilingual", "make it in Italian too" → language folder + menu switch) | ✅ | sites 41/41 |
| 20 thinking: journal, interruptions, reflection, lessons, queue instead of 'busy', everyday talk (to-do in plain words, clock, opinions, translations, Italian shop basics, EU return rules, shop names, descriptions from facts, launch list, Gmail codes, 'off to lunch' → study hour); mid-job manners (praise/status/'take your time'/'don't forget'/'when done, …'); research reads what the owner adds mid-job; brain refuses off-topic passages | ✅ | mind 42/42 · talk 56/56 · docs 20/20 |
| 14b research/compare deliver documents too (summary, one card per page with picture + link + points) | ✅ | practice day 27/27 |
| 12 real store | ⏳ awaits platform choice (end of the road, per owner) | — |

VERSION 1.8 (2026-09-08): documents for research/compare, eyes on listings with real photos, CAPTCHA try-then-move-on, no more 'I'm still busy' (queue), stop/hurry inside page loops, everyday talk (pricing, shipping sanity, recap, menu, customer words → draft).

VERSION 1.9 (2026-09-08): the assistant's manners — link-only seller checks, owner's conditions applied to verdicts, plain-words to-do list, clock/opinions/translations, Italian shop basics (Partita IVA, forfettario, INPS, OSS) and EU return rules, shop names, product descriptions from facts only, launch checklist, Gmail code fetch, 'off to lunch' quiet hour, resend/upload last document, store numbers, 'what did we decide', 'why so slow'; mid-job: praise/status/'take your time'/'don't forget'/'when done, …' handled properly, quick questions answered live; research covers what the owner adds mid-way (➕ pages); brain quality gate; ▶ Go no longer repeats the plan; course-note picker.
VERSION 2.0 (2026-09-08): the shop grows extras and a designer — discount codes, gift wrap and a shop notice by chat (proposals, undo, checkout + order page + labels follow; customers asking for a code get the live one; the notice is repeated in every reply while it is up); shipping labels as PDF with gift receipts; logos (three styles, PNG + SVG) and social banners made in-house and put on the shop header or posted to the Facebook Page through the official API after the tap; the auto-reply switch explained and listed in plain words; more ledger questions (best day, stock money, run-out dates, week vs week, ship speed, loss makers, last order). Talk 460/460, store 40/40, mind 42/42, brief 34/34, inbox 23/23, practice week 10/10.

## 2026-09-09 night marathon, item 1 (fallback contact) — done
- New agent/fallback.py (Gmail poll+reply, allowlist, watchdog, backup bot) + core wiring (idle hook, /fallback, status line, 401 watchdog) + OWNER_EMAILS/FALLBACK_BOT_TOKEN config. Regression: full score sweep matches main baselines exactly (talk 451/460 here vs 460/460 on PC with thinking model; inbox 22/23; browser suites need playwright — all identical on main, zero regressions).

## 2026-09-09 night marathon, item 10 (regression battery) — done
- New engine/scripts/score_all.py (24 suites + practice lane, --fast/--only/--compare, SKIP-clean on env gaps, selftest 5/5). Hardened score_store (browser sections guarded, 35/35 here) + score_shopfacts (graceful SKIP). Fast battery here: 9 PASS, 2 PARTIAL (talk 451/460 = no browser/model, inbox 22/23 pre-existing), 3 SKIP, 0 FAIL.

## 2026-09-09 night marathon, item 7 (queue + budgets + durations) — done
- Mind priority queue (classify/add/next/peek/list/set/clear, persisted), 6 core queue sites converted, /queue command, Pace.over_budget + research/compare guards + idle guards, EN/IT durations + parse_duration. score_queue 20/20. Caught by the battery mid-build: tuple-style queue readers (fixed), drain wording kept stable. Fast battery: 10 PASS, 2 pre-existing PARTIAL, 2 env SKIP, 0 FAIL.

## 2026-09-09 night marathon, item 2 (smarter research) — done
- plan_queries (EN/IT intent aspects), research() multi-query with dedupe + domain cap, _synthesize (agreement + ranked facts, per-page bullets kept), outer-loop budget cut recorded. score_research 19/19 (fake browser). Fast battery: 11 PASS, 2 pre-existing PARTIAL, 2 env SKIP, 0 FAIL.

## 2026-09-09 night marathon, item 4 (YouTube) — done
- Owner overrode API-first: browser-first, no key. InnerTube browse/next are 400/locked and feeds are empty shells, so: extract_trending/comments (rendered-DOM, PC browser) + top_for_topic (search page, live-verified: millions of views parsed) + transcript hardened (429 backoff, 4-track fallback; sandbox caption CDN throttled, PC verifies). score_youtube 12/12. Fast battery: 12 PASS, 2 pre-existing PARTIAL, 2 env SKIP, 0 FAIL.

## 2026-09-09 night marathon, item 8 (pack #3 seed) — done
- 37 verified dropshipping guides (fetch filtered 60 candidates) → 2,181 passages, 0.59M chars, 69% kept. tests/dropship.txt 36 questions, 36/36 grounded in passages. packs/feed_add.py grows packs across sessions (renumbered aids). Term index (5,321 terms, 42KB) makes grounding re-checkable offline. score_dropship 10/10. .kdw build + score_pack run on the PC (needs the C engine).
