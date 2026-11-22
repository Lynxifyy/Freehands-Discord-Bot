"""End-to-end pairing over real HTTP.

The webview talks to the supervisor, the supervisor proxies to the bot, and the
bot binds the account. That is three processes' worth of contract in one flow,
and each hop has had a bug in it, so this test runs the real servers on real
sockets instead of mocking the boundary away.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import console_api  # noqa: E402
from freehands.console import BotApi  # noqa: E402


def _post(port: int, body: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/pair",
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


class PairFlowTest(unittest.TestCase):
    def setUp(self):
        from freehands.config import OWNER_ID
        from .test_engine import build_engine

        self.engine, self.rest = build_engine(tempfile.mkdtemp())
        self.rest.members[OWNER_ID] = {
            "user": {"id": str(OWNER_ID), "username": "gllober3_28957"},
            "roles": [],
        }
        self.bot = BotApi(self.engine, port=0)
        self.assertTrue(self.bot.start())
        self.bot_port = self.bot._server.server_address[1]
        self.supervisor = console_api.ThreadingHTTPServer(
            ("127.0.0.1", 0), console_api.Handler,
        )
        self.supervisor.daemon_threads = True
        import threading

        threading.Thread(
            target=self.supervisor.serve_forever, daemon=True,
        ).start()
        self.sup_port = self.supervisor.server_address[1]
        # The supervisor forwards to a fixed loopback port, so point it at the
        # bot instance this test started.
        self._old_bot_api = console_api.BOT_API
        console_api.BOT_API = f"http://127.0.0.1:{self.bot_port}"

    def tearDown(self):
        console_api.BOT_API = self._old_bot_api
        self.supervisor.shutdown()
        self.bot._server.shutdown()

    def _approve(self, code: str):
        from freehands.commands import parse
        from freehands.config import OWNER_ID

        self.engine.dispatch(parse(f"+pair {code}"), OWNER_ID, 1, 555, set())

    def test_the_webview_flow_ends_with_a_working_token(self):
        # 1. The page asks for a code.
        status, opened = _post(self.sup_port, {"action": "open", "name": "webview"})
        self.assertEqual(status, 200, opened)
        code = opened["code"]
        self.assertTrue(code)

        # 2. Polling before approval says pending, and grants nothing.
        status, pending = _post(self.sup_port, {"action": "poll", "code": code})
        self.assertEqual(status, 200)
        self.assertEqual(pending["status"], "pending")
        self.assertNotIn("token", pending)

        # 3. The human approves it in Discord.
        self._approve(code)

        # 4. The poll returns the credential and says who it is bound to.
        status, done = _post(self.sup_port, {"action": "poll", "code": code})
        self.assertEqual(status, 200)
        self.assertEqual(done["status"], "approved")
        token = done["token"]
        self.assertTrue(token)
        from freehands.config import OWNER_ID

        self.assertEqual(done["identity"]["id"], str(OWNER_ID))
        # The webview shows this, so it must be present and non-empty.
        self.assertTrue(done["identity"]["label"])

        # 5. That token really is a device credential.
        self.assertIsNotNone(self.engine.pairing.verify(token))

    def test_a_poll_before_anyone_opens_returns_404(self):
        status, body = _post(self.sup_port, {"action": "poll", "code": "ZZZZZZ"})
        self.assertEqual(status, 404, body)

    def test_the_public_route_refuses_an_unknown_action(self):
        status, body = _post(self.sup_port, {"action": "take_over"})
        self.assertEqual(status, 400, body)

    def test_an_unapproved_code_never_yields_a_token(self):
        _, opened = _post(self.sup_port, {"action": "open", "name": "webview"})
        for _ in range(3):
            status, body = _post(
                self.sup_port, {"action": "poll", "code": opened["code"]},
            )
            self.assertEqual(status, 200)
            self.assertNotIn("token", body)


if __name__ == "__main__":
    unittest.main()
