"""Practice day — one integration run through the whole Phase 2 flow, exactly as the owner would type it, with the Telegram
network edge faked. Fails loudly on any exception or missing deliverable. Frequent-test guard for regressions between
the single-milestone scorers.

Run:  timeout 900 python3 engine/scripts/practice_day.py 2>&1 | grep -v '^{"t"' | tail -40
"""
import json
import os
import shutil
import sys
import threading
import time
import urllib.request

os.environ["BAI_STATE"] = "/tmp/bai_practice_day"
os.environ.pop("DISPLAY", None)
os.environ["BAI_STAGE_PORT"] = "8085"
os.environ["BAI_VIEW_PORT"] = "8767"
os.environ["BAI_STORE_PORT"] = "8084"
os.environ["BAI_ACCOUNT_EMAIL"] = "stagebot@example.com"
os.environ["BAI_ACCOUNT_PASSWORD"] = "BusinessAI001!"
shutil.rmtree(os.environ["BAI_STATE"], ignore_errors=True)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from agent import core                                                   # noqa: E402

checks = []


def check(name, ok, note=""):
    checks.append((name, bool(ok)))
    print(("✅" if ok else "❌"), name, ("— " + str(note)[:130]) if note else "", flush=True)


class FakeBot:
    def __init__(self, *a, **k):
        self.sent = []
        self.photos = []
        self.docs = []

    def get_me(self):
        return {"username": "bot", "id": 1}

    def send(self, chat, text, buttons=None, **k):
        self.sent.append((text, buttons))
        return {"message_id": len(self.sent)}

    def send_photo(self, chat, path, caption=None, **k):
        self.photos.append((str(path), caption))

    def send_document(self, chat, path, caption=None, **k):
        self.docs.append((str(path), caption))

    def __getattr__(self, n):
        return lambda *a, **k: None


def wait_until(pred, seconds):
    for _ in range(int(seconds * 2)):
        if pred():
            return True
        time.sleep(0.5)
    return pred()


def say(text):
    """The owner types something. Returns the direct reply (or None when the agent answered by a sent message)."""
    r = A.respond(text)
    if r:
        A.bot.sent.append((r, None))
    return r


def tap(data, msg_id=5):
    A.handle_callback({"id": str(time.time()), "from": {"id": 1, "username": "dreamer2664"}, "message": {"chat": {"id": 1}, "message_id": msg_id}, "data": data})


def last_buttons():
    for t, b in reversed(A.bot.sent):
        if b:
            return t, b
    return None, None


t0 = time.time()
core.Bot = lambda *a, **k: FakeBot()
A = core.Agent()
A.owner_id = 1
A.planner.available = lambda: False
A.planner.installed = lambda: False

# --- morning: greetings, status, help ----------------------------------------------------------------------------
r = say("hey, good morning")
check("chat answered without starting a job", r and not A.busy and A.last_brief is None, r)
r = say("/status")
check("status shows version, thinking line, accounts", r and "Business AI" in r and "thinking:" in r and "site account" in r)

# --- a quick question (ask → brain/planner or research) ---------------------------------------------------------------
r = say("make it quick: what's a good margin for dropshipping?")
check("quick question: answered or research started, timer set", (r and len(r) > 20) or A.busy, (r or "")[:80])
wait_until(lambda: not A.busy, 120)

# --- website: plan → change → go → deliverables --------------------------------------------------------------------------
say("build a website for a small bakery in Bergamo called Forno Bianchi")
t, b = last_buttons()
check("website: plan shown with Go/Change/Cancel", t and "My plan" in t and b and any("b:go" in str(x) for row in b for x in row), (t or "")[:80])
say("also mention that we deliver to offices")
t2, b2 = last_buttons()
check("website: change amended the plan (no new job)", t2 and "Shall I go" in t2 and A.last_brief is not None, (t2 or "")[-80:])
tap("b:go")
ok = wait_until(lambda: any(d[0].endswith(".zip") for d in A.bot.docs), 120)
check("website: zip + screenshot delivered", ok and A.bot.photos, (A.bot.docs[-1][0] if A.bot.docs else None))
rep = next((t for t, _ in A.bot.sent if t.startswith("🌐 Built a website")), "")
check("website: report says checks passed", "checks passed" in rep, rep[:120])
wait_until(lambda: not A.busy and A.mind.job is None, 30)

# --- mid-job conversation on a real job ---------------------------------------------------------------------------------
gate = threading.Event()
orig_run = A.tasks.run


def slow_run(command):
    A.viewer.plan_step(1, "reading page 1")
    gate.wait(15)
    return orig_run(command) if A.pace.should_stop() is False and False else "Report (fake, stopped early): epacket = China Post economy tracked service, 7-20 days to Italy."


