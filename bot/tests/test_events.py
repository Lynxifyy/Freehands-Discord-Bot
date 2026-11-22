"""The console feed must record what happened, and survive a restart."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from freehands.events import EventLog, _media


def _log() -> EventLog:
    return EventLog(Path(tempfile.mkdtemp()) / "events.jsonl")


class MediaTest(unittest.TestCase):
    def test_attachment_kinds_follow_the_content_type(self):
        rows = _media({"attachments": [
            {"url": "a", "content_type": "image/png"},
            {"url": "b", "content_type": "video/mp4"},
            {"url": "c", "content_type": "audio/ogg"},
            {"url": "d", "content_type": "application/pdf"},
        ]})
        self.assertEqual([r["kind"] for r in rows], ["image", "video", "audio", "file"])

    def test_stickers_become_a_cdn_link(self):
        rows = _media({"stickers": [{"id": "123", "name": "wave"}]})
        self.assertEqual(rows[0]["kind"], "sticker")
        self.assertIn("123", rows[0]["url"])
        self.assertTrue(rows[0]["url"].startswith("https://cdn.discordapp.com/stickers/"))

    def test_a_gif_embed_is_labelled_gif_not_embed(self):
        rows = _media({"embeds": [{"type": "gifv", "url": "https://x/y.gifv"}]})
        self.assertEqual(rows[0]["kind"], "gif")
        self.assertEqual(rows[0]["url"], "https://x/y.gifv")

    def test_a_plain_embed_falls_back_to_its_thumbnail(self):
        rows = _media({"embeds": [{"type": "link",
                                   "url": "https://x",
                                   "thumbnail": {"url": "https://x/t.png"}}]})
        self.assertEqual(rows[0]["url"], "https://x/t.png")

    def test_a_message_with_no_media_produces_nothing(self):
        self.assertEqual(_media({"content": "just text"}), [])


class EventLogTest(unittest.TestCase):
    def test_a_message_records_author_text_and_id(self):
        log = _log()
        row = log.message({"id": "9", "channel_id": "5", "content": "hello",
                           "author": {"id": "7", "username": "z"}})
        self.assertEqual(row["type"], "message")
        self.assertEqual(row["text"], "hello")
        self.assertEqual(row["author"]["name"], "z")
        self.assertEqual(row["message_id"], "9")

    def test_hydrated_content_wins_over_the_blank_gateway_field(self):
        log = _log()
        row = log.message({"id": "9", "content": "", "author": {"id": "7"}}, "recovered")
        self.assertEqual(row["text"], "recovered")

    def test_a_delete_carries_the_text_from_the_cache(self):
        log = _log()
        log.message({"id": "9", "channel_id": "5", "content": "said this",
                     "author": {"id": "7", "username": "z"}})
        row = log.deleted({"id": "9", "channel_id": "5"}, log.find_message("9"))
        self.assertEqual(row["type"], "delete")
        self.assertEqual(row["text"], "said this")
        self.assertEqual(row["author"]["name"], "z")

    def test_a_delete_for_an_unseen_message_still_records(self):
        log = _log()
        row = log.deleted({"id": "404", "channel_id": "5"}, None)
        self.assertEqual(row["type"], "delete")
        self.assertEqual(row["text"], "")

    def test_presence_records_where_the_user_is_online(self):
        log = _log()
        row = log.presence({"user": {"id": "7", "username": "z"},
                            "status": "online",
                            "client_status": {"desktop": "online", "mobile": "idle"}})
        self.assertEqual(row["type"], "presence")
        self.assertEqual(row["platforms"], ["desktop", "mobile"])

    def test_an_offline_client_is_not_listed(self):
        log = _log()
        row = log.presence({"user": {"id": "7"}, "status": "idle",
                            "client_status": {"web": "offline"}})
        self.assertEqual(row["platforms"], [])

    def test_recent_filters_by_sequence(self):
        log = _log()
        for i in range(5):
            log.message({"id": str(i), "content": f"m{i}", "author": {"id": "1"}})
        rows = log.recent(after=3)
        self.assertEqual([r["text"] for r in rows], ["m3", "m4"])

    def test_recent_respects_the_limit(self):
        log = _log()
        for i in range(10):
            log.message({"id": str(i), "content": f"m{i}", "author": {"id": "1"}})
        self.assertEqual(len(log.recent(limit=3)), 3)

    def test_counts_group_by_type(self):
        log = _log()
        log.message({"id": "1", "content": "a", "author": {"id": "1"}})
        log.message({"id": "2", "content": "b", "author": {"id": "1"}})
        log.deleted({"id": "1"}, None)
        self.assertEqual(log.counts(), {"message": 2, "delete": 1})

    def test_records_survive_a_reload_from_disk(self):
        path = Path(tempfile.mkdtemp()) / "events.jsonl"
        first = EventLog(path)
        first.message({"id": "1", "content": "kept", "author": {"id": "7", "username": "z"}})
        second = EventLog(path)
        self.assertEqual(second.recent()[0]["text"], "kept")

    def test_sequence_continues_after_a_reload(self):
        path = Path(tempfile.mkdtemp()) / "events.jsonl"
        EventLog(path).message({"id": "1", "content": "a", "author": {"id": "1"}})
        second = EventLog(path)
        row = second.message({"id": "2", "content": "b", "author": {"id": "1"}})
        self.assertEqual(row["seq"], 2)

    def test_a_corrupt_line_does_not_stop_the_reload(self):
        path = Path(tempfile.mkdtemp()) / "events.jsonl"
        path.write_text('{"seq":1,"type":"message","text":"ok"}\nnot json\n')
        log = EventLog(path)
        self.assertEqual(len(log.recent()), 1)

    def test_the_ring_is_bounded(self):
        log = _log()
        log._rows = type(log._rows)(maxlen=3)
        for i in range(10):
            log.message({"id": str(i), "content": f"m{i}", "author": {"id": "1"}})
        self.assertEqual(len(log.recent()), 3)

    def test_no_path_means_memory_only(self):
        log = EventLog(None)
        log.message({"id": "1", "content": "a", "author": {"id": "1"}})
        self.assertEqual(len(log.recent()), 1)

    def test_records_do_not_share_mutable_state(self):
        # A shared literal default would let one record's list edit another's.
        log = _log()
        first = log.message({"id": "1", "content": "a", "author": {"id": "1"}})
        second = log.message({"id": "2", "content": "b", "author": {"id": "1"}})
        third = log.deleted({"id": "9"}, None)
        self.assertIsNot(first["platforms"], second["platforms"])
        self.assertIsNot(first["platforms"], third["platforms"])
        self.assertIsNot(first["author"], second["author"])
        first["platforms"].append("web")
        self.assertEqual(second["platforms"], [])

    def test_old_rows_are_given_missing_fields_on_reload(self):
        path = Path(tempfile.mkdtemp()) / "events.jsonl"
        path.write_text('{"seq":1,"type":"message","text":"old"}\n')
        log = EventLog(path)
        row = log.recent()[0]
        self.assertEqual(row["platforms"], [])
        self.assertEqual(row["before"], "")
        self.assertIn("author", row)

    def test_file_lines_are_valid_json(self):
        path = Path(tempfile.mkdtemp()) / "events.jsonl"
        log = EventLog(path)
        log.message({"id": "1", "content": "a", "author": {"id": "1"}})
        for line in path.read_text().splitlines():
            json.loads(line)


if __name__ == "__main__":
    unittest.main()
