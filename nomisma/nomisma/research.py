"""Read-only provider diagnostics and current-session candidate discovery.

Snapshot and listing contracts:
https://docs.alpaca.markets/us/reference/stocksnapshots-1
https://docs.alpaca.markets/us/reference/get-v2-assets-1
https://docs.alpaca.markets/us/docs/real-time-stock-pricing-data

No fallback feed, order endpoints, or credential values are returned.
"""

from datetime import datetime, timedelta, timezone
import math
import re
import threading

from . import live_data as live
from . import providers
from . import monitor_metrics as metrics
from .monitor_metrics import demo_bundle


_DISCOVERY_DEFAULTS = {"source": "demo", "universe": "curated", "symbols": [],
                       "min_price": 0, "max_price": 1000, "min_day_volume": 0,
                       "min_change_pct": 0, "limit": 100}
_BOUNDS = {"min_price": (0, 1000000), "max_price": (0, 1000000),
           "min_day_volume": (0, 1e12), "min_change_pct": (-100, 1000000), "limit": (1, 500)}
_DEMO_SYMBOLS = ["LABA", "LABB", "LABC", "LABD", "LABE", "LABF", "LABG", "LABH"]


def _report(progress, message, stop_event=None):
    live._check_stop(stop_event)
    if progress:
        progress(message)


def validate_discovery(payload):
    if not isinstance(payload, dict) or set(payload) - set(_DISCOVERY_DEFAULTS):
        raise ValueError("Supply discovery source, universe, symbols, and supported filters.")
    result = dict(_DISCOVERY_DEFAULTS, **payload)
    if result["source"] not in ("demo", "alpaca"):
        raise ValueError("Discovery source must be demo or alpaca.")
    if result["universe"] not in ("curated", "all", "custom"):
        raise ValueError("Discovery universe must be curated, all, or custom.")
    for key, (low, high) in _BOUNDS.items():
        value = result[key]
        if not metrics._number(value, low, high):
            raise ValueError("{} must be a finite number from {} to {}.".format(key, low, high))
    if not isinstance(result["limit"], int):
        raise ValueError("Discovery limit must be an integer.")
    if result["min_price"] > result["max_price"]:
        raise ValueError("min_price cannot exceed max_price.")
    symbols = result["symbols"]
    if isinstance(symbols, str):
        symbols = [value for value in re.split(r"[\s,]+", symbols.strip()) if value]
    if not isinstance(symbols, (list, tuple)) or len(symbols) > providers.MAX_CUSTOM_SYMBOLS:
        raise ValueError("Discovery symbols must be a list of at most 1,000 ticker symbols.")
    result["symbols"] = list(dict.fromkeys(providers._symbol(value) for value in symbols))
    if result["universe"] == "custom" and not result["symbols"]:
        raise ValueError("Enter at least one ticker for a custom discovery universe.")
    return result


def _calendar(now, headers, account_url, stop_event=None):
    today = now.astimezone(live._NY).date()
    entries = live._get_json(account_url + "/v2/calendar", {
        "start": (today - timedelta(days=100)).isoformat(), "end": today.isoformat()}, headers, stop_event)
    return live._session(entries, now)


def _phase(session, now):
    if session["date"] != now.astimezone(live._NY).date().isoformat():
        return "closed"
    if now < live._stamp(session["open"]):
        return "premarket"
    if now < live._stamp(session["close"]):
        return "regular"
    return "after-hours"


