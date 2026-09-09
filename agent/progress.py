"""Progress in Google Docs (owner's item D): the owner follows a long job from his phone or laptop without asking.

Two documents, both native Google Docs in the library folder, shared read-only by link:

* the **day log** ("Business AI — <date>"): one per calendar day, every job appends its start, its steps as they
  happen, snags, the result and the document link. It is the heartbeat for long sessions: a line every few minutes
  while something runs, so a silent phone never means a dead agent.
* one **job log** per long job (started when the pace says slow / a budget or a floor of ≥ 30 min applies, or when the
  job runs longer than JOB_DOC_AFTER seconds): plan, steps, snags, mid-job changes, result. Its link goes to the owner
  with the first message ("follow along here") and again with the result.

Everything is buffered and flushed at most every FLUSH_EVERY seconds (the Docs API is chatty: one append = 2 calls),
never raises, and stays silent when Google is not connected. The writes run in a small worker thread so a slow API
never stalls the hands.

Templates (owner's item D): every finished job gets a Doc through `Templates.<kind>(...)` — native Docs with a
heading, a summary box, a table and per-option bullets, one shape per kind (research cards, trending table, deal
alert / seller check, site report, plain note). They are used by core when a job finishes.
"""
import datetime as _dt
import json
import queue
import threading
import time

from . import config

FLUSH_EVERY = 90          # seconds between appends to the same doc (batched)
JOB_DOC_AFTER = 20 * 60   # a job running this long gets its own doc even when nobody asked for slow pace
MAX_LINE = 240

STATE = config.STATE_DIR / "progress.json"


def _now():
    return _dt.datetime.now().strftime("%H:%M")


