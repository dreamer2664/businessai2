"""Time floors, ceilings and the project list (owner's item E).
"at least 3 hours" = a floor: first pass delivered, then deeper angles + project steps until the time is used or 'that's enough';
"at most 20 min" = a ceiling (the timer); no time given = the agent picks and says why. Brainstorms → projects → continued later.
Run:  rm -rf /tmp/bai_floor_state; python3 engine/scripts/score_floor.py"""
import os, sys, re, time, threading
os.environ["BAI_STATE"] = "/tmp/bai_floor_state"; os.environ["BAI_STORE_PORT"] = "8191"
import shutil; shutil.rmtree("/tmp/bai_floor_state", ignore_errors=True)
sys.path.insert(0, ".")
from agent.brief import parse_pace, Brief, topic_of          # noqa: E402
from agent.pace import Pace                                    # noqa: E402
from agent import projects as PJ                               # noqa: E402

ok = 0; tot = 0
def check(name, cond, got=""):
    global ok, tot
    tot += 1; ok += bool(cond); print(("✅" if cond else "❌"), name, "" if cond else f"→ {str(got)[:200]}")

# ---- 1. understanding: floor / ceiling / neither ------------------------------------------------
p = parse_pace("take at least 5 hours: research the best print on demand platforms for europe")
check("'at least 5 hours' → floor 300, slow, no deadline", p["floor_min"] == 300 and p["pace"] == "slow" and p["deadline_min"] is None, p)
p = parse_pace("almeno 3 ore: trovami fornitori affidabili di tazze")
check("'almeno 3 ore' → floor 180", p["floor_min"] == 180 and p["pace"] == "slow", p)
p = parse_pace("find me a good vinted seller for sambas 42, at most 20 minutes")
check("'at most 20 minutes' → ceiling = deadline 20, no floor", p["deadline_min"] == 20 and p["floor_min"] is None, p)
p = parse_pace("spend at least 45 minutes on it, no more than 2 hours")
check("floor + ceiling together", p["floor_min"] == 45 and p["deadline_min"] == 120 and p["pace"] == "slow", p)
p = parse_pace("real quick, find me cheap mugs, in 10 minutes")
check("quick + in 10 min unchanged", p["pace"] == "quick" and p["deadline_min"] == 10 and p["floor_min"] is None, p)
p = parse_pace("i'm going to work for 5 hours, take it real slow: find me reliable suppliers")
check("away-time budget unchanged", p["budget_min"] == 300 and p["pace"] == "slow" and p["floor_min"] is None, p)
p = parse_pace("find cheap cork slippers on vinted")
check("no time words → normal, nothing set", p["pace"] == "normal" and not p["deadline_min"] and not p["floor_min"] and not p["budget_min"], p)
p = parse_pace("research dropshipping margins, take at least an hour, quick")
check("floor beats a stray 'quick'", p["floor_min"] == 60 and p["pace"] == "slow", p)
check("floor words leave the topic", topic_of("take at least 5 hours: research the best print on demand platforms for europe") == "research the print on demand platforms for europe"
      and "hour" not in topic_of("research dropshipping margins, take at least an hour"), topic_of("research dropshipping margins, take at least an hour"))
B = Brief(planner=None, log=lambda k, **f: None)
b = B.make("take at least 3 hours: research the best print on demand platforms for europe, make me a doc")
t = Brief.text(b)
check("plan text says floor + how it's used + how to stop", "at least 3 hours" in t and "first pass" in t and "that's enough" in t, t)
b2 = B.make("find me a good vinted seller for sambas 42, at most 20 minutes")
t2 = Brief.text(b2)
check("plan text says ceiling as 'at most'", "at most 20 min" in t2 and "timer" in t2, t2)
b3 = B.make("find cheap cork slippers on vinted")
t3 = Brief.text(b3)
check("no time given → I pick and say why", "you gave no time, so I pick" in t3 and "usually needs" in t3, t3)

