#!/usr/bin/env python3
"""Read-only self check: token, identity, guild, roles, gateway handshake.

Sends nothing to the server. Use it after a deploy to confirm the bot can see
what it needs to see.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bot"))

from freehands.config import GUILD_ID, MAIN_CHAT_ID  # noqa: E402
from freehands.gateway import Gateway  # noqa: E402
from freehands.rest import Rest, RestError  # noqa: E402
from freehands.vault import load_token  # noqa: E402


def main() -> int:
    token = load_token()
    rest = Rest(token)

    try:
        me = rest.me()
    except RestError as exc:
        print(f"token rejected: {exc.status}")
        return 1
    print(f"identity   {me['username']} ({me['id']})")

    member = rest.member(GUILD_ID, int(me["id"]))
    if member is None:
        print("bot is NOT in the guild")
        return 1
    print(f"guild      ok, {len(member.get('roles', []))} roles")

    roles = rest.request("GET", f"/guilds/{GUILD_ID}/roles") or []
    top = max((r["position"] for r in roles if int(r["id"]) in
               {int(x) for x in member.get("roles", [])}), default=0)
    print(f"hierarchy  bot top position {top} of {max(r['position'] for r in roles)}")

    channel = rest.request("GET", f"/channels/{MAIN_CHAT_ID}")
    print(f"channel    #{channel['name']}")

    bans = rest.bans(GUILD_ID)
    print(f"bans       {len(bans)}")

    events: list[str] = []
    gateway = Gateway(token, lambda name, data: events.append(name))
    gateway.start()
    ready = gateway.wait_ready(15)
    print(f"gateway    {'ready' if ready else 'no READY within 15s'}")
    time.sleep(2)
    gateway.stop()
    print(f"events     {len(events)} received while sampling")
    return 0 if ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
