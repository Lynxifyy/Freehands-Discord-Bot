#!/usr/bin/env bash
# Start Freehands in the background and report the PID.
set -u

cd "$(dirname "$0")/.." || exit 1

PIDFILE="bot/freehands.pid"
LOG="bot/freehands.log"

# True only when the pidfile names a live Freehands process.
#
# `kill -0` is not enough: it succeeds for a zombie, whose pid the kernel keeps
# until the parent reaps it, and for an unrelated process that inherited the
# number. Either way the script would refuse to start the bot, or stop the
# wrong thing, and say "already running" while nothing was serving.
bot_alive() {
  local pid
  pid=$(cat "$PIDFILE" 2>/dev/null) || return 1
  [ -n "$pid" ] || return 1
  # A zombie has no cmdline; a live Freehands process has "freehands" in it.
  tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null | grep -q freehands
}

if [ -f "$PIDFILE" ] && bot_alive; then
  echo "already running (pid $(cat "$PIDFILE"))"
  exit 0
fi
rm -f "$PIDFILE"

mkdir -p bot
cd bot || exit 1
# The keeper inside the bot reads this file to find the supervisor. Write it
# before starting anything so a bot started by hand still watches the right
# port instead of the default.
printf '%s' "${FH_CONSOLE_PORT:-12000}" >console.port
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
    FH_CONSOLE_PORT="${FH_CONSOLE_PORT:-12000}" nohup python3 console_api.py >>"$SUPLOG" 2>&1 &
    echo "console API started (pid $!), logging to $SUPLOG"
  else
    echo "console API already running"
  fi
  # The wake door. The supervisor's port is closed whenever the supervisor is
  # dead, so the app needs somewhere else to knock to start it again.
  WAKELOG="bot/waker.log"
  if ! pgrep -f "waker.py" >/dev/null 2>&1; then
    FH_CONSOLE_PORT="${FH_CONSOLE_PORT:-12000}" nohup python3 waker.py >>"$WAKELOG" 2>&1 &
    echo "waker started (pid $!), logging to $WAKELOG"
  else
    echo "waker already running"
  fi
else
  echo "failed to start; last lines:"
  tail -n 20 "$LOG"
  rm -f "$PIDFILE"
  exit 1
fi
