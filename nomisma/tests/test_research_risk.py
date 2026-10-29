"""Conditional liquidation equity, observed-threshold control and passive parity."""

from copy import deepcopy
from decimal import Decimal
import heapq
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from nomisma import calibration, replay, research_risk
from test_calibration import make_catalog, two_sessions
from test_replay import OPEN, dataset, quote


def account_config(symbols=("AAA",)):
    config = replay.default_replay_config()
    config["account"]["initial_cash"] = 1000
    config["monitor"]["symbols"] = list(symbols)
    return config


def engine(guard=True, *, cash=1000, quantity=0, stop=9):
    result = research_risk._GuardedReplay({"symbols": ["AAA"], "sessions": []}, account_config(), guard)
    result.now = OPEN + 22 * replay.MINUTE
    result.cash = Decimal(str(cash))
    if quantity:
        result.positions["AAA"] = {"id": "trade-1", "symbol": "AAA", "quantity": quantity,
            "initial_quantity": quantity, "stop": Decimal(str(stop)), "target": Decimal("30"),
            "_risk_per_share": Decimal("1.003"), "_cap": Decimal("10"), "_entry": Decimal("10"),
            "exit_reason": None, "realized_net_pnl": Decimal(0), "exit_fees": Decimal(0),
            "exit_fills": [], "status": "open"}
    return result


def observe(instance, bid, *, event=None, raw=None):
    stamp = instance.now - replay.NS if event is None else event
    value = raw or quote(stamp, bid=bid, ask=bid + .01, size=10000)
    instance._observe_quote("AAA", value)
    return instance._sample("test")


def drain(instance, through):
    while instance.timers and instance.timers[0][0] <= through:
        stamp, _, _, kind, symbol, payload = heapq.heappop(instance.timers)
        instance.now = stamp
        instance._control_timer(kind, symbol, payload)
    instance.now = through


def reserve(instance, symbol="BBB", risk=10):
    instance.pending[symbol] = {"id": "order-" + symbol, "quantity": 1,
                               "_cap": Decimal("10"), "_cash_reserved": Decimal("10.001"),
                               "_risk_reserved": Decimal(str(risk))}


