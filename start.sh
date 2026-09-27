#!/usr/bin/env bash
# Start BiDiB2WLED. By default in the background; with --foreground in the
# foreground (for systemd, Docker or a terminal).
#
# Environment variables (optional):
#   BIDIB2WLED_CONFIG  path to config.yaml   (default: <project>/config.yaml if present)
#   BIDIB2WLED_HOST    web bind address      (default: program default 0.0.0.0)
#   BIDIB2WLED_PORT    web port              (default: program default 8080)
#   BIDIB2WLED_ARGS    extra arguments, e.g. "--simulate -v"
#   BIDIB2WLED_PIDFILE pid file              (default: <project>/bidib2wled.pid)
#   BIDIB2WLED_LOG     log file              (default: <project>/bidib2wled.log)
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDFILE="${BIDIB2WLED_PIDFILE:-$DIR/bidib2wled.pid}"
LOGFILE="${BIDIB2WLED_LOG:-$DIR/bidib2wled.log}"

FOREGROUND=0
if [ "${1:-}" = "--foreground" ] || [ "${1:-}" = "-f" ]; then
    FOREGROUND=1
    shift
fi

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "BiDiB2WLED is already running (PID $(cat "$PIDFILE"))."
    exit 0
fi
rm -f "$PIDFILE"

if [ -x "$DIR/.venv/bin/bidib2wled" ]; then
    CMD=("$DIR/.venv/bin/bidib2wled")
elif [ -x "$DIR/.venv/bin/python" ]; then
    CMD=("$DIR/.venv/bin/python" -m bidib2wled)
elif command -v bidib2wled >/dev/null 2>&1; then
    CMD=("$(command -v bidib2wled)")
else
    echo "bidib2wled not found. Create a virtual environment first:" >&2
    echo "  python3 -m venv .venv && .venv/bin/pip install -e \"$DIR\"" >&2
    exit 1
fi

CONFIG="${BIDIB2WLED_CONFIG:-}"
if [ -z "$CONFIG" ] && [ -f "$DIR/config.yaml" ]; then
    CONFIG="$DIR/config.yaml"
fi
[ -n "$CONFIG" ] && CMD+=(--config "$CONFIG")
[ -n "${BIDIB2WLED_HOST:-}" ] && CMD+=(--host "$BIDIB2WLED_HOST")
[ -n "${BIDIB2WLED_PORT:-}" ] && CMD+=(--port "$BIDIB2WLED_PORT")
# shellcheck disable=SC2206
[ -n "${BIDIB2WLED_ARGS:-}" ] && CMD+=(${BIDIB2WLED_ARGS})
CMD+=("$@")

export PYTHONUNBUFFERED=1

if [ "$FOREGROUND" = "1" ]; then
    exec "${CMD[@]}"
fi

cd "$DIR"
nohup "${CMD[@]}" >>"$LOGFILE" 2>&1 &
echo $! >"$PIDFILE"
sleep 1

if ! kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    rm -f "$PIDFILE"
    echo "Start failed. Last lines of $LOGFILE:" >&2
    tail -n 20 "$LOGFILE" >&2 || true
    exit 1
fi

echo "BiDiB2WLED started (PID $(cat "$PIDFILE")). Log: $LOGFILE"
echo "Web UI: http://127.0.0.1:${BIDIB2WLED_PORT:-8080}"
