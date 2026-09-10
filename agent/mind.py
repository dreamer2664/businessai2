"""Thinking (milestone 20): the agent knows what it is doing, why, how it is going, and what it learned.

Three pieces, all cheap (rules first, the thinking model only when it is running):

  Journal   — a live record of the current job: goal, step, what was just done, what comes next, snags. Written by the
              code paths that do the work (`mind.doing(...)`, `mind.snag(...)`) and read back to answer the owner *while*
              the job runs ("what are you doing?", "how long still?", "why?") without stopping it.
  Interrupt — understanding the owner's messages during a job: status question / hurry up / stop / change of plan /
              small talk / a NEW job → the right reaction (answer, speed up, cancel, amend, queue).
  Reflect   — after each job: did it deliver what was asked, in time, with what snags? One lesson per job goes to
              state/lessons.jsonl; the top lessons are shown to the planner in the next brief ("last time X went wrong,
              so this time do Y") and can be read with /lessons.

Everything is plain words: the same journal feeds the live screen and Telegram.
"""
import json
import re
import time

from . import config

LESSONS = config.STATE_DIR / "lessons.jsonl"
JOURNAL = config.STATE_DIR / "journal.jsonl"

STATUS_Q = re.compile(r"\b(what are you doing|what('s| is) (going on|happening|the status)|how('s| is) it going|is it going (well|ok|okay|fine)|are you (still )?(there|working|alive|on it)|status\??|progress|"
                      r"how long( still| more)?( will it take)?|how much (longer|time)|when (will|are) you (be )?(done|finished)|update\??|where are you( at)?|(did|have) you (find|found|got|get) (anything|something|it)( yet)?|"
                      r"any(thing)? (luck|news|results?)( yet)?|che stai facendo|a che punto sei|quanto manca|come va|hai trovato (qualcosa|niente))\b", re.I)
HURRY = re.compile(r"\b(hurry( up)?|faster|quick(er|ly)?|speed (it )?up|wrap (it )?up|finish (it )?(up|now)|i need it now|come on|sbrigati|veloce|fai presto|concludi)\b", re.I)
STOP = re.compile(r"^\W*(stop|cancel|abort|enough|that'?s enough|(ok|okay),? that'?s enough|good enough|you can stop|forget it|never ?mind|drop it|basta( cos[ìi])?|ferma(ti)?|annulla|lascia (stare|perdere))\b", re.I)
WHY = re.compile(r"\b(why|what for|perch[eé]|how come)\b", re.I)
CHAT = re.compile(r"^\W*((ok(ay)?|alright|fine|good|nice|great|cool|perfect|super|wow|lol|haha|thanks?( you)?( a lot| so much)?|thank you|grazie( mille)?|ottimo|perfetto|bene|hi|hello|hey|ciao|👍|❤️|🙏|👌|😊|🙂)[\s,!.]*)+"
                  r"((job|work) so far|so far|then|keep going|go on|continue|carry on|no rush|no hurry|take your time|whenever|con calma|vai pure|continua)?\W*$", re.I)
SLOW_DOWN = re.compile(r"\b(slow down|slower|take (it|your time) (real |really |very )?slow(ly)?|slowly|take it easy|not (so|that|too) fast|too fast|take (around |about )?\d+(\s*(-|–|to)\s*\d+)? ?(h(ou)?rs?|ore)|rallenta|più lento|con calma|non correre|troppo veloce)\b", re.I)
NO_RUSH = re.compile(r"\b(take your time|no rush|no hurry|whenever( you can)?|when you can|no stress|con calma|fai con calma|quando puoi|non c'è fretta)\b", re.I)
CHANGE = re.compile(r"\b(also|and also|instead|rather|only|but|actually|make it|change|switch to|add|include|exclude|not|no more than|max(imum)?|min(imum)?|under|below|above|cheaper|in italy|europe|anche|invece|solo|cambia|"
                    r"don'?t forget|remember (to|the)|make sure|be sure|focus on|prefer|preferably|skip|leave out|ignore|without|non dimenticare|ricordati)\b", re.I)
AFTERWARDS = re.compile(r"\b(when (you'?re |it'?s )?(done|finished|ready)|afterwards|after that|once (you'?re |it'?s )?(done|finished)|at the end|quando (hai finito|finisci)|alla fine)\b", re.I)


