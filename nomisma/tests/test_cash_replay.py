"""Cash conservation, settlement availability, causal allocation and risk edges."""

from copy import deepcopy
from decimal import Decimal
import heapq
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from nomisma import cash_calendar, cash_replay, replay, trade_plan
from test_cash_calendar import calendar, row
from test_calibration import make_catalog, two_sessions
from test_replay import OPEN, dataset, quote
from test_trade_plan import market, NOW


def engine(variant="C_single_max"):
    config = replay.default_replay_config()
    config["account"]["initial_cash"] = 1000
    config["monitor"]["symbols"] = ["AAA", "BBB"]
    mapping = {"2026-09-16": "2026-09-17", "2026-09-17": "2026-09-18"}
    cal = cash_calendar.SettlementCalendar(tuple(mapping), "test", "test", "2026-09-18", mapping)
    value = cash_replay._CashReplay({"symbols": ["AAA", "BBB"], "sessions": []}, config, cal, variant)
    value.now = OPEN + 22 * replay.MINUTE
    return value


def plan(value, quantity=20, trigger=10, cap=10.25, stop=8.5):
    return {"sizing": {"quantity": quantity},
        "levels": {"entry_trigger": trigger, "entry_max": cap, "stop": stop},
        "expires_at": replay._iso(value.now + 120 * replay.NS)}


def fill_entry(value, quantity=20, capacity=None, symbol="AAA", price=10, cap=10.25, stop=8.5):
    value.costs["entry_slippage"] = Decimal(0)
    value._submit(symbol, plan(value, quantity, cap=cap, stop=stop), "test-decision")
    raw = quote(value.now, bid=price, ask=price, size=10000)
    value._bucket(symbol, "ask", Decimal(str(price)), 10000)
    value._observe_quote(symbol, raw)
    value._enter(symbol, value.pending[symbol], raw, quantity if capacity is None else capacity)


def fill_exit(value, price=10.10, capacity=10000, symbol="AAA"):
    value.costs["stop_slippage"] = Decimal(0)
    raw = quote(value.now, bid=price, ask=price, size=10000)
    value._bucket(symbol, "bid", Decimal(str(price)), 10000)
    value._exit(symbol, raw, capacity)


def drain(value, through):
    while value.timers and value.timers[0][0] <= through:
        stamp, _, _, kind, symbol, ident = heapq.heappop(value.timers)
        value.now = stamp
        value._control_timer(kind, symbol, ident)
    value.now = through


