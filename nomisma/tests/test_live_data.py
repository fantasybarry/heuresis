"""Offline transport, wire-protocol, provenance and session-boundary tests."""

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
import socket
import struct
import threading
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from nomisma import live_data as live


ENV = {"ALPACA_API_KEY": "private-api-key", "ALPACA_SECRET_KEY": "private-secret",
       "ALPACA_FEED": "iex", "ALPACA_PAPER": "true"}
NOW = datetime(2025, 7, 3, 15, 32, 15, tzinfo=timezone.utc)


def calendar():
    start = NOW.date() - timedelta(days=99)
    return [{"date": (start + timedelta(days=i)).isoformat(), "open": "09:30",
             "close": "13:00" if (start + timedelta(days=i)).isoformat() == "2025-07-03" else "16:00"}
            for i in range(100) if (start + timedelta(days=i)).weekday() < 5]


def bar(stamp, volume=1000):
    return {"t": stamp, "o": 2, "h": 2.1, "l": 1.9, "c": 2.05, "v": volume, "vw": 2.02}


def frame(payload, opcode=1, final=True):
    if not isinstance(payload, bytes):
        payload = json.dumps(payload).encode("utf-8")
    first = (0x80 if final else 0) | opcode
    if len(payload) < 126:
        return bytes((first, len(payload))) + payload
    if len(payload) < 65536:
        return bytes((first, 126)) + struct.pack("!H", len(payload)) + payload
    return bytes((first, 127)) + struct.pack("!Q", len(payload)) + payload


def sent_frame(wire):
    first, second = wire[:2]
    size = second & 127
    position = 2
    if size == 126:
        size = struct.unpack("!H", wire[2:4])[0]
        position = 4
    elif size == 127:
        size = struct.unpack("!Q", wire[2:10])[0]
        position = 10
    mask = wire[position:position + 4]
    payload = wire[position + 4:position + 4 + size]
    return first & 15, bool(second & 128), bytes(value ^ mask[i % 4] for i, value in enumerate(payload))


class FakeSocket:
    def __init__(self, chunks=()):
        self.chunks = list(chunks)
        self.sent = []
        self.closed = False

    def recv(self, count):
        if not self.chunks:
            return b""
        value = self.chunks.pop(0)
        if isinstance(value, Exception):
            raise value
        if len(value) > count:
            self.chunks.insert(0, value[count:])
            return value[:count]
        return value

    def sendall(self, value):
        self.sent.append(value)

    def settimeout(self, timeout):
        self.timeout = timeout

    def do_handshake(self):
        pass

    def close(self):
        self.closed = True


