#!/bin/sh
# Install the Python libraries the agent needs at runtime but that no installer step covered on the PC
# (found by scripts/diag.sh on 2026-09-09: PIL, numpy missing → picture thumbnails in research docs, photo
# checks in seller checks and the eyes module silently degraded). Idempotent; safe to re-run.
cd "$(dirname "$0")/.." || exit 1
need=""
for m in PIL numpy zstandard pypdf; do
  python3 -c "import $m" 2>/dev/null || need="$need $m"
done
if [ -n "$need" ]; then
  pkgs="$(echo "$need" | sed 's/PIL/pillow/')"
  echo "installing:$pkgs"
  python3 -m pip install -q --user --break-system-packages $pkgs 2>/dev/null || python3 -m pip install -q --user $pkgs 2>/dev/null || \
    sudo apt-get install -y python3-pil python3-numpy python3-zstandard python3-pypdf
else
  echo "all libraries already present"
fi
for m in PIL numpy zstandard pypdf playwright requests; do
  python3 -c "import $m" 2>/dev/null && echo "ok      $m" || echo "MISSING $m"
done