class CashAccountingTests(unittest.TestCase):
    def test_researcher_receivable_fixture_conserves_equity_on_settlement(self):
        value = engine()
        fill_entry(value)
        self.assertEqual(value.settled_cash, Decimal("799.98"))
        fill_exit(value)
        self.assertEqual(value.cash, Decimal("1001.96"))
        self.assertEqual(value.settled_cash, Decimal("799.98"))
        self.assertEqual(value._cash_state()["unsettled_cash"], Decimal("201.98"))
        self.assertEqual(value._valuation()["equity"], Decimal("1001.96"))
        before = (value.cash, value.realized, value._valuation()["equity"])
        release = replay._ns(value.receivables[0]["available_at"])
        drain(value, release - 1)
        self.assertEqual(value.settled_cash, Decimal("799.98"))
        drain(value, release)
        self.assertEqual(value.settled_cash, Decimal("1001.96"))
        self.assertEqual(value._cash_state()["unsettled_cash"], 0)
        self.assertEqual(before, (value.cash, value.realized, value._valuation()["equity"]))
        with self.assertRaisesRegex(AssertionError, "Duplicate"):
            value._control_timer("cash_settlement", "", 0)

    def test_multiple_entries_may_use_unspent_settled_cash_but_not_sale_proceeds(self):
        value = engine("A_cash_legacy")
        value.costs["entry_per_share"] = Decimal(0)
        fill_entry(value, quantity=90)
        fill_exit(value)
        self.assertEqual(value.settled_cash, 100)
        self.assertGreater(value.cash, 1000)
        self.assertEqual(value._context({})["cash"], 100)
        self.assertEqual(value._submission_blocker("BBB", plan(value, quantity=10)), "insufficient_settled_cash")
        self.assertIsNone(value._submission_blocker("BBB", plan(value, quantity=9)))

    def test_reservation_and_cancellation_do_not_change_cash_or_equity(self):
        value = engine()
        value._submit("AAA", plan(value), "decision")
        self.assertEqual(value._cash_state()["cash_reserved"], Decimal("205.020"))
        self.assertEqual(value._cash_state()["cash_available"], Decimal("794.980"))
        self.assertEqual(value._valuation()["equity"], 1000)
        self.assertEqual(value._choice_blocker(), "single_pending_entry")
        value._cancel("AAA", "entry_expired")
        self.assertEqual(value.settled_cash, 1000)
        self.assertEqual(value._cash_state()["cash_available"], 1000)
        self.assertIsNone(value._choice_blocker())
        self.assertFalse(value.daily_choices)

    def test_partial_ioc_consumes_day_and_releases_unfilled_reservation(self):
        value = engine()
        fill_entry(value, quantity=20, capacity=5)
        self.assertEqual(value.orders[0]["status"], "partial_ioc")
        self.assertEqual(value._cash_state()["cash_reserved"], 0)
        self.assertEqual(value.settled_cash, Decimal("949.995"))
        self.assertEqual(value.daily_choices["2026-09-16"]["quantity"], 5)
        self.assertEqual(value._choice_blocker(), "single_open_position")
        fill_exit(value)
        self.assertEqual(value._choice_blocker(), "daily_entry_already_used")
        value.now += 86400 * replay.NS
        self.assertIsNone(value._choice_blocker())

    def test_partial_exits_create_distinct_receivables_and_final_horizon_retains_them(self):
        value = engine()
        fill_entry(value)
        fill_exit(value, capacity=5)
        self.assertEqual(value.positions["AAA"]["quantity"], 15)
        fill_exit(value)
        self.assertEqual([r["amount"] for r in value.receivables], [Decimal("50.495"), Decimal("151.485")])
        self.assertEqual(len({r["fill_id"] for r in value.receivables}), 2)
        self.assertTrue(all(r["settled_at"] is None for r in value.cash_report()["receivables"]))

    def test_negative_net_exit_is_preserved_as_payable_then_settled_deficit(self):
        value = engine()
        value.costs["entry_per_share"] = Decimal(0)
        fill_entry(value, quantity=100, cap=10, stop=9.5)
        fill_exit(value, price=0)
        self.assertEqual(value.cash, Decimal("-.100"))
        self.assertEqual(value._cash_state()["unsettled_payables"], Decimal(".100"))
        self.assertEqual(value._cash_state()["cash_available"], 0)
        self.assertEqual(value._cash_state()["funding_deficit"], Decimal(".100"))
        self.assertTrue(value.breached)
        self.assertIsNone(value._context({}))
        drain(value, replay._ns(value.receivables[0]["available_at"]))
        self.assertEqual(value.settled_cash, Decimal("-.100"))
        self.assertEqual(value._cash_state()["unsettled_cash"], 0)

    def test_exit_fee_payable_cancels_competing_reservation_before_next_fill(self):
        value = engine("A_cash_legacy")
        value.costs["entry_per_share"] = Decimal(0)
        fill_entry(value, quantity=90, cap=10, stop=9.5)
        value._submit("BBB", plan(value, quantity=10, cap=10, stop=9.5), "pending")
        self.assertEqual(value._cash_state()["cash_available"], 0)
        fill_exit(value, price=0)
        self.assertFalse(value.pending)
        self.assertEqual(value.orders[-1]["status"], "cancelled")
        self.assertTrue(any(r["event"] == "funding_deficit_cancel" for r in value.ledger))
        self.assertEqual(value._cash_state()["unsettled_payables"], Decimal(".090"))
        self.assertEqual(value.cash, Decimal("99.910"))

    def test_carried_position_blocks_next_day_until_it_is_closed(self):
        value = engine()
        fill_entry(value)
        value.now += 86400 * replay.NS
        self.assertEqual(value._choice_blocker(), "single_open_position")
        fill_exit(value)
        self.assertIsNone(value._choice_blocker())
        self.assertEqual(value.receivables[0]["settlement_date"], "2026-09-18")


