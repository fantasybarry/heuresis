"""Behavioral evidence for the offline replay's chronology and accounting."""

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import heapq
import json
import unittest

from nomisma.replay import (MINUTE, NS, _Replay, _config, _confirmation, _iso,
                            _ns, _quote_valid, default_replay_config, run_replay)


OPEN = _ns("2026-09-16T13:30:00Z")


def quote(stamp, bid=2.045, ask=2.05, size=400, ordinal=0):
    return {"t": _iso(stamp), "bp": bid, "ap": ask, "bs": size, "as": size,
            "c": ["R"], "_ordinal": ordinal}


def dataset(symbols=("AAA",), minutes=60):
    days, cursor = [], date(2026, 9, 15)
    while len(days) < 30:
        if cursor.weekday() < 5:
            days.append(cursor.isoformat())
        cursor -= timedelta(days=1)
    days.reverse()
    assets = []
    for symbol in symbols:
        bars, quotes, trades = [], [], []
        for index in range(minutes):
            close = round(1.98 + index * .001, 3)
            bars.append({"t": _iso(OPEN + index * MINUTE), "open": close,
                         "high": round(close + .04, 3), "low": round(close - .04, 3),
                         "close": close, "volume": 10000 if index < 20 else 20000,
                         "vwap": close - .005})
            ask = float((Decimal(str(close + .04)) / Decimal(".01")).to_integral_value(rounding="ROUND_FLOOR") * Decimal(".01") + Decimal(".01"))
            for seconds in (0, 3):
                stamp = OPEN + (index + 1) * MINUTE + seconds * NS
                quotes.append(quote(stamp, ask - .005, ask, ordinal=len(quotes)))
                trades.append({"t": _iso(stamp), "p": close, "s": 100, "_ordinal": len(trades)})
        daily = [{"date": day, "open": 1.9, "high": 2, "low": 1.8,
                  "close": 1.9, "volume": 200000} for day in days]
        assets.append({"symbol": symbol, "minutes": bars, "quotes": quotes,
                       "trades": trades, "daily": daily,
                       "quality": {"data_blockers": [], "daily_split_to_session_factor": 1}})
    return {"schema_version": 1, "source": "alpaca", "feed": "sip", "symbols": list(symbols),
            "sessions": [{"date": "2026-09-16", "open": _iso(OPEN),
                          "close": _iso(OPEN + minutes * MINUTE),
                          "previous_date": days[-1], "prior_dates": days,
                          "benchmark_bars": [], "assets": assets}]}


def accounting_engine(symbols=("AAA",)):
    frozen = dataset(symbols)
    engine = _Replay(frozen, _config(None, list(symbols)))
    engine.now = OPEN + 22 * MINUTE + NS
    return engine


def accounting_plan(quantity=50):
    # Researcher's accounting fixture: these supplied planner levels isolate
    # execution/bookkeeping from ATR geometry already covered by test_trade_plan.
    return {"sizing": {"quantity": quantity}, "levels": {"entry_trigger": 1.50,
            "entry_max": 1.52, "stop": 1.40},
            "expires_at": _iso(OPEN + 24 * MINUTE + NS)}


def observe(engine):
    """Advance the artificial clock to the next modeled quote observation."""
    timer = next(timer for timer in engine.timers if timer[3] == "quote_trigger")
    engine.timers.remove(timer)
    heapq.heapify(engine.timers)
    engine.now = timer[0]
    engine._control_timer(timer[3], timer[4], timer[5])