class LiquidationEquityTests(unittest.TestCase):
    def test_researcher_cost_fixture_does_not_subtract_pending_cash_or_entry_fees_twice(self):
        instance = engine(cash=899.99, quantity=10)
        reserve(instance, risk=10)
        value = observe(instance, 9.98)
        self.assertEqual(value["equity"], Decimal("999.770"))
        self.assertEqual(value["pending_risk"], Decimal(10))
        self.assertEqual(value["marks"]["AAA"]["net_liquidation_value"], Decimal("99.780"))
        self.assertEqual(value["new_risk_allowance"], Decimal("79.740"))
        self.assertEqual(instance.cash, Decimal("899.99"))

    def test_flat_cash_remains_completely_valued_without_quotes(self):
        instance = engine(cash=975)
        value = instance._sample("flat")
        self.assertTrue(value["complete"])
        self.assertEqual(value["equity"], Decimal(975))
        self.assertEqual(value["drawdown"], Decimal(25))
        self.assertEqual(value["new_risk_allowance"], Decimal(75))

    def test_quote_not_available_until_modeled_observation(self):
        instance = engine(cash=899.99, quantity=10)
        observed = instance.now
        raw = quote(observed, bid=9.98, ask=9.99)
        instance._quote("AAA", raw, OPEN, OPEN + 60 * replay.MINUTE)
        self.assertFalse(instance._valuation()["complete"])
        drain(instance, observed + replay.NS - 1)
        self.assertFalse(instance._valuation()["complete"])
        drain(instance, observed + replay.NS)
        self.assertEqual(instance._valuation()["equity"], Decimal("999.770"))

    def test_exact_freshness_boundary_and_unknown_duration(self):
        instance = engine(cash=899.99, quantity=10)
        event = instance.now - replay.NS
        observe(instance, 9.98, event=event)
        drain(instance, event + 5 * replay.NS)
        self.assertTrue(instance._sample("exact_five_seconds")["complete"])
        drain(instance, event + 5 * replay.NS + 1)
        self.assertFalse(instance._valuation()["complete"])
        self.assertIsNone(instance.equity_events[-1]["liquidation_equity"])
        instance.now += 2 * replay.NS
        observe(instance, 9.98)
        report = instance.equity_report()
        self.assertEqual(report["unknown_interval_count"], 1)
        self.assertEqual(report["unknown_duration_seconds"], 2)
        self.assertFalse(report["unknown_intervals"][0]["open_at_end"])

    def test_latest_invalid_quote_and_known_halt_invalidate_previous_good_mark(self):
        for mode in ("crossed", "unknown_condition", "halted"):
            instance = engine(cash=899.99, quantity=10)
            observe(instance, 9.98)
            instance.now += replay.NS
            raw = quote(instance.now - replay.NS, 9.98, 9.99)
            if mode == "crossed":
                raw["_invalid_reason"] = "crossed"
                raw["bp"] = 12
            elif mode == "unknown_condition":
                raw["c"] = []
            else:
                raw["halted"] = True
            with self.subTest(mode=mode):
                value = observe(instance, 9.98, raw=raw)
                self.assertFalse(value["complete"])
                self.assertIsNone(value["equity"])
                self.assertIn("AAA", value["unknown_symbols"])

    def test_rally_guard_risk_uses_mark_to_stop_giveback(self):
        instance = engine(cash=900, quantity=10)
        instance.costs.update(stop_slippage=Decimal(0), exit_per_share=Decimal(0))
        instance.positions["AAA"]["_risk_per_share"] = Decimal(1)
        value = observe(instance, 20)
        self.assertEqual(value["equity"], Decimal(1100))
        self.assertEqual(value["floor"], Decimal(1000))
        self.assertEqual(value["position_guard_risk"], Decimal(110))
        self.assertEqual(value["new_risk_allowance"], 0)


