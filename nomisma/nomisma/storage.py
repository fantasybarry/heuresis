"""Small, transaction-based local persistence for Nomisma."""

import json
import math
import os
import sqlite3
import tempfile
import uuid
from contextlib import closing, contextmanager
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
                CREATE TABLE IF NOT EXISTS monitor_alert_index (
                    id TEXT PRIMARY KEY, source TEXT, feed TEXT, session_date TEXT, symbol TEXT
                );
                CREATE INDEX IF NOT EXISTS monitor_alert_session ON monitor_alert_index(source,feed,session_date);
            """)
            # Backfill older local databases one record at a time, never load
            # hundreds of full chart payloads to render a short history list.
            rows = db.execute("SELECT id, created_at, payload FROM scans WHERE id NOT IN (SELECT id FROM scan_summaries)")
            for row in rows:
                scan = json.loads(row["payload"])
                db.execute("INSERT INTO scan_summaries VALUES(?,?,?,?,?)", (
                    row["id"], row["created_at"], scan.get("source"), scan.get("as_of"), scan.get("matched_count")))
            for row in db.execute("SELECT id,payload FROM monitor_alerts WHERE id NOT IN (SELECT id FROM monitor_alert_index)"):
                alert = json.loads(row["payload"])
                db.execute("INSERT INTO monitor_alert_index VALUES(?,?,?,?,?)", (
                    row["id"], alert.get("source"), alert.get("feed"), alert.get("session_date"), alert.get("symbol")))

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

    @staticmethod
    def _page(limit, offset):
        if type(limit) is not int or not 1 <= limit <= 500 or type(offset) is not int or offset < 0:
            raise ValueError("Use a limit from 1 to 500 and a nonnegative offset.")
        return limit, offset

    def history(self, limit=100, offset=0):
        limit, offset = self._page(limit, offset)
        with self.connect() as db:
            rows = db.execute("SELECT id,created_at,source,as_of,matched_count FROM scan_summaries ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
        return [dict(row) for row in rows]

    def history_total(self):
        with self.connect() as db:
            return db.execute("SELECT count(*) FROM scan_summaries").fetchone()[0]

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
            db.execute("INSERT INTO monitor_alert_index VALUES(?,?,?,?,?)", (
                alert["id"], alert.get("source"), alert.get("feed"), alert.get("session_date"), alert.get("symbol")))
            db.execute("INSERT INTO state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (
                "monitor_alert_tracker", json.dumps(tracker, allow_nan=False)))

    def monitor_alerts(self, limit=100, offset=0, include_evidence=False):
        limit, offset = self._page(limit, offset)
        with self.connect() as db:
            rows = db.execute("SELECT payload,acknowledged FROM monitor_alerts ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
        result = [dict(json.loads(row["payload"]), acknowledged=bool(row["acknowledged"])) for row in rows]
        if not include_evidence:
            for alert in result:
                for field in ("snapshot", "config", "session"):
                    alert.pop(field, None)
        return result

    def monitor_alerts_total(self):
        with self.connect() as db:
            return db.execute("SELECT count(*) FROM monitor_alerts").fetchone()[0]

    def monitor_alert(self, identifier):
        with self.connect() as db:
            row = db.execute("SELECT payload,acknowledged FROM monitor_alerts WHERE id=?", (identifier,)).fetchone()
        return dict(json.loads(row["payload"]), acknowledged=bool(row["acknowledged"])) if row else None

    def monitor_session_alerts(self, source, feed, session_date):
        with self.connect() as db:
            rows = db.execute("""SELECT alerts.payload FROM monitor_alerts AS alerts
                JOIN monitor_alert_index AS metadata ON metadata.id=alerts.id
                WHERE metadata.source=? AND metadata.feed=? AND metadata.session_date=?""",
                              (source, feed, session_date)).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def update_monitor_outcomes(self, identifier, outcomes):
        # Evidence is deliberately not accepted here: subsequent observations
        # can change, but the configuration and original setup cannot.
        with self.connect() as db:
            row = db.execute("SELECT payload FROM monitor_alerts WHERE id=?", (identifier,)).fetchone()
            if row is None:
                return
            alert = json.loads(row["payload"])
            alert["outcomes"] = outcomes
            db.execute("UPDATE monitor_alerts SET payload=? WHERE id=?", (json.dumps(alert, allow_nan=False), identifier))

    def backup(self, path=None):
        """A transactionally consistent SQLite snapshot, even during a scan."""
        if path is not None and Path(path).resolve() == self.path:
            raise ValueError("The backup must use a different file from the active database.")
        with tempfile.TemporaryDirectory(dir=self.directory) as temporary:
            target = Path(temporary) / "backup.sqlite3"
            with self.connect() as source, closing(sqlite3.connect(str(target))) as destination:
                source.backup(destination)
            content = target.read_bytes()
            if path is not None:
                destination = Path(path)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with os.fdopen(os.open(str(destination), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as handle:
                    handle.write(content)
                return str(destination.resolve())
            return content

    @staticmethod
    def _validate_backup(db):
        """Read only known table data; never execute schema from an upload."""
        from .engine import screen, validate_filters
        from .monitor_metrics import validate_monitor_config
        from .server import validate_settings

        expected = {
            "state": ["key", "value"], "scans": ["id", "created_at", "payload"],
            "scan_summaries": ["id", "created_at", "source", "as_of", "matched_count"],
            "watchlist": ["symbol"], "presets": ["id", "name", "filters"],
            "monitor_alerts": ["id", "created_at", "acknowledged", "payload"],
            "monitor_alert_index": ["id", "source", "feed", "session_date", "symbol"],
        }
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("The backup failed SQLite integrity validation.")
        schema = db.execute("SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
        if any(row["type"] in ("trigger", "view") for row in schema):
            raise ValueError("Backups with triggers or views are not supported.")
        tables = {row["name"] for row in schema if row["type"] == "table"}
        if tables not in (set(expected), set(expected) - {"monitor_alert_index"}):
            raise ValueError("This file does not have the Nomisma database schema.")
        for table, columns in expected.items():
            if table not in tables:
                continue
            found = [row["name"] for row in db.execute("PRAGMA table_info(%s)" % table)]
            if found != columns:
                raise ValueError("Unexpected backup schema for %s." % table)

        def decode(value):
            def invalid(value):
                raise ValueError("Non-finite numbers are not valid backup data.")
            def finite(value):
                parsed = float(value)
                return parsed if math.isfinite(parsed) else invalid(value)
            return json.loads(value, parse_constant=invalid, parse_float=finite)

        def stamp(value):
            if not isinstance(value, str):
                raise ValueError("Backup timestamps must be strings.")
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError("Backup timestamps need a time zone.")

        for row in db.execute("SELECT key,value FROM state"):
            value = decode(row["value"])
            if row["key"] == "settings":
                validate_settings(value)
            elif row["key"] == "monitor_config":
                validate_monitor_config(value)
            elif row["key"] == "csv_dataset":
                if not isinstance(value, dict) or value.get("source") != "csv":
                    raise ValueError("Invalid imported CSV dataset.")
                screen(value, {})
            elif row["key"] in ("monitor_alert_tracker", "monitor_float_overrides"):
                if not isinstance(value, dict) or any(not isinstance(item, dict) for item in value.values()):
                    raise ValueError("Invalid saved monitor state.")
                if row["key"] == "monitor_alert_tracker":
                    for item in value.values():
                        for field in ("bar", "last_alert_market_time"):
                            if item.get(field) is not None:
                                stamp(item[field])
                        for field in ("buy_streak", "strong_streak", "candidate_rank", "last_alert_rank"):
                            if field in item and (type(item[field]) is not int or item[field] < 0):
                                raise ValueError("Invalid alert confirmation state.")
                        if "armed" in item and type(item["armed"]) is not bool:
                            raise ValueError("Invalid alert rearming state.")
                else:
                    for symbol, item in value.items():
                        validate_monitor_config({"symbols": [symbol]})
                        shares = item.get("shares")
                        if type(shares) not in (int, float) or not 1 <= shares <= 1e13 or int(shares) != shares or item.get("source") != "Manual":
                            raise ValueError("Invalid saved float override.")
                        datetime.strptime(item.get("as_of", ""), "%Y-%m-%d")
            elif row["key"] == "schedule_last_success" and value is not None:
                datetime.strptime(value, "%Y-%m-%d")
            elif row["key"] == "schedule_retry_after" and value is not None:
                stamp(value)
        for row in db.execute("SELECT * FROM scans"):
            scan = decode(row["payload"])
            stamp(row["created_at"])
            if not isinstance(scan, dict) or scan.get("id") != row["id"] or scan.get("created_at") != row["created_at"] or not isinstance(scan.get("results"), list):
                raise ValueError("Invalid saved scan.")
            if not isinstance(scan.get("matched_count"), int) or scan["matched_count"] < 0 or scan.get("source") not in ("demo", "alpaca", "csv"):
                raise ValueError("Invalid saved scan summary.")
            validate_filters(scan.get("filters"))
            for result in scan["results"]:
                if not isinstance(result, dict) or not isinstance(result.get("symbol"), str):
                    raise ValueError("Invalid saved scan result.")
                if not isinstance(result.get("metrics"), dict) or not isinstance(result.get("chart"), list):
                    raise ValueError("Invalid saved scan indicators or chart.")
                for point in result["chart"]:
                    if not isinstance(point, dict) or type(point.get("close")) not in (int, float) or point["close"] <= 0:
                        raise ValueError("Invalid saved scan chart price.")
                    datetime.strptime(point.get("date", ""), "%Y-%m-%d")
                for field in ("signals", "risks"):
                    if not isinstance(result.get(field), list):
                        raise ValueError("Invalid saved scan explanation.")
        for row in db.execute("SELECT * FROM presets"):
            if not isinstance(row["name"], str) or not row["name"].strip():
                raise ValueError("Invalid preset name.")
            validate_filters(decode(row["filters"]))
        for row in db.execute("SELECT symbol FROM watchlist"):
            validate_settings({"symbols": [row["symbol"]]})
        for row in db.execute("SELECT * FROM monitor_alerts"):
            alert = decode(row["payload"])
            stamp(row["created_at"])
            if not isinstance(alert, dict) or alert.get("id") != row["id"] or alert.get("created_at") != row["created_at"] or row["acknowledged"] not in (0, 1):
                raise ValueError("Invalid saved alert.")
            validate_monitor_config({"symbols": [alert.get("symbol")]})
            stamp(alert.get("market_time"))
            if alert.get("level") not in ("Buy", "Strong buy") or alert.get("source") not in ("demo", "alpaca"):
                raise ValueError("Invalid saved alert setup.")
            if "config" in alert:
                validate_monitor_config(alert["config"])
            if "session" in alert:
                if not isinstance(alert["session"], dict):
                    raise ValueError("Invalid saved alert session.")
                for field in ("open", "close"):
                    if field in alert["session"]:
                        stamp(alert["session"][field])
            if alert.get("reference_at") is not None:
                stamp(alert["reference_at"])
            if alert.get("reference_price") is not None and (type(alert["reference_price"]) not in (int, float) or alert["reference_price"] <= 0):
                raise ValueError("Invalid saved alert reference price.")
            if "snapshot" in alert and not isinstance(alert["snapshot"], dict):
                raise ValueError("Invalid saved alert evidence.")
            if isinstance(alert.get("snapshot"), dict):
                snapshot = alert["snapshot"]
                for field in ("chart", "signals", "blockers", "warnings", "reasons", "volume_history"):
                    if field in snapshot and not isinstance(snapshot[field], list):
                        raise ValueError("Invalid saved alert %s." % field)
                for field in ("blockers", "warnings", "reasons"):
                    if any(not isinstance(item, str) for item in snapshot.get(field, [])):
                        raise ValueError("Invalid saved alert explanation.")
                if any(not isinstance(item, dict) for item in snapshot.get("signals", [])):
                    raise ValueError("Invalid saved alert signals.")
                for point in snapshot.get("chart", []):
                    if not isinstance(point, dict) or type(point.get("close")) not in (int, float) or point["close"] <= 0:
                        raise ValueError("Invalid saved alert chart.")
                    stamp(point.get("t"))
            if "outcomes" in alert:
                if not isinstance(alert["outcomes"], dict) or set(alert["outcomes"]) - {"5", "15", "30"}:
                    raise ValueError("Invalid saved alert outcomes.")
                for item in alert["outcomes"].values():
                    if not isinstance(item, dict) or item.get("status") not in ("pending", "unavailable", "observed"):
                        raise ValueError("Invalid saved alert observation.")
                    for field in ("close_change_pct", "adverse_excursion_pct", "end_close"):
                        if item.get(field) is not None and type(item[field]) not in (int, float):
                            raise ValueError("Invalid saved observation price.")
                    for field in ("target_at", "observed_at"):
                        if item.get(field) is not None:
                            stamp(item[field])
        return expected

    def restore_backup(self, content):
        """Validate fully, retain a safety copy, then atomically restore rows.

        The caller must stop workers and serialize mutations before calling.
        Uploaded SQL is never installed; rows are copied into our own schema.
        """
        if not isinstance(content, bytes) or not content.startswith(b"SQLite format 3\x00") or len(content) > 128 * 1024 * 1024:
            raise ValueError("Choose a Nomisma SQLite backup no larger than 128 MB.")
        with tempfile.TemporaryDirectory(dir=self.directory) as temporary:
            uploaded = Path(temporary) / "upload.sqlite3"
            with os.fdopen(os.open(str(uploaded), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as handle:
                handle.write(content)
            try:
                with closing(sqlite3.connect(uploaded.as_uri() + "?mode=ro", uri=True)) as source:
                    source.row_factory = sqlite3.Row
                    source.execute("PRAGMA trusted_schema=OFF")
                    tables = self._validate_backup(source)
                    safety = self.directory / "backups" / ("before-restore-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8] + ".sqlite3")
                    self.backup(safety)
                    with self.connect() as target:
                        for table, columns in tables.items():
                            target.execute("DELETE FROM %s" % table)
                            if table in ("scan_summaries", "monitor_alert_index"):
                                continue
                            placeholders = ",".join("?" for _ in columns)
                            target.executemany("INSERT INTO %s VALUES(%s)" % (table, placeholders),
                                               (tuple(row) for row in source.execute("SELECT * FROM %s" % table)))
                        for row in target.execute("SELECT id,created_at,payload FROM scans"):
                            scan = json.loads(row["payload"])
                            target.execute("INSERT INTO scan_summaries VALUES(?,?,?,?,?)", (
                                row["id"], row["created_at"], scan.get("source"), scan.get("as_of"), scan.get("matched_count")))
                        for row in target.execute("SELECT id,payload FROM monitor_alerts"):
                            alert = json.loads(row["payload"])
                            target.execute("INSERT INTO monitor_alert_index VALUES(?,?,?,?,?)", (
                                row["id"], alert.get("source"), alert.get("feed"), alert.get("session_date"), alert.get("symbol")))
            except (sqlite3.Error, TypeError, KeyError, OverflowError, RecursionError, json.JSONDecodeError) as exc:
                raise ValueError("The file is not a valid Nomisma backup.") from exc
        return {"backup_path": str(safety)}

    def acknowledge_monitor_alerts(self, identifier=None, all_alerts=False):
        with self.connect() as db:
            if all_alerts:
                db.execute("UPDATE monitor_alerts SET acknowledged=1 WHERE acknowledged=0")
            else:
                updated = db.execute("UPDATE monitor_alerts SET acknowledged=1 WHERE id=?", (identifier,))
                if updated.rowcount == 0:
                    raise ValueError("Alert not found.")
        return self.monitor_alerts()
