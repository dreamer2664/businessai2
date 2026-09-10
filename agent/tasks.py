"""Read-only browsing tasks (milestone 2): research jobs the agent runs by itself in
its own browser and reports back. No planner model yet — each task is a small,
deterministic procedure built on Browser + the knowledge brain:

  research(topic)            search → open the best 3 non-forum pages → extract the
                             definitions/steps/numbers → short report with sources
  compare_suppliers(product) search supplier directories → collect names, claims,
                             prices/shipping mentions → table
  summarize(url)             open a page or PDF and return the key points
  exam(bank, n)              sit an offline MCQ bank (agent/mcq.py) and report the score

Every task returns a text report; run_task() also logs and can notify the owner.
"""
import concurrent.futures
import contextlib
import re
import threading
import time
import urllib.parse

from . import config
from .browser import Browser, BrowserError
from . import sources
from . import video
from . import walls as _walls

FORUM = re.compile(r"reddit\.com|quora\.com|facebook\.com|youtube\.com|tiktok\.com|instagram\.com|pinterest\.|x\.com|twitter\.com|linkedin\.com/posts", re.I)
SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def clean(text):
    """Strip the browser's element numbers ([12]) and bullets from extracted text."""
    return re.sub(r"\s*\[\d+\]\s*", " ", text)


