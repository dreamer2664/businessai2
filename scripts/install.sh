#!/bin/sh
# One-shot install on a fresh Linux box (Debian/Ubuntu/WSL). Run as a normal user:
#   sh scripts/install.sh
# Then put your keys in .secrets/env (see .secrets.example) and run:  sh scripts/run.sh
set -e
cd "$(dirname "$0")/.."
command -v python3 >/dev/null || { echo "python3 missing: sudo apt install -y python3"; exit 1; }
mkdir -p .secrets state/logs release
[ -f .secrets/env ] || { cp .secrets.example .secrets/env; chmod 600 .secrets/env; echo "created .secrets/env - fill in your keys"; }
chmod 700 .secrets
python3 -m agent.selfcheck
echo
echo "Optional — the agent's own browser (needed for /research, /compare, /summarize; ~300 MB):"
echo "   sh scripts/install_browser.sh"
echo "Optional — the knowledge brain (needed for /ask and /exam; ~65 MB):   sh scripts/get_brain.sh"
echo "Optional — the thinking model (plain-language chat, written answers, exam; ~1 GB): sh scripts/get_model.sh"
echo "install OK. start with:  sh scripts/run.sh   (or install the service: sh scripts/service.sh)"
