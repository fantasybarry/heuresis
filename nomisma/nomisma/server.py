"""Loopback web application, scan orchestration, and persistent daily scheduling."""

import csv
import io
import json
import logging
import mimetypes
import re
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from .engine import DEFAULT_FILTERS, PRESETS, screen, validate_filters
from .providers import demo_dataset, fetch_alpaca, parse_csv, provider_status
from .storage import Store
from .monitor import LiveMonitor, MonitorBusy, monitor_csv

LOGGER = logging.getLogger("nomisma")
STATIC = Path(__file__).parent / "static"
MAX_BODY = 25 * 1024 * 1024
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


class BusyError(Exception):
    pass


class Application:
    def __init__(self, directory, seed=True):
        self.store = Store(directory)
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.job = {"running": False, "message": "Ready to scan", "error": None, "scan_id": None}
        if self.store.get("settings") is None:
            self.store.set("settings", default_settings())
        if seed and self.store.scan() is None:
            self.store.save_scan(screen(demo_dataset(), DEFAULT_FILTERS))
        self.monitor = LiveMonitor(self.store)

    def settings(self):
        return self.store.get("settings", default_settings())

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
            raise ValueError("Alpaca is not connected. Add ALPACA_API_KEY and ALPACA_SECRET_KEY to projects/nomisma/.env, then restart Nomisma.")
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
            with self.lock:
                self.job = {"running": False, "message": "Scan failed", "error": message, "scan_id": None}
            if scheduled_date:
                try:
                    self.store.set("schedule_retry_after", (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat())
                except Exception as persistence_error:
                    LOGGER.warning("Could not save scheduler retry state (%s)", type(persistence_error).__name__)
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

        def do_GET(self):
            if not self._same_origin():
                return
            try:
                parsed = urlparse(self.path)
                path = parsed.path
                if path == "/api/bootstrap":
                    return self._json(app.bootstrap())
                if path == "/api/monitor":
                    return self._json(app.monitor.snapshot())
                if path == "/api/monitor/events":
                    return self._monitor_events()
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
                file = {"/": "index.html", "/index.html": "index.html", "/styles.css": "styles.css", "/app.js": "app.js", "/live.js": "live.js", "/live.css": "live.css", "/favicon.svg": "favicon.svg"}.get(path)
                if not file or not (STATIC / file).is_file():
                    return self._json({"error": "Page not found."}, 404)
                data = (STATIC / file).read_bytes()
                kind = mimetypes.guess_type(file)[0] or "application/octet-stream"
                self._headers(200, kind + "; charset=utf-8", len(data))
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as exc:
                LOGGER.warning("Request failed (%s)", type(exc).__name__)
                self._json({"error": "The request could not be completed."}, 500)

        def _monitor_events(self):
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
                    payload = json.dumps(app.monitor.snapshot(), allow_nan=False, separators=(",", ":"))
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
            try:
                if self.headers.get_content_type() != "application/json":
                    return self._json({"error": "Send a JSON request body."}, 415)
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > MAX_BODY:
                    return self._json({"error": "Request body must be between 1 byte and 25 MB."}, 413)
                payload = json.loads(self.rfile.read(length), parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Non-finite JSON numbers are not allowed.")))
                if not isinstance(payload, dict):
                    raise ValueError("Send a JSON object.")
                path = urlparse(self.path).path
                if path == "/api/monitor/config":
                    return self._json({"config": app.monitor.save_config(payload)})
                if path == "/api/monitor/start":
                    return self._json(app.monitor.start(payload), 202)
                if path == "/api/monitor/stop":
                    return self._json(app.monitor.stop())
                if path == "/api/monitor/float":
                    return self._json({"float": app.monitor.set_float(payload)})
                if path == "/api/monitor/alerts/ack":
                    if payload.get("all") is not True and not isinstance(payload.get("id"), str):
                        raise ValueError("Supply an alert id or all: true.")
                    return self._json({"alerts": app.store.acknowledge_monitor_alerts(payload.get("id"), payload.get("all") is True)})
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
