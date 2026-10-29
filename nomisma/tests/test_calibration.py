"""Pinned streaming parity and exposed-development metric/selection contracts."""

from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import weakref

from nomisma import calibration, calibration_data, replay
from test_calibration_data import parent_archive
from test_replay import OPEN, dataset


def make_catalog(directory, frozen):
    source = parent_archive(directory / "source", tuple(session["date"] for session in frozen["sessions"]), frozen["symbols"])
    content = calibration_data._canonical(frozen)
    source.write_bytes(content)
    manifest_path = source.parent / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["dataset"]["sha256"] = calibration_data._sha(content)
    manifest_path.write_bytes(calibration_data._canonical(manifest))
    return calibration_data.create_catalog([source], directory / "catalog")


def two_sessions(carry=False):
    frozen = dataset()
    if carry:
        asset = frozen["sessions"][0]["assets"][0]
        asset["quotes"] = [item for item in asset["quotes"] if replay._ns(item["t"]) <= OPEN + 22 * replay.MINUTE + 3 * replay.NS]
    second = deepcopy(dataset()["sessions"][0])
    second.update(date="2026-09-17", open=replay._iso(OPEN + 86400 * replay.NS),
                  close=replay._iso(OPEN + 86400 * replay.NS + 60 * replay.MINUTE),
                  previous_date="2026-09-16", prior_dates=second["prior_dates"][1:] + ["2026-09-16"])
    for asset in second["assets"]:
        for key in ("quotes", "trades", "minutes"):
            for item in asset[key]:
                item["t"] = replay._iso(replay._ns(item["t"]) + 86400 * replay.NS)
        asset["daily"].append(dict(asset["daily"][-1], date="2026-09-16"))
    frozen["sessions"].append(second)
    return frozen


def boundary(day, event, cash, positions=None):
    return {"event": event, "session_date": day,
            "at": day + ("T13:30:00Z" if event == "session_open" else "T20:00:00Z"),
            "cash": cash, "positions": positions or {}, "pending_symbols": [],
            "cash_reserved": 0, "scenario_risk_reserved": 0}


def cash_result(cash, days=("2026-09-16", "2026-09-17"), config=None):
    ledger = []
    for index, day in enumerate(days):
        ledger.extend([boundary(day, "session_open", cash[index]), boundary(day, "session_end", cash[index + 1])])
    return {"config": config or replay.default_replay_config(), "ledger": ledger, "fills": [],
            "trades": [], "decisions": [], "unresolved": [], "run_fingerprint": "fixture"}


class CandidateTests(unittest.TestCase):
    def test_exact_27_independent_configs_change_only_registered_grid(self):
        base = replay.default_replay_config()
        original = deepcopy(base)
        candidates = calibration.generate_candidates(base)
        self.assertEqual(len(candidates), 27)
        self.assertEqual(len({item["id"] for item in candidates}), 27)
        combinations = set()
        for candidate in candidates:
            config = deepcopy(candidate["config"])
            combinations.add(tuple(config["policy"][key] for key in calibration.GRID))
            for key in calibration.GRID:
                config["policy"][key] = base["policy"][key]
            self.assertEqual(config, base)
        self.assertEqual(len(combinations), 27)
        self.assertEqual(base, original)
        candidates[0]["config"]["costs"]["entry_slippage"] = 99
        self.assertEqual(candidates[1]["config"]["costs"]["entry_slippage"], .001)
        self.assertEqual(base, original)

    def test_frozen_reward_risk_gate_is_not_relaxed_to_force_trades(self):
        frozen = dataset()
        # Thin stop distance plus unchanged assumed costs fails robust net RR.
        for bar in frozen["sessions"][0]["assets"][0]["minutes"]:
            bar["high"] = bar["close"] + .001
            bar["low"] = bar["close"] - .001
        low = next(item for item in calibration.generate_candidates(replay.default_replay_config()) if item["id"] == "k1-r2-h05")
        low["config"]["monitor"]["symbols"] = frozen["symbols"]
        result = replay.run_replay(frozen, low["config"])
        alerts = [item for item in result["decisions"] if item["alert_level"]]
        self.assertTrue(alerts)
        self.assertTrue(any("reward/risk" in " ".join(item.get("plan", {}).get("reasons", [])) for item in alerts))
        self.assertEqual(result["summary"]["entry_fills"], 0)
        self.assertEqual(result["config"]["policy"]["min_net_rr"], 1.5)


