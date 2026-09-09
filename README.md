# businessai

An AI that (eventually) runs an online store end to end: product and supplier
research, listings, customer messages, social media — reporting to its owner
and asking questions through Telegram.

**Status: milestone 11 — practice store** (`/store open`): a working shop the agent serves on your machine — catalogue, cart,
practice checkout, admin panel, simulated customers and days — where it ships, reorders and reprices *by proposal* (you tap
Apply) and answers store customers from the store's own pages. Score 40/40. Store extras by chat (all as proposals, undo-able):
**discount codes** (“make a code WELCOME10 for 10 % off”, “which codes are active?”, “switch off the code …”), **gift wrap** at
checkout (“add a gift wrap option at 2.90”), a **shop notice** on every page (“put a notice on the shop saying: …”) that customer
replies repeat while it is up; customers asking for a discount are given the live code. **Design** (`agent/design.py`): “make a logo” → three options (PNG + SVG) from the shop's name and colours; “make a banner for instagram / facebook / story” → the right size, text from the live notice, code or top product; rendered with the same headless Chromium, no paid tools. “post it” → the usual post draft with the picture attached; after your tap a **Facebook** post is published through the official Page API (`pages_manage_posts`), Instagram stays copy-paste (Meta needs a public image URL). Before that, milestone 10 — real customer channels**: your shop e-mail (any provider) and Facebook Page / Instagram messages
are read every few minutes, every real customer message gets a drafted reply on your phone with **Approve & send / Edit /
Reject**, and the answer goes out only after your tap (docs/CHANNELS.md; 36/36 on the channel checks). Before that: milestone 9,
bigger jobs for the operator (`/do` compares several pages, fills in forms, closes cookie banners, 15/15), eyes (vision
model + OCR, 16/16), desktop hands, the see → think → act → check loop; earlier: customer-message drafts 22/23, social post drafts, marketing exam 90 %, browse tasks 19/19, knowledge pack 52/55. Packs: [docs/PACKS.md](docs/PACKS.md). See [docs/PLAN.md](docs/PLAN.md)
for the roadmap and the rules (score-driven, frugal, owner-in-the-loop, no
CAPTCHA-breaking, official platform connections only).

## Layout
```
agent/      the agent: Telegram line, owner check, ask()/notify(), logs   (Python, no dependencies)
engine/     knowledge brain inherited from kdr-brain: C engine, pack builders, scorers
packs/      knowledge pack sources (milestone 1+)
tests/      score sets — every capability has one
scripts/    install.sh, run.sh, service.sh, push_to_github.sh, upload_release.sh, restore.sh
release/    built artefacts (git-ignored; published as GitHub Release assets)
state/      runtime memory + logs (git-ignored)
.secrets/   keys (git-ignored) — template in .secrets.example
```

## Run it (Linux / WSL, free, nothing to install beyond python3) — Windows step-by-step: [docs/INSTALL_WINDOWS.md](docs/INSTALL_WINDOWS.md)
```sh
git clone https://github.com/dreamer2664/businessai2 && cd businessai2
sh scripts/install.sh          # creates .secrets/env — put the bot token + your Telegram username in it
sh scripts/run.sh              # foreground; or: sh scripts/service.sh  (starts at boot, auto-restarts)
```
Then message the bot on Telegram: `/start`, `/status`, `/selftest` (asks you a question with buttons).

Knowledge brain (optional, ~65 MB): `sh scripts/get_brain.sh` downloads the engine + models + packs from the release; after that any
question you send (or `/ask …`) is answered from the business pack with its source.

