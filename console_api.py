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
import threading
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
# Present only while the operator has deliberately stopped the bot, so the
# watchdog can tell "stopped on purpose" from "crashed".
STOPPED_MARKER = BOT_DIR / "freehands.stopped"
STATE = BOT_DIR / "state.json"
BOT_API = "http://127.0.0.1:8791"
# Serialises start/stop so the watchdog and a button press cannot both spawn a
# bot. A re-entrant lock: `_restart` holds it across a stop and a start.
_LIFECYCLE = threading.RLock()
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


def _client_ip(headers, peer: str) -> str:
    """The address a request really came from.

    This host sits behind a proxy, so `peer` is the proxy and the real address
    is in a forwarding header. Only the first hop is taken: the rest of the list
    is client-controlled, so trusting it would let anyone claim any location.
    """
    for name in ("X-Forwarded-For", "X-Real-IP", "CF-Connecting-IP"):
        raw = headers.get(name) if headers else None
        if raw:
            first = str(raw).split(",")[0].strip()
            if first:
                return first
    return (peer or "").strip()


def _pair_allowed(addr: str) -> bool:
    now = time.time()
    recent = [t for t in _PAIR_ATTEMPTS.get(addr, []) if now - t < _PAIR_WINDOW]
    if len(recent) >= _PAIR_LIMIT:
        _PAIR_ATTEMPTS[addr] = recent
        return False
    recent.append(now)
    _PAIR_ATTEMPTS[addr] = recent
    return True