def _universe(config, headers, account_url, progress, stop_event):
    if config["universe"] == "custom":
        requested = config["symbols"]
        return requested, {symbol: providers._asset_metadata(symbol) for symbol in requested}, "Custom symbols", []
    if config["universe"] == "curated":
        requested = list(providers.CURATED_SYMBOLS)
        return requested, {symbol: providers._asset_metadata(symbol) for symbol in requested}, "Maintained starter universe", []
    _report(progress, "Loading active tradable US listings…", stop_event)
    listing = live._get_json(account_url + "/v2/assets", {"status": "active", "asset_class": "us_equity"}, headers, stop_event)
    if not isinstance(listing, list):
        raise ValueError("Alpaca returned an invalid listing response.")
    metadata = {}
    unsupported = 0
    for item in listing:
        if not isinstance(item, dict):
            raise ValueError("Alpaca returned an invalid listing record.")
        if (item.get("status") != "active" or item.get("tradable") is not True
                or item.get("class", "us_equity") != "us_equity"
                or item.get("exchange") not in ("NASDAQ", "NYSE", "AMEX", "ARCA", "NYSEARCA", "BATS")):
            continue
        try:
            symbol = providers._symbol(item.get("symbol"))
        except ValueError:
            unsupported += 1
            continue
        metadata[symbol] = {"symbol": symbol, "name": str(item.get("name") or symbol)[:160]}
    if not metadata or len(metadata) > 20000:
        raise ValueError("Listing universe is empty or exceeds 20,000 symbols; select a smaller universe.")
    warnings = ["All listings means active tradable NASDAQ, NYSE, AMEX, ARCA/NYSEARCA and BATS US equities offered by Alpaca; ETFs and other exchange-traded products may be included. It is not every US security."]
    if unsupported:
        warnings.append("Skipped {} unsupported ticker formats.".format(unsupported))
    return sorted(metadata), metadata, "Alpaca active tradable US listings", warnings


def _stamp_or_none(raw):
    try:
        return live._stamp(raw)
    except (ValueError, TypeError, AttributeError, OverflowError):
        return None


def _positive(raw, maximum=1e15):
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw) or not 0 < raw <= maximum:
        raise ValueError("Invalid positive value.")
    return float(raw)


def _candidate(symbol, snapshot, name, now, session):
    """Return a validated row plus exclusion reason; never borrow yesterday."""
    if not isinstance(snapshot, dict):
        return None, "invalid"
    try:
        trade, daily, previous = (snapshot.get(key) for key in ("latestTrade", "dailyBar", "prevDailyBar"))
        if not all(isinstance(value, dict) for value in (trade, daily, previous)):
            return None, "missing"
        trade_at, volume_at, previous_at = (live._stamp(raw) for raw in (trade.get("t"), daily.get("t"), previous.get("t")))
        today = now.astimezone(live._NY).date().isoformat()
        if (session["date"] != today or trade_at.astimezone(live._NY).date().isoformat() != today
                or volume_at.astimezone(live._NY).date().isoformat() != today
                or previous_at.astimezone(live._NY).date().isoformat() != session["previous_date"]):
            return None, "stale"
        if trade_at > now or volume_at > now:
            return None, "invalid"
        price, previous_close = _positive(trade.get("p")), _positive(previous.get("c"))
        volume = daily.get("v")
        if isinstance(volume, bool) or not isinstance(volume, (int, float)) or not math.isfinite(volume) or not 0 <= volume <= 1e15 or int(volume) != volume:
            return None, "invalid"
        age = max(0, (now - trade_at).total_seconds())
        quote = snapshot.get("latestQuote") or {}
        minute = snapshot.get("minuteBar") or {}
        quote_at = _stamp_or_none(quote.get("t")) if isinstance(quote, dict) else None
        minute_at = _stamp_or_none(minute.get("t")) if isinstance(minute, dict) else None
        return {"symbol": symbol, "name": name, "price": price,
                "change_pct": (price / previous_close - 1) * 100, "day_volume": int(volume),
                "trade_at": trade_at.isoformat(), "quote_at": quote_at.isoformat() if quote_at else None,
                "minute_at": minute_at.isoformat() if minute_at else None, "volume_at": volume_at.isoformat(),
                "volume_received_at": snapshot.get("_received_at"),
                "age_seconds": round(age, 1), "freshness": "fresh" if age <= 300 else "stale"}, None
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return None, "invalid"


