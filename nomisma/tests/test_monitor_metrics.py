"""Hand-checked intraday calculations and alert safety boundaries; no I/O."""

import copy
import json
import math
import unittest
from datetime import datetime, timedelta

from nomisma.monitor_metrics import (DEFAULT_MONITOR_CONFIG, build_rows,
                                     demo_bundle, validate_monitor_config)


def fixture(step=8):
    bundle = demo_bundle(["DEMO"], step)
    return bundle, datetime.fromisoformat(bundle["as_of"])


def row(bundle, now=None, **changes):
    config = validate_monitor_config(dict({"symbols": ["DEMO"]}, **changes))
    return build_rows(bundle, config, now or datetime.fromisoformat(bundle["as_of"]))[0]


class MonitorConfigTests(unittest.TestCase):
    def test_defaults_are_independent_and_partial_updates_preserve_fields(self):
        result = validate_monitor_config({})
        self.assertEqual(result, DEFAULT_MONITOR_CONFIG)
        result["symbols"].append("NEW")
        self.assertNotIn("NEW", DEFAULT_MONITOR_CONFIG["symbols"])
        current = validate_monitor_config({"min_price": 1, "symbols": ["demo", "DEMO", " brk.b "]})
        changed = validate_monitor_config({"max_price": 4}, current)
        self.assertEqual(changed["symbols"], ["DEMO", "BRK.B"])
        self.assertEqual(changed["min_price"], 1)
        self.assertEqual(current["max_price"], 5)

    def test_rejects_unknown_malformed_nonfinite_and_invalid_ranges(self):
        bad = [None, [], {"unknown": 1}, {"source": "delayed"}, {"source": []},
               {"min_price": 0}, {"max_price": 1000001}, {"max_price": 0.1},
               {"min_price": "1"}, {"min_price": True}, {"min_price": float("nan")},
               {"min_price": 10 ** 1000}, {"max_spread_pct": float("inf")},
               {"max_spread_pct": 0}, {"max_spread_pct": 21},
               {"buy_score": 85}, {"strong_buy_score": 60}, {"strong_buy_score": 101},
               {"confirmation_bars": 1.5}, {"confirmation_bars": 0},
               {"cooldown_seconds": 29}, {"cooldown_seconds": 3601},
               {"cooldown_seconds": True}, {"cooldown_seconds": 30.0},
               {"alerts_enabled": 1}, {"symbols": "DEMO"}, {"symbols": []},
               {"symbols": ["A"] * 21}, {"symbols": [None]}, {"symbols": ["BAD TICKER"]},
               {"symbols": ["A\nB"]}, {"symbols": ["A" * 16]},
               {"symbols": ["1ABC"]}, {"symbols": ["BRK/B"]}]
        for payload in bad:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                validate_monitor_config(payload)

    def test_zero_minimum_liquidity_and_numeric_boundaries_are_valid(self):
        config = validate_monitor_config({"min_session_volume": 0, "min_relative_volume": 0,
                                          "buy_score": 0, "strong_buy_score": 100,
                                          "confirmation_bars": 5, "cooldown_seconds": 3600})
        self.assertEqual(config["min_session_volume"], 0)


