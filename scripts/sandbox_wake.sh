#!/bin/sh
# Repair sandbox state after a snapshot restore (run first every session).
# Restores LOSE: .git/config (the remote!), fresh branch pointers drift, pip packages,
# Chromium, and release/llm (128MB cap + name exclusions). The brain (65MB) survives.
cd "$(dirname "$0")/.." || exit 1
git remote | grep -q origin || git remote add origin https://github.com/dreamer2664/businessai2.git
git config credential.helper store 2>/dev/null || true
git config user.name businessai 2>/dev/null || true
git config user.email businessai@users.noreply.github.com 2>/dev/null || true
[ -s ~/.git-credentials ] || echo "!! no ~/.git-credentials — pushes need the token (ask the owner)"
git fetch origin 2>&1 | tail -2
echo "main: $(git log --oneline origin/main -1 2>&1)"
echo "you are on: $(git branch --show-current 2>&1) @ $(git log --oneline -1 2>&1)"
git status --short | head -10
echo "--- deps ---"
python3 -c "import playwright" 2>/dev/null && echo "playwright pip OK" || echo "playwright pip MISSING (pip install --user playwright)"
[ -d "$HOME/.cache/ms-playwright" ] && echo "chromium OK" || echo "chromium MISSING (python3 -m playwright install chromium)"
[ -s release/llm/model.gguf ] && echo "model OK" || echo "model MISSING (sh scripts/get_model.sh — 1GB, only when needed)"
[ -s release/brain.kdr ] && echo "brain OK" || echo "brain MISSING (sh scripts/get_brain.sh)"
chmod +x scripts/*.sh 2>/dev/null
echo "WAKE DONE — review git status above before resetting anything"
