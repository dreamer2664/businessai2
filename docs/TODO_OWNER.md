# The owner's to-do list (his words, 2026-09-09) — working order, status, and what "done" means

Rules for this list: as slow as needed; every item ships with a test set + docs; scores in docs/SCORES.md never drop;
report progress to the owner by Google Doc without ending the session; watch disk (`du -sh release state ~/.cache`).

The overnight AI ticked every box of this list in one night (docs/TODO_NIGHT.md). My audit (builder/replies.md, 2026-09-09):
the code exists and passes its own offline tests, but the behaviour the owner actually complained about is NOT fixed yet.
Reality check on 2026-09-09 with the real browser:
- "get me the top 5 trending videos on youtube … google doc with links and the top comment for each" → the plan says
  "open the video(s) and read the captions", runs the *ideas* watcher, and comes back in 2 s with "watched 0 videos".
  /feed/trending redirects to the YouTube home page for a visitor (0 entries). YouTube *search* does work
  (21 videoRenderer blocks, ytInitialData present, 0 ids found by the old regex) → the reader must parse ytInitialData.
- "take at least 5 hours" / "almeno 3 ore" → pace = normal, no budget. The "at least N" rule does not exist yet.
- pace budget is filled by study.quiet_session (PDF / video / brainstorm) — no project list, brainstorms are not picked up later.

## Order of work (each = one milestone, one score set)
- [x] A. Reliable second channel (2026-09-09, bab647b/8b7b9c6: owner mailed from carlo.rella014@gmail.com → answered by mail in 63 s; replies carry plan/buttons/doc names; spoof check; /fallback check now|on|off) — the fallback module exists (fallback.py 17/17) but only as code; it must be *set up and
      proven* end to end with the owner: Gmail two-way (owner mails the bot, bot answers) + the backup Telegram bot;
      a "line check" every morning; a one-line owner guide. Done = owner has received a reply through each line.
- [x] B. Understanding requests like the YouTube one (2026-09-09: "trending" is its own kind → list/document, topic and N parsed; literal line checks "answer with X if you got this" answered literally) — intent → the right tool (a "trending" request is a *list*
      job, not "watch captions"); the plan names the tool it will use and the shape of the result.
- [x] C. YouTube done right (2026-09-09: video.py reads ytInitialData — search with sort/period filters, top comments from the same /next JSON the page loads, hot_now() = most-watched uploads of the week with the honest note; document with table + top comment; fixtures in tests/fixtures/yt_*; live check passed from the sandbox — PC check still worth doing). Trending page itself stays hidden from visitors; the browser feed is only a fallback. — search/trending readers parse ytInitialData (ids, titles, channel,
      views, published), top comment per video from the watch page, honest "trending is hidden from visitors → here is
      the search-by-recency fallback". Fixtures from real pages; live check on the PC.
- [x] D. Google Docs reports (2026-09-09 night: agent/progress.py — day log Doc in Drive/Progress + job log Doc for slow/long/quiet
      jobs or after 20 min, steps/snags/changes/result + "still on it" heartbeat, /progress command; Templates write native
      Docs for research / trending / seller check / site / note, used by run_task and the seller check; docs_write_blocks
      fixed for emoji (UTF-16 ranges) and links; docs/PROGRESS.md; progress 16/16 (+1 live), docs_native 7→9) — the native
      Docs writer exists; per-type templates (trending table, deal alert, research cards); every finished job gets its Doc
      link in the chat; heartbeat Doc for long sessions.
- [x] E. Time (2026-09-09 night: brief.parse_pace floor/ceiling EN+IT, pace.floor_until, core.run_floor = first pass →
      deeper angles → project steps → study until the floor or 'that's enough', 30-min lines, "Deeper on …" Doc; plan text
      says my pick when no time is given; agent/projects.py + /projects, brainstorms → projects, quiet time continues them;
      docs/TIME.md; floor 44/44) — "at least N hours" = a floor (the job keeps going, deeper reading + project work, never
      idle filler), "at most / in N" = a ceiling, unspecified = the agent picks and says why. Project list: brainstorms
      become projects (state/projects.json), the next free window continues them.
