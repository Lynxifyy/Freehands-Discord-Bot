"""`+test` must report the truth about each subsystem, including failures.

The value of this command is that a broken part is named instead of hidden, so
the tests drive both the healthy path and a failing one.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from freehands import test_command
from freehands.rest import RestError

from .test_engine import LYNX_ID, build_engine


class TestCommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine, self.rest = build_engine(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_test(self) -> str:
        test_command.run(self.engine, None, LYNX_ID, 1, 1234, set())
        return self.rest.replies[-1]["content"]

    def test_a_healthy_bot_reports_every_check_passing(self):
        body = self.run_test()
        self.assertIn("All checks passed", body)
        self.assertNotIn("FAIL", body)

    def test_every_check_is_named_so_a_failure_is_locatable(self):
        body = self.run_test()
        for name, _ in test_command.CHECKS:
            self.assertIn(name, body)

    def test_a_rejected_token_is_reported_as_a_failure_not_an_exception(self):
        def boom(*a, **kw):
            raise RestError(401, "Unauthorized", "/users/@me")
        self.rest.me = boom
        body = self.run_test()
        self.assertIn("FAIL  discord", body)
        self.assertIn("401", body)
        # The other checks must still have run.
        self.assertIn("OK    commands", body)
        self.assertNotIn("All checks passed", body)

    def test_the_summary_counts_passes(self):
        def boom(*a, **kw):
            raise RestError(500, "boom", "/x")
        self.rest.bans = boom
        body = self.run_test()
        self.assertIn(f"{len(test_command.CHECKS) - 1}/{len(test_command.CHECKS)}", body)

    def test_a_non_rest_exception_is_caught_too(self):
        def boom():
            raise RuntimeError("unexpected")
        self.rest.me = boom
        body = self.run_test()
        self.assertIn("RuntimeError", body)

    def test_pairing_count_is_reported(self):
        self.engine.pairing.open("x")
        self.engine.pairing.claim("", paired_by="1")  # no such code, no device
        body = self.run_test()
        self.assertIn("0 paired consoles", body)