class IntradayVolumeTests(unittest.TestCase):
    def test_30_prior_sessions_exclude_current_and_future_even_when_unsorted(self):
        bundle, now = fixture()
        bars = bundle["assets"][0]["bars"]
        for index, bar in enumerate(bars):
            bar["volume"] = (index + 1) * 100
        current = dict(bars[-1], date=bundle["session"]["date"], volume=999999999)
        future = dict(current, date="2026-01-01")
        bundle["assets"][0]["bars"] = [future, current] + list(reversed(bars)) + [bars[-1]]
        result = row(bundle, now)
        # There are 35 prior bars; exactly numbers 6..35 count once each.
        self.assertEqual(result["volume_30d_total"], sum(range(6, 36)) * 100)
        self.assertEqual(result["avg_volume_30d"], 2050)
        self.assertEqual(len(result["volume_history"]), 30)
        self.assertEqual(result["volume_history"][-1]["date"], "2025-05-13")

    def test_missing_30th_prior_session_is_null_and_blocks_alerts(self):
        bundle, now = fixture()
        bundle["assets"][0]["bars"] = bundle["assets"][0]["bars"][-29:]
        result = row(bundle, now)
        for key in ("volume_30d_total", "avg_volume_30d", "relative_volume"):
            self.assertIsNone(result[key])
        self.assertFalse(result["alert_eligible"])
        self.assertEqual(result["signal"], "Watch")

    def test_missing_recent_session_cannot_be_replaced_by_an_older_daily_bar(self):
        bundle, now = fixture()
        # Thirty-four daily bars remain, but one of the required recent thirty
        # is absent. Counting records alone would incorrectly accept this.
        del bundle["assets"][0]["bars"][-10]
        result = row(bundle, now)
        self.assertIsNone(result["volume_30d_total"])
        self.assertIsNone(result["avg_volume_30d"])
        self.assertEqual(len(result["volume_history"]), 29)
        self.assertFalse(result["alert_eligible"])

    def test_missing_or_malformed_calendar_baseline_cannot_enable_alerts(self):
        for dates in (None, [], ["2025-05-13"] * 30):
            bundle, now = fixture()
            bundle["session"]["prior_dates"] = dates
            result = row(bundle, now)
            self.assertIsNone(result["volume_30d_total"])
            self.assertFalse(result["alert_eligible"])

    def test_zero_daily_baseline_is_not_infinite_or_eligible(self):
        bundle, now = fixture()
        for bar in bundle["assets"][0]["bars"]:
            bar["volume"] = 0
        result = row(bundle, now)
        self.assertEqual(result["avg_volume_30d"], 0)
        self.assertIsNone(result["relative_volume"])
        self.assertFalse(result["alert_eligible"])
        json.dumps(result, allow_nan=False)

    def test_session_and_minute_relative_volume_have_different_denominators(self):
        bundle, now = fixture()
        minutes = bundle["assets"][0]["minutes"]
        for minute in minutes:
            minute["volume"] = 1000
        minutes[-1]["volume"] = 3000
        for bar in bundle["assets"][0]["bars"]:
            bar["volume"] = 200000
        result = row(bundle, now, min_session_volume=0)
        self.assertEqual(result["session_volume"], 50000)
        self.assertEqual(result["relative_volume"], 0.25)
        self.assertEqual(result["minute_relative_volume"], 3)
        self.assertEqual(result["volume_at"], (datetime.fromisoformat(minutes[-1]["t"]) + timedelta(minutes=1)).isoformat())

    def test_duplicate_out_of_order_and_late_replacement_bars_do_not_double_count(self):
        bundle, now = fixture()
        minutes = bundle["assets"][0]["minutes"]
        expected = sum(minute["volume"] for minute in minutes)
        correction = dict(minutes[5], volume=minutes[5]["volume"] + 1000)
        bundle["assets"][0]["minutes"] = list(reversed(minutes)) + [minutes[-1], correction]
        result = row(bundle, now)
        self.assertEqual(result["session_volume"], expected + 1000)
        self.assertEqual(len(result["chart"]), len(minutes))
        self.assertEqual(result["signal_bar_at"], minutes[-1]["t"])
        self.assertTrue(result["alert_eligible"])

    def test_extended_previous_day_and_unfinished_minutes_are_excluded(self):
        bundle, now = fixture()
        minutes = bundle["assets"][0]["minutes"]
        expected = sum(minute["volume"] for minute in minutes)
        opening = datetime.fromisoformat(bundle["session"]["open"])
        extra_times = [opening - timedelta(days=1), opening - timedelta(minutes=1),
                       now.replace(second=0), now + timedelta(minutes=10)]
        for stamp in extra_times:
            minutes.append(dict(minutes[0], t=stamp.isoformat(), volume=9999999))
        result = row(bundle, now)
        self.assertEqual(result["session_volume"], expected)
        self.assertEqual(len(result["chart"]), 48)
        self.assertTrue(result["alert_eligible"])

    def test_recent_missing_minute_blocks_minute_rvol_even_with_ample_history(self):
        bundle, now = fixture()
        del bundle["assets"][0]["minutes"][-5]
        result = row(bundle, now)
        self.assertIsNone(result["minute_relative_volume"])
        self.assertFalse(result["alert_eligible"])
        self.assertIn("contiguous", " ".join(result["blockers"]))

    def test_old_intraday_gap_with_recent_contiguous_minutes_withholds_session_totals(self):
        bundle, now = fixture()
        del bundle["assets"][0]["minutes"][5]
        result = row(bundle, now)
        self.assertIsNotNone(result["minute_relative_volume"])
        for key in ("session_volume", "vwap", "relative_volume", "float_turnover"):
            self.assertIsNone(result[key])
        self.assertFalse(result["alert_eligible"])
        self.assertIn("incomplete coverage", " ".join(result["blockers"]))

    def test_provider_day_volume_remains_separate_when_regular_history_is_incomplete(self):
        bundle, now = fixture()
        del bundle["assets"][0]["minutes"][5]
        snapshot = bundle["assets"][0]["snapshot"]
        snapshot["dailyBar"]["v"] = 9999999
        result = row(bundle, now)
        self.assertEqual(result["day_volume"], 9999999)
        self.assertEqual(result["day_volume_at"], now.isoformat())
        self.assertIsNone(result["session_volume"])
        self.assertIsNone(result["relative_volume"])
        self.assertFalse(result["alert_eligible"])

    def test_provider_daily_volume_date_uses_new_york_and_never_previous_day(self):
        bundle, now = fixture()
        snapshot = bundle["assets"][0]["snapshot"]
        # UTC May14 at01:00 is still May13 in NewYork.
        snapshot["dailyBar"]["t"] = "2025-05-14T01:00:00Z"
        result = row(bundle, now)
        self.assertIsNone(result["day_volume"])
        self.assertIsNone(result["day_volume_at"])
        self.assertIsNotNone(result["session_volume"])

    def test_daily_volume_receipt_time_never_uses_the_bar_period_start(self):
        bundle, now = fixture()
        snapshot = bundle["assets"][0]["snapshot"]
        del snapshot["_daily_received_at"]
        self.assertIsNone(row(bundle, now)["day_volume_at"])
        self.assertIsNotNone(row(bundle, now)["day_volume"])
        snapshot["_received_at"] = (now - timedelta(seconds=5)).isoformat()
        self.assertEqual(row(bundle, now)["day_volume_at"], snapshot["_received_at"])
        snapshot["_daily_received_at"] = (now + timedelta(seconds=1)).isoformat()
        self.assertIsNone(row(bundle, now)["day_volume_at"])

    def test_no_minutes_or_zero_baseline_never_pass_even_with_zero_volume_filter(self):
        for clear in (True, False):
            bundle, now = fixture()
            if clear:
                bundle["assets"][0]["minutes"] = []
            else:
                for minute in bundle["assets"][0]["minutes"][:-1]:
                    minute["volume"] = 0
            result = row(bundle, now, min_session_volume=0, min_relative_volume=0)
            self.assertFalse(result["alert_eligible"])
            self.assertIsNone(result["minute_relative_volume"])
            json.dumps(result, allow_nan=False)

    def test_malformed_minute_exclusion_is_visible_and_blocks(self):
        bundle, now = fixture()
        bundle["assets"][0]["minutes"][2]["volume"] = float("nan")
        result = row(bundle, now)
        self.assertFalse(result["alert_eligible"])
        self.assertIn("Malformed", " ".join(result["blockers"]))
        json.dumps(result, allow_nan=False)