# ---- 2. the clock -------------------------------------------------------------------------------
P = Pace()
P.set({"pace": "slow", "deadline_min": None, "budget_min": None, "floor_min": 2}, "x")
check("floor_left ≈ 120 s, under_floor", 110 < P.floor_left() <= 120 and P.under_floor(), P.floor_left())
check("pages budget deeper under a floor", P.pages_budget(3) == 5, P.pages_budget(3))
check("status text names the floor", "at least 0 h 2 min asked" in P.text() and "still to use" in P.text(), P.text())
P.stop_now()
check("'enough' (stop) ends the floor", P.floor_left() == 0 and not P.under_floor(), P.floor_left())
P.set({"pace": "normal", "floor_min": 1}, "y"); P.floor_done()
check("floor_done clears it", not P.under_floor() and "honoured" in P.text(), P.text())

# ---- 3. the project list ------------------------------------------------------------------------
J = PJ.Projects()
a = J.add("Test a bundle offer for the mugs", why="brainstorm")
check("project added with default steps", a and a["id"] == 1 and len(a["steps"]) == 3 and a["status"] == "open", a)
a2 = J.add("test a bundle offer for our mugs")
check("same idea twice → same project", a2 is a, a2)
bs = ("**Bundle the mugs with a coaster set.** Buyers add 8 € for a matching item; test it with the next 20 orders.\n\n"
      "**Free shipping over 35 €.** Our average order is 29 €; a threshold nudges a second item. Test for two weeks.\n\n"
      "Here is a summary of the above.")
newp = J.from_brainstorm(bs, when="09 Sep")
check("brainstorm → 2 projects (summary line skipped)", len(newp) == 2 and newp[0]["title"].startswith("Bundle the mugs") and newp[1]["source"] == "brainstorm", [p["title"] for p in newp])
nxt = J.next_step()
check("next step = oldest project, step 1", nxt and nxt[0]["id"] == 1 and nxt[1] == 0, nxt)
J.mark(1, 0, "bundles lift order value ~15 % in three sources")
check("step marked with a note", J.get(1)["steps"][0]["done"] and "15 %" in J.get(1)["steps"][0]["note"], J.get(1))
nxt = J.next_step()
check("advance rotates to the least recently touched project", nxt and nxt[0]["id"] == 2, nxt)
J.mark(1, 1, "n"); J.mark(1, 2, "n")
check("all steps done → project done", J.get(1)["status"] == "done", J.get(1))
lt = J.list_text()
check("list text: open count, next step, finished", "2 open project" in lt and "next:" in lt and "1 finished" in lt, lt)
J2 = PJ.Projects()
check("persisted to state/projects.json", len(J2.data["projects"]) == 3 and J2.get(1)["status"] == "done", J2.data)
r = PJ.command(J, "new project: try a loyalty card for repeat buyers")
check("'new project: …' opens one", r.startswith("📁 Project 4 opened") and "Steps:" in r, r)
check("'project 4' shows detail", PJ.command(J, "project 4").startswith("📁 4."), PJ.command(J, "project 4"))
check("'drop project 4'", PJ.command(J, "drop project 4").startswith("🗑") and J.get(4)["status"] == "dropped")
check("'project 2 is done'", PJ.command(J, "project 2 is done").startswith("✅") and J.get(2)["status"] == "done")
check("/projects lists", PJ.command(J, "/projects").startswith("📁"))
check("unrelated text → None", PJ.command(J, "what is the project margin on mugs") is None and PJ.command(J, "research project management tools") is None)

# ---- 4. the agent: floor phase after the first pass, then a clean finish -----------------------
from agent import core                                         # noqa: E402
class FakeBot:
    def __init__(self): self.sent = []; self.docs = []
    def get_me(self): return {"username": "fake"}
    def send(self, chat, text, buttons=None, **k): self.sent.append(text); return {"message_id": len(self.sent)}
    def send_document(self, chat, path, caption="", **k): self.docs.append(path)
    def __getattr__(self, n): return lambda *a, **k: None
core.Bot = lambda *a, **k: FakeBot()
A = core.Agent(); A.owner_id = 1
A.planner.available = lambda: False; A.planner.installed = lambda: False
A.log = lambda *a, **k: None
A.google.connected = lambda: False
A.FLOOR_CYCLE = 1
researched = []
def fake_research(topic, n_pages=3, want_doc=False):
    researched.append((topic, n_pages)); time.sleep(0.05)
    return f"Research: {topic}\nAcross the 2 pages I read:\n✓ agreed by 2 sources: {topic} costs about 12 € per unit\n• demand is steady\n(2 pages read in 3s)"
