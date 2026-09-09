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
- [ ] A. Reliable second channel — the fallback module exists (fallback.py 17/17) but only as code; it must be *set up and
      proven* end to end with the owner: Gmail two-way (owner mails the bot, bot answers) + the backup Telegram bot;
      a "line check" every morning; a one-line owner guide. Done = owner has received a reply through each line.
- [ ] B. Understanding requests like the YouTube one — intent → the right tool (a "trending" request is a *list*
      job, not "watch captions"); the plan names the tool it will use and the shape of the result.
- [ ] C. YouTube done right, browser-first — search/trending readers parse ytInitialData (ids, titles, channel,
      views, published), top comment per video from the watch page, honest "trending is hidden from visitors → here is
      the search-by-recency fallback". Fixtures from real pages; live check on the PC.
- [ ] D. Google Docs reports — the native Docs writer exists; per-type templates (trending table, deal alert,
      research cards); every finished job gets its Doc link in the chat; heartbeat Doc for long sessions.
- [ ] E. Time: "at least N hours" = a floor (the job keeps going, deeper reading + project work, never idle filler),
      "at most / in N" = a ceiling, unspecified = the agent picks and says why. Project list: brainstorms become
      projects (state/projects.json), the next free window continues them.
- [ ] F. Marketplaces — vinted + subito readers exist (markets.py, fixtures) but have never been run against the live
      sites from the PC; measure block rates *politely* first (throttle, real UA, no stealth), then decide with the owner.
      Facebook: waters only. Arbitrage: cross-check with eBay sold listings (public pages).
- [ ] G. Gmail as a tool — labels (Verification / Leads / Alerts), code fetching, tidy inbox; sign-up training on the
      local fake sites, real sign-ups only on owner-approved ones.
- [ ] H. Knowledge — pack #3 (dropshipping/used-goods/marketplaces): seed exists (37 guides); grow to ~150–200 pages,
      scored, size-budgeted.
- [ ] I. Thinking — the live viewer shows plan → critique → act per step; the reflection is the agent's own words,
      not a template.

## Log
- 2026-09-09: list written after the audit; A/B/C first because they are what the owner sees every day.
