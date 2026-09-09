"""Watching the disk (owner's rule: "watch disk — du -sh release state ~/.cache").

The agent runs for months on the owner's PC; nothing may fill the disk quietly. This module measures, prunes only what
is safe and rebuildable, and speaks in plain words: one line in /status, a warning to the owner once a day when the
free space is low, `/disk` for the details.

Safe to prune (all regenerable, none of it owner data):
  state/logs/*.jsonl      day logs older than KEEP_LOGS_DAYS
  state/logs/llm.log      thinking-model output, capped at LOG_CAP bytes (tail kept)
  state/desktop/*.png|jpg screenshots older than KEEP_SHOTS_DAYS
  state/journal.jsonl     the mind's step journal, capped at JOURNAL_LINES lines (tail kept)
  ~/.cache/bai/web*/      raw fetches of the knowledge-pack pipeline older than KEEP_CACHE_DAYS
  ~/.cache/pip            pip's download cache (pip re-downloads on demand)

Never touched: state/library (the owner's documents), notes/lessons/todo/accounts/store, release/ (models, packs),
~/.cache/ms-playwright (the browser: 250 MB but re-downloading it costs minutes and network).
"""
import os
import pathlib
import shutil
import time

from . import config

KEEP_LOGS_DAYS = 30
KEEP_SHOTS_DAYS = 7
KEEP_CACHE_DAYS = 14
LOG_CAP = 2 * 1024 * 1024        # llm.log / agent.out / eyes.log
JOURNAL_LINES = 2000
LOW_FREE_GB = 2.0                # warn the owner below this
CRITICAL_FREE_GB = 0.7           # and stop writing screenshots / raw caches below this

CACHE = pathlib.Path(os.environ.get("BAI_CACHE", pathlib.Path.home() / ".cache"))


