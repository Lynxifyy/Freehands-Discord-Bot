"""Public control API for the Freehands console app.

This is the only process that listens on a public port. It owns the bot's
lifecycle (start, stop, restart) and forwards reads and setting changes to the
bot's loopback API, so the process holding the Discord token is never directly
reachable from the network.

Auth is a bearer token. Two kinds are accepted:

* a **paired device token** from `/api/pair`, which is how the app gets access
  without anyone typing a secret, and
* `FH_CONSOLE_TOKEN`, kept for scripts and for recovering a lost pairing.

Pairing itself cannot require a token, or nobody could ever get one. It is
instead gated by a six-character code that only appears inside Discord, plus a
strict attempt limit so the code space cannot be walked.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REPO = "Lynxifyy/Freehands-Discord-Bot"
BOT_DIR = ROOT / "bot"
PIDFILE = BOT_DIR / "freehands.pid"
STATE = BOT_DIR / "state.json"
BOT_API = "http://127.0.0.1:8791"
DEFAULT_PORT = 8790


_VERSION_CACHE: dict[str, Any] = {"at": 0.0, "payload": None}
VERSION_TTL = 3600.0   # GitHub's unauthenticated limit is 60 requests/hour


def _latest_release() -> dict[str, Any]:
    """Ask GitHub for the newest release, cached for an hour.

    Unauthenticated on purpose: the app has no token before pairing, and a
    version check must work even then. The result is cached because GitHub
    allows only 60 anonymous calls an hour per address.
    """
    now = time.time()
    if _VERSION_CACHE["payload"] and now - _VERSION_CACHE["at"] < VERSION_TTL:
        return _VERSION_CACHE["payload"]

    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "freehands-console"},
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.loads(r.read() or b"{}")
    except (urllib.error.URLError, OSError, ValueError):
        # A failed lookup must not look like "up to date", but it also must not
        # break the app: report unknown and let the client decide to stay quiet.
        return {"known": False}

    tag = str(data.get("tag_name") or "").lstrip("v")
    asset = next(
        (a for a in data.get("assets") or [] if str(a.get("name", "")).endswith(".apk")),
        None,
    )
    payload = {
        "known": bool(tag),
        "version": tag,
        "url": (asset or {}).get("browser_download_url") or data.get("html_url") or "",
        "notes": (data.get("body") or "")[:600],
        "published": data.get("published_at") or "",
    }
    _VERSION_CACHE.update({"at": now, "payload": payload})
    return payload


def _token() -> str:
    return os.environ.get("FH_CONSOLE_TOKEN", "").strip()


# Pairing attempts are counted per client address. A six-character code from a
# 31-letter alphabet is ~887 million possibilities, so the only real risk is a
# script hammering the endpoint; a small budget makes that hopeless while
# leaving room for a person mistyping.
_PAIR_ATTEMPTS: dict[str, list[float]] = {}
_PAIR_WINDOW = 60.0
_PAIR_LIMIT = 10


def _pair_allowed(addr: str) -> bool:
    now = time.time()
    recent = [t for t in _PAIR_ATTEMPTS.get(addr, []) if now - t < _PAIR_WINDOW]
    if len(recent) >= _PAIR_LIMIT:
        _PAIR_ATTEMPTS[addr] = recent
        return False
    recent.append(now)
    _PAIR_ATTEMPTS[addr] = recent
    return True


def _is_bot(pid: int) -> bool:
    """True only when `pid` is really this bot.

    A bare `kill(pid, 0)` is not enough: if the bot died the PID can be reused
    by an unrelated process, and stopping would then kill the wrong thing.
    """
    try:
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
    except OSError:
        return False
    return b"freehands" in cmdline


def _read_pid() -> int | None:
    try:
        pid = int(PIDFILE.read_text().strip())
    except (OSError, ValueError):
        return None
    if not _is_bot(pid):
        # Stale or recycled: drop the file so the next start is clean.
        try:
            PIDFILE.unlink()
        except OSError:
            pass
        return None
    return pid


def _alive() -> bool:
    return _read_pid() is not None


def _start() -> dict[str, Any]:
    _reap()
    if _alive():
        return {"ok": True, "already": True, "pid": _read_pid()}
    BOT_DIR.mkdir(parents=True, exist_ok=True)
    log = (BOT_DIR / "freehands.log").open("a")
    proc = subprocess.Popen(
        [sys.executable, "-m", "freehands"],
        cwd=str(BOT_DIR), stdout=log, stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL, start_new_session=True,
    )
    PIDFILE.write_text(str(proc.pid))
    for _ in range(40):
        if _bot_api_up():
            break
        time.sleep(0.5)
    return {"ok": True, "pid": proc.pid}


def _stop() -> dict[str, Any]:
    pid = _read_pid()
    if pid is None:
        return {"ok": True, "already": True}
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    for _ in range(40):
        if _read_pid() is None:
            break
        time.sleep(0.25)
    try:
        PIDFILE.unlink()
    except OSError:
        pass
    _reap()
    return {"ok": True, "stopped": pid}


def _reap() -> None:
    """Collect exited children.

    The supervisor is the parent of every bot it starts. Without a wait the
    dead child stays a zombie, which leaks a process slot on a long-lived host
    and leaves an empty /proc entry that makes `_is_bot` read as "not running".
    """
    try:
        while True:
            pid, _ = os.waitpid(-1, os.WNOHANG)
            if pid == 0:
                break
    except ChildProcessError:
        pass
    except OSError:
        pass


def _restart() -> dict[str, Any]:
    _stop()
    time.sleep(1.0)
    return _start()


def _bot_api_up() -> bool:
    try:
        with urllib.request.urlopen(f"{BOT_API}/api/status", timeout=2) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


def _proxy(path: str, method: str = "GET", body: dict | None = None) -> tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{BOT_API}{path}", data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read() or b"{}")
        except ValueError:
            return exc.code, {"error": "upstream error"}
    except (urllib.error.URLError, OSError):
        return 503, {"error": "bot is not running", "running": False}


# Verifying a device token costs a loopback call, and the app polls every few
# seconds, so a short cache keeps that off the hot path. Revocation still takes
# effect within the TTL, and `+revoke` is not a security race against 30s.
_DEVICE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_DEVICE_TTL = 30.0


def _device_cached(token: str) -> dict[str, Any] | None:
    hit = _DEVICE_CACHE.get(token)
    now = time.time()
    if hit and now - hit[0] < _DEVICE_TTL:
        return hit[1]
    device = _DEVICE_LOOKUP(token)
    # A miss is cached too, otherwise anyone sending garbage tokens makes the
    # supervisor issue a loopback request per attempt.
    _DEVICE_CACHE[token] = (now, device)
    if len(_DEVICE_CACHE) > 512:
        _DEVICE_CACHE.clear()
    return device


def _state_devices() -> list[dict[str, Any]]:
    """Read the device rows the bot persists, without needing the bot alive."""
    try:
        payload = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = payload.get("devices")
    return rows if isinstance(rows, list) else []


def _device_for(token: str) -> dict[str, Any] | None:
    """Check a paired-device token against the persisted device registry.

    This deliberately reads `state.json` instead of asking the bot over
    loopback. Auth must not depend on the bot process, because the supervisor's
    job includes *starting* it: when the bot was down, every token failed and
    the app could not press Start. The file is the same source of truth, only
    hashes are stored, and `Pairing._save()` writes it with `force=True` before
    the token is ever handed out, so a freshly paired phone is valid at once.

    Returns the device row when the token matches.
    """
    if not token:
        return None
    digest = hashlib.sha256(token.encode()).hexdigest()
    match = None
    for row in _state_devices():
        stored = str(row.get("token_hash") or "")
        # Compare every row so timing does not reveal a near match.
        if stored and hmac.compare_digest(stored, digest):
            match = row
    if match is None:
        return None
    return {
        "id": match.get("id"),
        "name": match.get("name"),
        "created": match.get("created"),
    }


# Indirection so tests can replace the lookup without touching the network.
_DEVICE_LOOKUP = _device_for


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "FreehandsConsole/1.0"

    def log_message(self, *_args) -> None:
        pass

    def _send(self, status: int, payload: Any) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        # No wildcard origin: the only client is the Android app, which is not
        # subject to CORS. Allowing every site would let a page in the
        # operator's browser probe this endpoint.
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _authed(self) -> bool:
        got = (self.headers.get("Authorization") or "").replace("Bearer ", "").strip()
        if not got:
            return False
        expected = _token()
        if expected:
            # Constant-time compare: a remote control endpoint should not leak
            # the token length or a matching prefix through response timing.
            if len(got) == len(expected):
                diff = 0
                for a, b in zip(got, expected):
                    diff |= ord(a) ^ ord(b)
                if diff == 0:
                    return True
        device = _device_cached(got)
        if device is not None:
            self.device = device
            return True
        return False

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return {}

    def do_OPTIONS(self) -> None:
        self._send(204, {})

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path == "/health":
            return self._send(200, {"ok": True})
        if path == "/api/version":
            # Public: the app checks for updates before it is paired.
            return self._send(200, _latest_release())
        if not self._authed():
            return self._send(401, {"error": "unauthorized"})
        if path == "/api/power":
            return self._send(200, {
                "running": _alive(), "pid": _read_pid(),
                "device": getattr(self, "device", None),
            })
        query = ("?" + self.path.split("?", 1)[1]) if "?" in self.path else ""
        if path in ("/api/status", "/api/log", "/api/commands", "/api/settings",
                    "/api/selftest"):
            status, payload = _proxy(path + query)
            return self._send(status, payload)
        return self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        path = self.path.split("?")[0]
        # Pairing must work before a device has a token. The code is the
        # credential, and _pair_allowed stops the endpoint being brute-forced.
        if path == "/api/pair":
            if not _pair_allowed(self.client_address[0]):
                return self._send(429, {"error": "too many attempts, wait a minute"})
            body = self._body()
            # Only claiming is reachable from outside. Opening a code stays in
            # Discord, so a code can only come from an operator running +pair;
            # otherwise anyone could mint codes and phish one out of you.
            if str(body.get("action") or "").lower() != "claim":
                return self._send(400, {"error": "action must be claim"})
            status, payload = _proxy("/api/pair", "POST", body)
            return self._send(status, payload)
        if not self._authed():
            return self._send(401, {"error": "unauthorized"})
        body = self._body()
        if path == "/api/power":
            action = (body.get("action") or "").lower()
            if action == "start":
                return self._send(200, _start())
            if action == "stop":
                return self._send(200, _stop())
            if action in ("restart", "force_restart"):
                return self._send(200, _restart())
            return self._send(400, {"error": "action must be start, stop or restart"})
        return self._send(404, {"error": "not found"})

    def do_PATCH(self) -> None:
        if not self._authed():
            return self._send(401, {"error": "unauthorized"})
        if self.path.split("?")[0] == "/api/settings":
            status, payload = _proxy("/api/settings", "PATCH", self._body())
            return self._send(status, payload)
        return self._send(404, {"error": "not found"})


def main(serve: bool = True) -> int:
    if not _token():
        # Not fatal any more: devices pair themselves, and a paired device is
        # the normal credential. The endpoint is still closed to everyone
        # without one, so this is a notice rather than a refusal.
        print("No FH_CONSOLE_TOKEN set; only paired devices can connect.")
        print("Run +pair in Discord, then enter the code in the app.")
    port = int(os.environ.get("FH_CONSOLE_PORT", DEFAULT_PORT))
    # The bot has to be running before anyone can pair, because the pairing
    # code is issued by a Discord command. Starting it here means a fresh
    # machine reaches a usable state with no manual step.
    started = _start()
    print(f"bot: {started}")

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.daemon_threads = True
    print(f"Freehands console API on 0.0.0.0:{port}")
    if not serve:
        server.server_close()
        return 0
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