## Thinking model (planner)
`agent/planner.py` runs a small open model locally through llama.cpp (`sh scripts/get_model.sh` picks Qwen2.5-3B-Instruct on machines with ≥ 6 GB RAM, else Qwen2.5-1.5B; CPU only; the
server is our own fully static 16 MB build from the GitHub Release, so it runs on any x86-64 Linux/WSL). It is started on first use and stopped after 10 idle minutes, so RAM is only used while thinking.
It never answers from thin air: it gets evidence (knowledge-pack passages, page notes, the agent's own notes) and must say
when the evidence isn't enough. Any OpenAI-compatible endpoint can replace it (`BAI_LLM_URL`, `BAI_LLM_KEY`, `BAI_LLM_MODEL`).

## Low-memory machines
Browser and thinking model together need ~2.5 GB. With less, the agent enters low-memory mode automatically: it closes the browser before thinking and reopens it for the next task (slower, but no stalls). `/status` and `state/logs/llm.log` show why the model isn't running, and `sh scripts/get_model.sh --test` / `--build` fix a prebuilt server that doesn't match the machine.

## Memory
**Learning loop (bulk-feed → trim → pack).** Everything it reads (research, page summaries, videos, self-study) becomes a note;
when idle it boils new notes down to one-sentence facts (numbers/names kept, hype dropped, duplicates removed) and folds
them into its own knowledge pack `release/packs/learned.kdw`, searched together with the business pack. `/learned` shows the
latest facts and pack size; `/learned rebuild` forces a rebuild. Budget: ~40 KB per 100 facts, capped at 5000 facts.

`state/notes.jsonl` (everything researched/summarized, with sources), `state/todo.json` (to-do + learning goals).
`/visit <site> | <question>` (or just "open Amazon and tell me the bestsellers") goes to a site and reports what is really on it — answers are checked word-for-word against the page, and empty/login-only pages (YouTube, TikTok) are reported as such instead of guessed.
`/watch <video url or topic>` (or "watch a video about facebook ads and tell me what you learned") reads the video's captions — no download, no login — and reports the concrete claims plus whether the speaker is selling something.
`/goal <topic>` gives the agent a standing learning goal: when idle it studies one new angle per session, at most 6 sessions
a day, and sends a daily report at 20:00. That is the only thing it does on its own.

## Browser (eyes & hands)
`agent/browser.py` drives a headless Chromium: every page is turned into numbered text (`[7] button: Add to cart`), actions
refer to the numbers, and every step is logged in plain words. Built-in rules: never passes CAPTCHAs or logins (it stops and
reports), refuses buy/pay/post/submit clicks unless a task is explicitly allowed to act, blocklist for adult/gambling/banking.
Telegram: `/research <topic>`, `/compare <product>`, `/summarize <url>`, `/exam [n]`. Install: `sh scripts/install_browser.sh`.

## Watching it work (live screen)
Three ways, all free and local:
1. **Live page** — the agent serves its own screen at `http://localhost:8765` on the machine it runs on: latest screenshot
   (refreshes every second), a plain-words log of every step, and a toggle to see the numbered text it actually reads.
   No files are written; screenshots are only taken while somebody is watching. Change the port with `BAI_VIEW_PORT`.
2. **Phone** — `/screen` sends one screenshot; `/watch on` sends a photo after every browser step (`/watch off` to stop).
3. **A real window** — set `BAI_HEADED=1` (or just run where a display exists, e.g. WSLg on Windows 11) and the agent's
   Chrome opens visibly, slowed to 250 ms per action so you can follow the cursor. Without a display it falls back to
   invisible mode automatically. The window stays open between tasks and closes itself after 10 idle minutes.
Try it without Telegram: `python3 -m agent.viewer --demo` (runs a few read-only tasks in a loop).
4. **Google Docs** — with Google connected, every day gets a *day log* Doc (Drive → Progress) and every long job its own
   *job log* Doc (plan, each step as it happens, snags, your changes, result, "still on it" heartbeat); `/progress` gives
   today's link. Finished jobs land in Drive as native Docs (tables, links) from per-kind templates. [docs/PROGRESS.md](docs/PROGRESS.md).

**Time words** — "at least 3 hours" is a floor (first pass, then deeper angles and project steps until the time is used;
"that's enough" closes it), "at most 20 min" a ceiling with a timer, no time = the agent picks and says why. Ideas from
brainstorms and "new project: …" live in `/projects` and are continued in free windows. [docs/TIME.md](docs/TIME.md).

**Mailbox** — the app's Gmail is sorted every 15 min into Verification / Leads / Alerts / Newsletters (label, read,
archive by age — never delete or send); leads are flagged to you and never answered by the agent; verification codes
come from the Verification pile first. `/mail`, "tidy the inbox", "any leads?". [docs/MAILBOX.md](docs/MAILBOX.md).

