#!/usr/bin/env bash
# Start the WormGPT backend (idempotent: restarts if already running).
set -u
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
./.venv/bin/pip install -q -r requirements.txt
PID=$(ps aux | grep "[u]vicorn main:app" | awk '{print $2}')
[ -n "$PID" ] && kill $PID 2>/dev/null && sleep 2
cd app
nohup ../.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port "${PORT:-12000}" > ../server.log 2>&1 &
sleep 6
curl -s "http://127.0.0.1:${PORT:-12000}/api/health"; echo
