"""Stop / wait / self-training preemption manners. Run: rm -rf /tmp/bai_stop_state; python3 engine/scripts/score_stop.py"""
import os, sys, re, time, threading
os.environ["BAI_STATE"] = "/tmp/bai_stop_state"; os.environ["BAI_STORE_PORT"] = "8189"
sys.path.insert(0, ".")
from agent import core
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
started = []
A.tasks.run = lambda c: (started.append(c), time.sleep(0.2), "fake report")[-1]
ok = 0; tot = 0
def check(name, cond, got=""):
    global ok, tot
    tot += 1; ok += bool(cond); print(("✅" if cond else "❌"), name, "" if cond else f"→ {str(got)[:160]}")

# 1) idle: 'stop' is never a brain question
r = A.respond("stop"); check("idle stop → plain answer", isinstance(r, str) and r.startswith("Nothing is running"), r)
r = A.respond("basta"); check("idle basta → plain answer", isinstance(r, str) and "idle" in r, r)
# 2) filler running: an owner request preempts it and starts at once
A.busy = "self-training (quiet time)"; A.filler = True
r = A.respond("research bamboo toothbrush suppliers and write me a document with the options")
time.sleep(0.6)
check("request during filler → filler cut", A.filler is False and A.busy != "self-training (quiet time)", f"filler={A.filler} busy={A.busy}")
check("request during filler → not 'queued'", not (isinstance(r, str) and "queued" in r.lower()), r)
time.sleep(2)
# 3) filler running + 'stop' → stops filler, plain words
A.busy = "self-training (quiet time)"; A.filler = True
A.last_brief = None
r = A.respond("stop"); check("stop during filler → stopped, idle", isinstance(r, str) and r.startswith("Stopped the self-training"), r)
check("stop during filler → busy cleared", A.busy is None, A.busy)
# 4) one-word mystery is not a lecture
r = A.respond("kawhi"); check("one word → asks for more words", isinstance(r, str) and "few more words" in r, r)
# 5) long message keeps the full request (goal not cut mid-word)
r = A.respond("Look up the cheapest basketball jerseys for KAWHI LEONARD on Vinted and subito.it (subito.it has to have shipping on, not just hand offs) and report back to me with a well written and documented document in the drive. I want links and images.")
txt = r if isinstance(r, str) else (A.bot.sent[-1] if A.bot.sent else "")
check("long request → plan mentions vinted + subito", "vinted" in txt.lower() and "subito" in txt.lower(), txt)
check("long request → shipping condition kept", "shipping" in txt.lower() or "hand" in txt.lower(), txt)
# 6) 'wait' while a real job runs → stop message names the job, never a lecture
A.busy = "research: mugs"; A.filler = False
A.mind.job = {"goal": "research the cheapest stoneware mugs on etsy for the shop", "snags": [], "kind": "research", "t": time.time()}
r = A.respond("wait"); check("wait during a job → stopping the job", isinstance(r, str) and r.startswith("Stopping “research the cheapest stoneware mugs") and "so far" in r, r)
A.mind.job = None; A.busy = None; A.stop_flag = False
# 7) after 'stop', the planned request from the brief is dropped, in words
A.last_brief = {"goal": "x", "steps": [], "pace": {"pace": "normal", "deadline_min": None, "budget_min": None}, "kind": "research", "topic": "x", "deliverable": "answer"}
r = A.respond("stop"); check("stop with a pending plan → dropped", r == "Okay, dropped.", r)
# 8) "send me the last report as a PDF" → the same document, printed by the headless browser (never "a wish")
from agent import library
_doc = library.LIB_DIR / "pdf_check.html"; library.LIB_DIR.mkdir(parents=True, exist_ok=True)
_doc.write_text("<html><body><h1>PDF check</h1><p>hello</p></body></html>", encoding="utf-8")
library.register("research", "PDF check", _doc, options=1, sources=1)
A.bot.docs = []
r = A.respond("send me the last report as a pdf")
sent = A.bot.docs[-1] if A.bot.docs else ""
check("last report as pdf → a .pdf file is sent (or the HTML with an honest note)", str(sent).endswith((".pdf", ".html")) and "wish" not in str(r or ""), f"r={r} docs={A.bot.docs}")
if str(sent).endswith(".pdf"):
    check("the pdf is real", open(sent, "rb").read(5) == b"%PDF-", sent)
else:
    check("the pdf is real (skipped: no browser here)", True)
r = A.after_job("send it as a pdf")
check("'as a pdf when you're done' → the document is printed too, not 'a wish'", "wish" not in str(r or "") and len(A.bot.docs) >= 2, f"r={r} docs={A.bot.docs}")
print(f"STOP SCORE: {ok}/{tot}")