class GuardControlTests(unittest.TestCase):
    def test_peak_rises_floor_rises_breach_latches_and_does_not_reset_on_recovery(self):
        instance = engine(cash=900, quantity=10)
        instance.costs.update(stop_slippage=Decimal(0), exit_per_share=Decimal(0))
        observe(instance, 20)
        reserve(instance)
        instance.now += replay.NS
        value = observe(instance, 10)
        self.assertEqual(value["equity"], 1000)
        self.assertTrue(instance.breached)
        self.assertEqual(instance.breach_floor, 1000)
        self.assertFalse(instance.pending)
        self.assertEqual(instance.positions["AAA"]["exit_reason"], "peak_dollar_drawdown")
        self.assertEqual(instance.positions["AAA"]["_exit_active"], instance.now + replay.NS)
        instance.now += replay.NS
        observe(instance, 20)
        self.assertTrue(instance.breached)
        self.assertEqual(instance._context({})["risk_budget"], 0)

    def test_gap_can_overshoot_one_hundred_before_delayed_capacity_limited_exit(self):
        instance = engine(cash=800, quantity=20)
        observe(instance, 10)
        instance.now += replay.NS
        observe(instance, 3)
        report = instance.equity_report()
        self.assertTrue(report["guard_latched"])
        self.assertGreater(report["maximum_observed_overshoot"], 40)
        self.assertEqual(instance.positions["AAA"]["quantity"], 20)
        self.assertEqual(len(instance.fills), 0)
        active = instance.positions["AAA"]["_exit_active"]
        instance.now = active
        instance._quote("AAA", quote(active, bid=2, ask=2.01, size=40), OPEN, OPEN + 60 * replay.MINUTE)
        self.assertEqual(instance.positions["AAA"]["quantity"], 20)
        instance.now += 1
        instance._quote("AAA", quote(instance.now, bid=2, ask=2.01, size=40), OPEN, OPEN + 60 * replay.MINUTE)
        self.assertEqual(instance.positions["AAA"]["quantity"], 10)
        self.assertEqual(instance.fills[0]["quantity"], 10)

    def test_unknown_held_mark_cancels_pending_and_blocks_context_without_forced_exit(self):
        instance = engine(cash=900, quantity=10)
        reserve(instance)
        value = instance._sample("unknown")
        self.assertFalse(value["complete"])
        self.assertFalse(instance.pending)
        self.assertIsNone(instance._context({"AAA": {"bid": Decimal(10)}}))
        self.assertIsNone(instance.positions["AAA"]["exit_reason"])
        self.assertFalse(instance.breached)

    def test_pending_reservation_counted_once_and_engineering_caps_remain(self):
        instance = engine(cash=1000)
        reserve(instance, risk=60)
        value = instance._sample("pending")
        self.assertEqual(value["new_risk_allowance"], Decimal(40))
        context = instance._context({})
        self.assertEqual(context["risk_budget"], 25)
        self.assertEqual(context["day_risk_remaining"], 40)
        self.assertEqual(context["portfolio_risk_remaining"], 15)

    def test_larger_configured_limits_cannot_enlarge_registered_engineering_caps(self):
        instance = engine()
        instance.account.update(risk_per_trade=Decimal(1000), daily_loss_allowance=Decimal(1000),
                                portfolio_risk_limit=Decimal(1000))
        reserve(instance, risk=20)
        context = instance._context({})
        self.assertEqual(context["risk_budget"], 25)
        self.assertEqual(context["day_risk_remaining"], 80)
        self.assertEqual(context["portfolio_risk_remaining"], 55)

    def test_changed_or_missing_share_basis_makes_held_equity_unknown(self):
        instance = engine(cash=900, quantity=10)
        observe(instance, 10)
        instance.share_factors["AAA"] = 1
        instance._incoming_session = {"assets": [{"symbol": "AAA", "quality": {"daily_split_to_session_factor": 2}}]}
        instance._snapshot("session_open", session_date="2026-09-17")
        value = instance._valuation()
        self.assertFalse(value["complete"])
        self.assertIn("share basis", value["unknown_symbols"]["AAA"])


class AdapterTests(unittest.TestCase):
    def test_passive_observer_preserves_all_baseline_semantics_with_carry(self):
        frozen = two_sessions(carry=True)
        with tempfile.TemporaryDirectory() as temporary:
            path = make_catalog(Path(temporary), frozen)
            baseline = calibration.run_catalog(path, account_config())
            observed = research_risk.run_catalog_guarded(path, account_config(), guard_enabled=False)
        report = observed.pop("equity_report")
        self.assertEqual(calibration.semantic_result(observed), calibration.semantic_result(baseline))
        self.assertFalse(report["guard"]["enabled"])
        self.assertGreater(report["sample_count"], 0)
        self.assertGreater(report["unknown_duration_seconds"], 0)

    def test_replay_determinism_and_guarded_public_api(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = make_catalog(Path(temporary), dataset())
            first = research_risk.run_catalog_guarded(path, account_config())
            second = research_risk.run_catalog_guarded(path, account_config())
        self.assertEqual(first, second)
        self.assertEqual(first["equity_report"]["guard"]["amount"], 100)
        self.assertEqual(first["summary"]["initial_cash"], 1000)
        self.assertTrue(first["research_only"])

    def test_wrong_pin_and_other_capital_rejected(self):
        with patch.object(calibration, "replay_source_sha256", return_value="changed"):
            with self.assertRaisesRegex(ValueError, "engine hash"):
                research_risk.run_catalog_guarded(Path("unused"), account_config())
        with tempfile.TemporaryDirectory() as temporary:
            path = make_catalog(Path(temporary), dataset())
            invalid = account_config()
            invalid["account"]["initial_cash"] = 2000
            with self.assertRaisesRegex(ValueError, "1000"):
                research_risk.run_catalog_guarded(path, invalid)


if __name__ == "__main__":
    unittest.main()
