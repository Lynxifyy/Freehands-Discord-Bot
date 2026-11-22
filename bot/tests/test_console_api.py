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


class TokenOptionalTest(unittest.TestCase):
    """A missing shared token is no longer fatal: devices pair themselves."""

    def test_main_starts_without_a_shared_token(self):
        old = os.environ.pop("FH_CONSOLE_TOKEN", None)
        old_start = console_api._start
        old_port = os.environ.get("FH_CONSOLE_PORT")
        console_api._start = lambda: {"ok": True, "skipped": True}
        os.environ["FH_CONSOLE_PORT"] = "0"
        try:
            self.assertEqual(console_api.main(serve=False), 0)
        finally:
            console_api._start = old_start
            if old is not None:
                os.environ["FH_CONSOLE_TOKEN"] = old
            if old_port is None:
                os.environ.pop("FH_CONSOLE_PORT", None)
            else:
                os.environ["FH_CONSOLE_PORT"] = old_port


class DeviceTokenTest(unittest.TestCase):
    """A paired device token authenticates exactly like the shared token."""

    def setUp(self):
        console_api._DEVICE_CACHE.clear()
        self._old_lookup = console_api._DEVICE_LOOKUP
        self._old_token = os.environ.pop("FH_CONSOLE_TOKEN", None)

    def tearDown(self):
        console_api._DEVICE_LOOKUP = self._old_lookup
        console_api._DEVICE_CACHE.clear()
        if self._old_token is not None:
            os.environ["FH_CONSOLE_TOKEN"] = self._old_token

    def _authed(self, header: str | None) -> bool:
        handler = console_api.Handler.__new__(console_api.Handler)
        handler.headers = {"Authorization": header} if header else {}
        return handler._authed()

    def test_a_valid_device_token_is_accepted(self):
        console_api._DEVICE_LOOKUP = lambda t: {"id": "abc"} if t == "dev-token" else None
        self.assertTrue(self._authed("Bearer dev-token"))

    def test_a_second_call_uses_the_cache(self):
        calls = []
        console_api._DEVICE_LOOKUP = lambda t: calls.append(t) or {"id": "abc"}
        self._authed("Bearer dev-token")
        self._authed("Bearer dev-token")
        self.assertEqual(len(calls), 1, "the device lookup should be cached")

    def test_a_rejected_token_is_not_rechecked_every_time(self):
        calls = []
        console_api._DEVICE_LOOKUP = lambda t: calls.append(t) or None
        self.assertFalse(self._authed("Bearer garbage"))
        self.assertFalse(self._authed("Bearer garbage"))
        self.assertEqual(len(calls), 1, "a miss should be cached too")

    def test_an_unknown_device_token_is_refused(self):
        console_api._DEVICE_LOOKUP = lambda t: None
        self.assertFalse(self._authed("Bearer nope"))


class PairRateLimitTest(unittest.TestCase):
    def setUp(self):
        console_api._PAIR_ATTEMPTS.clear()

    def test_attempts_are_limited_per_address(self):
        results = [console_api._pair_allowed("9.9.9.9") for _ in range(12)]
        self.assertTrue(all(results[:10]))
        self.assertFalse(any(results[10:]))

    def test_one_address_does_not_block_another(self):
        for _ in range(12):
            console_api._pair_allowed("9.9.9.9")
        self.assertTrue(console_api._pair_allowed("8.8.8.8"))


if __name__ == "__main__":
    unittest.main()
