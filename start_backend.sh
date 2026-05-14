#!/bin/bash
# Kill any existing uvicorn on port 8000 before starting
fuser -k 8000/tcp 2>/dev/null
sleep 1
cd /opt/asx-screener/backend
exec /opt/asx-screener/asx-venv/bin/uvicorn app.main:app \
    --host 0.0.0.0 --port 8000 --workers 1
