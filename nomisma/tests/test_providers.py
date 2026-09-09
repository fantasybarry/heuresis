"""Offline tests for data integrity and read-only Alpaca transport behavior."""

from datetime import date, datetime, timezone
import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from nomisma import providers as p


HEADER = "symbol,date,open,high,low,close,volume\n"
ENV = {"ALPACA_API_KEY": "test-key", "ALPACA_SECRET_KEY": "test-secret",
       "ALPACA_FEED": "iex", "ALPACA_PAPER": "true"}
NOW = datetime(2025, 7, 3, 17, 45, tzinfo=timezone.utc)  # 13:45 New York
CALENDAR = [{"date": "2025-07-02", "open": "09:30", "close": "16:00"},
            {"date": "2025-07-03", "open": "09:30", "close": "13:00"}]


def raw_bar(day="2025-07-03", close=103):
    return {"t": day + "T04:00:00Z", "o": 100, "h": 105,
            "l": 98, "c": close, "v": 2000000}


class DemoTests(unittest.TestCase):
    def test_reproducible_independent_synthetic_history(self):
        first = p.demo_dataset()
        second = p.demo_dataset()
        self.assertEqual(first, second)
        self.assertEqual(first["source"], "demo")
        self.assertIn("synthetic", first["label"].lower())
        self.assertEqual(first["as_of"], p.DEMO_AS_OF)
        self.assertGreaterEqual(len(first["assets"]), 36)
        self.assertLessEqual(len(first["assets"]), 50)
        for asset in first["assets"] + [first["benchmark"]]:
            self.assertGreaterEqual(len(asset["bars"]), 201)
            dates = [bar["date"] for bar in asset["bars"]]
            self.assertEqual(dates, sorted(set(dates)))
            self.assertEqual(dates[-1], p.DEMO_AS_OF)
            for bar in asset["bars"]:
                self.assertLess(date.fromisoformat(bar["date"]).weekday(), 5)
                self.assertEqual(p._bar(bar["date"], bar, "demo"), bar)
        first["assets"][0]["bars"][0]["close"] = 0
        self.assertNotEqual(first, second)


