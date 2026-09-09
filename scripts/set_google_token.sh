#!/bin/sh
# Replace .secrets/google_token.json with a token handed over as base64 (no quotes → safe through PowerShell).
#   sh scripts/set_google_token.sh <base64>
cd "$(dirname "$0")/.." || exit 1
[ -n "$1" ] || { echo "usage: sh scripts/set_google_token.sh <base64>"; exit 1; }
mkdir -p .secrets
[ -f .secrets/google_token.json ] && cp .secrets/google_token.json ".secrets/google_token.json.bak.$(date +%Y%m%d-%H%M%S)"
echo "$1" | base64 -d > .secrets/google_token.json.new && python3 -c "import json;json.load(open('.secrets/google_token.json.new'))" \
  && mv .secrets/google_token.json.new .secrets/google_token.json && chmod 600 .secrets/google_token.json \
  && cp .secrets/google_token.json "$HOME/.bai_google_token.json" && echo "token updated" || { rm -f .secrets/google_token.json.new; echo "BAD TOKEN — nothing changed"; exit 1; }
python3 - <<'PY' 2>/dev/null | grep -v '^{"t"'
import sys; sys.path.insert(0, ".")
from agent.google import Google
g = Google(); print("google connected:", g.connected(), "| account:", g.account(), "| scopes:", " ".join(x.rsplit("/", 1)[-1] for x in (g.token.get("scope") or "").split()))
PY
