"""All-in requested sizing, settled funding and causal protective exits."""

from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from nomisma import all_in_replay as model, cash_calendar, replay, trade_plan
from test_calibration import make_catalog, two_sessions
from test_cash_calendar import calendar, row
from test_cash_replay import drain, fill_exit
from test_replay import OPEN, dataset, quote
from test_trade_plan import market, settings


def engine(rule="fixed_15m", config=None):
    configured = replay._config(config or {"account": {"initial_cash": 1000}}, ["AAA", "BBB"])
    mapping = {"2026-09-16": "2026-09-17", "2026-09-17": "2026-09-18"}
    cal = cash_calendar.SettlementCalendar(tuple(mapping), "test", "test", "2026-09-18", mapping)
    value = model._AllInReplay({"symbols": ["AAA", "BBB"], "sessions": []}, configured, cal, rule)
    value.now = OPEN + 22 * replay.MINUTE
    return value


def plan(value, quantity=99, trigger=10, cap=10.02, stop=9.85, atr=.10):
    return {"sizing": {"quantity": quantity}, "levels": {"entry_trigger": trigger,
        "entry_max": cap, "stop": stop, "atr": atr},
        "expires_at": replay._iso(value.now + 120 * replay.NS)}


def enter(value, quantity=99, size=200, trigger=10, cap=10.02, stop=9.85, atr=.10, ask=10):
    value._submit("AAA", plan(value, quantity, trigger, cap, stop, atr), "decision")
    value.now += 2 * replay.NS
    raw = quote(value.now, bid=ask - .01, ask=ask, size=size)
    value._quote("AAA", raw, OPEN, OPEN + 60 * replay.MINUTE)
    return value.positions["AAA"]


def observe(value, bid, *, event=None, invalid=False):
    stamp = value.now - value.config["timing"]["quote_delay_seconds"] * replay.NS if event is None else event
    raw = quote(stamp, bid=bid, ask=bid + .01, size=10000)
    if invalid:
        raw["_invalid_reason"] = "bad_quote"
    value._observe_quote("AAA", raw)


