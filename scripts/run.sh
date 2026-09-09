#!/bin/sh
# Run the agent in the foreground (Ctrl-C stops it). Logs: state/logs/YYYY-MM-DD.jsonl
cd "$(dirname "$0")/.."
exec python3 -m agent.core "$@"
