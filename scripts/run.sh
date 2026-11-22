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
  echo "bot started (pid $pid), logging to $LOG"
  tail -n 5 "$LOG"
  # The supervisor is what the app talks to; without it a paired phone has
  # nothing to reach. It starts the bot itself if that is ever not running.
  SUPLOG="bot/console.log"
  if ! pgrep -f "console_api.py" >/dev/null 2>&1; then
    nohup python3 console_api.py >>"$SUPLOG" 2>&1 &
    echo "console API started (pid $!), logging to $SUPLOG"
  else
    echo "console API already running"
  fi
else
  echo "failed to start; last lines:"
  tail -n 20 "$LOG"
  rm -f "$PIDFILE"
  exit 1
fi
