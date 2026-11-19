#!/usr/bin/env bash
# Start Freehands in the background and report the PID.
set -u

cd "$(dirname "$0")/.." || exit 1

PIDFILE="bot/freehands.pid"
LOG="bot/freehands.log"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "already running (pid $(cat "$PIDFILE"))"
  exit 0
fi

mkdir -p bot
cd bot || exit 1
nohup python3 -m freehands >>"../$LOG" 2>&1 &
pid=$!
cd ..
echo "$pid" >"$PIDFILE"
sleep 2

if kill -0 "$pid" 2>/dev/null; then
  echo "started (pid $pid), logging to $LOG"
  tail -n 5 "$LOG"
else
  echo "failed to start; last lines:"
  tail -n 20 "$LOG"
  rm -f "$PIDFILE"
  exit 1
fi
