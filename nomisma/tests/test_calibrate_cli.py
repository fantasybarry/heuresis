"""Checkpoint behavior protects reproducibility of the expensive offline sweep."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("calibration_cli", Path(__file__).resolve().parents[1] / "tools/calibrate.py")
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.identity = {"source_sha256": {"engine": "frozen"}, "catalog_sha256": "catalog"}
        self.config = {"policy": {"hold_minutes": 15}}
        self.result = {"run_fingerprint": "result", "summary": {"closed_trades": 0}}
        self.metrics = {"sessions": [], "aggregate": {"valid": False}}

    def save(self):
        with patch.object(cli, "source_hashes", return_value=self.identity["source_sha256"]), \
             patch.object(cli, "event"), \
             patch("nomisma.calibration.session_metrics", return_value=self.metrics):
            return cli.checkpoint(self.path, "policy", self.config, self.identity, lambda config: self.result)

    def test_completed_checkpoint_resumes_without_execution(self):
        expected = self.save()
        with patch.object(cli, "event"):
            actual = cli.checkpoint(self.path, "policy", self.config, self.identity,
                                    lambda config: self.fail("A verified complete result must be reused."))
        self.assertEqual(actual, expected)

    def test_modified_metrics_or_result_rejected(self):
        self.save()
        metrics_path = self.path / "policy/metrics.json"
        metrics_path.write_text(json.dumps({"aggregate": {"valid": True}}))
        with self.assertRaisesRegex(ValueError, "artifacts changed"):
            cli.checkpoint(self.path, "policy", self.config, self.identity, None)

    def test_changed_experiment_cannot_reuse_results(self):
        self.save()
        changed = {**self.identity, "catalog_sha256": "different"}
        with self.assertRaisesRegex(ValueError, "inputs/source differ"):
            cli.checkpoint(self.path, "policy", self.config, changed, None)

    def test_changed_exported_configuration_rejected(self):
        self.save()
        (self.path / "policy/config.json").write_text(json.dumps({"policy": {"hold_minutes": 99}}))
        with self.assertRaisesRegex(ValueError, "configuration changed"):
            cli.checkpoint(self.path, "policy", self.config, self.identity, None)

    def test_incomplete_output_preserved_and_not_reused(self):
        folder = self.path / "policy"
        folder.mkdir()
        marker = folder / "result.json.tmp"
        marker.write_text("interrupted")
        with self.assertRaisesRegex(ValueError, "Incomplete candidate"):
            cli.checkpoint(self.path, "policy", self.config, self.identity, None)
        self.assertEqual(marker.read_text(), "interrupted")

    def test_source_change_prevents_checkpoint(self):
        with patch.object(cli, "source_hashes", return_value={"engine": "changed"}), \
             patch.object(cli, "event"), \
             patch("nomisma.calibration.session_metrics", return_value=self.metrics):
            with self.assertRaisesRegex(RuntimeError, "Source changed"):
                cli.checkpoint(self.path, "policy", self.config, self.identity, lambda config: self.result)
        self.assertFalse((self.path / "policy/manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
