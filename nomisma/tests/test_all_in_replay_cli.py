"""Immutable all-in replay checkpoints and source identity contracts."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("all_in_replay_cli", Path(__file__).resolve().parents[1] / "tools/all_in_replay.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class AllInCliTests(unittest.TestCase):
    def test_existing_output_is_preserved_and_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            (output / "existing.json").write_text("original")
            with patch.object(cli.all_in_replay, "run_catalog_all_in") as run:
                with self.assertRaisesRegex(ValueError, "new or empty"):
                    cli.execute("missing", "missing", "missing", "fixed_15m", output)
                run.assert_not_called()
            self.assertEqual((output / "existing.json").read_text(), "original")

    def test_source_mutation_cannot_produce_a_success_checkpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = [root / name for name in ("catalog.json", "config.json", "calendar.json")]
            for path in paths:
                path.write_text("{}")
            with patch.object(cli.all_in_replay, "run_catalog_all_in", return_value={}), \
                    patch.object(cli.all_in_replay, "source_hashes", side_effect=[{"source": "before"}, {"source": "after"}]):
                with self.assertRaisesRegex(ValueError, "changed during"):
                    cli.execute(*paths, "fixed_15m", root / "output")
            self.assertFalse((root / "output").exists())

    def test_checkpoint_names_policy_and_removed_controls_with_exact_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = [root / name for name in ("catalog.json", "config.json", "calendar.json")]
            for path in paths:
                path.write_text("{}")
            output = root / "output"
            result = {"summary": {"sessions": 9}, "exit_rule": "trail_1atr"}
            with patch.object(cli.all_in_replay, "run_catalog_all_in", return_value=result), \
                    patch.object(cli.calibration, "session_metrics", return_value={"sessions": []}):
                cli.execute(*paths, "trail_1atr", output)
            identity = json.loads((output / "execution.json").read_text())
            self.assertEqual(identity["result_sha256"], cli.sha(output / "result.json"))
            self.assertEqual(identity["exit_rule"], "trail_1atr")
            self.assertIn("cash_calendar.py", identity["source_sha256"])
            self.assertEqual(json.loads((output / "result.json").read_text()), result)
            self.assertFalse(identity["trading_execution_authorized"])
            self.assertIsNone(identity["effective_policy"]["account_drawdown_limit"])
            self.assertFalse(identity["effective_policy"]["planning_liquidity_cap"])
            self.assertTrue(identity["effective_policy"]["actual_quote_capacity_retained"])


if __name__ == "__main__":
    unittest.main()
