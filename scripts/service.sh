#!/bin/sh
# Install the agent as a user service that starts at boot and restarts on crash (systemd, Linux).
set -e
cd "$(dirname "$0")/.."
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/businessai.service <<UNIT
[Unit]
Description=Business AI agent
After=network-online.target
[Service]
WorkingDirectory=$(pwd)
ExecStart=/usr/bin/env python3 -m agent.core
Environment=DISPLAY=${DISPLAY:-:0} WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-wayland-0} XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
Restart=always
RestartSec=5
RestartPreventExitStatus=42
[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable businessai
systemctl --user restart businessai
sleep 3
systemctl --user is-active businessai && echo "live screen: http://localhost:8765"
loginctl enable-linger "$USER" 2>/dev/null || true
echo "service running. status: systemctl --user status businessai   logs: journalctl --user -u businessai -f"
