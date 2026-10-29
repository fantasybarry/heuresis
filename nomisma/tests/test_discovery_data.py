"""Offline universe construction and holdout seal tests."""
from datetime import date
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from nomisma import discovery_data as data


def fake(path, params=None):
    if path.startswith("/v2/aggs/grouped/"):
        day = path.rsplit("/", 1)[1]
        rows = [] if day == "2025-12-25" else [
            {"T": "PENNY", "o": 1, "h": 1.2, "l": 0.9, "c": 1.1, "v": 1e6, "vw": 1.05, "n": 900},
            {"T": "BIG", "o": 50, "h": 51, "l": 49, "c": 50, "v": 1e6, "vw": 50, "n": 900},
            {"T": "ETF", "o": 5, "h": 5, "l": 5, "c": 5, "v": 1e6, "vw": 5, "n": 900},
            {"T": "NEWIPO", "o": 3, "h": 3, "l": 3, "c": 3, "v": 1e5, "vw": 3, "n": 90},
            {"T": "GONE", "o": 0.3, "h": 0.3, "l": 0.2, "c": 0.2, "v": 1e5, "vw": 0.25, "n": 90}]
        return json.dumps({"resultsCount": len(rows), "results": rows}).encode()
    if params.get("active") == "false":
        return json.dumps({"results": [{"ticker": "GONE", "type": "CS", "delisted_utc": "2025-12-15T00:00:00Z"},
                                       {"ticker": "OLD", "type": "CS", "delisted_utc": "2024-01-01T00:00:00Z"}],
                           "next_url": "https://api.massive.com/never-followed"}).encode()
    tickers = ["PENNY", "BIG"] + (["NEWIPO"] if params["date"] >= "2026-01" else [])
    return json.dumps({"results": [{"ticker": t} for t in tickers]}).encode()


class Universe(unittest.TestCase):
    def test_filters_and_seal(self):
        with tempfile.TemporaryDirectory() as root:
            start, end = date(2025, 12, 1), date(2025, 12, 31)
            data.fetch_tickers(fake, root, start, end, progress=lambda _: None)
            data.fetch_grouped(fake, root, start, end, progress=lambda _: None)
            # Jan snapshot classifies a December listing.
            data.fetch_tickers(fake, root, date(2026, 1, 1), date(2026, 1, 2), progress=lambda _: None)
            for path in (Path(root) / "discovery" / "raw" / "grouped").glob("2026-*"):
                path.unlink()
            summary = data.build_universe(root)
            with gzip.open(Path(root) / "discovery" / "universe.csv.gz", "rt") as handle:
                rows = [line.split(",")[:2] for line in handle.read().splitlines()[1:]]
            self.assertEqual({t for _, t in rows}, {"PENNY", "NEWIPO", "GONE"})
            self.assertFalse([d for d, t in rows if t == "GONE" and d > "2025-12-15"])
            self.assertNotIn(["2025-12-25", "PENNY"], rows)
            self.assertEqual(summary["sessions"], 22)
            with patch.object(data, "FINALISTS", Path(root) / "FINALISTS"):
                with self.assertRaises(PermissionError):
                    data.build_universe(root, "holdout")


if __name__ == "__main__":
    unittest.main()


class Signals(unittest.TestCase):
    def session(self, premarket_from=0):
        from datetime import datetime
        from nomisma import discovery_signals as signals
        open_ = datetime(2025, 10, 6, 9, 30, tzinfo=data.NY)
        bars = []
        for minute in range(premarket_from, 90):  # 09:00-10:29
            m = open_.replace(hour=9, minute=0) + signals.timedelta(minutes=minute)
            h, c = (1.00, 0.95) if minute < 30 else (0.98, 0.97)
            if m.strftime("%H:%M") in ("09:31", "09:33"):
                h, c = 1.03, 1.02
            if m.strftime("%H:%M") == "09:50":
                h, c = 1.06, 1.05
            bars.append({"m": m, "o": c, "h": h, "l": 0.94, "c": c, "v": 100})
        close = open_.replace(hour=16, minute=0)
        return [(o["arm"], o["minute"]) for o in signals.opportunities(bars, open_, close)], signals

    def test_arms_and_active_window(self):
        found, _ = self.session()
        # 09:33 re-crosses inside the 09:31 opportunities; b6 has no crossing after 10:00.
        self.assertEqual(sorted(found), [("b3", "09:50"), ("c", "09:31"), ("c", "09:50"),
                                         ("d", "09:31"), ("d", "09:50")])

    def test_thin_premarket_blocks_rolling_arm(self):
        found, _ = self.session()
        thin, _ = self.session(premarket_from=15)  # 09:15-09:29 only: 14 of 29 window minutes missing
        self.assertIn(("d", "09:31"), found)
        self.assertNotIn(("d", "09:31"), thin)
        self.assertIn(("c", "09:31"), thin)