class CSVTests(unittest.TestCase):
    def test_bom_normalization_sorting_and_benchmark(self):
        data = p.parse_csv("\ufeffSymbol,DATE,Open,High,Low,Close,Volume,name,sector\n"
                           "aapl,2025-07-02,100,110,90,108,2000000,Apple,Technology\n"
                           "aapl,2025-07-01,98,104,97,100,1800000,Apple,Technology\n"
                           "SPY,2025-07-02,500,510,490,505,10000000,SPY,ETF\n")
        self.assertEqual(data["source"], "csv")
        self.assertEqual(data["as_of"], "2025-07-02")
        self.assertEqual(data["benchmark"]["symbol"], "SPY")
        self.assertEqual([asset["symbol"] for asset in data["assets"]], ["AAPL"])
        self.assertEqual(data["assets"][0]["bars"][0]["date"], "2025-07-01")
        self.assertEqual(data["assets"][0]["sector"], "Technology")

    def test_missing_benchmark_warning(self):
        data = p.parse_csv(HEADER + "AAPL,2025-07-02,100,110,90,108,2000000\n")
        self.assertIsNone(data["benchmark"])
        self.assertTrue(any("No SPY" in message for message in data["warnings"]))

    def test_duplicate_dates_are_not_silently_overwritten(self):
        line = "AAPL,2025-07-02,100,110,90,108,2000000\n"
        with self.assertRaisesRegex(ValueError, "duplicate date"):
            p.parse_csv(HEADER + line + line)

    def test_invalid_prices_volumes_dates_and_symbols(self):
        cases = [
            "AAPL,2025-07-02,nan,110,90,108,2000000",
            "AAPL,2025-07-02,100,110,90,inf,2000000",
            "AAPL,2025-07-02,100,110,90,108,-1",
            "AAPL,2025-07-02,100,110,90,108,1.5",
            "AAPL,2025-07-02,0,110,90,108,2000000",
            "AAPL,2025-07-02,100,105,90,108,2000000",
            "AAPL,2025-02-30,100,110,90,108,2000000",
            "AAPL,2025-7-2,100,110,90,108,2000000",
            "AAPL,2025-07-05,100,110,90,108,2000000",
            "=AAPL,2025-07-02,100,110,90,108,2000000",
        ]
        for line in cases:
            with self.subTest(line=line), self.assertRaises(ValueError):
                p.parse_csv(HEADER + line + "\n")

    @patch.object(p, "_now", return_value=NOW)
    def test_current_and_future_daily_rows_rejected(self, now):
        for day in ("2025-07-03", "2025-07-04"):
            with self.assertRaisesRegex(ValueError, "earlier than today"):
                p.parse_csv(HEADER + "AAPL,{},100,110,90,108,2000000\n".format(day))

    def test_header_and_row_shape_validation(self):
        for text in ("", HEADER, "symbol,date,close\n", HEADER.replace("volume", "close"),
                     HEADER + "AAPL,2025-07-02,100,110,90,108,2000000,extra\n",
                     HEADER + "AAPL,2025-07-02,100,110\n",
                     HEADER + '"AAPL,2025-07-02,100,110,90,108,2000000\n',
                     HEADER.replace("volume", "volume,unknown")):
            with self.subTest(text=text), self.assertRaises(ValueError):
                p.parse_csv(text)

    def test_size_limit_utf8_and_metadata_conflict(self):
        with patch.object(p, "MAX_CSV_BYTES", 100):
            with self.assertRaisesRegex(ValueError, "20 MB"):
                p.parse_csv("é" * 51)
        with self.assertRaisesRegex(ValueError, "inconsistent name"):
            p.parse_csv(HEADER.strip() + ",name\n"
                        "AAPL,2025-07-02,100,110,90,108,2000000,Apple\n"
                        "AAPL,2025-07-01,100,110,90,108,2000000,Other\n")


class CalendarTests(unittest.TestCase):
    def test_early_close_and_buffer(self):
        before_buffer = datetime(2025, 7, 3, 17, 29, tzinfo=timezone.utc)
        self.assertEqual(p._completed_session(CALENDAR, before_buffer), date(2025, 7, 2))
        self.assertEqual(p._completed_session(CALENDAR, NOW), date(2025, 7, 3))

    def test_winter_timezone_and_unordered_calendar(self):
        days = [{"date": "2025-01-03", "close": "16:00"},
                {"date": "2025-01-02", "close": "16:00"}]
        now = datetime(2025, 1, 3, 21, 29, tzinfo=timezone.utc)
        self.assertEqual(p._completed_session(days, now), date(2025, 1, 2))

    def test_calendar_failure_is_not_guessed(self):
        for calendar in ({}, [], [{"date": "2025-07-03", "close": "invalid"}]):
            with self.subTest(calendar=calendar), self.assertRaises(p.ProviderError):
                p._completed_session(calendar, NOW)


class AlpacaTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, ENV, clear=True)
        self.env.start()
        self.clock = patch.object(p, "_now", return_value=NOW)
        self.clock.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.clock.stop)

    def test_provider_status_does_not_expose_credentials(self):
        self.assertEqual(p.provider_status(), {"alpaca_configured": True, "feed": "iex"})
        with patch.dict(os.environ, {"ALPACA_SECRET_KEY": ""}):
            self.assertFalse(p.provider_status()["alpaca_configured"])
            with self.assertRaisesRegex(p.ProviderError, "Set ALPACA_API_KEY"):
                p.fetch_alpaca()

    def test_pagination_adjustment_cutoff_and_progress(self):
        calls = []

        def response(url, params, headers):
            calls.append((url, dict(params), dict(headers)))
            if url.endswith("calendar"):
                return CALENDAR
            if "page_token" not in params:
                return {"bars": {"AAPL": [raw_bar("2025-07-02"), raw_bar("2025-07-07")]},
                        "next_page_token": "page-two"}
            return {"bars": {"AAPL": [raw_bar()], "SPY": [raw_bar()]}, "next_page_token": None}

        progress = []
        with patch.object(p, "_get_json", side_effect=response):
            data = p.fetch_alpaca("custom", ["aapl", "AAPL"], progress.append)
        self.assertEqual(data["source"], "alpaca")
        self.assertEqual(data["as_of"], "2025-07-03")
        self.assertEqual(len(data["assets"]), 1)
        self.assertEqual([bar["date"] for bar in data["assets"][0]["bars"]], ["2025-07-02", "2025-07-03"])
        self.assertEqual(calls[1][1]["adjustment"], "split")
        self.assertEqual(calls[1][1]["timeframe"], "1Day")
        self.assertEqual(calls[1][1]["feed"], "iex")
        self.assertEqual(calls[1][1]["symbols"], "AAPL,SPY")
        self.assertLessEqual(datetime.fromisoformat(calls[1][1]["end"]), NOW)
        self.assertEqual(calls[2][1]["page_token"], "page-two")
        self.assertTrue(any("single exchange" in warning for warning in data["warnings"]))
        self.assertTrue(progress)

    def test_all_filters_assets_and_batches_without_hiding_missing_data(self):
        listing = [
            {"symbol": "AAPL", "name": "Apple Inc.", "status": "active", "tradable": True, "exchange": "NASDAQ", "class": "us_equity"},
            {"symbol": "ZZZZ", "name": "Example ETF", "status": "active", "tradable": True, "exchange": "ARCA", "class": "us_equity"},
            {"symbol": "NOPE", "status": "inactive", "tradable": True, "exchange": "NYSE"},
            {"symbol": "OTCS", "status": "active", "tradable": True, "exchange": "OTC"},
            {"symbol": "HALT", "status": "active", "tradable": False, "exchange": "AMEX"},
        ]
        batches = []

        def response(url, params, headers):
            if url.endswith("calendar"):
                return CALENDAR
            if url.endswith("assets"):
                return listing
            batches.append(params["symbols"])
            return {"bars": {symbol: [raw_bar()] for symbol in params["symbols"].split(",") if symbol != "ZZZZ"},
                    "next_page_token": None}

        with patch.object(p, "_get_json", side_effect=response), patch.object(p, "BATCH_SIZE", 2):
            data = p.fetch_alpaca("all")
        self.assertEqual(batches, ["AAPL,SPY", "ZZZZ"])
        self.assertEqual([asset["symbol"] for asset in data["assets"]], ["AAPL", "ZZZZ"])
        self.assertEqual(data["assets"][1]["bars"], [])
        self.assertTrue(any("include ETFs" in warning for warning in data["warnings"]))
        self.assertTrue(any("No completed bars" in warning for warning in data["warnings"]))
        self.assertTrue(any("Sector classifications" in warning for warning in data["warnings"]))

    def test_repeated_token_or_conflicting_bars_abort(self):
        for pages in (
            [{"bars": {"AAPL": [raw_bar()]}, "next_page_token": "same"}] * 2,
            [{"bars": {"AAPL": [raw_bar()]}, "next_page_token": "next"},
             {"bars": {"AAPL": [raw_bar(close=102)]}, "next_page_token": None}],
        ):
            with self.subTest(pages=pages), patch.object(p, "_get_json", side_effect=[CALENDAR] + pages):
                with self.assertRaises(p.ProviderError):
                    p.fetch_alpaca("custom", ["AAPL"])

    def test_invalid_universe_and_empty_results_do_not_fallback(self):
        for universe, symbols in (("wrong", None), ("custom", []), ("custom", "AAPL"),
                                  ("custom", ["AAPL/../../orders"]), ("custom", [True])):
            with self.subTest(universe=universe, symbols=symbols), patch.object(p, "_get_json") as network:
                with self.assertRaises(ValueError):
                    p.fetch_alpaca(universe, symbols)
                network.assert_not_called()
        with patch.object(p, "_get_json", side_effect=[CALENDAR, {"bars": {}, "next_page_token": None}]):
            with self.assertRaisesRegex(p.ProviderError, "no completed daily bars"):
                p.fetch_alpaca("custom", ["AAPL"])

    def test_live_account_host_and_sip(self):
        with patch.dict(os.environ, {"ALPACA_PAPER": "false", "ALPACA_FEED": "sip"}), \
                patch.object(p, "_get_json", side_effect=[CALENDAR, {"bars": {"AAPL": [raw_bar()]}}]) as network:
            data = p.fetch_alpaca("custom", ["AAPL"])
        self.assertEqual(network.call_args_list[0].args[0], "https://api.alpaca.markets/v2/calendar")
        self.assertFalse(any("single exchange" in warning for warning in data["warnings"]))
        self.assertIsNone(data["benchmark"])