- [x] F. Marketplaces (2026-09-09 night, 9be45ce + next: measured live from the sandbox — Vinted and subito both serve a plain
      headless visitor, no walls in ~40 polite hits; readers rewritten for the 2026 layouts, Vinted's own page JSON gives
      seller location / feedback split / buyers' words / shipping; markets 20→40, sellers 34; docs/MARKETS.md). Still to do
      on this item: the same live check from the PC, Facebook stays waters-only, eBay sold-listings cross-check (arbitrage).
- [x] G. Gmail as a tool (2026-09-09 night: agent/mailbox.py — labels Verification / Leads / Alerts / Newsletters created in the
      real mailbox, rules EN+IT, 15-min tidy that labels, marks read and archives by age (never deletes or sends), leads flagged
      to the owner and never answered, codes fetched from the Verification pile first (chat + sign-up skill), /mail · 'tidy the
      inbox' · 'any leads?', /status mail line; docs/MAILBOX.md; mailbox 43/43 + live) — labels (Verification / Leads / Alerts),
      code fetching, tidy inbox; sign-up training on the local fake sites (accounts 18/18 covers it), real sign-ups only on
      owner-approved ones.
- [x] H. Knowledge — pack #3 (2026-09-09, dropship.kdw 2.7 MB: 176 guides / 8,313 passages — dropshipping, used goods &
      reselling, marketplace fees, EU rules; tests/dropship.txt 59/59 alone, 57/59 with all packs; business 52/55 and
      operations 38/41 unchanged; on the GitHub Release, the PC fetches it by itself on restart; docs/PACKS.md).
- [x] I. Thinking (2026-09-09 night: agent/mind.py cycle — each step on the live screen and in /thinking shows plan (what + why),
      did (hosts read, walls, documents) and check (verdict in plain words, green/yellow/orange); the after-job lesson is built
      from what really happened (weak step / slowest step / sources that did the work), the stock "went fine" line is gone;
      only bad-run lessons become next-plan advice; think 12→21, mind 42, talk 463; docs/THINKING.md).

## Log
- 2026-09-09: list written after the audit; A/B/C first because they are what the owner sees every day.
- 2026-09-09 (evening): ROOT CAUSE of months of 'answers only while someone works on it': Windows stops the WSL VM 60 s after the last terminal closes (journal: Stopping businessai.service after each command; -- Boot -- on the next). Fix in docs/INSTALL_WINDOWS.md §4 (.wslconfig vmIdleTimeout=-1 + keeper scheduled task). The sandbox has the same symptom for a different reason (processes suspended between turns) → the bot's home is the PC only.
- 2026-09-09 (evening): A proven live with the owner; B + C shipped (youtube 12→19, brief 34→39, talk +3, fallback 17→20). Next: D (Doc templates + heartbeat doc), E (time floors/ceilings, projects).
- 2026-09-09 (night): F shipped (markets 40/40, sellers 34/34, subito live e2e), D shipped (progress 16/16 live-verified). Next: E (time floor + project list), then G/H/I.
- 2026-09-09 (night, later): E shipped (floor 44/44). Next: G (Gmail labels/tidy), H (knowledge pages), I (plan → critique → act on the live screen).
- 2026-09-09 (night, later): G shipped (mailbox 43/43, live labels in the real Gmail). Next: H (knowledge pages), I (plan → critique → act).
- 2026-09-09 (night, later): H shipped (dropship.kdw 2.7 MB, 59/59; business 52/55 + operations 38/41 unchanged). **Google is OFF**:
  the token refresh now answers `disabled_client` — the OAuth client itself is switched off in the Cloud console (not the 7-day cut;
  Google does this to unverified apps after its notices — the three "Google notices" the mailbox filed under Alerts on 2026-09-09 were
  probably the warning). Owner must re-enable it: console.cloud.google.com → project businessai-508000 → Google Auth Platform → Clients,
  or create a new Desktop-app client and hand over its JSON. Until then Drive/Docs/mailbox/progress Doc are paused; the agent now says so
  once a day in plain words instead of sending links that cannot work (gmail 9→10). Progress-Doc entry 7 (H) is pending on that.
- 2026-09-09 (night, later): I shipped (think 21/21; the live screen shows plan / did / check per step, lessons in own words).
  **A–I all ticked.** Still open from the owner's list: smarter scraper, multi-source search, watch disk; Google client to re-enable
  (progress-Doc entries 7 + 8 pending on that). PC is on 10fc41d — the pull line brings everything.
- 2026-09-10: "watch disk" done as a habit, not a note: agent/housekeeping.py measures `release / state / ~/.cache`
  (the owner's du line) every 6 h in the idle loop, prunes only rebuildable things (day logs > 30 d, screenshots > 7 d,
  raw pack fetches > 14 d, model log capped at 2 MB, step journal at 2 000 lines; pip cache too when space is low),
  never the library / notes / models / browser; `/status` has a disk line; `/disk` explains, `/disk clean` acts;
  below 2 GB free the owner is told once a day. Sandbox today: 19 GB free; release 83 MB, state 1.8 MB, cache 369 MB. disk 10/10.
- 2026-09-10 (later): Google is back (the owner made a new Desktop-app client; project businessai was suspended and reinstated by
  Google on 9 Sep — the old client stayed disabled). Progress-Doc entries 7 + 8 posted. **Multi-source search shipped**: when a job has
  time left the research widens to a second engine, the shipping/price/spec pages inside the sites, Wikipedia and the most-watched
  YouTube video, and says so in the reply (research 30/30, sources 18/18). PC needs the pull line + `connect google` there (tokens are
  per machine). Still open from the owner's list: smarter scraper (fewer walls first, then a fuller listing card).
- 2026-09-10 (later): smarter scraper shipped — (1) wall memory: sites/engines that blocked me go last and are skipped after two
  walls (`/walls`, `/walls forget`), (2) fuller listing card from the shop's own product data (price+currency, stock, returns, shipping,
  brand, warranty…). walls memory 18/18, listing 20/20. **The owner's whole list is now ticked** (A–I, disk, Google, multi-source,
  scraper). PC still needs the pull line + `connect google`.
