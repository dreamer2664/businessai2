# Thinking on the live screen — plan → act → critique per step (item I, 2026-09-09)

What the owner sees at http://localhost:8765 (and with `/thinking` in Telegram) while a job runs:

```
🧠 Thinking
Why: Because you asked for “find reliable suppliers of bamboo toothbrushes”. This step (Read reviews) is how I get there: …
I'm on: … — step 3 of 5, 48 s in. Right now: … Next: … Snags so far: … Last check (step 2): 2 page(s) read, 1 blocked …
Step by step:
1. plan: Search for candidates — I need a few options before I can rank anything.
      did: searched duckduckgo.com
      check: searched duckduckgo.com in 4 s — results in hand, the reading is the next step.           (green)
2. plan: Open each listing — the listing itself tells me price, shipping and where it ships from …
      did: → reading listing 1/4: EcoBrush, reading ecobrush.example, etsy.com: captcha wall, reading amazon.it
      check: 2 page(s) read, 1 blocked (etsy.com: captcha wall) — enough; the blocked sites go last next time.   (green)
3. plan: Read reviews — reviews and complaints are where a bad seller shows before the price does.
      did: trustpilot.com: captcha wall
      check: …still on it                                                                                  (yellow)
```

## How it is built (agent/mind.py)
- **plan** — written when a step opens (`Mind._open_step`): the step's text + the reason for it (`_step_reason`, per kind of step).
- **act** — filled from the same event stream the screen shows (`Mind.on_event`): `browser_open` → `reading <host>` or
  `searched <engine>`, `task_wall` → `<host>: captcha wall`, `seller_check`, `doc_saved`, `captcha_passed`; notes from the
  code (`mind.doing(...)`) appear as `→ note`. Hosts, not full URLs — the owner reads it on a phone.
- **critique** — written when the next step opens or the job ends (`Mind._judge`), from the acts alone (no model):
  pages read / walls / documents / seconds → a plain sentence and a verdict: `ok` (green), `thin` (one source only),
  `redo` (only walls or 90 s with nothing to show), `doing` (yellow, still on it). It says what changes, not just what happened
  ("I change the angle or the site instead of retrying the wall").
- **reflection in the agent's own words** — the lesson after the job (`Mind._lesson`) is built from the cycle:
  the weak step and what really happened there, or the slowest step, or the sources that did the work
  ("2 source(s) did the work (corkway.com, shopify.com) in 1 min 12 s — start from those next time on this topic").
  With the thinking model running, the model gets the same step-by-step record and writes the sentence; without it the
  own-words builder does. The stock line "went fine — keep the same order of steps" is gone.
- Lessons carry `improve: true/false`; only lessons from jobs where something went wrong become "🧠 From last time" advice
  in the next plan. A clean run is a record, not a warning.
- `state/lessons.jsonl` records now keep the per-step cycle (`n`, `step`, `secs`, `verdict`, `critique`).

## Proof
`python3 engine/scripts/score_think.py` — 21/21 (was 12): cycle shape, search ≠ source, hosts + walls counted, walls → redo,
double announce = one record, document closes ok, own-words lesson for a bad run and for a clean run, status/thinking text,
viewer state + page. mind 42/42, talk 463/463, brief 39/39 unchanged.

## Not yet
- The critique judges from what the screen saw; a step that reads pages *without* opening the browser (knowledge-pack answers)
  shows "no pages needed here — decided from what I already had".
- Only the last 8 steps are kept per job, the panel shows the last 4.