class PriceAndFloatTests(unittest.TestCase):
    def test_session_vwap_uses_reported_volume_weighted_prices(self):
        bundle, now = fixture()
        minutes = bundle["assets"][0]["minutes"]
        for minute in minutes:
            minute["volume"], minute["vwap"] = 100, 1
        minutes[-1]["volume"], minutes[-1]["vwap"] = 200, 2
        result = row(bundle, now, min_session_volume=0)
        self.assertAlmostEqual(result["vwap"], 5100 / 4900)

    def test_missing_vwap_is_not_replaced_by_typical_price(self):
        bundle, now = fixture()
        del bundle["assets"][0]["minutes"][0]["vwap"]
        result = row(bundle, now)
        self.assertIsNone(result["vwap"])
        self.assertFalse(result["alert_eligible"])
        self.assertIn("actual VWAP", " ".join(result["blockers"]))

    def test_zero_volume_minute_does_not_need_vwap(self):
        bundle, now = fixture()
        bundle["assets"][0]["minutes"][0].update(volume=0, vwap=None)
        result = row(bundle, now)
        self.assertIsNotNone(result["vwap"])
        self.assertTrue(result["alert_eligible"])

    def test_gap_uses_exact_regular_open_and_split_adjusted_previous_close(self):
        bundle, now = fixture()
        asset = bundle["assets"][0]
        asset["bars"][-1].update(open=1, low=1, close=1, high=1)
        asset["minutes"][0].update(open=1.5, low=1)
        asset["snapshot"]["dailyBar"] = {"o": 0.75, "c": 1.9, "v": 9999999}
        asset["snapshot"]["prevDailyBar"] = {"c": 4}
        result = row(bundle, now)
        self.assertAlmostEqual(result["gap_pct"], 50)
        self.assertAlmostEqual(result["change_pct"], (result["price"] - 1) * 100)
        self.assertIn("corporate action", " ".join(result["warnings"]))

    def test_gap_missing_when_exact_opening_minute_is_absent(self):
        bundle, now = fixture()
        bundle["assets"][0]["minutes"].pop(0)
        result = row(bundle, now)
        self.assertIsNone(result["gap_pct"])
        self.assertIsNone(result["vwap"])
        self.assertFalse(result["alert_eligible"])
        self.assertIsNotNone(result["change_pct"])
        self.assertIn("exact regular-session opening", " ".join(result["warnings"]))

    def test_previous_session_reference_must_match_calendar_date(self):
        bundle, now = fixture()
        bundle["assets"][0]["bars"].pop()
        result = row(bundle, now)
        self.assertIsNone(result["gap_pct"])
        self.assertIsNone(result["change_pct"])
        self.assertFalse(result["alert_eligible"])

    def test_missing_float_is_null_without_inventing_an_alert_filter(self):
        bundle, now = fixture()
        bundle["assets"][0]["float"] = None
        result = row(bundle, now)
        for key in ("float_shares", "float_as_of", "float_source", "float_turnover"):
            self.assertIsNone(result[key])
        self.assertTrue(result["alert_eligible"])
        self.assertIn("Float unavailable", " ".join(result["warnings"]))

    def test_float_turnover_is_ratio_and_provenance_is_preserved(self):
        bundle, now = fixture()
        bundle.update(source="alpaca", feed="iex")
        bundle["assets"][0]["float"] = {"shares": 1000000, "as_of": "2025-05-13", "source": "Manual"}
        result = row(bundle, now, source="alpaca")
        self.assertEqual(result["float_turnover"], result["session_volume"] / 1000000)
        self.assertEqual(result["float_source"], "Manual")
        self.assertEqual(result["float_as_of"], "2025-05-13")
        self.assertIn("not provider verified", " ".join(result["warnings"]))
        self.assertIn("one exchange", " ".join(result["warnings"]))

    def test_future_invalid_or_cross_source_float_is_unusable(self):
        cases = [{"shares": 0}, {"shares": -1}, {"shares": 1.1}, {"shares": float("inf")},
                 {"shares": 10 ** 1000}, {"as_of": "2025-05-15"}, {"as_of": None},
                 {"source": "estimated"}, {"source": "FMP"}]
        for changes in cases:
            bundle, now = fixture()
            bundle["assets"][0]["float"].update(changes)
            with self.subTest(changes=changes):
                self.assertIsNone(row(bundle, now)["float_shares"])


