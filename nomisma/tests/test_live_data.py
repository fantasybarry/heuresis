"""Offline transport, wire-protocol, provenance and session-boundary tests."""

import base64
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import json
import os
import socket
import struct
import threading
import time
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
    def setUp(self):
        eligibility = patch("nomisma.instruments.require_stocks")
        eligibility.start()
        self.addCleanup(eligibility.stop)
        live._HISTORY_CACHE.clear()

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
                return {"ABCD": {"latestTrade": {"t": NOW.isoformat(), "p": 2.05},
                                 "dailyBar": {"t": "2025-07-03T04:00:00Z", "v": 120000}}}
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
        self.assertEqual([params for params in history if params["timeframe"] == "1Min"][-1]["page_token"], "second")
        self.assertTrue(calls[0][0].startswith("https://paper-api.alpaca.markets/"))
        self.assertIsNone(asset["float"])
        self.assertEqual(asset["snapshot"]["_received_at"], NOW.isoformat())
        self.assertNotIn("private-", json.dumps(bundle))

    @patch.dict(os.environ, ENV, clear=True)
    @patch.object(live, "_now", return_value=NOW)
    def test_seed_freezes_quote_response_receipt_without_changing_event_or_sizes(self, now):
        get, _ = self.fixture()
        quote = {"t": (NOW - timedelta(seconds=2)).isoformat(), "bp": 2, "ap": 2.01,
                 "bs": 200, "as": 300}

        def snapshots(url, params, headers):
            result = get(url, params, headers)
            if url.endswith("/snapshots"):
                result["ABCD"]["latestQuote"] = quote
            return result

        with patch.object(live.providers, "_get_json", side_effect=snapshots):
            bundle = live.load_live_seed(["ABCD"])
        frozen = bundle["assets"][0]["snapshot"]["latestQuote"]
        self.assertEqual(frozen["_received_at"], NOW.isoformat())
        self.assertEqual(frozen["t"], quote["t"])
        self.assertEqual(frozen["as"], 300)
        self.assertNotIn("_received_at", quote)

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

    @patch.dict(os.environ, ENV, clear=True)
    def test_premarket_seed_uses_extended_minutes_when_daily_snapshot_is_previous_day(self):
        now = NOW.replace(hour=13, minute=15)
        get, _ = self.fixture()

        def premarket(url, params, headers):
            if url.endswith("/snapshots"):
                return {"ABCD": {"latestTrade": {"t": now.isoformat(), "p": 2.05},
                                  "dailyBar": {"t": "2025-07-02T04:00:00Z", "v": 999999}}}
            if params.get("timeframe") == "1Min":
                return {"bars": {"ABCD": [bar("2025-07-03T08:00:00Z", 100),
                                            bar("2025-07-03T13:14:00Z", 900)]}}
            return get(url, params, headers)

        with patch.object(live, "_now", return_value=now), patch.object(live.providers, "_get_json", side_effect=premarket):
            bundle = live.load_live_seed(["ABCD"])
        self.assertEqual(bundle["assets"][0]["minutes"], [])
        self.assertEqual(bundle["assets"][0]["snapshot"]["_extended_day"]["volume"], 1000)
        self.assertEqual(bundle["assets"][0]["snapshot"]["dailyBar"]["v"], 999999)
        self.assertIn("benchmark_bars", bundle)

    @patch.dict(os.environ, ENV, clear=True)
    def test_optional_extended_volume_failure_preserves_prices_but_cancellation_propagates(self):
        from nomisma.monitor_metrics import build_rows, validate_monitor_config
        now = NOW.replace(hour=13, minute=15)
        get, _ = self.fixture()

        def premarket(url, params, headers):
            if url.endswith("/snapshots"):
                return {"ABCD": {"latestTrade": {"t": now.isoformat(), "p": 2.05},
                                  "latestQuote": {"t": now.isoformat(), "bp": 2.04, "ap": 2.06},
                                  "dailyBar": {"t": "2025-07-02T04:00:00Z", "v": 999999}}}
            return get(url, params, headers)

        with patch.object(live, "_now", return_value=now), patch.object(live.providers, "_get_json", side_effect=premarket):
            with patch.object(live, "extended_day_volumes", side_effect=ValueError("Request failed: private-provider-key")):
                bundle = live.load_live_seed(["ABCD"])
            result = build_rows(bundle, validate_monitor_config({"source": "alpaca", "symbols": ["ABCD"]}), now)[0]
            self.assertEqual(result["price"], 2.05)
            self.assertIsNone(result["day_volume"])
            self.assertFalse(result["day_volume_fresh"])
            self.assertFalse(result["alert_eligible"])
            self.assertIn("Extended-hours minute volume could not be loaded", " ".join(bundle["warnings"]))
            self.assertNotIn("private-provider-key", json.dumps(bundle))
            with patch.object(live, "extended_day_volumes", side_effect=live._Cancelled("Stopped")):
                with self.assertRaises(live._Cancelled):
                    live.load_live_seed(["ABCD"])

    @patch.dict(os.environ, ENV, clear=True)
    @patch.object(live, "_now", return_value=NOW)
    def test_current_provider_daily_volume_does_not_load_or_add_extended_fallback(self, now):
        get, _ = self.fixture()
        with patch.object(live.providers, "_get_json", side_effect=get), \
                patch.object(live, "extended_day_volumes", side_effect=AssertionError("Already have provider total")):
            bundle = live.load_live_seed(["ABCD"])
        self.assertNotIn("_extended_day", bundle["assets"][0]["snapshot"])
        self.assertEqual(bundle["assets"][0]["snapshot"]["dailyBar"]["v"], 120000)

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

    @patch.dict(os.environ, ENV, clear=True)
    @patch.object(live, "_now", return_value=NOW)
    def test_history_and_snapshots_overlap_without_losing_pagination(self, now):
        get, calls = self.fixture()
        barrier = threading.Barrier(3, timeout=2)

        def overlapping(url, params, headers):
            if url.endswith("/snapshots") or (url.endswith("/bars") and "page_token" not in params):
                barrier.wait()
            return get(url, params, headers)

        with patch.object(live.providers, "_get_json", side_effect=overlapping):
            bundle = live.load_live_seed(["ABCD"])
        self.assertEqual(len(bundle["assets"][0]["minutes"]), 122)
        self.assertEqual(sum(params.get("page_token") == "second" for _, params, _ in calls), 1)

    @patch.dict(os.environ, dict(ENV, FMP_API_KEY="private-fmp"), clear=True)
    @patch.object(live, "_now", return_value=NOW)
    def test_float_loads_use_two_workers_and_explicit_refresh_bypasses_cache(self, now):
        get, _ = self.fixture()
        barrier = threading.Barrier(2, timeout=2)
        observed = []

        def floating(symbol, refresh):
            observed.append((symbol, refresh))
            barrier.wait()
            return {"shares": 1000, "as_of": "2025-07-02", "source": "FMP"}

        with patch.object(live.providers, "_get_json", side_effect=get), \
                patch.object(live, "fetch_float", side_effect=floating), patch.object(live, "extended_day_volumes", return_value={}):
            bundle = live.load_live_seed(["ABCD", "WXYZ"], refresh=True)
        self.assertCountEqual(observed, [("ABCD", True), ("WXYZ", True)])
        self.assertTrue(all(asset["float"]["source"] == "FMP" for asset in bundle["assets"]))

    @patch.dict(os.environ, dict(ENV, FMP_API_KEY="private-fmp"), clear=True)
    @patch.object(live, "_now", return_value=NOW)
    def test_seed_failure_cancels_siblings_without_stopping_parent_monitor(self, now):
        get, _ = self.fixture()
        started, cancelled, parent_stop = threading.Event(), threading.Event(), threading.Event()

        def history(symbols, session, calendar_days, instant, feed, headers, stopped, timeframe, **kwargs):
            if timeframe == "1Min":
                started.set()
                deadline = time.monotonic() + 2
                while not stopped.is_set() and time.monotonic() < deadline:
                    time.sleep(0.01)
                if stopped.is_set():
                    cancelled.set()
                live._check_stop(stopped)
                raise AssertionError("Sibling request was not cancelled")
            self.assertTrue(started.wait(1))
            raise ValueError("History unavailable")

        with patch.object(live.providers, "_get_json", side_effect=get), \
                patch.object(live, "_history", side_effect=history), patch.object(live, "fetch_float", return_value=None):
            with self.assertRaisesRegex(ValueError, "History unavailable"):
                live.load_live_seed(["ABCD"], stop_event=parent_stop)
        self.assertTrue(cancelled.is_set())
        self.assertFalse(parent_stop.is_set())

    def test_provider_symbol_validation_matches_fifty_symbol_application_limit(self):
        symbols = ["S%s" % index for index in range(50)]
        self.assertEqual(live._symbols(symbols), symbols)
        with self.assertRaisesRegex(ValueError, "50"):
            live._symbols(symbols + ["EXTRA"])
        self.assertIn("reduce the symbol list", str(live._stream_error({"code": 405})))

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
        for symbols in ([], ["*"] , ["ABCD"] * 51):
            with self.subTest(symbols=symbols), self.assertRaises(ValueError):
                live.load_live_seed(symbols)
        with patch.dict(os.environ, {"ALPACA_FEED": "delayed_sip"}), self.assertRaisesRegex(ValueError, "real-time"):
            live.load_live_seed(["ABCD"])