class Replay(unittest.TestCase):
    def bars(self, closes, lows=None, opens=None):
        from datetime import datetime, timedelta
        start = datetime(2025, 10, 6, 10, 0, tzinfo=data.NY)
        lows = lows or [c - 0.01 for c in closes]
        opens = opens or closes
        return [{"m": start + timedelta(minutes=k), "o": o, "h": max(o, c) + 0.01, "l": l, "c": c, "v": 100}
                for k, (o, c, l) in enumerate(zip(opens, closes, lows))]

    def test_net_r(self):
        from nomisma import discovery_replay as replay
        self.assertAlmostEqual(replay.net_r(1.0, 1.1, 0.9, 0), 1.0)
        self.assertAlmostEqual(replay.net_r(1.0, 1.1, 0.9, 0.01), (1.089 - 1.01) / (1.01 - 0.891))

    def test_trade_exits(self):
        from nomisma import discovery_replay as replay
        bars = self.bars([1.0] * 20 + [1.2])
        cutoff = bars[-1]["m"]
        timed = replay.trade(bars, 1, bars[1]["m"], 0.95, cutoff)
        self.assertEqual((timed["exit_reason"], timed["exit"]), ("time", 1.0))  # bar 21 is past the 15-minute hold
        gapped = self.bars([1.0, 1.0, 1.0, 0.9], opens=[1.0, 1.0, 1.0, 0.88])
        stopped = replay.trade(gapped, 1, gapped[1]["m"], 0.95, cutoff)
        self.assertEqual((stopped["exit_reason"], stopped["exit"]), ("stop", 0.88))
        self.assertEqual(replay.trade(gapped, 3, gapped[3]["m"], 0.95, cutoff)["status"], "entry_at_or_below_stop")

    def test_continuation_rules(self):
        from nomisma import discovery_replay as replay
        def label(closes):
            bars = self.bars([1.02] + closes)
            return replay.outcome(bars, [b["m"] for b in bars], 0, 1.00, 0.90, 0.05)["continuation"]
        self.assertTrue(label([0.99, 0.99, 1.03, 1.04]))
        self.assertFalse(label([0.99, 1.01, 1.05]))         # weak first recovery is not repaired
        self.assertFalse(label([0.99, 0.99, 0.99, 1.05]))   # three consecutive closes at/below resistance
        self.assertFalse(label([1.03, 1.01]))               # ends below the breakout close

    def test_prevailing_half_spread(self):
        from datetime import datetime, timezone
        from nomisma import discovery_replay as replay
        quotes = [{"t": "2025-10-06T14:00:00Z", "bp": 1.0, "ap": 1.02},
                  {"t": "2025-10-06T14:00:00.5Z", "bp": 1.0, "ap": 1.01},
                  {"t": "2025-10-06T14:00:01.123456789Z", "bp": 0, "ap": 1.0}]  # invalid bid is skipped
        moment = datetime(2025, 10, 6, 14, 0, 1, tzinfo=timezone.utc)
        self.assertAlmostEqual(replay._half_spread(quotes, moment), 0.01 / 2.01)
        self.assertAlmostEqual(replay._half_spread(quotes, moment.replace(second=0, microsecond=0)), 0.02 / 2.02)

    def test_upward_only_stops(self):
        from nomisma import discovery_replay as replay
        # Entry 1.00, stop 0.95 (1R = 0.05); runs to a 1.10 high, then falls to 0.94.
        bars = self.bars([1.0, 1.05, 1.08, 1.02, 0.94], lows=[0.99, 1.0, 1.07, 1.01, 0.93],
                         opens=[1.0, 1.0, 1.05, 1.08, 1.0])
        bars[2]["h"] = 1.10
        self.assertEqual(replay.managed_trade(bars, 0, 0.95, 0.02, "fixed"), (0.95, "stop"))
        self.assertEqual(replay.managed_trade(bars, 0, 0.95, 0.02, "breakeven_1r"), (1.0, "stop"))
        self.assertEqual(replay.managed_trade(bars, 0, 0.95, 0.02, "trail_1.5atr"), (1.07, "stop"))
