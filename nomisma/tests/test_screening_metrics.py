"""Offline metric formulas, missing-history behavior, and ranking coverage."""

from datetime import date, timedelta
import unittest

from nomisma.screening_metrics import history_metrics, rank_rows, RANKING_WEIGHTS


SESSION = "2026-09-10"


def daily_bars(count=280, multiplier=1, volume=1000):
    days, cursor = [], date.fromisoformat(SESSION) - timedelta(days=1)
    while len(days) < count:
        if cursor.weekday() < 5:
            days.append(cursor.isoformat())
        cursor -= timedelta(days=1)
    values, close = [], 100.0
    for index, day in enumerate(reversed(days)):
        change = (0.003 if index % 2 else -0.002) * multiplier
        close *= 1 + change
        values.append({"date": day, "open": close, "high": close + 1, "low": close - 1,
                       "close": close, "volume": volume + index})
    return values


class HistoricalMetricTests(unittest.TestCase):
    def test_exact_volume_windows_beta_and_current_future_exclusion(self):
        stock, spy = daily_bars(multiplier=2), daily_bars()
        future = dict(stock[-1], date=SESSION, volume=10**9, close=10000, high=10001)
        result = history_metrics(stock + [future], spy, SESSION, previous_session_date="2026-09-09")
        self.assertAlmostEqual(result["avg_volume_3m"], sum(bar["volume"] for bar in stock[-63:]) / 63)
        self.assertAlmostEqual(result["avg_daily_volume"], sum(bar["volume"] for bar in stock[-20:]) / 20)
        self.assertAlmostEqual(result["beta"], 2)
        self.assertEqual(result["beta_observations"], 252)
        self.assertEqual(result["history_as_of"], "2026-09-09")
        self.assertEqual(result["history_sessions"], 280)
        self.assertTrue(all(value["available"] for value in result["metric_availability"].values()))

    def test_wilder_atr_initial_average_then_smoothing(self):
        bars = daily_bars(16)
        for bar in bars:
            bar.update(open=100, high=103, low=97, close=100)
        bars[-1].update(high=110, low=90)
        result = history_metrics(bars, bars, SESSION)
        self.assertEqual(result["atr"], 7)
        self.assertEqual(result["atr_pct"], 7)
        self.assertIsNone(result["avg_daily_volume"])
        self.assertIsNone(result["beta"])

    def test_stale_history_never_relabels_older_baseline(self):
        stock, spy = daily_bars(), daily_bars()
        result = history_metrics(stock[:-1], spy, SESSION)
        self.assertEqual(result["history_as_of"], stock[-2]["date"])
        self.assertEqual(result["history_expected_as_of"], stock[-1]["date"])
        for field in ("avg_volume_3m", "avg_daily_volume", "beta", "atr", "atr_pct"):
            self.assertIsNone(result[field])
            self.assertIn("previous exchange session", result["metric_availability"][field]["reason"])
        both_stale = history_metrics(stock[:-1], spy[:-1], SESSION)
        self.assertIsNone(both_stale["avg_daily_volume"])
        self.assertEqual(both_stale["history_expected_as_of"], "2026-09-09")

    def test_missing_recent_session_withholds_affected_windows_and_atr(self):
        stock, spy = daily_bars(100), daily_bars(100)
        stock.pop(-30)
        result = history_metrics(stock, spy, SESSION)
        self.assertIsNone(result["avg_volume_3m"])
        self.assertIsNotNone(result["avg_daily_volume"])
        self.assertIsNone(result["atr"])
        self.assertEqual(result["beta_observations"], 97)
        self.assertAlmostEqual(result["beta"], 1)

    def test_short_spy_calendar_does_not_certify_sixty_three_sessions(self):
        bars = daily_bars(100)
        result = history_metrics(bars, bars[-20:], SESSION, previous_session_date="2026-09-09")
        self.assertIsNone(result["avg_volume_3m"])
        self.assertIsNotNone(result["avg_daily_volume"])
        self.assertIsNone(result["atr"])
        self.assertIsNone(result["beta"])
        missing = history_metrics(bars, [], SESSION, previous_session_date="2026-09-09")
        self.assertTrue(all(missing[field] is None for field in ("avg_volume_3m", "avg_daily_volume", "atr", "beta")))

    def test_invalid_duplicates_and_constant_benchmark_do_not_create_false_metrics(self):
        stock, spy = daily_bars(80), daily_bars(80)
        for bar in spy:
            bar.update(open=100, high=101, low=99, close=100)
        result = history_metrics(stock, spy, SESSION)
        self.assertIsNone(result["beta"])
        self.assertEqual(result["beta_observations"], 79)
        malformed = dict(stock[-1], volume=float("nan"))
        conflicting = dict(stock[-1], volume=123456)
        result = history_metrics(stock + [malformed, conflicting], spy, SESSION)
        self.assertIsNone(result["avg_daily_volume"])
        self.assertEqual(result["history_sessions"], 79)
        with self.assertRaises(ValueError):
            history_metrics(stock, spy, "not-a-date")


