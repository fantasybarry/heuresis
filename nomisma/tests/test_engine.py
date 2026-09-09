"""Financial edge cases and observable screener behavior; no network access."""

import copy
import json
import math
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from nomisma.engine import DEFAULT_FILTERS, PRESETS, _atr, _ema, _rsi, screen, validate_filters


def make_bars(count=240, slope=0.12):
    bars = []
    session = date(2024, 1, 2)
    while len(bars) < count:
        if session.weekday() < 5:
            index = len(bars)
            price = 50 + slope * index + 0.7 * math.sin(index * 0.8)
            bars.append({"date": session.isoformat(), "open": price - 0.1,
                         "high": price + 0.8, "low": price - 0.8,
                         "close": price, "volume": 1000000})
        session += timedelta(days=1)
    return bars


def dataset(*assets, benchmark=True):
    if not assets:
        assets = ({"symbol": "ACME", "name": "Acme", "sector": "Technology", "bars": make_bars()},)
    spy_bars = make_bars(slope=0.04)
    return {"source": "csv", "label": "Test prices", "feed": "csv",
            "as_of": max(asset["bars"][-1]["date"] for asset in assets if asset["bars"]),
            "assets": list(assets), "warnings": [],
            "benchmark": {"symbol": "SPY", "bars": spy_bars} if benchmark else None}


def broad_filters(**overrides):
    filters = {"min_price": 0, "max_price": 10000000, "min_avg_volume": 0,
               "min_relative_volume": 0, "min_rsi": 0, "max_rsi": 100,
               "min_score": 0, "above_sma50": False, "above_sma200": False,
               "positive_macd": False, "min_return_20d": -100, "max_atr_pct": 1000}
    filters.update(overrides)
    return filters


class IndicatorTests(unittest.TestCase):
    def test_wilder_rsi_hand_calculation_and_smoothing(self):
        # Initial changes +2,-1,+3: gain=5/3, loss=1/3 => RSI=83.3333.
        # Next change -2: gain=10/9, loss=8/9 => RSI=55.5556.
        self.assertAlmostEqual(_rsi([10, 12, 11, 14], 3), 100 * 5 / 6)
        self.assertAlmostEqual(_rsi([10, 12, 11, 14, 12], 3), 100 * 5 / 9)

    def test_rsi_flat_all_gains_and_all_losses(self):
        self.assertEqual(_rsi([10.0] * 40), 50)
        self.assertEqual(_rsi(list(range(1, 41))), 100)
        self.assertEqual(_rsi(list(range(40, 0, -1))), 0)

    def test_ema_uses_sma_seed_and_exponential_smoothing(self):
        self.assertEqual(_ema([2, 4, 6, 10, 8], 3), [None, None, 4, 7, 7.5])

    def test_atr_accounts_for_gaps_and_uses_wilder_smoothing(self):
        bars = [{"high": 10, "low": 8, "close": 9},
                {"high": 15, "low": 14, "close": 14.5},  # TR 6, not 1
                {"high": 13, "low": 12, "close": 12.5},  # TR 2.5
                {"high": 13, "low": 12, "close": 12.5},  # TR 1
                {"high": 14, "low": 12, "close": 13}]   # TR 2
        self.assertAlmostEqual(_atr(bars[:4], 3), 9.5 / 3)
        self.assertAlmostEqual(_atr(bars, 3), ((9.5 / 3) * 2 + 2) / 3)

    def test_indicator_warmup_is_required(self):
        for function, values in ((_rsi, [1] * 14), (_atr, [{}] * 14), (_ema, [1] * 2)):
            with self.subTest(function=function.__name__), self.assertRaises(ValueError):
                function(values, 14 if function != _ema else 3)


class FilterTests(unittest.TestCase):
    def test_defaults_and_presets_are_valid_and_independent(self):
        result = validate_filters({})
        self.assertEqual(result, DEFAULT_FILTERS)
        result["sectors"].append("Changed")
        self.assertEqual(DEFAULT_FILTERS["sectors"], [])
        for preset in PRESETS:
            self.assertEqual(validate_filters(preset["filters"]), preset["filters"])

    def test_rejects_unknown_nonfinite_and_inconsistent_values(self):
        cases = [{"surprise": 1}, {"min_price": float("nan")},
                 {"max_rsi": float("inf")}, {"min_score": True},
                 {"min_price": "10"}, {"max_price": 9},
                 {"min_rsi": 76}, {"above_sma50": 1},
                 {"min_avg_volume": -1}, {"max_atr_pct": -1},
                 {"min_score": 101}, {"sectors": "Technology"},
                 {"sectors": [""]}, {"sectors": [None]},
                 {"min_price": 10 ** 1000}, {"sectors": ["Tech\nBad"]}]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                validate_filters(case)

    def test_normalizes_sectors_without_mutating_input(self):
        original = {"sectors": [" Technology ", "technology", "Energy"]}
        self.assertEqual(validate_filters(original)["sectors"], ["Energy", "Technology"])
        self.assertEqual(original["sectors"][0], " Technology ")