class Progress:
    def __init__(self, google=None, log=None):
        self.google = google
        self.log = log or (lambda kind, **f: None)
        self.state = self._load()
        self.q = queue.Queue()
        self.buf = {}                       # doc_id → [blocks]
        self.last_flush = {}                # doc_id → epoch
        self.job = None                     # {"goal", "kind", "started", "doc": id|None, "link", "lines": n, "steps": [...]}
        self._lock = threading.Lock()
        self._worker = threading.Thread(target=self._run, daemon=True, name="progress")
        self._worker.start()

    # ---- state -----------------------------------------------------------------------------
    def _load(self):
        try:
            return json.loads(STATE.read_text())
        except Exception:
            return {}

    def _save(self):
        try:
            STATE.parent.mkdir(parents=True, exist_ok=True)
            STATE.write_text(json.dumps(self.state))
        except Exception:
            pass

    def connected(self):
        try:
            return bool(self.google and self.google.connected())
        except Exception:
            return False

    # ---- the day log -----------------------------------------------------------------------
    def day_doc(self, create=True):
        """(doc_id, link) of today's log; created on first use. None when Google is off."""
        if not self.connected():
            return None, None
        today = _dt.date.today().isoformat()
        d = self.state.get("day") or {}
        if d.get("date") == today and d.get("id"):
            return d["id"], d["link"]
        if not create:
            return None, None
        try:
            doc = self.google.docs_create(f"Business AI — {_dt.date.today():%A %d %B %Y}", folder="Progress", share=True)
        except Exception as e:
            self.log("progress_day_doc_failed", error=str(e)[:120])
            return None, None
        self.state["day"] = {"date": today, "id": doc["id"], "link": doc["link"]}
        self._save()
        self._append(doc["id"], [("h1", f"Business AI — {_dt.date.today():%A %d %B %Y}"),
                                 ("p", "What I did today, as it happened. One line per step of every job, newest at the bottom. "
                                       "Long jobs get their own document — its link is in the line that starts them.")], now=True)
        return doc["id"], doc["link"]

    def day_link(self):
        _, link = self.day_doc(create=False)
        return link

    # ---- jobs --------------------------------------------------------------------------------
    def begin(self, goal, kind="", steps=(), pace=None, long=False):
        """A job starts. long=True (slow pace / budget / floor / explicit ask) → its own doc right away.
        Returns the job-doc link or None."""
        with self._lock:
            self.job = {"goal": str(goal)[:200], "kind": kind, "started": time.time(), "doc": None, "link": None, "lines": 0,
                        "steps": [str(s)[:MAX_LINE] for s in (steps or [])], "promoted": False}
        why = ""
        if pace is not None:
            try:
                if getattr(pace, "floor_until", None):
                    why = f"at least {int((pace.floor_until - pace.started) / 60)} min, as you asked"
                elif getattr(pace, "budget_until", None):
                    why = "you are away — quiet time"
                elif getattr(pace, "deadline_min", None):
                    why = f"you want it within {pace.deadline_min} min"
                elif getattr(pace, "mode", "") == "slow":
                    why = "slow pace"
            except Exception:
                why = ""
        line = f"{_now()} ▶ {self.job['goal']}" + (f" ({kind})" if kind else "") + (f" — {why}" if why else "")
        did, _ = self.day_doc()
        if did:
            self._append(did, [("p", line)] + ([("bullet", s) for s in self.job["steps"][:7]] if self.job["steps"] else []))
        if long or (pace is not None and (getattr(pace, "mode", "") == "slow" or getattr(pace, "floor_until", None) or getattr(pace, "budget_until", None))):
            return self._open_job_doc(why)
        return None

    def _open_job_doc(self, why=""):
        if not self.connected() or not self.job or self.job.get("doc"):
            return self.job.get("link") if self.job else None
        try:
            title = f"Job log — {self.job['goal'][:70]} — {_dt.datetime.now():%d %b %H:%M}"
            doc = self.google.docs_create(title, folder="Progress", share=True)
        except Exception as e:
            self.log("progress_job_doc_failed", error=str(e)[:120])
            return None
        self.job["doc"], self.job["link"] = doc["id"], doc["link"]
        blocks = [("h1", self.job["goal"]), ("p", f"Started {_dt.datetime.now():%d %b %Y %H:%M}" + (f" · {why}" if why else "") + ". This page fills in while I work; the result and the document link land at the bottom.")]
        if self.job["steps"]:
            blocks.append(("h2", "Plan"))
            blocks += [("bullet", s) for s in self.job["steps"]]
        blocks.append(("h2", "As it happens"))
        self._append(doc["id"], blocks, now=True)
        did, _ = self.day_doc()
        if did:
            self._append(did, [("p", f"{_now()} 📝 follow this job here: {doc['link']}")])
        self.log("progress_job_doc", link=doc["link"])
        return doc["link"]

    def step(self, text):
        """One line: a plan step, a page read, a snag. Cheap; buffered."""
        if not self.job:
            return
        text = str(text or "").strip()
        if not text:
            return
        line = f"{_now()} — {text[:MAX_LINE]}"
        self.job["lines"] += 1
        if not self.job.get("doc") and not self.job.get("promoted") and time.time() - self.job["started"] > JOB_DOC_AFTER:
            self.job["promoted"] = True
            self._open_job_doc("running long")
        if self.job.get("doc"):
            self._append(self.job["doc"], [("p", line)])
        did, _ = self.day_doc(create=False)
        if did and (self.job["lines"] <= 3 or self.job["lines"] % 5 == 0):     # the day log stays readable: first steps, then every 5th
            self._append(did, [("p", "   " + line)])

    def snag(self, text):
        self.step("⚠️ " + str(text))

    def change(self, text):
        self.step("✏️ you changed: " + str(text))

    def finish(self, outcome, doc_link=None, delivered=True):
        """The job ends: result line (+ document link) in both docs. Returns the job-doc link (for the final message)."""
        if not self.job:
            return None
        took = int(time.time() - self.job["started"])
        line = f"{_now()} {'✅' if delivered else '❌'} {str(outcome or '').strip()[:MAX_LINE]} ({took // 60} min {took % 60} s)" + (f" · document: {doc_link}" if doc_link else "")
        link = self.job.get("link")
        if self.job.get("doc"):
            self._append(self.job["doc"], [("h2", "Result"), ("p", line)], now=True)
        did, _ = self.day_doc(create=False)
        if did:
            self._append(did, [("p", line)], now=True)
        self.job = None
        return link

    def heartbeat(self, busy_text):
        """Called from the main loop every few minutes while a job runs: one 'still on it' line in the job doc when nothing
        else was written for a while (a silent phone must never mean a dead agent)."""
        if not self.job or not self.job.get("doc"):
            return
        last = self.last_flush.get(self.job["doc"], self.job["started"])
        if time.time() - last > 8 * 60 and not self.buf.get(self.job["doc"]):
            self._append(self.job["doc"], [("p", f"{_now()} — still on it: {str(busy_text or self.job['goal'])[:120]}")], now=True)

    # ---- viewer hook -------------------------------------------------------------------------
    def on_event(self, kind, f):
        """Listener on the live screen's events (same stream Mind uses) → progress lines. Never raises."""
        if not self.job:
            return
        try:
            if kind == "plan_step":
                self.step(f"step {f.get('n')}: {str(f.get('text', ''))[:160]}")
            elif kind == "browser_open":
                self.step(f"reading {str(f.get('url', ''))[:120]}")
            elif kind == "seller_check":
                self.step(f"checking seller {f.get('name', '')}")
            elif kind in ("task_wall", "search_engine_skip"):
                self.snag(f"{f.get('url') or f.get('engine')}: {f.get('wall') or f.get('reason')} wall")
            elif kind == "market_search_note":
                self.snag(f"{f.get('site')}: {f.get('note')}")
            elif kind in ("listing_failed", "transcript_failed", "login_failed"):
                self.snag(f"{kind.replace('_', ' ')}: {str(f.get('error') or f.get('url') or '')[:80]}")
            elif kind == "pace_late":
                self.snag("past the time you gave me")
            elif kind == "doc_saved":
                self.step(f"wrote the document: {f.get('title', '')}")
        except Exception:
            pass

    # ---- plumbing ------------------------------------------------------------------------------
    def _append(self, doc_id, blocks, now=False):
        with self._lock:
            self.buf.setdefault(doc_id, []).extend(blocks)
        if now or time.time() - self.last_flush.get(doc_id, 0) >= FLUSH_EVERY:
            self.q.put(doc_id)

    def flush(self, doc_id=None, timeout=20):
        """Push everything pending (used at shutdown and by tests). Synchronous, best effort."""
        ids = [doc_id] if doc_id else list(self.buf.keys())
        for d in ids:
            self._flush_one(d)

    def _flush_one(self, doc_id):
        with self._lock:
            blocks = self.buf.pop(doc_id, [])
        if not blocks:
            return
        self.last_flush[doc_id] = time.time()
        try:
            self.google.docs_write_blocks(doc_id, blocks)
        except Exception as e:
            self.log("progress_write_failed", error=str(e)[:120], n=len(blocks))

    def _run(self):
        while True:
            try:
                doc_id = self.q.get(timeout=FLUSH_EVERY)
                self._flush_one(doc_id)
            except queue.Empty:
                for d in list(self.buf.keys()):                   # timed flush of whatever waited
                    if time.time() - self.last_flush.get(d, 0) >= FLUSH_EVERY:
                        self._flush_one(d)
            except Exception as e:
                self.log("progress_worker_error", error=str(e)[:120])
                time.sleep(2)