class SeedTests(unittest.TestCase):
    def fixture(self):
        entries = calendar()
        daily = [bar(entry["date"] + "T04:00:00Z") for entry in entries[-36:]]
        minutes = [bar((datetime(2025, 7, 3, 13, 30, tzinfo=timezone.utc) + timedelta(minutes=i)).isoformat())
                   for i in range(123)]
        # Endpoints can return overlapping/out-of-range records; local guards apply.
        minutes.extend([bar("2025-07-03T13:29:00Z"), bar("2025-07-02T14:00:00Z")])
        calls = []

        def get(url, params, headers):
            calls.append((url, dict(params), headers))
            if url.endswith("/calendar"):
                return entries
            if url.endswith("/snapshots"):
                return {"ABCD": {"latestTrade": {"t": NOW.isoformat(), "p": 2.05}}}
            if params["timeframe"] == "1Day":
                return {"bars": {"ABCD": daily}, "next_page_token": None}
            if "page_token" not in params:
                return {"bars": {"ABCD": minutes[:60]}, "next_page_token": "second"}
            return {"bars": {"ABCD": minutes[60:]}, "next_page_token": None}

        return get, calls

    @patch.dict(os.environ, ENV, clear=True)
    @patch.object(live, "_now", return_value=NOW)
    def test_seed_full_regular_history_split_adjustment_and_pagination(self, now):
        get, calls = self.fixture()
        with patch.object(live.providers, "_get_json", side_effect=get):
            bundle = live.load_live_seed(["abcd"])
        asset = bundle["assets"][0]
        self.assertEqual(bundle["session"]["close"], "2025-07-03T13:00:00-04:00")
        self.assertEqual(bundle["session"]["previous_date"], "2025-07-02")
        self.assertEqual(len(bundle["session"]["prior_dates"]), 30)
        self.assertEqual(bundle["session"]["prior_dates"][-1], "2025-07-02")
        self.assertEqual(len(asset["minutes"]), 122)
        self.assertEqual(asset["minutes"][0]["t"], "2025-07-03T13:30:00+00:00")
        self.assertEqual(asset["minutes"][-1]["t"], "2025-07-03T15:31:00+00:00")
        self.assertEqual(asset["minutes"][0]["vwap"], 2.02)
        self.assertGreaterEqual(len(asset["bars"]), 30)
        self.assertTrue(all(item["date"] < "2025-07-03" for item in asset["bars"]))
        history = [params for url, params, headers in calls if url.endswith("/bars")]
        self.assertTrue(all(params["feed"] == "iex" and params["adjustment"] == "split" for params in history))
        self.assertEqual(history[-1]["page_token"], "second")
        self.assertTrue(calls[0][0].startswith("https://paper-api.alpaca.markets/"))
        self.assertIsNone(asset["float"])
        self.assertEqual(asset["snapshot"]["_received_at"], NOW.isoformat())
        self.assertNotIn("private-", json.dumps(bundle))

    @patch.dict(os.environ, dict(ENV, ALPACA_PAPER="false"), clear=True)
    @patch.object(live, "_now", return_value=NOW.replace(hour=12))
    def test_premarket_uses_today_session_without_fetching_minutes(self, now):
        get, calls = self.fixture()
        with patch.object(live.providers, "_get_json", side_effect=get):
            bundle = live.load_live_seed(["ABCD"])
        self.assertEqual(bundle["session"]["date"], "2025-07-03")
        self.assertEqual(bundle["assets"][0]["minutes"], [])
        self.assertFalse(any(params.get("timeframe") == "1Min" for url, params, headers in calls))
        self.assertTrue(calls[0][0].startswith("https://api.alpaca.markets/"))

    def test_weekend_calendar_selects_most_recent_session(self):
        session, _ = live._session(calendar(), NOW + timedelta(days=2))
        self.assertEqual(session["date"], "2025-07-03")

    def test_calendar_rejects_missing_previous_day_and_invalid_hours(self):
        for entries in ({}, [], [{"date": "2025-07-03", "open": "16:00", "close": "09:30"}]):
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                live._session(entries, NOW)

    @patch.dict(os.environ, ENV, clear=True)
    @patch.object(live, "_now", return_value=NOW)
    def test_repeated_pagination_token_fails_instead_of_partial_seed(self, now):
        get, _ = self.fixture()

        def bad_pages(url, params, headers):
            result = get(url, params, headers)
            if params.get("timeframe") == "1Min":
                result["next_page_token"] = "repeat"
            return result

        with patch.object(live.providers, "_get_json", side_effect=bad_pages), self.assertRaisesRegex(ValueError, "repeated"):
            live.load_live_seed(["ABCD"])

    @patch.dict(os.environ, dict(ENV, FMP_API_KEY="fmp-private"), clear=True)
    @patch.object(live, "_now", return_value=NOW)
    def test_float_failure_does_not_fail_prices_or_leak_credentials(self, now):
        get, _ = self.fixture()
        with patch.object(live.providers, "_get_json", side_effect=get), patch.object(
                live, "fetch_float", side_effect=ValueError("fmp-private")):
            bundle = live.load_live_seed(["ABCD"])
        self.assertIn("FMP float could not be loaded", " ".join(bundle["warnings"]))
        self.assertNotIn("fmp-private", json.dumps(bundle))

    def test_cancellation_returns_before_inflight_http_finishes(self):
        started, release, stopped = threading.Event(), threading.Event(), threading.Event()
        finished = threading.Event()

        def blocked():
            started.set()
            release.wait(2)

        def caller():
            try:
                live._cancellable_call(blocked, stopped)
            except live._Cancelled:
                finished.set()

        worker = threading.Thread(target=caller)
        worker.start()
        try:
            self.assertTrue(started.wait(1))
            stopped.set()
            self.assertTrue(finished.wait(0.5))
        finally:
            release.set()
            worker.join(1)

    @patch.dict(os.environ, ENV, clear=True)
    def test_credentials_and_symbols_rejected_before_network(self):
        for symbols in ([], ["*"] , ["ABCD"] * 21):
            with self.subTest(symbols=symbols), self.assertRaises(ValueError):
                live.load_live_seed(symbols)
        with patch.dict(os.environ, {"ALPACA_FEED": "delayed_sip"}), self.assertRaisesRegex(ValueError, "real-time"):
            live.load_live_seed(["ABCD"])


