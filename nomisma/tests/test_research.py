"""Offline tests for discovery provenance and bounded diagnostic access."""

from datetime import datetime, timedelta, timezone
import os
import threading
import unittest
from unittest.mock import patch

from nomisma import research
from nomisma import live_data as live
from nomisma import providers


NOW = datetime(2025, 7, 3, 15, 32, 15, tzinfo=timezone.utc)
ENV = {"ALPACA_API_KEY": "test-private-key", "ALPACA_SECRET_KEY": "test-private-secret",
       "ALPACA_FEED": "iex", "ALPACA_PAPER": "true"}
SESSION = {"date": "2025-07-03", "previous_date": "2025-07-02",
           "open": "2025-07-03T13:30:00+00:00", "close": "2025-07-03T17:00:00+00:00"}
SESSION["prior_dates"] = sorted((NOW.date() - timedelta(days=offset)).isoformat()
                               for offset in range(1, 61) if (NOW.date() - timedelta(days=offset)).weekday() < 5)[-30:]


def stock(price=2.2, stamp=None, volume=100000):
    stamp = stamp or NOW.isoformat()
    return {"latestTrade": {"p": price, "t": stamp}, "latestQuote": {"t": stamp, "ap": price + .01, "bp": price - .01},
            "dailyBar": {"t": "2025-07-03T04:00:00Z", "c": price, "v": volume},
            "prevDailyBar": {"t": "2025-07-02T04:00:00Z", "c": 2},
            "minuteBar": {"t": "2025-07-03T15:31:00Z", "c": price}}


def calendar():
    return [{"date": "2025-07-02", "open": "09:30", "close": "16:00"},
            {"date": "2025-07-03", "open": "09:30", "close": "13:00"}]