def _size(path):
    """Bytes under path (files only). Fast enough for our sizes; errors count as 0."""
    p = pathlib.Path(path)
    if not p.exists():
        return 0
    if p.is_file():
        return p.stat().st_size
    total = 0
    for root, _, files in os.walk(p, onerror=lambda e: None):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def human(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024


class Housekeeping:
    def __init__(self, log=None, state_dir=None, release_dir=None, cache_dir=None, now=None):
        self.log = log or (lambda kind, **f: None)
        self.state = pathlib.Path(state_dir or config.STATE_DIR)
        self.release = pathlib.Path(release_dir or (config.ROOT / "release"))
        self.cache = pathlib.Path(cache_dir or CACHE)
        self.now = now or time.time
        self.last_report = 0
        self.last_warned = 0
        self.last = None                 # last measure()
        self.usage = lambda: shutil.disk_usage(str(self.state if self.state.exists() else pathlib.Path.home()))   # tests pin this

    # ---- measure ------------------------------------------------------------------------------
    def measure(self):
        try:
            du = self.usage()
            free, total = du.free, du.total
        except Exception:
            free = total = 0
        m = {"free": free, "total": total,
             "release": _size(self.release), "state": _size(self.state), "cache": _size(self.cache),
             "library": _size(self.state / "library"), "logs": _size(self.state / "logs"),
             "shots": _size(self.state / "desktop"), "browser": _size(self.cache / "ms-playwright"),
             "packs_cache": sum(_size(p) for p in (self.cache / "bai").glob("*")) if (self.cache / "bai").exists() else 0,
             "pip": _size(self.cache / "pip")}
        m["free_gb"] = m["free"] / 1024 ** 3
        m["level"] = "critical" if 0 < m["free_gb"] < CRITICAL_FREE_GB else ("low" if 0 < m["free_gb"] < LOW_FREE_GB else "ok")
        self.last = m
        return m

    def status_line(self):
        m = self.last or self.measure()
        flag = {"ok": "", "low": " ⚠️ low", "critical": " 🛑 critical"}[m["level"]]
        return (f"disk: {human(m['free'])} free{flag} · release {human(m['release'])} · state {human(m['state'])} "
                f"(library {human(m['library'])}) · cache {human(m['cache'])}")

    def text(self):
        """/disk — the owner's `du -sh release state ~/.cache`, in words, plus what I would clean."""
        m = self.measure()
        lines = [f"💽 Disk: {human(m['free'])} free of {human(m['total'])}" + (" — LOW, I prune what is safe and stop saving screenshots" if m["level"] != "ok" else ""),
                 f"release (models, brain, packs): {human(m['release'])}",
                 f"state: {human(m['state'])} — library {human(m['library'])} (your documents, never pruned) · logs {human(m['logs'])} · screenshots {human(m['shots'])}",
                 f"cache: {human(m['cache'])} — browser {human(m['browser'])} · pack fetches {human(m['packs_cache'])} · pip {human(m['pip'])}",
                 f"I prune by myself: day logs > {KEEP_LOGS_DAYS} days, screenshots > {KEEP_SHOTS_DAYS} days, raw pack fetches > {KEEP_CACHE_DAYS} days, "
                 f"the model log above {human(LOG_CAP)}, the step journal above {JOURNAL_LINES} lines. Say '/disk clean' to do it now."]
        return "\n".join(lines)

    # ---- prune ---------------------------------------------------------------------------------
    def prune(self, aggressive=False):
        """Remove what is safe. Returns {'freed': bytes, 'items': [...]} — never raises, never touches owner data."""
        freed, items = 0, []
        now = self.now()

        def rm(p, why):
            nonlocal freed
            try:
                n = _size(p)
                if pathlib.Path(p).is_dir():
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    os.remove(p)
                freed += n
                items.append(f"{why}: {pathlib.Path(p).name} ({human(n)})")
            except Exception as e:
                self.log("prune_failed", path=str(p)[-60:], error=str(e)[:80])

        logs = self.state / "logs"
        if logs.exists():
            for f in logs.glob("*.jsonl"):
                try:
                    day = time.mktime(time.strptime(f.stem, "%Y-%m-%d"))
                except ValueError:
                    continue
                if now - day > KEEP_LOGS_DAYS * 86400:
                    rm(f, "old day log")
            for name in ("llm.log", "agent.out", "eyes.log"):
                f = logs / name
                try:
                    if f.exists() and f.stat().st_size > LOG_CAP:
                        data = f.read_bytes()
                        f.write_bytes(data[-LOG_CAP // 2:])
                        freed += len(data) - LOG_CAP // 2
                        items.append(f"trimmed {name} ({human(len(data))} → {human(LOG_CAP // 2)})")
                except Exception as e:
                    self.log("prune_failed", path=name, error=str(e)[:80])
        shots = self.state / "desktop"
        if shots.exists():
            for f in list(shots.glob("*.png")) + list(shots.glob("*.jpg")):
                try:
                    if now - f.stat().st_mtime > KEEP_SHOTS_DAYS * 86400:
                        rm(f, "old screenshot")
                except OSError:
                    pass
        j = self.state / "journal.jsonl"
        try:
            if j.exists():
                lines = j.read_text(encoding="utf-8", errors="replace").splitlines()
                if len(lines) > JOURNAL_LINES:
                    before = j.stat().st_size
                    j.write_text("\n".join(lines[-JOURNAL_LINES // 2:]) + "\n", encoding="utf-8")
                    freed += before - j.stat().st_size
                    items.append(f"trimmed the step journal ({len(lines)} → {JOURNAL_LINES // 2} lines)")
        except Exception as e:
            self.log("prune_failed", path="journal", error=str(e)[:80])
        bai = self.cache / "bai"
        if bai.exists():
            for d in bai.iterdir():
                if not d.is_dir() or not (d.name.startswith("web") or d.name.startswith("ext_") or d.name in ("txt",)):
                    continue                       # known_emb/known_keys (the embedding cache) stay: they save minutes on every rebuild
                try:
                    newest = max((p.stat().st_mtime for p in d.rglob("*") if p.is_file()), default=d.stat().st_mtime)
                    if now - newest > KEEP_CACHE_DAYS * 86400 or aggressive:
                        rm(d, "raw pack fetch")
                except OSError:
                    pass
        if aggressive and (self.cache / "pip").exists():
            rm(self.cache / "pip", "pip download cache")
        if freed or items:
            self.log("disk_pruned", freed=freed, items=len(items))
        return {"freed": freed, "items": items}

    # ---- the daily glance ----------------------------------------------------------------------
    def due(self, every=6 * 3600):
        return self.now() - self.last_report >= every

    def check(self):
        """Idle-loop call: measure, prune when due, and return a warning for the owner or None (at most one a day)."""
        if not self.due():
            return None
        self.last_report = self.now()
        m = self.measure()
        aggressive = m["level"] != "ok"
        r = self.prune(aggressive=aggressive)
        if aggressive:
            m = self.measure()
        self.log("disk_check", free_gb=round(m["free_gb"], 2), level=m["level"], freed=r["freed"])
        if m["level"] != "ok" and self.now() - self.last_warned >= 86400:
            self.last_warned = self.now()
            return (f"💽 Disk is getting full on my machine: {human(m['free'])} free. I cleaned {human(r['freed'])} of logs and caches "
                    f"({len(r['items'])} items). Biggest pieces: browser {human(m['browser'])}, models/brain {human(m['release'])}, "
                    f"your library {human(m['library'])} (untouched). If it keeps shrinking, free space on the drive or tell me to /disk clean.")
        return None

    def allow_heavy_writes(self):
        """False when critically low: screenshots and raw caches are skipped (documents and notes still saved)."""
        m = self.last or self.measure()
        return m["level"] != "critical"