def key_sentences(text, topic, limit=6):
    """Pick sentences that define or quantify the topic: contain topic words + a definition/number cue."""
    text = clean(text)
    tw = set(w[:6] for w in re.findall(r"[a-z0-9]+", topic.lower()) if len(w) > 2)
    out, seen = [], set()
    for para in text.split("\n"):
        para = para.strip("•# ").strip()
        if len(para) < 60 or para.lower().startswith(("cookie", "we use", "sign up", "subscribe", "©")):
            continue
        for s in SENT.split(para):
            s = s.strip()
            if not (60 <= len(s) <= 320):
                continue
            sw = set(w[:6] for w in re.findall(r"[a-z0-9]+", s.lower()))
            hit = len(tw & sw)
            cue = bool(re.search(r"\b(is|are|means|refers|typically|usually|average|percent|%|\d+|should|steps?|because|costs?)\b", s, re.I))
            if hit >= max(1, len(tw) // 2) and cue and s[:60].lower() not in seen:
                if re.match(r"^(home|blog|guide|complete guide|what's|what is)\b", s, re.I) and not re.search(r"\d", s):
                    continue                      # breadcrumb / headline echo, not a fact
                if re.search(r"\b(click here|sign up|my (course|program)|i found|let me be upfront|alternative that delivers)\b", s, re.I):
                    continue                      # sales pitch
                seen.add(s[:60]); out.append((bool(re.search(r"\d", s)) + bool(re.search(r"\b(is|are|means|refers)\b", s)), s))
    out.sort(key=lambda x: -x[0])
    return [s for _, s in out[:limit]]


class Tasks:
    IDLE_CLOSE = 600          # seconds; the browser window stays open between tasks, then closes itself

    @staticmethod
    def _mem_available_mb():
        try:
            for line in open("/proc/meminfo"):
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
        except Exception:
            pass
        return 99999

    def _release_page(self):
        """Before thinking: park the page (normal) or close the browser (low-memory machines, < 2.5 GB available)."""
        b = self._browser
        if b is None or not b.alive():
            return
        if self.low_mem:
            self.close_browser()
        else:
            self.on_hands(b.park, timeout=15)

    def __init__(self, log=None, notify=None, brain=None, viewer=None, planner=None, memory=None, eyes=None, pace=None):
        self.log = log or (lambda kind, **f: None)
        self.eyes = eyes
        self.pace = pace                      # the job clock: 'stop' and 'hurry up' are honoured inside the page loops
        self.notify = notify or (lambda text: None)
        self.brain = brain
        self.viewer = viewer
        self.planner = planner
        self.memory = memory
        self._browser = None
        self._lock = threading.Lock()
        self.walls = _walls.WallMemory(log=self.log)   # sites/engines that walled lately: last in line, skipped after two
        self.low_mem = self._mem_available_mb() < 2500
        if self.low_mem:
            self.log("low_memory_mode", available_mb=self._mem_available_mb())
        # Playwright's sync API is bound to the thread that created the browser, so ALL browser work runs on
        # this one long-lived "hands" thread; public methods submit to it and wait.
        self._hands = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="hands")

    def on_hands(self, fn, *a, timeout=None, **kw):
        """Run fn(*a, **kw) on the hands thread and return its result (callable from any thread)."""
        if threading.current_thread().name.startswith("hands"):
            return fn(*a, **kw)
        return self._hands.submit(fn, *a, **kw).result(timeout=timeout)

    def screenshot(self):
        """JPEG bytes of the current tab, or None when the browser is closed."""
        def _shot():
            b = self._browser
            if not (b and b.alive()):
                return None
            return b.page.screenshot(type="jpeg", quality=60, timeout=6000), b.page.title()[:80], b.page.url
        return self.on_hands(_shot, timeout=20)

    # ---- one browser, reused (so the owner can watch one window instead of a flicker of new ones) ----
    def close_browser(self):
        if self._browser is None:
            return
        if not threading.current_thread().name.startswith("hands"):    # Playwright objects live on the hands thread
            try:
                return self._hands.submit(self.close_browser).result(timeout=30)
            except Exception:
                pass
        try:
            self._browser.close()
        finally:
            self._browser = None

    def interrupt_page(self):
        """The owner said 'stop' twice: no further page opens on this job (the current navigation ends by its own 30 s timeout —
        Playwright objects cannot be touched from another thread, so this flag is the honest maximum)."""
        b = self._browser
        if b is not None:
            b.stop_requested = True
        self.log("browser_interrupt")

    def tick(self):
        """Call periodically: closes the browser after IDLE_CLOSE seconds without a task."""
        b = self._browser
        if b is not None and not self._lock.locked() and time.time() - b.last_used > self.IDLE_CLOSE:
            self._hands.submit(self.close_browser)
            self.log("session_closed")

    @contextlib.contextmanager
    def _session(self):
        with self._lock:
            b = self.browser()
            b.stop_requested = False                                  # a new job: the last 'stop' is spent
            try:
                yield b
            except Exception:
                self.close_browser()          # a broken browser is not reused
                raise

    # ---- tasks ---------------------------------------------------------
    @staticmethod
    def _core_topic(topic):
        t = re.sub(r"^(what is|what are|what was|how to|how do|how does|why|when|where|which|who|come|cosa|che cosa|perch[eé]|quando|dove|qual[ei])\b[\s,?]*", "", topic.strip(), flags=re.I).strip(" ?")
        return t or topic.strip()

    def plan_queries(self, topic, fast=False):
        """2-3 varied search angles for one topic (item 2): base + intent aspects. 1 when hurried."""
        base = self._core_topic(topic)
        if fast:
            return [base]
        low = topic.strip().lower()
        it = bool(re.search(r"\b(come|cosa|che|quale|quali|quanto|quando|dove|perch[eé]|una|uno|della|nella|sono|[eè]|ecco)\b", low)
                    or re.search(r"\b(miglior|prezz|cost[oi]|confront|recension|guid[aeo]|spiegaz|esempi|iniziare|offert|scont|acquist)\w*\b", low))
        orig = low
        if re.match(r"(what|why|cosa|che cosa|perch)", orig):
            aspects = ["explained", "examples"] if not it else ["spiegazione", "esempi"]
        elif re.search(r"\b(buy|price|cheap|cost|deal|shop|order|prezzo|costo|acquist|offerta|sconto)\w*\b", low):
            aspects = ["price", "review"] if not it else ["prezzo", "recensioni"]
        elif re.search(r"\b(vs|versus|compare|comparison|best|better|confronta|confronto|miglior)\w*\b", low) or re.search(r"\btop \d", low):
            aspects = ["vs", "best"] if not it else ["confronto", "migliore"]
        elif re.search(r"\b(how|guide|tutorial|learn|start|explained|come|guida|iniziare)\w*\b", low):
            aspects = ["guide", "tips"] if not it else ["guida", "consigli"]
        else:
            aspects = ["review", "guide"] if not it else ["recensioni", "guida"]
        seen, qs = set(), []
        for q in [base] + [f"{base} {x}" for x in aspects if not re.search(r"\b" + re.escape(x[:5]), base.lower())]:
            if q.lower() not in seen:
                seen.add(q.lower())
                qs.append(q)
        return qs

    @staticmethod
    def _synthesize(opened):
        """Model-free synthesis (item 2): dedupe + cross-domain agreement. Returns lines or []."""
        def norm(s):
            return re.sub(r"\s+", " ", re.sub(r"[^\w ]", "", s.lower())).strip()

        def dom(u):
            return urllib.parse.urlparse(u).netloc.lower().removeprefix("www.")

        if not opened:
            return []
        seen, agreed, rest = set(), [], []
        for title, url, ks in opened:
            for x in ks:
                n = norm(x)
                if not n or n in seen:
                    continue
                seen.add(n)
                ds = {dom(url)} | {dom(u) for _, u, ks2 in opened if u != url for s2 in ks2 if norm(s2) == n}
                (agreed if len(ds) >= 2 else rest).append((len(ds), x) if len(ds) >= 2 else x)
        lines = [f"Across the {len(opened)} pages I read:"]
        for nd, x in sorted(agreed, reverse=True)[:2]:
            lines.append(f"✓ agreed by {nd} sources: {x}")
        for x in sorted(rest, key=lambda v: (bool(re.search(r"\d", v)), len(v)), reverse=True)[:4]:
            lines.append(f"• {x}")
        return lines if (agreed or rest) else []

    WIDEN_PAGES = 4           # extra browser pages a widened research may read (second engine + inside-site links)

    def _time_left(self):
        """Is there time to look in more places? Slow mode, an "at least N" floor, or > 10 min of quiet time — and no hurry/stop."""
        p = self.pace
        if not p or self._hurried() or self._stopped() or self._over_budget():
            return False
        try:
            if getattr(p, "mode", "") == "slow" or (hasattr(p, "under_floor") and p.under_floor()):
                return True
            b = p.budget_left() if hasattr(p, "budget_left") else None
            return bool(b and b > 10 * 60)
        except Exception:
            return False

    def _widen(self, b, topic, queries, opened, q_of, deep, n_extra, want_doc, images):
        """More places, when time is left: a second engine, the facts pages inside the good sites, Wikipedia, YouTube.
        Appends to `opened`; returns {"second": (engine, n), "deep": n, "wikipedia": bool, "youtube": bool}."""
        info = {"second": None, "deep": 0, "wikipedia": False, "youtube": False}
        have = {u for _, u, _ in opened}
        doms = lambda: [urllib.parse.urlparse(u).netloc.lower() for u in have]

        def read(url, title_prefix=""):
            """Open url, return (title, url, key sentences) or None; walls and thin pages are skipped, never fought."""
            if self._stopped() or self._over_budget() or url in have or FORUM.search(url) or self.walls.skip(url):
                return None
            try:
                b.open(url)
                if b.status() != "ok":
                    self.log("task_wall", url=url, wall=b.status()); self.walls.hit(url, b.status()); return None
                ks = key_sentences(b.extract_text(), topic)
                self.walls.clear(url)
            except BrowserError:
                return None
            if not ks:
                return None
            have.add(url)
            title = (b.page.title() or "")[:80] or url
            if want_doc:
                images[url] = self._page_image(b)
            return (title_prefix + title, url, ks)

        budget = n_extra
        # 1) second opinion: the same question to an engine that did not answer the first time (different index → different sites)
        others = list(getattr(b, "other_engines", lambda: [])())
        if others and budget > 0:
            eng = others[0]
            try:
                results = b.search_results(queries[0], 8, engine=eng)
            except (BrowserError, TypeError) as e:
                self.log("widen_search_failed", engine=eng, error=str(e)[:80]); results = []
            got = 0
            for r in results:
                if got >= 2 or budget <= 0:
                    break
                dom = urllib.parse.urlparse(r["url"]).netloc.lower()
                if doms().count(dom) >= 2:
                    continue
                pg = read(r["url"])
                if pg:
                    opened.append(pg); q_of[r["url"]] = 0; got += 1; budget -= 1
            info["second"] = (eng, got)
        # 2) inside the sites: the shipping / price / spec / FAQ page a good page links to (one per site)
        seen_sites = set()
        for page_url, (label, url) in deep:
            if budget <= 0:
                break
            site = urllib.parse.urlparse(url).netloc.lower()
            if site in seen_sites:
                continue
            seen_sites.add(site)
            pg = read(url, title_prefix=f"{label} › ")
            if pg:
                opened.append(pg); q_of[url] = 0; info["deep"] += 1; budget -= 1
        # 3) the neutral definition (no browser: two small API calls)
        if not self._stopped():
            w = sources.wikipedia(self._core_topic(topic), lang="it" if re.search(r"\b(come|cosa|quale|migliori?|prezz\w*|dove|perch[eé])\b", topic.lower()) else "en")
            if w and w["url"] not in have:
                ks = key_sentences(w["text"], topic, limit=3) or [w["text"].split(". ")[0][:300] + "."]
                opened.append((w["title"], w["url"], ks)); have.add(w["url"]); info["wikipedia"] = True
        # 4) what people are told out loud: the most-watched video, its transcript when there is one
        if not self._stopped():
            y = sources.youtube(self._core_topic(topic))
            if y and y["url"] not in have:
                ks = sources.transcript_sentences(y["text"], topic) if y.get("text") else []
                opened.append((y["title"], y["url"], ks or [f"Most-watched video on the topic — {sources.views_text(y.get('views', 0))} views, channel {y.get('channel', '')}; no transcript to quote."]))
                have.add(y["url"]); info["youtube"] = True
        return info

    @staticmethod
    def _widen_line(info):
        bits = []
        if info.get("second"):
            eng, n = info["second"]
            bits.append(f"second opinion from {eng} ({n} page{'s' if n != 1 else ''})")
        if info.get("deep"):
            bits.append(f"{info['deep']} page{'s' if info['deep'] != 1 else ''} inside the sites (shipping/prices/specs)")
        if info.get("wikipedia"):
            bits.append("Wikipedia")
        if info.get("youtube"):
            bits.append("YouTube")
        return "Widened because there was time: " + (" · ".join(bits) if bits else "tried a second engine and the inside pages — nothing new") + "."

    def research(self, topic, n_pages=3, want_doc=False, widen=None):
        t0 = time.time()
        report = [f"Research: {topic}"]
        images = {}
        deep = []                     # [(page_url, (label, url))] — facts pages linked from the good pages, for the widening pass
        widen_info = None
        # 1) what the local pack already knows
        if self.brain and self.brain.ready:
            local = self.brain.ask(topic)
            if local:
                report.append("From my knowledge pack:\n" + local)
        # 2) the web
        opened = []
        q_of = {}
        queries = self.plan_queries(topic, fast=self._hurried())
        nq_ok, last_err = 0, None
        walled = {}                   # site → walls seen in this job; after two, the site is skipped (some sites wall one path, not all)
        tried = set()                 # every URL opened in this job — a page that gave nothing is not opened again from another angle
        with self._session() as b:
            stopped = False; cut = False
            for qi, q in enumerate(queries):
                if self._stopped() or self._over_budget() or len(opened) >= n_pages:
                    if self._over_budget() and not self._stopped():
                        cut = True
                    elif self._stopped():
                        stopped = True
                    break
                try:
                    results = self.walls.order(b.search_results(q, max(4, 12 // len(queries))))   # sites that walled lately go last
                    nq_ok += 1
                except BrowserError as e:
                    last_err = e
                    continue
                for r in results:
                    if self._stopped() or self._over_budget():
                        cut = self._over_budget() and not self._stopped()
                        stopped = self._stopped()
                        break
                    if self._hurried() and len(opened) >= max(1, n_pages - 1):
                        break
                    if len(opened) >= n_pages:
                        break
                    if FORUM.search(r["url"]) or r["url"] in q_of or r["url"] in tried:
                        continue
                    tried.add(r["url"])
                    dom = urllib.parse.urlparse(r["url"]).netloc.lower()
                    if dom and sum(1 for u in q_of if urllib.parse.urlparse(u).netloc.lower() == dom) >= 2:
                        continue                       # at most 2 pages per site (file:// pages have no site — never capped)
                    if dom and (walled.get(dom.removeprefix("www."), 0) >= 2 or self.walls.skip(r["url"])):
                        self.log("wall_skipped", url=r["url"])
                        continue                       # walled twice (this job or lately) — the next site, not a third knock
                    try:
                        b.open(r["url"])
                        st = b.status()
                        if st == "captcha" and self.pass_wall(b, r["url"]):
                            st = b.status()
                        if st != "ok":
                            self.log("task_wall", url=r["url"], wall=st)
                            if dom:
                                walled[dom.removeprefix("www.")] = walled.get(dom.removeprefix("www."), 0) + 1
                                self.walls.hit(r["url"], st)
                            continue
                        text = b.extract_text()
                        if dom:
                            self.walls.clear(r["url"])
                    except BrowserError:
                        continue
                    ks = key_sentences(text, topic)
                    if ks:
                        opened.append((b.page.title()[:80] or r["url"], r["url"], ks))
                        q_of[r["url"]] = qi
                        if want_doc:
                            images[r["url"]] = self._page_image(b)
                        try:
                            deep += [(r["url"], d) for d in sources.deep_links(b.links(120), r["url"], limit=2)]
                        except Exception:
                            pass
            if not opened and not nq_ok:
                return "\n".join(report + [f"(web search failed: {last_err})"])
            engine = getattr(b, "engine_used", None)
            # 2b) time left (slow / floor / quiet budget) → look in more places: another engine, inside the sites, Wikipedia, YouTube
            if (self._time_left() if widen is None else widen) and not stopped and not cut:
                try:
                    widen_info = self._widen(b, topic, queries, opened, q_of, deep, self.WIDEN_PAGES, want_doc, images)
                    self.log("research_widen", **{k: (v if not isinstance(v, tuple) else f"{v[0]} {v[1]}") for k, v in widen_info.items()})
                except Exception as e:
                    self.log("widen_failed", error=str(e)[:100])
        # 3) what the owner added while I was reading ("also look at prices in germany") → one or two more pages on that
        change, extra = self.owner_change.strip(), []
        self.owner_change = ""
        if change and not self._stopped() and not self._over_budget():
            q = re.sub(r"^\W*(also|and|please|can you|could you|don'?t forget( to)?|make sure( to)?|remember( to)?)\s+", "", change, flags=re.I).strip(" .")
            q = re.sub(r"^(look at|check|include|add|consider|read about|find)\s+", "", q, flags=re.I).strip() or change
            try:
                with self._session() as b:
                    for r in b.search_results(f"{topic} {q}", 8):
                        if len(extra) >= (1 if self._hurried() else 2) or self._stopped() or self._over_budget():
                            break
                        if FORUM.search(r["url"]) or any(r["url"] == u for _, u, _ in opened):
                            continue
                        try:
                            b.open(r["url"])
                            if b.status() != "ok":
                                continue
                            ks = key_sentences(b.extract_text(), f"{topic} {q}") or key_sentences(b.extract_text(), q)
                        except BrowserError:
                            continue
                        if ks:
                            extra.append((b.page.title()[:80] or r["url"], r["url"], ks))
                            if want_doc:
                                images[r["url"]] = self._page_image(b)
            except BrowserError as e:
                self.log("change_search_failed", error=str(e)[:80])
            opened += extra
            self.log("owner_change_applied", change=change[:80], pages=len(extra))
        brief = None
        self._release_page()
        if opened and self.planner and self.planner.installed():
            try:
                brief = self.planner.brief(topic + (f" (you also asked: {change})" if change else ""), opened)
            except Exception as e:
                self.log("brief_failed", error=str(e)[:100])
        if brief:
            report = [f"Research: {topic}\n\n{brief}", "\nPages I read:"] + [f"[{i+1}] {t} — {u}" for i, (t, u, _) in enumerate(opened)]
        else:
            synth = self._synthesize(opened)
            if synth:
                report.append("\n" + "\n".join(synth))
            for title, url, ks in opened:
                report.append(f"\n{title}\n{url}\n" + "\n".join(f"• {s}" for s in ks))
        if change:
            report.append(f"You added “{change}” while I worked: " + (f"{len(extra)} page(s) on it are included" + (" (marked in the document)" if want_doc else "") if extra else "I searched for it but found nothing solid — say it again with other words if it matters") + ".")
        if widen_info is not None:
            report.append(self._widen_line(widen_info))
        report.append(f"({len(opened)} pages read in {time.time() - t0:.0f}s" + (f" · {len(queries)} search angles" if len(queries) > 1 else "") + (f" · via {engine}" if engine else "") + (" — stopped early as you asked" if stopped else (" — quiet-time budget ran out, I stopped here" if cut else "")) + ")")
        out = "\n".join(report)
        if self.memory and opened:
            self.memory.note("research", topic, brief or out, [u for _, u, _ in opened])
        if want_doc and opened:
            self.last_doc = self._research_doc(topic, brief, opened, images, change=change, extra_urls={u for _, u, _ in extra})
            self.last_native = ("research", {"topic": topic, "summary": brief or "", "pages": [{"title": t, "url": u, "points": list(ks)} for t, u, ks in opened]})
            out = ((f"Research: {topic}\n\n{brief}" if brief else f"Research: {topic} — {len(opened)} pages read; the document has the key points per page with links and pictures.") +
                   (f"\nYou added “{change}” while I worked: " + (f"{len(extra)} page(s) on it are in the document, marked." if extra else "I searched for it but found nothing solid.") if change else "") +
                   (f"\n{self._widen_line(widen_info)}" if widen_info is not None else "") +
                   f"\n({len(opened)} pages read in {time.time() - t0:.0f}s)")
        elif want_doc:
            self.last_doc = None
            out += "\nNo document this time — none of the pages had anything solid on it. Tell me another angle (other words, a site to start from) and I try again."
        return out

    def _page_image(self, b):
        """A representative picture of the page (og:image or biggest image), ≤ 250 KB, or None."""
        try:
            d = b.page.evaluate("""() => { const og = document.querySelector('meta[property="og:image"], meta[name="twitter:image"]');
                const imgs = Array.from(document.images).filter(i => i.naturalWidth >= 300 && i.naturalHeight >= 200 && !/logo|icon|sprite|avatar|badge/i.test(i.src));
                imgs.sort((a, b) => b.naturalWidth * b.naturalHeight - a.naturalWidth * a.naturalHeight);
                return og && og.content ? new URL(og.content, document.baseURI).href : (imgs[0] ? imgs[0].currentSrc || imgs[0].src : null); }""")
            if not d:
                return None
            if d.startswith("file://"):
                with open(urllib.parse.unquote(d[7:]), "rb") as f:
                    data = f.read()
            else:
                data = b.page.request.get(d, timeout=12000).body()
            if not data or len(data) > 1500000:
                return None
            try:
                from PIL import Image
                import io as _io
                im = Image.open(_io.BytesIO(data)).convert("RGB")
                im.thumbnail((480, 480))
                buf = _io.BytesIO()
                im.save(buf, "JPEG", quality=70)
                return buf.getvalue()
            except Exception:
                return data if len(data) <= 250000 else None
        except Exception:
            return None

    def _research_doc(self, topic, brief, opened, images, change="", extra_urls=()):
        """Write the research as a library document: summary, one option per page (picture, link, key points), sources."""
        from . import library
        doc = library.Doc(f"Research: {topic}", f"{len(opened)} pages read · {time.strftime('%Y-%m-%d %H:%M')}" + (f" · you added: {change}" if change else ""), kind="research")
        if brief:
            doc.summary(brief)
        else:
            doc.summary("Key points per page below; the most useful pages come first. Links open the original." + (f" Pages marked ➕ answer what you added mid-way: “{change}”." if change and extra_urls else ""))
        for i, (title, url, ks) in enumerate(opened):
            doc.option(("➕ " if url in extra_urls else "") + title, url, image=images.get(url), facts={f"Point {j + 1}": k for j, k in enumerate(ks[:5])}, grade="ok")
        for title, url, _ in opened:
            doc.source(url, title)
        path = doc.save(f"research-{topic[:40]}")
        self.log("doc_saved", title=doc.title, options=len(opened))
        return path

    def summarize(self, url, max_points=8):
        if not re.match(r"^(?:https?://)?(?:[\w-]+(?:\.[\w-]+)*\.[a-z]{2,63}|localhost|\d{1,3}(?:\.\d{1,3}){3})(?::\d+)?(?:[/?#]|$)|^file:///", url.strip(), re.I):
            return f"“{url.strip()[:60]}” is not a web address, so there is no page to summarize — send me the link, or tell me what you want in a few more words."
        with self._session() as b:
            if url.lower().endswith(".pdf"):
                text = b.download_text(url); title = url
            else:
                b.open(url)
                if b.status() == "captcha":
                    self.pass_wall(b, url, essential=True)
                if b.status() != "ok":
                    return f"{url}: page shows a {b.status()} wall I couldn't get past" + (" (I tried the checkbox and asked you)." if b.status() == "captcha" else " (I never log in by myself).")
                title = b.page.title(); text = b.extract_text()
        self._release_page()
        heads = [h for h in (clean(l).strip("# ").strip() for l in text.split("\n") if l.startswith("#")) if 3 < len(h) < 80][:12]
        topic = " ".join(re.findall(r"[A-Za-z]+", title)[:6])
        ks = key_sentences(text, topic, limit=max_points) or key_sentences(text, " ".join(heads[:3]), limit=max_points)
        out = [f"Summary of: {title}", url]
        if heads:
            out.append("Sections: " + " | ".join(heads))
        if self.planner and self.planner.installed() and len(text) > 200:
            try:
                summary = self.planner.chat(
                    "You summarize web pages for a busy store owner. Plain words, no fluff.",
                    f"PAGE: {title}\n\n{clean(text)[:6000]}\n\nGive: one sentence on what the page is, then 3-6 bullet points with the most useful concrete facts (numbers, steps, warnings).",
                    max_tokens=260)
                out.append(summary)
                out.append(f"({len(text)} characters read)")
                res = "\n".join(out)
                if self.memory:
                    self.memory.note("summary", title or url, summary, [url])
                return res
            except Exception as e:
                self.log("summary_failed", error=str(e)[:100])
        out += [f"• {s}" for s in ks] or ["(no clear key sentences found — page may be mostly images/scripts)"]
        out.append(f"({len(text)} characters read)")
        if self.memory:
            self.memory.note("summary", title or url, "\n".join(ks), [url])
        return "\n".join(out)

    def compare_suppliers(self, product, n_pages=3, want_doc=False):
        rows = []
        with self._session() as b:
            queries = [f"{product} dropshipping supplier", f"{product} wholesale supplier Europe"]
            seen = set()
            for q in queries:
                if self._stopped() or self._over_budget() or (self._hurried() and rows):
                    break
                try:
                    results = b.search_results(q, 10)
                except BrowserError:
                    continue
                for r in self.walls.order(results):
                    if self._stopped() or self._over_budget():
                        break
                    if r["url"] in seen or FORUM.search(r["url"]) or len(rows) >= (n_pages if self._hurried() else n_pages * 2) or self.walls.skip(r["url"]):
                        continue
                    seen.add(r["url"])
                    try:
                        b.open(r["url"])
                        if b.status() == "captcha":
                            self.pass_wall(b, r["url"])
                        if b.status() != "ok":
                            self.log("task_wall", url=r["url"], wall=b.status()); self.walls.hit(r["url"], b.status())
                            continue
                        text = b.extract_text()
                        self.walls.clear(r["url"])
                    except BrowserError:
                        continue
                    dom = urllib.parse.urlparse(r["url"]).netloc.replace("www.", "")
                    prices = re.findall(r"(?:€|\$|£)\s?\d+(?:[.,]\d+)?", text)[:5]
                    ship = re.findall(r"\b\d+\s?(?:-|to)\s?\d+\s?(?:business )?days\b", text, re.I)[:3]
                    moq = re.findall(r"\bMOQ\b[^.]{0,60}|\bminimum order[^.]{0,60}", text, re.I)[:2]
                    kind = "directory/list" if re.search(r"\b(best|top \d+|list of)\b", (b.page.title() or ""), re.I) else "supplier/site"
                    rows.append((dom, kind, (b.page.title() or "")[:70], ", ".join(prices) or "-", ", ".join(ship) or "-", "; ".join(m.strip() for m in moq) or "-", r["url"]))
        if not rows:
            return f"Supplier comparison for {product}: nothing readable found (search blocked or pages behind walls)."
        out = [f"Supplier comparison: {product}", "site | kind | page | prices seen | shipping times | MOQ notes"]
        out += [" | ".join(r[:6]) for r in rows]
        out.append("Note: read-only research; nothing was contacted or ordered.")
        if self.memory:
            self.memory.note("suppliers", product, "\n".join(out[2:-1]), [r[6] for r in rows])
        if want_doc:
            from . import library
            doc = library.Doc(f"Comparison: {product}", f"{len(rows)} sites · {time.strftime('%Y-%m-%d %H:%M')}", kind="compare")
            doc.summary(f"{len(rows)} sites compared for {product}. Prices, shipping times and minimum-order notes are exactly as the pages state them; "
                        "nothing was contacted or ordered. Supplier sites are more useful than directory lists.")
            doc.table("Side by side", [(r[0], r[1], r[2], r[3], r[4], r[5]) for r in rows], header=["site", "kind", "page", "prices seen", "shipping times", "MOQ notes"])
            for r in rows:
                doc.option(r[2] or r[0], r[6], price=r[3] if r[3] != "-" else "", grade="ok",
                           facts={k: v for k, v in (("Kind", r[1]), ("Prices seen", r[3]), ("Shipping times", r[4]), ("Minimum order", r[5])) if v and v != "-"})
                doc.source(r[6], r[2])
            self.last_doc = doc.save(f"compare-{product[:40]}")
            self.log("doc_saved", title=doc.title, options=len(rows))
            out = [f"Supplier comparison: {product} — {len(rows)} sites, best-looking first in the document (table with prices, shipping, MOQ, links)."]
        return "\n".join(out)

    def exam(self, bank, n=40, seed=1):
        """Sit n questions. Retrieval solver first; the thinking model (with the retrieved passages as evidence) decides."""
        import json as _json, random
        from .mcq import MCQSolver
        qs = [_json.loads(l) for l in open(bank, encoding="utf-8") if l.strip()]
        random.seed(seed)
        qs = random.sample(qs, min(n, len(qs)))
        S = MCQSolver()
        use_llm = bool(self.planner and self.planner.installed())
        ok = ok_ret = 0
        t0 = time.time()
        for i, q in enumerate(qs):
            idx, conf, _ = S.answer(q["q"], q["choices"])
            ok_ret += idx == q["answer"]
            if use_llm:
                d = S.brain(q["q"])
                ev = "\n".join(f"[{h.get('title', '')}] {h.get('text', '')}" for h in d.get("hits", [])[:5])
                try:
                    li, lconf, _ = self.planner.mcq(q["q"], q["choices"], ev + f"\n(retrieval solver suggests {'ABCDEFGH'[idx]}, confidence {conf:.2f})")
                    idx = li
                except Exception:
                    pass
            ok += idx == q["answer"]
            if self.viewer:
                self.viewer.task = f"exam {i+1}/{len(qs)} — {ok} right so far"
        mode = "thinking model + knowledge brain" if use_llm else "knowledge brain only"
        return (f"Exam {bank.split('/')[-1]}: {ok}/{len(qs)} correct ({100*ok/len(qs):.0f}%) — {mode}, {time.time()-t0:.0f}s.\n"
                f"(retrieval alone would have scored {ok_ret}/{len(qs)})")

    def ask(self, question):
        """Answer from what I already know (knowledge pack + my notes), written by the thinking model."""
        ev, titles = [], []
        if self.brain and self.brain.ready:
            hits = []
            for pack in self.brain.refresh():
                d = self.brain.ask_raw(question, pack) or {}
                for h in d.get("hits", [])[:5]:
                    h["_pack"] = pack.rsplit("/", 1)[-1]
                    hits.append(h)
            hits.sort(key=lambda h: -float(h.get("score", 0)))
            for h in hits[:6]:
                tag = " (learned by me)" if h["_pack"].startswith("learned") else ""
                ev.append(f"[{h.get('title', '')}{tag}] {h.get('text', '')}")
                titles.append(h.get("title", ""))
        if self.memory:
            rec = self.memory.recall(question)
            if rec:
                ev.append(rec)
        if not ev:
            return None
        if self.planner and self.planner.installed():
            try:
                return self.planner.answer(question, "\n".join(ev))
            except Exception as e:
                self.log("answer_failed", error=str(e)[:100])
        return self.brain.ask(question) if self.brain and self.brain.ready else None

    SITES = {"youtube": "https://www.youtube.com/feed/trending", "amazon": "https://www.amazon.com/gp/bestsellers",
             "ebay": "https://www.ebay.com/trending", "etsy": "https://www.etsy.com/trending", "aliexpress": "https://www.aliexpress.com",
             "shopify": "https://www.shopify.com", "google trends": "https://trends.google.com/trending?geo=US",
             "reddit": "https://www.reddit.com/r/dropship/", "tiktok": "https://www.tiktok.com/discover",
             "temu": "https://www.temu.com", "alibaba": "https://www.alibaba.com", "product hunt": "https://www.producthunt.com"}

    NEEDS_LOGIN = {"youtube": "YouTube hides its trending/recommendation feeds from visitors without an account or cookies",
                   "tiktok": "TikTok shows nothing to a browser without an account", "reddit": "Reddit blocks automated browsers"}

    def _look_at_page(self, shot, question=None):
        """Eyes on a screenshot when the page text is useless: OCR lines + one vision answer. '' if the eyes are off."""
        if not (self.eyes and shot):
            return ""
        try:
            d = self.eyes.describe(shot)
            if d["kind"] in ("captcha", "login") or any(w in ("captcha", "login wall") for w in d["warnings"]):
                return f"it shows a {d['kind'] if d['kind'] in ('captcha', 'login') else 'login'} wall — I stopped (I never pass CAPTCHAs or log in)."
            parts = [f"• {d['summary']}" if d["summary"] else ""]
            words0 = " ".join(l["text"].lower() for l in self.eyes.lines(shot)) if self.eyes.ocr else ""
            if re.search(r"try searching to get started|start watching videos", words0):
                return ("YouTube shows me an empty home page ('Try searching to get started') because I'm not signed in — there is no "
                        "trending list on it. Ask me to /watch <topic> instead: I search videos directly and read their captions.")
            if question:
                ans = self.eyes.look(shot, question + " Answer only from what is visible; say 'not visible' if it is not on the screen.", max_tokens=140)
                if ans:
                    parts.append(f"• {ans}")
            words = self.eyes.lines(shot) if self.eyes.ocr else []
            good = [l["text"] for l in words if len(l["text"]) > 12][:10]
            if good:
                parts.append("• Text I can read on it: " + " | ".join(good)[:600])
            parts.append("(seen with my eyes, not read from the page — treat as approximate)")
            return "\n".join(p for p in parts if p)
        except Exception as e:
            self.log("look_failed", error=str(e)[:100])
            return ""

    def visit(self, site, question=""):
        """Go to a site (name or URL), read what is on it, and answer the owner's question from the page — grounded."""
        key = site.lower().strip(" .?")
        url = site if re.match(r"^https?://", site) else self.SITES.get(key) or self.SITES.get(key.replace("the ", "")) or None
        if not url:
            url = "https://" + re.sub(r"[^a-z0-9.-]", "", key) + ("" if "." in key else ".com")
        with self._session() as b:
            try:
                b.open(url)
            except BrowserError as e:
                return f"I couldn't open {url}: {e}"
            st = b.status()
            if st == "captcha" and self.pass_wall(b, url, essential=True):
                st = b.status()
            title, final = b.page.title(), b.page.url
            if st != "ok":
                return (f"I opened {final} but it shows a {st} wall I couldn't get past" + (" (I never log in by myself)" if st == "login" else " — I tried the checkbox and asked you") + ". Screenshot: /screen")
            text = clean(b.extract_text())
            if len(text) < 300:
                b.scroll("down", 2)
                text = clean(b.extract_text())
            lines = [l.strip(" #•") for l in text.splitlines() if len(l.strip(" #•")) > 2]
            thin = len(lines) < 8 or bool(re.search(r"try searching to get started|start watching videos|sign in to|log in to see", text, re.I))
            shot = b.page.screenshot(type="png", timeout=8000) if (thin and self.eyes) else None
        self._release_page()
        page = "\n".join(lines)[:3500]
        note = self.NEEDS_LOGIN.get(key.split()[0]) if key.split() else None
        if thin:
            seen = self._look_at_page(shot, question) if shot else ""
            if seen:
                out = f"{title} — {final}\n\nThe page text is empty for me, so I looked at the screen instead:\n{seen}"
            else:
                out = (f"{title} — {final}\n\nThe page shows almost nothing to me" + (f": {note}." if note else " (empty or script-only page).") +
                       " I won't guess at its contents. Screenshot: /screen")
            if self.memory:
                self.memory.note("visit", f"{site}: {question}"[:120], out, [final])
            return out
        if self.planner and self.planner.installed():
            try:
                q = question or "What is on this page? List the main items or headlines."
                ans = self.planner.chat(
                    "You read a web page for your owner and answer ONLY with items that appear word-for-word in the page text. "
                    "Number the items. If the page text does not contain what was asked, reply exactly: NOT ON PAGE",
                    f"PAGE TITLE: {title}\nURL: {final}\nPAGE TEXT:\n{page}\n\nOWNER ASKED: {q}", max_tokens=220, timeout=150)
                # grounding check: every listed item must really occur in the page text
                low = page.lower()
                items = [re.sub(r"^\d+[.)]\s*", "", l).strip(" \"'") for l in ans.splitlines() if re.match(r"^\d+[.)]", l.strip())]
                bad = [i for i in items if len(i) > 3 and i.lower()[:40] not in low]
                if "NOT ON PAGE" in ans or (items and len(bad) > len(items) // 2):
                    ans = ("What was asked is not on this page as I see it" + (f" ({note})" if note else "") +
                           ". Here is what the page actually shows:\n" + "\n".join(f"• {l}" for l in lines[:12]))
                out = f"{title} — {final}\n\n{ans}"
            except Exception as e:
                self.log("visit_answer_failed", error=str(e)[:100])
                out = f"{title} — {final}\n\n" + "\n".join(f"• {l}" for l in lines[:25])
        else:
            out = f"{title} — {final}\n\n" + "\n".join(f"• {l}" for l in lines[:25])
        if self.memory:
            self.memory.note("visit", f"{site}: {question}"[:120], out, [final])
        return out

    def youtube_trending(self, limit=10, topic="", with_comments=None, want_doc=None):
        """What's hot on YouTube. The trending feed is hidden from visitors, so this reads the public search page sorted
        by views for the week (ytInitialData) — no browser needed. With a document: one card per video, link, channel,
        views, upload time and the top comment. Falls back to the real browser feed only when that reader finds nothing."""
        want_doc = self.want_doc if want_doc is None else want_doc
        n = max(1, min(int(limit or 10), 15))
        try:
            vids, note = video.hot_now(topic, n)
        except Exception as e:
            self.log("hot_now_failed", error=str(e)[:120])
            vids, note = [], f"YouTube search failed: {str(e)[:100]}"
        if not vids:
            try:
                with self._session() as b:
                    b.open("https://www.youtube.com/feed/trending")
                    import time as _t
                    _t.sleep(3)
                    entries = video.extract_trending(b.page.content(), n)
                self._release_page()
                vids = [dict(e, url=f"https://www.youtube.com/watch?v={e['id']}", published="", length="") for e in entries]
                note = "From YouTube's trending page in my browser."
            except Exception as e:
                self.log("trending_empty", error=str(e)[:80])
            if not vids:
                return f"I couldn't read YouTube right now ({note}). Try again in a minute, or give me a topic: /trending <topic>."
        if with_comments is None:
            with_comments = want_doc or n <= 5
        if with_comments:
            for v in vids:
                if self._stopped():
                    break
                try:
                    cs, _ = video.top_comments(v["id"], 1)
                    v["top_comment"] = cs[0] if cs else None
                except Exception as e:
                    self.log("comments_failed", id=v["id"], error=str(e)[:80])
                    v["top_comment"] = None
        head = f"🔥 Hot on YouTube this week" + (f" — {topic}" if topic else "") + f" (top {len(vids)} by views):"
        lines = [head]
        for i, v in enumerate(vids, 1):
            meta = " · ".join(x for x in (v.get("channel", ""), f"{v['views']:,} views" if v.get("views") else "", v.get("published", "")) if x)
            lines.append(f"{i}. {v['title']}" + (f" ({meta})" if meta else "") + f"\n   {v['url']}")
            tc = v.get("top_comment")
            if tc:
                lines.append(f"   💬 {tc['author']} ({tc['likes']:,} ♥): {tc['text'][:160]}")
        lines.append(f"ℹ️ {note}")
        if want_doc:
            try:
                from . import library
                doc = library.Doc("YouTube — hot this week" + (f": {topic}" if topic else ""), f"top {len(vids)} by views · {time.strftime('%Y-%m-%d %H:%M')}", kind="trending")
                doc.summary(note)
                doc.table("The list", [[i, f"[{v['title']}]({v['url']})", v.get("channel", ""), f"{v['views']:,}" if v.get("views") else "", v.get("published", ""), v.get("length", "")]
                                       for i, v in enumerate(vids, 1)], header=["#", "Video", "Channel", "Views", "Uploaded", "Length"])
                for v in vids:
                    tc = v.get("top_comment")
                    doc.option(v["title"], v["url"], price=f"{v['views']:,} views" if v.get("views") else "",
                               facts={"Channel": v.get("channel", ""), "Uploaded": v.get("published", ""), "Length": v.get("length", ""),
                                      "Top comment": (f"{tc['author']} ({tc['likes']:,} ♥): {tc['text']}" if tc else ("(comments off or not readable)" if with_comments else ""))})
                self.last_doc = doc.save("youtube-hot-" + (topic[:30] or "week"))
                self.last_native = ("trending", {"title": doc.title, "note": note, "videos": vids})
                self.log("doc_saved", title=doc.title, options=len(vids))
            except Exception as e:
                self.log("trending_doc_failed", error=str(e)[:120])
        if self.memory:
            try:
                self.memory.note("trending", f"YouTube hot this week {topic}".strip(), "\n".join(lines[1:1 + len(vids) * 2]), [v["url"] for v in vids])
            except Exception:
                pass
        return "\n".join(lines)

    def topic_top(self, query, n=5):
        """Top videos for a topic ranked by views (all time). Search-page reader: works anywhere, no browser."""
        try:
            vids = video.top_for_topic(query, n)
        except Exception as e:
            return f"YouTube search failed: {str(e)[:100]}"
        if not vids:
            return f"No videos found for '{query}'."
        lines = [f"🔥 Most-watched on '{query}':"]
        for i, v in enumerate(vids, 1):
            meta = " · ".join(x for x in (v.get("channel", ""), f"{v['views']:,} views" if v.get("views") else "", v.get("published", "")) if x)
            lines.append(f"{i}. {v['title']}" + (f" ({meta})" if meta else "") + f"\n   https://www.youtube.com/watch?v={v['id']}")
        return "\n".join(lines)

    def video_comments(self, what, n=5):
        """Top comments on a video, most-liked first — read from the same JSON the watch page loads (no browser);
        the real browser is only the fallback."""
        vid = video.url_id(what)
        if not vid:
            try:
                found = video.search(what, 1)
            except Exception as e:
                return f"YouTube search failed: {str(e)[:100]}"
            if not found:
                return f"No videos found for '{what}'."
            vid = found[0]["id"]
        comments, meta = [], {}
        try:
            comments, meta = video.top_comments(vid, n)
        except Exception as e:
            self.log("comments_failed", id=vid, error=str(e)[:100])
        if not comments:
            try:
                with self._session() as b:
                    b.open(f"https://www.youtube.com/watch?v={vid}")
                    import time as _t
                    _t.sleep(2)
                    for _ in range(6):
                        b.scroll("down", 2)
                        _t.sleep(1)
                    comments = video.extract_comments(b.page.content(), n)
                self._release_page()
            except Exception as e:
                self.log("comments_browser_failed", id=vid, error=str(e)[:80])
        if not comments:
            return f"No readable comments on https://www.youtube.com/watch?v={vid} (comments may be off)."
        title = f" — {meta['title']}" if meta.get("title") else ""
        lines = [f"💬 Top comments{title} (https://www.youtube.com/watch?v={vid}):"]
        for c in comments:
            lines.append(f"• {c['author']} ({c['likes']:,} ♥): {c['text'][:280]}")
        return "\n".join(lines)

    def watch(self, what, n_videos=1):
        """'Watch' a video (URL/id) or the best video for a topic by reading its captions; summarize with the model."""
        vid = video.url_id(what)
        if vid:
            picks = [{"id": vid, "title": ""}]
        else:
            try:
                picks = [v for v in video.search(what, 8) if v["id"]][:n_videos + 3]
            except Exception as e:
                return f"YouTube search failed: {str(e)[:100]}"
            if not picks:
                return f"No videos found for '{what}'."
        out, done = [], 0
        for v in picks:
            if done >= n_videos:
                break
            try:
                text, meta = video.transcript(v["id"])
            except Exception as e:
                self.log("transcript_error", id=v["id"], error=str(e)[:100])
                continue
            title = meta.get("title") or v.get("title") or v["id"]
            url = f"https://www.youtube.com/watch?v={v['id']}"
            if len(text) < 400:
                self.log("video_no_captions", id=v["id"])
                continue
            done += 1
            mins = meta.get("seconds", 0) // 60
            head = f"▶ {title} — {meta.get('channel', '')} ({mins} min, {'auto' if meta.get('auto') else 'human'} captions)\n{url}"
            summary = None
            if self.planner and self.planner.installed():
                self._release_page()
                try:
                    summary = self.planner.chat(
                        "You watched a business video for your owner (you have its transcript). Plain words, no hype.",
                        f"TITLE: {title}\nTRANSCRIPT (may be auto-generated, no punctuation):\n{text[:7000]}\n\n"
                        "Give: one sentence on what the video is about, then 4-6 bullet points with the concrete, useful claims "
                        "(numbers, steps, warnings). Finish with one line: 'Trust: ' and whether the speaker is selling something.",
                        max_tokens=320, timeout=240)
                except Exception as e:
                    self.log("watch_summary_failed", error=str(e)[:100])
            if not summary:
                summary = "Transcript excerpt: " + text[:900]
            out.append(head + "\n" + summary)
            if self.memory:
                self.memory.note("video", title, summary, [url])
        if not out:
            return f"I found videos for '{what}' but none had readable captions, so I couldn't watch them."
        return "\n\n".join(out)

    def study(self, goal):
        return self.on_hands(self._study, goal)

    def _study(self, goal):
        """One self-directed study session on a learning goal: pick an angle not yet covered, research it, keep the note."""
        angles_done = goal.get("angles", [])
        angle = goal["topic"]
        if self.planner and self.planner.installed():
            try:
                raw = self.planner.chat("You plan research for a small online-store owner. Output one line only.",
                                        f"Learning goal: {goal['topic']}\nAlready researched angles: {angles_done or 'none'}\n"
                                        "Give ONE new web-search query (max 10 words) about a different aspect of this goal "
                                        "(e.g. costs, how it works, best options, risks, how to start). It MUST keep the goal's key words.",
                                        max_tokens=30, stop=["\n"])
                cand = raw.strip().strip('"')
                keys = [w for w in re.findall(r"[a-z]{4,}", goal["topic"].lower()) if w not in ("with", "from", "about", "that", "this")]
                if cand and sum(k in cand.lower() for k in keys) >= max(1, len(keys) // 2):
                    angle = cand
                else:
                    angle = f"{goal['topic']} " + ["how it works", "costs and pricing", "best options compared", "risks and problems", "how to start", "reviews"][len(angles_done) % 6]
            except Exception:
                pass
        out = self.research(angle)
        self.memory.studied(goal["id"], angle)
        return angle, out

    # ---- walls: try, then try something else (milestone 15) ---------------------------------
    accounts = None           # set by the agent: Accounts has solve_captcha / captcha_fallback
    captcha_stats = {"tried": 0, "passed": 0, "skipped": 0, "owner": 0}

    def pass_wall(self, b, url, essential=False, site=None):
        """A page shows a CAPTCHA/bot check. Try the simple solvers (checkbox, frame checkbox, text-in-image with the eyes,
        press-and-hold); if that fails and the page is essential (the owner asked for THIS page) ask the owner for one tap;
        otherwise skip it and let the caller use another page. Returns True when the page is now readable."""
        site = site or (urllib.parse.urlparse(url).netloc or url)[:60]
        site = re.sub(r"^(www|it|m)\.", "", site)
        self.captcha_stats["tried"] += 1
        acc = self.accounts
        if acc is not None and hasattr(acc, "captcha_budget") and acc.captcha_budget(site) <= 0:
            self.log("captcha_budget_spent", site=site)
            self.captcha_stats["skipped"] += 1
            return False
        passed = False
        try:
            if acc is not None and hasattr(acc, "solve_captcha"):
                self.log("captcha_try", site=site)
                if acc.solve_captcha(b, site, eyes=self.eyes):
                    passed = True
        except Exception as e:
            self.log("captcha_try_error", site=site, error=str(e)[:80])
        if not passed and essential and acc is not None and hasattr(acc, "captcha_fallback"):
            self.captcha_stats["owner"] += 1
            try:
                shot = None
                try:
                    shot = b.page.screenshot(type="jpeg", quality=70, timeout=6000)
                except Exception:
                    pass
                if acc.captcha_fallback(site, url, timeout=150, b=b, screenshot=shot):
                    if self._wall_cleared(b, url):
                        passed = True
            except Exception as e:
                self.log("captcha_fallback_error", site=site, error=str(e)[:80])
        if acc is not None and hasattr(acc, "captcha_spent"):
            acc.captcha_spent(site, passed)
        if passed:
            self.captcha_stats["passed"] += 1
            try:
                b.save_session()                                           # the solved check lives in cookies: keep them for next time
            except Exception:
                pass
            self.notify(f"🧩 Passed the security check on {site}{' by myself' if self.captcha_stats['owner'] == 0 else ' with your tap'} — session kept, it should not ask again for a while.")
            return True
        self.captcha_stats["skipped"] += 1
        self.log("captcha_skipped", site=site, essential=essential)
        return False

    @staticmethod
    def _wall_cleared(b, url):
        """After the owner's tap: the page may already have moved on by itself; else reload the wanted url and look again."""
        try:
            if b.status() == "ok" and not re.search(r"/risk/|/challenge|captcha", b.page.url, re.I):
                return True
            b.page.goto(url, wait_until="domcontentloaded", timeout=20000)
            time.sleep(2)
            return b.status() == "ok" and not re.search(r"/risk/|/challenge|captcha", b.page.url, re.I)
        except Exception:
            return False

    def _stopped(self):
        """True when the owner said stop mid-job — long loops check this between pages."""
        p = self.pace
        return bool(p and hasattr(p, "should_stop") and p.should_stop())

    def _over_budget(self):
        """Quiet-time budget used up → long loops wrap up early (owner may be back)."""
        try:
            return bool(self.pace and self.pace.over_budget())
        except Exception:
            return False

    def _hurried(self):
        p = self.pace
        return bool(p and hasattr(p, "hurry") and p.hurry())

    # ---- dispatcher ----------------------------------------------------
    want_doc = False          # set by the agent per job: the owner asked for a document (links + pictures), not a chat dump
    last_doc = None           # path of the last document written by research/compare
    last_native = None        # (kind, payload) for the native Google Doc template of the last document (progress.Templates)
    owner_change = ""         # what the owner said mid-job ("also look at prices in germany") — research reads one more page for it

    _machine_fault = ""          # the last machine-level failure text ("" when the last browser start went fine)

    def browser(self):
        if self._browser is None or not self._browser.alive():
            try:
                self._browser = Browser(log=self.log, viewer=self.viewer, lean=self.low_mem)
            except Exception as e:
                Tasks._machine_fault = str(e)[:200]
                raise
            Tasks._machine_fault = ""
            self._browser.walls = self.walls
        return self._browser

    def run(self, command, want_doc=None):
        if want_doc is not None:
            self.want_doc = bool(want_doc)
        self.last_doc = None
        self.last_native = None
        try:
            return self.on_hands(self._run, command)
        finally:
            self.want_doc = False

    def _run(self, command):
        """'research <topic>' | 'compare <product>' | 'summarize <url>' | 'visit <site> [, question]' | 'exam [n]'"""
        cmd, _, arg = command.strip().partition(" ")
        cmd = cmd.lower()
        t0 = time.time()
        self.log("task_start", cmd=cmd, arg=arg)
        try:
            if cmd == "research" and arg:
                out = self.research(arg, want_doc=self.want_doc)
            elif cmd in ("compare", "suppliers") and arg:
                out = self.compare_suppliers(arg, want_doc=self.want_doc)
            elif cmd in ("summarize", "summarise", "read") and arg:
                out = self.summarize(arg)
            elif cmd in ("watch", "video") and arg:
                out = self.watch(arg)
            elif cmd in ("trending", "hot"):
                a = arg.strip()
                m_ = re.match(r"^(\d{1,2})\s*(.*)$", a)
                n_, a = (int(m_.group(1)), m_.group(2).strip()) if m_ else (5 if self.want_doc else 10, a)
                out = self.youtube_trending(limit=n_, topic="" if a.lower() in ("", "global", "youtube") else a)
            elif cmd == "topvideos" and arg:
                out = self.topic_top(arg.strip())
            elif cmd in ("comments", "comment") and arg:
                out = self.video_comments(arg)
            elif cmd in ("visit", "open", "goto") and arg:
                site, _, question = arg.partition("|")
                out = self.visit(site.strip(), question.strip())
            elif cmd == "exam":
                n = int(arg) if arg.strip().isdigit() else 40
                out = self.exam(str(config.ROOT / "tests/banks/mcq_principles-marketing.jsonl"), n)
            else:
                out = "Tasks I can do: research <topic> · compare <product> · summarize <url> · visit <site> | <question> · watch <video url or topic> · trending [topic] · comments <video> · exam [n]"
        except Exception as e:  # noqa
            out = f"Task failed: {type(e).__name__}: {str(e)[:200]}"
            fix = self.machine_fix(str(e))
            if fix:                                                    # the machine, not the job: say what to do, in the owner's words
                out += "\n" + fix
                self.log("machine_fault", cmd=cmd, error=str(e)[:120])
        self.log("task_done", cmd=cmd, ms=int((time.time() - t0) * 1000), chars=len(out))
        return out

    @staticmethod
    def machine_fix(error):
        """A plain-words repair line for failures that are the PC's, not the plan's (browser missing, module missing, no space)."""
        e = error or ""
        if re.search(r"BrowserType\.launch|Executable doesn't exist|playwright install", e, re.I):
            return ("🔧 My browser is not installed on this machine, so I cannot read any web page until it is. Run the doctor line once "
                    "(PowerShell): wsl bash -lc \"curl -sL https://raw.githubusercontent.com/dreamer2664/businessai2/main/scripts/doctor.sh | bash\" — it installs it and restarts me.")
        if re.search(r"No module named|ModuleNotFoundError", e, re.I):
            return "🔧 A Python piece is missing on this machine. The doctor line fixes it (PowerShell): wsl bash -lc \"curl -sL https://raw.githubusercontent.com/dreamer2664/businessai2/main/scripts/doctor.sh | bash\""
        if re.search(r"No space left|ENOSPC|Errno 28", e, re.I):
            return "🔧 The disk is full — say /disk clean and I free what is safe to free."
        if re.search(r"cannot allocate memory|MemoryError|out of memory", e, re.I):
            return "🔧 The machine ran out of memory — close other programs or restart the PC, then ask me again."
        return ""
