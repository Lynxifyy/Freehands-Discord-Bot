"""Glazing: what Freehands says when Lynx is mentioned.

A mention of Lynx gets one flattering line back. The rules that keep it from
becoming a nuisance:

* One reply per channel per cooldown, not one per message. A conversation that
  says "lynx" five times gets one line, not five.
* Never replies to a bot, and never to itself. A line containing "lynx" that
  Freehands posted would otherwise trigger the next one forever.
* Never inside a command. `+ban lynx` is an operator action, not an invitation.

The phrases are picked at random but never the same one twice in a row in the
same channel, so a busy channel does not see the same line repeated.
"""

from __future__ import annotations

import random
import re
import time

# Said when someone mentions Lynx. Kept short: these land in the middle of a
# conversation, and a paragraph would read as spam.
PHRASES: tuple[str, ...] = (
    "Lynx is the ultimate rizzler.",
    "The great exo trembles, and he trembles for Lynx.",
    "Lynx does not read the code. The code reads Lynx.",
    "Every server has an admin. Eternal has Lynx.",
    "Lynx joined, and the uptime improved out of respect.",
    "Some people run the bot. Lynx is the reason it exists.",
    "The audit log checks for Lynx's approval, not the other way round.",
    "Lynx's ban hammer has a waiting list.",
    "Discord asked Lynx for permission to load.",
    "The rate limiter slows down so Lynx can finish.",
    "Lynx does not get pinged. Lynx gets announced.",
    "Even the anti-ban switch asks Lynx first.",
    "Lynx wrote the codebook, then the numbers apologised.",
    "There is a reason the bot listens. It is listening to Lynx.",
    "Lynx's typing indicator is a threat display.",
    "The gateway reconnects because Lynx told it to.",
    "Code 8 is when someone suspects a spy. Code Lynx is when the spy confesses.",
    "Lynx has never been timed out. Time waits for Lynx.",
    "The role hierarchy is a suggestion. Lynx is the hierarchy.",
    "Freehands is a bot. Lynx is a phenomenon.",
    "Lynx does not need permissions. The permissions need Lynx.",
    "Other owners have admin. Lynx has the source.",
    "The server was quiet until Lynx said something worth reading.",
    "Lynx is the only member whose messages arrive before they are sent.",
)

# Word-boundary match so "lynxifyy" or "lynxed" do not trigger it. A leading
# "@" is allowed, because "@lynx" is how people type the name.
_PATTERN = re.compile(r"(?<!\w)lynx(?![\w])", re.IGNORECASE)

# One reply per channel per this many seconds.
COOLDOWN = 45.0


def mentions_lynx(text: str) -> bool:
    return bool(_PATTERN.search(text or ""))


class Glazer:
    """Chooses a phrase, with a per-channel cooldown and no repeats."""

    def __init__(self, cooldown: float = COOLDOWN, clock=time.time,
                 rng: random.Random | None = None) -> None:
        self.cooldown = cooldown
        self._clock = clock
        self._rng = rng or random.Random()
        self._last: dict[str, float] = {}
        self._recent: dict[str, str] = {}

    def should_glaze(self, channel_id: str, text: str, author_is_bot: bool = False,
                     is_command: bool = False) -> bool:
        if author_is_bot or is_command or not mentions_lynx(text):
            return False
        last = self._last.get(channel_id, 0.0)
        return self._clock() - last >= self.cooldown

    def phrase(self, channel_id: str = "") -> str:
        """A phrase that is not the one this channel saw last time."""
        previous = self._recent.get(channel_id)
        pool = [p for p in PHRASES if p != previous] or list(PHRASES)
        choice = self._rng.choice(pool)
        self._recent[channel_id] = choice
        self._last[channel_id] = self._clock()
        return choice