def discover(payload, progress=None, stop_event=None):
    config = validate_discovery(payload)
    _report(progress, "Preparing intraday discovery…", stop_event)
    checked_at = live._now()
    now = checked_at
    warnings = []
    if config["source"] == "demo":
        if config["universe"] == "all":
            raise ValueError("The all-listings discovery universe requires Alpaca. Choose the synthetic starter or custom symbols for demo.")
        requested = config["symbols"] if config["universe"] == "custom" else _DEMO_SYMBOLS
        # Generate bounded chunks; the simulation uses the same explicitly
        # historical session as the live monitor, never today's real prices.
        snapshots, metadata = {}, {}
        for offset in range(0, len(requested), 20):
            bundle = demo_bundle(requested[offset:offset + 20], step=10)
            for asset in bundle["assets"]:
                snapshot = asset["snapshot"]
                snapshot["prevDailyBar"]["t"] = bundle["session"]["previous_date"] + "T13:30:00+00:00"
                snapshot["minuteBar"] = dict(asset["minutes"][-1])
                snapshot["_received_at"] = checked_at.isoformat()
                snapshots[asset["symbol"]] = snapshot
                metadata[asset["symbol"]] = {"name": asset["name"]}
        session = bundle["session"]
        now = live._stamp(bundle["as_of"])
        feed, label = "synthetic", "Synthetic momentum lab"
        warnings.extend(bundle["warnings"])
    else:
        status, headers, account_url = live._credentials()
        feed = status["feed"]
        _report(progress, "Checking today's exchange calendar…", stop_event)
        session, unused_days = _calendar(now, headers, account_url, stop_event)
        requested, metadata, label, listing_warnings = _universe(config, headers, account_url, progress, stop_event)
        warnings.extend(listing_warnings)
        snapshots = {}
        for offset in range(0, len(requested), providers.BATCH_SIZE):
            batch = requested[offset:offset + providers.BATCH_SIZE]
            _report(progress, "Loading snapshots {}–{} of {}…".format(offset + 1, offset + len(batch), len(requested)), stop_event)
            response = live._get_json("https://data.alpaca.markets/v2/stocks/snapshots", {
                "symbols": ",".join(batch), "feed": feed}, headers, stop_event)
            if not isinstance(response, dict) or any(symbol not in batch for symbol in response):
                raise ValueError("Alpaca returned invalid discovery snapshots; no partial result was used.")
            received_at = live._now().isoformat()
            response = {symbol: dict(value, _received_at=received_at) if isinstance(value, dict) else value
                        for symbol, value in response.items()}
            snapshots.update(response)
        now = live._now()
        if now.astimezone(live._NY).date() != checked_at.astimezone(live._NY).date():
            raise ValueError("The New York date changed during discovery. Refresh to scan one consistent session.")
    phase = _phase(session, now)
    if feed == "iex":
        warnings.append("IEX covers one exchange; prices and share volume are not consolidated US market data.")
    if phase == "closed":
        warnings.append("There is no exchange session today. Previous-session snapshots are excluded from current-session candidates.")
    warnings.append("Change is latest trade versus the raw previous-session close; corporate actions such as splits can distort it. Day volume is the provider's current daily aggregate and can include extended hours; its timestamp identifies the aggregate day, not the last update. Refresh is manual.")
    coverage = {"requested": len(requested), "received": len(snapshots), "current_session": 0,
                "matched": 0, "returned": 0, "missing": 0, "stale": 0, "invalid": 0}
    rows = []
    for symbol in requested:
        if symbol not in snapshots:
            coverage["missing"] += 1
            continue
        row, reason = _candidate(symbol, snapshots[symbol], metadata[symbol]["name"], now, session)
        if reason:
            coverage[reason] += 1
            continue
        coverage["current_session"] += 1
        if row["freshness"] == "stale":
            coverage["stale"] += 1
            # Explicit stale prices may be inspected during closed hours; while
            # a session is active, they cannot enter the candidate shortlist.
            if phase == "regular":
                continue
        if (config["min_price"] <= row["price"] <= config["max_price"]
                and row["day_volume"] >= config["min_day_volume"]
                and row["change_pct"] >= config["min_change_pct"]):
            rows.append(row)
    rows.sort(key=lambda row: (-row["change_pct"], -row["day_volume"], row["symbol"]))
    coverage.update(matched=len(rows), returned=min(len(rows), config["limit"]))
    if coverage["stale"]:
        warnings.append("Stale or previous-session data was found for {} symbols. Trades older than five minutes are excluded during regular hours; outside regular hours retained current-day rows are labeled stale.".format(coverage["stale"]))
    live._check_stop(stop_event)
    return {"source": config["source"], "feed": feed, "as_of": checked_at.isoformat(),
            "completed_at": live._now().isoformat(), "market_as_of": now.isoformat(),
            "session_date": now.astimezone(live._NY).date().isoformat(), "latest_session_date": session["date"],
            "market_phase": "synthetic" if feed == "synthetic" else phase,
            "universe": config["universe"], "universe_label": label, "coverage": coverage,
            "rows": rows[:config["limit"]], "warnings": warnings, "filters": config}


