# Time: floors, ceilings, and what happens when you say nothing (owner's item E)

Three ways to talk about time, all understood in English and Italian, by rules (no model needed):

| you say | what it is | what I do |
|---|---|---|
| "take **at least** 3 hours", "almeno 3 ore", "spend at least 45 minutes" | a **floor** | I deliver the first pass as soon as it is ready, then **keep going on purpose** until the time is used: deeper angles on the topic (costs, risks, options compared, reviews, how to start, alternatives — 5 pages each instead of 3), then steps of our open projects, then study. Never idle filler. One short line every 30 min; every item in the job log Doc. Say **"that's enough"** to close earlier; a new request closes it too and runs next. At the end: a summary and a "Deeper on …" Google Doc. |
| "**at most** 20 minutes", "in 10 minutes", "entro un'ora", "max 30 min" | a **ceiling** | the visible timer: reminders, "past the N minutes" once, short paths when it gets close. |
| "I'm away 5 hours", "back after lunch" | a **budget** | quiet time: the job may use it; what is left goes to self-training and project steps. |
| nothing | my pick | the plan says so: "you gave no time, so I pick: about 5–10 min is what a seller check usually needs; tell me a floor or a ceiling if you want otherwise". |

Floor and ceiling combine ("at least 45 minutes, no more than 2 hours"). A floor wins over a stray "quick".

## The project list — `/projects`

Ideas should not die with the chat. Two sources:
- my quiet-time **brainstorms** (3 ideas each) become projects automatically (`state/projects.json`);
- you: **"new project: test a bundle offer for the mugs"**.

Each project has steps (default: read 2–3 solid pages · find the one number that matters · write a one-page proposal).
The **next free window** — a floor phase, or quiet time when you are away — does **one step of the oldest project**,
keeps the finding on the step, and when a project completes you get the proposal (nothing bought, nothing posted).
`/projects` lists them · `project 2` shows its notes · `project 2 is done` · `drop project 2`.

Proof: `python3 engine/scripts/score_floor.py` → 44/44 (understanding, the clock, the list, the agent's floor phase
end-to-end with fake research: announce → deeper angles → project step → close; 'that's enough'; new job mid-floor;
quiet-time project step).
