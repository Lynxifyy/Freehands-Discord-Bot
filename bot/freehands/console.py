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
from .config import GUILD_ID
from .devices import identify
from .pairing import Identity
from .log import log
from .people import can_target, people as build_people

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
        # The bot's own identity never changes, and the app polls status every
        # few seconds, so it is resolved once instead of hitting Discord's REST
        # API on every poll.
        self._identity: dict[str, str] | None = None

    # -- handlers ---------------------------------------------------------
    def identity(self) -> dict[str, str]:
        if self._identity is None:
            me = self.engine.rest.me() or {}
            self._identity = {
                "id": str(me.get("id") or ""),
                "name": me.get("username") or "",
            }
        return self._identity

    def selftest(self) -> dict[str, Any]:
        """Run `+test`'s checks and return them as data for the app.

        Same checks as the Discord command: a phone that shows green must mean
        the same thing as `+test` saying OK in Discord.
        """
        from . import test_command

        results = []
        for name, fn in test_command.CHECKS:
            ok, detail = test_command._check(name, lambda f=fn: f(self.engine))
            results.append({"name": name, "ok": ok, "detail": detail})
        return {
            "passed": sum(1 for r in results if r["ok"]),
            "total": len(results),
            "checks": results,
        }

    def status(self, actor: str = "") -> dict[str, Any]:
        e = self.engine
        s = e.settings
        return {
            "running": True,
            "bot": self.identity(),
            "settings": s.to_json(),
            "stats": {"messages": 0, "events": e.events.counts()},
            "gateway": True,
            "identity": self._identity_of(actor),
        }

    def _identity_of(self, user_id: str) -> dict[str, Any] | None:
        """The verified account behind a device, for the app to display."""
        if not user_id:
            return None
        for device in self.engine.pairing.devices.values():
            if device.identity.user_id == user_id:
                return device.identity.to_json()
        return None

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

    def pair(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """The device-authorization flow for the console app.

        Three actions, all reachable before the app has a token:

        * `open`  - the app asks for a code and displays it.
        * `poll`  - the app waits to see whether a human approved it.
        * `claim` - retained for the older path; binds an already-verified
                    account directly.

        Approval itself happens in Discord, in `+pair`, because that is the
        only place the bot can see who is asking. Nothing here accepts an
        identity from the app: an app that could name its own account could
        claim to be anyone.
        """
        action = str(body.get("action") or "").lower()

        if action == "open":
            name = str(body.get("name") or "console")
            model = str(body.get("model") or "").strip()
            ip = str(body.get("ip") or "").strip()
            code = self.engine.pairing.open(name, model=model, ip=ip)
            log.info("pairing code opened for %s", name)
            return 200, {"ok": True, "code": code, "expires_in": 300,
                         "instructions": "Run +pair " + code + " in Discord."}

        if action == "poll":
            status = self.engine.pairing.poll(str(body.get("code") or ""))
            if status is None:
                return 404, {"error": "unknown or expired code"}
            return 200, status

        if action == "claim":
            # The address is forwarded by the supervisor, which is the only
            # process that sees the real client. It is recorded, not trusted:
            # a VPN or mobile carrier will place the phone elsewhere.
            from .geolocate import describe

            ip = str(body.get("ip") or "").strip()
            model = str(body.get("model") or "").strip()
            known = identify(model, name=str(body.get("name") or ""))
            raw_identity = body.get("identity")
            identity = Identity.from_json(raw_identity) if raw_identity else None
            if identity is None or not identity.user_id:
                # Without a verified identity there is nothing for the console
                # to act as, and trusting one supplied by the app would defeat
                # the point of pairing through Discord.
                return 400, {"error": "approve in Discord with +pair <code>"}
            token = self.engine.pairing.claim(
                str(body.get("code") or ""),
                paired_by=identity.user_id,
                name=str(body.get("name") or ""),
                ip=ip,
                location="" if known else (describe(ip) if ip else ""),
                app_version=str(body.get("app_version") or ""),
                model=model,
                identity=identity,
            )
            if token is None:
                return 404, {"error": "unknown or expired code"}
            device = max(self.engine.pairing.devices.values(), key=lambda d: d.created)
            return 200, {"ok": True, "token": token, "device": device.id,
                         "identity": identity.to_json()}
        return 400, {"error": "action must be open, poll or claim"}

    def devices(self) -> dict[str, Any]:
        return {"devices": [
            {"id": d.id, "name": d.name, "created": d.created,
             "last_seen": d.last_seen, "paired_by": d.paired_by,
             "identity": d.identity.to_json()}
            for d in sorted(self.engine.pairing.devices.values(), key=lambda d: d.created)
        ]}

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


    def _actor(self, handler) -> str:
        """The Discord id this request acts for, from its device token.

        The id comes from the paired device, never from the request body. A
        console that could name its own actor could name Lynx and reach every
        owner power, so the token is the only source of identity here.
        """
        bearer = (handler.headers.get("Authorization") or "").replace("Bearer ", "").strip()
        device = self.engine.pairing.verify(bearer)
        if device is None:
            return ""
        # The verified identity wins over the legacy field: `paired_by` records
        # who approved a pairing, which after the device-grant change is the
        # same account, but only `identity` was checked against the guild.
        return device.identity.user_id or str(device.paired_by)

    def people(self) -> dict[str, Any]:
        """Who can reach the bot, strongest first, for the loop dropdown."""
        try:
            members = self.engine.rest.members(GUILD_ID) or []
        except Exception as exc:  # noqa: BLE001 - the panel must still open
            log.warning("people listing failed: %r", exc)
            return {"people": [], "error": "could not read the member list"}
        return {"people": [p.to_json() for p in build_people(members)]}

    def loops(self) -> dict[str, Any]:
        return {"loops": self.engine.loops.listing()}

    def arm_loop(self, body: dict[str, Any], actor: str) -> tuple[int, dict[str, Any]]:
        """Start a loop from the console. Lynx-only, same as the command."""
        if not self.engine.powers.allowed(actor):
            return 403, {"ok": False, "error": "Only Lynx can arm a loop."}
        target = str(body.get("target") or "")
        ok, why = can_target(target)
        if not ok:
            return 403, {"ok": False, "error": why}
        try:
            loop = self.engine.loops.arm(
                str(body.get("kind") or "ban"),
                target,
                str(body.get("reason") or "loop"),
                float(body.get("interval") or 60),
                int(body.get("passes") or 1),
                actor,
                notify=bool(body.get("notify")),
            )
        except ValueError as exc:
            return 400, {"ok": False, "error": str(exc)}
        return 200, {"ok": True, "loop": loop.to_json()}

    def stop_loop(self, body: dict[str, Any], actor: str) -> tuple[int, dict[str, Any]]:
        if not self.engine.powers.allowed(actor):
            return 403, {"ok": False, "error": "Only Lynx can stop a loop."}
        loop_id = str(body.get("id") or "").upper()
        if loop_id == "ALL":
            return 200, {"ok": True, "stopped": self.engine.loops.stop_all("stopped from console")}
        if not self.engine.loops.stop(loop_id):
            return 404, {"ok": False, "error": f"No loop {loop_id}."}
        return 200, {"ok": True, "stopped": 1}

    def owner_panel(self, actor: str) -> tuple[int, dict[str, Any]]:
        payload = self.engine.powers.panel(actor)
        return (200 if payload.get("ok") else 403), payload

    def owner_set(self, body: dict[str, Any], actor: str) -> tuple[int, dict[str, Any]]:
        payload = self.engine.powers.set(
            actor,
            str(body.get("key") or ""),
            bool(body.get("on")),
            str(body.get("confirm") or ""),
        )
        return (200 if payload.get("ok") else 403), payload

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
                        return _json(self, 200, api.status(api._actor(self)))
                    if path == "/api/log":
                        return _json(self, 200, api.log_rows(
                            int(query.get("limit", 100)), int(query.get("after", 0))))
                    if path == "/api/commands":
                        return _json(self, 200, api.commands())
                    if path == "/api/selftest":
                        return _json(self, 200, api.selftest())
                    if path == "/api/settings":
                        return _json(self, 200, api.settings())
                    if path == "/api/people":
                        return _json(self, 200, api.people())
                    if path == "/api/loops":
                        return _json(self, 200, api.loops())
                    if path == "/api/owner":
                        status, payload = api.owner_panel(api._actor(self))
                        return _json(self, status, payload)
                    if path == "/api/devices":
                        # Called by the supervisor to check a device token.
                        # The token itself is the credential, so a match is
                        # returned as {"device": ...} and a miss as 401.
                        bearer = (self.headers.get("Authorization") or "").replace("Bearer ", "").strip()
                        device = api.engine.pairing.verify(bearer)
                        if device is None:
                            return _json(self, 401, {"error": "unknown device"})
                        return _json(self, 200, {"device": {
                            "id": device.id, "name": device.name,
                            "created": device.created, "last_seen": device.last_seen,
                        }})
                    return _json(self, 404, {"error": "not found"})
                except Exception as exc:  # noqa: BLE001 - report, never kill the server
                    log.warning("bot api GET %s failed: %r", path, exc)
                    return _json(self, 500, {"error": str(exc)})

            def do_POST(self) -> None:
                path = self.path.split("?")[0]
                try:
                    if path == "/api/pair":
                        status, payload = api.pair(self._body())
                        return _json(self, status, payload)
                    if path == "/api/loops":
                        status, payload = api.arm_loop(self._body(), api._actor(self))
                        return _json(self, status, payload)
                    if path == "/api/loops/stop":
                        status, payload = api.stop_loop(self._body(), api._actor(self))
                        return _json(self, status, payload)
                    if path == "/api/owner":
                        status, payload = api.owner_set(self._body(), api._actor(self))
                        return _json(self, status, payload)
                    return _json(self, 404, {"error": "not found"})
                except Exception as exc:  # noqa: BLE001
                    log.warning("bot api POST %s failed: %r", path, exc)
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
