"""Command parsing and dispatch.

A command is `+name args...` or `+name` inside a mention prefix. Parsing is
separated from execution so the grammar can be tested without a network and
unknown commands produce a helpful suggestion instead of silence.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Callable

from .config import PREFIX


@dataclass
class Command:
    name: str
    args: list[str] = field(default_factory=list)
    raw: str = ""

    @property
    def text(self) -> str:
        return " ".join(self.args)


# Commands whose name is more than one word. Kept here so `parse` can join them
# before the registry sees a name.
MULTIWORD = {"temp ownership"}


@dataclass
class Spec:
    name: str
    handler: Callable
    tier: str = "user"           # owner | admin | mod | user
    usage: str = ""
    summary: str = ""
    aliases: tuple[str, ...] = ()
    cooldown: float = 0.0
    only_user: int | None = None   # when set, nobody else may run this command


def parse(content: str, prefix: str = PREFIX) -> Command | None:
    """Return a Command when `content` starts with the prefix."""
    if not content:
        return None
    stripped = content.strip()
    if not stripped.startswith(prefix):
        return None
    body = stripped[len(prefix):].strip()
    if not body:
        return None
    parts = body.split()
    name = parts[0].lower()
    rest = parts[1:]
    # `+Temp Ownership @user` is one command, not `+temp` with an argument, so
    # absorb the second word when the pair forms a known multi-word command.
    if rest and f"{name} {rest[0].lower()}" in MULTIWORD:
        name = f"{name} {rest[0].lower()}"
        rest = rest[1:]
    return Command(name=name, args=rest, raw=body)


def _mention_prefix(content: str, bot_id: int, prefix: str) -> str | None:
    """`<@bot> +cmd` should work too; returns the remainder."""
    for token in (f"<@{bot_id}>", f"<@!{bot_id}>"):
        if content.startswith(token):
            rest = content[len(token):].strip()
            if rest.startswith(prefix):
                return rest
    return None


class Registry:
    def __init__(self) -> None:
        self.specs: dict[str, Spec] = {}
        self._alias: dict[str, str] = {}

    def add(self, spec: Spec) -> None:
        self.specs[spec.name] = spec
        for alias in spec.aliases:
            self._alias[alias] = spec.name

    def resolve(self, name: str) -> Spec | None:
        if name in self.specs:
            return self.specs[name]
        target = self._alias.get(name)
        return self.specs.get(target) if target else None

    def suggest(self, name: str) -> str | None:
        pool = list(self.specs) + list(self._alias)
        match = difflib.get_close_matches(name, pool, n=1, cutoff=0.6)
        return match[0] if match else None

    def by_tier(self, tier: str) -> list[Spec]:
        order = {"owner": 0, "admin": 1, "mod": 2, "user": 3}
        ceiling = order[tier]
        return sorted(
            (s for s in self.specs.values() if order[s.tier] >= ceiling),
            key=lambda s: (order[s.tier], s.name),
        )


def split_target_and_rest(args: list[str]) -> tuple[str | None, list[str]]:
    """Pull a leading user mention or id off the argument list."""
    if not args:
        return None, []
    return args[0], args[1:]


def user_id_from(token: str) -> int | None:
    """Accept `<@123>`, `<@!123>`, `123`, or `name#1234`-style leftovers."""
    if not token:
        return None
    digits = "".join(ch for ch in token if ch.isdigit())
    if len(digits) >= 15:
        return int(digits)
    return None
