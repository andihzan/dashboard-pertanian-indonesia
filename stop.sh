#!/usr/bin/env bash
# Stop Streamlit dashboard yang di-start oleh start.sh

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$PROJECT_DIR/.run"
PID_FILE="$LOG_DIR/dashboard.pid"

if [ ! -f "$PID_FILE" ]; then
  echo "Tidak ada PID file ($PID_FILE)."
  # Fallback: cari proses streamlit dari project ini
  PIDS=$(pgrep -f "streamlit.*run.*$PROJECT_DIR/app.py" 2>/dev/null || true)
  if [ -z "$PIDS" ]; then
    echo "Dashboard tidak sedang jalan."
    exit 0
  fi
  echo "Menemukan proses streamlit tanpa PID file: $PIDS"
  echo "Killing..."
  echo "$PIDS" | xargs kill 2>/dev/null || true
  sleep 1
  echo "Stopped."
  exit 0
fi

PID=$(cat "$PID_FILE")
if kill -0 "$PID" 2>/dev/null; then
  echo "Stopping dashboard (PID $PID)..."
  kill "$PID"
  # Wait for graceful shutdown
  for i in 1 2 3 4 5; do
    if ! kill -0 "$PID" 2>/dev/null; then
      break
    fi
    sleep 1
  done
  # Force kill if still running
  if kill -0 "$PID" 2>/dev/null; then
    echo "Force killing..."
    kill -9 "$PID" 2>/dev/null || true
  fi
  echo "Stopped."
else
  echo "PID $PID tidak aktif (mungkin sudah mati)."
fi
rm -f "$PID_FILE"
