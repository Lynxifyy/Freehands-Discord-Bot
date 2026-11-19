"""Behaviour tests for the engine.

A `FakeRest` stands in for the HTTP layer — the only external boundary — so the
real routing, permission, code and auto-mod code paths run exactly as they do
in production.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from freehands.codebook import Codebook
from freehands.config import (
    ARCEUS_ID,
    BOT_ID,
    GUILD_ID,
    LYNX_ID,
    MAIN_CHAT_ID,
    OWNER_ID,
    ROLE_MOD,
    ROLE_ETERNAL,
    WATCH_ID,
)
from freehands.engine import Engine
from freehands.moderation import RoleInfo
from freehands.store import Store


class FakeRest:
    """In-memory stand-in for `freehands.rest.Rest`."""

    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.replies: list[dict] = []
        self.deleted: list[tuple[int, int]] = []
        self.reactions: list[tuple[int, int, str]] = []
        self.timeouts: list[tuple[int, int]] = []
        self.unbans: list[int] = []
        self.ban_calls: list[tuple[int, str | None]] = []
        self.role_removed: list[tuple[int, int]] = []
        self.role_added: list[tuple[int, int]] = []
        self.members: dict[int, dict] = {}
        self.ban_rows: list[dict] = []
        self.audit_rows: list[dict] = []
        self.status = 204

    # -- reads ------------------------------------------------------------
    def me(self):
        return {"id": str(BOT_ID), "username": "Freehands"}

    def member(self, guild_id, user_id):
        row = self.members.get(user_id)
        return row

    def bans(self, guild_id):
        return self.ban_rows

    def audit(self, guild_id, action_type, limit=25):
        return self.audit_rows

    def messages(self, channel_id, limit=50, after=None):
        return []

    # -- writes -----------------------------------------------------------
    def send(self, channel_id, content="", **extra):
        self.sent.append({"channel": channel_id, "content": content, **extra})
        return {"id": str(len(self.sent)), "channel_id": str(channel_id)}

    def reply(self, channel_id, message_id, content, **extra):
        self.replies.append({"channel": channel_id, "to": message_id, "content": content, **extra})
        return {"id": str(len(self.replies))}

    def delete(self, channel_id, message_id):
        self.deleted.append((channel_id, message_id))
        return self.status

    def react(self, channel_id, message_id, emoji):
        self.reactions.append((channel_id, message_id, emoji))
        return self.status

    def typing(self, channel_id):
        return self.status

    def timeout(self, guild_id, user_id, seconds, reason=None):
        self.timeouts.append((user_id, seconds))
        return self.status

    def untimeout(self, guild_id, user_id, reason=None):
        return self.status

    def ban(self, guild_id, user_id, reason=None, delete_seconds=0):
        self.ban_calls.append((user_id, reason))
        return self.status

    def unban(self, guild_id, user_id, reason=None):
        self.unbans.append(user_id)
        return self.status

    def kick(self, guild_id, user_id, reason=None):
        return self.status

    def add_role(self, guild_id, user_id, role_id, reason=None):
        self.role_added.append((user_id, role_id))
        return self.status

    def remove_role(self, guild_id, user_id, role_id, reason=None):
        self.role_removed.append((user_id, role_id))
        return self.status

    def try_request(self, method, route, body=None, **kw):
        return self.status, None


def build_engine(tmp: str) -> tuple[Engine, FakeRest]:
    rest = FakeRest()
    store = Store(Path(tmp) / "state.json")
    engine = Engine(rest, store, Codebook())
    # The bot outranks everything in these fixtures unless a test says otherwise.
    engine.mod.roles = {
        1234: RoleInfo(1234, "1234", 1, False, 0),
        ROLE_ETERNAL: RoleInfo(ROLE_ETERNAL, "Eternal", 1, False, 0),
    }
    engine.mod.bot_top = 100
    return engine, rest


def message(user_id: int, content: str, message_id: int = 1,
            roles: list[int] | None = None) -> dict:
    return {
        "id": str(message_id),
        "channel_id": str(MAIN_CHAT_ID),
        "content": content,
        "author": {"id": str(user_id), "username": "tester", "bot": False},
        "member": {"roles": [str(r) for r in (roles or [])]},
    }


class CodeAlertTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine, self.rest = build_engine(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_code_8_alerts_and_pings_owner_and_arceus(self):
        self.engine.on_message(message(LYNX_ID, "code 8"))
        self.assertEqual(len(self.rest.sent), 1)
        body = self.rest.sent[0]["content"]
        self.assertIn("CODE 8", body)
        self.assertIn(f"<@{OWNER_ID}>", body)
        self.assertIn(f"<@{ARCEUS_ID}>", body)
        self.assertIn("\N{EYES}", body)
        mentions = self.rest.sent[0]["allowed_mentions"]
        self.assertIn(str(OWNER_ID), mentions["users"])
        self.assertIn(str(ARCEUS_ID), mentions["users"])

    def test_code_10_deletes_the_trigger_message(self):
        self.engine.on_message(message(LYNX_ID, "code 10", message_id=99))
        self.assertIn((MAIN_CHAT_ID, 99), self.rest.deleted)
        self.assertIn("GETTING FOUND OUT", self.rest.sent[0]["content"])

    def test_low_severity_code_does_not_ping(self):
        self.engine.on_message(message(LYNX_ID, "code 1"))
        mentions = self.rest.sent[0]["allowed_mentions"]["users"]
        self.assertNotIn(str(OWNER_ID), mentions)

    def test_incident_is_recorded(self):
        self.engine.on_message(message(LYNX_ID, "code 8"))
        self.assertEqual(self.engine.store.incidents[-1]["code"], 8)

    def test_bot_ignores_itself(self):
        row = message(BOT_ID, "code 8")
        row["author"]["bot"] = True
        self.engine.on_message(row)
        self.assertEqual(self.rest.sent, [])

    def test_code_sense_can_be_disabled(self):
        self.engine.settings.codes_enabled = False
        self.engine.on_message(message(LYNX_ID, "code 8"))
        self.assertEqual(self.rest.sent, [])

    def test_code_12_locks_the_channel(self):
        locked: list[bool] = []
        self.engine.mod.set_channel_locked = lambda cid, state: locked.append(state) or True
        self.engine.on_message(message(LYNX_ID, "code 12"))
        self.assertEqual(locked, [True])


class PermissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine, self.rest = build_engine(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_plain_member_cannot_use_owner_command(self):
        self.engine.on_message(message(5555, "+antiban off"))
        self.assertTrue(any("permission" in r["content"] for r in self.rest.replies))
        self.assertTrue(self.engine.settings.anti_ban)

    def test_owner_can_toggle_antiban(self):
        self.engine.on_message(message(OWNER_ID, "+antiban off"))
        self.assertFalse(self.engine.settings.anti_ban)

    def test_mod_role_grants_mod_tier(self):
        self.engine.on_message(message(5555, "+strikes", roles=[ROLE_MOD]))
        self.assertTrue(self.rest.replies)
        self.assertNotIn("permission", self.rest.replies[-1]["content"])

    def test_unknown_command_suggests(self):
        self.engine.on_message(message(OWNER_ID, "+antibna"))
        self.assertIn("antiban", self.rest.replies[-1]["content"])

    def test_ban_is_refused_while_antiban_armed(self):
        self.engine.on_message(message(OWNER_ID, "+ban <@777777777777777777>"))
        self.assertIn("anti-ban", self.rest.replies[-1]["content"])
        self.assertEqual(self.rest.ban_calls, [])

    def test_ban_works_when_antiban_disarmed(self):
        self.engine.settings.anti_ban = False
        self.engine.on_message(message(OWNER_ID, "+ban <@777777777777777777> spam"))
        self.assertEqual(self.rest.ban_calls[0][0], 777777777777777777)

    def test_keepbanned_add(self):
        self.engine.on_message(message(OWNER_ID, "+keepbanned add <@888888888888888888>"))
        self.assertIn(888888888888888888, self.engine.settings.keep_banned)

    def test_help_lists_codes(self):
        self.engine.on_message(message(5555, "+help"))
        body = self.rest.replies[-1]["content"]
        self.assertIn("Suspected spy", body)
        self.assertIn("+ping", body)


class AutomodTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine, self.rest = build_engine(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_slur_is_a_warning(self):
        self.engine.on_message(message(4444, "you n1gga"))
        self.assertEqual(self.rest.timeouts, [])
        self.assertIn("Strike 1", self.rest.replies[-1]["content"])

    def test_second_slur_times_out(self):
        self.engine.on_message(message(4444, "you n1gga"))
        self.engine.on_message(message(4444, "n1gga again", message_id=2))
        self.assertEqual(self.rest.timeouts[0][0], 4444)
        self.assertIn("Strike 2", self.rest.replies[-1]["content"])

    def test_third_slur_asks_operators(self):
        for index in range(3):
            self.engine.on_message(message(4444, "n1gga", message_id=index + 1))
        self.assertIn(f"<@{LYNX_ID}>", self.rest.replies[-1]["content"])
        self.assertIn(f"<@{ARCEUS_ID}>", self.rest.replies[-1]["content"])
        self.assertIn("slur", self.engine.store.questions)

    def test_exempt_member_is_not_struck(self):
        self.engine.on_message(message(LYNX_ID, "n1gga"))
        self.assertEqual(self.rest.replies, [])

    def test_invite_is_deleted(self):
        self.engine.on_message(message(4444, "join discord.gg/abc"))
        self.assertEqual(self.rest.deleted[0][1], 1)

    def test_spam_timeout(self):
        for index in range(self.engine.settings.spam_limit):
            self.engine.on_message(message(4444, "spam", message_id=index + 1))
        self.assertTrue(self.rest.timeouts)

    def test_punish_requires_bot_mention(self):
        self.engine.on_message(message(LYNX_ID, "punish dyllan"))
        self.assertEqual(self.rest.timeouts, [])
        self.engine.on_message(message(LYNX_ID, f"<@{BOT_ID}> punish dyllan", message_id=2))
        self.assertEqual(self.rest.timeouts[0][0], WATCH_ID)

    def test_punish_from_non_operator_is_ignored(self):
        self.engine.on_message(message(4444, f"<@{BOT_ID}> punish dyllan"))
        self.assertEqual(self.rest.timeouts, [])

    def test_three_punishments_start_a_lock_vote(self):
        self.engine.settings.punish_strikes_to_lock = 2
        self.engine.on_message(message(LYNX_ID, f"<@{BOT_ID}> punish dyllan", message_id=1))
        self.engine.on_message(message(LYNX_ID, f"<@{BOT_ID}> punish dyllan", message_id=2))
        self.assertIn("lockvote", self.engine.store.questions)

    def test_automod_off_lets_slurs_through(self):
        self.engine.settings.moderation_enabled = False
        self.engine.on_message(message(4444, "n1gga"))
        self.assertEqual(self.rest.replies, [])


class AntiBanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine, self.rest = build_engine(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_sweep_lifts_bans_but_respects_keep_banned(self):
        self.engine.settings.keep_banned = {9001}
        self.rest.ban_rows = [
            {"user": {"id": "111", "username": "a"}},
            {"user": {"id": "9001", "username": "veil"}},
        ]
        lifted = self.engine.mod.anti_ban_sweep()
        self.assertEqual(lifted, [111])
        self.assertEqual(self.rest.unbans, [111])

    def test_keep_banned_is_reapplied(self):
        self.engine.settings.keep_banned = {9001}
        self.rest.ban_rows = []
        applied = self.engine.mod.enforce_keep_banned()
        self.assertEqual(applied, [9001])

    def test_event_ban_is_reversed(self):
        self.engine.on_ban_add({"user": {"id": "222"}})
        self.assertEqual(self.rest.unbans, [222])
        self.assertIn("Anti-ban reversed", self.rest.sent[-1]["content"])

    def test_known_ban_is_not_reversed(self):
        self.engine.store.known_bans = {222}
        self.engine.on_ban_add({"user": {"id": "222"}})
        self.assertEqual(self.rest.unbans, [])

    def test_antiban_off_leaves_bans_alone(self):
        self.engine.settings.anti_ban = False
        self.engine.on_ban_add({"user": {"id": "222"}})
        self.assertEqual(self.rest.unbans, [])

    def test_seed_known_bans(self):
        self.rest.ban_rows = [{"user": {"id": "333", "username": "c"}}]
        self.engine.mod.seed_known_bans()
        self.assertEqual(self.engine.store.known_bans, {333})


class RoleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine, self.rest = build_engine(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_strip_keeps_eternal(self):
        self.rest.members[4444] = {
            "user": {"username": "t"}, "roles": [str(ROLE_ETERNAL), "1234"],
        }
        removed, skipped = self.engine.mod.strip_roles(4444)
        self.assertEqual(removed, ["1234"])
        self.assertEqual(skipped, ["Eternal"])

    def test_managed_role_is_skipped(self):
        self.engine.mod.roles[1234] = RoleInfo(1234, "bot-role", 1, True, 0)
        self.rest.members[4444] = {"user": {"username": "t"}, "roles": ["1234"]}
        removed, skipped = self.engine.mod.strip_roles(4444, keep=())
        self.assertEqual(removed, [])
        self.assertEqual(skipped, ["bot-role (above bot)"])

    def test_snapshot_then_restore(self):
        self.rest.members[4444] = {"user": {"username": "t"}, "roles": ["1234"]}
        self.engine.mod.snapshot(4444)
        self.assertEqual(self.engine.store.snapshots["4444"], [1234])
        added, _ = self.engine.mod.restore(4444)
        self.assertEqual(added, ["1234"])
        self.assertIn((4444, 1234), self.rest.role_added)


if __name__ == "__main__":
    unittest.main(verbosity=2)
