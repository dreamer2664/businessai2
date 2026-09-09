#!/bin/sh
# Business AI doctor: diagnose + repair the PC install, print a short report.
# Run from Windows PowerShell (one line, works even if the local repo is broken):
#   wsl bash -lc "curl -sL https://raw.githubusercontent.com/dreamer2664/businessai2/main/scripts/doctor.sh | bash"
# It NEVER prints secret values — only key names and value lengths.
DOCTOR_VERSION=5
set -u
echo "--- doctor v$DOCTOR_VERSION ---"
REPO_URL="https://github.com/dreamer2664/businessai2.git"

# 1. find the repo (or clone it fresh)
D="$HOME/businessai"
if [ ! -d "$D/.git" ]; then
  D="$(find "$HOME" -maxdepth 3 -name .git -type d 2>/dev/null | grep -i business | head -1)"
  D="$(dirname "$D" 2>/dev/null)"
fi
if [ -z "$D" ] || [ ! -d "$D/.git" ]; then
  echo "--- repo: NOT FOUND, cloning fresh to ~/businessai ---"
  git clone "$REPO_URL" "$HOME/businessai" || { echo "CLONE FAILED (no git? no network?)"; exit 1; }
  D="$HOME/businessai"
fi
cd "$D" || exit 1
echo "--- repo: $D (branch: $(git branch --show-current 2>&1)) ---"
git remote set-url origin "$REPO_URL" 2>&1
git config user.name "businessai" 2>/dev/null
git config user.email "businessai@users.noreply.github.com" 2>/dev/null
git config pull.rebase true 2>/dev/null
git fetch origin main 2>&1 | tail -2
echo "local-only commits (never pushed; kept and replayed on top of the latest code):"
git log --oneline origin/main..HEAD 2>&1 | head -5
git status --short 2>&1 | head -5
if git pull --rebase origin main 2>&1 | tail -3; then
  :
else
  echo "(rebase hit a conflict - aborted, your files are untouched; the bot keeps running on its current code)"
  git rebase --abort 2>/dev/null
fi
echo "HEAD: $(git log --oneline -1 2>&1)"

# 2. secrets: backup, point at businessai2, report key names + lengths only
echo "--- secrets (.secrets/env: names + lengths, never values) ---"
mkdir -p .secrets state
if [ ! -f .secrets/env ]; then
  cp .secrets.example .secrets/env 2>/dev/null || true
  echo "(no .secrets/env found - created from template, tokens must be filled in)"
else
  cp .secrets/env ".secrets/env.bak.$(date +%Y%m%d-%H%M%S)"
  echo "(backup of .secrets/env saved)"
fi
if grep -q "^GH_REPO=" .secrets/env 2>/dev/null; then
  sed -i 's/^GH_REPO=.*/GH_REPO=businessai2/' .secrets/env
else
  echo "GH_REPO=businessai2" >> .secrets/env
fi
if grep -q "^GH_OWNER=your-github-username" .secrets/env 2>/dev/null; then
  sed -i 's/^GH_OWNER=.*/GH_OWNER=dreamer2664/' .secrets/env
  echo "(GH_OWNER was still the template placeholder - set to dreamer2664)"
fi
echo "GH_OWNER/GH_REPO: $(grep '^GH_OWNER=' .secrets/env 2>/dev/null | cut -d= -f2) / $(grep '^GH_REPO=' .secrets/env 2>/dev/null | cut -d= -f2)"
awk -F= '/^[A-Za-z_][A-Za-z0-9_]*=/ {v=substr($0,index($0,"=")+1); gsub(/["\047]/,"",v); gsub(/^[ \t]+|[ \t]+$/,"",v); print $1": len="length(v)}' .secrets/env 2>/dev/null || echo "(unreadable .secrets/env)"
for k in TELEGRAM_BOT_TOKEN GITHUB_TOKEN; do
  grep -q "^$k=.." .secrets/env 2>/dev/null || echo "!! $k is EMPTY - the bot cannot run without it"
done
[ -f .secrets/google_client.json ] && echo "google_client.json: present" || echo "google_client.json: missing (needed later for Drive/Gmail)"

# 3. python sanity
echo "--- python ---"
python3 --version 2>&1
python3 -c "import agent.core; print('agent.core imports OK')" 2>&1 | tail -1

# 4. (re)start the bot
echo "--- service ---"
if systemctl --user list-units >/dev/null 2>&1; then
  echo "(systemd user manager present)"
  pkill -f "agent\.core" 2>/dev/null; sleep 1
  echo "(stray bot copies killed, if any: $(pgrep -c -f 'agent.core' 2>/dev/null || echo 0) left)"
  sh scripts/service.sh 2>&1 | tail -3
  echo "active: $(systemctl --user is-active businessai 2>&1)"
  echo "--- log (last 25 lines) ---"
  journalctl --user -u businessai -n 25 --no-pager 2>&1 | tail -25
else
  echo "(no systemd in this WSL - starting the bot directly in the background)"
  pkill -f "agent.core" 2>/dev/null; sleep 1
  setsid nohup python3 -m agent.core >> state/doctor-run.log 2>&1 < /dev/null &
  sleep 6
  echo "process: $(pgrep -af 'agent.core' | head -2 || echo NONE)"
  echo "--- log (last 25 lines) ---"
  tail -25 state/doctor-run.log 2>/dev/null || echo "(no log yet)"
fi
echo "--- processes (every bot copy) ---"
pgrep -af "agent.core" 2>/dev/null || echo "(no agent.core process found)"
echo "--- machine ---"
uptime 2>&1 | head -1
if systemctl --user list-units >/dev/null 2>&1; then
  echo "--- poll errors / crashes (last hour) ---"
  journalctl --user -u businessai --since "1 hour ago" --no-pager 2>&1 | grep -iE "poll_error|handler_error|traceback|401|409|conflict|unauthorized" | tail -8 || echo "(none)"
  echo "restarts (last hour): $(journalctl --user -u businessai --since '1 hour ago' --no-pager 2>&1 | grep -c 'Started businessai')"
fi
echo "--- google client file ---"
python3 -c "import json;d=json.load(open('.secrets/google_client.json'));i=d.get('installed',d.get('web',{}));print('valid JSON, type:',('installed' if 'installed' in d else ('web' if 'web' in d else '?')),'| id+secret:',bool(i.get('client_id')) and bool(i.get('client_secret')))" 2>&1
echo "--- REPORT END ---"
echo "Paste everything above back to the chat."
