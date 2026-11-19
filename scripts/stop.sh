#!/usr/bin/env bash
# Stop the background Freehands process.
set -u

cd "$(dirname "$0")/.." || exit 1

PIDFILE="bot/freehands.pid"

if [ ! -f "$PIDFILE" ]; then
  echo "not running (no pidfile)"
  exit 0
fi

pid=$(cat "$PIDFILE")
if kill -0 "$pid" 2>/dev/null; then
  kill "$pid"
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.5
  done
  kill -0 "$pid" 2>/dev/null && kill -9 "$pid"
  echo "stopped (pid $pid)"
else
  echo "pid $pid was not running"
fi
rm -f "$PIDFILE"