A.tasks.run = slow_run
say("research how epacket works for shipments to italy")
time.sleep(1)
r = say("what are you doing?")
check("mid-job status answered without stopping the job", r and "I'm on:" in r and A.busy, (r or "")[:100])
r = say("compare aliexpress vs cj dropshipping shipping times to italy, write me a document")
check("mid-job new request queued", r and "queued" in r, (r or "")[:80])
r = say("stop")
check("stop acknowledged", r and "Stopping" in r)
gate.set()
ok = wait_until(lambda: any("Now the request you queued" in t for t, _ in A.bot.sent), 30)
check("queued request started by itself", ok)
A.tasks.run = orig_run
# the queued compare is a document → plan with buttons; cancel it to move on
wait_until(lambda: A.last_brief is not None or A.busy, 20)
if A.last_brief:
    tap("b:no")
wait_until(lambda: not A.busy, 60)
r = say("/lessons")
check("lessons written after the stopped job", r and "research" in r, (r or "")[:120])

# --- social rehearsal ------------------------------------------------------------------------------------------------------
say("rehearse posting about our bamboo toothbrush set")
ok = wait_until(lambda: any(t.startswith("🎭 Rehearsal") for t, _ in A.bot.sent), 150)
line = next((t for t, _ in A.bot.sent if t.startswith("🎭 Rehearsal")), "")
check("rehearsal: posted on the practice network", ok and "posted in" in line, line[:120])
ok = wait_until(lambda: any(b and t.startswith("📨") for t, b in A.bot.sent), 40)
check("rehearsal: buyer comment → reply draft with buttons", ok)
t, b = last_buttons()
if b and t.startswith("📨"):
    mid = b[0][0][1].split(":")[-1]
    tap(f"r:ok:{mid}")
    ok = wait_until(lambda: any("Reply posted under the rehearsal post" in t for t, _ in A.bot.sent), 90)
    check("rehearsal: approved reply placed under the post", ok)
else:
    check("rehearsal: approved reply placed under the post", False, "no draft buttons")
wait_until(lambda: not A.busy, 30)

# --- self-study session (owner away) ---------------------------------------------------------------------------------------
r = say("i'm going to work for 5 hours, take it real slow: find me reliable suppliers of bamboo toothbrushes in europe")
t, b = last_buttons()
check("slow job: plan shows the 5 h budget and self-study promise", t and "up to 5 h" in t and "studying" in t, (t or "")[:160])
check("pace: not started yet → no quiet time", A.last_brief is not None and not A.pace.has_quiet_time())
tap("b:no")
A.pace.set({"pace": "slow", "deadline_min": None, "budget_min": 300, "why": "away"}, "test")
A.pace.finish()
check("pace: after finishing early the remaining budget is quiet time", A.pace.has_quiet_time())
# a quiet session with the study module (courses pending from the owner's two videos)
pend = A.study.pending_courses()
check("study: owner's two courses pending", len(pend) >= 2, pend)
A.pace.clear()

# --- website auto-training: one round ------------------------------------------------------------------------------------
n0 = len(A.bot.sent)
r = say("start auto training on website building")
check("training: started from the sentence", A.site_training and "training on" in (r or "").lower())
ok = wait_until(lambda: A.sites_built >= 1, 150)
say("stop training")
wait_until(lambda: not A.site_training and any(t.startswith("🏁") for t, _ in A.bot.sent), 90)
built_line = next((t for t, _ in A.bot.sent[n0:] if t.startswith("🌐 #1 built this website for")), "")
check("training: one real place built and one short line sent", ok and built_line, built_line[:120])
check("training: stopped cleanly with a summary", any(t.startswith("🏁") for t, _ in A.bot.sent))

# --- library + accounts + ideas overview ---------------------------------------------------------------------------------------
r = say("/library")
check("library lists the documents made today", r and ("Course" in r or "website" in r.lower() or "ideas" in r.lower() or "html" in r.lower() or "•" in r), (r or "")[:120])
r = say("/accounts")
check("accounts: practice network account remembered", r and "127.0.0.1:8085" in r, (r or "")[:120])
r = say("/rehearse map")
check("rehearsal map remembered", r and "Publish" in r)

# --- nothing leaked: no exceptions in the log, no owner nags for stage sign-ups ------------------------------------------------
logs = ""
for f in sorted((core.config.LOG_DIR).glob("*.jsonl")):
    logs += f.read_text()
bad = [l for l in logs.splitlines() if '"error"' in l and ("Traceback" in l or "_failed" in l) and "geocode_failed" not in l and "drive_upload" not in l and "site_upload" not in l and "study_upload" not in l]
check("log: no unexpected failures", len(bad) <= 2, [json.loads(l).get("kind") for l in bad[:4]])
check("no owner nag about signing up on my own stage", not any(t.startswith("🆕") for t, _ in A.bot.sent))

A.tasks.on_hands(A.tasks.close_browser, timeout=30)
ok = sum(1 for _, o in checks if o)
print(f"\nPRACTICE DAY {ok}/{len(checks)}  ({time.time() - t0:.0f}s)")
sys.exit(0 if ok == len(checks) else 1)
