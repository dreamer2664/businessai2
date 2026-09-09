# Night marathon — to-do (2026-09-09)

Owner's orders: slow, thorough, tested like everything else. Main stays green —
build on `night/marathon`, merge per item only when the full battery holds.

## Rules
- Score-driven: nothing merges that lowers any score in docs/SCORES.md.
- Every item ships with a test set + docs + heartbeat entry.
- Disk budget: watch `du -sh release state ~/.cache`; model+brain+browsers ≈ 1.5 GB, packs stay small.
- Secrets never in git. Gmail password lives in `.secrets/env` only (owner rotates it after setup — it passed through chat).

## List (weights = heartbeat %)
- [x] 1. Fallback contact — Gmail two-way (poll owner mail, obey, reply) + scope upgrade to send — 12%
- [x] 2. Smarter research — query planner, multi-source, synthesis (no more literal-query copy-paste) — 14%
- [ ] 3. Marketplace scrapers — Vinted + subito.it deep, Facebook waters-only; stealth, back-off, proxy support — 20%
- [ ] 4. YouTube trending + top comments (official API first, browser fallback) — 7%
- [x] 5. Google Docs layouts (core writer live-verified; per-type templates ride with item 2) — native Docs API tables/styles per report type — 8%
- [ ] 6. Gmail mastery + safe-signup training (fakes first, real signups only on owner-approved sites) — 8%
- [x] 7. Time budgets + priority queue (High=scrape, Medium=log, Low=brainstorm) + duration parsing — 8%
- [ ] 8. Pack #3 dropshipping/business feed + tests/dropship.txt (seed tonight, grow across sessions) — 10%
- [ ] 9. Viewer reasoning upgrade — thinking panel for owner + agent — 6%
- [x] 10. Heartbeat/progress system + docs + full regression battery — 7%

## Log
- 2026-09-09: list created. Q&A pending (heartbeat path, fallback scope, YouTube key). Starting with recon reads.
- 2026-09-09: owner answers: heartbeat = owner sends PC google_token.json after connect fixed (token path); fallback = Gmail + backup Telegram bot; YouTube = zero-intervention browser-first (API optional later). PC bot down at 00:01 UTC (message untouched 5+ min) → sandbox standby bot. Snapshot lessons: .git/config excluded (re-add remote), modes stripped, llm/chromium/pip wiped (128MB cap + name exclusions) → scripts/sandbox_wake.sh repairs.
- 2026-09-09 00:35 UTC: Google CONNECTED (chat-path OAuth, send scope). Heartbeat doc live. Marathon 8%. Owner to sleep; resume on 'go'.
- 2026-09-09 02:4x UTC: item 1 DONE (agent/fallback.py, 14/14 offline, docs/FALLBACK.md, zero regressions) — merged to main. Item 5 core done (native writer 7/7 + live PASS). Heartbeat 26%. Next: item 10 (regression battery).
- 2026-09-09 03:x UTC: item 10 DONE (score_all battery + suite hardening) — merged to main. Heartbeat 33%. Next: item 7 (time budgets).
- 2026-09-09 03:x UTC: item 7 DONE (queue 20/20, battery green) — merged to main. Heartbeat 41%. Next: item 2 (smarter research).
- 2026-09-09 0x:x UTC: item 2 DONE (research 19/19, battery green) — merged to main. Heartbeat 55%. Next: item 4 (YouTube).