def _append(path, rec):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _load(path, limit=None):
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out = []
    for l in (lines[-limit:] if limit else lines):
        try:
            out.append(json.loads(l))
        except Exception:
            continue
    return out


from . import config as _config

QUEUE_FILE = _config.STATE_DIR / "queue.json"


class Mind:
    def __init__(self, planner=None, log=None, pace=None, viewer=None):
        self.planner = planner
        self.log = log or (lambda kind, **f: None)
        self.pace = pace
        self.viewer = viewer
        self.job = None          # {"goal","kind","started","steps","step","done":[...],"snags":[...],"next":"", "why": ""}
        self.queue = []          # jobs the owner asked for while one was running: [(text, t)]
        self.q_load()  # item 7: the queue survives restarts

    # ---- priority queue (item 7): scrape/job high, log medium, brainstorm low ----
    def q_classify(self, item):
        import re
        text = (item.get("goal", "") if isinstance(item, dict) else str(item)).lower()
        if re.search(r"\b(brainstorm|ideas?|idee|think of|what should|which .* should|proponi|che nome|name ideas)\b", text):
            return ("brainstorm", 2)
        if re.search(r"\b(remind|remember|note|log|diary|write down|ricorda|appunta|promemoria|diario)\b", text):
            return ("log", 1)
        if re.search(r"\b(research|scrape|scraping|compare|comparison|visit|watch|suppliers|/shop|shop read|reviews of|cerca|confronta)\b", text):
            return ("scrape", 0)
        return ("job", 0)

    def q_add(self, item, prio=None, kind=None):
        """Queue an owner request (text or brief dict). Returns its 1-based position."""
        k, pr = self.q_classify(item)
        self.queue.append({"item": item, "ts": time.time(),
                           "prio": pr if prio is None else prio, "kind": kind or k})
        self.q_save()
        return len(self.queue)

    def q_next(self):
        """Pop the highest-priority entry (FIFO inside a priority). Returns the entry or None."""
        if not self.queue:
            return None
        i = min(range(len(self.queue)), key=lambda j: (self.queue[j].get("prio", 1), self.queue[j].get("ts", 0)))
        e = self.queue.pop(i)
        self.q_save()
        return e

    def q_peek(self):
        """Next entry without popping (highest priority, FIFO inside), or None."""
        if not self.queue:
            return None
        i = min(range(len(self.queue)), key=lambda j: (self.queue[j].get("prio", 1), self.queue[j].get("ts", 0)))
        return self.queue[i]

    def q_list(self):
        if not self.queue:
            return "Queue's empty — nothing waiting.\n/queue clear · /queue high|med|low <n>"
        names = {0: "HIGH", 1: "med", 2: "low"}
        order = sorted(range(len(self.queue)), key=lambda j: (self.queue[j].get("prio", 1), self.queue[j].get("ts", 0)))
        lines = []
        for n, j in enumerate(order, 1):
            e = self.queue[j]
            it = e["item"]
            label = it.get("goal", "?") if isinstance(it, dict) else str(it)
            lines.append(f"{n}. [{names.get(e.get('prio', 1), '?')}/{e.get('kind', 'job')}] {label[:70]}")
        return "Waiting:\n" + "\n".join(lines) + "\n/queue clear · /queue high|med|low <n>"

    def q_clear(self):
        n = len(self.queue)
        self.queue = []
        self.q_save()
        return n

    def q_set(self, num, prio):
        order = sorted(range(len(self.queue)), key=lambda j: (self.queue[j].get("prio", 1), self.queue[j].get("ts", 0)))
        if num < 1 or num > len(order):
            return None
        e = self.queue[order[num - 1]]
        e["prio"] = prio
        self.q_save()
        return e

    def q_save(self):
        import json
        try:
            QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
            QUEUE_FILE.write_text(json.dumps(self.queue))
        except Exception as e:
            self.log("queue_save_failed", error=str(e)[:120])

    def q_load(self):
        import json
        try:
            raw = json.loads(QUEUE_FILE.read_text())
        except Exception:
            return
        if isinstance(raw, list):
            self.queue = [e for e in raw if isinstance(e, dict) and "item" in e and "prio" in e]
            for e in self.queue:
                e.setdefault("kind", "job")
                e.setdefault("ts", 0)

    # ---- journal -------------------------------------------------------------------------------------------------
    def begin(self, goal, kind="", steps=None, why=""):
        self.job = {"goal": goal, "kind": kind, "started": time.time(), "steps": list(steps or []), "step": 0, "done": [], "snags": [], "next": (steps or [""])[0], "why": why, "hurry": False,
                    "cycle": []}          # item I: one record per step — plan (what + why) → acts (what really happened) → critique (verdict)
        self._open_step(0, (steps or [goal])[0])
        self.log("mind_begin", goal=goal[:80], job=kind)

    # ---- plan → act → critique, per step (item I) -------------------------------------------------------------------
    HOST = re.compile(r"https?://(?:www\.)?([^/\s]+)")

    @staticmethod
    def _host(url):
        m = Mind.HOST.search(str(url or ""))
        return m.group(1) if m else str(url or "")[:40]

    ENGINES = re.compile(r"(^|\.)(duckduckgo|bing|google|yahoo|brave|startpage|ecosia)\.", re.I)

    def _read_act(self, url):
        h = self._host(url)
        return f"searched {h}" if self.ENGINES.search(h) or "/search?" in str(url or "") else f"reading {h}"

    def _cur(self):
        c = self.job.get("cycle") if self.job else None
        return c[-1] if c else None

    def _open_step(self, n, text):
        """A new step begins: close the previous one with a critique, then write the plan for this one in my own words."""
        j = self.job
        if j is None:
            return
        cur = self._cur()
        if cur and cur["n"] == n and not cur["critique"]:
            if text and not cur["acts"]:
                cur["step"] = str(text)[:120]
                cur["plan"] = self._plan_words(cur["step"], j)
            return                                        # same step announced twice → one record
        self._close_step()
        step = str(text or "")[:120]
        j["cycle"].append({"n": n, "step": step, "plan": self._plan_words(step, j), "acts": [], "t0": time.time(), "secs": 0, "critique": "", "verdict": ""})
        j["cycle"] = j["cycle"][-8:]

    def _plan_words(self, step, j):
        n, total = (j["cycle"][-1]["n"] + 2 if j.get("cycle") else 1), max(1, len(j["steps"]))
        return f"{step or j['goal'][:80]} — {self._step_reason(step, j['kind'])}"

    def _act(self, what):
        c = self._cur()
        if c is None:
            return
        c["acts"].append(str(what)[:100])
        c["acts"] = c["acts"][-8:]

    def _close_step(self):
        c = self._cur()
        if c is None or c["critique"]:
            return
        c["secs"] = int(time.time() - c["t0"])
        c["critique"], c["verdict"] = self._judge(c)
        self.log("mind_critique", step=c["n"] + 1, verdict=c["verdict"], words=c["critique"][:120])

    def _judge(self, c):
        """What did this step actually give me, and is it enough? Judged from the acts, in plain words. → (critique, verdict)"""
        acts = c["acts"]
        pages = [a[8:] for a in acts if a.startswith("reading ")]
        searches = [a[9:] for a in acts if a.startswith("searched ")]
        walls = [a for a in acts if a.endswith(" wall")]
        docs = [a for a in acts if a.startswith("document written")]
        sellers = [a for a in acts if a.startswith("checking seller")]
        secs = c["secs"]
        if docs:
            return f"{docs[-1]} after {secs} s — the deliverable exists; I check it reads well before handing it over.", "ok"
        if sellers:
            return f"{len(sellers)} seller(s) checked ({', '.join(x[16:] for x in sellers[:3])}) in {secs} s" + (f", {len(walls)} behind walls" if walls else "") + " — enough to judge.", "ok"
        if pages and not walls:
            return (f"{len(pages)} page(s) read ({', '.join(pages[:3])}) in {secs} s, no walls — " +
                    ("enough to go on." if len(pages) >= 2 else "one source only; I look for a second before I trust it."),
                    "ok" if len(pages) >= 2 else "thin")
        if pages and walls:
            return (f"{len(pages)} page(s) read, {len(walls)} blocked ({'; '.join(walls[:2])}) — " +
                    ("enough; the blocked sites go last next time." if len(pages) >= 2 else "thin; I widen the search rather than fight the wall."),
                    "ok" if len(pages) >= 2 else "thin")
        if walls:
            return f"nothing readable: {'; '.join(walls[:3])} — I change the angle or the site instead of retrying the wall.", "redo"
        if searches and not pages:
            return f"searched {', '.join(searches[:2])} in {secs} s — results in hand, the reading is the next step.", "ok"
        if secs >= 90 and not acts:
            return f"{secs} s on this step with nothing to show — I move on and say so.", "redo"
        if acts:
            return f"{acts[-1][:70]} — done in {secs} s.", "ok"
        return "no pages needed here — decided from what I already had.", "ok"

    def cycle(self):
        """The plan → act → critique records of the running job (newest last), for the viewer and /thinking."""
        if not self.job:
            return []
        out = []
        for c in self.job.get("cycle", []):
            out.append({"n": c["n"] + 1, "step": c["step"], "plan": c["plan"], "acts": list(c["acts"]),
                        "critique": c["critique"] or "…still on it", "verdict": c["verdict"] or "doing",
                        "secs": c["secs"] or int(time.time() - c["t0"])})
        return out

    def doing(self, what, step=None):
        """Called by the work: 'reading reviews of CorkStep (2 of 4)'. Keeps the last 12 entries."""
        if not self.job:
            return
        j = self.job
        j["done"].append((time.strftime("%H:%M"), what[:140]))
        j["done"] = j["done"][-12:]
        if step is not None:
            j["step"] = step
            j["next"] = j["steps"][step + 1] if step + 1 < len(j["steps"]) else "finishing and writing it up"
            self._open_step(step, j["steps"][step] if step < len(j["steps"]) else what)
            if self.viewer:
                self.viewer.plan_step(step, what[:80])
        else:
            self._act("→ " + str(what)[:96])
        _append(JOURNAL, {"t": time.strftime("%Y-%m-%dT%H:%M"), "goal": j["goal"][:80], "what": what[:140]})

    def snag(self, what):
        if self.job:
            self.job["snags"].append(what[:160])
            self.job["snags"] = self.job["snags"][-8:]
        self.log("mind_snag", what=what[:120])

    def elapsed(self):
        return int(time.time() - self.job["started"]) if self.job else 0

    def status_line(self):
        """One honest paragraph about the job in progress — for the owner, mid-job."""
        j = self.job
        if not j:
            return "Nothing running right now — I'm free."
        el = self.elapsed()
        el_t = f"{el // 60} min {el % 60} s" if el >= 60 else f"{el} s"
        last = j["done"][-1][1] if j["done"] else "just started"
        n, total = j["step"] + 1, max(1, len(j["steps"]))
        out = [f"I'm on: {j['goal'][:120]} — step {min(n, total)} of {total}, {el_t} in.", f"Right now: {last}."]
        if j["next"]:
            out.append(f"Next: {j['next'][:100]}.")
        if self.pace and self.pace.active():
            r = self.pace.remaining()
            if r is not None:
                out.append("Time: " + (f"{int(r // 60)} min left of what you gave me." if r > 0 else f"{int(-r // 60)} min past your time — wrapping up."))
        if j["snags"]:
            out.append("Snags so far: " + "; ".join(j["snags"][-2:]) + ".")
        checked = [c for c in j.get("cycle", []) if c["critique"]]
        if checked:
            out.append(f"Last check (step {checked[-1]['n'] + 1}): {checked[-1]['critique']}")
        if self.queue:
            out.append(f"Queued after this: {len(self.queue)} request(s).")
        return " ".join(out)

    def why_line(self):
        j = self.job
        if not j:
            return "Nothing running, so nothing to explain — ask me why about a plan and I'll tell you."
        if j.get("why"):
            return j["why"]
        step = j["steps"][j["step"]] if j["steps"] and j["step"] < len(j["steps"]) else ""
        return f"Because you asked for “{j['goal'][:100]}”. This step ({step[:80]}) is how I get there: " + self._step_reason(step, j["kind"])

    @staticmethod
    def _step_reason(step, kind):
        s = step.lower()
        if "review" in s or "complaint" in s:
            return "reviews and complaints are where a bad seller shows before the price does."
        if "social" in s:
            return "a live social page with real comments is hard to fake and shows how they treat buyers."
        if "search" in s or "candidates" in s:
            return "I need a few options before I can rank anything."
        if "listing" in s or s.startswith("open each") or "price, condition" in s:
            return "the listing itself tells me price, shipping and where it ships from — the facts the verdict rests on."
        if s.startswith("judge") or "reliab" in s or "verdict" in s:
            return "this is where I weigh what I read into a yes / no / careful, with the reasons."
        if "keep" in s and ("fact" in s or "figure" in s or "key point" in s):
            return "only figures with a source survive into the report; the rest is noise."
        if "comment" in s:
            return "the most-liked comment shows what viewers actually took from it."
        if "caption" in s or "transcript" in s:
            return "the captions are the video's own words, faster and more exact than watching."
        if "offer" in s and "shop" in s:
            return "the store is yours — I propose, you decide."
        if "document" in s or "write" in s:
            return "you asked for something you can read and click, not a chat dump."
        if "check" in s and "browser" in s:
            return "I look at my own work before handing it over."
        if kind == "build_site":
            return "a site is only done when the pages are written, built and checked."
        return "it is the shortest path I know to what you asked."

    def on_event(self, kind, f):
        """Listener on the live screen's event stream: turns steps, page opens and walls into journal lines (no code in the
        tools has to know about the journal)."""
        if not self.job:
            return
        try:
            if kind == "plan_step":
                n = int(f.get("n", 1)) - 1
                note = str(f.get("text", ""))[:120]
                planned = self.job["steps"][n] if 0 <= n < len(self.job["steps"]) else note
                self._open_step(n, planned)
                if note and note != planned:
                    self._act("→ " + note[:96])
                self._doing_quiet(note, n)
            elif kind == "browser_open":
                self._act(self._read_act(f.get("url", "")))
                self._doing_quiet(f"reading {str(f.get('url', ''))[:90]}")
            elif kind == "seller_check":
                self._act(f"checking seller {f.get('name', '')}")
                self._doing_quiet(f"checking seller {f.get('name', '')}")
            elif kind in ("task_wall", "search_engine_skip"):
                self._act(f"{self._host(f.get('url')) or f.get('engine')}: {f.get('wall') or f.get('reason')} wall")
                self.snag(f"{f.get('url') or f.get('engine')}: {f.get('wall') or f.get('reason')} wall")
            elif kind == "research_widen":
                bits = [f"{k} {v}" for k, v in f.items() if v and v not in (False, 0, "0") and k != "second"] + ([f"2nd engine {f['second']}"] if f.get("second") else [])
                self._act("widened: " + (", ".join(bits) if bits else "nothing new")[:80])
                self._doing_quiet("looking in more places (time left)")
            elif kind == "captcha_passed":
                self._act("solved a checkbox CAPTCHA")
                self._doing_quiet("solved a checkbox CAPTCHA")
            elif kind in ("login_failed", "signup_error", "transcript_failed", "listing_failed", "image_failed", "look_failed"):
                self.snag(f"{kind.replace('_', ' ')}: {str(f.get('error') or f.get('note') or f.get('site') or '')[:60]}")
            elif kind == "pace_late":
                self.snag("past the owner's time")
            elif kind == "doc_saved":
                self._act(f"document written: {str(f.get('title', ''))[:60]}")
                self._doing_quiet(f"document written: {f.get('title', '')}")
        except Exception:
            pass

    def _doing_quiet(self, what, step=None):
        """doing() without echoing the step back to the viewer (the viewer is where it came from)."""
        j = self.job
        j["done"].append((time.strftime("%H:%M"), what[:140]))
        j["done"] = j["done"][-12:]
        if step is not None:
            j["step"] = step
            j["next"] = j["steps"][step + 1] if step + 1 < len(j["steps"]) else "finishing and writing it up"
        _append(JOURNAL, {"t": time.strftime("%Y-%m-%dT%H:%M"), "goal": j["goal"][:80], "what": what[:140]})

    # ---- interruptions -----------------------------------------------------------------------------------------------
    def interrupt(self, text):
        """What does a message *during a job* mean? → ('status'|'why'|'hurry'|'stop'|'chat'|'change'|'new', reply_or_None)."""
        t = text.strip()
        if STOP.search(t) and len(t.split()) <= 4:
            if self.job and self.job.get("stop_asked") and time.time() - self.job["stop_asked"] < 90:
                self.job["stop_again"] = self.job.get("stop_again", 0) + 1
                return "stop_again", ("Still stopping — I'm closing the page I'm on and hand over what I have in a moment (no new pages are opened). "
                                      "If nothing arrives within a minute, say 'stop' once more and I drop the result altogether.")
            if self.job:
                self.job["stop_asked"] = time.time()
            return "stop", None
        if STATUS_Q.search(t):
            return "status", self.status_line()
        unquoted = re.sub(r"[\"“”'‘’]([^\"“”'‘’]{1,40})[\"“”'‘’]", " ", t)          # 'you put "quick" as timing' talks about the word
        if SLOW_DOWN.search(unquoted) or (re.search(r"\b(said|told you|ho detto)\b", t, re.I) and re.search(r"\b(slow|hours?|ore)\b", t, re.I)):
            floor = budget = None
            try:
                from .brief import parse_pace
                pp = parse_pace(t)
                floor, budget = pp.get("floor_min"), pp.get("budget_min")
            except Exception:
                pass
            if self.job:
                self.job["hurry"] = False
            if self.pace:
                try:
                    self.pace.slow_now(floor, budget)
                except Exception:
                    pass
            span = (f" — at least {floor // 60} h" + (f" {floor % 60} min" if floor % 60 else "") if floor else "")
            span += (f", up to {budget // 60} h" if budget and budget != floor else "")
            return "hurry", f"Slowing down{span}: I take the long path from here (more listings, full reviews) and keep going until the time is used. Nothing is rushed."
        if HURRY.search(unquoted):
            if self.job:
                self.job["hurry"] = True
            if self.pace:
                try:
                    self.pace.hurry_now()
                except Exception:
                    pass
            return "hurry", "Speeding up — I'll skip the nice-to-haves and hand you what I have as soon as it's usable."
        if WHY.search(t) and len(t.split()) <= 8:
            return "why", self.why_line()
        if NO_RUSH.search(t) and len(t.split()) <= 8:
            if self.job:
                self.job["hurry"] = False
            return "chat", "Thanks — I'll do it properly then, and tell you when it's ready."
        if CHAT.search(t):
            return "chat", None
        if self.job and AFTERWARDS.search(t) and len(t.split()) <= 16 and not re.search(r"https?://", t):
            self.job.setdefault("after", []).append(t.strip())
            return "after", f"Will do, right after this job: “{t.strip()[:80]}”."
        if self.job and len(t.split()) <= 14 and CHANGE.search(t) and not re.search(r"https?://", t):
            return "change", None
        return "new", None

    # ---- reflection -------------------------------------------------------------------------------------------------
    def reflect(self, outcome, delivered=True, note=""):
        """Close the job: judge it, keep a lesson. outcome: short text of what was handed over (or the error)."""
        j = self.job
        if not j:
            return None
        el = self.elapsed()
        late = False
        if self.pace:
            try:
                r = self.pace.remaining()
                late = r is not None and r < 0
            except Exception:
                late = False
        self._close_step()                                  # the last step gets its critique too
        lesson = self._lesson(j, outcome, delivered, late, note)
        rec = {"t": time.strftime("%Y-%m-%dT%H:%M"), "goal": j["goal"][:120], "kind": j["kind"], "seconds": el, "delivered": bool(delivered),
               "late": late, "snags": j["snags"][-4:], "outcome": (outcome or "")[:200], "lesson": lesson,
               "cycle": [{"n": c["n"] + 1, "step": c["step"][:80], "secs": c["secs"], "verdict": c["verdict"], "critique": c["critique"][:160]} for c in j.get("cycle", [])],
               # is this lesson advice for the next plan? only when something was actually wrong with the PLAN (a clean run is a record,
               # not a warning; a broken machine — browser missing, no memory — is a repair for the owner, not a lesson for the planner)
               "improve": bool((not delivered and not self.machine_fault(outcome or note)) or late or j.get("hurry") or len(j["snags"]) >= 3
                               or any(c["verdict"] in ("thin", "redo") for c in j.get("cycle", []))),
               "machine": bool(not delivered and self.machine_fault(outcome or note))}
        _append(LESSONS, rec)
        self.log("mind_reflect", job=j["kind"], seconds=el, delivered=delivered, late=late, lesson=lesson[:100])
        self.job = None
        return rec

    MACHINE_FAULT = re.compile(r"(BrowserType\.launch|Executable doesn't exist|No module named|ModuleNotFoundError|playwright install|"
                               r"cannot allocate memory|MemoryError|No space left|Errno 28|Target page, context or browser has been closed|"
                               r"llama-server|connection refused|Failed to establish a new connection|ENOSPC|out of memory)", re.I)

    def machine_fault(self, text):
        """Was this failure the machine's (browser not installed, module missing, disk/memory), not the job's plan?"""
        return bool(text and self.MACHINE_FAULT.search(str(text)))

    def _lesson(self, j, outcome, delivered, late, note):
        snags = " ".join(j["snags"]).lower()
        if not delivered and re.search(r"is not a web address|ERR_NAME_NOT_RESOLVED at https?://\w+ ", outcome or note or "", re.I):
            return f"{j['kind']}: I treated plain words as a web address — that was a planning slip, not a site problem; the plan step should have been an answer."
        if j.get("stop_again") or (j.get("stop_asked") and not delivered):
            return f"{j['kind']}: the owner had to say stop more than once — check the stop flag between every page, not only between listings."
        if not delivered:
            if self.machine_fault(outcome or note):
                what = "the browser is not installed" if re.search(r"BrowserType\.launch|Executable doesn't exist|playwright install", outcome or note, re.I) else \
                    "a Python module is missing" if re.search(r"No module named|ModuleNotFoundError", outcome or note, re.I) else \
                    "the machine ran out of memory or disk" if re.search(r"memory|space left|ENOSPC|Errno 28", outcome or note, re.I) else "the machine, not the plan"
                return f"{j['kind']}: could not even start — {what} (fix on the PC: the doctor line in docs/INSTALL_WINDOWS.md). The plan itself was fine."
            if "captcha" in snags or "captcha" in (outcome or "").lower():
                return f"{j['kind']}: a CAPTCHA wall stopped me — next time try another site first and keep the walled one last."
            if "timeout" in snags or "timed out" in (outcome or "").lower():
                return f"{j['kind']}: a page hung and ate the time budget — set shorter per-page limits and move on sooner."
            return f"{j['kind']}: I did not deliver ({(outcome or note)[:80]}) — start with the cheapest reliable source next time."
        if late:
            return f"{j['kind']}: delivered but late by my own clock — open fewer pages up front, write earlier, refine only if time is left."
        if j.get("hurry"):
            return f"{j['kind']}: the owner had to hurry me — send a first usable version sooner, then improve."
        site_snags = [x for x in j["snags"] if not re.search(r"^owner (said|changed)", x)]
        if len(site_snags) >= 3:
            return f"{j['kind']}: many snags ({site_snags[0][:50]}…) — check the site's walls before planning around it."
        cyc = j.get("cycle", [])
        if self.planner and self.planner.installed() and (j["done"] or cyc):
            try:
                steps = "\n".join(f"step {c['n'] + 1} '{c['step']}' ({c['secs']} s): did {', '.join(c['acts']) or 'nothing visible'} → {c['critique']}" for c in cyc[-6:])
                out = self.planner.chat("You review your own work as a careful assistant. One sentence, concrete, no praise.",
                                        f"Job: {j['goal']}\nWhat happened, step by step:\n{steps or '; '.join(d[1] for d in j['done'][-8:])}\nSnags: {'; '.join(j['snags']) or 'none'}\nResult: {outcome[:300]}\n\nWrite ONE lesson for next time (max 25 words), or 'none' if nothing to improve.",
                                        max_tokens=60, timeout=90).strip()
                if out and out.lower() != "none" and len(out) < 220:
                    return f"{j['kind']}: {out}"
            except Exception:
                pass
        return f"{j['kind']}: {self._own_words(j, cyc)}"

    def _own_words(self, j, cyc):
        """The lesson without a model: built from what this job's steps actually did (hosts, seconds, verdicts), never a stock line."""
        el = self.elapsed()
        weak = [c for c in cyc if c["verdict"] in ("thin", "redo")]
        slow = max(cyc, key=lambda c: c["secs"]) if cyc else None
        hosts = []
        for c in cyc:
            for a in c["acts"]:
                if a.startswith("reading ") and a[8:] not in hosts:
                    hosts.append(a[8:])
        if weak:
            c = weak[0]
            return f"step {c['n'] + 1} ({c['step'][:50]}) was the weak point — {c['critique'][:110]}"
        if slow and slow["secs"] >= 60 and el >= 120 and slow["secs"] >= 0.5 * el:
            return f"step {slow['n'] + 1} ({slow['step'][:50]}) took {slow['secs']} s of {el} s — start there next time, or cap it."
        if hosts:
            return f"{len(hosts)} source(s) did the work ({', '.join(hosts[:3])}) in {el // 60} min {el % 60} s — start from those next time on this topic."
        if cyc:
            return f"{len(cyc)} step(s) in {el // 60} min {el % 60} s without a snag — nothing to change."
        return f"done in {el // 60} min — nothing to change."

    # ---- what the past says about a new job ------------------------------------------------------------------------
    ADVICE_DAYS = 14          # a lesson older than this is history, not advice

    def advice(self, kind, topic=""):
        """Lessons from earlier jobs of the same kind (most recent first, max 3) — shown in the plan and given to the planner.
        Only real plan lessons: not machine faults (old records included), not older than ADVICE_DAYS, and nothing from before the
        last clean run of the same kind — once a job went fine, the earlier warnings have been answered."""
        recs = [r for r in _load(LESSONS) if r.get("kind") == kind]
        cut = time.strftime("%Y-%m-%dT%H:%M", time.localtime(time.time() - self.ADVICE_DAYS * 86400))
        clean = [i for i, r in enumerate(recs) if r.get("delivered") and not r.get("late") and not r.get("improve", False)]
        recs = recs[clean[-1] + 1:] if clean else recs                 # only what happened after the last clean run (file order = time order)
        seen, out = set(), []
        for r in reversed(recs):
            if r.get("t", "") < cut:
                continue
            if r.get("machine") or self.machine_fault(r.get("outcome", "")) or self.machine_fault(r.get("lesson", "")):
                continue
            if not r.get("improve", not r["lesson"].endswith("keep the same order of steps.")):
                continue
            l = r["lesson"].split(": ", 1)[-1]
            if l not in seen:
                seen.add(l)
                out.append(l)
            if len(out) >= 3:
                break
        return out

    def lessons_text(self, limit=8):
        """/lessons — the last real lessons; a run of identical machine faults (browser missing ×5) is folded into one honest line."""
        recs = _load(LESSONS)
        if not recs:
            return "No lessons yet — I write one after every job."
        out, faults = [], 0
        for r in reversed(recs):
            if r.get("machine") or (not r.get("delivered", True) and self.machine_fault(r.get("outcome", "") + " " + r.get("lesson", ""))):
                faults += 1
                if faults > 1:
                    continue
                line = f"• {r['t'][5:16].replace('T', ' ')} · {r['kind']}: could not start — the machine was broken (browser or module missing), not the plan."
            else:
                line = f"• {r['t'][5:16].replace('T', ' ')} · {r['lesson']}"
            out.append(line)
            if len(out) >= limit:
                break
        if faults > 1:
            out = [l + (f" ({faults} such runs)" if "could not start" in l else "") for l in out]
        return "🧠 What I learned from my last jobs:\n" + "\n".join(out)

    def think_snapshot(self):
        """Live beliefs for the thinking panel (item 9): why + status + recent lessons + queue."""
        recs = _load(LESSONS, limit=3)
        if self.queue:
            highs = sum(1 for e in self.queue if e.get("prio", 1) == 0)
            q = f"{len(self.queue)} waiting" + (f" ({highs} HIGH)" if highs else "")
        else:
            q = "empty"
        return {"why": self.why_line()[:300], "status": self.status_line()[:480],
                "lessons": [r.get("lesson", "")[:160] for r in reversed(recs)],
                "queue": q, "cycle": self.cycle()}

    def thinking_text(self):
        """The panel in plain words — one source for the viewer, /thinking, and any agent reader."""
        s = self.think_snapshot()
        lines = ["\U0001F9E0 What I'm thinking:", "Why: " + s["why"], s["status"], "Queue: " + s["queue"] + "."]
        if s.get("cycle"):
            lines.append("Step by step:")
            for c in s["cycle"][-4:]:
                lines.append(f"{c['n']}. plan: {c['plan'][:120]}")
                if c["acts"]:
                    lines.append(f"   did: {', '.join(c['acts'][-4:])[:140]}")
                lines.append(f"   check: {c['critique'][:140]}")
        if s["lessons"]:
            lines.append("Recent lessons:")
            lines += ["\u2022 " + l for l in s["lessons"]]
        return "\n".join(lines)

    def stats_text(self):
        recs = _load(LESSONS)
        if not recs:
            return "no jobs reflected on yet"
        n = len(recs)
        ok = sum(1 for r in recs if r.get("delivered"))
        late = sum(1 for r in recs if r.get("late"))
        avg = sum(r.get("seconds", 0) for r in recs) / n
        return f"{n} jobs reflected on · {ok} delivered · {late} late · avg {avg / 60:.0f} min"