class AllInSizingTests(unittest.TestCase):
    def test_cash_only_quantity_ignores_decision_liquidity_and_retains_initial_rr(self):
        inputs = market()
        configured = settings()
        inputs["quote"].update(bid_size_shares=4, ask_size_shares=4)
        context = {"cash": 1000, "equity": 1000, "as_of": inputs["decision_at"], "positions": {}}
        actual = model.build_all_in_plan(inputs, configured["policy"], configured["costs"], context)
        original = trade_plan.build_trade_plan(inputs, configured)
        self.assertEqual(actual["sizing"]["quantity"], 494)
        self.assertEqual(actual["sizing"]["limiting_caps"], {"cash": 494})
        self.assertEqual(original["sizing"]["quantity"], 1)
        self.assertEqual(actual["sizing"]["robust_net_rr"], original["sizing"]["robust_net_rr"])
        self.assertEqual(actual["levels"], original["levels"])

    def test_tiny_legacy_account_fields_cannot_constrain_all_in_plan(self):
        tiny = {"account": {"initial_cash": 1000, **{key: .000001 for key in model.IGNORED_ACCOUNT_FIELDS}}}
        value = engine(config=tiny)
        inputs = market()
        inputs["symbol"] = "AAA"
        value.now = replay._ns(inputs["decision_at"])
        actual = model.build_all_in_plan(inputs, value.policy, value.config["costs"], value._context({}))
        self.assertEqual(actual["sizing"]["quantity"], 494)
        self.assertEqual(actual["sizing"]["limiting_caps"], {"cash": 494})
        self.assertNotIn("risk_budget", value._context({}))

    def test_initial_rr_and_structurally_empty_interval_still_reject(self):
        inputs = market()
        configured = settings()
        context = {"cash": 1000, "as_of": inputs["decision_at"]}
        failed = model.build_all_in_plan(inputs, {"min_net_rr": 1.55}, configured["costs"], context)
        self.assertEqual(failed["status"], "no_trade")
        self.assertEqual(failed["sizing"]["quantity"], 0)
        impossible_costs = dict(configured["costs"], entry_slippage=.02)
        impossible = model.build_all_in_plan(inputs, {}, impossible_costs, context)
        self.assertEqual(impossible["status"], "structurally_infeasible_entry")
        self.assertEqual(impossible["sizing"]["quantity"], 0)

    def test_researcher_99_requested_50_ioc_fill_and_no_topup(self):
        value = engine()
        enter(value)
        self.assertEqual(value.orders[0]["quantity"], 99)
        self.assertEqual(value.orders[0]["filled_quantity"], 50)
        self.assertEqual(value.orders[0]["cancelled_quantity"], 49)
        self.assertEqual(value.settled_cash, Decimal("499.900"))
        self.assertEqual(value._cash_state()["cash_reserved"], 0)
        self.assertEqual(value.daily_choices["2026-09-16"]["quantity"], 50)
        self.assertEqual(value._choice_blocker(), "single_open_position")
        fill_exit(value)
        self.assertEqual(value._choice_blocker(), "daily_entry_already_used")

    def test_199_cash_reservation_actual_fill_and_residual_fixture(self):
        value = engine()
        value._submit("AAA", plan(value, 199, 4.9, 5, 4.3, .4), "decision")
        self.assertEqual(value._cash_state()["cash_reserved"], Decimal("995.199"))
        value.now += 2 * replay.NS
        value._quote("AAA", quote(value.now, 4.94, 4.95, 800), OPEN, OPEN + 60 * replay.MINUTE)
        self.assertEqual(value.orders[0]["filled_quantity"], 199)
        self.assertEqual(value.settled_cash, Decimal("14.552"))
        choice = value.daily_choices["2026-09-16"]
        self.assertEqual(choice["settled_cash_used"], Decimal("985.448"))
        self.assertEqual(choice["settled_cash_after"], Decimal("14.552"))

    def test_settlement_preserved_and_over_100_drawdown_does_not_block_later_entry(self):
        value = engine()
        position = enter(value, quantity=99, size=400, stop=5)
        value.now += 2 * replay.NS
        observe(value, 8)
        self.assertGreater(value.max_observed_drawdown, 100)
        self.assertIsNone(position["exit_reason"])
        self.assertFalse(value.breached)
        fill_exit(value, price=8)
        self.assertGreater(value.max_observed_drawdown, 100)
        self.assertFalse(value.breached)
        self.assertEqual(value._cash_state()["cash_available"], Decimal("9.802"))
        self.assertGreater(value._cash_state()["unsettled_cash"], 700)
        release = replay._ns(value.receivables[0]["available_at"])
        drain(value, release)
        self.assertIsNone(value._choice_blocker())
        self.assertGreater(value._context({})["cash"], 800)
        later_plan = plan(value, quantity=1)
        self.assertIsNone(value._submission_blocker("BBB", later_plan))
        value._submit("BBB", later_plan, "next-day")
        self.assertIn("BBB", value.pending)
        report = value.equity_report()
        self.assertIsNone(report["account_drawdown_limit"])
        self.assertNotIn("equity_floor", report)
        self.assertNotIn("headroom", report)
        self.assertTrue(all("headroom" not in event for event in report["events"]))


