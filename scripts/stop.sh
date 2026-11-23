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
# Only a real Freehands process may be signalled. `kill -0` also passes for a
# zombie and for whatever process inherited a recycled pid, so a bare liveness
# check could stop something unrelated.
if tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null | grep -q freehands; then
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

# The supervisor and waker outlive the bot by design — that is what lets them
# restart it. A full stop has to take them too, or the keeper brings the bot
# straight back up and the stop looks ignored.
for name in console_api.py waker.py; do
  for p in $(pgrep -f "$name"); do
    kill "$p" 2>/dev/null && echo "stopped $name (pid $p)"
  done
done
