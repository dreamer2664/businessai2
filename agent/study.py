"""Self-study when the owner is away (milestone 17): find good business PDFs, judge them, keep the best in the Drive
library (with a one-page summary), and jot business ideas from short videos into an "Ideas" document.

Called from the idle loop while `pace.has_quiet_time()` (owner said "I'm away N hours, take it slow") and, at a lower
rate, during normal idle time. Every session is short (one PDF or one video), so an owner message is never kept waiting.
"""
import io
import json
import re
import time
import urllib.parse

from . import config, library, video
from .browser import BrowserError

STUDY_LOG = config.STATE_DIR / "study.jsonl"
IDEAS_FILE = config.STATE_DIR / "ideas.jsonl"

PDF_TOPICS = ["dropshipping business guide pdf", "e-commerce conversion rate optimization pdf", "small business marketing plan pdf",
              "customer service email templates e-commerce pdf", "product photography guide pdf", "shopify seo guide pdf",
              "EU consumer rights distance selling guide pdf", "supplier negotiation checklist pdf", "instagram marketing for small business pdf",
              "pricing strategy small business pdf", "inventory management basics pdf", "email marketing best practices pdf",
              "tiktok shop seller guide pdf", "google ads beginners guide pdf", "brand storytelling small business pdf"]
# the owner asked me to look into these (2026-09-08); they are long courses → chaptered notes over several quiet sessions
OWNER_VIDEOS = ["https://youtu.be/DNdBJ5tgyjI", "https://youtu.be/vo6aDcnPzCU"]
VIDEO_TOPICS = ["business ideas 2026 shorts", "dropshipping products trending this month", "side hustle ideas small budget",
                "ecommerce tips for beginners shorts", "print on demand ideas", "etsy shop ideas that sell"]
BAD_PDF = re.compile(r"\b(exam|syllabus|thesis|dissertation|homework|lecture notes|curriculum vitae|resume|invoice|terms and conditions)\b", re.I)


def _density(text):
    """How information-dense a text is: figures, steps, concrete nouns per 1000 characters (rough but stable)."""
    t = text[:60000]
    if len(t) < 2000:
        return 0.0
    figures = len(re.findall(r"\b\d+(?:[.,]\d+)?\s?(?:%|€|\$|£|days?|weeks?|months?|hours?|x|times|k\b)", t))
    steps = len(re.findall(r"(?:^|\n)\s*(?:\d+[.)]|step \d|•|-)\s+\S", t, re.I))
    headings = len(re.findall(r"\n[A-Z][A-Za-z ,:&-]{6,60}\n", t))
    words = max(1, len(t.split()))
    filler = len(re.findall(r"\b(very|really|amazing|incredible|absolutely|just|basically)\b", t, re.I))
    return round(1000 * (figures * 2 + steps + headings - filler) / words, 2)


