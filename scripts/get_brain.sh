#!/bin/sh
# Download the brain (engine + models + knowledge packs) from the GitHub Release into release/.
#   sh scripts/get_brain.sh            # latest release of dreamer2664/businessai2
set -e
cd "$(dirname "$0")/.."
REPO="${BAI_REPO:-dreamer2664/businessai2}"
mkdir -p release/packs
for f in kdr-brain-lite brain.kdr; do
  [ -s "release/$f" ] || { echo "fetching $f"; curl -fL --progress-bar -o "release/$f" "https://github.com/$REPO/releases/download/latest/$f"; }
done
for p in ${BAI_PACKS:-business.kdw operations.kdw dropship.kdw marketplaces.kdw}; do
  echo "fetching pack $p"; curl -fL --progress-bar -o "release/packs/$p" "https://github.com/$REPO/releases/download/latest/$p"
done
chmod +x release/kdr-brain-lite
echo "brain ready:"; ls -la release release/packs
echo "test:"; ./release/kdr-brain-lite release/brain.kdr --wiki release/packs/business.kdw wiki "What is dropshipping?" 2>/dev/null | head -c 300; echo
# python packages the pack builder needs (learned.kdw is rebuilt on this machine as the agent learns)
python3 -c "import numpy, zstandard" 2>/dev/null || python3 -m pip install -q --user --break-system-packages numpy zstandard 2>/dev/null || python3 -m pip install -q --user numpy zstandard || echo "note: could not install numpy/zstandard — run: pip install numpy zstandard"