## Customer messages (milestone 5, practice channel)
- `agent/inbox.py` reads `state/inbox.jsonl`, classifies each message (order status, damaged, return, cancel, discount,
  product question, complaint, compliment, spam, press/partnership, other), drafts a reply with the thinking model
  under the store policy (`state/policy.json`; see and change it with `/policy`), then runs hard checks: no numbers
  the customer never gave, no "it has shipped"/tracking claims, no refunds or discounts outside the policy, no time
  promises, no cancellations "done", no product or shipping facts the policy does not contain. A failing draft is
  repaired once, otherwise a safe template is used. Legal, chargeback, injury, personal-data and press messages get a
  holding reply and are handed to the owner; spam gets no reply.
- `/shop <address>` makes the agent read the owner's **own shop pages** (help, shipping, returns, contact, FAQ) and keep
  their exact sentences (`state/shopfacts.json`, refreshed weekly). Customer questions about delivery times, costs,
  destinations, returns, contact or payment are then answered with the shop's own words and figures; without it, such
  questions are deferred to the owner rather than guessed. The same read opens the shop's product pages (up to 12) and keeps
  name, price, availability, options and every detail line, so product questions (material, size, battery, compatibility,
  what is included) are answered from the listing — and a question about something the page does not mention gets "I will
  check with the owner", never a guess. `/shop` shows the sheet, `/shop forget` drops it.
- `/shop <address>` makes the agent read the owner's **own shop pages** (help, shipping, returns, contact, FAQ) and keep
  their exact sentences (`state/shopfacts.json`, refreshed weekly). Customer questions about delivery times, costs,
  destinations, returns, contact or payment are then answered with the shop's own words and figures; without it, such
  questions are deferred to the owner rather than guessed. The same read opens the shop's product pages (up to 12) and keeps
  name, price, availability, options and every detail line, so product questions (material, size, battery, compatibility,
  what is included) are answered from the listing — and a question about something the page does not mention gets "I will
  check with the owner", never a guess. `/shop` shows the sheet, `/shop forget` drops it.
- Every draft goes to the owner's phone with **Approve / Edit / Reject** buttons. Approved or edited text is written to
  `state/outbox.jsonl` — the agent never sends anything by itself. `/stats` shows the approval rate per message type
  and how far each is from the automatic-sending bar (30 decisions, ≥ 90 % approved as written; still off by design).
- Channel "owner": forward any customer message to the bot (or `/customer <text>`) → draft → tap → the final reply comes
  back as copyable text to paste into the shop chat / e-mail / Instagram. Real channels through official APIs come later.
- Edits teach style, not facts: from an edited reply the agent learns the greeting (`Ciao {name}!`), preferred length and
  sign-off (`state/style.json`, visible in `/policy`); the customer-specific words are never reused for another customer.
- `/inbox practice` loads 12 sample messages; `python3 engine/scripts/score_inbox.py` scores 23 messages
  (kind + must/must-not phrases + zero safety flags), currently 22/23.

## Real channels — shop e-mail, Facebook, Instagram (milestone 10)
`agent/channels.py` polls the connected channels every 3 minutes (IMAP for mail; the Meta Graph API for Page and Instagram
conversations — no public server needed) and puts real customer messages into the same inbox as the practice ones. Machine mail
(newsletters, auto-replies, bounces, no-reply senders) is skipped. Each draft reaches the phone with **✅ Approve & send ·
✏️ Edit · ❌ Reject**; the reply leaves only after the tap (`Agent.deliver` is the single sending point) — e-mail replies are
threaded under the customer's mail with their text quoted, Messenger/Instagram replies go out as customer-service responses.
A ledger of seen ids (state/channels.json) means nothing is drafted twice. Setup for Gmail, Outlook, Aruba, Libero, own domains
and the Meta app: [docs/CHANNELS.md](docs/CHANNELS.md). `/channels`, `/channels check`, `/channels now`.
Test without any account: `python3 engine/scripts/score_channels.py` (fake IMAP/SMTP server + fake Graph API, 36 checks).