class SetupSafetyTests(unittest.TestCase):
    def test_demo_deterministically_progresses_watch_buy_strong(self):
        self.assertEqual(demo_bundle(["DEMO"], 8), demo_bundle(["DEMO"], 8))
        for step, expected in ((0, "Watch"), (3, "Buy"), (8, "Strong buy")):
            bundle, now = fixture(step)
            result = row(bundle, now)
            self.assertEqual(result["signal"], expected)
            self.assertEqual(result["source"], "demo")
            self.assertEqual(result["feed"], "synthetic")
            self.assertGreaterEqual(result["signal_score"], 0)
            self.assertLessEqual(result["signal_score"], 100)
        earlier, later = demo_bundle(["DEMO"], 3), demo_bundle(["DEMO"], 8)
        self.assertEqual(earlier["assets"][0]["minutes"], later["assets"][0]["minutes"][:43])
        self.assertEqual(datetime.fromisoformat(later["as_of"]) - datetime.fromisoformat(earlier["as_of"]), timedelta(minutes=5))

    def test_trade_price_changes_display_but_not_completed_bar_score(self):
        bundle, now = fixture()
        initial = row(bundle, now)
        bundle["assets"][0]["snapshot"]["latestTrade"]["p"] = 1.5
        changed = row(bundle, now)
        self.assertEqual(changed["price"], 1.5)
        self.assertNotEqual(changed["change_pct"], initial["change_pct"])
        self.assertEqual(changed["signal_score"], initial["signal_score"])
        self.assertEqual(changed["signal_bar_at"], initial["signal_bar_at"])

    def test_stale_or_future_trade_or_quote_blocks_alert(self):
        for field in ("latestTrade", "latestQuote"):
            for seconds in (-31, 1):
                bundle, now = fixture()
                bundle["assets"][0]["snapshot"][field]["t"] = (now + timedelta(seconds=seconds)).isoformat()
                with self.subTest(field=field, seconds=seconds):
                    result = row(bundle, now)
                    self.assertFalse(result["alert_eligible"])
                    self.assertTrue(result["stale"])
                    self.assertEqual(result["signal"], "Watch")
                    self.assertLessEqual(datetime.fromisoformat(result["price_at"]), now)

    def test_alpaca_nanosecond_timestamps_are_accepted_on_python39(self):
        bundle, now = fixture()
        stamp = now.strftime("%Y-%m-%dT%H:%M:%S") + ".123456789Z"
        now += timedelta(seconds=1)
        bundle["assets"][0]["snapshot"]["latestTrade"]["t"] = stamp
        bundle["assets"][0]["snapshot"]["latestQuote"]["t"] = stamp
        result = row(bundle, now)
        self.assertTrue(result["alert_eligible"])
        self.assertFalse(result["stale"])
        self.assertTrue(result["price_at"].endswith(".123456+00:00"))

    def test_freshness_boundaries_are_inclusive_and_old_volume_blocks(self):
        bundle, now = fixture()
        snapshot = bundle["assets"][0]["snapshot"]
        snapshot["latestTrade"]["t"] = (now - timedelta(seconds=30)).isoformat()
        snapshot["latestQuote"]["t"] = (now - timedelta(seconds=30)).isoformat()
        self.assertTrue(row(bundle, now)["alert_eligible"])
        later = now + timedelta(seconds=111)
        snapshot["latestTrade"]["t"] = later.isoformat()
        snapshot["latestQuote"]["t"] = later.isoformat()
        result = row(bundle, later)
        self.assertFalse(result["alert_eligible"])
        self.assertIn("120 seconds", " ".join(result["blockers"]))

    def test_market_close_suppresses_even_with_fresh_prices(self):
        bundle, now = fixture(350)
        close = datetime.fromisoformat(bundle["session"]["close"])
        snapshot = bundle["assets"][0]["snapshot"]
        snapshot["latestTrade"]["t"] = close.isoformat()
        snapshot["latestQuote"]["t"] = close.isoformat()
        result = row(bundle, close)
        self.assertFalse(result["market_open"])
        self.assertFalse(result["alert_eligible"])
        self.assertFalse(result["stale"])
        self.assertEqual(result["volume_at"], close.isoformat())
        self.assertEqual(len(result["chart"]), 390)
        self.assertEqual(result["signal"], "Watch")
        self.assertIn("closed", " ".join(result["blockers"]))

    def test_missing_crossed_and_wide_quotes_do_not_pass(self):
        for quote in ({}, {"bp": 2, "ap": 1}, {"bp": 1, "ap": 2},
                      {"bp": 0, "ap": 2}, {"bp": float("nan"), "ap": 2}):
            bundle, now = fixture()
            bundle["assets"][0]["snapshot"]["latestQuote"] = dict(quote, t=now.isoformat())
            result = row(bundle, now)
            self.assertFalse(result["alert_eligible"])
            self.assertIn("spread", " ".join(result["blockers"]))
            json.dumps(result, allow_nan=False)

    def test_liquidity_price_and_enabled_settings_gate_alerts(self):
        bundle, now = fixture()
        for changes in ({"min_session_volume": 999999999}, {"max_price": 1},
                        {"min_relative_volume": 10}, {"alerts_enabled": False}):
            with self.subTest(changes=changes):
                result = row(bundle, now, **changes)
                self.assertFalse(result["alert_eligible"])
                self.assertEqual(result["signal"], "Watch")

    def test_pure_build_does_not_mutate_and_returns_only_requested_symbols(self):
        bundle = demo_bundle(["DEMO", "MOMO"])
        original = copy.deepcopy(bundle)
        rows = build_rows(bundle, validate_monitor_config({"symbols": ["DEMO"]}), datetime.fromisoformat(bundle["as_of"]))
        self.assertEqual([result["symbol"] for result in rows], ["DEMO"])
        self.assertEqual(bundle, original)
        json.dumps(rows, allow_nan=False)

    def test_invalid_now_rejected_and_unsupported_feed_blocks(self):
        bundle, now = fixture()
        with self.assertRaises(ValueError):
            row(bundle, now.replace(tzinfo=None))
        bundle.update(source="alpaca", feed="delayed_sip")
        self.assertFalse(row(bundle, now)["alert_eligible"])


if __name__ == "__main__":
    unittest.main()
