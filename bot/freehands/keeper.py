"""Keep the supervisor alive from the bot side.

The supervisor (`console_api.py`) already watches the bot. Nothing watched the
supervisor. When it died the public port went dead, and no HTTP call could
revive it: a request cannot reach a process that is not listening. The phone
was left pressing a button that had nowhere to arrive.

This closes the loop. The bot is the only long-lived process that is *not*
started by the supervisor, so it is the one thing that can notice the
supervisor is gone and bring it back. Each side now keeps the other alive, and
a phone that pairs once keeps working through either process dying.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

from .log import log

ROOT = Path(__file__).resolve().parent.parent.parent
SUPERVISOR = ROOT / "console_api.py"
PORTFILE = ROOT / "bot" / "console.port"

# The supervisor answers this on the port the public host forwards to. A TCP
# connect would say "up" for a hung process, so ask for a real reply.
HEALTH_PATH = "/health"


def supervisor_port() -> int:
    """The port the supervisor is on, as it last reported it.

    Reading the published file beats reading the environment. The supervisor
    may have been started by a shell that set FH_CONSOLE_PORT=12000 while this
    bot was started without it; guessing from the environment would have the
    keeper watch 8790 and spawn a second supervisor on the wrong port.

    A file that does not hold a usable port is ignored. `0` means "any port",
    which is what a test run binds; treating it as real made the keeper spawn
    supervisor after supervisor onto a port nothing can connect to.
    """
    try:
        port = int(PORTFILE.read_text().strip())
        if 0 < port < 65536:
            return port
    except (OSError, ValueError):
        pass
    return int(os.environ.get("FH_CONSOLE_PORT", "8790"))


def supervisor_url() -> str:
    return f"http://127.0.0.1:{supervisor_port()}"


def supervisor_up(timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(supervisor_url() + HEALTH_PATH, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def spawn_supervisor() -> int | None:
    """Start the supervisor detached, returning its pid.

    `start_new_session` matters: the supervisor must outlive this bot, so a
    restart of the bot does not take its own safety net down with it.
    """
    if not SUPERVISOR.exists():
        log.warning("keeper: no supervisor at %s", SUPERVISOR)
        return None
    env = dict(os.environ)
    # Start it on the port it was on before. Falling back to the default here
    # would put it somewhere the public host does not forward to, which looks
    # exactly like still being down.
    env["FH_CONSOLE_PORT"] = str(supervisor_port())
    try:
        with open(ROOT / "bot" / "console.log", "a") as out:
            proc = subprocess.Popen(
                [sys.executable, str(SUPERVISOR)],
                cwd=str(ROOT), stdout=out, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, start_new_session=True, env=env,
            )
        log.info("keeper: supervisor restarted (pid %s)", proc.pid)
        return proc.pid
    except OSError as exc:
        log.error("keeper: could not start supervisor: %s", exc)
        return None


def watch(interval: float = 30.0, grace: float = 45.0,
          stop: threading.Event | None = None) -> None:
    """Revive the supervisor when it stops answering.

    The grace period stops a supervisor that is merely restarting from being
    stampeded with duplicates — two supervisors cannot both bind the port, so
    the loser would exit and log noise for nothing.

    Failures back off. A supervisor that cannot start (a port already taken by
    something that is not us, a broken import) would otherwise be respawned on
    every pass for as long as the bot lives, filling the log with doomed
    processes.
    """
    down_since = 0.0
    failures = 0
    while not (stop and stop.is_set()):
        time.sleep(interval)
        try:
            if supervisor_up():
                down_since = 0.0
                failures = 0
                continue
            now = time.time()
            if down_since == 0.0:
                down_since = now
                continue
            if now - down_since < grace:
                continue
            log.warning("keeper: supervisor is not answering; restarting it")
            spawn_supervisor()
            failures += 1
            down_since = 0.0
            if failures > 3:
                # Give up the fast loop; the next pass still retries, but the
                # log stops filling with one failure per interval.
                backoff = min(60.0 * (failures - 3), 900.0)
                log.warning("keeper: backing off %.0fs after %d failures", backoff, failures)
                time.sleep(backoff)
        except Exception as exc:  # a keeper must never take the bot down
            log.error("keeper error: %r", exc)


def start(**kwargs) -> threading.Thread:
    thread = threading.Thread(target=watch, name="keeper", daemon=True, kwargs=kwargs)
    thread.start()
    return thread
