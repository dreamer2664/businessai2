# Progress in Google Docs (owner's item D)

You should never have to ask "what are you doing?". While I work, I write — in Google Docs
you can open on your phone.

## Two kinds of page

**The day log** — one Google Doc per day, `Business AI — Wednesday 09 September 2026`,
in Drive → *Progress*. Every job appends: `▶` start (goal, kind, why this pace), the plan
as bullets, the first steps and then every 5th one, `⚠️` snags (walls, failed pages),
`✏️` your mid-job changes, `✅/❌` result with the time it took and the link of the
document it produced. `/progress` gives you today's link (or say "show me the progress").

**A job log** — its own Doc, `Job log — <goal> — <date time>`, for every job that is
*long*: you said "take it slow", "at least 3 hours", you are away (quiet-time budget), you
asked for it, or the job simply passes 20 minutes. It holds the plan, then *every* step as
it happens, the snags, your changes, the result. The link comes with the first message
("📝 Follow along here") and again with the result.

**Heartbeat** — in a job log, if nothing was written for 8 minutes I add
"still on it: …", so a silent phone never means a dead agent.

## Native documents per job type

Finished jobs no longer land in Drive only as converted HTML: each kind has a template
that writes a real Google Doc (headings, tables, bullets, clickable links), from
`agent/progress.py::Templates`:

| kind | shape |
|---|---|
| research | In short · side-by-side table (page → first key point) · one section per page with its points · sources |
| trending | note · table #/Video/Channel/Views/Uploaded/Length · per video: link + top comment (or the honest "not readable") |
| seller_check / deal alert | conditions · side-by-side table with verdict marks · per seller: link, verdict, facts table, 👍/👎 · How I judged |
| site_report | pages, languages, notes |
| note | title + paragraphs + bullets (line checks, short answers) |

The HTML file is still sent on Telegram (it works offline, with pictures); if the Docs
API fails the HTML is converted as before — you always get a link.

## Costs and care

Writes are batched (one append every ~90 s per doc, 2 API calls each) in a worker thread;
Google off → silent no-ops; API errors are logged, never raised into a job. Docs indexes
are UTF-16 units, so emoji are counted as 2 (a bug that used to shift heading ranges).

Proof: `python3 engine/scripts/score_progress.py` (16/16 offline, +1 with `--live`),
`python3 engine/scripts/score_docs_native.py` (9/9, `--live` PASS).