## Eyes (milestone 6)
`agent/eyes.py`: a 310 MB vision model (LFM2-VL-450M, `/eyes install` once; runs on the same llama-server only while looking,
~550 MB RAM) answers plain questions about any screenshot, and tesseract OCR gives every word its position on the screen
(three views so white-on-colour button labels and boxed words are read too; menu items become separate targets).
Telegram: `/eyes` (status), `/look [question]` (its own screen), or just send it a screenshot/photo with a question as the caption.
Install the tools with `sh scripts/install_desktop.sh` (tesseract, Xvfb, xdotool, scrot). Score: `python3 engine/scripts/score_eyes.py` → 16/16.

## Desktop hands (milestone 7)
`agent/desktop.py`: its own virtual screen (or the real one when `DISPLAY` is set), screenshot → OCR → click on words with xdotool,
type, keys, scroll. Same rules as the browser: clicks that spend money, publish, delete or sign in need the owner's tap, passwords are
never typed, every click is checked by comparing the screen before and after.

## Operator — `/do <goal>` (milestones 8–9)
`agent/operator.py` repeats look → decide one step → guard → click/type/scroll → check, up to 12 steps (15 min), in two modes:
- **browser** (default): `/do https://en.wikipedia.org/wiki/Etsy | in which year was Etsy founded?` — fast and exact (page elements).
- **desktop**: `/do desktop put one bamboo toothbrush set in the cart` — works whatever window is open on its screen, from pixels only.
Questions are answered only from what is on the screen (numbers are checked against it; "I don't guess"); actions are confirmed by what
newly appeared ("Added to cart: 1 × …", and a *buy* needs an order confirmation). Any click that costs money, publishes, signs in,
deletes or submits waits for your tap on the phone; login / payment / password goals are refused up front; captcha and login walls stop it
and hand the screen to you. Score: `python3 engine/scripts/score_operator.py` → 15/15 on `tests/pages/` (see docs/SCORES.md).

Bigger jobs (milestone 9):
- **Compare pages** — give several addresses: `/do <url1> <url2> <url3> | which supplier is cheapest per pack for 200 packs?`
  It asks each page the same fact question, copies the figures exactly (price tiers included), and for *cheapest / lowest / fastest /
  most expensive / longest …* ranks them in code, e.g. `Cheapest: BambooDirect — € 1.95 (others: GreenTrade € 2.10, EcoSupply € 2.40)`.
  Non-numeric comparisons ("which one ships from Italy?") get a short summary that is checked against the findings.
- **Fill in a form** — `/do <url> | fill in the enquiry form: name = Anna Rossi, email = anna@example.com, message = Do you offer
  wholesale prices?` types into the matching fields (labels, placeholders, names) and stops: *"ready but NOT sent"* — you press Send.
- **Cookie banners** are closed before every look (page-level and inside consent iframes such as Sourcepoint/OneTrust; "reject",
  "necessary only" or "do not sell/share" preferred, otherwise close/accept) — tested on theguardian.com, wired.com and the test pages.
- **Wrong clicks**: when a page has nothing to do with the goal it goes back; when the thinker names a button that is not on the page,
  or wants to scroll a short page, it follows the most goal-related link instead (e.g. *About us* for a founding-year question).
- Fields show their current value to the thinker, so it never re-types what is already there.

## Phone line (what the agent can do today)
- Only the owner (Telegram username in `.secrets/env`, pinned to the numeric id at first contact) is served.
- `notify(text)` — one-way message to the phone.
- `ask(question, options)` — sends buttons (or waits for a typed reply) and blocks until answered; used by every
  later module for approvals ("post this?", "order this sample?").
- Every in/out message and decision is logged to `state/logs/<date>.jsonl` with secrets redacted.
