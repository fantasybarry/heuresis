"""Researcher numerical fixtures and safety boundaries; no I/O or orders."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import unittest

from nomisma import trade_plan


NOW = datetime(2026, 9, 16, 15, 0, 2, tzinfo=timezone.utc)


def market(count=20, now=NOW):
    start = now.replace(second=0, microsecond=0) - timedelta(minutes=count)
    return {
        "schema_version": 1, "valid": True, "blockers": [], "warnings": [],
        "symbol": "TEST", "source": "alpaca", "feed": "sip", "decision_at": now.isoformat(),
        "session_open": now.replace(hour=13, minute=30, second=0, microsecond=0).isoformat(),
        "session_close": now.replace(hour=20, minute=0, second=0, microsecond=0).isoformat(),
        "eligible": True, "halted": False,
        "minutes": [{"t": (start + timedelta(minutes=index)).isoformat(),
                     "open": 1.98, "high": 2, "low": 1.96, "close": 1.98,
                     "volume": 20000} for index in range(count)],
        "quote": {"schema_version": 1, "bid": 2, "ask": 2.01,
                  "bid_size_raw": 800, "ask_size_raw": 800,
                  "bid_size_shares": 800, "ask_size_shares": 800,
                  "size_unit": "shares", "size_basis": "provider_share_contract",
                  "event_at": now.isoformat(), "received_at": now.isoformat(),
                  "source": "alpaca", "feed": "sip"},
    }


def settings(now=NOW):
    return {
        "policy": {},
        "context": {"as_of": now.isoformat(), "equity": 10000, "cash": 5000,
                    "risk_budget": 25, "day_risk_remaining": 100,
                    "portfolio_risk_remaining": 100, "max_position_notional": 1000,
                    "gross_notional_remaining": 5000, "positions": {}},
        "costs": {"entry_fixed": 0, "entry_per_share": .002,
                  "exit_fixed": 0, "exit_per_share": .002, "entry_slippage": 0,
                  "stop_slippage": .01, "target_slippage": .005},
    }


class NumericalFixtureTests(unittest.TestCase):
    def test_researcher_fixture_levels_size_and_affine_reservations(self):
        plan = trade_plan.build_trade_plan(market(), settings())
        self.assertEqual(plan["status"], "conditional")
        self.assertEqual(plan["levels"], {
            "atr": .04, "entry_trigger": 2.01, "entry_max": 2.02, "stop": 1.95,
            "target_at_trigger": 2.13, "target_at_max": 2.16, "hold_minutes": 15})
        self.assertEqual(plan["sizing"], {
            "quantity": 200, "risk_reserved": 16.8, "notional_max": 404,
            "cash_required": 404.4, "robust_net_rr": 1.5,
            "limiting_caps": {"risk": 297, "cash": 2472, "notional": 495, "liquidity": 200}})
        self.assertEqual(plan["expires_at"], (NOW + timedelta(seconds=120)).isoformat())
        self.assertTrue(plan["research_only"])
        self.assertEqual(plan["calibration_status"], "unvalidated")
        json.dumps(plan, allow_nan=False)

    def test_lower_entry_rejects_even_when_maximum_entry_ratio_passes(self):
        configured = settings()
        configured["policy"]["min_net_rr"] = 1.55
        # Upper fill: (.14-.005-.004)/(.07+.01+.004) = 1.55952...
        # Lower fill: (.12-.005-.004)/(.06+.01+.004) = exactly 1.5.
        plan = trade_plan.build_trade_plan(market(), configured)
        self.assertEqual(plan["status"], "no_trade")
        self.assertEqual(plan["sizing"]["robust_net_rr"], 1.5)
        for key in ("quantity", "risk_reserved", "cash_required", "notional_max"):
            self.assertEqual(plan["sizing"][key], 0)

    def test_fixed_fees_reject_small_partials_despite_large_order_ratio(self):
        configured = settings()
        configured["costs"].update(entry_fixed=.01, exit_fixed=.01)
        plan = trade_plan.build_trade_plan(market(), configured)
        self.assertEqual(plan["status"], "no_trade")
        self.assertAlmostEqual(plan["sizing"]["robust_net_rr"], .091 / .094)

    def test_affine_full_quantity_cash_and_risk_cover_all_partial_sizes(self):
        configured = settings()
        configured["policy"]["min_net_rr"] = .9
        configured["costs"].update(entry_fixed=.01, exit_fixed=.01)
        plan = trade_plan.build_trade_plan(market(), configured)
        self.assertEqual(plan["sizing"]["quantity"], 200)
        self.assertEqual(plan["sizing"]["risk_reserved"], 16.82)
        self.assertEqual(plan["sizing"]["cash_required"], 404.41)
        for quantity in (1, 5, 199, 200):
            self.assertLessEqual(quantity * .084 + .02, plan["sizing"]["risk_reserved"] + 1e-10)
            self.assertLessEqual(quantity * 2.022 + .01, plan["sizing"]["cash_required"] + 1e-10)

    def test_wilder_minute_atr_smoothing_fixture(self):
        inputs = market(16)
        inputs["minutes"][-1].update(low=1.93, high=2)
        plan = trade_plan.build_trade_plan(inputs)
        self.assertEqual(plan["status"], "levels_only")
        self.assertAlmostEqual(plan["levels"]["atr"], (13 * .04 + .07) / 14)

    def test_true_range_accounts_for_price_gap(self):
        inputs = market(15)
        inputs["minutes"][0].update(open=1.8, high=1.82, low=1.78, close=1.8)
        plan = trade_plan.build_trade_plan(inputs)
        self.assertAlmostEqual(plan["levels"]["atr"], (.2 + 13 * .04) / 14)

    def test_price_grid_has_strict_next_trigger_and_directional_rounding(self):
        configured = settings()
        configured["policy"].update(tick_size=.005, reward_multiple=1.7)
        plan = trade_plan.build_trade_plan(market(), configured)
        self.assertEqual(plan["levels"]["entry_trigger"], 2.005)
        self.assertEqual(plan["levels"]["entry_max"], 2.015)
        self.assertEqual(plan["levels"]["stop"], 1.945)
        self.assertEqual(plan["levels"]["target_at_trigger"], 2.11)
        self.assertEqual(plan["levels"]["target_at_max"], 2.135)

    def test_risk_cash_notional_and_liquidity_each_constrain_quantity(self):
        for key, value, expected_cap in (("risk_budget", .084, "risk"),
                                         ("cash", 2.022, "cash"),
                                         ("max_position_notional", 2.02, "notional"),
                                         ("gross_notional_remaining", 2.02, "notional"),
                                         ("day_risk_remaining", .084, "risk"),
                                         ("portfolio_risk_remaining", .084, "risk")):
            configured = settings()
            configured["context"][key] = value
            with self.subTest(key=key):
                plan = trade_plan.build_trade_plan(market(), configured)
                self.assertEqual(plan["sizing"]["quantity"], 1)
                self.assertEqual(plan["sizing"]["limiting_caps"][expected_cap], 1)

    def test_liquidity_uses_median_last_twenty_and_both_quote_sides(self):
        inputs = market(25)
        for bar in inputs["minutes"][:5]:
            bar["volume"] = 1
        inputs["minutes"][-1]["volume"] = 10 ** 9
        inputs["quote"]["bid_size_shares"] = 12
        plan = trade_plan.build_trade_plan(inputs, settings())
        self.assertEqual(plan["sizing"]["quantity"], 3)
        inputs["quote"]["ask_size_shares"] = 4
        self.assertEqual(trade_plan.build_trade_plan(inputs, settings())["sizing"]["quantity"], 1)


class PlanStateTests(unittest.TestCase):
    def test_missing_context_or_costs_keeps_levels_with_no_invented_size(self):
        for change in ({}, {"context": {}}, {"costs": {}},
                       {"context": settings()["context"]}, {"costs": settings()["costs"]}):
            with self.subTest(change=change):
                plan = trade_plan.build_trade_plan(market(), change)
                self.assertEqual(plan["status"], "levels_only")
                self.assertIsNone(plan["sizing"]["quantity"])
                self.assertEqual(plan["levels"]["entry_trigger"], 2.01)

    def test_null_incomplete_fields_never_default_to_zero(self):
        for section, key in (("costs", "entry_fixed"), ("context", "cash"), ("context", "positions")):
            configured = settings()
            configured[section][key] = None
            plan = trade_plan.build_trade_plan(market(), configured)
            self.assertEqual(plan["status"], "levels_only")
            self.assertIsNone(plan["sizing"]["quantity"])

    def test_existing_position_prevents_second_entry(self):
        configured = settings()
        configured["context"]["positions"] = {"TEST": 1}
        plan = trade_plan.build_trade_plan(market(), configured)
        self.assertEqual(plan["status"], "no_trade")
        self.assertEqual(plan["sizing"]["quantity"], 0)

    def test_exhausted_risk_cash_or_quote_capacity_is_no_trade(self):
        for key in ("risk_budget", "day_risk_remaining", "portfolio_risk_remaining", "cash", "max_position_notional"):
            configured = settings()
            configured["context"][key] = 0
            plan = trade_plan.build_trade_plan(market(), configured)
            self.assertEqual(plan["status"], "no_trade")
            self.assertEqual(plan["sizing"]["quantity"], 0)
        inputs = market()
        inputs["quote"]["ask_size_shares"] = 0
        self.assertEqual(trade_plan.build_trade_plan(inputs, settings())["status"], "no_trade")

    def test_wait_conditions_and_slippage_allowance(self):
        for ask, slippage, status in ((2, 0, "wait"), (2.01, 0, "conditional"),
                                      (2.02, 0, "conditional"), (2.02, .001, "wait"),
                                      (2.03, 0, "wait")):
            inputs, configured = market(), settings()
            inputs["quote"]["ask"] = ask
            configured["costs"]["entry_slippage"] = slippage
            plan = trade_plan.build_trade_plan(inputs, configured)
            self.assertEqual(plan["status"], status)
            self.assertEqual(plan["sizing"]["quantity"], 200)

    def test_fifteen_bars_allow_atr_but_not_liquidity_sizing(self):
        plan = trade_plan.build_trade_plan(market(15), settings())
        self.assertEqual(plan["status"], "levels_only")
        self.assertEqual(plan["levels"]["atr"], .04)
        self.assertIsNone(plan["sizing"]["quantity"])
        self.assertEqual(trade_plan.build_trade_plan(market(14), settings())["status"], "unavailable")

    def test_missing_or_unverified_size_units_preserve_only_levels(self):
        for change in ({"size_unit": "lots"}, {"size_basis": None}, {"bid_size_shares": None}):
            inputs = market()
            inputs["quote"].update(change)
            self.assertEqual(trade_plan.build_trade_plan(inputs, settings())["status"], "levels_only")

    def test_account_freshness_is_relative_to_decision_with_inclusive_boundary(self):
        for seconds, status in ((0, "conditional"), (300, "conditional"), (301, "levels_only"), (-1, "levels_only")):
            configured = settings()
            configured["context"]["as_of"] = (NOW - timedelta(seconds=seconds)).isoformat()
            self.assertEqual(trade_plan.build_trade_plan(market(), configured)["status"], status)

    def test_shortened_exchange_session_limits_expiry_and_holding(self):
        inputs = market()
        inputs["session_close"] = (NOW + timedelta(minutes=21)).isoformat()
        plan = trade_plan.build_trade_plan(inputs, settings())
        self.assertEqual(plan["expires_at"], (NOW + timedelta(minutes=1)).isoformat())
        inputs["session_close"] = (NOW + timedelta(minutes=20)).isoformat()
        plan = trade_plan.build_trade_plan(inputs, settings())
        self.assertEqual(plan["status"], "expired")
        self.assertIsNone(plan["sizing"]["quantity"])

    def test_invalid_normalizer_gate_preserves_blockers(self):
        inputs = market()
        inputs.update(valid=False, blockers=["Original contemporaneous quote was not saved."])
        plan = trade_plan.build_trade_plan(inputs, settings())
        self.assertEqual(plan["status"], "unavailable")
        self.assertEqual(plan["reasons"], inputs["blockers"])
        self.assertIsNone(plan["levels"]["entry_trigger"])
        self.assertIsNone(plan["sizing"]["quantity"])

    def test_completed_minute_age_matches_normalizer_boundary(self):
        for age, expected in ((120, "conditional"), (121, "unavailable")):
            inputs = market()
            # Last original minute ends at15:00:00; retain event/receipt at
            # each later decision to isolate completed-bar age from quote age.
            decision = NOW.replace(second=0) + timedelta(seconds=age)
            inputs["decision_at"] = decision.isoformat()
            inputs["quote"].update(event_at=decision.isoformat(), received_at=decision.isoformat())
            self.assertEqual(trade_plan.build_trade_plan(inputs, settings(decision))["status"], expected)

    def test_unknown_halt_status_has_explicit_warning(self):
        inputs = market()
        inputs["halted"] = None
        plan = trade_plan.build_trade_plan(inputs, settings())
        self.assertEqual(plan["status"], "conditional")
        self.assertTrue(any("Halt status is unknown" in value for value in plan["warnings"]))


class ValidationTests(unittest.TestCase):
    def test_defaults_are_independent_and_partial_merges_replace_positions(self):
        first = trade_plan.default_plan_settings()
        first["policy"]["hold_minutes"] = 5
        self.assertEqual(trade_plan.default_plan_settings()["policy"]["hold_minutes"], 15)
        old = settings()
        old["context"]["positions"] = {"TEST": 1}
        snapshot = deepcopy(old)
        merged = trade_plan.validate_plan_settings({"context": {"positions": {"OTHER": 2}},
                                                    "policy": {"hold_minutes": 30}}, old)
        self.assertEqual(old, snapshot)
        self.assertEqual(merged["context"]["positions"], {"OTHER": 2})
        self.assertEqual(merged["context"]["cash"], 5000)
        self.assertEqual(merged["policy"]["hold_minutes"], 30)
        self.assertEqual(merged["costs"]["stop_slippage"], .01)

    def test_unknown_nonfinite_boolean_invalid_policy_and_account_inputs_rejected(self):
        cases = [None, [], {"unknown": 1}, {"policy": None}, {"policy": {"future": 1}},
                 {"policy": {"atr_period": 15}}, {"policy": {"breakout_bars": 6}},
                 {"policy": {"atr_period": True}}, {"policy": {"hold_minutes": 10}},
                 {"policy": {"entry_valid_seconds": 1.5}}, {"policy": {"close_buffer_seconds": 901}},
                 {"policy": {"stop_atr_multiple": 0}}, {"policy": {"chase_atr_multiple": -1}},
                 {"policy": {"participation_rate": .11}}, {"policy": {"tick_size": 0}},
                 {"policy": {"tick_size": "0.01"}}, {"policy": {"min_net_rr": True}},
                 {"policy": {"reward_multiple": float("nan")}},
                 {"costs": {"entry_fixed": float("inf")}}, {"costs": {"entry_per_share": -1}},
                 {"costs": {"unknown": 0}}, {"context": {"equity": 0}},
                 {"context": {"equity": 10, "cash": 11}},
                 {"context": {"as_of": "2026-09-16T15:00:00"}},
                 {"context": {"positions": []}}, {"context": {"positions": {"TEST": 1.1}}},
                 {"context": {"positions": {"TEST": True}}}, {"context": {"positions": {"TEST": -1}}},
                 {"context": {"positions": {"bad symbol": 1}}}, {"context": {"cash": 10 ** 1000}}]
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ValueError):
                trade_plan.validate_plan_settings(value)

    def test_tiny_research_ticks_are_rejected_before_serialization_can_erase_breakout(self):
        for tick in (1e-16, 1e-20, 1e-60, 0.000000999999):
            configured = settings()
            configured["policy"]["tick_size"] = tick
            with self.subTest(tick=tick), self.assertRaisesRegex(ValueError, "representability"):
                trade_plan.build_trade_plan(market(), configured)

    def test_minimum_tick_keeps_strict_output_geometry_at_maximum_market_price(self):
        inputs = market()
        for bar in inputs["minutes"]:
            bar.update(open=999999999.98, high=1000000000, low=999999999.96,
                       close=999999999.98)
        inputs["quote"].update(bid=999999999.99, ask=1000000000)
        plan = trade_plan.build_trade_plan(inputs, {"policy": {"tick_size": .000001}})
        self.assertEqual(plan["status"], "levels_only")
        levels = json.loads(json.dumps(plan))["levels"]
        self.assertGreater(levels["entry_trigger"], 1000000000)
        self.assertTrue(0 < levels["stop"] < levels["entry_trigger"] <= levels["entry_max"]
                        < levels["target_at_max"])
        self.assertGreater(levels["target_at_trigger"], levels["entry_trigger"])
        self.assertIsNone(plan["sizing"]["quantity"])

    def test_market_invalidity_fails_closed(self):
        changes = [lambda x: x.update(schema_version=True),
                   lambda x: x.update(eligible=False), lambda x: x.update(halted=True),
                   lambda x: x.update(decision_at="not a timestamp"),
                   lambda x: x["quote"].update(bid=2.02),
                   lambda x: x["quote"].update(schema_version=True),
                   lambda x: x.update(source="unsupported"),
                   lambda x: x["quote"].update(ask=float("nan")),
                   lambda x: x["quote"].update(feed="iex"),
                   lambda x: x["quote"].update(event_at=(NOW - timedelta(seconds=6)).isoformat()),
                   lambda x: x["quote"].update(received_at=(NOW + timedelta(seconds=1)).isoformat()),
                   lambda x: x["minutes"][-1].update(t=NOW.isoformat()),
                   lambda x: x["minutes"][1].update(t=x["minutes"][0]["t"]),
                   lambda x: x["minutes"][0].update(low=2.1),
                   lambda x: x["minutes"][0].update(volume=-1),
                   lambda x: x["minutes"].reverse()]
        for change in changes:
            inputs = market()
            change(inputs)
            with self.subTest(inputs=inputs):
                plan = trade_plan.build_trade_plan(inputs, settings())
                self.assertEqual(plan["status"], "unavailable")
                self.assertIsNone(plan["sizing"]["quantity"])

    def test_zero_atr_and_invalid_grid_geometry_are_unavailable(self):
        inputs = market()
        for bar in inputs["minutes"]:
            bar.update(open=2, high=2, low=2, close=2)
        self.assertEqual(trade_plan.build_trade_plan(inputs, settings())["status"], "unavailable")
        configured = settings()
        configured["policy"].update(tick_size=1, stop_atr_multiple=.1)
        # This coarse grid is still valid: stop rounds to 2 below trigger 3.
        self.assertEqual(trade_plan.build_trade_plan(market(), configured)["levels"]["stop"], 2)
        configured["policy"].update(tick_size=.01, stop_atr_multiple=10)
        inputs = market()
        for bar in inputs["minutes"]:
            bar.update(low=.01)
        self.assertEqual(trade_plan.build_trade_plan(inputs, configured)["status"], "unavailable")

    def test_deterministic_and_does_not_mutate_inputs_or_settings(self):
        inputs, configured = market(), settings()
        before = deepcopy((inputs, configured))
        first = trade_plan.build_trade_plan(inputs, configured)
        second = trade_plan.build_trade_plan(inputs, configured)
        self.assertEqual(first, second)
        self.assertEqual((inputs, configured), before)
        self.assertEqual(set(first), {"schema_version", "model_id", "research_only", "calibration_status", "symbol",
                                     "source", "feed", "as_of", "expires_at", "status", "levels", "sizing",
                                     "policy", "reasons", "warnings"})


if __name__ == "__main__":
    unittest.main()
