#!/bin/sh
# Full health report of a Business AI install (read-only). Run: sh scripts/diag.sh
cd "$(dirname "$0")/.." || exit 1
echo "=== when / where"; date; hostname; echo "user: $(id -un)"; echo "uptime: $(cut -d' ' -f1 /proc/uptime) s"
echo "=== service"
systemctl --user is-active businessai 2>&1
systemctl --user is-enabled businessai 2>&1
systemctl --user show businessai -p NRestarts,ActiveEnterTimestamp,MemoryCurrent,MainPID 2>&1
loginctl show-user "$(id -un)" -p Linger 2>&1
echo "=== code"
git log -1 --oneline 2>&1
git status --short 2>&1 | head -5
echo "=== resources"
free -m | head -2
df -h ~ | tail -1
du -sh release state ~/.cache 2>/dev/null
echo "=== model + browser + python libs"
ls -la release/llm/ 2>/dev/null || echo "no release/llm"
ls ~/.cache/ms-playwright 2>/dev/null || echo "no playwright browsers"
python3 - <<'EOF'
import importlib
for m in ("playwright", "requests", "PIL", "google.oauth2", "googleapiclient", "numpy"):
    try:
        importlib.import_module(m); print("lib ok :", m)
    except Exception as e:
        print("lib MISSING:", m, "-", str(e)[:60])
EOF
echo "=== secrets (names + sizes only)"
ls -la .secrets/ 2>/dev/null | grep -v bak
echo "=== selfcheck"
python3 -m agent.selfcheck 2>&1 | grep -v '^{"t"'
echo "=== google + fallback state"
python3 - <<'EOF' 2>&1 | grep -v '^{"t"'
import sys, json, time
sys.path.insert(0, ".")
from agent.google import Google
g = Google(); print("google connected:", g.connected(), "| account:", g.account() or "?")
print("token scopes:", " ".join(x.rsplit("/", 1)[-1] for x in (g.token.get("scope") or "").split()) or "(none recorded)", "| token age (days):", round((time.time() - g.token.get("t", 0)) / 86400, 1) if g.token.get("t") else "?")
try:
    print("drive folder:", g.folder_link())
except Exception as e:
    print("drive err:", str(e)[:80])
try:
    d = json.load(open("state/fallback.json"))
    print("fallback allowed:", d.get("allowed"), "| daily:", d.get("daily"), "| last poll:", int(time.time() - d.get("last_poll", 0)), "s ago | answered:", d.get("answered"))
except Exception as e:
    print("fallback state:", str(e)[:80])
try:
    a = json.load(open("state/alive.json")); print("heartbeat:", a.get("t"), "pid", a.get("pid"), "up", a.get("up_s"), "s")
except Exception as e:
    print("heartbeat: none", str(e)[:60])
EOF
echo "=== log: errors / restarts / watchdog today"
journalctl --user -u businessai --since today --no-pager 2>/dev/null | grep -i 'error\|failed\|watchdog\|traceback\|Started\|Stopped' | tail -15 | cut -c1-220
echo "=== log: last 12 lines (no chat)"
journalctl --user -u businessai --since today --no-pager 2>/dev/null | grep -v '"kind": "in"\|"kind": "out"\|"kind": "talk"' | tail -12 | cut -c1-220
echo "=== DIAG-DONE"
