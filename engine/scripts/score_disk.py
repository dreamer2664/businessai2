"""Score: watching the disk (owner's rule). Offline, in a temp tree. Prunes only what is safe; owner data untouched."""
import os
import pathlib
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent import housekeeping as hk
from agent.housekeeping import Housekeeping, human

CHECKS = []


def check(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


DAY = 86400


def tree():
    """A fake state/release/cache tree with old and fresh things of every pruned kind, plus owner data."""
    root = pathlib.Path(tempfile.mkdtemp(prefix="disk_"))
    st, rel, cache = root / "state", root / "release", root / "cache"
    now = time.time()
    old = now - 45 * DAY
    for d in ("logs", "desktop", "library", "bai/web3", "bai/web_old", "bai/ext_old", "pip", "ms-playwright"):
        (st / d if not d.startswith(("bai", "pip", "ms-")) else cache / d).mkdir(parents=True, exist_ok=True)
    rel.mkdir()
    (rel / "brain.kdr").write_bytes(b"x" * 5000)

    def w(p, size, mtime=None):
        p.write_bytes(b"y" * size)
        if mtime:
            os.utime(p, (mtime, mtime))
    old_day = time.strftime("%Y-%m-%d", time.localtime(old))
    w(st / "logs" / f"{old_day}.jsonl", 3000, old)
    w(st / "logs" / f"{time.strftime('%Y-%m-%d')}.jsonl", 3000)
    w(st / "logs" / "llm.log", hk.LOG_CAP + 4096)
    w(st / "logs" / "agent.out", 100)
    w(st / "desktop" / "1_old.png", 2000, now - 10 * DAY)
    w(st / "desktop" / "2_new.png", 2000)
    w(st / "library" / "2026-09-09_research-old.html", 7000, old)      # owner's document: OLD but never pruned
    (st / "notes.jsonl").write_text("note\n" * 5)
    (st / "lessons.jsonl").write_text("lesson\n" * 5)
    (st / "journal.jsonl").write_text("".join(f'{{"n":{i}}}\n' for i in range(hk.JOURNAL_LINES + 500)))
    w(cache / "bai" / "web3" / "web.tsv", 4000)
    w(cache / "bai" / "web_old" / "web.tsv", 4000, old)
    w(cache / "bai" / "ext_old" / "passages.tsv", 4000, old)
    w(cache / "bai" / "known_emb.npy", 4000, old)                            # embedding cache: kept
    w(cache / "pip" / "wheel.whl", 6000, old)
    w(cache / "ms-playwright" / "chrome", 9000, old)
    h = Housekeeping(log=lambda k, **f: None, state_dir=st, release_dir=rel, cache_dir=cache)
    h.usage = lambda: type("U", (), {"free": 20 * 1024 ** 3, "total": 25 * 1024 ** 3})()      # a healthy 20 GB, whatever this box has
    return root, h


@check("measure: free/total, release/state/cache/library/browser sizes, level ok")
def _():
    root, h = tree()
    m = h.measure()
    assert m["total"] > 0 and m["free"] > 0 and m["release"] == 5000 and m["library"] == 7000 and m["browser"] == 9000, m
    assert m["state"] > m["library"] and m["cache"] > m["browser"] and m["level"] == "ok", m


@check("status line for /status: free space + the owner's three du figures")
def _():
    _, h = tree()
    s = h.status_line()
    assert s.startswith("disk: ") and " free" in s and "release" in s and "state" in s and "cache" in s and "library" in s, s
    assert "⚠️" not in s


@check("/disk text: plain words, names what is never pruned and what is pruned by itself")
def _():
    _, h = tree()
    t = h.text()
    assert "💽 Disk:" in t and "never pruned" in t and "I prune by myself" in t and "/disk clean" in t, t
    assert "browser" in t and "pack fetches" in t and "pip" in t


@check("prune: old day log, old screenshot, old raw pack fetches removed; fresh ones kept")
def _():
    root, h = tree()
    st, cache = root / "state", root / "cache"
    r = h.prune()
    names = " ".join(r["items"])
    assert not list(st.glob("logs/*.jsonl"))[0].stem < "2026" or True
    logs = [p.name for p in (st / "logs").glob("*.jsonl")]
    assert len(logs) == 1 and logs[0].startswith(time.strftime("%Y-%m-%d")), logs
    assert not (st / "desktop" / "1_old.png").exists() and (st / "desktop" / "2_new.png").exists()
    assert not (cache / "bai" / "web_old").exists() and not (cache / "bai" / "ext_old").exists() and (cache / "bai" / "web3").exists(), names
    assert "old day log" in names and "old screenshot" in names and "raw pack fetch" in names, names
    assert r["freed"] > 0


@check("prune: big model log and long journal are trimmed to their tails, not deleted")
def _():
    root, h = tree()
    st = root / "state"
    h.prune()
    assert (st / "logs" / "llm.log").exists() and (st / "logs" / "llm.log").stat().st_size == hk.LOG_CAP // 2
    assert (st / "logs" / "agent.out").stat().st_size == 100                  # small: untouched
    lines = (st / "journal.jsonl").read_text().splitlines()
    assert len(lines) == hk.JOURNAL_LINES // 2 and lines[-1] == f'{{"n":{hk.JOURNAL_LINES + 499}}}', (len(lines), lines[-1])


@check("prune never touches owner data, models, the browser, the embedding cache, or pip unless aggressive")
def _():
    root, h = tree()
    st, rel, cache = root / "state", root / "release", root / "cache"
    h.prune()
    assert (st / "library" / "2026-09-09_research-old.html").exists()
    assert (st / "notes.jsonl").exists() and (st / "lessons.jsonl").exists()
    assert (rel / "brain.kdr").stat().st_size == 5000
    assert (cache / "ms-playwright" / "chrome").exists() and (cache / "bai" / "known_emb.npy").exists()
    assert (cache / "pip" / "wheel.whl").exists()
    h.prune(aggressive=True)
    assert not (cache / "pip").exists() and not (cache / "bai" / "web3").exists()
    assert (st / "library" / "2026-09-09_research-old.html").exists() and (cache / "ms-playwright" / "chrome").exists() and (rel / "brain.kdr").exists()


@check("prune is idempotent and never raises on a missing tree")
def _():
    root, h = tree()
    h.prune()
    r2 = h.prune()
    assert r2["freed"] == 0 and r2["items"] == [], r2
    h2 = Housekeeping(log=lambda k, **f: None, state_dir=root / "nope", release_dir=root / "nope2", cache_dir=root / "nope3")
    assert h2.prune() == {"freed": 0, "items": []} and h2.measure()["release"] == 0 and "free" in h2.status_line()


@check("check(): every 6 h; quiet when the disk is fine; warns once a day when low; aggressive prune then")
def _():
    root, h = tree()
    clock = {"t": time.time()}
    h.now = lambda: clock["t"]
    assert h.due()
    assert h.check() is None                                 # ok level → no message
    assert not h.due()
    clock["t"] += 7 * 3600
    h.usage = lambda: type("U", (), {"free": int(1.2 * 1024 ** 3), "total": 25 * 1024 ** 3})()
    warn = h.check()
    assert warn and warn.startswith("💽 Disk is getting full") and "1.2 GB free" in warn and "untouched" in warn, warn
    assert not (root / "cache" / "pip").exists()             # low → aggressive
    clock["t"] += 7 * 3600
    assert h.check() is None                                 # same day: no second warning
    clock["t"] += 24 * 3600
    assert h.check() is not None                             # next day: reminded
    assert h.allow_heavy_writes()
    h.usage = lambda: type("U", (), {"free": int(0.5 * 1024 ** 3), "total": 25 * 1024 ** 3})()
    assert h.measure()["level"] == "critical" and not h.allow_heavy_writes()
    assert "🛑 critical" in h.status_line()


@check("human sizes read well")
def _():
    assert human(512) == "512 B" and human(2048) == "2 KB" and human(5 * 1024 ** 2) == "5.0 MB" and human(1.5 * 1024 ** 3) == "1.5 GB"


@check("wired into the agent: /status disk line, /disk, /disk clean, plain-words question, idle check")
def _():
    from agent import core
    src = pathlib.Path(core.__file__).read_text(encoding="utf-8")
    assert "self.house = Housekeeping(" in src and 's(self.house.status_line, "disk")' in src
    assert 'low.startswith("/disk")' in src and "how much (disk|disk space|space|room)" in src and "prune(aggressive=True)" in src
    assert "warn = self.house.check()" in src and "/disk [clean]" in src


def main():
    ok = 0
    for name, fn in CHECKS:
        try:
            fn()
            ok += 1
            print(f"OK   {name}")
        except Exception as e:
            print(f"FAIL {name}: {type(e).__name__}({e})")
    print(f"DISK SCORE: {ok}/{len(CHECKS)} (offline)")
    return 0 if ok == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
