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
    # The server owner and Lynx are different people, and an operator code has
    # to reach both: OWNER_ID is the guild owner, LYNX_ID is the bot's creator.
    ping_lynx: bool = False
    ping_roles: tuple[str, ...] = ()
    silence: bool = False             # delete the trigger message (go dark)
    purge_seconds: int = 0            # delete recent messages from the sender
    ops: bool = False                 # alert into the private channel, not open chat
    room: bool = False                # open a private room and say nothing in open chat
    arm_watch: bool = False           # start watching the flagged member
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
        "medium", SIREN, ping_owner=True, ping_lynx=True, ping_arceus=True,
        response="Backup requested. Operators notified.",
        aliases=("request backup", "need backup"),
    ),
    4: Code(
        4, "Comms compromised", "Assume the channel is being read.",
        "high", SIREN, ping_owner=True, ping_lynx=True, ping_arceus=True, silence=True, ops=True,
        response="Comms compromised. Going quiet — move to a private channel.",
        aliases=("comms compromised",),
    ),
    5: Code(
        5, "Target acquired", "The subject is identified.",
        "medium", "\N{DIRECT HIT}", ping_owner=True, ping_lynx=True,
        response="Target acquired. File the identification when safe.",
        aliases=("target acquired",),
    ),
    6: Code(
        6, "Extraction needed", "An operator needs to be pulled out.",
        "high", SIREN, ping_owner=True, ping_lynx=True, ping_arceus=True,
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
        "high", EYES, ping_owner=True, ping_lynx=True, ping_arceus=True,
        # Nothing is posted in open chat: naming a suspected spy where the spy
        # can read it defeats the point. The alert goes to a private room and
        # the trigger message is removed.
        room=True, silence=True,
        response=(
            "**Code 8 — suspected spy.** "
            "This room exists so the alert never appears in open chat. "
            "Nobody say anything sensitive in the main channel until it is "
            "cleared. Watch who reacts and who goes quiet."
        ),
        aliases=("suspected spy", "there's a spy", "theres a spy", "we have a spy"),
    ),
    9: Code(
        9, "Cover blown", "Identity is exposed; evacuate the operation.",
        "critical", SIREN, ping_owner=True, ping_lynx=True, ping_arceus=True, silence=True, ops=True,
        purge_seconds=300,
        response=(
            "**Code 9 — cover blown.** Evacuate. Stop posting here. "
            "Operators pinged and the trigger message has been removed."
        ),
        aliases=("cover blown",),
    ),
    10: Code(
        10, "Getting found out", "The sender believes they are being discovered.",
        "critical", SIREN, ping_owner=True, ping_lynx=True, ping_arceus=True, silence=True, ops=True,
        response=(
            "**Code 10 — operator is being found out.** "
            "Message removed. @here is not pinged; operators, check your DMs "
            "and assume this channel is watched. Do not reply to the sender here."
        ),
        aliases=("getting found out", "im getting found out", "i'm getting found out"),
    ),
    11: Code(
        11, "Dyllan's back", "Dyllan has returned to the server.",
        "high", EYES, ping_owner=True, ping_lynx=True, ping_arceus=True, ops=True, arm_watch=True,
        response=(
            "**Code 11 - Dyllan's back.** The watch is armed. Every message he "
            "sends is now logged here and screened. Operators pinged."
        ),
        aliases=("dyllans back", "dyllan's back", "dyllan is back", "dyllan back",
                 "mysterious stranger is back", "ms is back"),
    ),
    12: Code(
        12, "Full lockdown", "Lock the channel and stop all traffic.",
        "critical", SIREN, ping_owner=True, ping_lynx=True, ping_arceus=True, silence=True, ops=True,
        response="**Code 12 — lockdown.** Channel locked, traffic stopped.",
        aliases=("full lockdown",),
    ),
    13: Code(
        13, "Raid incoming", "A join wave is starting or already underway.",
        "critical", SIREN, ping_owner=True, ping_lynx=True, ping_arceus=True, ops=True,
        response=(
            "**Code 13 — raid incoming.** Raise verification and stop inviting. "
            "Auto-lockdown will trigger on its own if joins keep landing."
        ),
        aliases=("raid incoming", "raid", "we're getting raided"),
    ),
    14: Code(
        14, "Leak", "Server content is being copied out.",
        "critical", SIREN, ping_owner=True, ping_lynx=True, ping_arceus=True, silence=True, ops=True,
        purge_seconds=600,
        response=(
            "**Code 14 — leak.** Screenshots or files are leaving the server. "
            "Trigger removed and the sender's recent messages purged. "
            "Operators, check who has been downloading."
        ),
        aliases=("leak", "we have a leak", "leaking"),
    ),
    15: Code(
        15, "Impersonation", "Someone is posing as an operator or the bot.",
        "high", EYES, ping_owner=True, ping_lynx=True, ping_arceus=True, ops=True,
        response=(
            "**Code 15 — impersonation.** Check display names, avatars and role "
            "colours. Real operators will not DM you first."
        ),
        aliases=("impersonation", "someone is impersonating", "fake operator"),
    ),
    16: Code(
        16, "Admin abuse", "A staff account is acting against the server.",
        "critical", SIREN, ping_owner=True, ping_lynx=True, ping_arceus=True, ops=True,
        response=(
            "**Code 16 — admin abuse.** Stop granting roles. Review the audit "
            "log and pull the account's permissions before anything else."
        ),
        aliases=("admin abuse", "rogue admin", "staff is compromised"),
    ),
    17: Code(
        17, "DM compromise", "An operator's direct messages are exposed.",
        "critical", SIREN, ping_owner=True, ping_lynx=True, ping_arceus=True, silence=True, ops=True,
        response=(
            "**Code 17 — DM compromise.** Assume every private conversation is "
            "readable. Rotate the token, then change passwords."
        ),
        aliases=("dm compromise", "dms are compromised", "account compromised"),
    ),
    18: Code(
        18, "Evidence secured", "Proof has been saved; it is safe to move on.",
        "low", WHITE_CHECK, ping_owner=True, ping_lynx=True,
        response="Evidence secured. Nothing further needed here.",
        aliases=("evidence secured", "evidence saved", "proof secured"),
    ),
    19: Code(
        19, "Radio silence", "Nobody posts until an operator clears it.",
        "high", "🔇", ping_owner=True, ping_lynx=True, ping_arceus=True,
        silence=True, ops=True,
        response=(
            "**Code 19 — radio silence.** Stop posting in open chat. Operators "
            "will clear it with code 1."
        ),
        aliases=("radio silence", "stop posting", "everyone stop talking"),
    ),
    20: Code(
        20, "Server compromised", "The guild itself may be under someone else's control.",
        "critical", SIREN, ping_owner=True, ping_lynx=True, ping_arceus=True, ops=True,
        response=(
            "**Code 20 — server compromised.** Treat every staff account as "
            "hostile. Owner: verify your 2FA and active sessions now."
        ),
        aliases=("server compromised", "server is compromised", "guild compromised"),
    ),
}

