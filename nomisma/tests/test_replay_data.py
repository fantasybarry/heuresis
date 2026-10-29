"""Offline archive invariants, including adversarial and incomplete responses."""
from datetime import date, timedelta
from decimal import Decimal
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from nomisma import replay_data as data

DAY = "2026-09-11"
STAMP = "2026-09-11T13:30:00Z"


def fixture(url, params, headers):
    if url.endswith("calendar"):
        begin = date(2026, 6, 1)
        return [{"date": (begin + timedelta(days=i)).isoformat(), "open": "09:30", "close": "16:00"}
                for i in range(103) if (begin + timedelta(days=i)).weekday() < 5]
    if url.endswith("meta/conditions/quote"):
        return {"R": "Regular, two-sided open quote"}
    symbols = params["symbols"].split(",")
    if url.endswith("bars"):
        if params["timeframe"] == "1Day":
            start = date(2026, 6, 3)
            bars = [{"t": (start + timedelta(days=i)).isoformat() + "T04:00:00Z", "o": 2, "h": 2.1, "l": 1.9, "c": 2, "v": 10000} for i in range(100) if (start + timedelta(days=i)).weekday() < 5]
        else:
            bars = [{"t": STAMP, "o": 2, "h": 2.1, "l": 1.9, "c": 2, "v": 1000, "vw": 2}]
        return {"bars": {s: bars for s in symbols}, "next_page_token": None}
    if url.endswith("quotes"):
        return {"quotes": {s: [{"t": "2026-09-11T13:30:00.123456789Z", "bp": 1.99, "ap": 2.01, "bs": 100, "as": 200, "c": ["R"], "z": "C"}] for s in symbols}}
    return {"trades": {s: [{"t": "2026-09-11T13:30:00.123456790Z", "p": 2, "s": 100, "i": 7, "x": "V", "c": ["@"]}] for s in symbols}}