class ProtectiveExitTests(unittest.TestCase):
    def test_cost_aware_breakeven_and_trailing_fixtures(self):
        for rule, expected in (("breakeven_1atr", Decimal("10.01")), ("trail_1atr", Decimal("10.02"))):
            value = engine(rule)
            position = enter(value)
            value.now += 2 * replay.NS
            observe(value, 10.12)
            with self.subTest(rule=rule):
                self.assertEqual(position["_entry"], Decimal("10.001"))
                self.assertTrue(position["protection_armed"])
                self.assertEqual(position["stop"], expected)
                initial_target = position["target"]
                value.now += replay.NS
                observe(value, 10.20)
                self.assertEqual(position["stop"], Decimal("10.10") if rule == "trail_1atr" else expected)
                value.now += replay.NS
                observe(value, 10.15)
                self.assertEqual(position["stop"], Decimal("10.10") if rule == "trail_1atr" else expected)
                self.assertEqual(position["target"], initial_target)
                self.assertEqual(position["decision_atr"], Decimal(".1"))

    def test_prefill_stale_invalid_and_incompatible_quotes_cannot_arm(self):
        for mode in ("prefill", "stale", "invalid", "basis"):
            value = engine("trail_1atr")
            position = enter(value)
            value.now += 2 * replay.NS
            event = value.now - replay.NS
            if mode == "prefill":
                event = position["_entry_ns"] - 1
            elif mode == "stale":
                event = value.now - 5 * replay.NS - 1
            elif mode == "basis":
                value._unknown_basis["AAA"] = "unknown basis"
            observe(value, 10.20, event=event, invalid=mode == "invalid")
            with self.subTest(mode=mode):
                self.assertFalse(position["protection_armed"])
                self.assertIsNone(position["highest_observed_bid"])
                self.assertIsNone(position["exit_reason"])

    def test_raw_quote_does_not_schedule_old_trigger_and_delays_apply_once(self):
        value = engine()
        position = enter(value)
        event = value.now + 2 * replay.NS
        value.now = event
        value._quote("AAA", quote(event, 9.8, 9.81, 40), OPEN, OPEN + 60 * replay.MINUTE)
        self.assertIsNone(position["exit_reason"])
        self.assertFalse(any(timer[3] == "quote_trigger" for timer in value.timers))
        drain(value, event + replay.NS)
        self.assertEqual(position["exit_reason"], "initial_stop")
        self.assertEqual(position["_exit_active"], event + 2 * replay.NS)
        value.now = position["_exit_active"]
        value._quote("AAA", quote(value.now, 9.8, 9.81, 40), OPEN, OPEN + 60 * replay.MINUTE)
        self.assertEqual(position["quantity"], 50)
        value.now += 1
        value._quote("AAA", quote(value.now, 9.8, 9.81, 40), OPEN, OPEN + 60 * replay.MINUTE)
        self.assertEqual(position["quantity"], 40)

    def test_zero_delay_entry_quote_is_evaluated_once_after_first_fill(self):
        for bid, expected in ((9.8, "initial_stop"), (9.99, None)):
            value = engine("trail_1atr", {"account": {"initial_cash": 1000},
                "timing": {"quote_delay_seconds": 0, "routing_delay_seconds": 0}})
            value._submit("AAA", plan(value), "decision")
            value.now += 1
            value._quote("AAA", quote(value.now, bid, 10, 200), OPEN, OPEN + 60 * replay.MINUTE)
            position = value.positions["AAA"]
            with self.subTest(bid=bid):
                self.assertEqual(position["exit_reason"], expected)
                self.assertEqual(len(value.fills), 1)
                if expected:
                    self.assertEqual(position["_exit_active"], value.now)
                    value.now += 1
                    value._quote("AAA", quote(value.now, bid, 10, 40), OPEN, OPEN + 60 * replay.MINUTE)
                    self.assertEqual(position["quantity"], 40)
                else:
                    self.assertEqual(position["highest_observed_bid"], Decimal(str(bid)))

    def test_deadline_equality_wins_over_price_exit(self):
        value = engine("trail_1atr")
        position = enter(value)
        value.now = position["_deadline"]
        observe(value, 9.8)
        self.assertEqual(position["exit_reason"], "holding_limit")
        self.assertFalse(value.protection_events)

    def test_same_observation_rounding_crossing_requests_later_exit(self):
        value = engine("breakeven_1atr")
        position = enter(value, atr=.001)
        value.now += 2 * replay.NS
        observe(value, 10.006)
        self.assertEqual(position["stop"], Decimal("10.01"))
        self.assertEqual(position["exit_reason"], "protection_stop")
        self.assertEqual(len(value.fills), 1)
        self.assertGreater(position["_exit_active"], value.now)

    def test_latched_protection_survives_partial_exits_and_gap_can_lose(self):
        value = engine("trail_1atr")
        position = enter(value)
        deadline = position["_deadline"]
        value.now += 2 * replay.NS
        observe(value, 10.2)
        value.now += replay.NS
        observe(value, 10.09)
        self.assertEqual(position["exit_reason"], "protection_stop")
        frozen_stop = position["stop"]
        value.now = position["_exit_active"] + 1
        value._quote("AAA", quote(value.now, 9, 9.01, 40), OPEN, OPEN + 60 * replay.MINUTE)
        self.assertEqual(position["quantity"], 40)
        self.assertLess(position["realized_net_pnl"], 0)
        value.now += 2 * replay.NS
        observe(value, 20)
        self.assertEqual(position["exit_reason"], "protection_stop")
        self.assertEqual(position["stop"], frozen_stop)
        self.assertEqual(position["_deadline"], deadline)