class StreamingTests(unittest.TestCase):
    def test_semantic_parity_with_full_replay_including_carry_and_timers(self):
        frozen = two_sessions(carry=True)
        baseline = replay.run_replay(frozen)
        config = baseline["config"]
        with tempfile.TemporaryDirectory() as temporary:
            path = make_catalog(Path(temporary), frozen)
            streamed = calibration.run_catalog(path, config)
        self.assertEqual(calibration.semantic_result(streamed), calibration.semantic_result(baseline))
        self.assertNotEqual(streamed["dataset_fingerprint"], baseline["dataset_fingerprint"])
        self.assertEqual(streamed["summary"]["sessions"], 2)
        opens = [item for item in streamed["ledger"] if item["event"] == "session_open"]
        self.assertTrue(opens[1]["positions"])
        self.assertEqual(streamed["streaming"]["engine_sha256"], calibration.PINNED_REPLAY_SHA256)

    def test_requested_subset_does_not_read_other_session_and_repeats_identically(self):
        frozen = two_sessions()
        config = replay.run_replay(frozen)["config"]
        with tempfile.TemporaryDirectory() as temporary:
            path = make_catalog(Path(temporary), frozen)
            (path.parent / "sessions/2026-09-17.json").write_text("unreadable unrequested outcome")
            first = calibration.run_catalog(path, config, ["2026-09-16"])
            second = calibration.run_catalog(path, config, ["2026-09-16"])
        self.assertEqual(first, second)
        self.assertEqual(first["summary"]["sessions"], 1)

    def test_wrong_engine_pin_fails_before_any_catalog_outcomes_are_read(self):
        with patch.object(calibration_data, "load_catalog") as load:
            with self.assertRaisesRegex(ValueError, "engine hash"):
                calibration.run_catalog(Path("unused"), {}, expected_engine_sha256="wrong")
            load.assert_not_called()
        with patch.object(calibration, "replay_source_sha256", return_value="changed"):
            with self.assertRaisesRegex(ValueError, "engine hash"):
                calibration.run_catalog(Path("unused"), {})

    def test_chronological_selection_and_stream_boundaries_validated(self):
        frozen = two_sessions()
        with tempfile.TemporaryDirectory() as temporary:
            path = make_catalog(Path(temporary), frozen)
            config = replay.run_replay(frozen)["config"]
            with self.assertRaisesRegex(ValueError, "chronological"):
                calibration.run_catalog(path, config, ["2026-09-17", "2026-09-16"])
            second = deepcopy(frozen["sessions"][1])
            second["open"] = frozen["sessions"][0]["open"]
            with patch.object(calibration_data, "iter_sessions", return_value=iter([frozen["sessions"][0], second])):
                with self.assertRaisesRegex(ValueError, "nonoverlapping"):
                    calibration.run_catalog(path, config)

    def test_previous_session_reference_released_before_next_parse(self):
        frozen = two_sessions()
        with tempfile.TemporaryDirectory() as temporary:
            path = make_catalog(Path(temporary), frozen)
            class Session(dict):
                pass
            def stream(*args):
                item = Session(deepcopy(frozen["sessions"][0]))
                reference = weakref.ref(item)
                yield item
                del item
                self.assertIsNone(reference())
                yield deepcopy(frozen["sessions"][1])
            with patch.object(calibration_data, "iter_sessions", side_effect=stream):
                calibration.run_catalog(path, replay.run_replay(frozen)["config"])


class MetricTests(unittest.TestCase):
    def test_researcher_numerical_mean_total_return_and_close_drawdown(self):
        metrics = calibration.session_metrics(cash_result([10000, 9900, 9999]))
        self.assertEqual([row["session_return"] for row in metrics["sessions"]], [-.01, .01])
        aggregate = metrics["aggregate"]
        self.assertEqual(aggregate["mean_session_return"], 0)
        self.assertEqual(aggregate["compounded_session_return"], -.0001)
        self.assertEqual(aggregate["session_close_drawdown"], .01)
        self.assertEqual(aggregate["net_pnl"], -1)
        self.assertIsNone(aggregate["full_intraday_drawdown"])

    def test_cash_spent_on_open_position_is_not_scored_as_loss(self):
        result = cash_result([10000, 9900, 9999])
        result["ledger"][1]["positions"] = {"FTFT": 50}
        metrics = calibration.session_metrics(result)
        self.assertFalse(metrics["sessions"][0]["valid"])
        self.assertIsNone(metrics["sessions"][0]["session_return"])
        self.assertFalse(metrics["aggregate"]["valid"])
        self.assertIsNone(metrics["aggregate"]["mean_session_return"])
        self.assertIsNone(metrics["aggregate"]["net_pnl"])

    def test_nonpositive_cash_missing_boundaries_and_pending_exposure_invalid(self):
        for mode in ("zero", "negative", "missing", "pending"):
            result = cash_result([10000, 10000, 10000])
            if mode in ("zero", "negative"):
                result["ledger"][0]["cash"] = 0 if mode == "zero" else -1
            elif mode == "missing":
                del result["ledger"][1]
            else:
                result["ledger"][1].update(pending_symbols=["FTFT"], cash_reserved=100)
            with self.subTest(mode=mode):
                metrics = calibration.session_metrics(result)
                self.assertEqual(len(metrics["sessions"]), 2)
                self.assertFalse(metrics["aggregate"]["valid"])

    def test_fees_traded_days_symbols_and_flat_no_trade_dates_retained(self):
        result = cash_result([10000, 10010, 10010])
        result["fills"] = [{"at": "2026-09-16T14:00:00Z", "symbol": "TE", "side": "buy", "parent_id": "order1", "fee": .2},
                           {"at": "2026-09-16T14:15:00Z", "symbol": "TE", "side": "sell", "parent_id": "trade1", "fee": .2}]
        result["trades"] = [{"status": "closed", "exit_at": "2026-09-16T14:15:00Z"}]
        metrics = calibration.session_metrics(result)
        aggregate = metrics["aggregate"]
        self.assertEqual(aggregate["fees"], .4)
        self.assertEqual(aggregate["traded_days"], 1)
        self.assertEqual(aggregate["no_trade_days"], 1)
        self.assertEqual(aggregate["traded_symbols"], ["TE"])
        self.assertEqual(aggregate["opened_trades"], 1)
        self.assertEqual(aggregate["closed_trades"], 1)
        self.assertEqual(metrics["sessions"][1]["session_return"], 0)


