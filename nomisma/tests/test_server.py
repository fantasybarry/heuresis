import copy
from contextlib import closing
import http.client
import json
import sqlite3
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from nomisma.server import Application, BusyError, csv_export, default_settings, make_handler, validate_settings
from nomisma.storage import Store


class SettingsTests(unittest.TestCase):
    def test_default_is_valid(self):
        self.assertEqual(validate_settings(default_settings()), default_settings())

    def test_partial_updates_preserve_existing_settings(self):
        current = default_settings()
        current["source"] = "csv"
        self.assertEqual(validate_settings({"universe": "all"}, current)["source"], "csv")

    def test_invalid_settings(self):
        for payload in [{"source": "random"}, {"universe": "custom"}, {"symbols": ["AAPL; rm"]},
                        {"schedule": {"enabled": "false"}}, {"schedule": {"time": "25:00"}},
                        {"schedule": {"timezone": "UTC"}}, {"surprise": True}, {"filters": {"min_score": float("nan")}}]:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                validate_settings(payload)

    def test_tickers_normalized(self):
        self.assertEqual(validate_settings({"symbols": [" aapl", "AAPL", "brk.b"]})["symbols"], ["AAPL", "BRK.B"])


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = Application(self.temp.name, seed=False)

    def test_state_survives_restart(self):
        self.app.save_settings({"filters": dict(default_settings()["filters"], min_score=71)})
        self.app.store.set_watch("AAPL", True)
        self.app.store.save_preset("Custom", default_settings()["filters"])
        another = Application(self.temp.name, seed=False)
        self.assertEqual(another.settings()["filters"]["min_score"], 71)
        self.assertEqual(another.store.watchlist(), ["AAPL"])
        self.assertEqual(another.store.presets()[0]["name"], "Custom")

    def test_disabled_schedule_does_not_run(self):
        self.assertIsNone(self.app.schedule_due(datetime(2026, 9, 8, 22, tzinfo=timezone.utc)))

    def test_schedule_time_timezone_weekends_and_deduplication(self):
        self.app.save_settings({"schedule": {"enabled": True, "time": "17:00"}})
        self.assertIsNone(self.app.schedule_due(datetime(2026, 9, 8, 20, 59, tzinfo=timezone.utc)))
        due = self.app.schedule_due(datetime(2026, 9, 8, 21, tzinfo=timezone.utc))
        self.assertEqual(due, "2026-09-08")
        self.app.store.set("schedule_last_success", due)
        self.assertIsNone(self.app.schedule_due(datetime(2026, 9, 8, 22, tzinfo=timezone.utc)))
        self.assertIsNone(self.app.schedule_due(datetime(2026, 9, 12, 22, tzinfo=timezone.utc)))
        # Winter EST: 17:00 is 22:00 UTC, not 21:00.
        self.assertIsNone(self.app.schedule_due(datetime(2026, 12, 8, 21, 30, tzinfo=timezone.utc)))
        self.assertEqual(self.app.schedule_due(datetime(2026, 12, 8, 22, tzinfo=timezone.utc)), "2026-12-08")

    def test_schedule_retry_backoff(self):
        self.app.save_settings({"schedule": {"enabled": True}})
        self.app.store.set("schedule_retry_after", "2026-09-08T22:15:00+00:00")
        self.assertIsNone(self.app.schedule_due(datetime(2026, 9, 8, 22, 10, tzinfo=timezone.utc)))
        self.assertEqual(self.app.schedule_due(datetime(2026, 9, 8, 22, 16, tzinfo=timezone.utc)), "2026-09-08")

    def test_failed_scan_does_not_create_or_replace_results(self):
        self.app.store.save_scan({"source": "csv", "as_of": "2026-09-04", "matched_count": 0, "results": []})
        original = self.app.store.scan()["id"]
        with patch.object(self.app, "run_scan", side_effect=RuntimeError("Data provider unavailable")):
            self.app._worker(default_settings(), "2026-09-08")
        self.assertEqual(self.app.store.scan()["id"], original)
        self.assertIn("unavailable", self.app.job["error"])
        self.assertIsNone(self.app.store.get("schedule_last_success"))
        self.assertIsNotNone(self.app.store.get("schedule_retry_after"))

    @patch("nomisma.server.provider_status", return_value={"alpaca_configured": False, "feed": "iex"})
    def test_live_requires_credentials_without_demo_fallback(self, _status):
        with patch("nomisma.server.demo_dataset") as demo, self.assertRaisesRegex(ValueError, "not connected"):
            self.app.start_scan({"source": "alpaca"})
        demo.assert_not_called()
        self.assertFalse(self.app.job["running"])

    def test_only_one_scan_at_a_time(self):
        self.app.job["running"] = True
        with self.assertRaises(BusyError):
            self.app.start_scan({})

    def test_database_failure_cannot_leave_scan_permanently_running(self):
        self.app.job["running"] = True
        with patch.object(self.app, "run_scan", side_effect=OSError("disk full")), \
                patch.object(self.app.store, "set", side_effect=OSError("disk full")):
            self.app._worker(default_settings(), "2026-09-08")
        self.assertFalse(self.app.job["running"])
        self.assertIsNotNone(self.app.job["error"])

    def test_empty_csv_source_rejected(self):
        with self.assertRaisesRegex(ValueError, "Import"):
            self.app.start_scan({"source": "csv"})

    def test_watchlist_idempotent(self):
        self.app.store.set_watch("MSFT", True)
        self.app.store.set_watch("MSFT", True)
        self.assertEqual(self.app.store.watchlist(), ["MSFT"])
        self.assertEqual(self.app.store.set_watch("MSFT", False), [])

    def test_history_and_unchanged_poll_do_not_deserialize_scan_payloads(self):
        scan = self.app.store.save_scan({"source": "csv", "as_of": "2026-09-04", "matched_count": 2, "results": []})
        with patch("nomisma.storage.json.loads", side_effect=AssertionError("Full scan should not be parsed")):
            self.assertEqual(self.app.store.history()[0]["matched_count"], 2)
            status = self.app.status(since=scan["id"])
        self.assertIsNone(status["latest"])
        self.assertEqual(status["history"][0]["id"], scan["id"])

    def test_custom_universe_applies_to_imported_data(self):
        dataset = {"assets": [{"symbol": "AAPL"}, {"symbol": "MSFT"}], "warnings": [], "source": "csv"}
        self.app.store.set("csv_dataset", dataset)
        settings = validate_settings({"source": "csv", "universe": "custom", "symbols": ["AAPL", "XYZ"]})
        with patch("nomisma.server.screen", return_value={"results": []}) as screen_mock:
            self.app.run_scan(settings)
        actual = screen_mock.call_args[0][0]
        self.assertEqual([a["symbol"] for a in actual["assets"]], ["AAPL"])
        self.assertIn("XYZ", actual["warnings"][0])

    def test_csv_export_escapes_formulas_and_records_provenance(self):
        scan = {"source": "demo", "feed": "synthetic", "results": [{"symbol": "AAPL", "name": "=HYPERLINK(\"bad\")", "metrics": {}, "change_pct": -1.5}]}
        content = csv_export(scan).decode("utf-8-sig")
        self.assertIn("'=HYPERLINK", content)
        self.assertIn("demo,synthetic", content)
        self.assertIn("-1.5", content)

    def test_restore_preserves_recovery_copy_and_reloads_stopped_monitor(self):
        self.app.store.set_watch("AAPL", True)
        self.app.monitor.save_config({"symbols": ["SAVED"]})
        backup = self.app.store.backup()
        self.app.store.set_watch("AAPL", False)
        self.app.monitor.save_config({"symbols": ["CURRENT"]})
        old_monitor = self.app.monitor
        result = self.app.restore_workspace(backup)
        self.assertTrue(result["restored"])
        self.assertEqual(self.app.store.watchlist(), ["AAPL"])
        self.assertEqual(self.app.monitor.config["symbols"], ["SAVED"])
        self.assertIsNot(self.app.monitor, old_monitor)
        self.assertFalse(self.app.monitor.status["running"])
        self.assertTrue(old_monitor.stop_event.is_set())
        with closing(sqlite3.connect(result["backup_path"])) as recovery:
            config = json.loads(recovery.execute("SELECT value FROM state WHERE key='monitor_config'").fetchone()[0])
            self.assertEqual(config["symbols"], ["CURRENT"])

    def test_restore_refuses_active_work(self):
        for kind in ("scan", "monitor", "research"):
            with self.subTest(kind=kind):
                self.app.job["running"] = kind == "scan"
                self.app.monitor.status["running"] = kind == "monitor"
                self.app.research_jobs = {"x": {"running": True}} if kind == "research" else {}
                with self.assertRaises(BusyError):
                    self.app.restore_workspace(b"not read while busy")
        self.app.job["running"] = False
        self.app.monitor.status["running"] = False
        self.app.research_jobs = {}

    def test_failed_schedule_remains_busy_until_retry_state_is_saved(self):
        self.app.job["running"] = True
        original_set = self.app.store.set
        def save_retry(key, value):
            if key == "schedule_retry_after":
                self.assertTrue(self.app.job["running"])
                with self.assertRaises(BusyError):
                    self.app.restore_workspace(b"not read while busy")
            return original_set(key, value)
        with patch.object(self.app, "run_scan", side_effect=RuntimeError("Provider unavailable")), \
                patch.object(self.app.store, "set", side_effect=save_retry):
            self.app._worker(default_settings(), "2026-09-09")
        self.assertFalse(self.app.job["running"])

    def test_discovery_job_completes_and_remains_available_for_polling(self):
        complete = threading.Event()
        release = threading.Event()
        def discovery(*args, **kwargs):
            complete.set()
            release.wait(2)
            return {"source": "demo", "rows": []}
        with patch("nomisma.research.discover", side_effect=discovery):
            job = self.app.start_research("discovery", {"source": "demo"})
            self.assertTrue(complete.wait(2))
            with self.assertRaises(BusyError):
                self.app.start_research("diagnostics", {})
            release.set()
            for _ in range(100):
                result = self.app.research_status(job["id"])
                if not result["running"]:
                    break
                time.sleep(.01)
            self.assertFalse(result["running"])
            self.assertEqual(result["result"], {"source": "demo", "rows": []})


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.app = Application(cls.temp.name, seed=False)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.app))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        cls.temp.cleanup()

    def request(self, path, payload=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            request_headers = {"Content-Type": "application/json"}
            request_headers.update(headers or {})
            connection.request("POST" if payload is not None else "GET", path,
                               body=json.dumps(payload) if payload is not None else None, headers=request_headers)
            response = connection.getresponse()
            body = response.read()
            return response.status, json.loads(body), dict(response.getheaders())
        finally:
            connection.close()

    def test_bootstrap(self):
        status, body, headers = self.request("/api/bootstrap")
        self.assertEqual(status, 200)
        self.assertIn("settings", body)
        self.assertIn("Content-Security-Policy", headers)

    def test_health_identifies_the_workspace(self):
        status, body, _ = self.request("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["app"], "nomisma")
        self.assertEqual(body["data_directory"], str(self.app.store.directory))

    def test_paginated_history_and_alerts_validate_offsets(self):
        for route, field in (("/api/history", "history"), ("/api/monitor/alerts", "alerts")):
            status, body, _ = self.request(route + "?limit=2&offset=1")
            self.assertEqual(status, 200)
            self.assertIn(field, body)
            self.assertEqual(body["offset"], 1)
            for query in ("limit=0", "limit=101", "offset=-1", "offset=abc"):
                self.assertEqual(self.request(route + "?" + query)[0], 400)

    def test_research_routes_dispatch_and_poll(self):
        job = {"id": "sample", "kind": "discovery", "running": True, "message": "Searching", "error": None, "result": None}
        with patch.object(self.app, "start_research", return_value=job) as dispatch:
            status, body, _ = self.request("/api/discovery", {"source": "demo"})
            self.assertEqual(status, 202)
            self.assertEqual(body["job"], job)
            dispatch.assert_called_once_with("discovery", {"source": "demo"})
        with patch.object(self.app, "research_status", return_value=job):
            self.assertEqual(self.request("/api/research/jobs/sample")[1]["job"], job)
        self.assertEqual(self.request("/api/research/jobs/missing")[0], 404)
        self.assertEqual(self.request("/api/monitor/alerts/missing")[0], 404)

    def test_backup_download_and_restore_require_local_origin(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request("GET", "/api/workspace/backup")
            response = connection.getresponse()
            backup = response.read()
            self.assertEqual(response.status, 200)
            self.assertTrue(backup.startswith(b"SQLite format 3"))
            self.assertIn("attachment", response.getheader("Content-Disposition"))
            connection.request("POST", "/api/workspace/restore", backup,
                               {"Content-Type": "application/octet-stream", "Origin": "https://example.com"})
            response = connection.getresponse()
            response.read()
            self.assertEqual(response.status, 403)
        finally:
            connection.close()

    def test_invalid_restore_leaves_workspace_unchanged(self):
        self.app.store.set_watch("KEEP", True)
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request("POST", "/api/workspace/restore", b"not sqlite", {"Content-Type": "application/octet-stream"})
            response = connection.getresponse()
            response.read()
            self.assertEqual(response.status, 400)
            self.assertIn("KEEP", self.app.store.watchlist())
        finally:
            self.app.store.set_watch("KEEP", False)
            connection.close()

    def test_unknown_and_private_paths_are_not_exposed(self):
        for path in ("/api/missing", "/.env", "/../storage.py", "/data/nomisma.sqlite3", "/api/scans/missing"):
            self.assertEqual(self.request(path)[0], 404)

    def test_cross_origin_mutation_rejected(self):
        status, _, _ = self.request("/api/watchlist", {"symbol": "AAPL", "enabled": True}, {"Origin": "https://example.com"})
        self.assertEqual(status, 403)

    def test_foreign_host_rejected(self):
        self.assertEqual(self.request("/api/bootstrap", headers={"Host": "evil.example"})[0], 403)

    def test_post_requires_json(self):
        self.assertEqual(self.request("/api/settings", {}, {"Content-Type": "text/plain"})[0], 415)

    def test_watchlist_api_validation(self):
        self.assertEqual(self.request("/api/watchlist", {"symbol": "<script>", "enabled": True})[0], 400)
        self.assertEqual(self.request("/api/watchlist", {"symbol": "NVDA", "enabled": "yes"})[0], 400)
        self.assertEqual(self.request("/api/watchlist", {"symbol": "NVDA", "enabled": True})[1]["watchlist"], ["NVDA"])

    def test_unknown_filter_and_nonfinite_rejected(self):
        self.assertEqual(self.request("/api/settings", {"filters": {"typo": 1}})[0], 400)
        self.assertEqual(self.request("/api/settings", {"filters": {"min_score": float("nan")}})[0], 400)


if __name__ == "__main__":
    unittest.main()