AUTHORIZE_HTML = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Freehands - authorize this phone</title>
<style>
  :root { color-scheme: dark; }
  body {
    margin: 0; padding: 28px 22px calc(28px + env(safe-area-inset-bottom));
    background: #0b0d14; color: #f2f4ff;
    font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    display: flex; flex-direction: column; justify-content: center;
    min-height: 100vh; box-sizing: border-box;
  }
  .mark { font-size: 26px; font-weight: 700; letter-spacing: 3px; }
  .sub { color: #8b93ad; font-size: 12px; margin-bottom: 28px; }
  .label { color: #8b93ad; font-size: 10px; letter-spacing: 1.2px; margin-bottom: 8px; }
  .code {
    font: 700 30px/1.2 ui-monospace, SFMono-Regular, Menlo, monospace;
    letter-spacing: 8px; color: #7c8bff; margin: 10px 0 6px;
  }
  .hint { color: #8b93ad; font-size: 12px; }
  .status {
    margin-top: 22px; padding: 12px 14px; border-radius: 12px;
    background: #151a26; border: 1px solid #232b3d; font-size: 13px;
  }
  .ok { border-color: #2c6e49; background: #10251a; }
  .bad { border-color: #6e2c2c; background: #251010; }
  button {
    margin-top: 18px; width: 100%; padding: 14px; border: 0; border-radius: 12px;
    background: #5865f2; color: #fff; font-size: 15px; font-weight: 600;
  }
  button[disabled] { background: #2b3350; color: #8b93ad; }
  .who { margin-top: 14px; font-size: 13px; color: #8b93ad; }
</style></head>
<body>
  <div class="mark">FREEHANDS</div>
  <div class="sub">Authorize this phone</div>
  <div class="label">CODE</div>
  <div class="code" id="code">------</div>
  <div class="hint">In Discord, run <b>+pair CODE</b>. Approval has to happen
  there, because that is where the bot can verify who you are.</div>
  <div class="status" id="status">Waiting for approval&hellip;</div>
  <div class="who" id="who"></div>
  <button id="again" disabled onclick="start()">Get a new code</button>
<script>
let code = null, timer = null;
const statusEl = document.getElementById('status');
const codeEl = document.getElementById('code');
const whoEl = document.getElementById('who');
const again = document.getElementById('again');

async function api(body) {
  const res = await fetch('/api/pair', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
  return {ok: res.ok, data: await res.json().catch(() => ({}))};
}

async function start() {
  again.disabled = true;
  clearInterval(timer);
  statusEl.className = 'status';
  statusEl.textContent = 'Requesting a code\u2026';
  const r = await api({action: 'open', name: 'webview'});
  if (!r.ok || !r.data.code) {
    statusEl.className = 'status bad';
    statusEl.textContent = 'Could not reach the bot. Is it running?';
    again.disabled = false;
    return;
  }
  code = r.data.code;
  codeEl.textContent = code;
  statusEl.textContent = 'Waiting for approval\u2026';
  timer = setInterval(check, 2000);
}

async function check() {
  if (!code) return;
  const r = await api({action: 'poll', code: code});
  if (!r.ok) {
    clearInterval(timer);
    statusEl.className = 'status bad';
    statusEl.textContent = 'This code expired. Get a new one.';
    again.disabled = false;
    return;
  }
  if (r.data.status === 'approved') {
    clearInterval(timer);
    statusEl.className = 'status ok';
    statusEl.textContent = 'Approved. Return to the app.';
    const id = r.data.identity || {};
    whoEl.textContent = id.label ? ('Signed in as ' + id.label) : '';
    again.disabled = false;
    // The app reads this to pick the token up without a second flow.
    window.FreehandsPairing = {token: r.data.token, identity: id};
    // The page does not navigate after approval, so `onPageFinished` has
    // already fired and will not fire again. Push the result to the app
    // instead of waiting to be asked for it.
    if (window.FreehandsAndroid && window.FreehandsAndroid.onPaired) {
      window.FreehandsAndroid.onPaired(JSON.stringify(window.FreehandsPairing));
    }
  }
}

start();
</script>
</body></html>
"""


def _oauth_configured() -> bool:
    """True when a real Discord OAuth app is set up for this deployment.

    A client secret cannot be shipped in a public repository, so the authorize
    page works as a device-code page by default and upgrades to full Discord
    sign-in only when the operator supplies a secret in the environment.
    """
    return bool(os.environ.get("FH_DISCORD_CLIENT_ID")
                and os.environ.get("FH_DISCORD_CLIENT_SECRET"))


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


def _healthy() -> bool:
    """True only when the bot process exists *and* answers its own API.

    A bare PID check is not enough. The gateway reads its socket with no
    timeout, so a half-open connection leaves the process alive but wedged:
    `_alive()` still says yes, so pressing Start used to return
    `already: true` and never restart anything. That is the "it turned off and
    I cannot turn it back on" report. Asking the API is the only check that
    reflects what the app can actually do.
    """
    return _alive() and _bot_api_up()


def _wanted() -> bool:
    """False after the operator pressed Stop, until they press Start.

    The watchdog must not resurrect a bot that was stopped on purpose. The
    pidfile cannot express that: Stop deletes it, which looks identical to a
    crash.
    """
    return not STOPPED_MARKER.exists()


def _start() -> dict[str, Any]:
    _reap()
    with _LIFECYCLE:
        return _start_locked()


def _start_locked() -> dict[str, Any]:
    try:
        STOPPED_MARKER.unlink()
    except OSError:
        pass
    if _healthy():
        return {"ok": True, "already": True, "pid": _read_pid()}
    if _alive():
        # Process is there but wedged. Kill it rather than starting a second
        # one: two bots on the same token fight over the gateway session and
        # the console port, which is worse than the hang.
        print("restarting unresponsive bot")
        _kill(_read_pid())
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


def _kill(pid: int, timeout: float = 10.0) -> bool:
    """Terminate `pid`, escalating to SIGKILL if it will not go.

    A wedged bot often ignores SIGTERM: the signal is handled by the main
    thread, which may itself be blocked. Without the escalation the supervisor
    would sit there with a process it cannot remove and never start a new one.
    """
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            break
        except OSError:
            return False
        deadline = time.time() + timeout
        while time.time() < deadline:
            if _read_pid() != pid:
                return True
            time.sleep(0.2)
    return _read_pid() != pid


def _stop() -> dict[str, Any]:
    with _LIFECYCLE:
        return _stop_locked()


def _stop_locked() -> dict[str, Any]:
    pid = _read_pid()
    # Written before the kill so a watchdog that runs in between does not
    # treat the shutdown as a crash and start the bot straight back up.
    try:
        STOPPED_MARKER.write_text(str(int(time.time())))
    except OSError:
        pass
    if pid is None:
        return {"ok": True, "already": True}
    ok = _kill(pid)
    try:
        PIDFILE.unlink()
    except OSError:
        pass
    _reap()
    if not ok:
        return {"ok": False, "error": f"process {pid} did not exit"}
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
    with _LIFECYCLE:
        _stop_locked()
        time.sleep(1.0)
        return _start_locked()


def _watchdog(interval: float = 20.0, grace: float = 90.0) -> None:
    """Keep the bot up without a human pressing Start.

    Before this, a bot that crashed or wedged stayed down until someone
    noticed and pressed the button — and pressing it did nothing, because
    `_start` only checked for a live PID. The grace period covers a stop that
    is still settling; `_wanted` covers a deliberate Stop from the app, which
    must not be undone. Both stop a crash-loop from hammering Discord's login
    endpoint.
    """
    down_since = 0.0
    while True:
        time.sleep(interval)
        try:
            if _healthy():
                down_since = 0.0
                continue
            if not _wanted():
                down_since = 0.0
                continue
            now = time.time()
            if down_since == 0.0:
                down_since = now
                continue
            if now - down_since < grace:
                continue
            print("watchdog: bot is not answering; restarting it")
            _start()
            down_since = 0.0
        except Exception as exc:  # a watchdog must never take the supervisor down
            print(f"watchdog error: {exc!r}")


def _bot_api_up() -> bool:
    try:
        with urllib.request.urlopen(f"{BOT_API}/api/status", timeout=2) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


def _proxy(path: str, method: str = "GET", body: dict | None = None,
           token: str = "") -> tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    # The bot derives the acting operator from the device token, so the
    # caller's credential has to survive the hop. Dropping it made every
    # authenticated route look like an unpaired caller.
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"{BOT_API}{path}", data=data, method=method, headers=headers,
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

    def _send_html(self, status: int, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # The page is self-contained: no scripts, styles or frames from
        # anywhere else, so a strict policy costs nothing and blocks injected
        # markup from phoning home.
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

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

    def _bearer(self) -> str:
        return (self.headers.get("Authorization") or "").replace("Bearer ", "").strip()

    def _authed(self) -> bool:
        got = self._bearer()
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
        if path in ("/authorize", "/authorize/"):
            # Public, and deliberately so: it is the page a not-yet-paired
            # phone opens. It shows only a code this process just minted.
            return self._send_html(200, AUTHORIZE_HTML)
        if path == "/api/auth-info":
            return self._send(200, {"oauth": _oauth_configured()})
        if not self._authed():
            return self._send(401, {"error": "unauthorized"})
        if path == "/api/power":
            return self._send(200, {
                "running": _alive(), "pid": _read_pid(),
                # What the app should actually gate on. `running` is the
                # process; `healthy` means it is answering, which is the
                # difference between "up" and "working".
                "healthy": _healthy(), "wanted": _wanted(),
                "device": getattr(self, "device", None),
            })
        query = ("?" + self.path.split("?", 1)[1]) if "?" in self.path else ""
        if path in ("/api/status", "/api/log", "/api/commands", "/api/settings",
                    "/api/selftest", "/api/people", "/api/loops", "/api/owner"):
            status, payload = _proxy(path + query, token=self._bearer())
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
            action = str(body.get("action") or "").lower()
            # `open` and `poll` are how a phone that is showing its own screen
            # gets a code. Neither can grant access: `open` only mints a code
            # that has no identity attached, and `poll` returns nothing until
            # an operator approves that code inside Discord. The code is shown
            # on the operator's own phone, so it never crosses an untrusted
            # channel the way a code sent by DM would.
            if action not in ("open", "poll", "claim"):
                return self._send(400, {"error": "unknown action"})
            # The bot cannot see the client: it listens on loopback. The real
            # address is stamped here so `+devices` can report where a phone
            # paired from. It is advisory only and never used for auth.
            body["ip"] = _client_ip(self.headers, self.client_address[0])
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
        if path in ("/api/loops", "/api/loops/stop", "/api/owner"):
            status, payload = _proxy(path, "POST", body, token=self._bearer())
            return self._send(status, payload)
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
    threading.Thread(target=_watchdog, name="watchdog", daemon=True).start()

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
