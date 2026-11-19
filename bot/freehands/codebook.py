"""Code sense.

Operators speak in short numeric codes in chat ("code 8"). Each code carries a
severity, an emoji, a list of people/roles to ping and a response line. The
table is data, not code, so `codes.json` can extend or override it without a
restart of the source tree.

Matching is deliberately narrow: a bare number never triggers, and phrase
aliases must match as whole words, so ordinary chatter stays quiet.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

EYES = "\N{EYES}"  # 👀
SIREN = "\N{POLICE CARS REVOLVING LIGHT}"  # 🚨
WHITE_CHECK = "\N{WHITE HEAVY CHECK MARK}"  # ✅

# Code numbers written as words are common in a hurry; keep the map small.
_WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}

_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7,
          "viii": 8, "ix": 9, "x": 10, "xi": 11, "xii": 12}


@dataclass(frozen=True)
class Code:
    number: int
    title: str
    meaning: str
    severity: str = "medium"          # low | medium | high | critical
    emoji: str = EYES
    ping_owner: bool = False
    ping_arceus: bool = False
    ping_roles: tuple[str, ...] = ()
    silence: bool = False             # delete the trigger message (go dark)
    purge_seconds: int = 0            # delete recent messages from the sender
    response: str = ""
    aliases: tuple[str, ...] = ()

    @property
    def critical(self) -> bool:
        return self.severity == "critical"


DEFAULT_CODES: dict[int, Code] = {
    1: Code(
        1, "All clear", "Stand down, the situation is resolved.",
        "low", WHITE_CHECK,
        response="All clear acknowledged. Standing down.",
        aliases=("all clear", "stand down"),
    ),
    2: Code(
        2, "Moving position", "Relocating to a secondary channel.",
        "low", "\N{DIRECT HIT}",
        response="Movement logged. Watch the new position.",
        aliases=("moving position",),
    ),
    3: Code(
        3, "Request backup", "More operators are needed.",
        "medium", SIREN, ping_owner=True, ping_arceus=True,
        response="Backup requested. Operators notified.",
        aliases=("request backup", "need backup"),
    ),
    4: Code(
        4, "Comms compromised", "Assume the channel is being read.",
        "high", SIREN, ping_owner=True, ping_arceus=True, silence=True,
        response="Comms compromised. Going quiet — move to a private channel.",
        aliases=("comms compromised",),
    ),
    5: Code(
        5, "Target acquired", "The subject is identified.",
        "medium", "\N{DIRECT HIT}", ping_owner=True,
        response="Target acquired. File the identification when safe.",
        aliases=("target acquired",),
    ),
    6: Code(
        6, "Extraction needed", "An operator needs to be pulled out.",
        "high", SIREN, ping_owner=True, ping_arceus=True,
        response="Extraction flagged. Hold position until contact.",
        aliases=("extraction needed",),
    ),
    7: Code(
        7, "Going dark", "No further traffic from the sender.",
        "medium", "\N{NEW MOON SYMBOL}", silence=True,
        response="Going dark acknowledged. No reply expected.",
        aliases=("going dark",),
    ),
    8: Code(
        8, "Suspected spy", "A member of this channel is suspected of spying.",
        "high", EYES, ping_owner=True, ping_arceus=True,
        response=(
            "**Code 8 — suspected spy.** "
            "Operators pinged. Nobody say anything sensitive in this channel "
            "until it is cleared. Watch who reacts and who goes quiet."
        ),
        aliases=("suspected spy", "there's a spy", "theres a spy", "we have a spy"),
    ),
    9: Code(
        9, "Cover blown", "Identity is exposed; evacuate the operation.",
        "critical", SIREN, ping_owner=True, ping_arceus=True, silence=True,
        purge_seconds=300,
        response=(
            "**Code 9 — cover blown.** Evacuate. Stop posting here. "
            "Operators pinged and the trigger message has been removed."
        ),
        aliases=("cover blown",),
    ),
    10: Code(
        10, "Getting found out", "The sender believes they are being discovered.",
        "critical", SIREN, ping_owner=True, ping_arceus=True, silence=True,
        response=(
            "**Code 10 — operator is being found out.** "
            "Message removed. @here is not pinged; operators, check your DMs "
            "and assume this channel is watched. Do not reply to the sender here."
        ),
        aliases=("getting found out", "im getting found out", "i'm getting found out"),
    ),
    11: Code(
        11, "Silent alarm", "Something is wrong; respond without drawing attention.",
        "high", EYES, ping_owner=True, ping_arceus=True, silence=True,
        response="Silent alarm logged. Operators are aware. Act normal.",
        aliases=("silent alarm",),
    ),
    12: Code(
        12, "Full lockdown", "Lock the channel and stop all traffic.",
        "critical", SIREN, ping_owner=True, ping_arceus=True, silence=True,
        response="**Code 12 — lockdown.** Channel locked, traffic stopped.",
        aliases=("full lockdown",),
    ),
}

_CODE_PATTERNS = (
    re.compile(r"\bcode\s*[-:#]?\s*(\d{1,3})\b", re.I),
    re.compile(r"\bcode\s*[-:#]?\s*(i{1,3}|iv|vi{0,3}|ix|xi{0,2}|x)\b", re.I),
    re.compile(r"\bcode\s*[-:#]?\s*(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b", re.I),
)


def _normalise(text: str) -> str:
    return re.sub(r"[\u2018\u2019]", "'", text.lower())


@dataclass
class Hit:
    code: Code
    trigger: str
    matched_text: str


@dataclass
class Codebook:
    codes: dict[int, Code] = field(default_factory=lambda: dict(DEFAULT_CODES))
    _alias_index: dict[str, int] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._rebuild_aliases()

    def _rebuild_aliases(self) -> None:
        index: dict[str, int] = {}
        for code in self.codes.values():
            for alias in code.aliases:
                index[_normalise(alias)] = code.number
        self._alias_index = index

    # -- loading ----------------------------------------------------------
    @classmethod
    def load(cls, path: Path | None) -> "Codebook":
        book = cls()
        if not path or not Path(path).exists():
            return book
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return book
        for entry in raw.get("codes", []):
            try:
                number = int(entry["number"])
            except (KeyError, TypeError, ValueError):
                continue
            base = book.codes.get(number)
            book.codes[number] = Code(
                number=number,
                title=entry.get("title", base.title if base else f"Code {number}"),
                meaning=entry.get("meaning", base.meaning if base else ""),
                severity=entry.get("severity", base.severity if base else "medium"),
                emoji=entry.get("emoji", base.emoji if base else EYES),
                ping_owner=bool(entry.get("ping_owner", base.ping_owner if base else False)),
                ping_arceus=bool(entry.get("ping_arceus", base.ping_arceus if base else False)),
                ping_roles=tuple(str(r) for r in entry.get(
                    "ping_roles", base.ping_roles if base else ())),
                silence=bool(entry.get("silence", base.silence if base else False)),
                purge_seconds=int(entry.get("purge_seconds", base.purge_seconds if base else 0)),
                response=entry.get("response", base.response if base else ""),
                aliases=tuple(entry.get("aliases", base.aliases if base else ())),
            )
        book._rebuild_aliases()
        return book

    # -- sensing ----------------------------------------------------------
    def sense(self, text: str) -> Hit | None:
        """Return the first recognised code in `text`, if any."""
        if not text:
            return None
        lowered = _normalise(text)

        for index, pattern in enumerate(_CODE_PATTERNS):
            for match in pattern.finditer(lowered):
                token = match.group(1)
                if index == 0:
                    number = int(token)
                elif index == 1:
                    number = _ROMAN.get(token)
                else:
                    number = _WORD_NUMBERS.get(token)
                if number in self.codes:
                    return Hit(self.codes[number], "number", match.group(0))

        for alias, number in self._alias_index.items():
            if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", lowered):
                return Hit(self.codes[number], "phrase", alias)
        return None

    def get(self, number: int) -> Code | None:
        return self.codes.get(number)

    def listing(self) -> list[Code]:
        return [self.codes[n] for n in sorted(self.codes)]


def render_alert(hit: Hit, author_id: int, author_name: str,
                 owner_id: int, arceus_id: int, extra_pings: list[str]) -> str:
    """Build the alert body for a triggered code."""
    code = hit.code
    pings = list(extra_pings)
    if code.ping_owner:
        pings.append(f"<@{owner_id}>")
    if code.ping_arceus:
        pings.append(f"<@{arceus_id}>")
    head = f"{code.emoji} **CODE {code.number} — {code.title.upper()}**"
    lines = [head, ""]
    lines.append(f"**Reported by** <@{author_id}>")
    lines.append(f"**Meaning** {code.meaning}")
    if code.response:
        lines.append("")
        lines.append(code.response)
    if pings:
        lines.append("")
        lines.append(" ".join(dict.fromkeys(pings)))
    if code.silence:
        lines.append("")
        lines.append("_Trigger message removed._")
    return "\n".join(lines)
