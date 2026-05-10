#!/usr/bin/env bash
# Start Streamlit dashboard.
# Usage: ./start.sh [port]
# Default port: 8502

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

PORT="${1:-8502}"
LOG_DIR="$PROJECT_DIR/.run"
PID_FILE="$LOG_DIR/dashboard.pid"
LOG_FILE="$LOG_DIR/dashboard.log"

mkdir -p "$LOG_DIR"

# Check if already running
if [ -f "$PID_FILE" ]; then
  OLD_PID=$(cat "$PID_FILE")
  if kill -0 "$OLD_PID" 2>/dev/null; then
    echo "Dashboard sudah jalan (PID $OLD_PID, port $PORT)."
    echo "URL: http://localhost:$PORT"
    echo "Log: $LOG_FILE"
    echo "Stop dengan: ./stop.sh"
    exit 0
  else
    rm -f "$PID_FILE"
  fi
fi

# Verify port free
if lsof -ti:"$PORT" >/dev/null 2>&1; then
  echo "ERROR: port $PORT sudah dipakai proses lain."
  echo "Ganti port: ./start.sh 8503"
  echo "Atau kill: lsof -ti:$PORT | xargs kill"
  exit 1
fi

# Locate streamlit
STREAMLIT="$(command -v streamlit 2>/dev/null || true)"
if [ -z "$STREAMLIT" ]; then
  for candidate in \
      "$HOME/Library/Python/3.13/bin/streamlit" \
      "$HOME/Library/Python/3.12/bin/streamlit" \
      "$HOME/Library/Python/3.11/bin/streamlit" \
      "/usr/local/bin/streamlit" \
      "/opt/homebrew/bin/streamlit"; do
    if [ -x "$candidate" ]; then
      STREAMLIT="$candidate"
      break
    fi
  done
fi
if [ -z "$STREAMLIT" ]; then
  echo "ERROR: streamlit tidak ditemukan. Install: pip install -r requirements.txt"
  exit 1
fi

echo "Starting dashboard on port $PORT..."
nohup "$STREAMLIT" run app.py \
  --server.headless=true \
  --server.port="$PORT" \
  --browser.gatherUsageStats=false \
  > "$LOG_FILE" 2>&1 &

PID=$!
echo "$PID" > "$PID_FILE"

# Wait briefly and verify it's still running
sleep 2
if ! kill -0 "$PID" 2>/dev/null; then
  echo "ERROR: streamlit gagal start. Cek log:"
  tail -20 "$LOG_FILE"
  rm -f "$PID_FILE"
  exit 1
fi

echo ""
echo "  Dashboard running"
echo "  PID:  $PID"
echo "  URL:  http://localhost:$PORT"
echo "  Log:  $LOG_FILE"
echo "  Stop: ./stop.sh"
