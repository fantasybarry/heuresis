"""Settlement follows archived provider dates, with no trading-day extrapolation."""

from dataclasses import FrozenInstanceError
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from nomisma import cash_calendar as data


def row(day, settlement, close="16:00"):
    return {"date": day, "open": "09:30", "close": close, "session_open": "04:00",
            "session_close": "20:00", "settlement_date": settlement}


# Explicit rows observed in the real archived calendar, independently of replay
# outcomes. Tests use synthetic archive bytes rather than depend on local data.
SEPTEMBER = [row("2026-09-03", "2026-09-04"), row("2026-09-04", "2026-09-08"),
             row("2026-09-08", "2026-09-09"), row("2026-09-09", "2026-09-10"),
             row("2026-09-10", "2026-09-11"), row("2026-09-11", "2026-09-14"),
             row("2026-09-14", "2026-09-15"), row("2026-09-15", "2026-09-16"),
             row("2026-09-16", "2026-09-17")]


def archive(directory, rows=SEPTEMBER):
    source = directory / "source"
    (source / "raw").mkdir(parents=True)
    body = data._canonical(rows)
    compressed = gzip.compress(body, mtime=0)
    raw_path = source / "raw/calendar.json.gz"
    raw_path.write_bytes(compressed)
    received = "2026-09-18T18:08:59.316955+00:00"
    manifest = {
        "kind": "current_research_metadata", "status": "complete",
        "items": {"calendar": {"page_path": "raw/calendar.json.gz", "received_at": received, "records": len(rows)}},
        "pages": [{"path": "raw/calendar.json.gz", "url": "https://api.alpaca.markets/v2/calendar",
                   "params": {"start": rows[0]["date"], "end": rows[-1]["date"]},
                   "retrieved_at": received, "sha256": data._sha(compressed),
                   "body_sha256": data._sha(body), "response_bytes": len(body)}],
    }
    manifest_path = source / "manifest.json"
    manifest_path.write_bytes(data._canonical(manifest))
    return manifest_path, data._sha(compressed)


def calendar(directory, rows=SEPTEMBER):
    source, pinned = archive(directory, rows)
    return data.create_calendar(source, directory / "calendar.json", [r["date"] for r in rows],
                                expected_raw_sha256=pinned)


