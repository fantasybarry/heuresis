"""Immutable cash-run outputs and source identity checks."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("cash_replay_cli", Path(__file__).resolve().parents[1] / "tools/cash_replay.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class CashCliTests(unittest.TestCase):
    def test_existing_output_is_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            (output / "existing.json").write_text("original")
            with patch.object(cli.cash_replay, "run_catalog_cash") as run:
                with self.assertRaisesRegex(ValueError, "new or empty"):
                    cli.execute("missing", "missing", "missing", "C_single_max", output)
                run.assert_not_called()
            self.assertEqual((output / "existing.json").read_text(), "original")

    def test_source_mutation_prevents_successful_checkpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = [root / name for name in ("catalog.json", "config.json", "calendar.json")]
            for path in paths:
                path.write_text("{}")
            with patch.object(cli.cash_replay, "run_catalog_cash", return_value={}), \
                    patch.object(cli.cash_replay, "source_hashes", side_effect=[{"source": "before"}, {"source": "after"}]):
                with self.assertRaisesRegex(ValueError, "changed during"):
                    cli.execute(*paths, "C_single_max", root / "output")
            self.assertFalse((root / "output").exists())

    def test_checkpoint_records_source_inputs_and_exact_result_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = [root / name for name in ("catalog.json", "config.json", "calendar.json")]
            for path in paths:
                path.write_text("{}")
            output = root / "output"
            result = {"summary": {"sessions": 9}}
            with patch.object(cli.cash_replay, "run_catalog_cash", return_value=result), \
                    patch.object(cli.calibration, "session_metrics", return_value={"sessions": []}):
                cli.execute(*paths, "C_single_max", output)
            identity = json.loads((output / "execution.json").read_text())
            self.assertEqual(identity["result_sha256"], cli.sha(output / "result.json"))
            self.assertIn("cash_calendar.py", identity["source_sha256"])
            self.assertEqual(json.loads((output / "result.json").read_text()), result)
            self.assertFalse(identity["trading_execution_authorized"])


if __name__ == "__main__":
    unittest.main()