class ScreeningHistoryTests(unittest.TestCase):
    def setUp(self):
        live._HISTORY_CACHE.clear()
        self.session, _ = live._session(calendar(), NOW)
        self.headers = {"APCA-API-KEY-ID": "mock", "APCA-API-SECRET-KEY": "secret"}

    def test_history_requests400_days_and_spy_excludes_current_weekend_and_future(self):
        prior = (NOW.date() - timedelta(days=300))
        while prior.weekday() >= 5:
            prior -= timedelta(days=1)
        payload = {"bars": {"ABCD": [bar(prior.isoformat() + "T04:00:00Z"),
                    bar("2025-06-28T04:00:00Z"), bar("2025-07-03T04:00:00Z"),
                    bar("2025-07-04T04:00:00Z")], "SPY": [bar("2025-07-02T04:00:00Z")]}}
        with patch.object(live, "_get_json", return_value=payload) as get:
            result = live.screening_history(["ABCD"], self.session, NOW, "iex", self.headers)
        params = get.call_args.args[1]
        self.assertEqual(params["symbols"], "ABCD,SPY")
        self.assertEqual(params["adjustment"], "split")
        self.assertEqual(date.fromisoformat(params["start"][:10]), NOW.date() - timedelta(days=400))
        self.assertEqual([item["date"] for item in result["ABCD"]], [prior.isoformat()])
        self.assertEqual(result["SPY"][0]["date"], "2025-07-02")

    def test_history_cache_is_bounded_isolated_and_explicit_refresh_bypasses_it(self):
        payload = {"bars": {"ABCD": [bar("2025-07-02T04:00:00Z")], "SPY": []}}
        with patch.object(live, "_get_json", return_value=payload) as get:
            first = live.screening_history(["ABCD"], self.session, NOW, "iex", self.headers)
            first["ABCD"][0]["volume"] = 999
            again = live.screening_history(["ABCD"], self.session, NOW, "iex", self.headers)
            self.assertEqual(again["ABCD"][0]["volume"], 1000)
            self.assertEqual(get.call_count, 1)
            live.screening_history(["ABCD"], self.session, NOW, "iex", self.headers, refresh=True)
            self.assertEqual(get.call_count, 2)
            live.screening_history(["ABCD"], self.session, NOW, "sip", self.headers)
            live.screening_history(["ABCD"], self.session, NOW, "iex", dict(self.headers, **{"APCA-API-KEY-ID": "other"}))
            self.assertEqual(get.call_count, 4)
            with patch.object(live, "_HISTORY_CACHE_LIMIT", 3):
                live.screening_history(["ABCD"], self.session, NOW, "iex", self.headers, refresh=True)
                self.assertLessEqual(len(live._HISTORY_CACHE), 3)

    def test_history_cache_expires_and_session_change_fetches_again(self):
        payload = {"bars": {"ABCD": [bar("2025-07-02T04:00:00Z")], "SPY": []}}
        with patch.object(live, "_get_json", return_value=payload) as get:
            with patch.object(live.time, "monotonic", return_value=100):
                live.screening_history(["ABCD"], self.session, NOW, "iex", self.headers)
            with patch.object(live.time, "monotonic", return_value=100 +live._HISTORY_TTL):
                live.screening_history(["ABCD"], self.session, NOW, "iex", self.headers)
                self.assertEqual(get.call_count, 2)
                session = dict(self.session, date="2025-07-04")
                live.screening_history(["ABCD"], session, NOW +timedelta(days=1), "iex", self.headers)
                self.assertEqual(get.call_count, 3)

    def test_extended_volume_spans_premarket_regular_and_deduplicates_overlap(self):
        opening = bar("2025-07-03T08:00:00Z", 200)
        regular = bar("2025-07-03T13:30:00Z", 300)
        payload = {"bars": {"ABCD": [bar("2025-07-03T07:59:00Z", 999), opening, opening, regular,
                                                bar("2025-07-03T15:32:00Z", 999)]}}
        with patch.object(live, "_get_json", return_value=payload) as get, patch.object(live, "_now", return_value=NOW):
            result = live.extended_day_volumes(["ABCD"], self.session, NOW, "iex", self.headers)["ABCD"]
        self.assertEqual(result["volume"], 500)
        self.assertEqual(len(result["minutes"]), 2)
        self.assertEqual(result["received_at"], NOW.isoformat())
        self.assertEqual(get.call_args.args[1]["start"], "2025-07-03T08:00:00+00:00")
        self.assertEqual(get.call_args.args[1]["adjustment"], "split")

    def test_failed_or_partial_history_is_not_cached(self):
        payload = {"bars": {"ABCD": [bar("2025-07-02T04:00:00Z")]}, "next_page_token": "repeat"}
        with patch.object(live, "_get_json", return_value=payload), self.assertRaisesRegex(ValueError, "repeated"):
            live.screening_history(["ABCD"], self.session, NOW, "iex", self.headers)
        self.assertEqual(len(live._HISTORY_CACHE), 0)


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

    @patch.dict(os.environ, {"FMP_API_KEY": "private-fmp-key"}, clear=True)
    @patch.object(live, "_now", return_value=NOW)
    def test_explicit_float_refresh_does_not_reuse_ttl_cache(self, now):
        first = self.get([{"symbol": "ABCD", "floatShares": 1000, "date": "2025-07-02"}])
        updated = self.get([{"symbol": "ABCD", "floatShares": 2000, "date": "2025-07-03"}])
        with patch.object(live, "build_opener", side_effect=[first, updated]):
            self.assertEqual(live.fetch_float("ABCD")["shares"], 1000)
            self.assertEqual(live.fetch_float("ABCD")["shares"], 1000)
            self.assertEqual(live.fetch_float("ABCD", refresh=True)["shares"], 2000)
        self.assertEqual(first.open.call_count, 1)
        self.assertEqual(updated.open.call_count, 1)

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
        self.assertEqual([event for event in received if event["T"] != "nomisma_subscription"], events)
        subscription = next(event for event in received if event["T"] == "nomisma_subscription")
        self.assertTrue(subscription["required"])
        self.assertFalse(subscription["statuses"])
        self.assertFalse(subscription["lulds"])
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
    def test_optional_channel_denial_preserves_price_stream_and_checks_other_channel(self):
        stop = threading.Event()
        fake = MagicMock()
        accepted = dict(self.acknowledgment(), statuses=[], lulds=["ABCD"])
        fake.message.side_effect = [[{"T": "success", "msg": "authenticated"}], [self.acknowledgment()],
                                    [{"T": "error", "code": 410, "msg": "private-secret"}], [accepted],
                                    [{"T": "t", "S": "ABCD", "p": 2.1}]]
        received = []

        def receive(event):
            received.append(event)
            if event["T"] == "t":
                stop.set()

        with patch.object(live, "_WebSocket", return_value=fake):
            live.stream_live(["ABCD"], receive, stop)
        self.assertEqual(fake.send_json.call_args_list[2][0][0], {"action": "subscribe", "statuses": ["ABCD"]})
        self.assertEqual(fake.send_json.call_args_list[3][0][0], {"action": "subscribe", "lulds": ["ABCD"]})
        channels = [event for event in received if event["T"] == "nomisma_subscription"][-1]
        self.assertFalse(channels["statuses"])
        self.assertTrue(channels["lulds"])
        self.assertNotIn("private-secret", str(received))
        self.assertEqual(received[-1]["T"], "t")
        fake.close.assert_called_once()

    @patch.dict(os.environ, ENV, clear=True)
    def test_optional_acknowledgments_and_halt_events_are_forwarded(self):
        stop = threading.Event()
        fake = MagicMock()
        halt = {"T": "s", "S": "ABCD", "sc": "H", "t": NOW.isoformat()}
        fake.message.side_effect = [[{"T": "success", "msg": "authenticated"}], [self.acknowledgment()],
                                    [dict(self.acknowledgment(), statuses=["ABCD"])],
                                    [dict(self.acknowledgment(), statuses=["ABCD"], lulds=["ABCD"])], [halt]]
        received = []

        def receive(event):
            received.append(event)
            if event["T"] == "s":
                stop.set()

        with patch.object(live, "_WebSocket", return_value=fake):
            live.stream_live(["ABCD"], receive, stop)
        channels = [event for event in received if event["T"] == "nomisma_subscription"][-1]
        self.assertTrue(channels["statuses"])
        self.assertTrue(channels["lulds"])
        self.assertEqual(received[-1], halt)

    @patch.dict(os.environ, ENV, clear=True)
    def test_stop_before_stream_does_not_connect(self):
        stop = threading.Event()
        stop.set()
        with patch.object(live, "_WebSocket") as connect:
            live.stream_live(["ABCD"], lambda event: None, stop)
        connect.assert_not_called()