class RankingTests(unittest.TestCase):
    def row(self, symbol, value=1):
        return dict({field: value for field in RANKING_WEIGHTS}, symbol=symbol)

    def test_fixed_weights_and_inverse_spread_favor_liquidity_and_volatility(self):
        low, high = self.row("LOW"), self.row("HIGH", 2)
        high["spread_pct"] = .5
        rows = rank_rows([low, high])
        self.assertEqual([row["symbol"] for row in rows], ["LOW", "HIGH"])
        self.assertEqual(high["liquidity_volatility_score"], 100)
        self.assertEqual(low["liquidity_volatility_score"], 0)
        self.assertEqual(high["rank"], 1)
        self.assertEqual(sum(part["points"] for part in high["ranking_components"].values()), 100)

    def test_missing_metrics_receive_zero_without_rejection_or_denominator_inflation(self):
        complete, missing = self.row("FULL"), {"symbol": "MISSING", "day_volume": 1000}
        rows = rank_rows([complete, missing])
        self.assertEqual(len(rows), 2)
        self.assertEqual(missing["liquidity_volatility_score"], 15)
        self.assertEqual(missing["ranking_available_metrics"], 1)
        self.assertEqual(len(missing["ranking_missing_metrics"]), 6)
        self.assertEqual(missing["ranking_components"]["atr_pct"]["points"], 0)
        self.assertGreater(complete["liquidity_volatility_score"], missing["liquidity_volatility_score"])

    def test_negative_beta_stale_inputs_and_nonfinite_values_cannot_boost_score(self):
        row = self.row("TEST")
        row.update(beta=-2, spread_pct=.001, spread_fresh=False, day_volume=10**12,
                   day_relative_volume=1000, day_volume_fresh=False, atr_pct=float("nan"))
        rank_rows([row])
        self.assertEqual(row["ranking_components"]["beta"]["points"], 0)
        self.assertTrue(row["ranking_components"]["beta"]["available"])
        for field in ("spread_pct", "day_volume", "day_relative_volume", "atr_pct"):
            self.assertFalse(row["ranking_components"][field]["available"])
            self.assertEqual(row["ranking_components"][field]["points"], 0)
        self.assertEqual(row["liquidity_volatility_score"], 20)

    def test_ties_use_symbol_order_and_equal_values_have_equal_points(self):
        first, second = self.row("ZZZ"), self.row("AAA")
        rank_rows([first, second])
        self.assertEqual(first["liquidity_volatility_score"], second["liquidity_volatility_score"])
        self.assertEqual((first["rank"], second["rank"]), (2, 1))

    def test_rank_is_total_day_volume_high_to_low(self):
        busy, volatile, stale = self.row("BUSY"), self.row("VOLAT", 5), self.row("STALE")
        busy["day_volume"], volatile["day_volume"], stale["day_volume"] = 50e6, 10e6, 99e6
        stale["day_volume_fresh"] = False
        rank_rows([volatile, busy, stale])
        self.assertGreater(volatile["liquidity_volatility_score"], busy["liquidity_volatility_score"])
        self.assertEqual((busy["rank"], volatile["rank"], stale["rank"]), (1, 2, 3))


if __name__ == "__main__":
    unittest.main()
