"""Live monitor orchestration, event reconciliation, and durable setup alerts."""

import copy
import csv
import io
import logging
import math
import re
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .live_data import live_provider_status, load_live_seed, stream_live
from .monitor_metrics import DEFAULT_MONITOR_CONFIG, _minutes, build_rows, demo_bundle, validate_monitor_config

LOGGER = logging.getLogger("nomisma.monitor")
LEVELS = {"Watch": 0, "Buy": 1, "Strong buy": 2}
OBSERVATION_BASIS = "Observed completed-minute prices relative to the alert's completed-minute close. These are not simulated executions or investment returns; fees, spread and slippage are not included."


def timestamp(value):
    try:
        value = re.sub(r"(\.\d{6})\d+(?=Z|[+-]\d\d:\d\d$)", r"\1", value)
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result if result.tzinfo is not None else None
    except (AttributeError, TypeError, ValueError):
        return None


def utcnow():
    return datetime.now(timezone.utc)


class MonitorBusy(ValueError):
    pass


class LiveMonitor:
    def __init__(self, store):
        self.store = store
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.generation = 0
        self.config = validate_monitor_config(store.get("monitor_config", DEFAULT_MONITOR_CONFIG))
        self.bundle = None
        self.rows = []
        self.computed_at = 0
        self.dirty = True
        self.minute_versions = {}
        self.connection_epoch = 0
        self.status = {"running": False, "connection": "stopped", "message": "Choose your symbols and start monitoring.",
                       "error": None, "source": self.config["source"], "feed": None, "updated_at": None,
                       "session": None, "warnings": []}
        self.tracker = self.store.get("monitor_alert_tracker", {})
        # Earlier versions did not include the feed in tracker keys. Preserve
        # their deduplication only when a saved alert identifies that feed.
        legacy = {key: state for key, state in self.tracker.items() if key.count(":") == 2}
        if legacy:
            for alert in self.store.monitor_alerts(limit=500):
                market_time = timestamp(alert.get("market_time"))
                if market_time is None or not alert.get("feed"):
                    continue
                day = market_time.astimezone(ZoneInfo("America/New_York")).date().isoformat()
                old_key = "%s:%s:%s" % (alert.get("source"), alert.get("symbol"), day)
                if old_key in legacy:
                    new_key = "%s:%s:%s:%s" % (alert.get("source"), alert["feed"], alert.get("symbol"), day)
                    self.tracker.setdefault(new_key, legacy.pop(old_key))

    def save_config(self, payload):
        with self.lock:
            if self.status["running"]:
                raise MonitorBusy("Stop monitoring before changing symbols or alert settings.")
            config = validate_monitor_config(payload, self.config)
            self.store.set("monitor_config", config)
            if config != self.config:
                self.bundle = None
                self.rows = []
                self.minute_versions = {}
                self.status.update(source=config["source"], feed=None, session=None, updated_at=None,
                                   connection="stopped", warnings=[], error=None,
                                   message="Configuration saved. Start monitoring to load this selection.")
                self.dirty = True
            self.config = config
            return copy.deepcopy(config)

    def start(self, payload=None):
        with self.lock:
            if self.status["running"]:
                raise MonitorBusy("Monitoring is already running. Stop it before starting another session.")
            config = validate_monitor_config(payload or {}, self.config)
            if config["source"] == "alpaca" and not live_provider_status()["alpaca_configured"]:
                raise ValueError("Alpaca is not configured. Save ALPACA_API_KEY and ALPACA_SECRET_KEY in the project .env, then restart Nomisma.")
            self.store.set("monitor_config", config)
            self.config = config
            self.generation += 1
            generation = self.generation
            stop = threading.Event()
            self.stop_event = stop
            self.bundle = None
            self.rows = []
            self.minute_versions = {}
            self.dirty = True
            self.status = {"running": True, "connection": "loading", "message": "Loading session history and volume baselines…",
                           "error": None, "source": config["source"], "feed": None, "updated_at": None,
                           "session": None, "warnings": []}
            worker = threading.Thread(target=self._worker, args=(copy.deepcopy(config), generation, stop), daemon=True, name="nomisma-monitor")
            worker.start()
        return self.snapshot()

    def stop(self):
        with self.lock:
            self.stop_event.set()
            self.generation += 1
            self.status.update(running=False, connection="stopped", message="Monitoring stopped.", error=None)
            self.dirty = True
        return self.snapshot()

    def close(self):
        with self.lock:
            self.stop_event.set()
            self.generation += 1
            self.status.update(running=False, connection="stopped")

    def _active(self, generation, stop):
        return generation == self.generation and not stop.is_set() and self.status["running"]

    def _set_status(self, generation, stop, connection=None, message=None, error=None):
        with self.lock:
            if self._active(generation, stop):
                self.status.update(error=error)
                if connection:
                    self.status["connection"] = connection
                if message:
                    self.status["message"] = message
                self.dirty = True

    def _install_bundle(self, bundle, generation, stop):
        with self.lock:
            if not self._active(generation, stop):
                return False
            if bundle["source"] != "demo":
                overrides = self.store.get("monitor_float_overrides", {})
                for asset in bundle["assets"]:
                    if asset["symbol"] in overrides:
                        asset["float"] = overrides[asset["symbol"]]
            if not self.bundle or self.bundle["session"]["date"] != bundle["session"]["date"]:
                self.minute_versions = {}
            self.bundle = bundle
            self.status.update(source=bundle["source"], feed=bundle["feed"], session=bundle["session"],
                               warnings=list(bundle.get("warnings", [])), updated_at=bundle.get("as_of"), error=None)
            self._refresh_outcomes()
            self.dirty = True
            return True

    def _worker(self, config, generation, stop):
        if config["source"] == "demo":
            step = 0
            try:
                while not stop.is_set():
                    bundle = demo_bundle(config["symbols"], step=step)
                    if not self._install_bundle(bundle, generation, stop):
                        return
                    with self.lock:
                        if not self._active(generation, stop):
                            return
                        self.status.update(connection="demo", message="Synthetic simulation · one simulated minute every 3 seconds.")
                        self._refresh_rows()
                        self._evaluate_alerts(self.rows, config)
                    step += 1
                    if stop.wait(3):
                        return
            except Exception as exc:
                self._terminal_error(generation, stop, exc)
            return

        attempt = 0
        while not stop.is_set():
            try:
                with self.lock:
                    self.connection_epoch += 1
                    epoch = self.connection_epoch
                self._set_status(generation, stop, "loading", "Loading completed minute bars, 30-session volume, and float…")
                bundle = load_live_seed(config["symbols"],
                                        progress=lambda message: self._set_status(generation, stop, message=message),
                                        stop_event=stop)
                if not self._install_bundle(bundle, generation, stop):
                    return
                self._set_status(generation, stop, "connecting", "Authenticating the real-time market stream…")

                def on_status(state):
                    message = "Streaming trades and quotes · minute-bar technical alerts." if state == "live" else "Connecting to Alpaca…"
                    self._set_status(generation, stop, state, message)
                    if state == "live":
                        # REST history and stream authentication are not atomic.
                        # Reconcile in the background so a minute crossing that
                        # boundary does not leave permanent volume/VWAP gaps.
                        threading.Thread(target=self._reconcile, args=(config, generation, stop, epoch),
                                         name="nomisma-minute-reconcile", daemon=True).start()

                stream_live(config["symbols"], lambda event: self._on_event(event, config, generation, stop), stop, on_status=on_status)
                if stop.is_set():
                    return
                raise ValueError("The market stream disconnected.")
            except Exception as exc:
                if stop.is_set() or generation != self.generation:
                    return
                attempt += 1
                delay = min(30, 2 ** min(attempt, 5))
                message = str(exc) if isinstance(exc, ValueError) else "The market connection was interrupted."
                self._set_status(generation, stop, "reconnecting", "Reconnecting in %s seconds; alerts are paused." % delay, message)
                if stop.wait(delay):
                    return

    def _reconcile(self, config, generation, stop, epoch):
        """Repair missing minute history without rolling back newer events."""
        while not stop.is_set():
            with self.lock:
                if not self._active(generation, stop) or self.status["connection"] != "live" or epoch != self.connection_epoch:
                    return
            started = time.monotonic()
            try:
                refreshed = load_live_seed(config["symbols"], stop_event=stop)
                with self.lock:
                    if not self._active(generation, stop) or not self.bundle or self.status["connection"] != "live" or epoch != self.connection_epoch:
                        return
                    if refreshed["session"]["date"] != self.bundle["session"]["date"]:
                        return
                    for fresh in refreshed["assets"]:
                        current = next((asset for asset in self.bundle["assets"] if asset["symbol"] == fresh["symbol"]), None)
                        if current is None:
                            continue
                        current["bars"] = fresh["bars"]
                        merged = {timestamp(bar["t"]): bar for bar in current["minutes"]}
                        for bar in fresh["minutes"]:
                            stamp = timestamp(bar["t"])
                            if self.minute_versions.get((current["symbol"], stamp), 0) <= started:
                                merged[stamp] = bar
                        current["minutes"] = [merged[stamp] for stamp in sorted(merged)][-600:]
                        for field in ("latestTrade", "latestQuote"):
                            incoming = fresh.get("snapshot", {}).get(field) or {}
                            existing = current.get("snapshot", {}).get(field) or {}
                            new_time, old_time = timestamp(incoming.get("t")), timestamp(existing.get("t"))
                            if new_time and (old_time is None or new_time > old_time):
                                current.setdefault("snapshot", {})[field] = incoming
                        fresh_snapshot = fresh.get("snapshot", {})
                        current_snapshot = current.setdefault("snapshot", {})
                        received = timestamp(fresh_snapshot.get("_received_at"))
                        existing_received = timestamp(current_snapshot.get("_daily_received_at") or current_snapshot.get("_received_at"))
                        if (received and (existing_received is None or received > existing_received)
                                and current_snapshot.get("_daily_stream_version", 0) <= started):
                            current_snapshot["dailyBar"] = fresh_snapshot.get("dailyBar")
                            current_snapshot["_daily_received_at"] = received.isoformat()
                        override = self.store.get("monitor_float_overrides", {}).get(current["symbol"])
                        current["float"] = override or fresh.get("float")
                    self.dirty = True
                    self._refresh_outcomes()
            except Exception as exc:
                if stop.is_set() or generation != self.generation:
                    return
                with self.lock:
                    message = "Minute-history refresh failed; incomplete histories cannot trigger alerts."
                    if message not in self.status["warnings"]:
                        self.status["warnings"].append(message)
                LOGGER.warning("Minute reconciliation failed (%s)", type(exc).__name__)
            if stop.wait(60):
                return

    def _terminal_error(self, generation, stop, exc):
        with self.lock:
            if self._active(generation, stop):
                message = str(exc) if isinstance(exc, ValueError) else "Monitoring could not continue. Stop and restart the monitor."
                self.status.update(running=False, connection="error", message="Monitoring needs attention.", error=message)
                self.dirty = True
        LOGGER.warning("Monitor failed (%s)", type(exc).__name__)

    def _on_event(self, event, config, generation, stop):
        with self.lock:
            if not self._active(generation, stop) or not self.bundle or not isinstance(event, dict):
                return
            if event.get("T") == "nomisma_subscription":
                self.status["channel_subscriptions"] = {key: event.get(key) for key in
                                                        ("statuses", "lulds", "required", "checked_at", "message")}
                self.dirty = True
                return
            symbol = event.get("S")
            asset = next((item for item in self.bundle["assets"] if item["symbol"] == symbol), None)
            if asset is None:
                return
            kind = event.get("T")
            stamp = timestamp(event.get("t"))
            if stamp is None:
                return
            now = utcnow()
            if stamp > now + timedelta(seconds=5):
                return
            session = self.bundle["session"]
            session_close = timestamp(session["close"])
            # Re-seed on the first event of a subsequent trading date; do not
            # reuse yesterday's VWAP, opening gap, volume, or alert state.
            if stamp.astimezone(ZoneInfo("America/New_York")).date() > date.fromisoformat(session["date"]):
                raise ValueError("A new trading session is starting; refreshing baselines.")
            snapshot = asset.setdefault("snapshot", {})
            advancing_bar = False
            if kind in ("t", "q"):
                key = "latestTrade" if kind == "t" else "latestQuote"
                previous = timestamp(snapshot.get(key, {}).get("t"))
                if previous and stamp < previous:
                    return
                snapshot[key] = dict(event)
            elif kind in ("b", "u"):
                session_open = timestamp(session["open"])
                if not session_open <= stamp < session_close:
                    return
                fields = {"open": "o", "high": "h", "low": "l", "close": "c", "volume": "v", "vwap": "vw"}
                minute = {"t": event["t"]}
                for name, key in fields.items():
                    value = event.get(key)
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                        return
                    if value < 0 or (name != "volume" and value == 0):
                        return
                    minute[name] = value
                if minute["low"] > min(minute["open"], minute["close"]) or minute["high"] < max(minute["open"], minute["close"]):
                    return
                minute_map = {timestamp(bar["t"]): bar for bar in asset.get("minutes", [])}
                advancing_bar = not minute_map or stamp > max(minute_map)
                minute_map[stamp] = minute
                asset["minutes"] = [minute_map[key] for key in sorted(minute_map)][-600:]
                self.minute_versions[(symbol, stamp)] = time.monotonic()
            elif kind == "d":
                snapshot["dailyBar"] = dict(event)
                snapshot["_daily_received_at"] = now.isoformat()
                snapshot["_daily_stream_version"] = time.monotonic()
            elif kind in ("s", "l"):
                key = "tradingStatus" if kind == "s" else "priceBands"
                previous = timestamp(snapshot.get(key, {}).get("t"))
                if previous and stamp < previous:
                    return
                snapshot[key] = dict(event)
            elif kind in ("c", "x"):
                current = snapshot.get("latestTrade", {})
                canceled = event.get("oi") if kind == "c" else event.get("i")
                if current.get("i") == canceled:
                    snapshot.pop("latestTrade", None)
            else:
                return
            self.status["updated_at"] = now.isoformat()
            self.dirty = True
            if kind in ("b", "u"):
                self._refresh_outcomes()
            if kind == "b" and advancing_bar and stamp + timedelta(minutes=1) <= now:
                # Replacements and duplicate bars may refresh display, but the
                # persisted signal_bar_at gate prevents repeated notifications.
                single = dict(self.bundle, assets=[asset])
                rows = build_rows(single, config, now=now)
                if self.status["connection"] == "live" and rows and timestamp(rows[0].get("signal_bar_at")) == stamp:
                    try:
                        self._evaluate_alerts(rows, config)
                    except Exception as exc:
                        self.status["error"] = "Could not persist an alert. Check available disk space."
                        LOGGER.warning("Could not persist monitor alert (%s)", type(exc).__name__)

    def _refresh_rows(self):
        if self.bundle is None:
            self.rows = []
            return
        now = timestamp(self.bundle["as_of"]) if self.bundle["source"] == "demo" else utcnow()
        rows = build_rows(self.bundle, self.config, now=now)
        if not self.status["running"] or self.status["connection"] not in ("demo", "live"):
            for row in rows:
                row["alert_eligible"] = False
                row["signal"] = "Watch"
                row["blockers"] = list(row.get("blockers", [])) + ["Alerts paused: monitor is not connected."]
                row["eligibility"].update(eligible=False, primary_blocker="Alerts paused: monitor is not connected.")
        for row in rows:
            self._confirmation(row, self.config)
        self.rows = rows
        self.computed_at = time.monotonic()
        self.dirty = False

    def _evaluate_alerts(self, rows, config):
        changed = False
        for row in rows:
            bar = row.get("signal_bar_at")
            bar_time = timestamp(bar)
            if bar_time is None:
                continue
            key = self._tracker_key(row)
            previous = self.tracker.get(key, {})
            last = timestamp(previous.get("bar"))
            if last and bar_time <= last:
                continue
            state = copy.deepcopy(previous)
            level = row.get("signal", "Watch") if row.get("alert_eligible") and config["alerts_enabled"] else "Watch"
            rank = LEVELS.get(level, 0)
            prior_rank = state.get("candidate_rank", 0)
            contiguous = last is not None and bar_time - last == timedelta(minutes=1)
            state["buy_streak"] = state.get("buy_streak", 0) + 1 if contiguous and rank >= 1 and prior_rank >= 1 else int(rank >= 1)
            state["strong_streak"] = state.get("strong_streak", 0) + 1 if contiguous and rank >= 2 and prior_rank >= 2 else int(rank >= 2)
            state.update(bar=bar, candidate_rank=rank)
            if rank == 0:
                state["armed"] = True
            confirmed_rank = (2 if rank == 2 and state["strong_streak"] >= config["confirmation_bars"]
                              else 1 if rank >= 1 and state["buy_streak"] >= config["confirmation_bars"] else 0)
            last_alert = timestamp(state.get("last_alert_market_time"))
            elapsed = (bar_time - last_alert).total_seconds() if last_alert else float("inf")
            prior_alert_rank = state.get("last_alert_rank", 0)
            upgrade = confirmed_rank > prior_alert_rank
            rearmed = state.get("armed", True) and elapsed >= config["cooldown_seconds"]
            if confirmed_rank and (upgrade or rearmed):
                confirmed_level = "Strong buy" if confirmed_rank == 2 else "Buy"
                self._confirmation(row, config, state)
                alert = {"id": uuid.uuid4().hex, "symbol": row["symbol"], "level": confirmed_level, "source": row["source"],
                         "feed": row["feed"], "created_at": utcnow().isoformat(), "market_time": bar,
                         "price": row.get("price"), "score": row.get("signal_score"),
                         "reasons": row.get("reasons", []), "acknowledged": False}
                reference = next((item.get("close") for item in row.get("chart", []) if timestamp(item.get("t")) == bar_time), None)
                session = copy.deepcopy(self.bundle.get("session", {})) if self.bundle else {}
                alert.update(schema_version=1, session_date=row["session_date"], config=copy.deepcopy(config),
                             snapshot=copy.deepcopy(row), session=session, reference_price=reference,
                             reference_at=(bar_time + timedelta(minutes=1)).isoformat(), observation_basis=OBSERVATION_BASIS)
                alert["outcomes"] = self._observations(alert, self.bundle)
                state.update(last_alert_market_time=bar, last_alert_rank=confirmed_rank, armed=False)
                updated = dict(self.tracker, **{key: state})
                self.store.save_monitor_alert(alert, self._trim_tracker(updated))
                self.tracker = updated
            else:
                self.tracker[key] = state
            changed = True
            self._confirmation(row, config)
        if changed:
            self.tracker = self._trim_tracker(self.tracker)
            self.store.set("monitor_alert_tracker", self.tracker)

    @staticmethod
    def _tracker_key(row):
        return "%s:%s:%s:%s" % (row["source"], row["feed"], row["symbol"], row["session_date"])

    def _confirmation(self, row, config, state=None):
        state = state if state is not None else self.tracker.get(self._tracker_key(row), {})
        current_bar = timestamp(row.get("signal_bar_at"))
        matching = current_bar is not None and timestamp(state.get("bar")) == current_bar
        enabled = row.get("alert_eligible") and config["alerts_enabled"]
        buy = state.get("buy_streak", 0) if matching and enabled else 0
        strong = state.get("strong_streak", 0) if matching and enabled else 0
        level = row.get("signal", "Watch")
        bars = strong if level == "Strong buy" else buy if level == "Buy" else 0
        last_alert = timestamp(state.get("last_alert_market_time"))
        cooldown = max(0, config["cooldown_seconds"] - (current_bar - last_alert).total_seconds()) if current_bar and last_alert else 0
        row["confirmation"] = {"buy_bars": buy, "strong_buy_bars": strong, "required": config["confirmation_bars"],
                               "bars": min(bars, config["confirmation_bars"]), "level": level,
                               "confirmed": bars >= config["confirmation_bars"], "cooldown_remaining_seconds": cooldown}

    @staticmethod
    def _observations(alert, bundle):
        """Only complete, contiguous future windows from matching provenance."""
        old = alert.get("outcomes", {})
        session = alert.get("session") or {}
        reference_at = timestamp(alert.get("reference_at"))
        reference = alert.get("reference_price")
        valid_reference = (reference_at is not None and type(reference) in (int, float)
                           and math.isfinite(reference) and reference > 0)
        session_open, session_close = timestamp(session.get("open")), timestamp(session.get("close"))
        now = (timestamp(bundle.get("as_of")) if bundle and bundle.get("source") == "demo" else utcnow())
        same = bool(bundle and bundle.get("source") == alert.get("source") and bundle.get("feed") == alert.get("feed")
                    and bundle.get("session", {}).get("date") == alert.get("session_date"))
        asset = next((item for item in bundle.get("assets", []) if item.get("symbol") == alert.get("symbol")), None) if same else None
        minutes, _ = _minutes(asset.get("minutes"), session_open, session_close, now) if asset and now else ([], False)
        by_time = {bar["t"]: bar for bar in minutes}
        result = {}
        for duration in (5, 15, 30):
            key = str(duration)
            target = reference_at + timedelta(minutes=duration) if reference_at else None
            outcome = {"status": "pending", "reason": "Waiting for the complete observation window.",
                       "target_at": target.isoformat() if target else None, "source": alert.get("source"), "feed": alert.get("feed"),
                       "close_change_pct": None, "adverse_excursion_pct": None, "end_close": None, "observed_at": None}
            if not valid_reference or session_open is None or session_close is None:
                outcome.update(status="unavailable", reason="This alert has no complete original price/session evidence; older alerts cannot be reconstructed.")
            elif target > session_close:
                outcome.update(status="unavailable", reason="The observation window extends beyond the regular session close.")
            elif not same or asset is None:
                # Preserve already observed results when looking at a different
                # symbol, feed, or session. Never mix providers or sessions.
                if old.get(key, {}).get("status") == "observed":
                    outcome = old[key]
                elif alert.get("source") == "demo":
                    outcome.update(reason="Resume the matching synthetic session and symbol to collect this observation.")
                elif now and now >= target:
                    outcome.update(status="unavailable", reason="Matching symbol, source, feed and session minute history is not loaded.")
                else:
                    outcome.update(reason="Matching symbol, source, feed and session minute history is not loaded yet.")
            elif now is None or now < target:
                pass
            else:
                window = [by_time.get(reference_at + timedelta(minutes=index)) for index in range(duration)]
                if any(bar is None for bar in window):
                    outcome.update(status="unavailable", reason="One or more completed minutes are missing from the observation window; history reconciliation may repair it.")
                else:
                    end_close = window[-1]["close"]
                    low = min(bar["low"] for bar in window)
                    outcome.update(status="observed", reason=None, end_close=end_close,
                                   close_change_pct=(end_close / reference - 1) * 100,
                                   adverse_excursion_pct=min(0, (low / reference - 1) * 100),
                                   observed_at=target.isoformat())
            result[key] = outcome
        return result

    def _refresh_outcomes(self):
        if self.bundle is None:
            return
        alerts = self.store.monitor_session_alerts(self.bundle["source"], self.bundle["feed"], self.bundle["session"]["date"])
        for alert in alerts:
            outcomes = self._observations(alert, self.bundle)
            if outcomes != alert.get("outcomes"):
                self.store.update_monitor_outcomes(alert["id"], outcomes)

    def refresh_outcomes(self):
        with self.lock:
            self._refresh_outcomes()

    def alert_detail(self, identifier):
        with self.lock:
            alert = self.store.monitor_alert(identifier)
            if alert is None:
                return None
            outcomes = self._observations(alert, self.bundle)
            if outcomes != alert.get("outcomes"):
                self.store.update_monitor_outcomes(identifier, outcomes)
                alert["outcomes"] = outcomes
            alert.setdefault("observation_basis", OBSERVATION_BASIS)
            return alert

    @staticmethod
    def _trim_tracker(tracker):
        # Bound state while retaining recent symbol/session deduplication.
        return dict(sorted(tracker.items(), key=lambda item: item[1].get("bar", ""))[-500:])

    def snapshot(self):
        with self.lock:
            if self.dirty or time.monotonic() - self.computed_at >= 1:
                self._refresh_rows()
            result = {"config": copy.deepcopy(self.config), "status": copy.deepcopy(self.status), "rows": copy.deepcopy(self.rows)}
        result["alerts"] = self.store.monitor_alerts()
        result["provider_status"] = live_provider_status()
        return result

    def set_float(self, payload):
        if not isinstance(payload, dict) or set(payload) - {"symbol", "shares", "as_of"}:
            raise ValueError("Supply a symbol, float shares, and as_of date.")
        symbol = payload.get("symbol")
        validated = validate_monitor_config({"symbols": [symbol]}, self.config)
        symbol = validated["symbols"][0]
        shares = payload.get("shares")
        value = None
        if shares is not None:
            if isinstance(shares, bool) or not isinstance(shares, (int, float)) or not math.isfinite(shares) or not 1 <= shares <= 1e13 or int(shares) != shares:
                raise ValueError("Float must be a positive whole number of shares, at most 10 trillion.")
            try:
                day = date.fromisoformat(payload["as_of"])
            except (KeyError, TypeError, ValueError):
                raise ValueError("Float as_of must use YYYY-MM-DD.") from None
            if day > utcnow().date():
                raise ValueError("Float as_of cannot be a future date.")
            value = {"shares": int(shares), "as_of": day.isoformat(), "source": "Manual"}
        with self.lock:
            overrides = self.store.get("monitor_float_overrides", {})
            if value is None:
                overrides.pop(symbol, None)
            else:
                overrides[symbol] = value
            self.store.set("monitor_float_overrides", overrides)
            if self.bundle and self.bundle["source"] != "demo":
                for asset in self.bundle["assets"]:
                    if asset["symbol"] == symbol:
                        asset["float"] = value
                self.dirty = True
        return value


def monitor_csv(snapshot):
    fields = ["symbol", "source", "feed", "session_date", "price", "price_at", "day_volume", "day_volume_at", "session_volume", "volume_at",
              "float_shares", "float_as_of", "float_source", "float_turnover", "volume_30d_total", "avg_volume_30d",
              "relative_volume", "minute_relative_volume", "gap_pct", "change_pct", "spread_pct", "vwap", "ema9", "ema20",
              "rsi", "signal_score", "signal", "alert_eligible", "stale", "market_open"]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in snapshot["rows"]:
        values = {}
        for key in fields:
            value = row.get(key, "")
            if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
                value = "'" + value
            values[key] = value
        writer.writerow(values)
    return output.getvalue().encode("utf-8-sig")