class ReplayChronologyTests(unittest.TestCase):
    def test_entire_cohort_all_minutes_determinism_and_input_immutability(self):
        frozen = dataset(("AAA", "BBB"))
        before = deepcopy(frozen)
        first = run_replay(frozen)
        second = run_replay(frozen)
        self.assertEqual(first, second)
        self.assertEqual(frozen, before)
        self.assertEqual(first["summary"]["decisions"], 120)
        self.assertEqual(first["summary"]["alerts"], 2)
        self.assertEqual(first["summary"]["entry_fills"], 2)
        self.assertEqual(first["summary"]["closed_trades"], 2)
        self.assertEqual([item["disposition"] for item in first["decisions"][-2:]], ["session_closed"] * 2)
        self.assertAlmostEqual(first["summary"]["ending_cash"] - 10000, first["summary"]["total_net_pnl"])
        json.dumps(first, allow_nan=False)

    def test_future_bars_quotes_trades_daily_cannot_change_prior_decisions(self):
        original = dataset()
        baseline = run_replay(original)
        changed = deepcopy(original)
        asset = changed["sessions"][0]["assets"][0]
        cutoff = OPEN + 25 * MINUTE + NS
        for bar in asset["minutes"]:
            if _ns(bar["t"]) >= cutoff:
                bar.update(open=99, high=100, low=98, close=99, volume=999999999, vwap=99)
        for item in asset["quotes"]:
            if _ns(item["t"]) > cutoff - NS:
                item.update(bp=99, ap=100, bs=99999, **{"as": 99999})
        for item in asset["trades"]:
            if _ns(item["t"]) > cutoff - NS:
                item["p"] = 99
        asset["daily"].append(dict(asset["daily"][-1], date="2026-09-16", volume=999999999))
        replay = run_replay(changed)
        prior = lambda result: [item for item in result["decisions"] if _ns(item["at"]) <= cutoff]
        self.assertEqual(prior(baseline), prior(replay))

    def test_invalid_latest_quote_blocks_signal_instead_of_reusing_old_valid_quote(self):
        frozen = dataset()
        asset = frozen["sessions"][0]["assets"][0]
        stamp = OPEN + 22 * MINUTE
        asset["quotes"].append(dict(quote(stamp), _ordinal=99999, _invalid_reason="crossed", bp=3, ap=2))
        result = run_replay(frozen)
        decision = next(item for item in result["decisions"] if item["at"] == _iso(stamp + NS))
        self.assertFalse(decision["eligible"])
        self.assertIsNone(decision["alert_level"])
        self.assertIn("two-sided", " ".join(decision["blockers"]))

    def test_missing_minutes_and_data_blockers_remain_visible(self):
        for kind in ("gap", "quarantine"):
            frozen = dataset()
            asset = frozen["sessions"][0]["assets"][0]
            if kind == "gap":
                del asset["minutes"][5]
            else:
                asset["quality"]["data_blockers"] = ["Malformed timestamp in provider quotes."]
            result = run_replay(frozen)
            self.assertEqual(result["summary"]["decisions"], 60)
            self.assertEqual(result["summary"]["alerts"], 0)
            self.assertEqual(result["summary"]["entry_fills"], 0)
            self.assertTrue(any(item["blockers"] for item in result["decisions"]))

    def test_stale_quote_can_pass_signal_but_cannot_size_plan(self):
        frozen = dataset()
        asset = frozen["sessions"][0]["assets"][0]
        # At 22:01 the latest quote is 21:54 (seven seconds old).
        stamp = OPEN + 22 * MINUTE
        asset["quotes"] = [item for item in asset["quotes"] if not stamp - 7 * NS < _ns(item["t"]) <= stamp]
        asset["quotes"].append(quote(stamp - 6 * NS, ordinal=99999))
        result = run_replay(frozen)
        decision = next(item for item in result["decisions"] if item["at"] == _iso(stamp + NS))
        self.assertTrue(decision["alert_level"])
        self.assertEqual(decision["disposition"], "unavailable")
        self.assertIn("five seconds", " ".join(decision["plan"]["reasons"]))

    def test_nanoseconds_preserved_and_same_timestamp_last_ordinal_is_only_opportunity(self):
        value = "2026-09-16T13:52:03.123456789Z"
        self.assertEqual(_iso(_ns(value)), value)
        frozen = dataset()
        asset = frozen["sessions"][0]["assets"][0]
        stamp = OPEN + 22 * MINUTE + 3 * NS
        asset["quotes"].extend([quote(stamp, size=400, ordinal=9000),
                                quote(stamp, size=4, ordinal=9001)])
        result = run_replay(frozen)
        buys = [item for item in result["fills"] if item["side"] == "buy"]
        self.assertEqual(len(buys), 1)
        self.assertEqual(buys[0]["quantity"], 1)
        self.assertEqual(buys[0]["quote_ordinal"], 9001)

    def test_future_unobserved_bid_cannot_expand_shared_portfolio_context(self):
        frozen = dataset(("AAA", "BBB"))
        # Delay BBB's participation burst until AAA already holds shares.
        for index, bar in enumerate(frozen["sessions"][0]["assets"][1]["minutes"]):
            bar["volume"] = 10000 if index < 24 else 20000
        baseline = run_replay(frozen)
        changed_data = deepcopy(frozen)
        asset = changed_data["sessions"][0]["assets"][0]
        # Decision is at :01; this event is processed but not observed until :01.5.
        asset["quotes"].append(quote(OPEN + 26 * MINUTE + NS // 2, bid=100, ask=100.01, ordinal=99999))
        changed = run_replay(changed_data)
        stamp = _iso(OPEN + 26 * MINUTE + NS)
        select = lambda result: [item for item in result["decisions"] if item["at"] == stamp]
        self.assertEqual(select(baseline), select(changed))
        decision = next(item for item in select(changed) if item["symbol"] == "BBB")
        self.assertEqual(decision["account_context"]["positions"], {"AAA": 100})
        self.assertLess(decision["portfolio_marks"]["AAA"]["bid"], 3)

    def test_invalid_trade_record_blocks_signal_and_does_not_reuse_old_trade(self):
        frozen = dataset()
        stamp = OPEN + 22 * MINUTE
        frozen["sessions"][0]["assets"][0]["trades"].append({"t": _iso(stamp), "p": 2,
            "s": 100, "_ordinal": 99999, "_invalid_reason": "invalid_trade_size"})
        result = run_replay(frozen)
        decision = next(item for item in result["decisions"] if item["at"] == _iso(stamp + NS))
        self.assertFalse(decision["eligible"])
        self.assertIn("valid trade", " ".join(decision["blockers"]))

    def test_delayed_stop_observation_cannot_preempt_earlier_holding_deadline(self):
        frozen = dataset()
        asset = frozen["sessions"][0]["assets"][0]
        deadline = OPEN + 37 * MINUTE + 3 * NS
        asset["quotes"].append(quote(deadline - NS // 2, bid=1, ask=1.01, ordinal=99999))
        result = run_replay(frozen)
        trade = result["trades"][0]
        self.assertEqual(trade["exit_reason"], "holding_limit")
        self.assertEqual(trade["exit_trigger_at"], _iso(deadline))

    def test_three_way_timer_quote_decision_tie_holding_deadline_wins(self):
        frozen = dataset()
        asset = frozen["sessions"][0]["assets"][0]
        # Make first entry :01 on the next minute, matching future decision time.
        asset["quotes"] = [item for item in asset["quotes"]
                           if not OPEN + 22 * MINUTE < _ns(item["t"]) < OPEN + 23 * MINUTE + NS]
        fill_at = OPEN + 23 * MINUTE + NS
        asset["quotes"].append(quote(fill_at, ordinal=9999))
        deadline = fill_at + 15 * MINUTE
        asset["quotes"].append(quote(deadline, bid=1, ask=1.01, ordinal=10000))
        result = run_replay(frozen)
        self.assertEqual(result["trades"][0]["entry_at"], _iso(fill_at))
        self.assertEqual(result["trades"][0]["exit_reason"], "holding_limit")
        ledger_times = [_ns(item["at"]) for item in result["ledger"]]
        self.assertEqual(ledger_times, sorted(ledger_times))

    def test_all_minutes_accounted_even_with_maximum_bar_delay(self):
        result = run_replay(dataset(), {"timing": {"bar_delay_seconds": 60}})
        self.assertEqual(result["summary"]["decisions"], 60)
        self.assertEqual([item["disposition"] for item in result["decisions"][-2:]], ["session_closed"] * 2)

    def test_cross_session_changed_share_basis_freezes_old_holding(self):
        frozen = dataset(("AAA", "BBB"))
        first = frozen["sessions"][0]
        # Both original holdings lose exit quote coverage.
        for asset in first["assets"]:
            asset["quotes"] = [item for item in asset["quotes"] if _ns(item["t"]) <= OPEN + 22 * MINUTE + 3 * NS]
        second = deepcopy(dataset(("AAA", "BBB"))["sessions"][0])
        second.update(date="2026-09-17", open=_iso(OPEN + 86400 * NS),
                      close=_iso(OPEN + 86400 * NS + 60 * MINUTE), previous_date="2026-09-16",
                      prior_dates=second["prior_dates"][1:] + ["2026-09-16"])
        for asset in second["assets"]:
            for key in ("quotes", "trades", "minutes"):
                for item in asset[key]:
                    item["t"] = _iso(_ns(item["t"]) + 86400 * NS)
            asset["daily"].append(dict(asset["daily"][-1], date="2026-09-16"))
        second["assets"][0]["quality"]["daily_split_to_session_factor"] = 2
        frozen["sessions"].append(second)
        result = run_replay(frozen)
        unresolved = next(item for item in result["unresolved"] if item["symbol"] == "AAA")
        self.assertIn("share basis", unresolved["reason"])
        self.assertIsNone(unresolved["last_observed_bid"])
        self.assertIsNone(result["summary"]["total_net_pnl"])
        self.assertEqual(len([item for item in result["fills"] if item["symbol"] == "AAA"]), 1)


class AccountingTests(unittest.TestCase):
    def test_researcher_partial_ioc_reservations_fees_and_display_consumption(self):
        engine = accounting_engine()
        engine._submit("AAA", accounting_plan(), "decision-1")
        self.assertEqual(engine.ledger[-1]["cash_reserved"], 76.05)
        self.assertEqual(engine.ledger[-1]["scenario_risk_reserved"], 6.15)
        active = engine.pending["AAA"]["_active"]
        engine.now = active
        engine._quote("AAA", quote(active, 1.49, 1.50, 80), OPEN, OPEN + 60 * MINUTE)
        self.assertEqual(len(engine.fills), 0)
        engine.now += 1
        engine._quote("AAA", quote(engine.now, 1.49, 1.50, 80), OPEN, OPEN + 60 * MINUTE)
        position = engine.positions["AAA"]
        self.assertEqual(position["quantity"], 20)
        self.assertEqual(position["target"], Decimal("1.71"))
        self.assertEqual(engine.cash, Decimal("9969.960"))
        self.assertEqual(engine.ledger[-1]["cash_reserved"], 0)
        self.assertEqual(engine.ledger[-1]["scenario_risk_reserved"], 2.46)
        self.assertEqual(engine.orders[0]["cancelled_quantity"], 30)
        engine.now += NS
        engine._quote("AAA", quote(engine.now, 1.72, 1.73, 40), OPEN, OPEN + 60 * MINUTE)
        observe(engine)
        active = position["_exit_active"]
        engine.now = active
        engine._quote("AAA", quote(active, 1.72, 1.73, 40), OPEN, OPEN + 60 * MINUTE)
        self.assertEqual(position["quantity"], 20)
        engine.now += 1
        engine._quote("AAA", quote(engine.now, 1.72, 1.73, 40), OPEN, OPEN + 60 * MINUTE)
        self.assertEqual(position["quantity"], 10)
        for size in (40, 20, 40):
            engine.now += NS
            engine._quote("AAA", quote(engine.now, 1.72, 1.73, size), OPEN, OPEN + 60 * MINUTE)
            self.assertEqual(position["quantity"], 10)
        engine.now += NS
        engine._quote("AAA", quote(engine.now, 1.72, 1.73, 80), OPEN, OPEN + 60 * MINUTE)
        self.assertNotIn("AAA", engine.positions)
        self.assertEqual(engine.cash, Decimal("10004.320"))
        self.assertEqual(engine.realized, Decimal("4.320"))
        self.assertEqual(engine.ledger[-1]["scenario_risk_reserved"], 0)

    def test_competing_symbols_share_pending_cash_and_reservations(self):
        frozen = dataset(("AAA", "BBB"))
        result = run_replay(frozen, {"account": {"initial_cash": 150}})
        alerts = [item for item in result["decisions"] if item["alert_level"]]
        self.assertEqual(alerts[0]["symbol"], "AAA")
        self.assertGreater(alerts[0]["plan"]["sizing"]["quantity"], 0)
        self.assertEqual(alerts[1]["plan"]["sizing"]["quantity"], 0)
        for item in result["ledger"]:
            self.assertGreaterEqual(item["cash_available"], 0)
        self.assertEqual(result["summary"]["entry_fills"], 1)

    def test_no_quote_does_not_fabricate_holding_deadline_liquidation(self):
        frozen = dataset()
        asset = frozen["sessions"][0]["assets"][0]
        asset["quotes"] = [item for item in asset["quotes"] if _ns(item["t"]) <= OPEN + 22 * MINUTE + 3 * NS]
        result = run_replay(frozen)
        self.assertEqual(result["summary"]["entry_fills"], 1)
        self.assertEqual(result["summary"]["exit_fills"], 0)
        self.assertEqual(result["summary"]["unresolved_positions"], 1)
        self.assertIsNone(result["summary"]["total_net_pnl"])
        self.assertEqual(result["trades"][0]["exit_reason"], "holding_limit")
        self.assertGreater(result["unresolved"][0]["mark_age_seconds"], 5)
        self.assertGreater(result["ledger"][-1]["scenario_risk_reserved"], 0)

    def test_untriggered_order_expires_and_releases_reservations(self):
        frozen = dataset()
        for item in frozen["sessions"][0]["assets"][0]["quotes"]:
            if _ns(item["t"]) > OPEN + 22 * MINUTE:
                item.update(bp=1.99, ap=2)
        result = run_replay(frozen)
        self.assertEqual(result["summary"]["expired_orders"], 1)
        self.assertEqual(result["summary"]["entry_fills"], 0)
        self.assertEqual(result["ledger"][-1]["cash_reserved"], 0)
        self.assertEqual(result["ledger"][-1]["scenario_risk_reserved"], 0)

    def test_gap_loss_debits_daily_allowance_and_exit_is_latched(self):
        engine = accounting_engine()
        engine._submit("AAA", accounting_plan(), "d")
        engine.now += 3 * NS
        engine._quote("AAA", quote(engine.now, 1.49, 1.5, 80), OPEN, OPEN + 60 * MINUTE)
        engine.now += NS
        engine._quote("AAA", quote(engine.now, 1.3, 1.31, 40), OPEN, OPEN + 60 * MINUTE)
        observe(engine)
        self.assertEqual(engine.positions["AAA"]["exit_reason"], "stop")
        engine.now += 3 * NS
        engine._quote("AAA", quote(engine.now, 1, 1.01, 40), OPEN, OPEN + 60 * MINUTE)
        self.assertEqual(engine.loss_debits, Decimal("5.04"))
        engine.now += NS
        engine._quote("AAA", quote(engine.now, 1.8, 1.81, 40), OPEN, OPEN + 60 * MINUTE)
        self.assertEqual(engine.loss_debits, Decimal("5.04"))
        self.assertEqual(engine.trades[0]["exit_reason"], "stop")

    def test_entry_quote_bid_below_stop_latches_stop_without_same_quote_exit(self):
        engine = accounting_engine()
        engine._submit("AAA", accounting_plan(), "d")
        engine.now += 3 * NS
        engine._quote("AAA", quote(engine.now, 1.3, 1.5, 80), OPEN, OPEN + 60 * MINUTE)
        self.assertIsNone(engine.positions["AAA"]["exit_reason"])
        observe(engine)
        self.assertEqual(engine.positions["AAA"]["exit_reason"], "stop")
        self.assertEqual(len(engine.fills), 1)


class ContractTests(unittest.TestCase):
    def test_unknown_conditions_and_invalid_quote_marker_are_rejected(self):
        for conditions in (None, [], ["A"], ["R", "A"]):
            raw = quote(OPEN)
            raw["c"] = conditions
            self.assertFalse(_quote_valid(raw))
        self.assertFalse(_quote_valid(dict(quote(OPEN), _invalid_reason="invalid_quote_sizes")))

    def test_confirmation_reset_upgrade_and_cooldown(self):
        state, config = {}, default_replay_config()["monitor"]
        def evaluate(index, signal):
            stamp = OPEN + index * MINUTE
            return _confirmation(state, {"signal_bar_at": _iso(stamp), "signal": signal,
                                         "alert_eligible": signal != "Watch"}, stamp, config)
        self.assertIsNone(evaluate(0, "Buy"))
        self.assertEqual(evaluate(1, "Buy"), "Buy")
        self.assertIsNone(evaluate(2, "Strong buy"))
        self.assertEqual(evaluate(3, "Strong buy"), "Strong buy")
        self.assertIsNone(evaluate(4, "Watch"))
        self.assertIsNone(evaluate(5, "Buy"))
        self.assertIsNone(evaluate(6, "Buy"))
        self.assertIsNone(evaluate(7, "Buy"))
        self.assertEqual(evaluate(8, "Buy"), "Buy")

    def test_unsupported_fixed_fees_and_bad_session_order_fail_loudly(self):
        with self.assertRaisesRegex(ValueError, "zero fixed"):
            run_replay(dataset(), {"costs": {"entry_fixed": 1}})
        frozen = dataset()
        frozen["sessions"].append(deepcopy(frozen["sessions"][0]))
        with self.assertRaisesRegex(ValueError, "chronological"):
            run_replay(frozen)


if __name__ == "__main__":
    unittest.main()
