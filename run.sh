#!/usr/bin/env bash
# Arranque local del SCADA de flotación (PI + Feedforward) — FastAPI + WebSocket
set -euo pipefail
cd "$(dirname "$0")"
python3 -m pip install -q -r requirements.txt
: "${SCADA_HOST:=127.0.0.1}"
: "${SCADA_PORT:=8000}"
exec python3 -m uvicorn backend.main:app --host "$SCADA_HOST" --port "$SCADA_PORT"
