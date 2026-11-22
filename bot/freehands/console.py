"""Loopback API for the operator console.

This server binds to 127.0.0.1 only and is never exposed directly. The
supervisor (`console_api.py`) holds the public port and proxies here, so the
internet never reaches the process that owns the Discord token.

It reads the engine's live objects in-process, which is the one place settings
can be changed safely: a second process writing `state.json` would be
overwritten by the running bot's next save.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

from .command_docs import detail_for
from .log import log

BOT_API_PORT = 8791


def _json(handler: BaseHTTPRequestHandler, status: int, payload: Any) -> None:
    body = json.dumps(payload).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class BotApi:
    """Serve the console's read and write calls from inside the bot process."""

    def __init__(self, engine, port: int = BOT_API_PORT) -> None:
        self.engine = engine
        self.port = port
        self._server: ThreadingHTTPServer | None = None

    # -- handlers ---------------------------------------------------------
    def status(self) -> dict[str, Any]:
        e = self.engine
        s = e.settings
        return {
            "running": True,
            "bot": {"id": str(e.rest.me().get("id")), "name": e.rest.me().get("username")},
            "settings": s.to_json(),
            "stats": {"messages": 0, "events": e.events.counts()},
            "gateway": True,
        }

    def log_rows(self, limit: int, after: int) -> dict[str, Any]:
        rows = self.engine.events.recent(limit=limit, after=after)
        return {"rows": rows, "counts": self.engine.events.counts()}

    def commands(self) -> dict[str, Any]:
        """Every registered command, grouped by the tier that may run it."""
        out = []
        for spec in self.engine.registry.all():
            out.append({
                "name": spec.name,
                "usage": spec.usage,
                "summary": spec.summary,
                "detail": spec.detail or detail_for(spec.name, spec.summary),
                "tier": spec.tier,
                "aliases": list(spec.aliases),
            })
        return {"commands": out}

    def settings(self, patch: dict[str, Any] | None = None) -> dict[str, Any]:
        s = self.engine.settings
        if patch:
            allowed = {
                "anti_ban": bool,
                "moderation_enabled": bool,
                "automod": bool,
                "watch_enabled": bool,
                "watch_armed": bool,
                "codes_enabled": bool,
                "lockdown": bool,
                "presence_enabled": bool,
                "punish_strikes_to_lock": int,
                "spam_limit": int,
                "spam_window": float,
                "raid_joins": int,
                "raid_window": float,
            }
            changed = {}
            for key, value in patch.items():
                caster = allowed.get(key)
                if caster is None:
                    continue
                setattr(s, key, caster(value))
                changed[key] = getattr(s, key)
            if changed:
                self.engine.store.touch()
                self.engine.store.save(force=True)
                log.info("settings changed from console: %s", changed)
            return {"settings": s.to_json(), "changed": changed}
        return {"settings": s.to_json()}

    # -- server -----------------------------------------------------------
    def _make_handler(self):
        api = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args) -> None:
                pass

            def _body(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length") or 0)
                if not length:
                    return {}
                try:
                    return json.loads(self.rfile.read(length) or b"{}")
                except ValueError:
                    return {}

            def do_GET(self) -> None:
                path = self.path.split("?")[0]
                query = {}
                if "?" in self.path:
                    for pair in self.path.split("?", 1)[1].split("&"):
                        if "=" in pair:
                            k, v = pair.split("=", 1)
                            query[k] = v
                try:
                    if path == "/api/status":
                        return _json(self, 200, api.status())
                    if path == "/api/log":
                        return _json(self, 200, api.log_rows(
                            int(query.get("limit", 100)), int(query.get("after", 0))))
                    if path == "/api/commands":
                        return _json(self, 200, api.commands())
                    if path == "/api/settings":
                        return _json(self, 200, api.settings())
                    return _json(self, 404, {"error": "not found"})
                except Exception as exc:  # noqa: BLE001 - report, never kill the server
                    log.warning("bot api GET %s failed: %r", path, exc)
                    return _json(self, 500, {"error": str(exc)})

            def do_PATCH(self) -> None:
                if self.path.split("?")[0] != "/api/settings":
                    return _json(self, 404, {"error": "not found"})
                try:
                    return _json(self, 200, api.settings(self._body()))
                except Exception as exc:  # noqa: BLE001
                    return _json(self, 500, {"error": str(exc)})

        return Handler

    def start(self) -> bool:
        try:
            self._server = ThreadingHTTPServer(
                ("127.0.0.1", self.port), self._make_handler()
            )
        except OSError as exc:
            log.warning("console api not started on %s: %s", self.port, exc)
            return False
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, daemon=True,
                         name="console-api").start()
        log.info("console api on 127.0.0.1:%s", self.port)
        return True

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server = None