class ReplayDataTests(unittest.TestCase):
    def test_nanoseconds_preserved_and_offsets_equivalent(self):
        a = data.timestamp_ns("2026-09-11T13:30:00.123456789Z")
        self.assertEqual(data.timestamp_ns("2026-09-11T09:30:00.123456789-04:00"), a)
        self.assertEqual(data.timestamp_ns("2026-09-11T13:30:00.123456790Z") - a, 1)
        with self.assertRaises(ValueError):
            data.timestamp_ns("2026-09-11T13:30:00")

    def test_complete_archive_integrity_and_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = data.download_dataset(directory, ["TE"], [DAY], requester=fixture)
            dataset = data.load_dataset(path)
            asset = dataset["sessions"][0]["assets"][0]
            self.assertIsNone(dataset["provenance"]["original_received_at"])
            self.assertEqual(asset["quotes"][0]["t"], "2026-09-11T13:30:00.123456789Z")
            self.assertEqual(len(asset["quality"]["missing_rth_minutes"]), 389)
            self.assertEqual(asset["quality"]["data_blockers"], [])
            self.assertEqual(asset["quality"]["daily_split_to_session_factor"], "1")
            manifest = json.loads((Path(directory) / "manifest.json").read_text())
            self.assertEqual(manifest["request_count"], 9)
            raw = Path(directory) / manifest["pages"][0]["path"]
            self.assertIsInstance(json.loads(gzip.decompress(raw.read_bytes())), list)
            raw.write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                data.load_dataset(path)

    def test_budget_failure_preserves_incomplete_raw_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "budget exhausted"):
                data.download_dataset(directory, ["TE"], [DAY], max_requests=1, requester=fixture)
            manifest = json.loads((Path(directory) / "manifest.json").read_text())
            self.assertEqual(manifest["status"], "incomplete")
            self.assertEqual(len(manifest["pages"]), 1)
            self.assertFalse((Path(directory) / "dataset.json").exists())
            with self.assertRaisesRegex(ValueError, "incomplete"):
                data.load_dataset(Path(directory) / "dataset.json")

    def test_non_object_events_abort_archive_with_raw_evidence(self):
        for endpoint in ("quotes", "trades"):
            with self.subTest(endpoint=endpoint), tempfile.TemporaryDirectory() as directory:
                def malformed(url, params, headers):
                    if url.endswith("/" + endpoint):
                        return {endpoint: {"TE": [None]}}
                    return fixture(url, params, headers)
                with self.assertRaisesRegex(ValueError, "unorderable non-object event"):
                    data.download_dataset(directory, ["TE"], [DAY], requester=malformed)
                manifest = json.loads((Path(directory) / "manifest.json").read_text())
                self.assertEqual(manifest["status"], "incomplete")
                self.assertFalse((Path(directory) / "dataset.json").exists())
                event = next(row for row in manifest["quality"] if row["kind"] == "malformed_record")
                self.assertEqual(event["session_date"], DAY)
                self.assertEqual(event["endpoint"], endpoint)
                page = Path(directory) / manifest["pages"][-1]["path"]
                self.assertEqual(json.loads(gzip.decompress(page.read_bytes()))[endpoint]["TE"], [None])

    def test_pagination_must_finish_and_repeated_tokens_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            def repeated(url, params, headers):
                return {"quotes": {"TE": []}, "next_page_token": "again"}
            archive = data._Archive(Path(directory), 10, repeated, {})
            with self.assertRaisesRegex(ValueError, "token repeated"):
                archive.paged("quotes", ["TE"], {})
            self.assertEqual(archive.requests, 2)

    def test_crossed_quote_is_timeline_invalidation_not_silently_removed(self):
        quality = []
        quote = {"t": STAMP, "bp": 3, "ap": 2, "bs": 100, "as": 100, "_ordinal": 1}
        rows = data._events([quote], "quotes", data.timestamp_ns(STAMP), data.timestamp_ns(STAMP) + 10**9, quality, {})
        self.assertEqual(rows[0]["_invalid_reason"], "crossed_quote")
        self.assertEqual(quality[0]["kind"], "crossed_quote")

    def test_duplicate_trade_and_native_order(self):
        quality = []
        trade = {"t": STAMP, "p": 2, "s": 3, "i": 7, "x": "V", "_ordinal": 1}
        rows = data._events([trade, dict(trade, _ordinal=2)], "trades", data.timestamp_ns(STAMP), data.timestamp_ns(STAMP) + 10**9, quality, {})
        self.assertEqual(len(rows), 1)
        self.assertEqual(quality[0]["kind"], "duplicate_trade_identity")

    def test_reused_trade_id_retains_distinct_market_observations(self):
        quality = []
        first = {"t": STAMP, "p": 2, "s": 3, "i": 7, "x": "D", "_ordinal": 1}
        second = dict(first, t="2026-09-11T13:30:00.000000001Z", p=2.5, _ordinal=2)
        rows = data._events([first, second], "trades", data.timestamp_ns(STAMP), data.timestamp_ns(STAMP) + 10**9, quality, {})
        self.assertEqual([row["p"] for row in rows], [2, 2.5])
        self.assertEqual(quality[0]["kind"], "reused_trade_id_preserved")

    def test_invalid_trade_remains_timeline_invalidation(self):
        trade = {"t": STAMP, "p": 0, "s": 1, "_ordinal": 1}
        rows = data._events([trade], "trades", data.timestamp_ns(STAMP), data.timestamp_ns(STAMP) + 10**9, [], {})
        self.assertEqual(rows[0]["_invalid_reason"], "invalid_trade")

    def test_resume_reuses_verified_prefix_and_original_acquisition_times(self):
        with tempfile.TemporaryDirectory() as directory:
            old, new = Path(directory)/"old", Path(directory)/"new"
            with self.assertRaisesRegex(ValueError, "budget exhausted"):
                data.download_dataset(old, ["TE"], [DAY], max_requests=4, requester=fixture)
            before = json.loads((old/"manifest.json").read_text())
            calls = []
            def count(url, params, headers):
                calls.append(url)
                return fixture(url, params, headers)
            path = data.download_dataset(new, ["TE"], [DAY], requester=count, resume_from=old)
            self.assertEqual(len(calls), 5)
            after = json.loads((new/"manifest.json").read_text())
            self.assertEqual((after["reused_page_count"], after["network_request_count"]), (4, 5))
            self.assertEqual(after["pages"][0]["retrieved_at"], before["pages"][0]["retrieved_at"])
            self.assertEqual(data.load_dataset(path)["symbols"], ["TE"])

    def test_resume_rejects_tampering_and_changed_request_sequence(self):
        for attack in ("raw", "params"):
            with self.subTest(attack=attack), tempfile.TemporaryDirectory() as directory:
                old, new = Path(directory)/"old", Path(directory)/"new"
                with self.assertRaises(ValueError):
                    data.download_dataset(old, ["TE"], [DAY], max_requests=1, requester=fixture)
                path = old/"manifest.json"
                manifest = json.loads(path.read_text())
                if attack == "raw":
                    (old/manifest["pages"][0]["path"]).write_bytes(b"tampered")
                else:
                    manifest["pages"][0]["params"]["end"] = "2000-01-01"
                    path.write_text(json.dumps(manifest))
                with self.assertRaisesRegex(ValueError, "hash mismatch|sequence differs"):
                    data.download_dataset(new, ["TE"], [DAY], requester=fixture, resume_from=old)

    def test_future_split_scale_rebased_and_changes_rejected(self):
        raw = [{"t": STAMP, "open": 4, "high": 4, "low": 4, "close": 4, "volume": 100}]
        split = [dict(raw[0], open=2, high=2, low=2, close=2, volume=200)]
        factor, error = data._basis(raw, split, data.timestamp_ns(STAMP))
        self.assertEqual(factor, Decimal(2))
        self.assertIsNone(error)
        rebased = data._rescale_daily([dict(split[0], date=DAY)], factor)
        self.assertEqual(rebased[0]["close"], 4)
        self.assertEqual(rebased[0]["volume"], 100)
        split[0]["high"] = 2.5
        self.assertIsNotNone(data._basis(raw, split, data.timestamp_ns(STAMP))[1])

    def test_conflicting_bars_fail_instead_of_choosing(self):
        bar = {"t": STAMP, "o": 2, "h": 3, "l": 1, "c": 2, "v": 100, "_ordinal": 1}
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            data._bars([bar, dict(bar, c=2.1)], data.timestamp_ns(STAMP), data.timestamp_ns(STAMP) + 60 * 10**9, [], {})


if __name__ == "__main__":
    unittest.main()