class FloatTests(unittest.TestCase):
    def setUp(self):
        live._FLOAT_CACHE.clear()

    def get(self, payload):
        opener = MagicMock()
        opener.open.return_value.__enter__.side_effect = lambda: io.BytesIO(json.dumps(payload).encode())
        return opener

    @patch.dict(os.environ, {"FMP_API_KEY": "private-fmp-key"}, clear=True)
    @patch.object(live, "_now", return_value=NOW)
    def test_actual_float_and_source_date_fixed_https_get(self, now):
        opener = self.get([{"symbol": "ABCD", "floatShares": 123456, "outstandingShares": 987654,
                            "date": "2025-07-02 17:24:00"}])
        with patch.object(live, "build_opener", return_value=opener):
            result = live.fetch_float("abcd")
        self.assertEqual(result, {"shares": 123456, "as_of": "2025-07-02", "source": "FMP"})
        request = opener.open.call_args[0][0]
        self.assertEqual(request.method, "GET")
        self.assertTrue(request.full_url.startswith("https://financialmodelingprep.com/stable/shares-float?"))
        self.assertEqual(opener.open.call_args[1]["timeout"], 10)

    @patch.dict(os.environ, {"FMP_API_KEY": "private-fmp-key"}, clear=True)
    @patch.object(live, "_now", return_value=NOW)
    def test_missing_float_date_nonfinite_future_fractional_and_wrong_symbol_not_substituted(self, now):
        invalid = [{"outstandingShares": 1000}, {"floatShares": 1000},
                   {"floatShares": float("nan"), "date": "2025-07-02"},
                   {"floatShares": 1000.5, "date": "2025-07-02"},
                   {"floatShares": 1000, "date": "2027-07-02"},
                   {"floatShares": True, "date": "2025-07-02"}]
        for item in invalid:
            live._FLOAT_CACHE.clear()
            with self.subTest(item=item), patch.object(live, "build_opener", return_value=self.get([dict(item, symbol="ABCD")])):
                self.assertIsNone(live.fetch_float("ABCD"))

    @patch.dict(os.environ, {"FMP_API_KEY": "private-fmp-key"}, clear=True)
    @patch.object(live, "_now", return_value=NOW)
    def test_float_cache_expires_after_24_hours_and_returns_independent_value(self, now):
        opener = self.get([{"symbol": "ABCD", "floatShares": 123456, "date": "2025-07-02"}])
        with patch.object(live, "build_opener", return_value=opener), patch.object(live.time, "monotonic", return_value=100):
            first = live.fetch_float("ABCD")
            first["shares"] = 1
            self.assertEqual(live.fetch_float("ABCD")["shares"], 123456)
        self.assertEqual(opener.open.call_count, 1)
        with patch.object(live, "build_opener", return_value=opener), patch.object(
                live.time, "monotonic", return_value=100 + live._FLOAT_TTL):
            live.fetch_float("ABCD")
        self.assertEqual(opener.open.call_count, 2)

    @patch.dict(os.environ, {"FMP_API_KEY": "private-fmp-key"}, clear=True)
    def test_error_sanitized_and_redirect_denied(self):
        opener = MagicMock()
        opener.open.side_effect = HTTPError("https://financialmodelingprep.com/?apikey=private-fmp-key", 403,
                                           "private-fmp-key", {}, io.BytesIO())
        with patch.object(live, "build_opener", return_value=opener), self.assertRaises(ValueError) as caught:
            live.fetch_float("ABCD")
        self.assertNotIn("private-fmp-key", str(caught.exception))
        with self.assertRaises(ValueError):
            live._NoFloatRedirect().redirect_request(None, None, 302, "", {}, "https://evil.example")

    @patch.dict(os.environ, {}, clear=True)
    def test_unconfigured_float_and_status_do_not_expose_keys(self):
        self.assertIsNone(live.fetch_float("ABCD"))
        self.assertEqual(live.live_provider_status(), {"alpaca_configured": False, "feed": "iex", "float_configured": False})


