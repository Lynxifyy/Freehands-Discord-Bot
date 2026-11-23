"""A door the phone can knock on when the supervisor is dead.

A request cannot reach a process that is not listening, so "start the
supervisor from the app" has no HTTP path on the main port: when the supervisor
is down, that port is closed and the app's call fails at the socket. Something
has to be listening somewhere else.

This listens on the second host (default 12001) and does exactly two things:
answer `/health`, and spawn `console_api.py` on the real port. It holds no
state, proxies nothing, and takes no arguments from the caller, so the worst a
stranger can do with it is start the supervisor that was meant to be running.

    python3 waker.py            # listens on FH_WAKER_PORT, default 12001
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SUPERVISOR = ROOT / "console_api.py"
LOG = ROOT / "bot" / "console.log"

WAKER_PORT = int(os.environ.get("FH_WAKER_PORT", "12001"))


def _published_port() -> int:
    """The port the supervisor last bound, so a wake restarts it where it was.

    A value outside the real port range is ignored. `0` in particular means
    "any port", and waking a supervisor onto it starts a process that nothing
    can connect to.
    """
    try:
        port = int((ROOT / "bot" / "console.port").read_text().strip())
        if 0 < port < 65536:
            return port
    except (OSError, ValueError):
        pass
    return int(os.environ.get("FH_CONSOLE_PORT", "12000"))


_SPAWN_LOCK = threading.Lock()
# A wake can hold the lock for ten seconds while it waits for the port to
# answer. This endpoint is public, so without a floor between attempts a
# handful of concurrent callers would pile up threads doing the same wait.
_SPAWN_COOLDOWN = 5.0
_last_attempt = 0.0


def target_up(timeout: float = 2.0) -> bool:
    try:
        port = _published_port()
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def wake() -> dict:
    """Start the supervisor if it is not already answering."""
    global _last_attempt
    with _SPAWN_LOCK:
        port = _published_port()
        if target_up():
            return {"ok": True, "already": True, "port": port}
        if not SUPERVISOR.exists():
            return {"ok": False, "error": "supervisor missing"}
        now = time.time()
        if now - _last_attempt < _SPAWN_COOLDOWN:
            return {"ok": False, "error": "already starting", "port": port}
        _last_attempt = now
        env = dict(os.environ)
        env["FH_CONSOLE_PORT"] = str(port)
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a") as out:
            proc = subprocess.Popen(
                [sys.executable, str(SUPERVISOR)],
                cwd=str(ROOT), stdout=out, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, start_new_session=True, env=env,
            )
        # Answer only once it is actually reachable, so the app can poll the
        # real port straight away instead of racing a supervisor that is still
        # importing and binding.
        for _ in range(40):
            if target_up():
                return {"ok": True, "started": True, "pid": proc.pid, "port": port}
            time.sleep(0.25)
        return {"ok": False, "error": "supervisor did not come up", "pid": proc.pid}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args) -> None:
        pass

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path == "/health":
            return self._send(200, {"ok": True, "role": "waker",
                                    "target": _published_port(), "target_up": target_up()})
        return self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path.split("?")[0] != "/wake":
            return self._send(404, {"error": "not found"})
        return self._send(200, wake())


def main() -> int:
    server = ThreadingHTTPServer(("0.0.0.0", WAKER_PORT), Handler)
    server.daemon_threads = True
    print(f"waker listening on 0.0.0.0:{WAKER_PORT} -> starts supervisor on {_published_port()}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
