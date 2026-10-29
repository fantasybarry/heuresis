"""Causal input evidence, quantity conventions and explicit rejection paths."""

import copy
import json
import unittest
from nomisma.monitor_metrics import build_rows, demo_bundle, validate_monitor_config
from nomisma.planning_data import capture_planning_quote, prepare_plan_inputs


def fixture():
    bundle = demo_bundle(["DEMO"], 8)
    row = build_rows(bundle, validate_monitor_config({"symbols": ["DEMO"]}), bundle["as_of"])[0]
    return {"symbol": "DEMO", "source": "demo", "feed": "synthetic", "level": "Buy",
            "session": copy.deepcopy(bundle["session"]), "session_date": bundle["session"]["date"],
            "market_time": row["signal_bar_at"], "snapshot": row, "created_at": "2026-09-16T14:00:00Z"}


def quote_at(stamp, source="alpaca", feed="sip", **changes):
    raw = {"t": stamp, "_received_at": stamp, "bp": 2, "ap": 2.01, "bs": 200, "as": 300}
    raw.update(changes)
    return capture_planning_quote(raw, source, feed)


class QuoteCaptureTests(unittest.TestCase):
    def test_sip_share_convention_starts_on_exchange_date_without_multiplication(self):
        old = quote_at("2025-11-03T00:01:00Z")  # Still November 2 in New York.
        new = quote_at("2025-11-03T14:30:00Z")
        self.assertEqual(old["size_unit"], "unknown")
        self.assertIsNone(old["bid_size_shares"])
        self.assertEqual(old["bid_size_raw"], 200)
        self.assertEqual(new["size_unit"], "shares")
        self.assertEqual(new["bid_size_shares"], 200)
        self.assertEqual(new["ask_size_shares"], 300)
        self.assertIn("2025-11-03", new["size_basis"])

    def test_known_zero_size_is_zero_capacity_not_missing_evidence(self):
        result = quote_at("2026-09-16T14:30:00Z", bs=0, **{"as": 0})
        self.assertEqual(result["bid_size_shares"], 0)
        self.assertEqual(result["ask_size_shares"], 0)

    def test_iex_and_unknown_sources_never_guess_lot_size(self):
        for source, feed in (("alpaca", "iex"), ("alpaca", "delayed_sip"), ("other", "sip")):
            result = quote_at("2026-09-16T14:30:00Z", source, feed)
            self.assertEqual(result["size_unit"], "unknown")
            self.assertIsNone(result["ask_size_shares"])

    def test_demo_sizes_are_explicit_shares_even_before_provider_change(self):
        result = quote_at("2025-05-14T14:18:09Z", "demo", "synthetic")
        self.assertEqual(result["ask_size_shares"], 300)
        self.assertIn("synthetic", result["size_basis"])

    def test_missing_receipt_not_invented_and_raw_input_not_mutated(self):
        raw = {"t": "2026-09-16T14:30:00.123456789Z", "bp": 2, "ap": 2.01, "bs": 200, "as": 300}
        before = copy.deepcopy(raw)
        result = capture_planning_quote(raw, "alpaca", "sip")
        self.assertEqual(raw, before)
        self.assertIsNone(result["received_at"])
        self.assertEqual(result["event_at"], "2026-09-16T14:30:00.123456+00:00")

    def test_invalid_quantities_are_null_not_coerced_and_output_is_finite(self):
        for size in (True, "200", float("nan"), float("inf"), -2, 1.5, 10**1000):
            result = quote_at("2026-09-16T14:30:00Z", bs=size)
            self.assertIsNone(result["bid_size_shares"], repr(size))
            json.dumps(result, allow_nan=False)