class ScreeningTests(unittest.TestCase):
    def test_exact_prior_volume_high_and_return_windows(self):
        data = dataset()
        bars = data["assets"][0]["bars"]
        bars[-1]["volume"] = 3000000
        bars[-1]["high"] = 999  # Must not enter the prior-high comparison.
        result = screen(data, broad_filters())["results"][0]
        metrics = result["metrics"]
        self.assertEqual(metrics["avg_volume"], 1000000)
        self.assertEqual(metrics["relative_volume"], 3)
        expected_return = (bars[-1]["close"] / bars[-21]["close"] - 1) * 100
        expected_breakout = (bars[-1]["close"] / max(bar["high"] for bar in bars[-21:-1]) - 1) * 100
        self.assertAlmostEqual(metrics["return_20d"], expected_return, places=5)
        self.assertAlmostEqual(metrics["breakout_distance"], expected_breakout, places=5)

    def test_macd_linear_trend_and_signal_have_known_steady_value(self):
        data = dataset()
        bars = data["assets"][0]["bars"]
        for i, bar in enumerate(bars):
            bar.update(open=50 + i, close=50 + i, high=51 + i, low=49 + i)
        metrics = screen(data, broad_filters())["results"][0]["metrics"]
        # On a linear +1/session series, EMA12 lags 5.5 and EMA26 lags 12.5.
        self.assertAlmostEqual(metrics["macd"], 7)
        self.assertAlmostEqual(metrics["macd_signal"], 7)
        self.assertAlmostEqual(metrics["macd_histogram"], 0)

    def test_scores_sum_to_total_and_ties_sort_by_symbol(self):
        shared = make_bars()
        data = dataset({"symbol": "ZZZ", "bars": shared}, {"symbol": "AAA", "bars": shared})
        result = screen(data, broad_filters())
        self.assertEqual([row["symbol"] for row in result["results"]], ["AAA", "ZZZ"])
        for row in result["results"]:
            self.assertAlmostEqual(row["score"], sum(signal["points"] for signal in row["signals"]))
            self.assertEqual(sum(signal["max_points"] for signal in row["signals"]), 100)
            self.assertTrue(all(0 <= signal["points"] <= signal["max_points"] for signal in row["signals"]))
        self.assertEqual(result["eligible_count"], 2)
        self.assertEqual(result["matched_count"], 2)

    def test_json_safe_deterministic_and_does_not_mutate_inputs(self):
        data = dataset()
        saved = copy.deepcopy(data)
        filters = broad_filters()
        self.assertEqual(screen(data, filters), screen(data, filters))
        json.dumps(screen(data, filters), allow_nan=False)
        self.assertEqual(data, saved)

    def test_missing_benchmark_is_null_and_receives_no_unearned_points(self):
        result = screen(dataset(benchmark=False), broad_filters())
        stock = result["results"][0]
        self.assertIsNone(result["market"])
        self.assertIsNone(stock["metrics"]["relative_strength"])
        self.assertEqual(stock["signals"][3]["points"], 0)
        self.assertTrue(any("SPY" in risk for risk in stock["risks"]))

    def test_relative_strength_requires_matching_session_dates(self):
        data = dataset()
        stock = screen(data, broad_filters())["results"][0]
        benchmark_return = (data["benchmark"]["bars"][-1]["close"] / data["benchmark"]["bars"][-21]["close"] - 1) * 100
        self.assertAlmostEqual(stock["metrics"]["relative_strength"], stock["metrics"]["return_20d"] - benchmark_return, places=5)
        del data["benchmark"]["bars"][-10]
        stock = screen(data, broad_filters())["results"][0]
        self.assertIsNone(stock["metrics"]["relative_strength"])

    def test_down_day_high_volume_does_not_earn_bullish_volume_points(self):
        data = dataset()
        previous = data["assets"][0]["bars"][-2]["close"]
        data["assets"][0]["bars"][-1].update(open=previous, high=previous + 1,
                                                  low=previous - 2, close=previous - 1, volume=10000000)
        stock = screen(data, broad_filters())["results"][0]
        self.assertEqual(stock["signals"][2]["points"], 0)
        self.assertNotEqual(stock["setup"], "Volume breakout")

    def test_invalid_bars_and_duplicate_symbols_are_excluded(self):
        cases = [lambda bars: bars[-1].update(close=float("nan")),
                 lambda bars: bars[-1].update(low=1000),
                 lambda bars: bars[-1].update(volume=-1),
                 lambda bars: bars[-1].update(date=bars[-2]["date"]),
                 lambda bars: bars.reverse(),
                 lambda bars: bars[-1].update(close=0),
                 lambda bars: bars[-1].update(date="2099-01-01"),
                 lambda bars: bars[-1].update(open=True)]
        for mutate in cases:
            data = dataset()
            mutate(data["assets"][0]["bars"])
            result = screen(data, broad_filters())
            self.assertEqual(result["rejected"], {"invalid_data": 1})
            self.assertEqual(result["matched_count"], 0)
        result = screen(dataset({"symbol": "AAA", "bars": make_bars()},
                                {"symbol": "aaa", "bars": make_bars()}), broad_filters())
        self.assertEqual(result["rejected"], {"duplicate_symbol": 2})

    def test_requires_201_bars_and_nonzero_baseline_volume(self):
        data = dataset(benchmark=False)
        data["assets"][0]["bars"] = data["assets"][0]["bars"][-200:]
        self.assertEqual(screen(data, broad_filters())["rejected"], {"insufficient_history": 1})
        data = dataset()
        for bar in data["assets"][0]["bars"][-21:-1]:
            bar["volume"] = 0
        self.assertEqual(screen(data, broad_filters())["rejected"], {"unavailable_volume": 1})

    def test_exactly_201_bars_are_sufficient(self):
        data = dataset()
        data["assets"][0]["bars"] = data["assets"][0]["bars"][-201:]
        self.assertEqual(screen(data, broad_filters())["matched_count"], 1)

    def test_extreme_numeric_inputs_cannot_escape_as_nonfinite_json(self):
        data = dataset()
        for bar in data["assets"][0]["bars"][-21:-1]:
            bar["volume"] = 5e-324
        result = screen(data, broad_filters())
        self.assertEqual(result["rejected"], {"invalid_data": 1})
        json.dumps(result, allow_nan=False)
        data = dataset()
        for bar in data["benchmark"]["bars"]:
            bar.update(open=5e-324, close=5e-324, high=5e-324, low=5e-324)
        result = screen(data, broad_filters())
        self.assertIsNone(result["market"])
        self.assertEqual(result["matched_count"], 1)
        json.dumps(result, allow_nan=False)

    def test_stale_assets_excluded_and_overall_staleness_is_flagged(self):
        data = dataset()
        stale = copy.deepcopy(data["assets"][0])
        stale["symbol"] = "OLD"
        stale["bars"].pop()
        data["assets"].append(stale)
        with patch("nomisma.engine._today", return_value=date.fromisoformat(data["as_of"]) + timedelta(days=6)):
            result = screen(data, broad_filters())
        self.assertEqual(result["rejected"], {"stale_symbol": 1})
        self.assertEqual(result["eligible_count"], 1)
        self.assertTrue(any("stale" in warning for warning in result["warnings"]))
        with patch("nomisma.engine._today", return_value=date.fromisoformat(data["as_of"]) + timedelta(days=5)):
            result = screen(data, broad_filters())
        self.assertFalse(any("Data is stale" in warning for warning in result["warnings"]))

    def test_stale_benchmark_does_not_use_an_unequal_return_window(self):
        data = dataset()
        data["benchmark"]["bars"].pop()
        result = screen(data, broad_filters())
        self.assertIsNone(result["market"])
        self.assertIsNone(result["results"][0]["metrics"]["relative_strength"])

    def test_filter_counts_are_nonexclusive_and_sector_case_insensitive(self):
        result = screen(dataset(), broad_filters(min_price=500, min_avg_volume=2000000, sectors=["energy"]))
        self.assertEqual(result["eligible_count"], 1)
        self.assertEqual(result["matched_count"], 0)
        self.assertEqual(result["rejected"], {"average_volume": 1, "price": 1, "sector": 1})
        self.assertEqual(screen(dataset(), broad_filters(sectors=["technology"]))["matched_count"], 1)

    def test_filters_use_unrounded_values(self):
        data = dataset()
        self.assertEqual(screen(data, broad_filters(min_relative_volume=1.0000001))["matched_count"], 0)
        self.assertEqual(screen(data, broad_filters(min_relative_volume=1))["matched_count"], 1)

    def test_flat_prices_are_finite_and_not_a_strong_bullish_signal(self):
        data = dataset()
        for bar in data["assets"][0]["bars"]:
            bar.update(open=50, high=50, low=50, close=50)
        result = screen(data, broad_filters())
        row = result["results"][0]
        self.assertEqual(row["metrics"]["rsi"], 50)
        self.assertEqual(row["metrics"]["atr"], 0)
        self.assertLessEqual(row["score"], 10)
        json.dumps(result, allow_nan=False)

    def test_empty_universe_and_invalid_dataset(self):
        data = dataset()
        data["assets"] = []
        self.assertEqual(screen(data, {})["matched_count"], 0)
        for change in ({"as_of": "2024-02-30"}, {"as_of": "2099-01-01"},
                       {"source": "pretend"}, {"assets": {}}, {"warnings": "bad"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                screen(dict(data, **change), {})


if __name__ == "__main__":
    unittest.main()
