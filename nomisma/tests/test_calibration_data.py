"""Catalog lineage, selective loading, and bounded acquisition contracts."""
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from nomisma import calibration_data as data


def parent_archive(directory, days=("2026-09-11", "2026-09-14"), symbols=("FTFT", "SES", "TE")):
    directory.mkdir()
    (directory / "raw").mkdir()
    raw_body = b'{"bars":{}}'
    raw = gzip.compress(raw_body, mtime=0)
    (directory / "raw/00001.json.gz").write_bytes(raw)
    sessions = [{"date": day, "open": day + "T13:30:00Z", "close": day + "T20:00:00Z",
                 "assets": [{"symbol": symbol, "minutes": [], "daily": [], "quotes": [], "trades": [],
                             "quality": {"data_blockers": ["Fixture has no market observations."]}}
                            for symbol in symbols]} for day in days]
    dataset = {"schema_version": 1, "source": "alpaca", "feed": "sip", "symbols": list(symbols),
               "sessions": sessions, "manifest": "manifest.json", "provenance": {"test_fixture": True}}
    content = data._canonical(dataset)
    (directory / "dataset.json").write_bytes(content)
    manifest = {"schema_version": 1, "status": "complete", "symbols": list(symbols), "session_dates": list(days),
                "dataset": {"path": "dataset.json", "sha256": data._sha(content)},
                "pages": [{"path": "raw/00001.json.gz", "sha256": data._sha(raw), "body_sha256": data._sha(raw_body)}]}
    (directory / "manifest.json").write_bytes(data._canonical(manifest))
    return directory / "dataset.json"


class CalibrationDataTests(unittest.TestCase):
    def test_split_exact_and_parent_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = parent_archive(directory / "parent")
            original = source.read_bytes()
            path = data.create_catalog([source], directory / "catalog")
            metadata = data.load_catalog(path)
            self.assertEqual([row["date"] for row in metadata["sessions"]], ["2026-09-11", "2026-09-14"])
            self.assertTrue(all(row["exposed"] and row["partition"] == "development" for row in metadata["sessions"]))
            self.assertEqual(list(data.iter_sessions(path)), json.loads(original)["sessions"])
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(metadata["sources"][0]["dataset_sha256"], data._sha(original))

    def test_excluded_session_contents_never_opened(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path = data.create_catalog([parent_archive(directory / "parent")], directory / "catalog")
            excluded = directory / "catalog/sessions/2026-09-14.json"
            excluded.write_bytes(b"Deliberately unreadable JSON; must not be opened")
            selected = list(data.iter_sessions(path, ["2026-09-11"]))
            self.assertEqual([row["date"] for row in selected], ["2026-09-11"])
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                list(data.iter_sessions(path))

    def test_metadata_and_selected_session_tampering_detected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path = data.create_catalog([parent_archive(directory / "parent")], directory / "catalog")
            catalog = json.loads(path.read_bytes())
            manifest = directory / "catalog" / catalog["sources"][0]["manifest_path"]
            original = manifest.read_bytes()
            manifest.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "manifest hash mismatch"):
                data.load_catalog(path)
            manifest.write_bytes(original)
            catalog["symbols"] = ["OTHER"]
            path.write_bytes(data._canonical(catalog))
            with self.assertRaisesRegex(ValueError, "metadata hash differs"):
                data.load_catalog(path)

    def test_duplicate_dates_and_cohort_mismatch_fail_closed(self):
        for mode in ("dates", "cohort"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                first = parent_archive(directory / "first", days=("2026-09-11",))
                second = parent_archive(directory / "second", days=("2026-09-11",) if mode == "dates" else ("2026-09-14",),
                                        symbols=("FTFT", "SES", "TE") if mode == "dates" else ("TE",))
                with self.assertRaisesRegex(ValueError, "Duplicate session|different cohorts"):
                    data.create_catalog([first, second], directory / "catalog")
                self.assertFalse((directory / "catalog/catalog.json").exists())
                self.assertEqual(json.loads((directory / "catalog/build_status.json").read_bytes())["status"], "incomplete")

    def test_parent_raw_hash_checked_before_splitting(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = parent_archive(directory / "parent")
            (source.parent / "raw/00001.json.gz").write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                data.create_catalog([source], directory / "catalog")
            self.assertFalse((directory / "catalog/catalog.json").exists())

    def test_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path = data.create_catalog([parent_archive(directory / "parent")], directory / "catalog")
            session = directory / "catalog/sessions/2026-09-11.json"
            outside = directory / "outside.json"
            session.rename(outside)
            session.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "symbolic links"):
                list(data.iter_sessions(path, ["2026-09-11"]))

    def test_sealed_holdout_excluded_and_explicit_request_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path = data.create_catalog([parent_archive(directory / "parent")], directory / "catalog")
            catalog = json.loads(path.read_bytes())
            catalog["sessions"][1]["partition"] = "sealed_holdout"
            catalog["catalog_sha256"] = data._catalog_digest(catalog)
            path.write_bytes(data._canonical(catalog))
            (directory / "catalog/sessions/2026-09-14.json").write_bytes(b"sealed outcomes must never be read")
            self.assertEqual([row["date"] for row in data.iter_sessions(path)], ["2026-09-11"])
            with self.assertRaisesRegex(ValueError, "Sealed holdout"):
                list(data.iter_sessions(path, ["2026-09-14"]))

    def test_download_sequential_budget_and_partial_failure_visible(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            calls = []
            def downloader(output, symbols, dates, max_requests):
                calls.append((dates, max_requests))
                if len(calls) == 2:
                    raise ValueError("request budget exhausted")
                output.mkdir()
                path = output / "dataset.json"
                path.write_text("{}")
                return path
            with patch.object(data.replay_data, "download_dataset", side_effect=downloader):
                with self.assertRaisesRegex(ValueError, "budget exhausted"):
                    data.download_development(directory / "batch", ["TE"], ["2026-09-04", "2026-09-03"], 200)
            self.assertEqual(calls, [(["2026-09-03"], 200), (["2026-09-04"], 200)])
            manifest = json.loads((directory / "batch/development_batch.json").read_bytes())
            self.assertEqual(manifest["max_requests_total"], 400)
            self.assertEqual(manifest["status"], "incomplete")
            self.assertEqual(len(manifest["archives"]), 1)


if __name__ == "__main__":
    unittest.main()