class WebSocketTests(unittest.TestCase):
    def connection(self, wire):
        connection = live._WebSocket("iex", threading.Event())
        # Partial reads and a timeout between bytes exercise buffer preservation.
        connection.sock = FakeSocket([wire[:1], socket.timeout(), wire[1:3], wire[3:]])
        return connection

    def test_fragmented_json_ping_pong_and_partial_reads(self):
        payload = json.dumps([{"T": "q", "S": "ABCD", "bp": 2.01}]).encode()
        wire = frame(payload[:12], final=False) + frame(b"alive", opcode=9) + frame(payload[12:], opcode=0)
        connection = self.connection(wire)
        self.assertEqual(connection.message(), [{"T": "q", "S": "ABCD", "bp": 2.01}])
        opcode, masked, payload = sent_frame(connection.sock.sent[0])
        self.assertEqual((opcode, masked, payload), (10, True, b"alive"))

    def test_outbound_frames_masked_for_all_length_encodings(self):
        connection = self.connection(b"")
        for size in (5, 126, 65536):
            with self.subTest(size=size):
                payload = b"x" * size
                connection.send(1, payload)
                self.assertEqual(sent_frame(connection.sock.sent[-1]), (1, True, payload))

    def test_invalid_server_frames_and_messages_rejected(self):
        cases = [b"\x81\x80", b"\xc1\x00", b"\x89\x7e\x00\x7e",
                 b"\x81\x7f" + struct.pack("!Q", live._FRAME_LIMIT + 1),
                 frame(b"orphan", opcode=0), frame(b"x", opcode=8),
                 frame(struct.pack("!H", 1005), opcode=8),
                 frame(struct.pack("!H", 1000) + b"\xff", opcode=8),
                 frame(b"[]", final=False) + frame(b"[]"), frame(b"not json"),
                 frame({"T": "q"}), frame(b"\xff"), b"\x81\x7e\x00\x01x"]
        for wire in cases:
            with self.subTest(wire=wire[:15]), self.assertRaises(ValueError):
                self.connection(wire).message()

    def test_server_close_echoes_masked_close_and_raises(self):
        connection = self.connection(frame(struct.pack("!H", 1000), opcode=8))
        with self.assertRaisesRegex(ValueError, "closed"):
            connection.message()
        self.assertEqual(sent_frame(connection.sock.sent[0]), (8, True, struct.pack("!H", 1000)))

    def test_stop_during_partial_frame_is_prompt(self):
        connection = self.connection(b"\x81")
        connection.stop_event.set()
        with self.assertRaises(live._Cancelled):
            connection.message()

    def handshake(self, accept=None):
        key = base64.b64encode(b"k" * 16).decode()
        expected = base64.b64encode(hashlib.sha1((key + live._GUID).encode()).digest()).decode()
        return ("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: keep-alive, Upgrade\r\n"
                "Sec-WebSocket-Accept: {}\r\n\r\n").format(expected if accept is None else accept).encode()

    def test_tls_default_verification_handshake_and_initial_buffer_preserved(self):
        wire = self.handshake() + frame([{"T": "success", "msg": "connected"}])
        raw, secured = FakeSocket(), FakeSocket([wire[:10], wire[10:]])
        context = MagicMock()
        context.wrap_socket.return_value = secured
        with patch.object(live.socket, "create_connection", return_value=raw) as connect, patch.object(
                live.ssl, "create_default_context", return_value=context), patch.object(live.os, "urandom", return_value=b"k" * 16):
            connection = live._WebSocket("sip", threading.Event())
            connection.connect()
        connect.assert_called_once_with(("stream.data.alpaca.markets", 443), timeout=5)
        context.wrap_socket.assert_called_once_with(raw, server_hostname="stream.data.alpaca.markets", do_handshake_on_connect=False)
        self.assertIn(b"GET /v2/sip HTTP/1.1", secured.sent[0])
        self.assertNotIn(b"private-", secured.sent[0])
        self.assertEqual(connection.message(), [{"T": "success", "msg": "connected"}])

    def test_bad_handshake_accept_rejected_and_socket_closed(self):
        secured = FakeSocket([self.handshake("forged")])
        context = MagicMock()
        context.wrap_socket.return_value = secured
        with patch.object(live.socket, "create_connection", return_value=FakeSocket()), patch.object(
                live.ssl, "create_default_context", return_value=context), self.assertRaisesRegex(ValueError, "verification"):
            live._WebSocket("iex", threading.Event()).connect()
        self.assertTrue(secured.closed)

    def test_silent_connection_sends_ping_before_timeout(self):
        connection = self.connection(frame(b"ok", opcode=10) + frame([]))
        connection.upgraded = True
        connection.last_ping -= 25
        self.assertEqual(connection.message(), [])
        self.assertEqual(sent_frame(connection.sock.sent[0]), (9, True, b"nomisma"))