class CashCalendarTests(unittest.TestCase):
    def test_weekday_weekend_labor_day_and_final_session_maturity(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = calendar(Path(temporary).resolve())
            cal = data.load_calendar(path)
            self.assertEqual(cal.settlement_date("2026-09-03"), "2026-09-04")
            self.assertEqual(cal.settlement_date("2026-09-04"), "2026-09-08")
            self.assertEqual(cal.settlement_date("2026-09-11"), "2026-09-14")
            self.assertEqual(cal.settlement_date("2026-09-16"), "2026-09-17")
            self.assertEqual(cal.release_at("2026-09-16"), "2026-09-17T13:30:00Z")
            self.assertEqual(cal.last_settlement_date, "2026-09-17")
            self.assertEqual(cal.file_sha256, data._sha(path.read_bytes()))
            self.assertEqual(cal.validate_dates(["2026-09-03", "2026-09-16"]), ("2026-09-03", "2026-09-16"))

    def test_trading_open_columbus_day_is_not_settlement_day(self):
        rows = [row("2026-10-09", "2026-10-13"), row("2026-10-12", "2026-10-13")]
        with tempfile.TemporaryDirectory() as temporary:
            cal = data.load_calendar(calendar(Path(temporary).resolve(), rows))
            self.assertEqual(cal.settlement_date("2026-10-09"), "2026-10-13")
            self.assertNotEqual(cal.settlement_date("2026-10-09"), cal.trade_dates[1])
            self.assertEqual(cal.settlement_date("2026-10-12"), "2026-10-13")

    def test_synthetic_early_close_does_not_change_settlement_or_winter_offset(self):
        # This synthetic early-close fixture is not claimed present in the archive.
        rows = [row("2026-11-27", "2026-11-30", close="13:00")]
        with tempfile.TemporaryDirectory() as temporary:
            cal = data.load_calendar(calendar(Path(temporary).resolve(), rows))
            self.assertEqual(cal.release_at("2026-11-27"), "2026-11-30T14:30:00Z")

    def test_runtime_fail_closed_for_nontrading_and_outside_bounds(self):
        with tempfile.TemporaryDirectory() as temporary:
            cal = data.load_calendar(calendar(Path(temporary).resolve()))
            for day in ("2026-09-02", "2026-09-05", "2026-09-07", "2026-09-17", "2026-10-09"):
                with self.subTest(day=day), self.assertRaisesRegex(ValueError, "outside registered"):
                    cal.release_at(day)
            for dates in ([], ["2026-09-04", "2026-09-03"], ["2026-09-03", "2026-09-03"]):
                with self.assertRaises(ValueError):
                    cal.validate_dates(dates)
            for day in ("20260903", "2026-09-03T13:30:00Z", None):
                with self.assertRaises(ValueError):
                    cal.settlement_date(day)

    def test_object_and_file_are_immutable(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            path = calendar(directory)
            cal = data.load_calendar(path)
            with self.assertRaises(FrozenInstanceError):
                cal.last_settlement_date = "2026-09-18"
            with self.assertRaises(TypeError):
                cal._settlements["2026-09-03"] = "2026-09-05"
            original = path.read_bytes()
            manifest = json.loads(original)
            with self.assertRaises(FileExistsError):
                data.create_calendar(directory / "source/manifest.json", path, list(cal.trade_dates),
                                     expected_raw_sha256=manifest["source"]["raw_page_sha256"])
            self.assertEqual(path.read_bytes(), original)

    def test_pinned_raw_and_manifest_integrity(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            source, pinned = archive(directory)
            with self.assertRaisesRegex(ValueError, "pinned hash"):
                data.create_calendar(source, directory / "wrong.json", [r["date"] for r in SEPTEMBER],
                                     expected_raw_sha256="0" * 64)
            self.assertFalse((directory / "wrong.json").exists())
            path = data.create_calendar(source, directory / "calendar.json", [r["date"] for r in SEPTEMBER],
                                        expected_raw_sha256=pinned)
            raw_path = directory / "source/raw/calendar.json.gz"
            original = raw_path.read_bytes()
            raw_path.write_bytes(b"corrupted raw payload")
            with self.assertRaisesRegex(ValueError, "raw page hash mismatch"):
                data.load_calendar(path)
            raw_path.write_bytes(original)
            source.write_bytes(source.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "Source manifest hash mismatch"):
                data.load_calendar(path)

    def test_derived_tampering_fails_even_after_rehashing_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = calendar(Path(temporary).resolve())
            original = json.loads(path.read_bytes())
            mutations = [lambda value: value["rows"][1].update(settlement_date="2026-09-07"),
                         lambda value: value["coverage"].update(last_settlement_date="2026-09-18"),
                         lambda value: value["release_policy"].update(local_time="00:00:00"),
                         lambda value: value["source"].pop("raw_page_sha256")]
            for mutate in mutations:
                changed = json.loads(data._canonical(original))
                mutate(changed)
                changed["calendar_sha256"] = data._digest(changed)
                path.write_bytes(data._canonical(changed))
                with self.assertRaises(ValueError):
                    data.load_calendar(path)

    def test_incomplete_coverage_and_invalid_source_dates_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            source, pinned = archive(directory)
            for days in (["2026-09-03", "2026-09-16"], ["2026-09-03", "2026-09-07"]):
                with self.assertRaisesRegex(ValueError, "every provider|missing from"):
                    data.create_calendar(source, directory / "bad.json", days, expected_raw_sha256=pinned)
            for rows in ([row("2026-09-03", "2026-09-03")], [row("2026-09-04", "2026-09-05")],
                         [row("2026-09-03", "2026-09-04"), row("2026-09-03", "2026-09-04")]):
                with self.assertRaises(ValueError):
                    data._provider_rows(rows, {"start": "2026-09-03", "end": "2026-09-04"})

    def test_source_raw_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            path = calendar(directory)
            raw = directory / "source/raw/calendar.json.gz"
            outside = directory / "elsewhere.gz"
            raw.rename(outside)
            raw.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "symbolic links"):
                data.load_calendar(path)


if __name__ == "__main__":
    unittest.main()