class CashPolicyTests(unittest.TestCase):
    def test_empty_interval_rejected_without_order_cash_or_timer(self):
        value = engine()
        impossible = plan(value, trigger=4.49, cap=4.49, stop=4.3)
        before = (value.cash, list(value.timers), len(value.orders))
        self.assertEqual(value._submission_blocker("AAA", impossible), "structurally_infeasible_entry")
        with self.assertRaisesRegex(ValueError, "structurally_infeasible"):
            value._submit("AAA", impossible, "bad-decision")
        self.assertEqual(before, (value.cash, value.timers, len(value.orders)))
        self.assertFalse(value.pending)
        equality = plan(value, trigger=4.49, cap=4.491, stop=4.3)
        self.assertIsNone(value._submission_blocker("AAA", equality))

    def test_C_removes_legacy_caps_but_respects_remaining_drawdown(self):
        value = engine()
        self.assertEqual(value._context({})["risk_budget"], 100)
        value.cash = value.settled_cash = Decimal(940)
        self.assertEqual(value._context({})["risk_budget"], 40)
        self.assertEqual(value._context({})["portfolio_risk_remaining"], 40)
        legacy = engine("B_single_legacy")
        self.assertEqual(legacy._context({})["risk_budget"], 25)
        self.assertEqual(legacy._context({})["portfolio_risk_remaining"], 75)
        value.cash = value.settled_cash = Decimal(1200)
        context = value._context({})
        self.assertEqual(context["max_position_notional"], 1200)
        self.assertEqual(context["risk_budget"], 100)
        value.loss_debits = Decimal(99)
        self.assertEqual(value._context({})["day_risk_remaining"], 100)

    def test_actual_planner_researcher_57_vs_14_risk_sizing(self):
        inputs = market()
        inputs["symbol"] = "AAA"
        for bar in inputs["minutes"]:
            bar.update(open=9.5, high=9.99, low=8.99, close=9.5, volume=1000000)
        inputs["quote"].update(bid=9.99, ask=10, bid_size_shares=10000, ask_size_shares=10000)
        for variant, expected in (("C_single_max", 57), ("B_single_legacy", 14)):
            value = engine(variant)
            value.now = replay._ns(NOW.isoformat())
            actual = trade_plan.build_trade_plan(inputs, {"policy": value.policy,
                "costs": value.config["costs"], "context": value._context({})})
            self.assertEqual(actual["levels"]["entry_max"], 10.25)
            self.assertEqual(actual["levels"]["stop"], 8.5)
            self.assertEqual(actual["sizing"]["quantity"], expected)
            self.assertEqual(actual["sizing"]["limiting_caps"]["cash"], 97)

    def test_unknown_marks_cancel_reservations_and_permanent_breach_does_not_reset(self):
        value = engine("A_cash_legacy")
        fill_entry(value, quantity=5)
        value._submit("BBB", plan(value, quantity=1), "second")
        value.observed_quotes.clear()
        value._sample("unknown")
        self.assertFalse(value.pending)
        self.assertIsNone(value._context({}))
        fill_exit(value, price=0)
        value.cash = value.settled_cash = Decimal(800)
        value.receivables.clear()
        value._sample("loss")
        self.assertTrue(value.breached)
        value.cash = value.settled_cash = Decimal(1100)
        value.now += 86400 * replay.NS
        self.assertEqual(value._context({})["risk_budget"], 0)

    def test_gap_guard_overshoot_uses_delayed_partial_exit_and_unsettled_cash(self):
        value = engine()
        fill_entry(value, quantity=20, cap=10, stop=9.5)
        value.now += replay.NS
        value._observe_quote("AAA", quote(value.now, bid=3, ask=3.01, size=40))
        self.assertTrue(value.breached)
        self.assertGreater(value.max_observed_drawdown, 100)
        self.assertEqual(value.positions["AAA"]["quantity"], 20)
        active = value.positions["AAA"]["_exit_active"]
        value.now = active
        value._quote("AAA", quote(active, bid=3, ask=3.01, size=40), OPEN, OPEN + 60 * replay.MINUTE)
        self.assertEqual(value.positions["AAA"]["quantity"], 20)
        value.now += 1
        value._quote("AAA", quote(value.now, bid=3, ask=3.01, size=40), OPEN, OPEN + 60 * replay.MINUTE)
        self.assertEqual(value.positions["AAA"]["quantity"], 10)
        self.assertEqual(value._cash_state()["unsettled_cash"], Decimal("29.980"))
        self.assertEqual(value.settled_cash, Decimal("799.980"))