def _safe_failure(error):
    # ProviderError originates in the fixed-host transport with hardcoded,
    # sanitized messages. Never echo arbitrary network exceptions or payloads.
    if isinstance(error, providers.ProviderError):
        return str(error)
    return "Check failed. Check network connectivity, feed access, and provider response validity."


def diagnose(config, snapshot, progress=None, stop_event=None, snapshot_provider=None):
    """Test actual read access and required subscriptions without a second live socket."""
    if not isinstance(config, dict) or not isinstance(snapshot, dict):
        raise ValueError("Diagnostics require monitor configuration and a snapshot.")
    symbols = live._symbols(config.get("symbols", ["AAPL"]))
    source = config.get("source", "demo")
    if source not in ("demo", "alpaca"):
        raise ValueError("Diagnostic source must be demo or alpaca.")
    now = live._now()
    result = {"checked_at": now.isoformat(), "source": source, "feed": "synthetic" if source == "demo" else providers.provider_status()["feed"],
              "checks": [], "symbols": [], "session": None, "warnings": []}

    def check(name, status, message):
        result["checks"].append({"name": name, "status": status, "message": message})

    if source == "demo":
        check("Source", "warning", "Synthetic historical simulation. No provider connectivity or entitlement was tested.")
        bundle = demo_bundle(symbols)
        result["session"] = bundle["session"]
        result["symbols"] = [{"symbol": asset["symbol"], "trade_at": asset["snapshot"]["latestTrade"]["t"],
                              "quote_at": asset["snapshot"]["latestQuote"]["t"], "minute_at": asset["minutes"][-1]["t"],
                              "history_sessions": len(asset["bars"]), "missing_history": False, "issues": []}
                             for asset in bundle["assets"]]
        for name in ("Authentication", "Feed access", "Stream subscriptions", "Trading status"):
            check(name, "skipped", "Select Alpaca to test real market data access.")
        return result
    _report(progress, "Checking provider configuration…", stop_event)
    try:
        status, headers, account_url = live._credentials()
    except ValueError as error:
        # _credentials validates only locally generated settings messages.
        check("Configuration", "fail", str(error))
        for name in ("Authentication", "Exchange calendar", "Feed access", "History", "Stream subscriptions"):
            check(name, "skipped", "Provider configuration must be corrected first.")
        return result
    check("Configuration", "pass", "Credentials are present; actual provider access is tested below.")
    session, calendar_days = None, None
    _report(progress, "Testing authentication and exchange calendar access…", stop_event)
    try:
        session, calendar_days = _calendar(now, headers, account_url, stop_event)
        result["session"] = session
        check("Authentication", "pass", "Authenticated GET to the exchange calendar succeeded.")
        check("Exchange calendar", "pass", "Latest session {} ({}).".format(session["date"], _phase(session, now)))
    except live._Cancelled:
        raise
    except Exception as error:
        check("Authentication / exchange calendar", "fail", _safe_failure(error))
    snapshots = {}
    _report(progress, "Testing the configured real-time snapshot feed…", stop_event)
    try:
        snapshots = live._get_json("https://data.alpaca.markets/v2/stocks/snapshots", {
            "symbols": ",".join(symbols), "feed": status["feed"]}, headers, stop_event)
        if not isinstance(snapshots, dict) or any(symbol not in symbols for symbol in snapshots):
            raise ValueError("Invalid snapshots.")
        check("Feed access", "pass", "Authenticated {} snapshot request succeeded for {} of {} symbols.".format(status["feed"].upper(), len(snapshots), len(symbols)))
    except live._Cancelled:
        raise
    except Exception as error:
        snapshots = {}
        check("Feed access", "fail", _safe_failure(error))
    daily, minutes = {}, {}
    if session:
        _report(progress, "Checking prior sessions and completed minute history…", stop_event)
        try:
            daily = live._history(symbols, session, calendar_days, now, status["feed"], headers, stop_event, "1Day")
            check("Daily history", "pass", "Split-adjusted prior-session bars loaded; per-symbol coverage appears below.")
        except live._Cancelled:
            raise
        except Exception as error:
            check("Daily history", "fail", _safe_failure(error))
        try:
            minutes = live._history(symbols, session, calendar_days, now, status["feed"], headers, stop_event, "1Min")
            check("Minute history", "pass", "Completed regular-session minute history request succeeded.")
        except live._Cancelled:
            raise
        except Exception as error:
            check("Minute history", "fail", _safe_failure(error))
    else:
        check("History", "skipped", "A valid exchange calendar is required before requesting session history.")
    now = live._now()
    for symbol in symbols:
        raw = snapshots.get(symbol) or {}
        issues = []
        stamps = {}
        for key, field in (("latestTrade", "trade_at"), ("latestQuote", "quote_at")):
            value = raw.get(key) if isinstance(raw, dict) else None
            stamp = _stamp_or_none(value.get("t")) if isinstance(value, dict) else None
            stamps[field] = stamp.isoformat() if stamp else None
            if stamp is None:
                issues.append("Missing {} timestamp.".format(key))
            elif stamp > now:
                issues.append("{} timestamp is in the future.".format(key))
            elif (now - stamp).total_seconds() > 30:
                issues.append("{} is older than the 30-second alert limit{}.".format(key, " (market is outside regular hours)" if session and _phase(session, now) != "regular" else ""))
        trade = raw.get("latestTrade") or {} if isinstance(raw, dict) else {}
        quote = raw.get("latestQuote") or {} if isinstance(raw, dict) else {}
        if not isinstance(trade, dict) or not metrics._number(trade.get("p"), .000001, 1e9):
            issues.append("Trade price is missing or invalid.")
        if (not isinstance(quote, dict) or not metrics._number(quote.get("bp"), .000001, 1e9)
                or not metrics._number(quote.get("ap"), .000001, 1e9) or quote["ap"] < quote["bp"]):
            issues.append("A valid two-sided quote is missing.")
        normalized_daily = metrics._daily(daily.get(symbol, []), metrics._date(session["date"]) if session else None)
        count = len(normalized_daily)
        prior_dates = session.get("prior_dates", []) if session else []
        missing_dates = sorted(set(prior_dates) - {bar["date"] for bar in normalized_daily})
        normalized_minutes, invalid_minutes = metrics._minutes(minutes.get(symbol, []),
            metrics._time(session["open"]) if session else None,
            metrics._time(session["close"]) if session else None, now)
        minute_rows = normalized_minutes
        missing = count < 30 or len(prior_dates) != 30 or bool(missing_dates)
        minute_gaps = None
        if count < 30:
            issues.append("Only {} prior sessions; 30 are required for the volume baseline.".format(count))
        if len(prior_dates) != 30:
            issues.append("The exchange calendar did not establish all 30 prior baseline sessions.")
        if missing_dates:
            issues.append("Missing baseline sessions: {}.".format(", ".join(missing_dates)))
        if normalized_daily and not sum(bar["volume"] for bar in normalized_daily if bar["date"] in prior_dates):
            issues.append("The prior-session volume baseline is not positive.")
        if invalid_minutes:
            missing = True
            issues.append("Minute history contains malformed bars.")
        if any(bar["vwap"] is None and bar["volume"] > 0 for bar in minute_rows):
            issues.append("Minute VWAP is missing or invalid for one or more bars; session VWAP is unavailable.")
        if session and now > live._stamp(session["open"]) + timedelta(minutes=1) and not minute_rows:
            missing = True
            issues.append("No completed regular-session minute bars were returned.")
        if session:
            end = min(now.replace(second=0, microsecond=0), live._stamp(session["close"]))
            opening = live._stamp(session["open"])
            expected = max(0, int((end - opening).total_seconds() // 60))
            expected_times = {opening + timedelta(minutes=index) for index in range(expected)}
            minute_gaps = len(expected_times - {bar["t"] for bar in minute_rows})
            if minute_gaps and minute_rows:
                missing = True
                issues.append("{} regular-session minute slots have no bar; this can reflect no trades or missing data.".format(minute_gaps))
        if len(minute_rows) < 21 or any(right["t"] - left["t"] != timedelta(minutes=1) for left, right in zip(minute_rows[-21:-1], minute_rows[-20:])):
            issues.append("Twenty-one contiguous completed regular-session minutes are not available yet.")
        if minute_rows and (now - minute_rows[-1]["t"] - timedelta(minutes=1)).total_seconds() > 120:
            issues.append("Completed minute volume is older than the 120-second alert limit.")
        result["symbols"].append(dict({"symbol": symbol, "minute_at": minute_rows[-1]["t"].isoformat() if minute_rows else None,
                                       "history_sessions": count, "minute_count": len(minute_rows), "missing_history": missing,
                                       "missing_history_dates": missing_dates, "minute_gaps": minute_gaps, "issues": issues}, **stamps))
    if any(row["issues"] for row in result["symbols"]):
        check("Data quality", "warning", "Some symbols have stale, missing, or insufficient history; inspect their timestamps and coverage below.")
    else:
        check("Data quality", "pass", "All requested symbols have recent trade/quote timestamps and baseline history.")
    if snapshot_provider:
        refreshed = snapshot_provider()
        if isinstance(refreshed, dict):
            snapshot = refreshed
    monitor = snapshot.get("status") or {}
    channels = monitor.get("channel_subscriptions") or {}
    if monitor.get("running") and monitor.get("source") == "alpaca":
        running_config = snapshot.get("config") or {}
        same_selection = (running_config.get("source") == source
                          and set(running_config.get("symbols", [])) == set(symbols)
                          and monitor.get("feed") == status["feed"])
        if monitor.get("connection") == "live" and same_selection:
            check("Stream subscriptions", "pass", "The running monitor already authenticated and confirmed required price subscriptions. No second connection was opened.")
        else:
            check("Stream subscriptions", "warning", "The monitor is running but required subscriptions for this exact symbol selection and feed are not currently confirmed. No second connection was opened.")
        supported = channels.get("statuses") is True and monitor.get("connection") == "live" and same_selection
        check("Trading status", "pass" if supported else "warning", "Trading-status channel subscription confirmed. Current status remains unknown until a dated status event arrives." if supported else "Trading-status channel access is not currently confirmed; halt detection is unavailable or incomplete.")
        result["channel_subscriptions"] = channels
    else:
        _report(progress, "Testing a bounded authenticated price-stream subscription…", stop_event)
        stream_stop = threading.Event()
        confirmed = []
        timer = threading.Timer(15, stream_stop.set)
        timer.daemon = True
        timer.start()

        def on_status(value):
            if value == "live":
                confirmed.append(True)
                stream_stop.set()

        def on_event(event):
            if stop_event and stop_event.is_set():
                stream_stop.set()

        try:
            live.stream_live(symbols, on_event, stream_stop, on_status)
            check("Stream subscriptions", "pass" if confirmed else "fail", "Authentication and all required price channels were confirmed; test connection closed." if confirmed else "The stream test ended before required subscriptions were confirmed.")
        except Exception as error:
            # stream_live owns hardcoded errors; still redact arbitrary failures.
            check("Stream subscriptions", "fail", "Stream authentication/subscription test failed. Check feed entitlement, network access, and whether another application holds the feed's connection limit.")
        finally:
            stream_stop.set()
            timer.cancel()
        check("Trading status", "skipped", "Start monitoring to check optional status and price-band channel entitlements. The connection test closes after required price subscriptions are confirmed.")
    if status["feed"] == "iex":
        result["warnings"].append("IEX prices and volumes cover one exchange, not consolidated US trading.")
    result["warnings"].append("Read-only connectivity checks do not establish complete market coverage or guarantee halt detection.")
    live._check_stop(stop_event)
    return result
