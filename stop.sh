#!/usr/bin/env bash
# Stop a BiDiB2WLED started with start.sh.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDFILE="${BIDIB2WLED_PIDFILE:-$DIR/bidib2wled.pid}"

if [ ! -f "$PIDFILE" ]; then
    echo "No pid file ($PIDFILE) – BiDiB2WLED does not seem to be running."
    exit 0
fi

PID="$(cat "$PIDFILE")"
if ! kill -0 "$PID" 2>/dev/null; then
    echo "Process $PID no longer exists, removing pid file."
    rm -f "$PIDFILE"
    exit 0
fi

kill "$PID"
for _ in $(seq 1 30); do
    if ! kill -0 "$PID" 2>/dev/null; then
        rm -f "$PIDFILE"
        echo "BiDiB2WLED stopped (PID $PID)."
        exit 0
    fi
    sleep 0.5
done

echo "Process $PID does not react, sending SIGKILL." >&2
kill -9 "$PID" 2>/dev/null || true
rm -f "$PIDFILE"
echo "BiDiB2WLED killed (PID $PID)."
