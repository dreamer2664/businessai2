"""The project list (owner's item E): brainstorms and the owner's "let's look into X" become projects with steps,
kept in state/projects.json; the next free window (a time floor, quiet time) continues them one step at a time —
so time is never filled with idle filler and an idea from Tuesday is not forgotten by Thursday.

A project is read-only work: reading, comparing, writing a note. Anything that costs money, posts or messages a
customer stays with the owner (the step just proposes it).

    P = Projects()
    P.add("Test a bundle offer for the mugs", why="brainstorm 09 Sep", steps=[...])     -> project dict
    P.from_brainstorm(text)                    -> new projects parsed from the 3 paragraphs of a brainstorm
    P.next_step()                              -> (project, index, step) of the next open step, or None
    P.mark(pid, i, note)                       -> step done with a one-line finding
    P.list_text() / P.done(pid) / P.drop(pid)
"""
import json
import re
import time

from . import config

FILE = config.STATE_DIR / "projects.json"
DEFAULT_STEPS = ["Read 2–3 solid pages on it: what exactly, for whom, what it costs",
                 "Find one number that matters (price, margin, time, demand) and where it comes from",
                 "Write a one-page note: what to try, why, how to test it cheaply — and propose it to the owner"]
MAX_OPEN = 12


class Projects:
    def __init__(self, log=None):
        self.log = log or (lambda kind, **f: None)
        self.data = {"projects": [], "next_id": 1}
        self._load()

    # ---- storage ------------------------------------------------------------------
    def _load(self):
        try:
            if FILE.exists():
                d = json.loads(FILE.read_text(encoding="utf-8"))
                if isinstance(d, dict) and isinstance(d.get("projects"), list):
                    self.data = d
        except Exception as e:
            self.log("projects_load_failed", error=str(e)[:100])

    def _save(self):
        try:
            config.ensure_dirs()
            FILE.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception as e:
            self.log("projects_save_failed", error=str(e)[:100])

    # ---- adding -------------------------------------------------------------------
    def open(self):
        return [p for p in self.data["projects"] if p.get("status") == "open"]

    def get(self, pid):
        for p in self.data["projects"]:
            if p["id"] == int(pid):
                return p
        return None

    def add(self, title, why="", steps=None, source="owner"):
        title = re.sub(r"\s+", " ", str(title)).strip(" .:-—*#").strip()
        if len(title) < 6:
            return None
        for p in self.open():                                            # same idea twice → the same project
            if _same(p["title"], title):
                return p
        if len(self.open()) >= MAX_OPEN and source != "owner":
            return None
        p = {"id": self.data["next_id"], "title": title[:140], "why": str(why)[:300], "source": source,
             "status": "open", "created": time.time(), "updated": time.time(),
             "steps": [{"text": str(s)[:200], "done": False, "note": ""} for s in (steps or DEFAULT_STEPS)][:8]}
        self.data["next_id"] += 1
        self.data["projects"].append(p)
        self._save()
        self.log("project_added", id=p["id"], title=title[:60], source=source)
        return p

    def from_brainstorm(self, text, when=""):
        """A brainstorm is 3 short paragraphs (what / why / how to test) → up to 3 projects. Returns the new ones."""
        out = []
        if not text:
            return out
        paras = [re.sub(r"\s+", " ", x).strip() for x in re.split(r"\n\s*\n|\n(?=\s*(?:\d+[.)]|[-•*])\s)", str(text)) if x.strip()]
        for para in paras[:4]:
            para = re.sub(r"^\s*(?:\d+[.)]|[-•*]|#+)\s*", "", para).strip("* ")
            m = re.match(r"^\**([^.:!?\n]{6,120})[.:!?]?\**", para)
            title = (m.group(1) if m else para[:100]).strip("* ")
            if len(title.split()) < 2 or re.match(r"^(here|these|this|the following|in short|summary)\b", title, re.I):
                continue
            p = self.add(title, why=(f"my own idea during quiet time{(' ' + when) if when else ''}: " + para[:220]), source="brainstorm")
            if p and p["why"].startswith("my own idea") and p["created"] > time.time() - 5:
                out.append(p)
        return out

    # ---- working ------------------------------------------------------------------
    def next_step(self):
        """The next open step, oldest project first (each project advances one step per turn)."""
        for p in sorted(self.open(), key=lambda x: x.get("updated", 0)):
            for i, s in enumerate(p["steps"]):
                if not s["done"]:
                    return p, i, s["text"]
        return None

    def mark(self, pid, i, note=""):
        p = self.get(pid)
        if not p or not 0 <= i < len(p["steps"]):
            return False
        p["steps"][i]["done"] = True
        p["steps"][i]["note"] = str(note)[:400]
        p["updated"] = time.time()
        if all(s["done"] for s in p["steps"]):
            p["status"] = "done"
            p["finished"] = time.time()
        self._save()
        self.log("project_step", id=pid, step=i, done=p["status"] == "done")
        return True

    def done(self, pid):
        p = self.get(pid)
        if not p:
            return False
        p["status"] = "done"; p["finished"] = time.time(); p["updated"] = time.time()
        self._save()
        return True

    def drop(self, pid):
        p = self.get(pid)
        if not p:
            return False
        p["status"] = "dropped"; p["updated"] = time.time()
        self._save()
        return True

    # ---- telling ------------------------------------------------------------------
    def list_text(self, n=8):
        op = self.open()
        if not op:
            return ("No projects yet. They come from my quiet-time brainstorms and from you — say 'new project: test a bundle "
                    "offer for the mugs' and the next free window (a time floor, your away-time) works on it step by step.")
        lines = [f"📁 {len(op)} open project(s) — the next free window continues them (one step at a time):"]
        for p in op[:n]:
            done = sum(1 for s in p["steps"] if s["done"])
            nxt = next((s["text"] for s in p["steps"] if not s["done"]), "")
            lines.append(f"{p['id']}. {p['title']} — {done}/{len(p['steps'])} steps · next: {nxt[:90]}" + (f" · from {p['source']}" if p["source"] != "owner" else ""))
        fin = [p for p in self.data["projects"] if p.get("status") == "done"]
        if fin:
            lines.append(f"✅ {len(fin)} finished: " + " · ".join(p["title"][:40] for p in fin[-3:]))
        lines.append("Say: 'new project: …' · 'drop project 2' · 'project 2 is done' · 'project 2' for its notes.")
        return "\n".join(lines)

    def detail(self, pid):
        p = self.get(pid)
        if not p:
            return "No project with that number — /projects lists them."
        lines = [f"📁 {p['id']}. {p['title']} ({p['status']})", f"why: {p['why'][:200]}" if p.get("why") else ""]
        for i, s in enumerate(p["steps"]):
            lines.append(f"{'✅' if s['done'] else '⬜'} {i + 1}. {s['text']}" + (f"\n   → {s['note'][:200]}" if s["note"] else ""))
        return "\n".join(x for x in lines if x)


