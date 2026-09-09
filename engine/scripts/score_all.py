"""The full regression battery (marathon item 10): run every score_*.py suite.

Usage:
  python3 engine/scripts/score_all.py [--fast] [--only NAME] [--compare] [--with-practice]

--fast skips the browser/live/model suites (quick signal, ~3 min).
--compare diffs each suite's fraction against state/scores_last.json and flags drops.
--with-practice also runs practice_day.py (slow, ~15 min).

Results: PASS (full marks) · PARTIAL (ran, x/y) · SKIP (env lacks playwright/model/...)
· FAIL (crashed) · TIMEOUT. Exit 0 unless a suite FAILs/TIMEOUTs or --compare finds a drop.
Self-test: python3 engine/scripts/score_all.py --selftest
"""
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS = os.path.join(ROOT, "engine", "scripts")
LAST_FILE = os.path.join(ROOT, "state", "scores_last.json")

SKIP_MARKERS = ["No module named 'playwright'", "aiosmtpd",
                "thinking model not installed", "kdr-brain-lite",
                "vision model not installed"]

# suite -> (extra args, timeout seconds, needs browser/live/model?)
CONFIG = {
    "score_accounts": ([], 300, True), "score_brief": ([], 120, False),
    "score_browse": ([], 600, True), "score_channels": ([], 180, False),
    "score_docs": ([], 300, True), "score_docs_native": ([], 180, False),
    "score_eyes": ([], 300, True), "score_eyes_listing": ([], 300, False),
    "score_fallback": ([], 120, False), "score_inbox": ([], 120, False),
    "score_live": ([], 600, True), "score_mind": ([], 180, False),
    "score_operator": ([], 600, True),
    "score_pack": (["tests/business.txt", "release/packs/business.kdw"], 300, False),
    "score_phone": ([], 240, False),
    "score_queue": ([], 120, False), "score_rehearsal": ([], 300, True),
    "score_research": ([], 120, False),
    "score_youtube": ([], 120, False),
    "score_dropship": ([], 120, False), "score_disk": ([], 120, False),
    "score_think": ([], 120, False),
    "score_gmail": ([], 120, False),
    "score_markets": ([], 180, False),
    "score_progress": ([], 120, False), "score_floor": ([], 180, False), "score_mailbox": ([], 120, False),
    "score_sellers": ([], 300, True), "score_shopfacts": ([], 180, True),
    "score_sites": ([], 600, True), "score_stop": ([], 120, False),
    "score_store": ([], 180, False), "score_study": ([], 120, False),
    "score_talk": ([], 420, False), "score_walls": ([], 300, True),
    "score_warmup": ([], 300, "model"),
    "practice_day": ([], 900, "slow"), "practice_week": ([], 900, "slow"),
}

FRAC = re.compile(r"(\d+)\s*/\s*(\d+)")


def classify(name, code, output):
    skip = next((m for m in SKIP_MARKERS if m in output), None)
    fracs = FRAC.findall(output)
    frac = f"{fracs[-1][0]}/{fracs[-1][1]}" if fracs else None
    if code != 0:
        if skip and (not frac or frac.split("/")[0] == "0"):
            return ("SKIP", frac, skip)
        if frac and skip:
            return ("PARTIAL", frac, skip)
        return ("FAIL", frac, None)
    if skip and (not frac or frac.split("/")[0] == "0"):
        return ("SKIP", frac, skip)
    if frac:
        x, y = frac.split("/")
        return ("PASS", frac, None) if x == y else ("PARTIAL", frac, None)
    return ("PASS", None, None)


def run_suite(name, args, timeout):
    cmd = [sys.executable, os.path.join(SCRIPTS, name + ".py")] + args
    t0 = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=ROOT)
        out = (p.stdout or "") + (p.stderr or "")
        res, frac, why = classify(name, p.returncode, out)
        tail = "\n".join([ln for ln in out.splitlines() if ln.strip()][-2:])
        return {"result": res, "frac": frac, "why": why, "secs": int(time.time() - t0), "tail": tail[:300]}
    except subprocess.TimeoutExpired:
        return {"result": "TIMEOUT", "frac": None, "why": f">{timeout}s", "secs": timeout, "tail": ""}


def selftest():
    import tempfile
    d = tempfile.mkdtemp(prefix="battery_")
    fix = {"ok": ("print('SCORE 1/1')", 0), "part": ("print('SCORE 1/2')", 0),
           "fail": ("raise SystemExit(1)", 1),
           "skip": ("raise ModuleNotFoundError(\"No module named 'playwright'\")", 1),
           "partskip": ("print('SCORE 1/2'); raise ModuleNotFoundError(\"No module named 'playwright'\")", 1)}
    want = {"ok": "PASS", "part": "PARTIAL", "fail": "FAIL", "skip": "SKIP", "partskip": "PARTIAL"}
    n = 0
    for name, (code, _) in fix.items():
        fp = os.path.join(d, name + ".py")
        open(fp, "w").write(code)
        p = subprocess.run([sys.executable, fp], capture_output=True, text=True)
        got = classify(name, p.returncode, (p.stdout or "") + (p.stderr or ""))[0]
        assert got == want[name], f"{name}: got {got}, want {want[name]}"
        n += 1
    print(f"BATTERY SELFTEST: {n}/{len(fix)} classifications correct")
    return 0


def main(argv):
    if "--selftest" in argv:
        return selftest()
    fast = "--fast" in argv
    compare = "--compare" in argv
    with_practice = "--with-practice" in argv
    only = [a.split("=", 1)[1] for a in argv if a.startswith("--only=")]
    names = [n for n in CONFIG if not only or any(o in n for o in only)]
    if fast:
        names = [n for n in names if CONFIG[n][2] is False]
    if not with_practice:
        names = [n for n in names if CONFIG[n][2] != "slow"]
    prev = {}
    if os.path.exists(LAST_FILE):
        try:
            prev = json.load(open(LAST_FILE))
        except Exception:
            pass
    results, drops = {}, []
    for n in names:
        args, timeout, _ = CONFIG[n]
        r = run_suite(n, args, timeout)
        results[n] = r
        flag = ""
        if compare and n in prev and r["frac"] and prev[n].get("frac"):
            try:
                ox, oy = prev[n]["frac"].split("/")
                nx, ny = r["frac"].split("/")
                if int(nx) * int(oy) < int(ox) * int(ny):
                    drops.append(n)
                    flag = f"  <-- DROP (was {prev[n]['frac']})"
            except Exception:
                pass
        extra = f" {r['frac']}" if r["frac"] else ""
        why = f" ({r['why']})" if r.get("why") else ""
        print(f"{r['result']:7s} {n:20s}{extra:>10s} {r['secs']:>4d}s{why}{flag}")
    try:
        os.makedirs(os.path.dirname(LAST_FILE), exist_ok=True)
        slim = {n: {"result": r["result"], "frac": r["frac"]} for n, r in results.items()}
        json.dump({**prev, **slim}, open(LAST_FILE, "w"), indent=1)
    except Exception:
        pass
    counts = {}
    for r in results.values():
        counts[r["result"]] = counts.get(r["result"], 0) + 1
    print(f"BATTERY: {len(results)} suites — " + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())))
    if drops:
        print("REGRESSIONS: " + ", ".join(drops))
    bad = counts.get("FAIL", 0) + counts.get("TIMEOUT", 0)
    return 1 if bad or drops else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