# ---- native Doc templates per job kind (item D) -------------------------------------------------------

def _cell(x, n=180):
    s = str(x if x is not None else "")
    return s if len(s) <= n else s[:n - 1] + "…"


class Templates:
    """Blocks for google.docs_write_blocks — one shape per job kind. Pure functions: easy to test offline."""

    @staticmethod
    def research(topic, summary, pages, sources=()):
        """pages: [{title, url, points:[...]}]."""
        b = [("h1", f"Research: {topic}"), ("p", f"{len(pages)} pages read · {_dt.datetime.now():%d %b %Y %H:%M} · written by Business AI"),
             ("h2", "In short"), ("p", summary or "Key points per page below; the most useful pages come first.")]
        if pages:
            b.append(("h2", "Pages, side by side"))
            b.append(("table", [["#", "Page", "Key point"]] + [[str(i + 1), _cell(p.get("title", ""), 70), _cell((p.get("points") or [""])[0], 160)] for i, p in enumerate(pages)]))
        for i, p in enumerate(pages):
            b.append(("h2", f"{i + 1}. {_cell(p.get('title', ''), 90)}"))
            b.append(("p", p.get("url", "")))
            b += [("bullet", _cell(k, 300)) for k in (p.get("points") or [])[:5]]
        srcs = list(dict.fromkeys(list(sources) + [p.get("url", "") for p in pages if p.get("url")]))
        if srcs:
            b.append(("h2", "Sources — pages I read"))
            b += [("bullet", s) for s in srcs]
        return b

    @staticmethod
    def trending(title, note, videos):
        """videos: [{title, url, channel, views, published, length, top_comment:{author, likes, text}|None}]."""
        b = [("h1", title), ("p", f"top {len(videos)} by views · {_dt.datetime.now():%d %b %Y %H:%M} · written by Business AI"), ("h2", "In short"), ("p", note or "")]
        b.append(("table", [["#", "Video", "Channel", "Views", "Uploaded", "Length"]] +
                           [[str(i + 1), _cell(v.get("title", ""), 80), _cell(v.get("channel", ""), 30), f"{v['views']:,}" if v.get("views") else "", _cell(v.get("published", ""), 20), _cell(v.get("length", ""), 10)] for i, v in enumerate(videos)]))
        for i, v in enumerate(videos):
            b.append(("h2", f"{i + 1}. {_cell(v.get('title', ''), 90)}"))
            b.append(("p", v.get("url", "")))
            tc = v.get("top_comment")
            b.append(("bullet", f"Top comment — {tc['author']} ({tc.get('likes', 0):,} ♥): {_cell(tc.get('text', ''), 300)}" if tc else "Top comment: not readable (comments off or hidden)"))
        return b

    @staticmethod
    def seller_check(product, summary, options, conditions=""):
        """options: [{seller, url, grade, verdict, facts:{}, pros:[], cons:[]}] — the deal alert / seller check shape."""
        b = [("h1", f"{product} — seller check"), ("p", f"{len(options)} options researched · read-only, nothing bought or contacted" + (f" · your conditions: {conditions}" if conditions else "") + f" · {_dt.datetime.now():%d %b %Y %H:%M}"),
             ("h2", "In short"), ("p", summary or "")]
        mark = {"good": "👍 good", "ok": "🤔 ok", "bad": "👎 avoid"}
        b.append(("h2", "Side by side"))
        b.append(("table", [["Seller", "Price", "Shipping", "From", "Verdict"]] +
                           [[_cell(o.get("seller", "?"), 30), _cell((o.get("facts") or {}).get("Price", "-"), 14), _cell((o.get("facts") or {}).get("Shipping", "-"), 30),
                             _cell((o.get("facts") or {}).get("Ships from / origin", "-"), 20), mark.get(o.get("grade", "ok"), o.get("grade", ""))] for o in options]))
        for i, o in enumerate(options):
            f = {k: v for k, v in (o.get("facts") or {}).items() if not str(k).startswith("_") and v}
            b.append(("h2", f"{i + 1}. {_cell(o.get('seller', '?'), 40)} — {mark.get(o.get('grade', 'ok'), '')}"))
            b.append(("p", o.get("url", "")))
            if o.get("verdict"):
                b.append(("p", _cell(o["verdict"], 300)))
            if f:
                b.append(("table", [[k, _cell(v, 160)] for k, v in list(f.items())[:14]]))
            if o.get("pros"):
                b.append(("bullet", "👍 " + " · ".join(_cell(p, 80) for p in o["pros"])))
            if o.get("cons"):
                b.append(("bullet", "👎 " + " · ".join(_cell(c, 80) for c in o["cons"])))
        b.append(("h2", "How I judged"))
        b.append(("p", "Price, shipping and origin are quoted from each listing page; on marketplaces the seller's own profile gives location and feedback. "
                       "Reliability comes from ratings and review counts, complaint/praise words in what buyers wrote, and (when my eyes are on) whether the photo matches the text. Nothing was bought, no account was used."))
        return b

    @staticmethod
    def site_report(name, url, pages, notes=(), langs=()):
        b = [("h1", f"Website: {name}"), ("p", f"{len(pages)} pages · {', '.join(langs) if langs else 'one language'} · {_dt.datetime.now():%d %b %Y %H:%M}")]
        if url:
            b.append(("p", f"Preview / files: {url}"))
        b.append(("h2", "Pages"))
        b += [("bullet", _cell(p, 120)) for p in pages]
        if notes:
            b.append(("h2", "Notes"))
            b += [("bullet", _cell(n, 240)) for n in notes]
        return b

    @staticmethod
    def note(title, paragraphs, bullets=()):
        b = [("h1", title), ("p", f"{_dt.datetime.now():%d %b %Y %H:%M} · written by Business AI")]
        b += [("p", _cell(p, 1200)) for p in paragraphs if p]
        b += [("bullet", _cell(x, 300)) for x in bullets]
        return b