class TransportTests(unittest.TestCase):
    def test_get_only_headers_and_timeout(self):
        opener = unittest.mock.Mock()
        opener.open.return_value = io.BytesIO(json.dumps({"ok": True}).encode())
        with patch.object(p, "build_opener", return_value=opener):
            self.assertEqual(p._get_json("https://data.alpaca.markets/v2/stocks/bars", {"symbols": "BRK.B,AAPL"},
                                         {"APCA-API-KEY-ID": "key"}), {"ok": True})
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertIsNone(request.data)
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 30)
        self.assertIn("BRK.B%2CAAPL", request.full_url)
        with self.assertRaises(p.ProviderError):
            p._NoRedirect().redirect_request(request, None, 302, "redirect", {}, "https://other.example")

    def test_fixed_hosts_required(self):
        for url in ("http://data.alpaca.markets/v2/stocks/bars", "https://evil.example/v2/stocks/bars",
                    "https://data.alpaca.markets.evil.example/", "https://user@data.alpaca.markets/",
                    "https://data.alpaca.markets:8443/"):
            with self.subTest(url=url), self.assertRaises(p.ProviderError):
                p._get_json(url, {}, {})

    def test_rate_limit_retry_is_bounded(self):
        opener = unittest.mock.Mock()
        opener.open.side_effect = [HTTPError("https://data.alpaca.markets", 429, "limited", {"Retry-After": "2"}, io.BytesIO()),
                                   io.BytesIO(b'{"ok": true}')]
        with patch.object(p, "build_opener", return_value=opener), patch.object(p.time, "sleep") as sleep:
            self.assertEqual(p._get_json("https://data.alpaca.markets/v2/stocks/bars", {}, {}), {"ok": True})
        self.assertEqual(opener.open.call_count, 2)
        sleep.assert_called_once_with(2.0)

    def test_network_error_redaction_and_bounded_retries(self):
        opener = unittest.mock.Mock()
        opener.open.side_effect = URLError("sensitive contents")
        with patch.object(p, "build_opener", return_value=opener), patch.object(p.time, "sleep"):
            with self.assertRaises(p.ProviderError) as caught:
                p._get_json("https://data.alpaca.markets/v2/stocks/bars", {}, {})
        self.assertEqual(opener.open.call_count, 3)
        self.assertNotIn("sensitive", str(caught.exception))

    def test_auth_error_not_retried_or_echoed(self):
        opener = unittest.mock.Mock()
        opener.open.side_effect = HTTPError("https://data.alpaca.markets", 401, "test-secret", {}, io.BytesIO())
        with patch.object(p, "build_opener", return_value=opener), patch.object(p.time, "sleep") as sleep:
            with self.assertRaisesRegex(p.ProviderError, "authentication failed") as caught:
                p._get_json("https://data.alpaca.markets/v2/stocks/bars", {}, {})
        self.assertNotIn("test-secret", str(caught.exception))
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