A.tasks.research = fake_research
A.tasks.run = lambda c: (time.sleep(0.1), "fake report — first pass")[-1]
A.study.quiet_session = lambda n: "📚 fake study"
check("agent has the project list", isinstance(A.projects, PJ.Projects))
A.projects.add("Test a bundle offer for the mugs", why="brainstorm", steps=["Read 2 pages on bundles"])
b = A.briefer.make("research bamboo toothbrush suppliers, take at least 1 hour")
b["kind"] = "research"; b["deliverable"] = "answer"
r = A.execute(b, approved=True)
A.pace.floor_until = time.time() + 6                           # a 6-second "hour": enough for angles + the project step
time.sleep(1.5)
check("first pass delivered, floor announced", any(x.startswith("⏬ First pass delivered") and "at least 1 hour" in x for x in A.bot.sent), A.bot.sent)
check("busy says deepening, job still open", A.busy and A.busy.startswith("deepening") and A.mind.job is not None and A.pace.done_at is None, (A.busy, A.pace.done_at))
st = A.respond("what are you doing")
check("status mid-floor mentions the floor", isinstance(st, str) and ("still to use" in st or "at least" in st), st)
time.sleep(8)
check("deeper angles were researched with the topic", sum(1 for t_, _ in researched if "bamboo toothbrush" in t_ and "costs" in t_) >= 1 and all(n == 5 for _, n in researched if "bamboo" in _), researched)
closing = [x for x in A.bot.sent if x.startswith("⏬ Floor closed")]
check("closing summary: time used, angles count", closing and "deeper angle(s)" in closing[-1] and "the time you asked for is used" in closing[-1], A.bot.sent[-3:])
check("finished cleanly: pace done, idle, no floor", A.pace.done_at is not None and A.busy is None and not A.pace.under_floor() and A._in_floor is False, (A.busy, A.pace.done_at))
# 'that's enough' mid-floor ends it early
A.bot.sent.clear(); researched.clear()
b = A.briefer.make("research cork slippers, take at least 2 hours"); b["kind"] = "research"; b["deliverable"] = "answer"
A.execute(b, approved=True)
time.sleep(1.2)
A.pace.floor_until = time.time() + 600
r = A.respond("ok that's enough")
check("'that's enough' → stopping, in words", isinstance(r, str) and r.startswith("Stopping"), r)
time.sleep(3)
closing = [x for x in A.bot.sent if x.startswith("⏬ Floor closed")]
check("floor closed early: 'you said enough'", closing and "you said enough" in closing[-1] and A.busy is None and A.pace.done_at is not None, A.bot.sent[-2:])
# a new request during the floor closes it and runs next
A.bot.sent.clear(); researched.clear()
b = A.briefer.make("research bamboo cups, at least 2 hours"); b["kind"] = "research"; b["deliverable"] = "answer"
A.execute(b, approved=True)
time.sleep(1.2)
A.pace.floor_until = time.time() + 600
r = A.respond("what's the weather like on mars")
check("new request mid-floor → queued", isinstance(r, str) and "queued" in r.lower(), r)
time.sleep(4)
closing = [x for x in A.bot.sent if x.startswith("⏬ Floor closed")]
check("floor closed for the new job", closing and "new job" in closing[-1], A.bot.sent[-3:])
# projects continue in quiet time (owner away, nothing else to do)
A.projects.add("Free shipping over 35 euro", steps=["Read 2 pages on thresholds"])
A.quiet_sessions = 1
A.bot.sent.clear(); researched.clear()
A.run_quiet()
check("quiet session with an open project → one project step done", any(x.startswith("📁") for x in A.bot.sent) and any("Free shipping" in t_ or "bundle" in t_.lower() for t_, _ in researched), (A.bot.sent, researched))
print(f"FLOOR SCORE: {ok}/{tot}")
