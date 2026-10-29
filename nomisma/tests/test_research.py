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
    def setUp(self):
        eligibility = patch("nomisma.instruments.stock_symbols")
        allowed = eligibility.start().return_value
        allowed.__contains__.return_value = True
        self.addCleanup(eligibility.stop)
        history = patch.object(live, "screening_history", return_value={})
        self.history_mock = history.start()
        self.addCleanup(history.stop)
        # Regular-session minute bars for the volume minimum; extended-hours fallbacks use the real loader.
        self.regular = {}
        real_history = live._history

        def minute_history(symbols, session, days, now, feed, headers, stop, timeframe, *args, **kwargs):
            if timeframe == "1Min" and not args and not kwargs:
                return {symbol: [{"volume": self.regular.get(symbol, 1e12)}] for symbol in symbols}
            return real_history(symbols, session, days, now, feed, headers, stop, timeframe, *args, **kwargs)
        regular = patch.object(live, "_history", side_effect=minute_history)
        regular.start()
        self.addCleanup(regular.stop)

    def test_volume_minimum_uses_regular_session_volume_not_premarket(self, unused_now):
        def get(url, params, headers, stop_event=None):
            if url.endswith("/calendar"):
                return calendar()
            return {symbol: stock(volume=9000000) for symbol in params["symbols"].split(",")}

        self.regular = {"PRE": 4000000, "REG": 6000000}  # PRE's total day volume is mostly premarket
        with patch.object(live, "_get_json", side_effect=get):
            result = research.discover({"source": "alpaca", "universe": "custom", "symbols": ["PRE", "REG"],
                                        "min_day_volume": 5000000})
        self.assertEqual([row["symbol"] for row in result["rows"]], ["REG"])
        self.assertEqual(result["rows"][0]["regular_volume"], 6000000)

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

    def test_lenient_default_keeps_decliners_and_saved_filter_still_applies(self, unused_now):
        self.assertEqual(research.default_discovery()["min_change_pct"], -100)
        data = {"DOWN": stock(price=1.9), "UP": stock(price=2.2)}
        with patch.object(research, "_calendar", return_value=(SESSION, set())), patch.object(live, "_get_json", return_value=data):
            result = research.discover({"source": "alpaca", "universe": "custom", "symbols": list(data)})
            filtered = research.discover({"source": "alpaca", "universe": "custom", "symbols": list(data), "min_change_pct": 0})
        self.assertEqual({row["symbol"] for row in result["rows"]}, set(data))
        self.assertEqual([row["symbol"] for row in filtered["rows"]], ["UP"])

    def test_ranking_enriches_pool_before_final_limit(self, unused_now):
        # The highest price gain is intentionally not the strongest liquidity
        # candidate. All matched rows must reach enrichment before limit=1.
        data = {"GAIN": stock(price=4, volume=1000), "LIQUID": stock(price=2.2, volume=1000000)}
        with patch.object(research, "_calendar", return_value=(SESSION, set())), patch.object(live, "_get_json", return_value=data):
            result = research.discover({"source": "alpaca", "universe": "custom", "symbols": list(data), "limit": 1})
        self.assertEqual(set(self.history_mock.call_args.args[0]), set(data))
        self.assertEqual(result["coverage"]["ranking_pool"], 2)
        self.assertEqual(result["coverage"]["matched"], 2)
        # Day volume and spread each carry15 points; make the rank expectation
        # explicit without relying on price gain as an undocumented tiebreaker.
        self.assertEqual(result["rows"][0]["rank"], 1)
        self.assertIn("ranking_components", result["rows"][0])
        self.assertIn("avg_volume_3m", result["rows"][0]["ranking_missing_metrics"])

    def test_current_daily_aggregate_includes_extended_volume_without_adding_minutes(self, unused_now):
        data = {"TOTAL": stock(volume=123456)}
        with patch.object(research, "_calendar", return_value=(SESSION, set())), \
                patch.object(live, "_get_json", return_value=data), patch.object(live, "extended_day_volumes") as extended:
            result = research.discover({"source": "alpaca", "universe": "custom", "symbols": ["TOTAL"]})
        extended.assert_not_called()
        row = result["rows"][0]
        self.assertEqual(row["day_volume"], 123456)
        self.assertTrue(row["day_volume_fresh"])
        self.assertEqual(row["volume_basis"], "provider_daily_aggregate")
        self.assertFalse(row["volume_partial"])

    def test_premarket_fallback_replaces_previous_daily_volume_with_partial_minutes(self, clock):
        clock.return_value = datetime(2025, 7, 3, 13, 15, tzinfo=timezone.utc)
        snapshot = stock(stamp=clock.return_value.isoformat(), volume=9000000)
        snapshot["dailyBar"]["t"] = "2025-07-02T04:00:00Z"
        fallback = {"PRE": {"volume": 25000, "as_of": "2025-07-03T13:14:00Z", "received_at": clock.return_value.isoformat()}}
        with patch.object(research, "_calendar", return_value=(SESSION, set())), \
                patch.object(live, "_get_json", return_value={"PRE": snapshot}), \
                patch.object(live, "extended_day_volumes", return_value=fallback) as extended:
            result = research.discover({"source": "alpaca", "universe": "custom", "symbols": ["PRE"]})
        extended.assert_called_once()
        self.assertEqual(result["market_phase"], "premarket")
        row = result["rows"][0]
        self.assertEqual(row["day_volume"], 25000)
        self.assertEqual(row["volume_basis"], "completed_extended_minutes")
        self.assertTrue(row["volume_partial"])
        self.assertIn("undercount", " ".join(result["warnings"]))
        self.assertEqual(result["coverage"]["extended_volume_loaded"], 1)

    def test_fallback_preserves_volume_through_and_stale_totals_cannot_rank_or_pass_positive_filter(self, clock):
        now = datetime(2025, 7, 3, 13, 15, tzinfo=timezone.utc)
        clock.return_value = now
        data = {symbol: stock(stamp=now.isoformat(), volume=500000) for symbol in ("STALE", "FRESH", "DAILY")}
        for symbol in ("STALE", "FRESH"):
            data[symbol]["dailyBar"]["t"] = "2025-07-02T04:00:00Z"
        fallback = {"STALE": {"volume": 500000, "as_of": "2025-07-03T12:00:00Z", "received_at": now.isoformat()},
                    "FRESH": {"volume": 500000, "as_of": "2025-07-03T13:14:00Z", "received_at": now.isoformat()}}
        dates, cursor = [], now.date() - timedelta(days=1)
        while len(dates) < 70:
            if cursor.weekday() < 5:
                dates.append(cursor.isoformat())
            cursor -= timedelta(days=1)
        bars = [dict(date=day, open=2, high=2.1, low=1.9, close=2, volume=1000) for day in reversed(dates)]
        self.history_mock.return_value = {symbol: bars for symbol in ("STALE", "FRESH", "DAILY", "SPY")}
        with patch.object(research, "_calendar", return_value=(SESSION, set())), \
                patch.object(live, "_get_json", return_value=data), patch.object(live, "extended_day_volumes", return_value=fallback):
            result = research.discover({"source": "alpaca", "universe": "custom", "symbols": list(data)})
            filtered = research.discover({"source": "alpaca", "universe": "custom", "symbols": list(data), "min_day_volume": 100000})
        rows = {row["symbol"]: row for row in result["rows"]}
        self.assertEqual(rows["STALE"]["volume_at"], "2025-07-03T12:00:00+00:00")
        self.assertEqual(rows["STALE"]["volume_received_at"], now.isoformat())
        self.assertFalse(rows["STALE"]["day_volume_fresh"])
        self.assertIsNone(rows["STALE"]["day_relative_volume"])
        for key in ("day_volume", "day_relative_volume"):
            self.assertEqual(rows["STALE"]["ranking_components"][key]["points"], 0)
            self.assertFalse(rows["STALE"]["ranking_components"][key]["available"])
        self.assertTrue(rows["FRESH"]["day_volume_fresh"])
        self.assertEqual(rows["FRESH"]["day_relative_volume"], 500)
        self.assertTrue(rows["DAILY"]["day_volume_fresh"])
        self.assertEqual(rows["DAILY"]["volume_at"], "2025-07-03T04:00:00+00:00")
        self.assertEqual({row["symbol"] for row in filtered["rows"]}, {"FRESH", "DAILY"})

    def test_fallback_freshness_checks_receipt_and_completed_minute_at_inclusive120_seconds(self, clock):
        now = datetime(2025, 7, 3, 13, 15, tzinfo=timezone.utc)
        clock.return_value = now
        for name, through_age, receipt_age, expected in (("BOUNDARY", 120, 120, True),
                ("OLDMINUTE", 121, 0, False), ("OLDRECEIPT", 0, 121, False),
                ("FUTURE", -1, 0, False), ("MISSING", None, 0, False)):
            with self.subTest(case=name):
                snapshot = stock(stamp=now.isoformat())
                snapshot["dailyBar"]["t"] = "2025-07-02T04:00:00Z"
                fallback = {name: {"volume": 100000,
                    "as_of": (now - timedelta(seconds=through_age)).isoformat() if through_age is not None else None,
                    "received_at": (now - timedelta(seconds=receipt_age)).isoformat()}}
                with patch.object(research, "_calendar", return_value=(SESSION, set())), \
                        patch.object(live, "_get_json", return_value={name: snapshot}), \
                        patch.object(live, "extended_day_volumes", return_value=fallback):
                    result = research.discover({"source": "alpaca", "universe": "custom", "symbols": [name]})
                self.assertEqual(result["rows"][0]["day_volume_fresh"], expected)
                self.assertEqual(result["rows"][0]["ranking_components"]["day_volume"]["available"], expected)

    def test_fallback_expiring_during_enrichment_is_retained_only_without_positive_volume_filter(self, clock):
        now = datetime(2025, 7, 3, 13, 15, tzinfo=timezone.utc)
        snapshot = stock(stamp=now.isoformat())
        snapshot["dailyBar"]["t"] = "2025-07-02T04:00:00Z"
        fallback = {"PRE": {"volume": 500000, "as_of": (now - timedelta(seconds=60)).isoformat(), "received_at": now.isoformat()}}

        def history(*args, **kwargs):
            clock.return_value = now + timedelta(seconds=61)
            return {}

        self.history_mock.side_effect = history
        for minimum in (0, 100000):
            with self.subTest(minimum=minimum):
                clock.return_value = now
                with patch.object(research, "_calendar", return_value=(SESSION, set())), \
                        patch.object(live, "_get_json", return_value={"PRE": snapshot}), \
                        patch.object(live, "extended_day_volumes", return_value=fallback):
                    result = research.discover({"source": "alpaca", "universe": "custom", "symbols": ["PRE"], "min_day_volume": minimum})
                if minimum:
                    self.assertEqual(result["rows"], [])
                    self.assertEqual(result["coverage"]["expired_volume_during_enrichment"], 1)
                    self.assertIn("minimum-volume filter", " ".join(result["warnings"]))
                else:
                    self.assertEqual(len(result["rows"]), 1)
                    self.assertFalse(result["rows"][0]["day_volume_fresh"])
                    self.assertFalse(result["rows"][0]["ranking_components"]["day_volume"]["available"])

    def test_unavailable_volume_is_lenient_only_with_zero_volume_threshold(self, unused_now):
        snapshot = stock()
        snapshot["dailyBar"]["t"] = "2025-07-02T04:00:00Z"
        with patch.object(research, "_calendar", return_value=(SESSION, set())), \
                patch.object(live, "_get_json", return_value={"UNKNOWN": snapshot}), \
                patch.object(live, "extended_day_volumes", side_effect=ValueError("Unavailable")):
            result = research.discover({"source": "alpaca", "universe": "custom", "symbols": ["UNKNOWN"]})
            filtered = research.discover({"source": "alpaca", "universe": "custom", "symbols": ["UNKNOWN"], "min_day_volume": 1})
        self.assertIsNone(result["rows"][0]["day_volume"])
        self.assertIn("day_volume", result["rows"][0]["ranking_missing_metrics"])
        self.assertEqual(filtered["rows"], [])

    def test_stale_or_invalid_quote_is_unavailable_for_ranking(self, unused_now):
        data = {"OLD": stock(), "CROSSED": stock(), "FRESH": stock()}
        data["OLD"]["latestQuote"]["t"] = (NOW - timedelta(seconds=31)).isoformat()
        data["CROSSED"]["latestQuote"].update(bp=3, ap=2)
        with patch.object(research, "_calendar", return_value=(SESSION, set())), patch.object(live, "_get_json", return_value=data):
            result = research.discover({"source": "alpaca", "universe": "custom", "symbols": list(data)})
        rows = {row["symbol"]: row for row in result["rows"]}
        for symbol in ("OLD", "CROSSED"):
            self.assertIsNone(rows[symbol]["spread"])
            self.assertIsNone(rows[symbol]["spread_pct"])
            self.assertEqual(rows[symbol]["ranking_components"]["spread_pct"]["points"], 0)
        self.assertAlmostEqual(rows["FRESH"]["spread"], .02)

    def test_enrichment_uses_complete_prior_history_and_day_volume_for_rvol(self, unused_now):
        dates, cursor = [], NOW.date() - timedelta(days=1)
        while len(dates) < 80:
            if cursor.weekday() < 5:
                dates.append(cursor.isoformat())
            cursor -= timedelta(days=1)
        bars, benchmark, stock_close, spy_close = [], [], 100, 100
        for index, day in enumerate(reversed(dates)):
            change = .003 if index % 2 else -.002
            stock_close *= 1 + 2 * change
            spy_close *= 1 + change
            bars.append(dict(date=day, open=stock_close, high=stock_close + 1, low=stock_close - 1,
                             close=stock_close, volume=1000 + index))
            benchmark.append(dict(date=day, open=spy_close, high=spy_close + 1, low=spy_close - 1,
                                  close=spy_close, volume=1000000))
        self.history_mock.return_value = {"FULL": bars, "SPY": benchmark}
        with patch.object(research, "_calendar", return_value=(SESSION, set())), \
                patch.object(live, "_get_json", return_value={"FULL": stock(volume=100000)}):
            result = research.discover({"source": "alpaca", "universe": "custom", "symbols": ["FULL"]})
        row = result["rows"][0]
        self.assertEqual(row["history_as_of"], SESSION["previous_date"])
        self.assertEqual(row["avg_volume_3m"], sum(bar["volume"] for bar in bars[-63:]) / 63)
        self.assertEqual(row["day_relative_volume"], 100000 / row["avg_daily_volume"])
        self.assertAlmostEqual(row["beta"], 2)
        self.assertIsNotNone(row["atr"])
        self.assertEqual(row["ranking_available_metrics"], 7)

    def test_quote_freshness_is_rechecked_after_history_finishes(self, clock):
        def history(*args, **kwargs):
            clock.return_value = NOW + timedelta(seconds=31)
            return {}
        self.history_mock.side_effect = history
        with patch.object(research, "_calendar", return_value=(SESSION, set())), \
                patch.object(live, "_get_json", return_value={"AGED": stock()}):
            result = research.discover({"source": "alpaca", "universe": "custom", "symbols": ["AGED"]})
        self.assertEqual(len(result["rows"]), 1)
        self.assertIsNone(result["rows"][0]["spread_pct"])
        self.assertFalse(result["rows"][0]["spread_fresh"])
        self.assertEqual(result["market_as_of"], clock.return_value.isoformat())

    def test_slow_history_refreshes_quotes_without_replacing_trade_or_volume(self, clock):
        refreshed_at = NOW + timedelta(seconds=60)
        headers = {"APCA-API-KEY-ID": "test-key", "APCA-API-SECRET-KEY": "test-secret"}
        calls = []

        def history(*args, **kwargs):
            clock.return_value = refreshed_at
            return {}

        def get(url, params, request_headers, stop_event=None):
            if url.endswith("/quotes/latest"):
                self.assertIs(request_headers, headers)
                calls.append(dict(params))
                return {"quotes": {"AGED": {"t": refreshed_at.isoformat(), "bp": 2.19, "ap": 2.21}}}
            return {"AGED": stock(volume=123456)}

        self.history_mock.side_effect = history
        with patch.object(research, "_calendar", return_value=(SESSION, set())), \
                patch.object(live, "_credentials", return_value=({"feed": "iex"}, headers, "test-account")), \
                patch.object(live, "_get_json", side_effect=get):
            result = research.discover({"source": "alpaca", "universe": "custom", "symbols": ["AGED"]})
        row = result["rows"][0]
        self.assertEqual(calls, [{"symbols": "AGED", "feed": "iex"}])
        self.assertAlmostEqual(row["spread"], .02)
        self.assertTrue(row["ranking_components"]["spread_pct"]["available"])
        self.assertEqual(row["quote_at"], refreshed_at.isoformat())
        self.assertEqual(row["trade_at"], NOW.isoformat())
        self.assertEqual(row["price"], 2.2)
        self.assertEqual(row["day_volume"], 123456)
        self.assertEqual(row["volume_received_at"], NOW.isoformat())
        self.assertEqual(result["coverage"]["quote_refresh_requested"], 1)
        self.assertEqual(result["coverage"]["quote_refresh_loaded"], 1)
        self.assertEqual(result["coverage"]["quote_refresh_unavailable"], 0)

    def test_quote_refresh_skips_fresh_quotes_and_expired_regular_trades(self, unused_clock):
        rows = [dict(symbol="FRESH", trade_at=NOW.isoformat(), quote_at=NOW.isoformat(), spread_fresh=True),
                dict(symbol="EXPIRED", trade_at=(NOW - timedelta(seconds=301)).isoformat(),
                     quote_at=None, spread_fresh=False)]
        with patch.object(live, "_get_json") as get:
            summary, warnings = research._refresh_screening_quotes(rows, SESSION, NOW, "iex", {})
        get.assert_not_called()
        self.assertEqual(summary, {"requested": 0, "loaded": 0, "unavailable": 0})
        self.assertEqual(warnings, [])

    def test_quote_refresh_rejects_invalid_prices_and_provider_timestamps(self, unused_clock):
        quotes = {
            "STALE": {"t": (NOW - timedelta(seconds=31)).isoformat(), "bp": 2, "ap": 2.1},
            "FUTURE": {"t": (NOW + timedelta(seconds=1)).isoformat(), "bp": 2, "ap": 2.1},
            "MISSING": {"bp": 2, "ap": 2.1},
            "CROSSED": {"t": NOW.isoformat(), "bp": 2.1, "ap": 2},
            "ZERO": {"t": NOW.isoformat(), "bp": 0, "ap": 2},
            "NAN": {"t": NOW.isoformat(), "bp": 2, "ap": float("nan")},
            "LOCKED": {"t": (NOW - timedelta(seconds=30)).isoformat(), "bp": 2, "ap": 2},
        }
        data = {symbol: stock() for symbol in quotes}
        for snapshot in data.values():
            snapshot.pop("latestQuote")

        def get(url, params, headers, stop_event=None):
            return {"quotes": quotes} if url.endswith("/quotes/latest") else data

        with patch.object(research, "_calendar", return_value=(SESSION, set())), \
                patch.object(live, "_get_json", side_effect=get):
            result = research.discover({"source": "alpaca", "universe": "custom", "symbols": list(data)})
        rows = {row["symbol"]: row for row in result["rows"]}
        for symbol in set(quotes) - {"LOCKED"}:
            self.assertIsNone(rows[symbol]["spread"])
            self.assertFalse(rows[symbol]["spread_fresh"])
            self.assertEqual(rows[symbol]["ranking_components"]["spread_pct"]["points"], 0)
            self.assertEqual(rows[symbol]["trade_at"], NOW.isoformat())
        self.assertEqual(rows["LOCKED"]["spread"], 0)
        self.assertTrue(rows["LOCKED"]["spread_fresh"])
        self.assertEqual(result["coverage"]["quote_refresh_unavailable"], 6)

    def test_quote_refresh_failure_preserves_candidates_with_sanitized_warning(self, unused_clock):
        snapshot = stock()
        snapshot.pop("latestQuote")

        def get(url, params, headers, stop_event=None):
            if url.endswith("/quotes/latest"):
                raise providers.ProviderError("private-token=must-not-appear")
            return {"MISSING": snapshot}

        with patch.object(research, "_calendar", return_value=(SESSION, set())), \
                patch.object(live, "_get_json", side_effect=get):
            result = research.discover({"source": "alpaca", "universe": "custom", "symbols": ["MISSING"]})
        self.assertEqual(len(result["rows"]), 1)
        self.assertIsNone(result["rows"][0]["spread_pct"])
        self.assertEqual(result["coverage"]["quote_refresh_unavailable"], 1)
        self.assertIn("Latest quote refresh left 1 of 1", " ".join(result["warnings"]))
        self.assertNotIn("must-not-appear", str(result))

    def test_quote_refresh_rechecks_response_age_after_requests_finish(self, clock):
        snapshot = stock()
        snapshot.pop("latestQuote")

        def get(url, params, headers, stop_event=None):
            if url.endswith("/quotes/latest"):
                clock.return_value = NOW + timedelta(seconds=31)
                return {"quotes": {"LATE": {"t": NOW.isoformat(), "bp": 2, "ap": 2.1}}}
            return {"LATE": snapshot}

        with patch.object(research, "_calendar", return_value=(SESSION, set())), \
                patch.object(live, "_get_json", side_effect=get):
            result = research.discover({"source": "alpaca", "universe": "custom", "symbols": ["LATE"]})
        self.assertEqual(result["coverage"]["quote_refresh_loaded"], 0)
        self.assertIsNone(result["rows"][0]["spread_pct"])
        self.assertEqual(result["market_as_of"], clock.return_value.isoformat())

    def test_quote_refresh_batches_only_selected_symbols_with_bounded_parallelism(self, unused_clock):
        rows = [dict(symbol="X%s" % index, trade_at=NOW.isoformat(), quote_at=None, spread_fresh=False)
                for index in range(101)]
        calls, active = [], [0, 0]
        lock, started = threading.Lock(), threading.Barrier(2)

        def get(url, params, headers, stop_event=None):
            symbols = params["symbols"].split(",")
            with lock:
                calls.append(symbols)
                active[0] += 1
                active[1] = max(active)
                first_pair = len(calls) <= 2
            try:
                if first_pair:
                    started.wait(timeout=2)
                self.assertEqual(params["feed"], "sip")
                return {"quotes": {symbol: {"t": NOW.isoformat(), "bp": 2, "ap": 2.1} for symbol in symbols}}
            finally:
                with lock:
                    active[0] -= 1

        with patch.object(live, "_get_json", side_effect=get):
            summary, warnings = research._refresh_screening_quotes(rows, SESSION, NOW, "sip", {})
        self.assertEqual(sorted(map(len, calls)), [1, 50, 50])
        self.assertEqual(active[1], 2)
        self.assertCountEqual([symbol for batch in calls for symbol in batch], [row["symbol"] for row in rows])
        self.assertEqual(summary, {"requested": 101, "loaded": 101, "unavailable": 0})
        self.assertEqual(warnings, [])

    def test_quote_refresh_cancellation_propagates_and_stops_sibling_requests(self, unused_clock):
        rows = [dict(symbol="X%s" % index, trade_at=NOW.isoformat(), quote_at=None, spread_fresh=False)
                for index in range(100)]
        parent_stop, sibling_cancelled = threading.Event(), threading.Event()
        started = threading.Barrier(2)

        def get(url, params, headers, stop_event=None):
            started.wait(timeout=2)
            if params["symbols"].split(",")[0] == "X0":
                raise live._Cancelled()
            if stop_event.cancelled.wait(timeout=2):
                sibling_cancelled.set()
            live._check_stop(stop_event)
            self.fail("Sibling request did not receive cancellation")

        with patch.object(live, "_get_json", side_effect=get), self.assertRaises(live._Cancelled):
            research._refresh_screening_quotes(rows, SESSION, NOW, "iex", {}, stop_event=parent_stop)
        self.assertTrue(sibling_cancelled.is_set())
        self.assertFalse(parent_stop.is_set())

    def test_large_match_set_discloses_highest_volume_enrichment_cap(self, clock):
        data = {"X%s" % index: stock(volume=1000 + index) for index in range(503)}
        quote_symbols = []

        def history(*args, **kwargs):
            clock.return_value = NOW + timedelta(seconds=60)
            return {}

        def snapshots(url, params, headers, stop_event=None):
            if url.endswith("/quotes/latest"):
                symbols = params["symbols"].split(",")
                quote_symbols.extend(symbols)
                return {"quotes": {symbol: {"t": clock.return_value.isoformat(), "bp": 2, "ap": 2.1}
                                   for symbol in symbols}}
            return {symbol: data[symbol] for symbol in params["symbols"].split(",")}

        self.history_mock.side_effect = history
        with patch.object(research, "_calendar", return_value=(SESSION, set())), patch.object(live, "_get_json", side_effect=snapshots):
            result = research.discover({"source": "alpaca", "universe": "custom", "symbols": list(data), "limit": 500})
        enriched = self.history_mock.call_args.args[0]
        self.assertEqual(len(enriched), 500)
        self.assertNotIn("X0", enriched)
        self.assertIn("X502", enriched)
        self.assertCountEqual(quote_symbols, enriched)
        self.assertEqual(result["coverage"]["quote_refresh_loaded"], 500)
        self.assertEqual(result["coverage"]["matched"], 503)
        self.assertEqual(result["coverage"]["ranking_omitted"], 3)
        self.assertIn("500 highest total-day-volume", " ".join(result["warnings"]))


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
