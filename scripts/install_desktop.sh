#!/bin/sh
# Eyes & desktop tools (all free): OCR + a virtual screen + mouse/keyboard control. Re-runnable.
#   sh scripts/install_desktop.sh
# Debian/Ubuntu (incl. WSL). On other systems install: tesseract-ocr, xvfb, xdotool, scrot, x11-utils.
set -e
cd "$(dirname "$0")/.."
if command -v apt-get >/dev/null 2>&1; then
  echo "installing tesseract-ocr xvfb xdotool scrot x11-utils (asks for your password once) ..."
  sudo apt-get install -y -qq tesseract-ocr xvfb xdotool scrot x11-utils
fi
python3 -c "import PIL" 2>/dev/null || python3 -m pip install -q --user --break-system-packages pillow 2>/dev/null || python3 -m pip install -q --user pillow
python3 -c "import numpy" 2>/dev/null || python3 -m pip install -q --user --break-system-packages numpy 2>/dev/null || python3 -m pip install -q --user numpy
echo "tools:"; for t in tesseract Xvfb xdotool scrot xdpyinfo; do printf "  %-10s %s\n" "$t" "$(command -v $t || echo MISSING)"; done
echo "vision model: send /eyes install to the bot (310 MB, once) — or run: python3 -c 'from agent.eyes import Eyes; print(Eyes().install())'"