class AllInIntegrationTests(unittest.TestCase):
    def test_causal_alphabetical_choice_all_in_request_and_unknown_exit_retained(self):
        frozen = dataset(("BBB", "AAA"))
        for asset in frozen["sessions"][0]["assets"]:
            asset["quotes"] = [item for item in asset["quotes"] if replay._ns(item["t"]) <= OPEN + 22 * replay.MINUTE + 3 * replay.NS]
        value = engine()
        value.dataset = frozen
        result = value.run()
        buys = [fill for fill in result["fills"] if fill["side"] == "buy"]
        self.assertEqual(len(buys), 1)
        self.assertEqual(buys[0]["symbol"], "AAA")
        self.assertGreater(result["orders"][0]["quantity"], buys[0]["quantity"])
        self.assertEqual(result["summary"]["unresolved_positions"], 1)
        self.assertIsNone(result["summary"]["total_net_pnl"])

    def test_public_adapter_deterministic_metadata_and_no_frozen_source_changes(self):
        before = {name: model.source_hashes()[name] for name in model.PINNED}
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            (directory / "data").mkdir()
            catalog_path = make_catalog(directory / "data", dataset())
            calendar_path = calendar(directory / "calendar", [row("2026-09-16", "2026-09-17")])
            config = {"account": {"initial_cash": 1000}}
            first = model.run_catalog_all_in(catalog_path, config, calendar_path, "trail_1atr")
            second = model.run_catalog_all_in(catalog_path, config, calendar_path, "trail_1atr")
        self.assertEqual(first, second)
        self.assertEqual(first["model_id"], model.MODEL_ID)
        self.assertIsNone(first["effective_policy"]["account_drawdown_limit"])
        self.assertFalse(first["effective_policy"]["financial_risk_sizing"])
        self.assertFalse(first["effective_policy"]["planning_liquidity_cap"])
        self.assertTrue(first["effective_policy"]["actual_quote_capacity_retained"])
        self.assertIsNone(first["stable_profit_accepted_configuration"])
        self.assertEqual(before, {name: model.source_hashes()[name] for name in model.PINNED})

    def test_source_pin_and_unregistered_exit_rejected(self):
        with patch.object(model, "source_hashes", return_value={}):
            with self.assertRaisesRegex(ValueError, "dependencies changed"):
                model.run_catalog_all_in(Path("missing"), {}, Path("missing"))
        with self.assertRaisesRegex(ValueError, "exit rule"):
            engine("future_peak")


if __name__ == "__main__":
    unittest.main()
