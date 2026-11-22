"""Minimal Discord gateway client.

A websocket hand-rolled on `socket`/`ssl` so the bot needs no third-party
package. Handles hello/heartbeat/identify/resume/reconnect and hands each
dispatched event to a callback on a worker thread.

Speed matters here: MESSAGE_CREATE arrives the moment it is sent, so a code or
a command lands in well under a second instead of waiting on a poll interval.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import ssl
import struct
import threading
import time
import urllib.parse

from .config import (
    INTENTS,
    INTENT_GUILD_MEMBERS,
    INTENT_GUILD_PRESENCES,
    INTENT_MESSAGE_CONTENT,
)
from .log import log

OP_DISPATCH = 0
OP_HEARTBEAT = 1
OP_IDENTIFY = 2
OP_RESUME = 6
OP_RECONNECT = 7
OP_INVALID_SESSION = 9
OP_HELLO = 10
OP_HEARTBEAT_ACK = 11

GATEWAY_HOST = "gateway.discord.gg"
GATEWAY_PATH = "/?v=10&encoding=json"


class GatewayClosed(Exception):
    pass


class Gateway:
    def __init__(self, token: str, on_event, on_ready=None,
                 intents: int = INTENTS) -> None:
        self.token = token
        self.on_event = on_event
        self.on_ready = on_ready
        self.intents = intents
        # True once a privileged intent had to be dropped; the engine uses it
        # to know message content must be hydrated over REST.
        self.reduced = False
        self.seq: int | None = None
        self.session_id: str | None = None
        self.resume_url: str | None = None
        self.alive = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="gateway", daemon=True)
        self._sock: ssl.SSLSocket | None = None
        self._write_lock = threading.Lock()

    # -- lifecycle --------------------------------------------------------
    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        sock = self._sock
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def is_alive(self) -> bool:
        return self._thread.is_alive() and self.alive.is_set()

    def wait_ready(self, timeout: float = 20.0) -> bool:
        return self.alive.wait(timeout)

    # -- framing ----------------------------------------------------------
    def _connect(self) -> ssl.SSLSocket:
        context = ssl.create_default_context()
        raw = socket.create_connection((GATEWAY_HOST, 443), timeout=30)
        sock = context.wrap_socket(raw, server_hostname=GATEWAY_HOST)
        key = base64.b64encode(os.urandom(16)).decode()
        handshake = (
            f"GET {GATEWAY_PATH} HTTP/1.1\r\n"
            f"Host: {GATEWAY_HOST}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "User-Agent: Freehands/2.0\r\n\r\n"
        )
        sock.sendall(handshake.encode())
        header = b""
        while b"\r\n\r\n" not in header:
            chunk = sock.recv(1)
            if not chunk:
                raise GatewayClosed("handshake closed")
            header += chunk
        status_line = header.split(b"\r\n", 1)[0].decode("latin-1")
        if "101" not in status_line:
            raise GatewayClosed(f"handshake rejected: {status_line}")
        # A finite timeout, not None. With no timeout a half-open connection
        # (the usual cause of a bot that goes quiet after a few hours) blocks
        # in recv() forever and nothing ever notices. It is widened once the
        # heartbeat interval is known.
        sock.settimeout(30)
        return sock

    @staticmethod
    def _recv_exact(sock, count: int) -> bytes:
        buffer = b""
        while len(buffer) < count:
            chunk = sock.recv(count - len(buffer))
            if not chunk:
                raise GatewayClosed("socket closed")
            buffer += chunk
        return buffer

    def _read_frame(self, sock) -> tuple[int, bytes]:
        first, second = self._recv_exact(sock, 2)
        opcode = first & 0x0F
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._recv_exact(sock, 2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._recv_exact(sock, 8))[0]
        if second & 0x80:
            mask = self._recv_exact(sock, 4)
            data = bytearray(self._recv_exact(sock, length))
            for i in range(len(data)):
                data[i] ^= mask[i % 4]
            return opcode, bytes(data)
        return opcode, self._recv_exact(sock, length)

    def _send_frame(self, sock, payload: str) -> None:
        data = payload.encode()
        header = bytearray([0x81])
        length = len(data)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header += struct.pack("!H", length)
        else:
            header.append(0x80 | 127)
            header += struct.pack("!Q", length)
        mask = os.urandom(4)
        header += mask
        masked = bytearray(data)
        for i in range(len(masked)):
            masked[i] ^= mask[i % 4]
        with self._write_lock:
            sock.sendall(bytes(header) + bytes(masked))

    # -- protocol ---------------------------------------------------------
    def _identify(self, sock) -> None:
        self._send_frame(sock, json.dumps({
            "op": OP_IDENTIFY,
            "d": {
                "token": self.token,
                "intents": self.intents,
                "properties": {
                    "os": "linux",
                    "browser": "freehands",
                    "device": "freehands",
                },
            },
        }))

    def _resume(self, sock) -> None:
        self._send_frame(sock, json.dumps({
            "op": OP_RESUME,
            "d": {
                "token": self.token,
                "session_id": self.session_id,
                "seq": self.seq,
            },
        }))

    def _heartbeat_loop(self, sock, interval: float) -> None:
        try:
            while not self._stop.is_set():
                time.sleep(interval)
                self._send_frame(sock, json.dumps({"op": OP_HEARTBEAT, "d": self.seq}))
        except Exception as exc:
            # This used to `return` silently. The reader below blocks on a
            # socket with no timeout, so a send that failed here left the bot
            # alive, holding a dead socket, receiving nothing — the "it stops
            # working after a few hours" report. Close the socket so the
            # reader wakes up and the reconnect path runs.
            log.warning("heartbeat failed (%s); dropping the connection", exc)
            try:
                sock.close()
            except OSError:
                pass

    def _run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                sock = self._connect()
                self._sock = sock
                opcode, payload = self._read_frame(sock)
                hello = json.loads(payload)
                if hello.get("op") != OP_HELLO:
                    raise GatewayClosed("expected hello")
                interval = hello["d"]["heartbeat_interval"] / 1000.0
                # Discord sends a heartbeat ACK within one interval. Waiting
                # three gives two missed beats of slack before we declare the
                # connection dead, which is the usual guidance for websockets.
                sock.settimeout(max(interval * 3.0, 15.0))

                if self.session_id and self.seq is not None:
                    self._resume(sock)
                else:
                    self._identify(sock)

                threading.Thread(
                    target=self._heartbeat_loop, args=(sock, interval), daemon=True
                ).start()

                while not self._stop.is_set():
                    opcode, payload = self._read_frame(sock)
                    if opcode == 0x8:
                        raise GatewayClosed(_describe_close(payload))
                    if opcode == 0x9:
                        self._send_frame(sock, json.dumps({"op": OP_HEARTBEAT, "d": self.seq}))
                        continue
                    if opcode not in (0x1, 0x2):
                        continue
                    event = json.loads(payload)
                    if event.get("s") is not None:
                        self.seq = event["s"]
                    op = event.get("op")
                    name = event.get("t")
                    data = event.get("d")

                    if op == OP_HEARTBEAT_ACK:
                        continue
                    if op == OP_HEARTBEAT:
                        self._send_frame(sock, json.dumps({"op": OP_HEARTBEAT, "d": self.seq}))
                        continue
                    if op == OP_RECONNECT:
                        raise GatewayClosed("reconnect requested")
                    if op == OP_INVALID_SESSION:
                        self.session_id = None
                        self.seq = None
                        raise GatewayClosed("invalid session")
                    if op == OP_DISPATCH:
                        if name == "READY":
                            self.session_id = data.get("session_id")
                            self.resume_url = data.get("resume_gateway_url")
                            self.alive.set()
                            log.info("gateway ready as %s", data["user"]["username"])
                            if self.on_ready:
                                self.on_ready(data)
                            continue
                        if name == "RESUMED":
                            self.alive.set()
                            log.info("gateway resumed")
                            continue
                        try:
                            self.on_event(name, data)
                        except Exception as exc:
                            log.error("handler error on %s: %r", name, exc)
                backoff = 1.0
            except Exception as exc:
                self.alive.clear()
                if self._stop.is_set():
                    return
                if "4014" in str(exc):
                    # The app lacks a privileged intent. Drop them and retry at
                    # once; content is hydrated over REST instead.
                    stripped = self.intents & ~(
                        INTENT_GUILD_MEMBERS
                        | INTENT_MESSAGE_CONTENT
                        | INTENT_GUILD_PRESENCES
                    )
                    if stripped != self.intents:
                        log.warning("privileged intents unavailable; retrying without them")
                        self.intents = stripped
                        self.reduced = True
                        self.session_id = None
                        self.seq = None
                        continue
                log.warning("gateway dropped (%s); retry in %.0fs", exc, backoff)
                time.sleep(backoff)
                backoff = min(backoff * 2, 60.0)


def _describe_close(payload: bytes) -> str:
    """Turn a close frame into `4014 <reason>` so callers can branch on it."""
    if len(payload) >= 2:
        code = struct.unpack("!H", payload[:2])[0]
        reason = payload[2:].decode("utf-8", "replace")
        return f"{code} {reason}".strip()
    return "server closed"


def parse_snowflake(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def quote(value: str) -> str:
    return urllib.parse.quote(value, safe="")
