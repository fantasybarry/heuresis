"""Loopback web application, scan orchestration, and persistent daily scheduling."""

import csv
import copy
import io
import json
import logging
import mimetypes
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from .engine import DEFAULT_FILTERS, PRESETS, screen, validate_filters
from .providers import demo_dataset, fetch_alpaca, parse_csv, provider_status
from .storage import Store
from .live_data import fetch_candles
from .monitor import LiveMonitor, MonitorBusy, monitor_csv
from .monitor_metrics import MAX_MONITOR_SYMBOLS
from .research import default_discovery, validate_discovery

LOGGER = logging.getLogger("nomisma")
# After the day's first scheduled search, discovery repeats on this interval until the 4 p.m. close.
DISCOVERY_REPEAT = timedelta(minutes=30)
STATIC = Path(__file__).parent / "static"
MAX_BODY = 25 * 1024 * 1024
MAX_BACKUP = 128 * 1024 * 1024
SYMBOL = re.compile(r"^[A-Z][A-Z0-9.\-]{0,14}$")


def default_settings():
    return {
        "filters": dict(DEFAULT_FILTERS), "source": "demo", "universe": "curated", "symbols": [],
        "schedule": {"enabled": False, "time": "17:00", "timezone": "America/New_York"},
    }


def validate_settings(payload, current=None):
    if not isinstance(payload, dict):
        raise ValueError("Settings must be a JSON object.")
    value = dict(current or default_settings())
    unknown = set(payload) - set(default_settings())
    if unknown:
        raise ValueError("Unknown settings: " + ", ".join(sorted(unknown)))
    value.update(payload)
    value["filters"] = validate_filters(value["filters"])
    if value["source"] not in ("demo", "alpaca", "csv"):
        raise ValueError("Choose demo, alpaca, or csv as the data source.")
    if value["universe"] not in ("curated", "all", "custom"):
        raise ValueError("Choose curated, all, or custom as the universe.")
    symbols = value["symbols"]
    if not isinstance(symbols, list) or len(symbols) > 1000:
        raise ValueError("Symbols must be a list of at most 1,000 tickers.")
    if any(not isinstance(s, str) or not SYMBOL.fullmatch(s.strip().upper()) for s in symbols):
        raise ValueError("Use valid ticker symbols, such as AAPL, MSFT, or BRK.B.")
    value["symbols"] = sorted(set(s.strip().upper() for s in symbols))
    if value["universe"] == "custom" and not value["symbols"]:
        raise ValueError("Add at least one symbol for a custom universe.")
    schedule = value["schedule"]
    if not isinstance(schedule, dict) or set(schedule) - {"enabled", "time", "timezone"}:
        raise ValueError("Invalid daily schedule.")
    schedule = dict(default_settings()["schedule"], **schedule)
    if type(schedule["enabled"]) is not bool:
        raise ValueError("Schedule enabled must be true or false.")
    if not isinstance(schedule["time"], str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", schedule["time"]):
        raise ValueError("Schedule time must use HH:MM, for example 17:00.")
    if schedule["timezone"] != "America/New_York":
        raise ValueError("Daily schedules use America/New_York (Eastern time).")
    value["schedule"] = schedule
    return value


def default_discovery_settings():
    return {"config": default_discovery(),
            "schedule": {"enabled": False, "time": "09:15", "timezone": "America/New_York"}}


def validate_discovery_settings(payload, current=None):
    if not isinstance(payload, dict) or set(payload) - {"config", "schedule"}:
        raise ValueError("Supply discovery config and a weekday schedule.")
    result = copy.deepcopy(current or default_discovery_settings())
    if "config" in payload:
        if not isinstance(payload["config"], dict):
            raise ValueError("Discovery config must be a JSON object.")
        result["config"] = validate_discovery(dict(result["config"], **payload["config"]))
    else:
        result["config"] = validate_discovery(result["config"])
    if "schedule" in payload:
        if not isinstance(payload["schedule"], dict):
            raise ValueError("Discovery schedule must be a JSON object.")
        result["schedule"].update(payload["schedule"])
    # Both schedulers use the same Eastern wall-clock validation. Their saved
    # configuration, execution state, and successful dates stay independent.
    result["schedule"] = validate_settings({"schedule": result["schedule"]})["schedule"]
    if result["config"]["source"] == "demo" and result["config"]["universe"] == "all":
        raise ValueError("All-listings discovery requires Alpaca. Choose starter or custom symbols for demo.")
    return result


def default_discovery_state():
    return {"last_run": None, "latest": None, "last_success_date": None, "retry_after": None}


class BusyError(Exception):
    pass


class Application:
    def __init__(self, directory, seed=True):
        self.store = Store(directory)
        self.lock = threading.Lock()
        self.mutation_lock = threading.RLock()
        self.research_jobs = {}
        self.radar_date, self.radar_paused = None, False
        self.stop_event = threading.Event()
        self.job = {"running": False, "message": "Ready to scan", "error": None, "scan_id": None}
        if self.store.get("settings") is None:
            self.store.set("settings", default_settings())
        if self.store.get("discovery_settings") is None:
            self.store.set("discovery_settings", default_discovery_settings())
        self._recover_discovery()
        if seed and self.store.scan() is None:
            self.store.save_scan(screen(demo_dataset(), DEFAULT_FILTERS))
        self.monitor = LiveMonitor(self.store)
        from .planner import Planner
        self.planner = Planner(self.store, self.monitor)

    def settings(self):
        return self.store.get("settings", default_settings())

    def _recover_discovery(self):
        state = self.store.get("discovery_state", default_discovery_state())
        previous = state.get("last_run")
        if previous and previous.get("running"):
            previous.update(running=False, message="Previous discovery was interrupted",
                            error="Nomisma closed before this search finished. The enabled schedule will retry when due.",
                            completed_at=datetime.now(timezone.utc).isoformat())
            state["retry_after"] = None
            self.store.set("discovery_state", state)

    def discovery_settings(self):
        return self.store.get("discovery_settings", default_discovery_settings())

    def save_discovery_settings(self, payload):
        with self.mutation_lock, self.lock:
            settings = validate_discovery_settings(payload, self.discovery_settings())
            if settings["schedule"]["enabled"] and settings["config"]["source"] == "alpaca":
                self.check_source({"source": "alpaca"})
            self.store.set("discovery_settings", settings)
        return self.discovery_snapshot()

    def _discovery_next_due(self, settings, state, now):
        schedule = settings["schedule"]
        if not schedule["enabled"]:
            return None
        zone = ZoneInfo(schedule["timezone"])
        local = now.astimezone(zone)
        retry = datetime.fromisoformat(state["retry_after"]) if state.get("retry_after") else now
        hour, minute = map(int, schedule["time"].split(":"))
        for offset in range(9):
            day = local.date() + timedelta(days=offset)
            if day.weekday() >= 5:
                continue
            scheduled = datetime(day.year, day.month, day.day, hour, minute, tzinfo=zone)
            if day.isoformat() == state.get("last_success_date"):
                last = state.get("last_success_at")
                scheduled = datetime.fromisoformat(last) + DISCOVERY_REPEAT if last else None
                if scheduled is None or scheduled.astimezone(zone) >= datetime(day.year, day.month, day.day, 16, tzinfo=zone):
                    continue
            candidate = max(scheduled, now, retry)
            if candidate.astimezone(zone).date() == day:
                return candidate.isoformat()
        return None

    def discovery_snapshot(self, now=None):
        now = now or datetime.now(timezone.utc)
        with self.lock:
            settings = self.discovery_settings()
            state = self.store.get("discovery_state", default_discovery_state())
            running = next((copy.deepcopy(job) for job in self.research_jobs.values()
                            if job["running"] and job["kind"] == "discovery"), None)
            busy = any(job["running"] for job in self.research_jobs.values())
        next_due = None if running else self._discovery_next_due(settings, state, now)
        enabled = settings["schedule"]["enabled"]
        message = "Weekday schedule is off"
        if running:
            message = running["message"]
        elif enabled:
            if busy and next_due and datetime.fromisoformat(next_due) <= now:
                message = "Waiting for the current research check to finish"
            elif state.get("retry_after") and datetime.fromisoformat(state["retry_after"]) > now:
                message = "Discovery failed; retry scheduled"
            else:
                message = "Weekday schedule is enabled"
        last_run = copy.deepcopy(state.get("last_run"))
        if last_run:
            last_run.pop("result", None)
        status = {"enabled": enabled, "running": running is not None,
                  "last_run": last_run, "last_success_date": state.get("last_success_date"),
                  "next_due": next_due, "retry_after": state.get("retry_after"), "message": message}
        return dict(settings, status=status, latest=state.get("latest"), job=running or state.get("last_run"))

    def discovery_due(self, now=None):
        now = now or datetime.now(timezone.utc)
        settings = self.discovery_settings()
        state = self.store.get("discovery_state", default_discovery_state())
        next_due = self._discovery_next_due(settings, state, now)
        if next_due and datetime.fromisoformat(next_due) <= now:
            return now.astimezone(ZoneInfo(settings["schedule"]["timezone"])).date().isoformat()
        return None

    def presets(self):
        return list(PRESETS) + self.store.presets()

    def status(self, since=None):
        with self.lock:
            job = dict(self.job)
        identifier = self.store.latest_id()
        latest = self.store.scan(identifier) if identifier and identifier != since else None
        return {"job": job, "latest": latest, "history": self.store.history()}

    def bootstrap(self):
        return dict(self.status(), settings=self.settings(), presets=self.presets(),
                    watchlist=self.store.watchlist(),
                    provider_status=dict(provider_status(), csv_available=self.store.get("csv_dataset") is not None))

    def save_settings(self, payload):
        with self.lock:
            settings = validate_settings(payload, self.settings())
            if settings["schedule"]["enabled"]:
                self.check_source(settings)
            self.store.set("settings", settings)
        return settings

    def check_source(self, settings):
        if settings["source"] == "alpaca" and not provider_status()["alpaca_configured"]:
            raise ValueError("Alpaca is not connected. Add ALPACA_API_KEY and ALPACA_SECRET_KEY to this project's .env, then restart Nomisma.")
        if settings["source"] == "csv" and self.store.get("csv_dataset") is None:
            raise ValueError("Import a historical OHLCV CSV before scanning this source.")

    def progress(self, message):
        with self.lock:
            self.job["message"] = str(message)

    def run_scan(self, settings):
        self.check_source(settings)
        self.progress("Loading daily price history…")
        if settings["source"] == "alpaca":
            dataset = fetch_alpaca(settings["universe"], settings["symbols"], progress=self.progress)
        elif settings["source"] == "csv":
            dataset = self.store.get("csv_dataset")
            from .instruments import stock_symbols
            allowed = stock_symbols()
            dataset = dict(dataset, assets=[asset for asset in dataset["assets"] if asset["symbol"] in allowed],
                           warnings=list(dataset.get("warnings", [])) + ["Stocks only: imported non-stock and unverified symbols are excluded."])
        else:
            dataset = demo_dataset()
        # Custom selections also apply to imported and illustrative datasets.
        if settings["universe"] == "custom" and settings["source"] != "alpaca":
            wanted = set(settings["symbols"])
            dataset = dict(dataset, assets=[asset for asset in dataset["assets"] if asset["symbol"] in wanted])
            missing = wanted - {asset["symbol"] for asset in dataset["assets"]}
            if missing:
                dataset["warnings"] = list(dataset.get("warnings", [])) + ["Symbols unavailable in this source: " + ", ".join(sorted(missing))]
        self.progress("Calculating indicators and ranking matching stocks…")
        return self.store.save_scan(screen(dataset, settings["filters"]))

    def start_scan(self, payload, scheduled_date=None):
        with self.mutation_lock:
            return self._start_scan(payload, scheduled_date)

    def _start_scan(self, payload, scheduled_date=None):
        settings = validate_settings(payload, self.settings())
        self.check_source(settings)
        with self.lock:
            if self.job["running"]:
                raise BusyError("A scan is already running. Wait for it to finish.")
            self.job = {"running": True, "message": "Starting scan…", "error": None, "scan_id": None}
            job = dict(self.job)
        worker = threading.Thread(target=self._worker, args=(settings, scheduled_date), daemon=True, name="nomisma-scan")
        worker.start()
        return job

    def start_research(self, kind, payload, scheduled_date=None):
        with self.mutation_lock:
            return self._start_research(kind, payload, scheduled_date)

    def _start_research(self, kind, payload, scheduled_date=None):
        if kind not in ("diagnostics", "discovery"):
            raise ValueError("Unknown research action.")
        settings = None
        if kind == "discovery":
            settings = validate_discovery_settings({"config": payload}, self.discovery_settings())
            payload = settings["config"]
        with self.lock:
            if any(job["running"] for job in self.research_jobs.values()):
                raise BusyError("A market-data check or discovery search is already running.")
            identifier = uuid.uuid4().hex
            job = {"id": identifier, "kind": kind, "running": True,
                   "message": "Checking market data…" if kind == "diagnostics" else "Finding session candidates…",
                   "error": None, "result": None, "started_at": datetime.now(timezone.utc).isoformat(),
                   "completed_at": None, "scheduled_date": scheduled_date}
            if settings is not None:
                self.store.set("discovery_settings", settings)
                state = self.store.get("discovery_state", default_discovery_state())
                state["last_run"] = copy.deepcopy(job)
                self.store.set("discovery_state", state)
            self.research_jobs[identifier] = job
            while len(self.research_jobs) > 32:
                del self.research_jobs[next(iter(self.research_jobs))]
            initial = copy.deepcopy(job)
        worker = threading.Thread(target=self._research_worker, args=(job, copy.deepcopy(payload)),
                                  name="nomisma-" + kind, daemon=True)
        try:
            worker.start()
        except Exception:
            self._finish_research(job, error="The research worker could not start. Try again.")
            raise
        return initial

    def _finish_research(self, job, result=None, error=None):
        with self.lock:
            completed = dict(job, running=False, completed_at=datetime.now(timezone.utc).isoformat(),
                             message="Needs attention" if error else (
                                 "Check complete" if job["kind"] == "diagnostics" else "Discovery complete"),
                             result=result, error=error)
            try:
                if job["kind"] == "discovery":
                    state = self.store.get("discovery_state", default_discovery_state())
                    state["last_run"] = dict(completed, result=None)
                    if error is None:
                        state["latest"] = completed
                    if job.get("scheduled_date"):
                        if error is None:
                            state["last_success_date"] = job["scheduled_date"]
                            state["last_success_at"] = completed["completed_at"]
                            state["retry_after"] = None
                        else:
                            state["retry_after"] = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
                    # A single transaction commits the result and deduplication
                    # date together, before advertising that the worker is idle.
                    self.store.set("discovery_state", state)
            except Exception as exc:
                completed.update(message="Needs attention", error="Discovery finished but could not save its result. Check available disk space and retry.")
                LOGGER.warning("Could not save research state (%s)", type(exc).__name__)
        # Update the radar before advertising completion, so a client that sees the job finish reads the new symbols.
        try:
            if job["kind"] == "discovery" and error is None and result:
                self._update_radar(result)
        finally:
            with self.lock:
                job.update(completed)

    def _update_radar(self, result):
        """Replace the radar's symbols with the search's top results; an active monitor restarts on them."""
        symbols = [row["symbol"] for row in result.get("rows", [])][:MAX_MONITOR_SYMBOLS]
        day = result.get("session_date")
        if not symbols:
            # An empty search keeps today's radar, not an earlier session's: pause until a search finds today's stocks.
            if day != self.radar_date and self.monitor.status["running"]:
                self.monitor.stop()
                with self.monitor.lock:
                    self.monitor.status["message"] = "Paused: no stock meets today's search yet. Monitoring resumes after the next search finds stocks."
                self.radar_paused = True
            return
        self.radar_date = day
        resume, self.radar_paused = self.radar_paused, False
        config = self.monitor.config
        if not resume and result.get("source") == config["source"] and set(symbols) == set(config["symbols"]):
            return
        change = {"source": result["source"], "symbols": symbols}
        try:
            if self.monitor.status["running"] or resume:
                self.monitor.stop()
                self.monitor.start(change)
            else:
                self.monitor.save_config(change)
        except Exception as exc:
            LOGGER.warning("Could not update the radar from discovery (%s)", type(exc).__name__)

    def _research_worker(self, job, payload):
        def progress(message):
            with self.lock:
                job["message"] = str(message)

        try:
            from .research import diagnose, discover
            if job["kind"] == "diagnostics":
                snapshot = self.monitor.snapshot()
                result = diagnose(snapshot["config"], snapshot, progress=progress, stop_event=self.stop_event,
                                  snapshot_provider=self.monitor.snapshot)
            else:
                result = discover(payload, progress=progress, stop_event=self.stop_event)
            self._finish_research(job, result=result)
        except Exception as exc:
            message = str(exc) if isinstance(exc, ValueError) else "The research action could not finish. Check your connection and try again."
            self._finish_research(job, error=message)
            LOGGER.warning("Research action failed (%s)", type(exc).__name__)

    def research_status(self, identifier):
        with self.lock:
            return copy.deepcopy(self.research_jobs.get(identifier))

    def restore_workspace(self, content):
        with self.mutation_lock, self.lock:
            if self.job["running"] or self.monitor.status["running"] or any(job["running"] for job in self.research_jobs.values()):
                raise BusyError("Stop the monitor and wait for scans and research checks to finish before restoring.")
            result = self.store.restore_backup(content)
            self.monitor.close()
            self.monitor = LiveMonitor(self.store)
            from .planner import Planner
            self.planner = Planner(self.store, self.monitor)
            self.job = {"running": False, "message": "Workspace restored", "error": None, "scan_id": None}
            self.research_jobs = {}
            self._recover_discovery()
            return dict(result, restored=True)

    def _worker(self, settings, scheduled_date):
        try:
            scan = self.run_scan(settings)
            if scheduled_date:
                self.store.set("schedule_last_success", scheduled_date)
                self.store.set("schedule_retry_after", None)
            with self.lock:
                self.job = {"running": False, "message": "Scan complete", "error": None, "scan_id": scan["id"]}
        except Exception as exc:
            # Do not log request headers, credentials, or provider response bodies.
            message = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else "The scan could not finish. Check your data source and try again."
            if scheduled_date:
                try:
                    self.store.set("schedule_retry_after", (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat())
                except Exception as persistence_error:
                    LOGGER.warning("Could not save scheduler retry state (%s)", type(persistence_error).__name__)
            with self.lock:
                self.job = {"running": False, "message": "Scan failed", "error": message, "scan_id": None}
            LOGGER.warning("Scan failed (%s)", type(exc).__name__)

    def schedule_due(self, now=None):
        settings = self.settings()
        schedule = settings["schedule"]
        local = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(schedule["timezone"]))
        if not schedule["enabled"] or local.weekday() >= 5 or local.strftime("%H:%M") < schedule["time"]:
            return None
        date = local.date().isoformat()
        if self.store.get("schedule_last_success") == date:
            return None
        retry = self.store.get("schedule_retry_after")
        if retry and local < datetime.fromisoformat(retry):
            return None
        return date

    def scheduler_tick(self, now=None):
        with self.mutation_lock:
            return self._scheduler_tick(now)

    def _scheduler_tick(self, now=None):
        due = self.schedule_due(now)
        if due:
            try:
                self.start_scan(self.settings(), scheduled_date=due)
            except BusyError:
                pass
            except (ValueError, RuntimeError) as exc:
                self.store.set("schedule_retry_after", (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat())
                with self.lock:
                    self.job.update(message="Scheduled scan needs attention", error=str(exc))

        discovery_date = self.discovery_due(now)
        if discovery_date:
            try:
                self.start_research("discovery", self.discovery_settings()["config"], scheduled_date=discovery_date)
            except BusyError:
                # Retain the due date; the next tick retries after other
                # diagnostics or a manual discovery search has finished.
                pass

    def start_scheduler(self):
        def loop():
            while not self.stop_event.is_set():
                try:
                    self.scheduler_tick()
                except Exception as exc:
                    LOGGER.warning("Scheduler check failed (%s)", type(exc).__name__)
                self.stop_event.wait(30)
        thread = threading.Thread(target=loop, daemon=True, name="nomisma-scheduler")
        thread.start()


def csv_export(scan):
    output = io.StringIO(newline="")
    fields = ["symbol", "name", "sector", "price", "change_pct", "score", "setup", "as_of", "source", "feed", "rsi", "relative_volume", "avg_volume", "return_20d", "relative_strength", "atr_pct"]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for result in scan["results"]:
        combined = dict(result, **result["metrics"])
        combined.update(source=scan["source"], feed=scan.get("feed", ""))
        row = {key: combined.get(key, "") for key in fields}
        for key, value in row.items():
            if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
                row[key] = "'" + value
        writer.writerow(row)
    return output.getvalue().encode("utf-8-sig")


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = "Nomisma"

        def log_message(self, format, *args):
            # Omit URL/query/body to keep local server logs minimal.
            return

        def _headers(self, status, kind, size, extra=None):
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()

        def _json(self, payload, status=200):
            data = json.dumps(payload, allow_nan=False).encode()
            self._headers(status, "application/json; charset=utf-8", len(data))
            self.wfile.write(data)

        def _same_origin(self):
            port = self.server.server_address[1]
            allowed = {"127.0.0.1:" + str(port), "localhost:" + str(port)}
            if self.headers.get("Host", "") not in allowed:
                self._json({"error": "Use the localhost address printed by Nomisma."}, 403)
                return False
            origin = self.headers.get("Origin")
            if origin and origin not in {"http://" + host for host in allowed}:
                self._json({"error": "Requests must originate from this Nomisma app."}, 403)
                return False
            return True

        def _page(self, query):
            params = parse_qs(query)
            try:
                limit = int(params.get("limit", ["20"])[0])
                offset = int(params.get("offset", ["0"])[0])
            except (TypeError, ValueError):
                raise ValueError("Pagination requires integer limit and offset.") from None
            if not 1 <= limit <= 100 or not 0 <= offset <= 10000000:
                raise ValueError("Limit must be 1–100 and offset must be 0–10000000.")
            return limit, offset

        def do_GET(self):
            if not self._same_origin():
                return
            try:
                parsed = urlparse(self.path)
                path = parsed.path
                if path == "/api/health":
                    return self._json({"app": "nomisma", "status": "ok", "version": "2", "data_directory": str(app.store.directory)})
                if path == "/api/history":
                    limit, offset = self._page(parsed.query)
                    return self._json({"history": app.store.history(limit, offset), "total": app.store.history_total(), "limit": limit, "offset": offset})
                if path == "/api/monitor/alerts":
                    limit, offset = self._page(parsed.query)
                    return self._json({"alerts": app.store.monitor_alerts(limit, offset), "total": app.store.monitor_alerts_total(), "limit": limit, "offset": offset})
                if path.startswith("/api/monitor/alerts/"):
                    # Detail can reconcile observed outcomes. Resolve the
                    # monitor inside the restore boundary, never against the
                    # previous workspace while its rows are being replaced.
                    with app.mutation_lock:
                        alert = app.monitor.alert_detail(path.removeprefix("/api/monitor/alerts/"))
                    return self._json(alert or {"error": "Alert not found."}, 200 if alert else 404)
                if path.startswith("/api/research/jobs/"):
                    job = app.research_status(path.removeprefix("/api/research/jobs/"))
                    return self._json({"job": job} if job else {"error": "Research job not found."}, 200 if job else 404)
                if path == "/api/workspace/backup":
                    data = app.store.backup()
                    filename = "nomisma-backup-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".sqlite3"
                    self._headers(200, "application/vnd.sqlite3", len(data), {"Content-Disposition": 'attachment; filename="' + filename + '"'})
                    return self.wfile.write(data)
                if path == "/api/planner/settings":
                    return self._json({"settings": app.planner.settings()})
                if path.startswith("/api/planner/alerts/"):
                    result = app.planner.alert_plan(path.removeprefix("/api/planner/alerts/"))
                    return self._json(result or {"error": "Alert not found."}, 200 if result else 404)
                if path == "/api/bootstrap":
                    return self._json(app.bootstrap())
                if path == "/api/discovery/settings":
                    return self._json(app.discovery_snapshot())
                if path == "/api/discovery/latest":
                    snapshot = app.discovery_snapshot()
                    return self._json({"job": snapshot["job"] if snapshot["status"]["running"] else snapshot["latest"],
                                       "status": snapshot["status"]})
                if path == "/api/monitor":
                    compact = parse_qs(parsed.query).get("compact", [None])[0] == "1"
                    return self._json(app.monitor.snapshot(compact=True) if compact else app.monitor.snapshot())
                if path.startswith("/api/monitor/symbol/"):
                    symbol = path.removeprefix("/api/monitor/symbol/").upper()
                    if not SYMBOL.fullmatch(symbol):
                        raise ValueError("Use a valid ticker symbol.")
                    row = app.monitor.row_detail(symbol)
                    return self._json({"row": row} if row is not None else {"error": "Monitor symbol not found."},
                                      200 if row is not None else 404)
                if path.startswith("/api/monitor/candles/"):
                    symbol = path.removeprefix("/api/monitor/candles/").upper()
                    if not SYMBOL.fullmatch(symbol):
                        raise ValueError("Use a valid ticker symbol.")
                    query = parse_qs(parsed.query)
                    return self._json(fetch_candles(symbol, query.get("timeframe", ["5Min"])[0], query.get("before", [None])[0]))
                if path == "/api/monitor/events":
                    return self._monitor_events(compact=parse_qs(parsed.query).get("compact", [None])[0] == "1")
                if path == "/api/monitor/export.csv":
                    data = monitor_csv(app.monitor.snapshot())
                    self._headers(200, "text/csv; charset=utf-8", len(data), {"Content-Disposition": 'attachment; filename="nomisma-intraday-monitor.csv"'})
                    return self.wfile.write(data)
                if path == "/api/status":
                    return self._json(app.status(parse_qs(parsed.query).get("since", [None])[0]))
                if path.startswith("/api/scans/"):
                    scan = app.store.scan(path.removeprefix("/api/scans/"))
                    return self._json(scan if scan else {"error": "Scan not found."}, 200 if scan else 404)
                if path == "/api/export.csv":
                    identifier = parse_qs(parsed.query).get("scan", [None])[0]
                    scan = app.store.scan(identifier)
                    if scan is None:
                        return self._json({"error": "Scan not found."}, 404)
                    data = csv_export(scan)
                    self._headers(200, "text/csv; charset=utf-8", len(data), {"Content-Disposition": 'attachment; filename="nomisma-' + scan["id"] + '.csv"'})
                    return self.wfile.write(data)
                if path.startswith("/api/"):
                    return self._json({"error": "Endpoint not found."}, 404)
                # Explicit allowlist prevents serving the database, .env, or Python source.
                file = {"/": "index.html", "/index.html": "index.html", "/styles.css": "styles.css", "/app.js": "app.js", "/live.js": "live.js", "/live.css": "live.css", "/planner.js": "planner.js", "/planner.css": "planner.css", "/favicon.svg": "favicon.svg"}.get(path)
                if not file or not (STATIC / file).is_file():
                    return self._json({"error": "Page not found."}, 404)
                data = (STATIC / file).read_bytes()
                kind = mimetypes.guess_type(file)[0] or "application/octet-stream"
                self._headers(200, kind + "; charset=utf-8", len(data))
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except ValueError as exc:
                self._json({"error": str(exc)}, 400)
            except Exception as exc:
                LOGGER.warning("Request failed (%s)", type(exc).__name__)
                self._json({"error": "The request could not be completed."}, 500)

        def _monitor_events(self, compact=False):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            last = None
            heartbeat = 0
            try:
                while not app.stop_event.is_set():
                    snapshot = app.monitor.snapshot(compact=True) if compact else app.monitor.snapshot()
                    payload = json.dumps(snapshot, allow_nan=False, separators=(",", ":"))
                    if payload != last:
                        self.wfile.write(("event: monitor\ndata: " + payload + "\n\n").encode())
                        self.wfile.flush()
                        last = payload
                        heartbeat = 0
                    else:
                        heartbeat += 1
                        if heartbeat >= 15:
                            self.wfile.write(b": heartbeat\n\n")
                            self.wfile.flush()
                            heartbeat = 0
                    if app.stop_event.wait(1):
                        break
            except (BrokenPipeError, ConnectionResetError, TimeoutError):
                pass

        def do_POST(self):
            if not self._same_origin():
                return
            with app.mutation_lock:
                self._post()

        def _post(self):
            try:
                path = urlparse(self.path).path
                if path == "/api/workspace/restore":
                    if self.headers.get_content_type() not in ("application/octet-stream", "application/vnd.sqlite3"):
                        return self._json({"error": "Choose a Nomisma SQLite backup file."}, 415)
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 1 <= length <= MAX_BACKUP:
                        return self._json({"error": "Backup must be between 1 byte and 128 MB."}, 413)
                    content = self.rfile.read(length)
                    if len(content) != length:
                        raise ValueError("The backup upload was incomplete.")
                    return self._json(app.restore_workspace(content))
                if self.headers.get_content_type() != "application/json":
                    return self._json({"error": "Send a JSON request body."}, 415)
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > MAX_BODY:
                    return self._json({"error": "Request body must be between 1 byte and 25 MB."}, 413)
                payload = json.loads(self.rfile.read(length), parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Non-finite JSON numbers are not allowed.")))
                if not isinstance(payload, dict):
                    raise ValueError("Send a JSON object.")
                if path == "/api/diagnostics":
                    return self._json({"job": app.start_research("diagnostics", payload)}, 202)
                if path == "/api/planner/settings":
                    return self._json(app.planner.save_settings(payload))
                if path == "/api/planner/analyze":
                    return self._json(app.planner.analyze(payload))
                if path == "/api/discovery":
                    return self._json({"job": app.start_research("discovery", payload)}, 202)
                if path == "/api/discovery/settings":
                    return self._json(app.save_discovery_settings(payload))
                if path == "/api/monitor/config":
                    return self._json({"config": app.monitor.save_config(payload)})
                if path == "/api/monitor/start":
                    with app.lock:
                        if any(job["running"] and job["kind"] == "diagnostics" for job in app.research_jobs.values()):
                            raise BusyError("Wait for the connection diagnostic to finish before starting the monitor.")
                    return self._json(app.monitor.start(payload), 202)
                if path == "/api/monitor/stop":
                    return self._json(app.monitor.stop())
                if path == "/api/monitor/refresh":
                    with app.lock:
                        if any(job["running"] and job["kind"] == "diagnostics" for job in app.research_jobs.values()):
                            raise BusyError("Wait for the connection diagnostic to finish before updating the monitor.")
                    return self._json(app.monitor.refresh(), 202)
                if path == "/api/monitor/float":
                    return self._json({"float": app.monitor.set_float(payload)})
                if path == "/api/monitor/alerts/ack":
                    if payload.get("all") is not True and not isinstance(payload.get("id"), str):
                        raise ValueError("Supply an alert id or all: true.")
                    if "source" in payload and payload["source"] not in ("demo", "alpaca"):
                        raise ValueError("Alert source must be demo or alpaca.")
                    return self._json({"alerts": app.store.acknowledge_monitor_alerts(
                        payload.get("id"), payload.get("all") is True, source=payload.get("source"))})
                if path == "/api/scan":
                    return self._json({"job": app.start_scan(payload)}, 202)
                if path == "/api/settings":
                    return self._json({"settings": app.save_settings(payload)})
                if path == "/api/watchlist":
                    symbol = payload.get("symbol", "")
                    if not isinstance(symbol, str) or not SYMBOL.fullmatch(symbol.strip().upper()):
                        raise ValueError("Invalid stock symbol.")
                    if type(payload.get("enabled")) is not bool:
                        raise ValueError("Watchlist enabled must be true or false.")
                    return self._json({"watchlist": app.store.set_watch(symbol.strip().upper(), payload["enabled"])})
                if path == "/api/presets":
                    name = payload.get("name", "")
                    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 60:
                        raise ValueError("Preset name must contain 1 to 60 characters.")
                    app.store.save_preset(name.strip(), validate_filters(payload.get("filters", {})))
                    return self._json({"presets": app.presets()})
                if path == "/api/import":
                    content = payload.get("csv")
                    if not isinstance(content, str):
                        raise ValueError("Supply CSV text in the csv field.")
                    dataset = parse_csv(content)
                    app.store.set("csv_dataset", dataset)
                    return self._json({"asset_count": len(dataset["assets"]), "as_of": dataset["as_of"]})
                return self._json({"error": "Endpoint not found."}, 404)
            except (BusyError, MonitorBusy) as exc:
                self._json({"error": str(exc)}, 409)
            except (ValueError, TypeError, KeyError) as exc:
                self._json({"error": str(exc) if isinstance(exc, ValueError) else "Invalid request fields."}, 400)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as exc:
                LOGGER.warning("Request failed (%s)", type(exc).__name__)
                self._json({"error": "The request could not be completed."}, 500)

    return Handler


def serve(app, port=8765):
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app))
    app.start_scheduler()
    print("Nomisma by Heuresis is running at http://127.0.0.1:%d" % server.server_port, flush=True)
    print("Keep this process running for daily schedules. Press Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.stop_event.set()
        app.monitor.close()
        server.server_close()