- 2026-09-10 (later): the stale "BrowserType.launch" advice is gone — machine faults (browser/module missing, no disk/memory) are
  repairs for the owner (🔧 line with the doctor command), never planner lessons; old advice retires after 14 days or a clean run.
  selfcheck + doctor.sh v6 install/verify the browser. think 25/25.

## 2026-09-10 — your "best deals list" test: what was wrong and what changed
- The one word that broke everything: **subito**. In Italian it means "right away", and the bot read your "look in subito.it"
  as "do it quick". From there every "slow down" was misunderstood. Fixed: a site name is never a pace word.
- "Take around 5-6 hours" now means: at least 5 hours of work, stop by 6. "Slow down" during a job slows it (it never says
  "Speeding up" to a complaint). A message that is only about pace is never a task.
- "the list I'm about to send" → it now shows the plan and **waits for your list** (one item per line, "— max 150" optional).
  The list starts the job at once, no "Go" needed. "Facebook only in Barletta" is kept as a rule.
- A second "stop" tells you the truth ("still stopping, the current page finishes, no new pages"); a third drops the result.
- Cookie banners and popups (Subito's, Vinted's "Dove vivi?") are now closed on every page the bot opens.
- New: a **deal hunter** — one document, one section per item, cheapest sound listing first, pictures, seller feedback,
  accessories/broken units pushed down. From this sandbox: Vinted + Subito work fully; Banggood works; Wallapop, DHgate,
  Shein block the sandbox's address (they may work from your PC — the bot says so per site); Temu and Facebook need a login,
  so they are named as not searchable.
- "What time is it in the UK" works (and the clock is yours, Europe/Rome, not the machine's).

## 2026-09-10 (while you were out) — what the deal hunter learned
- It no longer falls for "€ 1" listings (that's "make me an offer"), "Nintendo switch zelda" (a game), or a "Dyson hanger" (an
  accessory) as the best deal — the best is the cheapest *real* item; the odd ones are still in the document, marked.
- Longer time = deeper: with "take 5-6 hours" it reads more pages, opens the top 3 listings per item, and then **watches** the
  marketplaces every 15 minutes, telling you only when a new listing beats the best ("🔔 Better deal for …").
- It now browses as an Italian visitor (Italian pages, € prices), so fewer popups and no dollar prices.
- New command **/markets**: one real search on each marketplace and a ✅/❌ list with the honest reason (blocked, CAPTCHA, login).
  Run it once on your PC — your home connection will get different answers than my sandbox (e.g. Wallapop/eBay may work for you).
