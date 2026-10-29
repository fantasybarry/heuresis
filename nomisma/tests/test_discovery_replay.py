"""Entry gating, deadline exit and wick exit of the discovery replay on synthetic minute bars."""
from datetime import datetime, timedelta
import unittest

from nomisma import discovery_data as data
from nomisma import discovery_replay as replay

T0 = datetime(2025, 10, 7, 9, 47, tzinfo=data.NY)
CUTOFF = datetime(2025, 10, 7, 13, 0, tzinfo=data.NY)


def bars(*minutes, o=5.0, h=5.1, l=4.95, c=5.05):
    return [{"m": T0 + timedelta(minutes=m), "o": o, "h": h, "l": l, "c": c, "v": 1000} for m in minutes]


class TradeTest(unittest.TestCase):
    def test_halt_gap_and_limit_keep_counterfactual(self):
        decision = T0 + timedelta(minutes=1)
        halted = replay.trade(bars(0, 10, *range(11, 30)), 1, decision, 4.0, CUTOFF)
        self.assertEqual((halted["status"], halted["exit_reason"]), ("suspected_halt", "time"))
        late = replay.trade(bars(0, 5, *range(6, 30)), 1, decision, 4.0, CUTOFF)
        self.assertEqual(late["status"], "filled")  # four missing minutes is not a suspected halt
        dear = replay.trade(bars(0, *range(1, 30)), 1, decision, 4.0, CUTOFF, limit=4.9)
        self.assertEqual(dear["status"], "above_limit")

    def test_missing_deadline_minute_exits_at_next_print(self):
        path = bars(0, *range(1, 12)) + bars(20, o=4.5, h=4.6, l=4.4, c=4.55)
        result = replay.trade(path, 1, T0 + timedelta(minutes=1), 4.0, CUTOFF)
        self.assertEqual((result["exit"], result["exit_at"]), (4.5, "10:07"))
        complete = replay.trade(bars(*range(0, 30)), 1, T0 + timedelta(minutes=1), 4.0, CUTOFF)
        self.assertEqual((complete["exit"], complete["exit_at"]), (5.05, "10:03"))

    def test_wick_exit_on_pullback_candle(self):
        path = bars(0, 1, 2) + bars(3, o=4.9, h=5.3, l=4.85, c=4.9) + bars(4, o=4.88, h=4.9, l=4.8, c=4.85) + bars(*range(5, 30))
        result = replay.trade(path, 1, T0 + timedelta(minutes=1), 4.0, CUTOFF, level=5.0, wick=0.5)
        self.assertEqual((result["exit_reason"], result["exit"], result["exit_at"]), ("wick", 4.88, "09:51"))
        plain = replay.trade(path, 1, T0 + timedelta(minutes=1), 4.0, CUTOFF)
        self.assertEqual(plain["exit_reason"], "time")


class ReclaimTest(unittest.TestCase):
    def path(self, pullback_high=5.12, gap=0):
        return (bars(0) + bars(1, h=5.3, c=5.2) + bars(2, o=5.1, h=pullback_high, l=4.9, c=4.95)
                + bars(3 + gap, o=4.96, h=5.08, l=4.92, c=5.06) + bars(4 + gap, o=5.06, h=5.1, l=5.0, c=5.08)
                + bars(5 + gap, o=5.1, h=5.35, l=5.05, c=5.3) + bars(*range(6 + gap, 30)))

    def test_reclaim_enters_next_open_and_exits_at_target(self):
        result = replay.reclaim(self.path(), 0, 5.0, CUTOFF)
        self.assertEqual((result["status"], result["entry"], result["entry_at"]), ("filled", 5.06, "09:51"))
        self.assertAlmostEqual(result["stop"], 4.89)
        self.assertEqual((result["target"], result["exit_reason"], result["exit"]), (5.3, "target", 5.3))

    def test_long_pullback_wick_and_slow_reclaim_are_no_trade(self):
        self.assertEqual(replay.reclaim(self.path(pullback_high=5.3), 0, 5.0, CUTOFF)["status"], "wick_skip")
        # two silent minutes after the pullback close: three minutes at/below resistance before the reclaim
        self.assertEqual(replay.reclaim(self.path(gap=2), 0, 5.0, CUTOFF)["status"], "failed_reclaim")
        self.assertEqual(replay.reclaim(bars(*range(0, 30)), 0, 5.0, CUTOFF)["status"], "no_pullback")

    def test_stop_fills_before_target_in_the_same_minute(self):
        path = bars(0, 1) + bars(2, o=5.0, h=5.6, l=4.0, c=5.0) + bars(*range(3, 30))
        result = replay.trade(path, 1, T0 + timedelta(minutes=1), 4.5, CUTOFF, target=5.5)
        self.assertEqual((result["exit_reason"], result["exit"]), ("stop", 4.5))


class OutcomeTest(unittest.TestCase):
    def test_missing_minutes_extend_a_streak_below_resistance(self):
        # breakout at 5.05 over 5.0; one close at/below, three silent minutes, then recovery: four minutes below
        path = bars(*range(0, 3)) + bars(3, c=4.98) + bars(*range(7, 20), c=5.2)
        times = [bar["m"] for bar in path]
        self.assertFalse(replay.outcome(path, times, 0, 5.0, 4.0, 0.05)["continuation"])
        dense = bars(*range(0, 3)) + bars(3, c=4.98) + bars(*range(4, 20), c=5.2)
        self.assertTrue(replay.outcome(dense, [bar["m"] for bar in dense], 0, 5.0, 4.0, 0.05)["continuation"])


if __name__ == "__main__":
    unittest.main()
