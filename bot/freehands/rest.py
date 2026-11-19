"""Discord REST transport.

Kept deliberately thin: one `request()` that knows about rate limits and
retries, and typed helpers on top. Every response's rate-limit bucket is
remembered per route so a burst of moderation calls waits instead of getting
429'd.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .config import API
from .log import log

USER_AGENT = "DiscordBot (https://github.com/Lynxifyy/Freehands-Discord-Bot, 2.0.0)"


class RestError(Exception):
    def __init__(self, status: int, body: str, route: str) -> None:
        super().__init__(f"{status} {route}: {body[:200]}")
        self.status = status
        self.body = body
        self.route = route


class Bucket:
    """Per-route token bucket derived from Discord's rate-limit headers."""

    __slots__ = ("remaining", "reset_at")

    def __init__(self) -> None:
        self.remaining = 1
        self.reset_at = 0.0

    def wait(self) -> float:
        if self.remaining > 0 or time.time() >= self.reset_at:
            return 0.0
        return max(0.0, self.reset_at - time.time())

    def update(self, headers) -> None:
        try:
            self.remaining = int(headers.get("X-RateLimit-Remaining", "1"))
        except (TypeError, ValueError):
            self.remaining = 1
        try:
            reset_after = float(headers.get("X-RateLimit-Reset-After", "0"))
        except (TypeError, ValueError):
            reset_after = 0.0
        self.reset_at = time.time() + reset_after