class CashReplayIntegrationTests(unittest.TestCase):
    def run_fixture(self, frozen, variant="C_single_max"):
        value = engine(variant)
        value.dataset = deepcopy(frozen)
        value.config["monitor"]["symbols"] = list(frozen["symbols"])
        result = value.run()
        result["cash_account"] = value.cash_report()
        return result

    def test_simultaneous_first_feasible_alphabetical_choice_and_one_fill(self):
        frozen = dataset(("BBB", "AAA"))
        result = self.run_fixture(frozen)
        buys = [f for f in result["fills"] if f["side"] == "buy"]
        self.assertEqual(len(buys), 1)
        self.assertEqual(buys[0]["symbol"], "AAA")
        self.assertTrue(any(d["disposition"] == "single_pending_entry" for d in result["decisions"]))
        self.assertEqual(result, self.run_fixture(frozen))

    def test_infeasible_first_symbol_does_not_create_stale_order_reference(self):
        original = cash_replay.build_trade_plan
        def altered(inputs, settings):
            result = original(inputs, settings)
            if inputs["symbol"] == "AAA" and result["status"] in ("conditional", "wait"):
                result["levels"]["entry_max"] = result["levels"]["entry_trigger"]
            return result
        with patch.object(cash_replay, "build_trade_plan", side_effect=altered):
            result = self.run_fixture(dataset(("AAA", "BBB")))
        rejected = [d for d in result["decisions"] if d["disposition"] == "structurally_infeasible_entry"]
        self.assertTrue(rejected)
        self.assertTrue(all("order_id" not in d for d in rejected))
        self.assertEqual([f["symbol"] for f in result["fills"] if f["side"] == "buy"], ["BBB"])

    def test_future_price_changes_cannot_change_prior_decisions(self):
        frozen = dataset(("AAA", "BBB"))
        first = self.run_fixture(frozen)
        changed = deepcopy(frozen)
        cutoff = OPEN + 25 * replay.MINUTE
        for asset in changed["sessions"][0]["assets"]:
            for q in asset["quotes"]:
                if replay._ns(q["t"]) > cutoff:
                    q["bp"], q["ap"] = 100, 101
        second = self.run_fixture(changed)
        prior = lambda result: [d for d in result["decisions"] if replay._ns(d["at"]) <= cutoff]
        self.assertEqual(prior(first), prior(second))

    def test_streaming_two_dates_settles_before_new_day_purchase(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            (root / "data").mkdir()
            catalog = make_catalog(root / "data", two_sessions())
            cal = calendar(root / "calendar", [row("2026-09-16", "2026-09-17"), row("2026-09-17", "2026-09-18")])
            config = replay.default_replay_config()
            config["account"]["initial_cash"] = 1000
            config["monitor"]["symbols"] = ["AAA"]
            result = cash_replay.run_catalog_cash(catalog, config, cal)
            transfers = [r for r in result["ledger"] if r["event"] == "cash_settlement"]
            self.assertEqual(len(transfers), 1)
            self.assertEqual(transfers[0]["at"], "2026-09-17T13:30:00Z")
            self.assertEqual(len(result["cash_account"]["daily_choices"]), 2)
            self.assertTrue(any(r["settled_at"] is None for r in result["cash_account"]["receivables"]))
            with patch.object(cash_replay, "PINNED_RISK_SHA256", "changed"):
                with self.assertRaisesRegex(ValueError, "source changed"):
                    cash_replay.run_catalog_cash(catalog, config, cal)

    def test_settlement_posts_on_omitted_replay_day_not_later_opening(self):
        value = engine()
        fill_entry(value)
        fill_exit(value)
        next_session = deepcopy(dataset()["sessions"][0])
        shift = 2 * 86400 * replay.NS
        next_session.update(date="2026-09-18", open=replay._iso(OPEN + shift),
                            close=replay._iso(OPEN + shift + 60 * replay.MINUTE))
        # No signals/fills needed on the later date; prior settlement timers
        # must still drain at their own dates before this opening snapshot.
        next_session["assets"] = []
        value._session(next_session)
        transfer = next(r for r in value.ledger if r["event"] == "cash_settlement")
        self.assertEqual(transfer["at"], "2026-09-17T13:30:00Z")
        self.assertEqual(transfer["cash"], 1001.96)
        self.assertEqual(transfer["settled_cash"], 1001.96)


if __name__ == "__main__":
    unittest.main()
