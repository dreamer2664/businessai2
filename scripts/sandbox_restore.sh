#!/bin/sh
# Re-fetch everything the sandbox loses on a reset (git-ignored downloads, pip packages, browser). Idempotent.
cd "$(dirname "$0")/.." || exit 1
mkdir -p release/llm release/packs
REL=https://github.com/dreamer2664/businessai2/releases/download/latest
for a in operations.kdw business.kdw; do [ -s release/packs/$a ] || curl -sL -o release/packs/$a "$REL/$a"; done
[ -s release/brain.kdr ] || curl -sL -o release/brain.kdr "$REL/brain.kdr"
[ -x release/kdr-brain-lite ] || { curl -sL -o release/kdr-brain-lite "$REL/kdr-brain-lite" && chmod +x release/kdr-brain-lite; }
[ -x release/llm/llama-server ] || { curl -sL -o release/llm/llama-server "$REL/llama-server-static" && chmod +x release/llm/llama-server; }
[ -s release/llm/model.gguf ] || { curl -sL -o release/llm/model.gguf.part "https://huggingface.co/bartowski/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/Qwen2.5-1.5B-Instruct-Q4_K_M.gguf" \
    && mv release/llm/model.gguf.part release/llm/model.gguf && echo Qwen2.5-1.5B-Instruct-Q4_K_M.gguf > release/llm/model.name; }
python3 -c "import playwright, numpy, zstandard, PIL, aiosmtpd" 2>/dev/null || pip install -q numpy zstandard playwright pillow aiosmtpd 2>&1 | grep -v notice
[ -d "$HOME/.cache/ms-playwright/chromium_headless_shell-1234" ] || python3 -m playwright install chromium 2>&1 | tail -1
ldconfig -p 2>/dev/null | grep -q libnspr4 || sudo python3 -m playwright install-deps chromium >/dev/null 2>&1
[ -f /swapfile ] || { sudo fallocate -l 3G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile >/dev/null && sudo swapon /swapfile; }
command -v tesseract >/dev/null 2>&1 || sudo apt-get install -y -qq tesseract-ocr >/dev/null 2>&1
[ -s release/eyes/model.gguf ] || python3 -c "from agent.eyes import Eyes; print(Eyes().install())" 2>/dev/null | tail -1
chmod +x scripts/*.sh
ls -la release/llm/model.gguf release/packs | grep -v "^total\|^d"
echo "RESTORE DONE"
