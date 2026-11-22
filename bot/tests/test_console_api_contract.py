"""The Android app reads these endpoints, so their shape is a contract.

A missing key does not crash Kotlin's `optString`, it silently renders blank,
which is why the shape is asserted here rather than left to the app.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from freehands.events import EventLog

REQUIRED_ROW = {
    "seq", "type", "at", "channel", "author", "text",
    "before", "media", "platforms", "message_id",
}
REQUIRED_AUTHOR = {"id", "name"}


def _log() -> EventLog:
    return EventLog(Path(tempfile.mkdtemp()) / "events.jsonl")


class RecordShapeTest(unittest.TestCase):
    def test_a_message_row_has_every_key_the_app_reads(self):
        log = _log()
        row = log.message({"id": "1", "channel_id": "2", "content": "hi",
                           "author": {"id": "3", "username": "z"}})
        self.assertLessEqual(REQUIRED_ROW, set(row))
        self.assertLessEqual(REQUIRED_AUTHOR, set(row["author"]))

    def test_a_delete_row_has_every_key_the_app_reads(self):
        log = _log()
        log.message({"id": "1", "channel_id": "2", "content": "hi",
                     "author": {"id": "3", "username": "z"}})
        row = log.deleted({"id": "1", "channel_id": "2"}, log.find_message("1"))
        self.assertLessEqual(REQUIRED_ROW, set(row))

    def test_an_edit_row_has_every_key_the_app_reads(self):
        log = _log()
        row = log.edited({"id": "1", "channel_id": "2", "content": "new",
                          "author": {"id": "3", "username": "z"}}, "old")
        self.assertLessEqual(REQUIRED_ROW, set(row))
        self.assertEqual(row["before"], "old")

    def test_a_presence_row_has_every_key_the_app_reads(self):
        log = _log()
        row = log.presence({"user": {"id": "3", "username": "z"},
                            "status": "online", "client_status": {"web": "online"}})
        self.assertLessEqual(REQUIRED_ROW, set(row))
        self.assertEqual(row["platforms"], ["web"])

    def test_every_row_is_json_serialisable(self):
        log = _log()
        log.message({"id": "1", "channel_id": "2", "content": "hi",
                     "author": {"id": "3"}, "attachments": [{"url": "u"}]})
        log.presence({"user": {"id": "3"}, "client_status": {"web": "online"}})
        for row in log.recent():
            json.dumps(row)

    def test_media_entries_always_carry_kind_url_and_name(self):
        log = _log()
        row = log.message({"id": "1", "channel_id": "2", "author": {"id": "3"},
                           "attachments": [{"url": "u"}]})
        self.assertLessEqual({"kind", "url", "name"}, set(row["media"][0]))


if __name__ == "__main__":
    unittest.main()


class StatusCachingTest(unittest.TestCase):
    """The app polls status every few seconds; identity must not hit REST each time."""

    def test_identity_is_resolved_once(self):
        import sys
        from pathlib import Path as P

        sys.path.insert(0, str(P(__file__).resolve().parents[1]))
        from freehands.console import BotApi

        class Rest:
            calls = 0

            def me(self):
                Rest.calls += 1
                return {"id": "1", "username": "Freehands"}

        class Settings:
            def to_json(self):
                return {}

        class Events:
            def counts(self):
                return {}

        class Engine:
            rest = Rest()
            settings = Settings()
            events = Events()

        api = BotApi(Engine())
        for _ in range(5):
            api.status()
        self.assertEqual(Rest.calls, 1)
        self.assertEqual(api.identity(), {"id": "1", "name": "Freehands"})