class CandleTests(unittest.TestCase):
    def test_pages_newest_first_and_returns_oldest_first(self):
        def bar(minute):
            return {"t": "2025-07-03T15:%02d:00Z" % minute, "o": 2, "h": 3, "l": 1, "c": 2.5, "v": 100}
        pages = [{"bars": {"AAPL": [bar(3), bar(2)]}, "next_page_token": "next"},
                 {"bars": {"AAPL": [bar(1)]}, "next_page_token": None}]
        with patch.dict(os.environ, ENV), patch.object(live, "_get_json", side_effect=pages) as get:
            result = live.fetch_candles("aapl", "5Min")
        self.assertEqual([candle["t"] for candle in result["candles"]],
                         ["2025-07-03T15:0%d:00+00:00" % minute for minute in (1, 2, 3)])
        self.assertEqual(get.call_args_list[0].args[1]["sort"], "desc")
        self.assertEqual(get.call_args_list[1].args[1]["page_token"], "next")

    def test_before_cursor_ends_just_before_the_oldest_loaded_bar(self):
        with patch.dict(os.environ, ENV), patch.object(live, "_get_json", return_value={"bars": {}}) as get:
            self.assertEqual(live.fetch_candles("AAPL", "1Hour", "2025-07-03T15:00:00+00:00")["candles"], [])
        self.assertEqual(get.call_args.args[1]["end"], "2025-07-03T14:59:59.999999+00:00")

    def test_rejects_unknown_timeframe_and_invalid_bars(self):
        with self.assertRaisesRegex(ValueError, "Timeframe"):
            live.fetch_candles("AAPL", "2Min")
        bad = {"bars": {"AAPL": [{"t": "2025-07-03T15:00:00Z", "o": 2, "h": 1, "l": 1, "c": 2, "v": 1}]}}
        with patch.dict(os.environ, ENV), patch.object(live, "_get_json", return_value=bad):
            with self.assertRaisesRegex(ValueError, "invalid 1Min candle"):
                live.fetch_candles("AAPL", "1Min")


if __name__ == "__main__":
    unittest.main()