class ComparisonTests(unittest.TestCase):
    def rows(self):
        configs = calibration.generate_candidates(replay.default_replay_config())
        first = next(item for item in configs if item["id"] == "k1-r2-h05")
        second = next(item for item in configs if item["id"] == "k1-r2-h15")
        return [{**first, "result": cash_result([10000, 10100, 9999], config=first["config"])},
                {**second, "result": cash_result([10000, 10000, 10000], config=second["config"])}]

    def test_fold_leader_selected_on_training_then_evaluated_on_validation(self):
        report = calibration.compare_candidates(iter(self.rows()), ["2026-09-16", "2026-09-17"],
            [{"id": "fold-1", "train_dates": ["2026-09-16"], "validation_dates": ["2026-09-17"]}])
        fold = report["folds"][0]
        self.assertEqual(fold["diagnostic_training_best_observed"], "k1-r2-h05")
        self.assertEqual(fold["validation_of_training_diagnostic"]["mean_session_return"], -.01)
        self.assertEqual(report["diagnostic_best_observed"]["candidate_id"], "k1-r2-h05")
        self.assertTrue(report["diagnostic_best_observed"]["posthoc"])
        self.assertIsNone(report["candidate_for_holdout"])
        self.assertIsNone(report["selected_config"])
        self.assertTrue(all(gate["status"] == "not_assessed" for gate in report["confidence_gates"].values()))
        self.assertEqual(report["neighbor_grid"][0]["neighbors"][0]["id"], "k1-r2-h15")

    def test_no_trade_policy_can_be_diagnostic_best_without_becoming_selection(self):
        rows = self.rows()
        rows[0]["result"] = cash_result([10000, 9900, 9800], config=rows[0]["config"])
        report = calibration.compare_candidates(rows, ["2026-09-16", "2026-09-17"], [])
        self.assertEqual(report["diagnostic_best_observed"]["candidate_id"], "k1-r2-h15")
        self.assertEqual(report["candidates"][1]["development"]["traded_days"], 0)
        self.assertEqual(report["calibration_status"], "development_only_insufficient_evidence")

    def test_invalid_scored_date_invalidates_entire_candidate_and_missing_dates_visible(self):
        rows = self.rows()
        rows[0]["result"]["ledger"][1]["positions"] = {"TE": 10}
        report = calibration.compare_candidates(rows, ["2026-09-16", "2026-09-17"], [])
        self.assertFalse(report["candidates"][0]["development"]["valid"])
        self.assertEqual(report["diagnostic_best_observed"]["candidate_id"], "k1-r2-h15")
        report = calibration.compare_candidates(rows, ["2026-09-16", "2026-09-17", "2026-09-18"], [])
        self.assertIsNone(report["diagnostic_best_observed"]["candidate_id"])
        self.assertIn("2026-09-18", report["candidates"][1]["development"]["invalid_dates"])

    def test_compact_api_and_generator_match_without_retaining_results(self):
        rows = self.rows()
        compact = [{"id": row["id"], "config": row["config"], "metrics": calibration.session_metrics(row["result"]),
                    "run_fingerprint": row["result"]["run_fingerprint"]} for row in rows]
        expected = calibration.compare_metrics(compact, ["2026-09-16", "2026-09-17"], [])
        self.assertEqual(expected, calibration.compare_candidates((row for row in rows), ["2026-09-16", "2026-09-17"], []))

    def test_validation_cannot_precede_training(self):
        with self.assertRaisesRegex(ValueError, "Training must precede"):
            calibration.compare_candidates(self.rows(), ["2026-09-16", "2026-09-17"],
                [{"id": "bad", "train_dates": ["2026-09-17"], "validation_dates": ["2026-09-16"]}])


if __name__ == "__main__":
    unittest.main()