# One pass covers digits, roman numerals and spelled-out numbers. Three
# separate patterns used to mean three full scans of every message.
_CODE_PATTERN = re.compile(
    r"\bcode\s*[-:#]?\s*(\d{1,3}"
    r"|i{1,3}|iv|vi{0,3}|ix|xi{0,2}|x"
    r"|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b",
    re.I,
)


# Leet spellings of the word "code" only. Folding digits across the whole
# message would turn "code 10" into "code io", so the number is left alone.
_LEET_CODE = re.compile(
    r"\b[ck][\s._*~|/-]*[o0][\s._*~|/-]*d[\s._*~|/-]*[e3]\b", re.I)


def _normalise(text: str) -> str:
    return re.sub(r"[\u2018\u2019]", "'", text.lower())


def _code_number(token: str) -> int | None:
    """Turn the captured token (digit, roman or word) into a code number."""
    if token.isdigit():
        return int(token)
    return _ROMAN.get(token) or _WORD_NUMBERS.get(token)


def _first_code(text: str, codes: dict[int, "Code"]) -> Hit | None:
    for match in _CODE_PATTERN.finditer(text):
        number = _code_number(match.group(1).lower())
        if number in codes:
            return Hit(codes[number], "number", match.group(0))
    return None


def _loose(text: str) -> str:
    """A de-obfuscated copy, used only when the plain form finds nothing.

    People type codes in a hurry and Discord users obfuscate words to dodge
    filters, so `c0de 8`, `cod3 8` and `c o d e 8` all mean the same thing. The
    copy folds lookalike characters and strips separators between single
    characters, which leaves normal sentences intact.
    """
    # "c0de", "cod3", "c0d3", "kode", "c o d e", "c.o.d.e" -> "code".
    return _LEET_CODE.sub("code", text)


@dataclass
class Hit:
    code: Code
    trigger: str
    matched_text: str


@dataclass
class Codebook:
    codes: dict[int, Code] = field(default_factory=lambda: dict(DEFAULT_CODES))
    _alias_index: dict[str, int] = field(default_factory=dict, repr=False)
    _alias_re: re.Pattern[str] | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self._rebuild_aliases()

    def _rebuild_aliases(self) -> None:
        index: dict[str, int] = {}
        for code in self.codes.values():
            for alias in code.aliases:
                index[_normalise(alias)] = code.number
        self._alias_index = index
        # Compiling one alternation turns 48 regex searches per message into a
        # single scan. Longest alias first so the more specific phrase wins at
        # the same starting position.
        ordered = sorted(index, key=len, reverse=True)
        self._alias_re: re.Pattern[str] | None = (
            re.compile(r"(?<!\w)(?:" + "|".join(re.escape(a) for a in ordered) + r")(?!\w)")
            if ordered else None
        )

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
                ops=bool(entry.get("ops", base.ops if base else False)),
                arm_watch=bool(entry.get("arm_watch", base.arm_watch if base else False)),
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
        # "code" has to appear before any pattern can match, so a substring
        # test skips the regex entirely for ordinary chatter.
        lowered = _normalise(text)
        if "code" in lowered:
            hit = _first_code(lowered, self.codes)
            if hit is not None:
                return hit

        if self._alias_re is not None:
            match = self._alias_re.search(lowered)
            if match is not None:
                alias = match.group(0)
                number = self._alias_index.get(alias)
                if number in self.codes:
                    return Hit(self.codes[number], "phrase", alias)

        # Nothing matched plainly, so try the de-obfuscated form. This costs an
        # extra pass but only on messages that did not already trigger, and it
        # closes the "c0de 8" hole that a plain scan walks straight past.
        loose = _loose(lowered)
        return _first_code(loose, self.codes) if loose != lowered else None

    def get(self, number: int) -> Code | None:
        return self.codes.get(number)

    def listing(self) -> list[Code]:
        return [self.codes[n] for n in sorted(self.codes)]


def render_alert(hit: Hit, author_id: int, author_name: str,
                 owner_id: int, arceus_id: int, extra_pings: list[str],
                 lynx_id: int = 0) -> str:
    """Build the alert body for a triggered code."""
    code = hit.code
    pings = list(extra_pings)
    if code.ping_owner:
        pings.append(f"<@{owner_id}>")
    if code.ping_arceus:
        pings.append(f"<@{arceus_id}>")
    if code.ping_lynx and lynx_id:
        pings.append(f"<@{lynx_id}>")
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