@patch.dict(os.environ, ENV, clear=True)
@patch.object(live, "_now", return_value=NOW)
class DiscoveryTests(unittest.TestCase):
    def test_batches_and_filters_with_explicit_feed(self, unused_now):
        calls = []

        def get(url, params, headers, stop_event=None):
            calls.append((url, dict(params)))
            self.assertEqual(headers["APCA-API-KEY-ID"], ENV["ALPACA_API_KEY"])
            if url.endswith("/calendar"):
                return calendar()
            return {symbol: stock(price=2.2 + int(symbol[1:]) / 100, volume=100000 + int(symbol[1:]))
                    for symbol in params["symbols"].split(",")}

        with patch.object(live, "_get_json", side_effect=get):
            result = research.discover({"source": "alpaca", "universe": "custom",
                                        "symbols": ["X{}".format(i) for i in range(51)], "limit": 3,
                                        "min_change_pct": 20, "min_day_volume": 100010})
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(params["feed"] == "iex" for url, params in calls if url.endswith("snapshots")))
        self.assertEqual(result["coverage"]["requested"], 51)
        self.assertEqual(result["coverage"]["received"], 51)
        self.assertEqual(result["coverage"]["returned"], 3)
        self.assertEqual([row["symbol"] for row in result["rows"]], ["X50", "X49", "X48"])
        self.assertEqual(result["market_phase"], "regular")
        self.assertEqual(result["session_date"], "2025-07-03")
        self.assertTrue(any("IEX" in warning for warning in result["warnings"]))

    def test_stale_missing_invalid_and_previous_session_are_excluded(self, unused_now):
        prior = stock(stamp="2025-07-02T15:32:00Z")
        wrong_close = stock()
        wrong_close["prevDailyBar"]["t"] = "2025-07-01T04:00:00Z"
        data = {"FRESH": stock(), "OLD": stock(stamp="2025-07-03T15:00:00Z"), "PRIOR": prior,
                "WRONG": wrong_close, "BAD": stock(price=float("nan")),
                "FUTURE": stock(stamp="2025-07-03T16:32:00Z")}
        with patch.object(research, "_calendar", return_value=(SESSION, set())), patch.object(live, "_get_json", return_value=data):
            result = research.discover({"source": "alpaca", "universe": "custom", "symbols": list(data) + ["MISSING"]})
        self.assertEqual([row["symbol"] for row in result["rows"]], ["FRESH"])
        self.assertEqual(result["coverage"]["stale"], 3)
        self.assertEqual(result["coverage"]["missing"], 1)
        self.assertEqual(result["coverage"]["invalid"], 2)

    def test_weekend_never_presents_previous_session_as_current(self, now):
        now.return_value = datetime(2025, 7, 5, 15, 32, tzinfo=timezone.utc)
        with patch.object(research, "_calendar", return_value=(SESSION, set())), patch.object(live, "_get_json", return_value={"ABC": stock()}):
            result = research.discover({"source": "alpaca", "universe": "custom", "symbols": ["ABC"]})
        self.assertEqual(result["rows"], [])
        self.assertEqual(result["session_date"], "2025-07-05")
        self.assertEqual(result["latest_session_date"], "2025-07-03")
        self.assertEqual(result["market_phase"], "closed")
        self.assertIn("no exchange session", " ".join(result["warnings"]))

    def test_all_listings_filters_inactive_otc_and_reports_coverage(self, unused_now):
        listing = [{"symbol": symbol, "status": status, "tradable": tradable, "exchange": exchange, "name": "Name " + symbol}
                   for symbol, status, tradable, exchange in (("AAA", "active", True, "NYSE"), ("BBB", "active", True, "BATS"),
                                                            ("ZZZ", "inactive", True, "NYSE"), ("OTC", "active", True, "OTC"),
                                                            ("NOPE", "active", False, "NASDAQ"))]

        def get(url, params, headers, stop=None):
            return listing if url.endswith("assets") else {"AAA": stock(), "BBB": stock()}

        with patch.object(research, "_calendar", return_value=(SESSION, set())), patch.object(live, "_get_json", side_effect=get):
            result = research.discover({"source": "alpaca", "universe": "all"})
        self.assertEqual(result["coverage"]["requested"], 2)
        self.assertEqual([row["symbol"] for row in result["rows"]], ["AAA", "BBB"])
        self.assertIn("not every US security", " ".join(result["warnings"]))

    def test_failed_batch_does_not_return_partial_or_demo(self, unused_now):
        with patch.object(research, "_calendar", return_value=(SESSION, set())), patch.object(live, "_get_json", side_effect=providers.ProviderError("Alpaca denied access.")):
            with self.assertRaisesRegex(providers.ProviderError, "denied"):
                research.discover({"source": "alpaca", "universe": "custom", "symbols": ["ABC"]})

    def test_demo_is_explicit_historical_and_no_provider_calls(self, unused_now):
        with patch.object(live, "_get_json") as get:
            result = research.discover({"source": "demo", "universe": "custom", "symbols": "LABA, LABB"})
        get.assert_not_called()
        self.assertEqual(result["feed"], "synthetic")
        self.assertEqual(result["session_date"], "2025-05-14")
        self.assertEqual(result["market_phase"], "synthetic")
        self.assertEqual(len(result["rows"]), 2)

    def test_cancel_and_invalid_input_do_not_call_provider(self, unused_now):
        stop = threading.Event()
        stop.set()
        with patch.object(live, "_get_json") as get, self.assertRaises(live._Cancelled):
            research.discover({"source": "alpaca"}, stop_event=stop)
        get.assert_not_called()
        for payload in ({"max_price": float("nan")}, {"limit": True}, {"min_price": 5, "max_price": 2},
                        {"universe": "custom", "symbols": []}, {"source": "csv"}, {"unknown": 1},
                        {"universe": "custom", "symbols": ["AAA"] * 1001}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                research.validate_discovery(payload)


@patch.dict(os.environ, ENV, clear=True)
@patch.object(live, "_now", return_value=NOW)
class DiagnosticTests(unittest.TestCase):
    def fixture(self):
        def history(symbols, session, days, now, feed, headers, stop, timeframe):
            if timeframe == "1Day":
                return {symbol: [dict(date=day, open=2, high=2.1, low=1.9, close=2, volume=10000)
                                 for day in SESSION["prior_dates"]] for symbol in symbols}
            opening = live._stamp(SESSION["open"])
            return {symbol: [dict(t=(opening + timedelta(minutes=i)).isoformat(), open=2, high=2.1, low=1.9,
                                 close=2, volume=10000, vwap=2) for i in range(122)] for symbol in symbols}
        return patch.object(research, "_calendar", return_value=(SESSION, set())), patch.object(live, "_get_json", return_value={"AAA": stock()}), patch.object(live, "_history", side_effect=history)

    def test_running_monitor_uses_existing_ack_without_second_connection(self, unused_now):
        one, two, three = self.fixture()
        snapshot = {"config": {"source": "alpaca", "symbols": ["AAA"]}, "status": {"running": True, "source": "alpaca", "feed": "iex", "connection": "live", "channel_subscriptions": {"statuses": True, "lulds": False, "required": True}}}
        with one, two, three, patch.object(live, "stream_live") as stream:
            result = research.diagnose({"source": "alpaca", "symbols": ["AAA"]}, snapshot)
        stream.assert_not_called()
        checks = {row["name"]: row for row in result["checks"]}
        self.assertEqual(checks["Authentication"]["status"], "pass")
        self.assertEqual(checks["Stream subscriptions"]["status"], "pass")
        self.assertEqual(checks["Trading status"]["status"], "pass")
        self.assertEqual(result["symbols"][0]["minute_gaps"], 0)
        self.assertFalse(result["symbols"][0]["missing_history"])
        self.assertNotIn("test-private", str(result))

    def test_standalone_stream_stops_at_price_confirmation(self, unused_now):
        one, two, three = self.fixture()

        def stream(symbols, on_event, stop, on_status):
            self.assertFalse(stop.is_set())
            on_status("connecting")
            on_status("live")
            self.assertTrue(stop.is_set())

        with one, two, three, patch.object(live, "stream_live", side_effect=stream) as connect:
            result = research.diagnose({"source": "alpaca", "symbols": ["AAA"]}, {"status": {"running": False}})
        connect.assert_called_once()
        self.assertEqual(next(row for row in result["checks"] if row["name"] == "Stream subscriptions")["status"], "pass")
        self.assertEqual(next(row for row in result["checks"] if row["name"] == "Trading status")["status"], "skipped")

    def test_reconnecting_monitor_does_not_open_second_socket(self, unused_now):
        one, two, three = self.fixture()
        with one, two, three, patch.object(live, "stream_live") as connect:
            result = research.diagnose({"source": "alpaca", "symbols": ["AAA"]}, {"status": {"running": True, "source": "alpaca", "connection": "reconnecting"}})
        connect.assert_not_called()
        self.assertEqual(next(row for row in result["checks"] if row["name"] == "Stream subscriptions")["status"], "warning")

    def test_stream_state_is_refreshed_and_different_selection_is_not_certified(self, unused_now):
        one, two, three = self.fixture()
        refreshed = {"config": {"source": "alpaca", "symbols": ["OTHER"]},
                     "status": {"running": True, "source": "alpaca", "feed": "iex", "connection": "live"}}
        with one, two, three, patch.object(live, "stream_live") as connect:
            result = research.diagnose({"source": "alpaca", "symbols": ["AAA"]}, {}, snapshot_provider=lambda: refreshed)
        connect.assert_not_called()
        self.assertEqual(next(row for row in result["checks"] if row["name"] == "Stream subscriptions")["status"], "warning")

    def test_provider_and_unexpected_failures_are_sanitized(self, unused_now):
        with patch.object(research, "_calendar", side_effect=RuntimeError("secret=do-not-print")), patch.object(live, "_get_json", side_effect=providers.ProviderError("Alpaca denied access.")), patch.object(live, "stream_live", side_effect=RuntimeError("secret=do-not-print")):
            result = research.diagnose({"source": "alpaca", "symbols": ["AAA"]}, {})
        self.assertNotIn("do-not-print", str(result))
        self.assertIn("Alpaca denied access", str(result))
        self.assertTrue(result["symbols"][0]["missing_history"])

    def test_missing_configuration_and_demo_do_not_contact_provider(self, unused_now):
        with patch.dict(os.environ, {}, clear=True), patch.object(live, "_get_json") as get:
            result = research.diagnose({"source": "alpaca", "symbols": ["AAA"]}, {})
        get.assert_not_called()
        self.assertEqual(result["checks"][0]["status"], "fail")
        with patch.object(live, "_get_json") as get:
            demo = research.diagnose({"source": "demo", "symbols": ["AAA"]}, {})
        get.assert_not_called()
        self.assertEqual(demo["feed"], "synthetic")
        self.assertIn("No provider connectivity", demo["checks"][0]["message"])

    def test_exact_calendar_history_and_internal_minute_gaps_are_reported(self, unused_now):
        def history(symbols, session, days, now, feed, headers, stop, timeframe):
            if timeframe == "1Day":
                # Thirty rows cannot substitute an older date for an expected day.
                dates = ["2025-04-01"] + SESSION["prior_dates"][1:]
                return {"AAA": [dict(date=day, open=2, high=2.1, low=1.9, close=2, volume=10000) for day in dates]}
            opening = live._stamp(SESSION["open"])
            return {"AAA": [dict(t=(opening + timedelta(minutes=i)).isoformat(), open=2, high=2.1, low=1.9,
                                  close=2, volume=10000, vwap=2) for i in range(122) if i != 10]}

        raw = stock(stamp=(NOW - timedelta(seconds=45)).isoformat())
        with patch.object(research, "_calendar", return_value=(SESSION, set())), patch.object(live, "_get_json", return_value={"AAA": raw}), patch.object(live, "_history", side_effect=history):
            result = research.diagnose({"source": "alpaca", "symbols": ["AAA"]}, {"status": {"running": True, "source": "alpaca", "connection": "live"}})
        symbol = result["symbols"][0]
        self.assertEqual(symbol["history_sessions"], 30)
        self.assertEqual(symbol["missing_history_dates"], [SESSION["prior_dates"][0]])
        self.assertEqual(symbol["minute_gaps"], 1)
        self.assertTrue(symbol["missing_history"])
        self.assertIn("30-second alert limit", " ".join(symbol["issues"]))
        self.assertEqual(next(row for row in result["checks"] if row["name"] == "Data quality")["status"], "warning")


if __name__ == "__main__":
    unittest.main()