class Study:
    last_brainstorm = ""

    def __init__(self, tasks, planner=None, google=None, memory=None, log=None, notify=None, viewer=None):
        self.T = tasks
        self.planner = planner
        self.google = google
        self.memory = memory
        self.log = log or (lambda kind, **f: None)
        self.notify = notify or (lambda t: None)
        self.viewer = viewer
        self.seen = self._load_seen()

    def _load_seen(self):
        seen = set()
        if STUDY_LOG.exists():
            for l in STUDY_LOG.read_text(encoding="utf-8").splitlines():
                try:
                    seen.add(json.loads(l)["url"])
                except Exception:
                    pass
        return seen

    def _record(self, rec):
        STUDY_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(STUDY_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.seen.add(rec["url"])

    def sessions_today(self):
        today = time.strftime("%Y-%m-%d")
        n = 0
        if STUDY_LOG.exists():
            for l in STUDY_LOG.read_text(encoding="utf-8").splitlines():
                if today in l[:40]:
                    n += 1
        return n

    # ---- PDFs ------------------------------------------------------------------------
    def pdf_session(self, topic=None):
        """Find one good PDF on a business topic, judge it, keep the best (Drive + summary). Returns a one-line report."""
        topic = topic or PDF_TOPICS[self.sessions_today() % len(PDF_TOPICS)]
        if self.viewer:
            self.viewer.task = f"self-study: {topic}"
        t0 = time.time()
        found = None
        with self.T._session() as b:
            try:
                results = b.search_results(topic, 12)
            except BrowserError as e:
                return f"study: search failed ({e})"
            for r in results:
                u = r["url"]
                if u in self.seen or not (u.lower().endswith(".pdf") or "pdf" in u.lower()) or BAD_PDF.search(r["title"]):
                    continue
                try:
                    text = b.download_text(u, max_chars=120000)
                except BrowserError:
                    continue
                if len(text) < 4000 or text.startswith("(pdf could not"):
                    self._record({"t": time.strftime("%Y-%m-%dT%H:%M"), "url": u, "kept": False, "why": "unreadable/short"})
                    continue
                d = _density(text)
                self._record({"t": time.strftime("%Y-%m-%dT%H:%M"), "url": u, "title": r["title"][:90], "density": d, "kept": d >= 4.0, "chars": len(text)})
                if d >= 4.0:
                    found = (r["title"][:90], u, text, d)
                    break
        self.T._release_page()
        if not found:
            return f"study: read a few PDFs about {topic}, none dense enough to keep ({time.time() - t0:.0f}s)"
        title, url, text, d = found
        summary = self._summarize(title, text)
        doc = library.Doc(f"Notes: {title}", f"from {url} · density {d}", kind="study")
        doc.summary(summary, "What I took from it")
        doc.section("Most useful passages", self._dense_passages(text))
        doc.source(url, title)
        path = doc.save(f"notes-{title[:30]}")
        link = ""
        if self.google and self.google.connected():
            try:
                pdf_bytes = self._fetch_pdf(url)
                if pdf_bytes:
                    up = self.google.upload_bytes(pdf_bytes, re.sub(r"[^\w.-]+", "_", title)[:60] + ".pdf", folder="PDF library", mime="application/pdf")
                    link = up["link"]
                self.google.upload(path, folder="PDF library", convert_to_doc=True)
            except Exception as e:
                self.log("study_upload_failed", error=str(e)[:100])
        if self.memory:
            self.memory.note("study", title, summary, [url])
        self.log("study_kept", title=title[:60], density=d)
        return f"📚 Kept a good PDF: “{title}” (density {d}) — notes in my library" + (f", file in Drive: {link}" if link else "") + f" ({time.time() - t0:.0f}s)"

    def _fetch_pdf(self, url, max_mb=25):
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read(max_mb * 1024 * 1024 + 1)
            return data if len(data) <= max_mb * 1024 * 1024 and data[:4] == b"%PDF" else None
        except Exception:
            return None

    def _dense_passages(self, text, n=6):
        """The n paragraphs with most figures/steps — the 'information-dense part' the owner asked for."""
        paras = [p.strip() for p in re.split(r"\n\s*\n|\.\s{2,}", text) if 200 <= len(p.strip()) <= 1200]
        scored = sorted(paras, key=lambda p: -_density(p * 12))
        return "\n\n".join(scored[:n]) or text[:2000]

    def _summarize(self, title, text):
        if self.planner and self.planner.installed():
            try:
                out = self.planner.chat("You take notes for a small online-store owner. Plain words, concrete, no fluff.",
                                        f"Document: {title}\n\n{text[:6000]}\n\nWrite 5-8 bullet notes with the concrete, reusable points (numbers, steps, rules). Then one line: 'Use it for: …'.",
                                        max_tokens=320, timeout=180)
                if len(out) > 80:
                    return out
            except Exception as e:
                self.log("study_summary_error", error=str(e)[:80])
        from .tasks import key_sentences
        return "\n".join(f"• {s}" for s in key_sentences(text, title, limit=8))

    # ---- short videos → ideas ---------------------------------------------------------------
    def video_session(self, query=None, urls=None):
        """Read the captions of short business videos and jot the concrete ideas into the Ideas list (+ Drive doc)."""
        t0 = time.time()
        vids = []
        if urls:
            vids = [{"id": video.url_id(u), "title": u, "url": u} for u in urls if video.url_id(u)]
        else:
            query = query or VIDEO_TOPICS[self.sessions_today() % len(VIDEO_TOPICS)]
            try:
                vids = [v for v in video.search(query, 8) if v.get("id") and (v.get("url") or "") not in self.seen][:3]
            except Exception as e:
                return f"ideas: video search failed ({e})"
        if self.viewer:
            self.viewer.task = "self-study: business ideas from short videos"
        new_ideas = []
        reports = []
        for v in vids:
            try:
                text, meta = video.transcript(v["id"])
            except Exception as e:
                self.log("transcript_failed", id=v["id"], error=str(e)[:80])
                continue
            if not text:
                continue
            if meta.get("seconds", 0) > 25 * 60 or len(text) > 60000:              # a course, not a short: chaptered notes instead
                reports.append(self.course_session(v.get("url") or f"https://youtu.be/{v['id']}"))
                continue
            if meta.get("title") and (not v.get("title") or v["title"].startswith("http")):
                v["title"] = meta["title"]
            ideas = self._ideas_from(text, v.get("title", ""))
            url = v.get("url") or f"https://youtu.be/{v['id']}"
            for idea in ideas:
                new_ideas.append({"t": time.strftime("%Y-%m-%d"), "idea": idea, "source": url, "title": (v.get("title") or "")[:80]})
            self._record({"t": time.strftime("%Y-%m-%dT%H:%M"), "url": url, "title": (v.get("title") or "")[:80], "kept": bool(ideas), "ideas": len(ideas)})
        if not new_ideas:
            if reports:
                return "\n".join(reports)
            return f"ideas: watched {len(vids)} videos, nothing concrete to keep ({time.time() - t0:.0f}s)"
        IDEAS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(IDEAS_FILE, "a", encoding="utf-8") as f:
            for i in new_ideas:
                f.write(json.dumps(i, ensure_ascii=False) + "\n")
        self._sync_ideas_doc()
        if self.memory:
            self.memory.note("ideas", "business ideas from videos", "\n".join("• " + i["idea"] for i in new_ideas), list({i["source"] for i in new_ideas}))
        self.log("ideas_kept", n=len(new_ideas))
        return "\n".join(reports + [f"💡 Jotted {len(new_ideas)} business ideas from {len(vids)} short videos into my Ideas list ({time.time() - t0:.0f}s):\n" + "\n".join("• " + i["idea"][:140] for i in new_ideas[:6])])

    # ---- long videos (courses) → chaptered notes ---------------------------------------------------
    def course_session(self, url, max_chunks=None):
        """A multi-hour video (a course) is read chunk by chunk (≈ 12 min each); each chunk gives 2-4 concrete lessons.
        Progress is saved, so it can continue over several quiet sessions. Returns a one-line report."""
        vid = video.url_id(url)
        if not vid:
            return "course: not a YouTube link"
        prog_file = config.STATE_DIR / f"course_{vid}.json"
        try:
            prog = json.loads(prog_file.read_text())
        except Exception:
            prog = {"url": url, "done": 0, "lessons": [], "title": ""}
        if not prog.get("text"):
            text, meta = video.transcript(vid)
            if not text:
                return "course: no captions on that video"
            prog.update(text=text, title=meta.get("title", url)[:100], seconds=meta.get("seconds", 0))
        chunks = [prog["text"][i:i + 9000] for i in range(0, len(prog["text"]), 9000)]
        n_total = len(chunks)
        budget = max_chunks or (6 if (self.planner and self.planner.installed()) else 12)      # ≈ 1-2 h of video per session
        t0 = time.time()
        if self.viewer:
            self.viewer.task = f"studying course: {prog['title'][:50]} ({prog['done']}/{n_total})"
        start = prog["done"]
        for i in range(start, min(n_total, start + budget)):
            lessons = self._lessons_from(chunks[i], prog["title"], i, n_total)
            prog["lessons"].extend({"part": i + 1, "text": l} for l in lessons)
            prog["done"] = i + 1
            prog_file.parent.mkdir(parents=True, exist_ok=True)
            prog_file.write_text(json.dumps({k: v for k, v in prog.items() if k != "text"} | {"text": prog["text"]}, ensure_ascii=False))
            if time.time() - t0 > 900:
                break
        # (re)write the notes document
        doc = library.Doc(f"Course notes: {prog['title']}", f"{prog['done']}/{n_total} parts read · {len(prog['lessons'])} lessons · source {url}", kind="course")
        by_part = {}
        for l in prog["lessons"]:
            by_part.setdefault(l["part"], []).append(l["text"])
        for part in sorted(by_part):
            mins = (part - 1) * (prog.get("seconds", 0) / n_total) / 60 if prog.get("seconds") else 0
            doc.bullets(f"Part {part}" + (f" (~{int(mins)} min in)" if mins else ""), by_part[part])
        doc.source(url, prog["title"])
        path = doc.save(f"course-{prog['title'][:30]}")
        if self.google and self.google.connected():
            try:
                self.google.upload(path, name=f"Course notes - {prog['title'][:50]}.html", folder="Courses", convert_to_doc=True)
            except Exception as e:
                self.log("course_upload_failed", error=str(e)[:100])
        if self.memory and prog["lessons"]:
            self.memory.note("course", prog["title"], "\n".join("• " + l["text"] for l in prog["lessons"][-12:]), [url])
        self._record({"t": time.strftime("%Y-%m-%dT%H:%M"), "url": f"{url}#part{prog['done']}", "title": prog["title"], "kept": True, "lessons": len(prog["lessons"])})
        state = "finished" if prog["done"] >= n_total else f"{prog['done']}/{n_total} parts so far — I'll continue in my next quiet session"
        return f"🎓 Course “{prog['title'][:60]}”: {len(prog['lessons'])} lessons noted ({state}) — notes in my library ({time.time() - t0:.0f}s)"

    def _lessons_from(self, chunk, title, i, n):
        if self.planner and self.planner.installed():
            try:
                out = self.planner.chat("You take course notes for a small online-store owner. Only concrete, reusable lessons: numbers, steps, tools, rules of thumb. No hype, no filler.",
                                        f"Course: {title} (part {i + 1} of {n})\nTranscript:\n{chunk[:8000]}\n\nWrite 2-4 lessons, one per line, each max 25 words. If this part has no real lesson (intro, sales talk), output NONE.",
                                        max_tokens=220, timeout=180)
                lines = [re.sub(r"^[-•*\d.)\s]+", "", l).strip() for l in out.splitlines() if len(l.strip()) > 12]
                return [l for l in lines if l.upper() != "NONE"][:4]
            except Exception as e:
                self.log("lessons_model_error", error=str(e)[:80])
        sents = re.split(r"(?<=[.!?])\s+", chunk)
        return self.pick_lessons(sents)

    @staticmethod
    def pick_lessons(sents, n=3, min_score=6):
        """Extractive fallback (no thinking model): instructions and rules of thumb, never the guru's income brags."""
        def score(x):
            low = x.lower()
            sc = 0
            sc += 3 * len(re.findall(r"\b(you (?:should|need to|want to|have to|must|can|could)|make sure|the (?:key|trick|rule|goal) is|rule of thumb|at least|no more than|never|always|avoid|don'?t|step \d|the first thing|the (?:best|easiest|cheapest|fastest) way|instead of|before you|the (?:reason|problem) is)\b", low))
            sc += 2 * len(re.findall(r"\d+\s?%|\d+\s?(?:x|times)\b|\d+\s?(?:percent|per cent)\b|\b\d+\s?(?:days?|hours?|weeks?|seconds?|products?|orders?|reviews?|customers?|variations?)\b", low))
            sc += len(re.findall(r"\b(margin|profit|supplier|shipping|conversion|refund|return rate|ad spend|cost per|break[- ]even|test(?:ing)?|winning product|competitor|reviews?|creatives?|hook|landing page|checkout|upsell|bundle)\b", low))
            sc += 1 if re.search(r"[$€]\s?\d", low) and re.search(r"\b(cost|price|sell (?:it )?for|charge|spend|budget|per (?:order|day|unit|product)|at least)\b", low) else 0
            # brag / filler / story → out
            sc -= 5 * len(re.findall(r"\b(i|we) (?:was|were|am|'m|have been|had been|started|ended up|remember)\b.{0,60}\b(?:making|doing|bringing|earning|generating|pulling|profit(?:ing)?|revenue|a day|per day|a month|per month|figures?)\b", low))
            sc -= 5 * len(re.findall(r"\b(?:\$|€)\s?\d[\d,.]*\s?(?:k|thousand|million|m|billion)?\s?(?:a|per|every(?: single)?) (?:day|month|year|week)\b", low))
            sc -= 4 * len(re.findall(r"\b(subscribe|like this video|my (?:course|program|mentorship|community)|link in (?:the )?(?:bio|description)|comment below|congrats|welcome (?:back|to)|in this video|i'?ve made|hundreds of videos|autopilot|without (?:barely )?working|my last brand|my students?|if i had to guess|i would assume|i literally|as you (?:guys )?can see|trust me|guys)\b", low))
            sc -= 3 if re.search(r"^(so|and|but|now|okay|ok|alright|look)\b", low) and len(x) < 70 else 0
            sc -= 2 if re.search(r"\b(billion|processed over|\d{3},\d{3},\d{3})\b", low) else 0
            sc -= 2 if low.count(" i ") + low.startswith("i ") >= 2 else 0
            # screen-deictic / sales-funnel / vague sentences carry nothing without the video
            sc -= 4 * len(re.findall(r"\b(click (?:right )?here|right here|over here|this (?:website|page|tab|button|link)|like this|something like this|this sort of|book a call|my team|member of my team|sign up (?:here|below)|the software i showed|as i showed|we are going to do this|we don'?t need to do this|right now|you know,?)\b", low))
            sc -= 3 if not re.search(r"\b(product|supplier|shipping|margin|profit|price|cost|customer|ad|ads|store|shop|order|review|competitor|niche|market|brand|conversion|refund|budget|test|video|creative|traffic|sales?|revenue|inventory|stock|alibaba|aliexpress|amazon|tiktok|facebook|shopify)\w*\b", low) and not re.search(r"\d", low) else 0
            sc -= 4 * len(re.findall(r"\b(you can (?:go|click|copy|come|see|scroll|type|search up|paste|just|also do|easily go)|go (?:right )?back|come (?:over )?here|copy (?:this|it|the)|paste (?:it|this)|(?:on|in) (?:the|their|your) dashboard|color code|this color|filters?\b|drop-?down|tab|button)\b", low))
            sc -= 3 * len(re.findall(r"\b(um+|uh+|i mean|god forbid|really,? really|kind of|sort of|you guys|literally|basically)\b", low))
            sc -= 3 if re.search(r"\bi (?:don'?t|do not) (?:know|recommend|think)\b|\bi (?:like|love|hate) to\b", low) else 0
            sc += 3 if re.search(r"\b(because|so that|which means|the reason)\b", low) else 0          # a lesson explains itself
            sc += 2 * len(re.findall(r"\b(have to have|has to have|need to have|must have|required|mandatory|before (?:you|we) (?:start|run|launch)|once (?:you|we) start)\b", low))
            return sc
        picks = [x.strip() for x in sents if 40 <= len(x.strip()) <= 220 and not x.strip().endswith(("…", ","))]
        picks = sorted(dict.fromkeys(picks), key=lambda x: -score(x))
        out = []
        for x in picks:
            if score(x) < min_score:
                break
            words = set(re.findall(r"[a-z]{4,}", x.lower()))
            if any(len(words & set(re.findall(r"[a-z]{4,}", y.lower()))) >= max(3, int(0.6 * len(words))) for y in out):
                continue                                                # near-duplicate of one already kept
            out.append(x)
            if len(out) >= n:
                break
        return out

    def pending_courses(self):
        out = []
        started = {f.name[7:-5] for f in config.STATE_DIR.glob("course_*.json")}
        for u in OWNER_VIDEOS:                                         # not started yet → pending too
            if video.url_id(u) not in started:
                out.append(u)
        for f in config.STATE_DIR.glob("course_*.json"):
            try:
                d = json.loads(f.read_text())
                n_total = max(1, -(-len(d.get("text", "")) // 9000))
                if d.get("done", 0) < n_total:
                    out.append(d["url"])
            except Exception:
                continue
        return out

    def _ideas_from(self, text, title):
        text = re.sub(r"\s+", " ", text)[:7000]
        if self.planner and self.planner.installed():
            try:
                out = self.planner.chat("You extract concrete business ideas from a video transcript for a small online-store owner. Output a plain list, one idea per line, no numbering. Skip hype.",
                                        f"Video: {title}\nTranscript: {text}\n\nList the concrete ideas (product, niche, tactic, tool) with the one figure or reason given. Max 6 lines. If there is nothing concrete, output NONE.",
                                        max_tokens=260, timeout=180)
                lines = [re.sub(r"^[-•*\d.)\s]+", "", l).strip() for l in out.splitlines() if len(l.strip()) > 12]
                lines = [l for l in lines if l.upper() != "NONE"]
                if lines:
                    return lines[:6]
            except Exception as e:
                self.log("ideas_model_error", error=str(e)[:80])
        # rule fallback: sentences with an idea verb + a noun phrase, or a figure
        sents = re.split(r"(?<=[.!?])\s+", text)
        picks = [s.strip() for s in sents if re.search(r"\b(sell|selling|start|launch|niche|product|idea|make money|earn|profit|margin|\$\d|\d+%|€\d)\b", s, re.I) and 40 <= len(s) <= 220]
        return list(dict.fromkeys(picks))[:5]

    def ideas_text(self, n=12):
        if not IDEAS_FILE.exists():
            return "No ideas jotted yet — I collect them from short business videos when I have quiet time (or ask me: 'watch some videos about business ideas')."
        rows = [json.loads(l) for l in IDEAS_FILE.read_text(encoding="utf-8").splitlines() if l.strip()][-n:]
        return "💡 My ideas list (latest):\n" + "\n".join(f"• {r['idea'][:150]}  — {r['source']}" for r in rows[::-1])

    def _sync_ideas_doc(self):
        """Rewrite the Ideas document in the library (and Drive) from the full list."""
        rows = [json.loads(l) for l in IDEAS_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
        doc = library.Doc("Business ideas", f"{len(rows)} ideas jotted from short videos and articles", kind="ideas")
        by_day = {}
        for r in rows:
            by_day.setdefault(r["t"], []).append(r)
        for day in sorted(by_day, reverse=True):
            doc.bullets(day, [f"{r['idea']} — {r['source']}" for r in by_day[day]])
        path = doc.save("business-ideas")
        if self.google and self.google.connected():
            try:
                self.google.upload(path, name="Business ideas.html", folder="Ideas", convert_to_doc=True)
            except Exception as e:
                self.log("ideas_upload_failed", error=str(e)[:100])
        return path

    # ---- quiet-time loop -------------------------------------------------------------------------
    def quiet_session(self, n_done):
        """One session of self-training while the owner is away: alternate PDFs and videos; brainstorm every 4th."""
        pend = self.pending_courses()
        if pend and n_done % 2 == 0:
            return self.course_session(pend[0])
        kind = ["pdf", "video", "pdf", "brainstorm"][n_done % 4]
        if kind == "pdf":
            return self.pdf_session()
        if kind == "video":
            return self.video_session()
        return self.brainstorm()

    def brainstorm(self):
        """Think about the shop: 3 concrete improvement ideas from recent notes — written to the library, not sent as chatter."""
        if not (self.planner and self.planner.installed() and self.memory):
            return "brainstorm: skipped (no thinking model)"
        notes = self.memory.notes(limit=8)
        ctx = "\n".join(f"- {n['topic']}: {n['text'][:300]}" for n in notes)[:4000]
        try:
            out = self.planner.chat("You are the assistant of a small online store, thinking on your own during quiet time. Be concrete and short.",
                                    f"Recent things I learned:\n{ctx}\n\nPropose 3 concrete improvements or experiments for the store (what, why, how to test cheaply). Plain words, 3 short paragraphs.",
                                    max_tokens=350, timeout=180)
        except Exception as e:
            return f"brainstorm: model error {str(e)[:60]}"
        self.last_brainstorm = out                       # the project list picks the 3 ideas up (core.run_quiet)
        doc = library.Doc("Brainstorm " + time.strftime("%d %b %Y %H:%M"), "ideas I had during quiet time", kind="brainstorm")
        doc.summary(out, "Three things to try")
        path = doc.save("brainstorm")
        if self.memory:
            self.memory.note("brainstorm", "quiet-time ideas", out[:1500], [])
        return f"🧠 Brainstormed 3 improvements for the store — in my library ({path.name})"
