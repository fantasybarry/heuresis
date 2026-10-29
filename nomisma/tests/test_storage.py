from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from nomisma.engine import screen
from nomisma.providers import demo_dataset
from nomisma.server import Application, default_settings
from nomisma.storage import Store


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)

    def edit_backup(self, content, sql, args=()):
        path = Path(self.temp.name) / "edited.sqlite3"
        path.write_bytes(content)
        with closing(sqlite3.connect(str(path))) as db, db:
            db.execute(sql, args)
        return path.read_bytes()

    def test_pagination_has_totals_and_validates_bounds(self):
        scan = screen(demo_dataset(), {})
        identifiers = [self.store.save_scan(scan)["id"] for _ in range(4)]
        self.assertEqual(self.store.history_total(), 4)
        self.assertEqual([row["id"] for row in self.store.history(limit=2, offset=1)], list(reversed(identifiers))[1:3])
        for kwargs in ({"limit": 0}, {"limit": True}, {"offset": -1}, {"limit": 501}):
            with self.assertRaises(ValueError):
                self.store.history(**kwargs)

    def test_source_scoped_alert_pagination_keeps_default_journal_and_evidence(self):
        for source in ("alpaca", "demo"):
            for number in range(3):
                self.store.save_monitor_alert({"id": "%s-%s" % (source, number),
                    "source": source, "feed": "iex" if source == "alpaca" else "synthetic",
                    "created_at": "2026-09-08T15:0%s:00+00:00" % number,
                    "snapshot": {"price": 2.5}, "config": {"source": source}, "session": {"date": "2026-09-08"}}, {})
        self.assertEqual([row["id"] for row in self.store.monitor_alerts(limit=1, offset=1, source="alpaca")], ["alpaca-1"])
        self.assertEqual({row["source"] for row in self.store.monitor_alerts()}, {"alpaca", "demo"})
        self.assertNotIn("snapshot", self.store.monitor_alerts(source="alpaca")[0])
        self.assertEqual(self.store.monitor_alerts(source="alpaca", include_evidence=True)[0]["snapshot"], {"price": 2.5})
        self.assertEqual(self.store.monitor_alerts_total(), 6)

    def test_source_scoped_acknowledgment_does_not_mark_other_source_or_change_tracker(self):
        for source in ("alpaca", "demo"):
            self.store.save_monitor_alert({"id": source, "source": source,
                "created_at": "2026-09-08T15:00:00+00:00", "snapshot": {"price": 2.5}}, {"saved": {"bar": "unchanged"}})
        response = self.store.acknowledge_monitor_alerts(all_alerts=True, source="alpaca")
        self.assertEqual([row["id"] for row in response], ["alpaca"])
        self.assertTrue(self.store.monitor_alert("alpaca")["acknowledged"])
        self.assertFalse(self.store.monitor_alert("demo")["acknowledged"])
        with self.assertRaisesRegex(ValueError, "not found"):
            self.store.acknowledge_monitor_alerts("demo", source="alpaca")
        self.assertFalse(self.store.monitor_alert("demo")["acknowledged"])
        self.assertEqual(self.store.get("monitor_alert_tracker"), {"saved": {"bar": "unchanged"}})
        self.assertEqual(self.store.monitor_alert("demo")["snapshot"], {"price": 2.5})
        self.store.acknowledge_monitor_alerts(all_alerts=True)
        self.assertTrue(all(row["acknowledged"] for row in self.store.monitor_alerts()))

    def test_invalid_alert_source_is_rejected_before_read_or_acknowledgment(self):
        self.store.save_monitor_alert({"id": "demo", "source": "demo", "created_at": "2026-09-08T15:00:00+00:00"}, {})
        for source in ("csv", "all", "ALPACA", "", [], {}, True):
            with self.subTest(source=source):
                with self.assertRaisesRegex(ValueError, "source"):
                    self.store.monitor_alerts(source=source)
                with self.assertRaisesRegex(ValueError, "source"):
                    self.store.acknowledge_monitor_alerts(all_alerts=True, source=source)
        self.assertFalse(self.store.monitor_alert("demo")["acknowledged"])

    def test_backup_restore_round_trip_keeps_safety_copy_and_rebuilds_summaries(self):
        self.store.set("settings", default_settings())
        self.store.set_watch("AAPL", True)
        saved = self.store.save_scan(screen(demo_dataset(), {}))
        self.store.save_preset("My preset", {})
        content = self.store.backup()
        self.store.set_watch("MSFT", True)
        self.store.set("settings", dict(default_settings(), source="alpaca"))
        result = self.store.restore_backup(content)
        self.assertEqual(self.store.watchlist(), ["AAPL"])
        self.assertEqual(self.store.get("settings")["source"], "demo")
        self.assertEqual(self.store.history()[0]["id"], saved["id"])
        self.assertEqual(self.store.scan(), saved)
        safety = Path(result["backup_path"])
        if os.name != "nt":
            self.assertEqual(os.stat(str(safety)).st_mode & 0o777, 0o600)
        with closing(sqlite3.connect(str(safety))) as db:
            self.assertEqual(db.execute("SELECT symbol FROM watchlist ORDER BY symbol").fetchall(), [("AAPL",), ("MSFT",)])

    def test_rejects_invalid_config_json_schema_and_triggers_without_changing_data(self):
        self.store.set("settings", default_settings())
        content = self.store.backup()
        cases = [
            b"not sqlite",
            self.edit_backup(content, "UPDATE state SET value=? WHERE key='settings'", ('{"source":"bogus"}',)),
            self.edit_backup(content, "UPDATE state SET value=? WHERE key='settings'", ('{"filters":{"min_price":1e999}}',)),
            self.edit_backup(content, "CREATE TRIGGER invalid AFTER INSERT ON watchlist BEGIN DELETE FROM watchlist; END"),
            self.edit_backup(content, "DROP TABLE presets"),
            self.edit_backup(content, "INSERT INTO scans VALUES('bad','2026-09-08T00:00:00+00:00','{}')"),
        ]
        self.store.set_watch("MSFT", True)
        for candidate in cases:
            with self.subTest(candidate=candidate[:20]), self.assertRaises(ValueError):
                self.store.restore_backup(candidate)
            self.assertEqual(self.store.watchlist(), ["MSFT"])
            self.assertEqual(self.store.get("settings"), default_settings())

    def test_legacy_schema_without_alert_index_can_restore(self):
        self.store.set("settings", default_settings())
        content = self.edit_backup(self.store.backup(), "DROP TABLE monitor_alert_index")
        self.store.restore_backup(content)
        self.assertEqual(self.store.get("settings"), default_settings())

    def test_backup_cannot_overwrite_live_database_or_existing_file(self):
        with self.assertRaises(ValueError):
            self.store.backup(self.store.path)
        path = Path(self.temp.name) / "copy.sqlite3"
        self.store.backup(path)
        with self.assertRaises(FileExistsError):
            self.store.backup(path)

    def test_backup_and_restore_close_all_database_handles(self):
        # Windows cannot remove temporary SQLite files with open connections.
        # SQLite's own context manager commits but does not close a connection.
        connections = []
        connect = sqlite3.connect

        def record_connection(*args, **kwargs):
            connection = connect(*args, **kwargs)
            connections.append(connection)
            return connection

        with patch("nomisma.storage.sqlite3.connect", side_effect=record_connection):
            content = self.store.backup()
            self.store.restore_backup(content)
        self.assertTrue(connections)
        for connection in connections:
            with self.assertRaises(sqlite3.ProgrammingError):
                connection.execute("SELECT 1")

    def test_discovery_schedule_result_and_retry_state_restore_and_validate(self):
        from nomisma.research import discover
        app = Application(self.temp.name, seed=False)
        app.save_discovery_settings({"config": {"source": "demo", "min_price": 1},
                                     "schedule": {"enabled": True, "time": "09:15"}})
        with patch("nomisma.server.threading.Thread.start"):
            initial = app.start_research("discovery", {}, scheduled_date="2026-09-08")
        job = app.research_jobs[initial["id"]]
        app._finish_research(job, result=discover(app.discovery_settings()["config"]))
        content = self.store.backup()
        self.store.set("discovery_settings", {})
        self.store.restore_backup(content)
        self.assertEqual(self.store.get("discovery_settings")["schedule"]["time"], "09:15")
        state = self.store.get("discovery_state")
        self.assertEqual(state["latest"]["id"], job["id"])
        self.assertEqual(state["last_success_date"], "2026-09-08")
        self.assertTrue(state["latest"]["result"]["rows"])
        invalid_states = [dict(state, retry_after="tomorrow"), dict(state, last_success_date="bad")]
        bad_result = json.loads(json.dumps(state))
        bad_result["latest"]["result"]["rows"][0]["price"] = -1
        invalid_states.append(bad_result)
        bad_count = json.loads(json.dumps(state))
        bad_count["latest"]["result"]["coverage"]["returned"] = 10000
        invalid_states.append(bad_count)
        for invalid in invalid_states:
            candidate = self.edit_backup(content, "UPDATE state SET value=? WHERE key='discovery_state'", (json.dumps(invalid),))
            with self.subTest(invalid=invalid.get("retry_after")), self.assertRaises(ValueError):
                self.store.restore_backup(candidate)
            self.assertEqual(self.store.get("discovery_state"), state)
        candidate = self.edit_backup(content, "UPDATE state SET value=? WHERE key='discovery_settings'",
                                     (json.dumps({"schedule": {"enabled": "yes"}}),))
        with self.assertRaises(ValueError):
            self.store.restore_backup(candidate)

    def test_discovery_backup_preserves_unavailable_volume_and_screening_metrics(self):
        from nomisma.research import discover
        app = Application(self.temp.name, seed=False)
        with patch("nomisma.server.threading.Thread.start"):
            initial = app.start_research("discovery", {})
        result = discover(app.discovery_settings()["config"])
        row = result["rows"][0]
        row.update(day_volume=None, volume_at=None, day_volume_fresh=False, volume_basis="unavailable",
                   avg_volume_3m=None, avg_daily_volume=100000, beta=-0.4, spread=None, atr=0.5)
        app._finish_research(app.research_jobs[initial["id"]], result=result)
        content = self.store.backup()
        self.store.restore_backup(content)
        state = self.store.get("discovery_state")
        self.assertEqual(state["latest"]["result"]["rows"][0], row)
        for update in ({"volume_basis": "provider_daily"}, {"day_volume_fresh": True},
                       {"avg_daily_volume": -1}, {"spread": "unknown"}):
            bad = json.loads(json.dumps(state))
            bad["latest"]["result"]["rows"][0].update(update)
            candidate = self.edit_backup(content, "UPDATE state SET value=? WHERE key='discovery_state'", (json.dumps(bad),))
            with self.subTest(update=update), self.assertRaises(ValueError):
                self.store.restore_backup(candidate)


if __name__ == "__main__":
    unittest.main()