def _same(a, b):
    wa = set(re.findall(r"[a-zà-ú0-9]{4,}", a.lower())); wb = set(re.findall(r"[a-zà-ú0-9]{4,}", b.lower()))
    return bool(wa and wb) and len(wa & wb) / max(1, min(len(wa), len(wb))) >= 0.7


OWNER_ADD = re.compile(r"^(?:/projects?\s+add|(?:new|add|start|open)\s+(?:a\s+)?project\s*:?|nuovo\s+progetto\s*:?|let'?s\s+(?:look into|explore|try)\s+(?:the\s+)?(?:project|idea)\s*:?)\s+(.{6,160})$", re.I)
OWNER_DONE = re.compile(r"^(?:/projects?\s+done\s+(\d+)|project\s+(\d+)\s+(?:is\s+)?(?:done|finished|complete)|progetto\s+(\d+)\s+(?:fatto|finito))$", re.I)
OWNER_DROP = re.compile(r"^(?:/projects?\s+drop\s+(\d+)|(?:drop|forget|remove|cancel)\s+(?:the\s+)?project\s+(\d+)|(?:togli|elimina)\s+(?:il\s+)?progetto\s+(\d+))$", re.I)
OWNER_SHOW = re.compile(r"^(?:/projects?\s+(\d+)|project\s+(\d+)|progetto\s+(\d+))$", re.I)
OWNER_LIST = re.compile(r"^(?:/projects?|(?:show|list|what are)\s+(?:me\s+)?(?:the\s+|our\s+|your\s+|my\s+)?projects\??|(?:i\s+)?progetti\??)$", re.I)


def command(P, text):
    """Owner phrasing → reply string, or None when the message is not about projects."""
    t = text.strip().rstrip(" .!")
    m = OWNER_ADD.match(t)
    if m:
        p = P.add(m.group(1), why="you asked", source="owner")
        return (f"📁 Project {p['id']} opened: {p['title']}\nSteps:\n" + "\n".join(f"{i + 1}. {s['text']}" for i, s in enumerate(p["steps"]))
                + "\nI work on it in the next free window (a time floor, or when you're away) and note what I find.") if p else "Give the project a few more words, e.g. 'new project: test a bundle offer for the mugs'."
    m = OWNER_DONE.match(t)
    if m:
        pid = next(g for g in m.groups() if g)
        return f"✅ Project {pid} marked done." if P.done(pid) else "No project with that number — /projects lists them."
    m = OWNER_DROP.match(t)
    if m:
        pid = next(g for g in m.groups() if g)
        return f"🗑 Project {pid} dropped." if P.drop(pid) else "No project with that number — /projects lists them."
    m = OWNER_SHOW.match(t)
    if m:
        return P.detail(next(g for g in m.groups() if g))
    if OWNER_LIST.match(t):
        return P.list_text()
    return None
