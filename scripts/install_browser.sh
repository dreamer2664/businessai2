#!/bin/sh
# Install the agent's own browser: Playwright + a headless Chromium (~300 MB). Debian/Ubuntu/WSL.
set -e
cd "$(dirname "$0")/.."
python3 -m pip --version >/dev/null 2>&1 || sudo apt install -y python3-pip
python3 -m pip install -q --user --break-system-packages playwright pypdf 2>/dev/null || python3 -m pip install -q --user playwright pypdf
python3 -m playwright install chromium
# system libraries chromium needs (asks for sudo once)
python3 -m playwright install-deps chromium 2>/dev/null || sudo python3 -m playwright install-deps chromium
python3 - <<'PY'
from agent.browser import Browser
with Browser() as b:
    print("browser OK:", b.open("https://example.com").split("\n")[1])
PY
echo "browser installed. Try on Telegram:  /summarize https://en.wikipedia.org/wiki/Dropshipping"
