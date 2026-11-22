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


class NewPanelContractTest(unittest.TestCase):
    """The loop and owner panels read these keys. A missing one renders blank."""

    def _api(self):
        from freehands.console import BotApi
        from freehands.loops import Loops
        from freehands.owner_powers import OwnerPowers

        class Rest:
            def members(self, guild_id, limit=1000):
                return [{
                    "user": {"id": "1002131928775925840", "username": "lynx"},
                    "roles": [],
                }]

        class Settings:
            def to_json(self):
                return {}

        class Events:
            def counts(self):
                return {}

        class Pairing:
            devices = {}

            def verify(self, token):
                return None

        class Engine:
            rest = Rest()
            settings = Settings()
            events = Events()
            pairing = Pairing()

        engine = Engine()
        engine.loops = Loops(engine.rest)
        engine.powers = OwnerPowers(engine)
        return BotApi(engine)

    def test_people_carries_every_key_the_dropdown_reads(self):
        rows = self._api().people()["people"]
        self.assertEqual(len(rows), 1)
        self.assertLessEqual(
            {"id", "name", "display", "tier", "label", "avatar",
             "protected", "reason"},
            set(rows[0]),
        )
        self.assertTrue(rows[0]["protected"], "Lynx must be marked protected")

    def test_loops_carries_every_key_the_list_reads(self):
        api = self._api()
        self.assertEqual(api.loops(), {"loops": []})
        api.engine.loops.arm("ban", "555", "x", 600, 2, "1")
        row = api.loops()["loops"][0]
        self.assertLessEqual(
            {"id", "kind", "target", "reason", "interval", "passes",
             "fired", "running", "stopped", "last_error"},
            set(row),
        )
        api.engine.loops.stop_all()

    def test_the_owner_panel_carries_every_key_the_sheet_reads(self):
        from freehands.config import LYNX_ID
        status, payload = self._api().owner_panel(str(LYNX_ID))
        self.assertEqual(status, 200)
        self.assertLessEqual(
            {"key", "name", "blurb", "kind", "confirm", "on"},
            set(payload["powers"][0]),
        )

    def test_a_non_lynx_caller_is_refused_by_the_endpoint(self):
        status, payload = self._api().owner_panel("123")
        self.assertEqual(status, 403)
        self.assertFalse(payload["ok"])

    def test_arming_a_loop_from_the_endpoint_refuses_lynx_as_a_target(self):
        from freehands.config import LYNX_ID
        status, payload = self._api().arm_loop(
            {"kind": "ban", "target": str(LYNX_ID), "passes": 2}, str(LYNX_ID)
        )
        self.assertEqual(status, 403)
        self.assertFalse(payload["ok"])

    def test_arming_a_loop_from_the_endpoint_refuses_a_non_lynx_actor(self):
        status, payload = self._api().arm_loop(
            {"kind": "ban", "target": "555", "passes": 2}, "123"
        )
        self.assertEqual(status, 403)
        self.assertFalse(payload["ok"])