class StreamTests(unittest.TestCase):
    def acknowledgment(self):
        return dict({"T": "subscription"}, **{channel: ["ABCD"] for channel in live._CHANNELS})

    @patch.dict(os.environ, ENV, clear=True)
    def test_auth_and_subscription_verified_before_live_and_late_events_forwarded(self):
        stop = threading.Event()
        fake = MagicMock()
        events = [{"T": "t", "S": "ABCD", "p": 2}, {"T": "u", "S": "ABCD", "v": 321}]
        fake.message.side_effect = [[{"T": "success", "msg": "connected"}],
                                    [{"T": "success", "msg": "authenticated"}], [self.acknowledgment()], events]
        received, statuses = [], []

        def receive(event):
            received.append(event)
            if event["T"] == "u":
                stop.set()

        with patch.object(live, "_WebSocket", return_value=fake):
            live.stream_live(["ABCD"], receive, stop, statuses.append)
        self.assertEqual(statuses, ["connecting", "live"])
        self.assertEqual(received, events)
        self.assertEqual(fake.send_json.call_args_list[0][0][0]["action"], "auth")
        self.assertEqual(fake.send_json.call_args_list[1][0][0]["updatedBars"], ["ABCD"])
        fake.close.assert_called_once()

    @patch.dict(os.environ, ENV, clear=True)
    def test_partial_subscription_or_pre_auth_data_never_marks_live(self):
        partial = self.acknowledgment()
        partial["quotes"] = []
        excessive = self.acknowledgment()
        excessive["quotes"] = ["ABCD", "UNREQUESTED"]
        for reply in (partial, excessive, {"T": "t", "S": "ABCD", "p": 2}):
            with self.subTest(reply=reply):
                fake = MagicMock()
                fake.message.side_effect = [[{"T": "success", "msg": "authenticated"}], [reply]]
                statuses = []
                with patch.object(live, "_WebSocket", return_value=fake), self.assertRaises(ValueError):
                    live.stream_live(["ABCD"], lambda event: None, threading.Event(), statuses.append)
                self.assertEqual(statuses, ["connecting"])

    @patch.dict(os.environ, ENV, clear=True)
    def test_auth_errors_redact_upstream_messages(self):
        fake = MagicMock()
        fake.message.return_value = [{"T": "error", "code": 402, "msg": "private-secret"}]
        with patch.object(live, "_WebSocket", return_value=fake), self.assertRaises(ValueError) as caught:
            live.stream_live(["ABCD"], lambda event: None, threading.Event())
        self.assertIn("authentication failed", str(caught.exception))
        self.assertNotIn("private-secret", str(caught.exception))

    @patch.dict(os.environ, ENV, clear=True)
    def test_stop_before_stream_does_not_connect(self):
        stop = threading.Event()
        stop.set()
        with patch.object(live, "_WebSocket") as connect:
            live.stream_live(["ABCD"], lambda event: None, stop)
        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
