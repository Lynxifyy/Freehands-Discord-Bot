"""What the console shows when a message is deleted.

A delete event carries two ids and nothing else. Everything a reader wants -
what was said, who said it, who removed it - has to be reconstructed, and it
was reconstructed wrongly before: the console labelled the *author* slot, which
a delete event never fills, so every row read "unknown deleted a message".
"""

from __future__ import annotations

import tempfile
import unittest

from freehands.config import BOT_ID, MAIN_CHAT_ID
from freehands.store import Store
from freehands.codebook import Codebook
from freehands.engine import Engine

from .test_engine import FakeRest, message

SAID_BY = 444555666777888999
DELETED_BY = 111222333444555666


def build(tmp: str):
    rest = FakeRest()
    engine = Engine(rest, Store(__import__("pathlib").Path(tmp) / "state.json"), Codebook())
    return engine, rest


class DeleteAttributionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.engine, self.rest = build(self.tmp)

    def _rows(self, kind: str = "delete"):
        return [r for r in self.engine.events.recent(limit=100) if r["type"] == kind]

    def test_the_deleted_text_survives(self):
        """The message is gone from Discord, so our copy is the only record."""
        self.engine.on_message(message(SAID_BY, "the secret plan is at noon", message_id=7))
        self.engine.on_message_delete({"id": "7", "channel_id": str(MAIN_CHAT_ID)})

        row = self._rows()[-1]
        self.assertEqual(row["text"], "the secret plan is at noon")
        self.assertEqual(row["author"]["id"], str(SAID_BY))

    def test_the_deleter_is_named_from_the_audit_log(self):
        """The gateway never says who deleted; the audit log does."""
        self.engine.on_message(message(SAID_BY, "something", message_id=7))
        self.rest.audit_rows = [
            {"target_id": "7", "user": {"id": str(DELETED_BY)}, "action_type": 72},
        ]
        self.engine.on_message_delete({"id": "7", "channel_id": str(MAIN_CHAT_ID)})

        row = self._rows()[-1]
        self.assertEqual(row["actor"]["id"], str(DELETED_BY))
        self.assertIn(str(DELETED_BY), row["actor"]["name"])

    def test_the_author_and_the_deleter_are_kept_apart(self):
        """Two different people: confusing them is the bug this fixes."""
        self.engine.on_message(message(SAID_BY, "oops", message_id=7))
        self.rest.audit_rows = [
            {"target_id": "7", "user": {"id": str(DELETED_BY)}, "action_type": 72},
        ]
        self.engine.on_message_delete({"id": "7", "channel_id": str(MAIN_CHAT_ID)})

        row = self._rows()[-1]
        self.assertEqual(row["author"]["id"], str(SAID_BY))
        self.assertEqual(row["actor"]["id"], str(DELETED_BY))

    def test_a_bot_delete_is_labelled_as_automod(self):
        self.engine.on_message(message(SAID_BY, "join my server xyz", message_id=7))
        self.rest.audit_rows = [
            {"target_id": "7", "user": {"id": str(BOT_ID)}, "action_type": 72},
        ]
        self.engine.on_message_delete({"id": "7", "channel_id": str(MAIN_CHAT_ID)})

        self.assertIn("automod", self._rows()[-1]["actor"]["name"])

    def test_an_audit_entry_for_another_message_is_ignored(self):
        """The log is recent-first, so the first entry is usually not ours."""
        self.engine.on_message(message(SAID_BY, "mine", message_id=7))
        self.rest.audit_rows = [
            {"target_id": "999", "user": {"id": "1"}, "action_type": 72},
            {"target_id": "7", "user": {"id": str(DELETED_BY)}, "action_type": 72},
        ]
        self.engine.on_message_delete({"id": "7", "channel_id": str(MAIN_CHAT_ID)})

        self.assertEqual(self._rows()[-1]["actor"]["id"], str(DELETED_BY))

    def test_a_delete_of_a_message_we_never_saw_still_records(self):
        """A message older than our window must not produce an exception."""
        self.engine.on_message_delete({"id": "12345", "channel_id": str(MAIN_CHAT_ID)})
        row = self._rows()[-1]
        self.assertEqual(row["message_id"], "12345")
        self.assertEqual(row["text"], "")

    def test_media_on_a_deleted_message_is_kept(self):
        """Deleting the message does not delete the attachment record."""
        msg = message(SAID_BY, "look", message_id=7)
        msg["attachments"] = [{
            "url": "https://cdn.discordapp.com/attachments/1/2/photo.png",
            "filename": "photo.png", "content_type": "image/png", "size": 1234,
        }]
        self.engine.on_message(msg)
        self.engine.on_message_delete({"id": "7", "channel_id": str(MAIN_CHAT_ID)})

        media = self._rows()[-1]["media"]
        self.assertEqual(media[0]["url"], "https://cdn.discordapp.com/attachments/1/2/photo.png")

    def test_a_forbidden_audit_log_stops_being_asked(self):
        """A non-moderator bot gets 403 forever; retrying each delete is waste."""
        calls = {"n": 0}

        def boom(guild_id, action_type, limit=25):
            calls["n"] += 1
            raise RuntimeError("403 Forbidden")

        self.rest.audit = boom
        for mid in ("1", "2", "3"):
            self.engine.on_message_delete({"id": mid, "channel_id": str(MAIN_CHAT_ID)})

        self.assertEqual(calls["n"], 1, "the second delete must not retry a 403")
        self.assertEqual(len(self._rows()), 3, "every delete is still recorded")

    def test_the_console_row_carries_an_actor_field_even_when_empty(self):
        """Every record has the same keys, so the app reads one shape."""
        self.engine.on_message_delete({"id": "9", "channel_id": str(MAIN_CHAT_ID)})
        self.assertIn("actor", self._rows()[-1])
        self.assertEqual(self._rows()[-1]["actor"], {"id": "", "name": ""})


class DeleteRenderingTests(unittest.TestCase):
    """The API shape the app parses, exercised through the real endpoint."""

    def setUp(self) -> None:
        from freehands.console import BotApi

        self.tmp = tempfile.mkdtemp()
        self.engine, self.rest = build(self.tmp)
        self.api = BotApi(self.engine)

    def test_the_api_exposes_actor_separately_from_author(self):
        self.engine.on_message(message(SAID_BY, "removed", message_id=7))
        self.rest.audit_rows = [
            {"target_id": "7", "user": {"id": str(DELETED_BY)}, "action_type": 72},
        ]
        self.engine.on_message_delete({"id": "7", "channel_id": str(MAIN_CHAT_ID)})

        rows = self.api.log_rows(50, 0)["rows"]
        delete = [r for r in rows if r["type"] == "delete"][-1]
        self.assertEqual(delete["actor"]["id"], str(DELETED_BY))
        self.assertEqual(delete["author"]["id"], str(SAID_BY))
        self.assertEqual(delete["text"], "removed")


if __name__ == "__main__":
    unittest.main()