class PlanningInputTests(unittest.TestCase):
    def test_valid_original_evidence_uses_simulation_clock_and_does_not_mutate(self):
        alert = fixture()
        before = copy.deepcopy(alert)
        result = prepare_plan_inputs(alert)
        self.assertTrue(result["valid"], result["blockers"])
        self.assertEqual(result["decision_at"], "2025-05-14T14:18:10+00:00")
        self.assertEqual(len(result["minutes"]), 48)
        self.assertEqual(result["quote"]["ask_size_shares"], 10000)
        self.assertIsNone(result["halted"])
        self.assertEqual(alert, before)
        json.dumps(result, allow_nan=False)

    def test_legacy_snapshot_has_no_created_at_or_reference_time_fallback(self):
        for missing in ("decision_at", "planning_quote"):
            alert = fixture()
            del alert["snapshot"][missing]
            result = prepare_plan_inputs(alert)
            self.assertFalse(result["valid"])
            self.assertIn("Original", " ".join(result["blockers"]))

    def test_quote_schema_version_is_an_integer_and_supported(self):
        for version in (None, True, "1", 2):
            alert = fixture()
            alert["snapshot"]["planning_quote"]["schema_version"] = version
            self.assertFalse(prepare_plan_inputs(alert)["valid"])

    def test_unknown_size_and_missing_size_do_not_block_geometry(self):
        alert = fixture()
        alert["source"] = alert["snapshot"]["source"] = "alpaca"
        alert["feed"] = alert["snapshot"]["feed"] = "sip"
        # May 2025 SIP units are unknown; keep original raw values.
        alert["snapshot"]["planning_quote"] = quote_at(
            "2025-05-14T14:18:09Z", _received_at="2025-05-14T14:18:10Z")
        result = prepare_plan_inputs(alert)
        self.assertTrue(result["valid"], result["blockers"])
        self.assertIsNone(result["quote"]["ask_size_shares"])
        self.assertIn("sizing", " ".join(result["warnings"]))
        alert = fixture()
        quote = alert["snapshot"]["planning_quote"]
        quote["ask_size_raw"] = quote["ask_size_shares"] = None
        self.assertTrue(prepare_plan_inputs(alert)["valid"])

    def test_declared_normalization_cannot_override_documented_units(self):
        alert = fixture()
        quote = alert["snapshot"]["planning_quote"]
        quote["ask_size_shares"] *= 100
        result = prepare_plan_inputs(alert)
        self.assertFalse(result["valid"])
        self.assertIsNone(result["quote"]["ask_size_shares"])

    def test_invalid_quote_prices_are_explicit_blockers(self):
        for field, value in (("bid", True), ("bid", 0), ("ask", float("nan")),
                             ("ask", float("inf")), ("ask", "2.5"), ("ask", 0.5)):
            alert = fixture()
            alert["snapshot"]["planning_quote"][field] = value
            result = prepare_plan_inputs(alert)
            self.assertFalse(result["valid"], (field, value))
            self.assertIn("two-sided", " ".join(result["blockers"]))
            json.dumps(result, allow_nan=False)

    def test_quote_event_receipt_order_freshness_and_awareness(self):
        cases = [("event_at", "2025-05-14T14:18:04Z"),
                 ("event_at", "2025-05-14T14:18:11Z"),
                 ("received_at", "2025-05-14T14:18:11Z"),
                 ("received_at", "2025-05-14T14:18:08Z"),
                 ("received_at", None), ("event_at", "2025-05-14T14:18:09")]
        for field, value in cases:
            alert = fixture()
            alert["snapshot"]["planning_quote"][field] = value
            result = prepare_plan_inputs(alert)
            self.assertFalse(result["valid"], (field, value))
            self.assertIn("5 seconds", " ".join(result["blockers"]))
        alert = fixture()
        alert["snapshot"]["planning_quote"]["event_at"] = "2025-05-14T14:18:05Z"
        self.assertTrue(prepare_plan_inputs(alert)["valid"])

    def test_malformed_missing_duplicate_and_unsorted_bars_are_not_repaired(self):
        for kind in ("missing", "duplicate", "reversed", "malformed", "opening", "empty", "few"):
            alert = fixture()
            bars = alert["snapshot"]["chart"]
            if kind == "missing":
                del bars[5]
            elif kind == "duplicate":
                bars.insert(5, copy.deepcopy(bars[5]))
            elif kind == "reversed":
                bars.reverse()
            elif kind == "malformed":
                bars[5] = None
            elif kind == "opening":
                del bars[0]
            elif kind == "empty":
                bars.clear()
            elif kind == "few":
                del bars[14:]
            result = prepare_plan_inputs(alert)
            self.assertFalse(result["valid"], kind)
            self.assertEqual(result["minutes"], [], kind)

    def test_bar_numeric_and_timestamp_validation(self):
        for key, value in (("low", 999), ("high", 0.1), ("open", False),
                           ("close", float("inf")), ("volume", -1), ("volume", 1.5),
                           ("volume", "200"), ("t", "2025-05-14T13:35:01Z"),
                           ("t", "2025-05-14T14:19:00Z"), ("t", "2025-05-14T13:35:00")):
            alert = fixture()
            alert["snapshot"]["chart"][5][key] = value
            result = prepare_plan_inputs(alert)
            self.assertFalse(result["valid"], (key, value))
            self.assertEqual(result["minutes"], [])
            json.dumps(result, allow_nan=False)

    def test_bar_staleness_and_signal_alignment(self):
        alert = fixture()
        alert["snapshot"]["chart"] = alert["snapshot"]["chart"][:-3]
        result = prepare_plan_inputs(alert)
        self.assertIn("120 seconds", " ".join(result["blockers"]))
        self.assertIn("signal timestamps", " ".join(result["blockers"]))

    def test_fifteen_bars_allow_geometry_without_twenty_bar_capacity(self):
        alert = fixture()
        row = alert["snapshot"]
        row["chart"] = row["chart"][:15]
        row["decision_at"] = "2025-05-14T13:45:01Z"
        row["signal_bar_at"] = alert["market_time"] = row["chart"][-1]["t"]
        row["planning_quote"] = quote_at("2025-05-14T13:45:00Z", "demo", "synthetic")
        result = prepare_plan_inputs(alert)
        self.assertTrue(result["valid"], result["blockers"])
        self.assertEqual(len(result["minutes"]), 15)

    def test_provenance_session_and_eligibility_mismatches(self):
        cases = [("snapshot", "source", "alpaca"), ("snapshot", "symbol", "OTHER"),
                 ("snapshot", "session_date", "2025-05-15"), ("session", "date", "2025-05-15"),
                 ("snapshot", "decision_at", "2025-05-14T20:00:00Z"),
                 ("snapshot", "alert_eligible", False), ("planning_quote", "feed", "sip")]
        for container, key, value in cases:
            alert = fixture()
            target = alert["snapshot"]["planning_quote"] if container == "planning_quote" else alert[container]
            target[key] = value
            self.assertFalse(prepare_plan_inputs(alert)["valid"], (container, key))

    def test_known_halt_blocks_and_unknown_halt_remains_visible(self):
        alert = fixture()
        alert["snapshot"]["trading_status"]["halted"] = True
        result = prepare_plan_inputs(alert)
        self.assertFalse(result["valid"])
        self.assertTrue(result["halted"])
        self.assertIn("halt", " ".join(result["blockers"]))

    def test_arbitrary_missing_evidence_returns_diagnostics_not_exceptions(self):
        for value in (None, [], {}, {"snapshot": []}, {"session": False}):
            result = prepare_plan_inputs(value)
            self.assertFalse(result["valid"])
            self.assertTrue(result["blockers"])
            json.dumps(result, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