class Rest:
    def __init__(self, token: str) -> None:
        self.token = token
        self.buckets: dict[str, Bucket] = {}
        self._global_until = 0.0

    # -- core -------------------------------------------------------------
    def _bucket_key(self, method: str, route: str) -> str:
        return f"{method} {route.split('?')[0]}"

    def request(
        self,
        method: str,
        route: str,
        body: Any = None,
        *,
        reason: str | None = None,
        retries: int = 3,
        timeout: float = 15.0,
    ) -> Any:
        key = self._bucket_key(method, route)
        bucket = self.buckets.setdefault(key, Bucket())
        attempt = 0
        while True:
            pause = max(bucket.wait(), self._global_until - time.time())
            if pause > 0:
                time.sleep(min(pause, 10.0))

            data = None if body is None else json.dumps(body).encode()
            headers = {
                "Authorization": f"Bot {self.token}",
                "User-Agent": USER_AGENT,
                "Content-Type": "application/json",
            }
            if reason:
                headers["X-Audit-Log-Reason"] = urllib.parse.quote(reason[:512])
            req = urllib.request.Request(API + route, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    bucket.update(resp.headers)
                    payload = resp.read()
                    return json.loads(payload) if payload else None
            except urllib.error.HTTPError as exc:
                raw = exc.read().decode("utf-8", "replace")
                bucket.update(exc.headers)
                if exc.code == 429:
                    delay = _retry_after(raw)
                    self._global_until = time.time() + delay
                    log.warning("rate limited on %s, sleeping %.2fs", key, delay)
                    attempt += 1
                    if attempt > retries:
                        raise RestError(429, raw, route) from exc
                    time.sleep(min(delay, 10.0))
                    continue
                if exc.code >= 500:
                    attempt += 1
                    if attempt > retries:
                        raise RestError(exc.code, raw, route) from exc
                    time.sleep(min(0.5 * 2 ** attempt, 5.0))
                    continue
                raise RestError(exc.code, raw, route) from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                attempt += 1
                if attempt > retries:
                    raise RestError(0, repr(exc), route) from exc
                time.sleep(min(0.5 * 2 ** attempt, 5.0))

    def try_request(self, method: str, route: str, body: Any = None, **kw) -> tuple[int, Any]:
        """Like `request` but returns (status, payload) instead of raising."""
        try:
            return 200, self.request(method, route, body, **kw)
        except RestError as exc:
            return exc.status, None

    # -- convenience ------------------------------------------------------
    def me(self) -> dict:
        return self.request("GET", "/users/@me")

    def send(self, channel_id: int, content: str = "", **extra) -> dict:
        payload: dict[str, Any] = {
            "allowed_mentions": {"parse": [], "replied_user": False},
        }
        if content:
            payload["content"] = content
        payload.update(extra)
        return self.request("POST", f"/channels/{channel_id}/messages", payload)

    def reply(self, channel_id: int, message_id: int, content: str, **extra) -> dict:
        payload: dict[str, Any] = {
            "message_reference": {"message_id": str(message_id), "fail_if_not_exists": False},
            "allowed_mentions": {"parse": [], "replied_user": False},
        }
        if content:
            payload["content"] = content
        payload.update(extra)
        return self.request("POST", f"/channels/{channel_id}/messages", payload)

    def edit(self, channel_id: int, message_id: int, content: str) -> dict:
        return self.request(
            "PATCH", f"/channels/{channel_id}/messages/{message_id}", {"content": content}
        )

    def delete(self, channel_id: int, message_id: int) -> int:
        return self.try_request("DELETE", f"/channels/{channel_id}/messages/{message_id}")[0]

    def react(self, channel_id: int, message_id: int, emoji: str) -> int:
        quoted = urllib.parse.quote(emoji, safe="")
        route = f"/channels/{channel_id}/messages/{message_id}/reactions/{quoted}/@me"
        return self.try_request("PUT", route)[0]

    def typing(self, channel_id: int) -> int:
        return self.try_request("POST", f"/channels/{channel_id}/typing")[0]

    def messages(self, channel_id: int, limit: int = 50, after: int | None = None) -> list[dict]:
        query = f"?limit={min(limit, 100)}"
        if after:
            query += f"&after={after}"
        return self.request("GET", f"/channels/{channel_id}/messages{query}") or []

    def timeout(self, guild_id: int, user_id: int, seconds: int, reason: str | None = None) -> int:
        from datetime import datetime, timedelta, timezone

        until = (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()
        status, _ = self.try_request(
            "PATCH",
            f"/guilds/{guild_id}/members/{user_id}",
            {"communication_disabled_until": until},
            reason=reason,
        )
        return status

    def untimeout(self, guild_id: int, user_id: int, reason: str | None = None) -> int:
        status, _ = self.try_request(
            "PATCH",
            f"/guilds/{guild_id}/members/{user_id}",
            {"communication_disabled_until": None},
            reason=reason,
        )
        return status

    def ban(self, guild_id: int, user_id: int, reason: str | None = None,
            delete_seconds: int = 0) -> int:
        return self.try_request(
            "PUT",
            f"/guilds/{guild_id}/bans/{user_id}",
            {"delete_message_seconds": delete_seconds},
            reason=reason,
        )[0]

    def unban(self, guild_id: int, user_id: int, reason: str | None = None) -> int:
        return self.try_request("DELETE", f"/guilds/{guild_id}/bans/{user_id}", reason=reason)[0]

    def kick(self, guild_id: int, user_id: int, reason: str | None = None) -> int:
        return self.try_request(
            "DELETE", f"/guilds/{guild_id}/members/{user_id}", reason=reason
        )[0]

    def bans(self, guild_id: int) -> list[dict]:
        return self.request("GET", f"/guilds/{guild_id}/bans?limit=1000") or []

    def member(self, guild_id: int, user_id: int) -> dict | None:
        status, payload = self.try_request("GET", f"/guilds/{guild_id}/members/{user_id}")
        return payload if status == 200 else None

    def add_role(self, guild_id: int, user_id: int, role_id: int, reason=None) -> int:
        return self.try_request(
            "PUT", f"/guilds/{guild_id}/members/{user_id}/roles/{role_id}", reason=reason
        )[0]

    def remove_role(self, guild_id: int, user_id: int, role_id: int, reason=None) -> int:
        return self.try_request(
            "DELETE", f"/guilds/{guild_id}/members/{user_id}/roles/{role_id}", reason=reason
        )[0]

    def audit(self, guild_id: int, action_type: int, limit: int = 25) -> list[dict]:
        payload = self.request(
            "GET", f"/guilds/{guild_id}/audit-logs?limit={min(limit, 100)}&action_type={action_type}"
        )
        return (payload or {}).get("audit_log_entries", [])


def _retry_after(raw: str) -> float:
    try:
        payload = json.loads(raw)
    except ValueError:
        return 1.0
    try:
        return min(max(float(payload.get("retry_after", 1.0)), 0.05), 10.0)
    except (TypeError, ValueError):
        return 1.0
