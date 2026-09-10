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
from nomisma.server import default_settings
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


if __name__ == "__main__":
    unittest.main()
