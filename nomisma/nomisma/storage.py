"""Small, transaction-based local persistence for Nomisma."""

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class Store:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "nomisma.sqlite3"
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS scans (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS scans_created_at ON scans(created_at);
                CREATE TABLE IF NOT EXISTS scan_summaries (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, source TEXT,
                    as_of TEXT, matched_count INTEGER
                );
                CREATE INDEX IF NOT EXISTS summaries_created_at ON scan_summaries(created_at);
                CREATE TABLE IF NOT EXISTS watchlist (symbol TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS presets (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, filters TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS monitor_alerts (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
                    acknowledged INTEGER NOT NULL DEFAULT 0, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS monitor_alerts_created ON monitor_alerts(created_at);
            """)
            # Backfill older local databases one record at a time, never load
            # hundreds of full chart payloads to render a short history list.
            rows = db.execute("SELECT id, created_at, payload FROM scans WHERE id NOT IN (SELECT id FROM scan_summaries)")
            for row in rows:
                scan = json.loads(row["payload"])
                db.execute("INSERT INTO scan_summaries VALUES(?,?,?,?,?)", (
                    row["id"], row["created_at"], scan.get("source"), scan.get("as_of"), scan.get("matched_count")))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(str(self.path), timeout=20)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, key, default=None):
        with self.connect() as db:
            row = db.execute("SELECT value FROM state WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def set(self, key, value):
        payload = json.dumps(value, allow_nan=False)
        with self.connect() as db:
            db.execute("INSERT INTO state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, payload))

    def save_scan(self, result):
        scan = dict(result, id=uuid.uuid4().hex, created_at=datetime.now(timezone.utc).isoformat())
        with self.connect() as db:
            db.execute("INSERT INTO scans VALUES(?,?,?)", (scan["id"], scan["created_at"], json.dumps(scan, allow_nan=False)))
            db.execute("INSERT INTO scan_summaries VALUES(?,?,?,?,?)", (
                scan["id"], scan["created_at"], scan.get("source"), scan.get("as_of"), scan.get("matched_count")))
        return scan

    def latest_id(self):
        with self.connect() as db:
            row = db.execute("SELECT id FROM scans ORDER BY created_at DESC LIMIT 1").fetchone()
        return row["id"] if row else None

    def scan(self, identifier=None):
        with self.connect() as db:
            if identifier is None:
                row = db.execute("SELECT payload FROM scans ORDER BY created_at DESC LIMIT 1").fetchone()
            else:
                row = db.execute("SELECT payload FROM scans WHERE id=?", (identifier,)).fetchone()
        return json.loads(row["payload"]) if row else None

    def history(self):
        with self.connect() as db:
            rows = db.execute("SELECT id,created_at,source,as_of,matched_count FROM scan_summaries ORDER BY created_at DESC LIMIT 100").fetchall()
        return [dict(row) for row in rows]

    def watchlist(self):
        with self.connect() as db:
            return [row["symbol"] for row in db.execute("SELECT symbol FROM watchlist ORDER BY symbol")]

    def set_watch(self, symbol, enabled):
        with self.connect() as db:
            if enabled:
                db.execute("INSERT OR IGNORE INTO watchlist VALUES(?)", (symbol,))
            else:
                db.execute("DELETE FROM watchlist WHERE symbol=?", (symbol,))
        return self.watchlist()

    def presets(self):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM presets ORDER BY rowid").fetchall()
        return [{"id": row["id"], "name": row["name"], "description": "Your saved filter preset", "filters": json.loads(row["filters"])} for row in rows]

    def save_preset(self, name, filters):
        with self.connect() as db:
            count = db.execute("SELECT count(*) FROM presets").fetchone()[0]
            if count >= 100:
                raise ValueError("You can save up to 100 custom presets.")
            db.execute("INSERT INTO presets VALUES(?,?,?)", ("custom-" + uuid.uuid4().hex, name, json.dumps(filters, allow_nan=False)))

    def save_monitor_alert(self, alert, tracker):
        # The inbox item and its duplicate-suppression marker commit together.
        with self.connect() as db:
            db.execute("INSERT INTO monitor_alerts VALUES(?,?,?,?)", (
                alert["id"], alert["created_at"], int(alert.get("acknowledged", False)), json.dumps(alert, allow_nan=False)))
            db.execute("INSERT INTO state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (
                "monitor_alert_tracker", json.dumps(tracker, allow_nan=False)))

    def monitor_alerts(self):
        with self.connect() as db:
            rows = db.execute("SELECT payload,acknowledged FROM monitor_alerts ORDER BY created_at DESC LIMIT 100").fetchall()
        return [dict(json.loads(row["payload"]), acknowledged=bool(row["acknowledged"])) for row in rows]

    def acknowledge_monitor_alerts(self, identifier=None, all_alerts=False):
        with self.connect() as db:
            if all_alerts:
                db.execute("UPDATE monitor_alerts SET acknowledged=1 WHERE acknowledged=0")
            else:
                updated = db.execute("UPDATE monitor_alerts SET acknowledged=1 WHERE id=?", (identifier,))
                if updated.rowcount == 0:
                    raise ValueError("Alert not found.")
        return self.monitor_alerts()
