"""The supervisor is the only public door to the bot, so its guards are tested."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import console_api  # noqa: E402


class AuthTest(unittest.TestCase):
    """`_authed` is exercised through the handler with a fake request."""

    def _handler(self, header: str | None, expected: str):
        class Fake:
            headers = {"Authorization": header} if header else {}

        handler = console_api.Handler.__new__(console_api.Handler)
        handler.headers = Fake.headers
        old = os.environ.get("FH_CONSOLE_TOKEN")
        os.environ["FH_CONSOLE_TOKEN"] = expected
        try:
            return handler._authed()
        finally:
            if old is None:
                os.environ.pop("FH_CONSOLE_TOKEN", None)
            else:
                os.environ["FH_CONSOLE_TOKEN"] = old

    def test_the_right_token_is_accepted(self):
        self.assertTrue(self._handler("Bearer s3cret", "s3cret"))

    def test_a_wrong_token_is_refused(self):
        self.assertFalse(self._handler("Bearer wrong", "s3cret"))

    def test_a_prefix_is_refused(self):
        self.assertFalse(self._handler("Bearer s3cre", "s3cret"))

    def test_a_longer_token_is_refused(self):
        self.assertFalse(self._handler("Bearer s3cretx", "s3cret"))

    def test_a_missing_header_is_refused(self):
        self.assertFalse(self._handler(None, "s3cret"))

    def test_an_empty_configured_token_never_authorises(self):
        self.assertFalse(self._handler("Bearer ", ""))

    def test_a_different_case_scheme_is_refused(self):
        self.assertFalse(self._handler("bearer s3cret", "s3cret"))


class PidTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._old_pidfile = console_api.PIDFILE
        console_api.PIDFILE = self.tmp / "freehands.pid"

    def tearDown(self):
        console_api.PIDFILE = self._old_pidfile

    def test_a_missing_pidfile_is_not_alive(self):
        self.assertIsNone(console_api._read_pid())

    def test_a_garbage_pidfile_is_not_alive(self):
        console_api.PIDFILE.write_text("not-a-number")
        self.assertIsNone(console_api._read_pid())

    def test_an_unrelated_pid_is_not_treated_as_the_bot(self):
        # This test process is not the bot, so a PID file naming it must not
        # resolve; otherwise stop would SIGTERM the wrong process.
        console_api.PIDFILE.write_text(str(os.getpid()))
        self.assertIsNone(console_api._read_pid())

    def test_a_stale_pidfile_is_cleaned_up(self):
        console_api.PIDFILE.write_text(str(os.getpid()))
        console_api._read_pid()
        self.assertFalse(console_api.PIDFILE.exists())

    def test_a_dead_pid_is_not_alive(self):
        console_api.PIDFILE.write_text("999999")
        self.assertIsNone(console_api._read_pid())


class TokenRequiredTest(unittest.TestCase):
    def test_main_refuses_without_a_token(self):
        old = os.environ.pop("FH_CONSOLE_TOKEN", None)
        try:
            self.assertEqual(console_api.main(), 2)
        finally:
            if old is not None:
                os.environ["FH_CONSOLE_TOKEN"] = old


if __name__ == "__main__":
    unittest.main()
