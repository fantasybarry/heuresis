"""Pure, explainable intraday momentum metrics; no order execution or forecasts.

Volume is built from completed regular-session minute bars. Daily relative
volume deliberately uses a full-session denominator, while minute RVOL uses
the preceding twenty minutes. These are different measures, not forecasts.
"""

import math
import re
from datetime import date, datetime, time as daytime, timedelta, timezone
from zoneinfo import ZoneInfo

from .engine import _ema, _number, _rsi
from .planning_data import _iso, _time, capture_planning_quote
from .screening_metrics import history_metrics, rank_rows


MAX_MONITOR_SYMBOLS = 50

DEFAULT_MONITOR_CONFIG = {
    "source": "demo", "symbols": ["DEMO", "MOMO", "GAP"],
    "min_price": 0.5, "max_price": 5, "min_session_volume": 100000,
    "buy_score": 65, "strong_buy_score": 85, "confirmation_bars": 2,
    "cooldown_seconds": 300, "alerts_enabled": True,
}
_SYMBOL = re.compile(r"[A-Z][A-Z0-9]{0,9}(?:[.\-][A-Z0-9]{1,4})?\Z")
_BOUNDS = {
    "min_price": (0.000001, 1000000), "max_price": (0.000001, 1000000),
    "min_session_volume": (0, 1000000000000), "buy_score": (0, 100),
    "strong_buy_score": (0, 100), "confirmation_bars": (1, 5),
    "cooldown_seconds": (30, 3600),
}
# Former alert gates; saved configurations that still carry them load without them.
_RETIRED_SETTINGS = ("min_relative_volume", "max_spread_pct")
# Minute RVOL still earns the "Minute participation" score points at the former default.
_PARTICIPATION_RVOL = 1.5
_UTC = timezone.utc
_NY = ZoneInfo("America/New_York")
_MINUTE = timedelta(minutes=1)
# Exchange timestamps can run slightly ahead of a lagging local clock; a strict check drops the newest trades.
_CLOCK_SKEW = timedelta(seconds=2)


def validate_monitor_config(payload, current=None):
    """Return a fresh validated configuration; never coerce numeric strings."""
    if not isinstance(payload, dict) or (current is not None and not isinstance(current, dict)):
        raise ValueError("Monitor configuration must be an object.")
    result = dict(DEFAULT_MONITOR_CONFIG)
    for item in (current or {}, payload):
        item = {key: value for key, value in item.items() if key not in _RETIRED_SETTINGS}
        unknown = set(item) - set(DEFAULT_MONITOR_CONFIG)
        if unknown:
            raise ValueError("Unknown monitor setting: {}.".format(", ".join(sorted(map(str, unknown)))))
        result.update(item)
    if result["source"] not in ("demo", "alpaca"):
        raise ValueError("Monitor source must be demo or alpaca.")
    if not isinstance(result["alerts_enabled"], bool):
        raise ValueError("alerts_enabled must be true or false.")
    for key, (minimum, maximum) in _BOUNDS.items():
        if not _number(result[key], minimum, maximum):
            raise ValueError("{} must be a finite number between {} and {}.".format(key, minimum, maximum))
    for key in ("confirmation_bars", "cooldown_seconds"):
        if not isinstance(result[key], int) or isinstance(result[key], bool):
            raise ValueError("{} must be an integer.".format(key))
    if result["min_price"] > result["max_price"]:
        raise ValueError("min_price cannot exceed max_price.")
    if result["buy_score"] >= result["strong_buy_score"]:
        raise ValueError("buy_score must be below strong_buy_score.")
    symbols = result["symbols"]
    if not isinstance(symbols, list) or not 1 <= len(symbols) <= MAX_MONITOR_SYMBOLS:
        raise ValueError("symbols must be a list of 1 to {} ticker symbols.".format(MAX_MONITOR_SYMBOLS))
    normalized = []
    for symbol in symbols:
        if not isinstance(symbol, str) or not _SYMBOL.fullmatch(symbol.strip().upper()):
            raise ValueError("Tickers must start with a letter, use at most ten letters/numbers, and optionally end with a dot/hyphen and up to four letters/numbers.")
        symbol = symbol.strip().upper()
        if symbol not in normalized:
            normalized.append(symbol)
    result["symbols"] = normalized
    return result


def _date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _ohlcv(raw):
    if not isinstance(raw, dict):
        return None
    values = {key: raw.get(key) for key in ("open", "high", "low", "close", "volume")}
    for key, value in values.items():
        if not _number(value, 0 if key == "volume" else 0.000001,
                       1000000000000 if key == "volume" else 1000000000):
            return None
    if values["low"] > min(values["open"], values["close"]) or values["high"] < max(values["open"], values["close"]):
        return None
    return values


def _minutes(raw, session_open, session_close, now):
    """Normalize ordering; a repeated timestamp is a replacement, never a sum."""
    result, invalid = {}, False
    if not isinstance(raw, list) or session_open is None or session_close is None:
        return [], False
    for item in raw:
        if not isinstance(item, dict):
            invalid = True
            continue
        start = _time(item.get("t"))
        if start is None:
            invalid = True
            continue
        if start < session_open or start + _MINUTE > min(now, session_close):
            continue
        values = _ohlcv(item)
        if values is None or start.second or start.microsecond:
            invalid = True
            continue
        values["t"] = start
        values["vwap"] = item.get("vwap") if _number(item.get("vwap"), 0.000001, 1000000000) else None
        result[start] = values
    return [result[key] for key in sorted(result)], invalid


def _daily(raw, session_date):
    result = {}
    if not isinstance(raw, list) or session_date is None:
        return []
    for item in raw:
        if not isinstance(item, dict):
            continue
        session = _date(item.get("date"))
        values = _ohlcv(item)
        if session is not None and session < session_date and values is not None:
            values["date"] = session.isoformat()
            result[session] = values
    return [result[key] for key in sorted(result)]


def _pct(value, reference):
    return (value / reference - 1) * 100 if value is not None and reference else None


def _fresh(stamp, now, seconds):
    return stamp is not None and -_CLOCK_SKEW.total_seconds() <= (now - stamp).total_seconds() <= seconds


def build_rows(bundle, config, now=None):
    """Build finite/null display data and conservatively guarded setup labels.

The service owns confirmation and notification deduplication. This function
must never make a fresh trade or quote change the completed-bar setup score.
"""
    config = validate_monitor_config(config)
    now = _time(now) if now is not None else datetime.now(_UTC)
    if now is None:
        raise ValueError("now must be a timezone-aware datetime.")
    if not isinstance(bundle, dict):
        raise ValueError("Market data bundle must be an object.")
    session = bundle.get("session") or {}
    session_date = _date(session.get("date"))
    previous_date = _date(session.get("previous_date"))
    session_open, session_close = _time(session.get("open")), _time(session.get("close"))
    valid_session = (session_date is not None and previous_date is not None
                     and previous_date < session_date and session_open is not None
                     and session_close is not None and session_open < session_close)
    market_open = bool(valid_session and session_open <= now < session_close)
    prior_dates = session.get("prior_dates")
    valid_calendar_history = (
        isinstance(prior_dates, list) and len(prior_dates) == 30
        and all(_date(day) is not None for day in prior_dates)
        and len(set(prior_dates)) == 30 and prior_dates == sorted(prior_dates)
        and session_date is not None and all(_date(day) < session_date for day in prior_dates)
        and previous_date is not None and prior_dates[-1] == previous_date.isoformat())
    source, feed = bundle.get("source"), bundle.get("feed")
    rows = []
    assets = bundle.get("assets", [])
    if not isinstance(assets, list):
        return rows
    seen = set()
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        symbol = asset.get("symbol")
        if symbol not in config["symbols"] or symbol in seen:
            continue
        seen.add(symbol)
        blockers, warnings = [], []
        minutes, invalid_minutes = _minutes(asset.get("minutes"), session_open, session_close, now)
        daily = _daily(asset.get("bars"), session_date)
        screening = history_metrics(asset.get("bars", []), bundle.get("benchmark_bars", []),
                                    session.get("date"), previous_session_date=session.get("previous_date"))
        history = ([bar for bar in daily if bar["date"] in prior_dates]
                   if valid_calendar_history else daily[-30:])
        full_history = valid_calendar_history and len(history) == 30
        total_30d = math.fsum(bar["volume"] for bar in history) if full_history else None
        average_30d = total_30d / 30 if total_30d is not None else None
        prior_bar = next((bar for bar in reversed(daily) if bar["date"] == str(previous_date)), None)
        prior_close = prior_bar["close"] if prior_bar else None
        last = minutes[-1] if minutes else None
        volume_at = last["t"] + _MINUTE if last else None
        has_opening = bool(minutes) and minutes[0]["t"] == session_open
        # A missing minute has no trades (often a trading halt), so totals and VWAP from the
        # minutes received stay exact; only a missing opening minute or a malformed bar withholds them.
        complete_coverage = has_opening and not invalid_minutes
        gap_minutes = sum(int((current["t"] - previous["t"]) / _MINUTE) - 1
                          for previous, current in zip(minutes, minutes[1:]))
        session_volume = math.fsum(bar["volume"] for bar in minutes) if complete_coverage else None
        relative_volume = session_volume / average_30d if session_volume is not None and average_30d else None
        contiguous = len(minutes) >= 21 and all(
            current["t"] - previous["t"] == _MINUTE
            for previous, current in zip(minutes[-21:-1], minutes[-20:]))
        minute_baseline = math.fsum(bar["volume"] for bar in minutes[-21:-1]) / 20 if len(minutes) >= 21 else None
        minute_rvol = last["volume"] / minute_baseline if contiguous and minute_baseline else None
        snapshot = asset.get("snapshot") if isinstance(asset.get("snapshot"), dict) else {}
        # VWAP starts at the 4 a.m. pre-market open, so completed pre-market minutes count before the regular ones.
        # Without loaded pre-market minutes (an empty list means no trades) VWAP stays unavailable.
        extended = snapshot.get("_extended_day") if isinstance(snapshot.get("_extended_day"), dict) else {}
        premarket, invalid_premarket = (_minutes(extended["minutes"], datetime.combine(session_date, daytime(4), _NY), session_open, now)
                                        if isinstance(extended.get("minutes"), list) and session_date else ([], True))
        premarket_ok = not invalid_premarket and all(bar["vwap"] is not None for bar in premarket if bar["volume"] > 0)
        premarket_volume = math.fsum(bar["volume"] for bar in premarket)
        premarket_value = math.fsum(bar["vwap"] * bar["volume"] for bar in premarket if bar["volume"] > 0) if premarket_ok else 0
        vwap_complete = premarket_ok and complete_coverage and all(bar["vwap"] is not None for bar in minutes if bar["volume"] > 0)
        vwap_volume = session_volume + premarket_volume if session_volume is not None else None
        vwap = (premarket_value + math.fsum(bar["vwap"] * bar["volume"] for bar in minutes if bar["volume"] > 0)) / vwap_volume if vwap_volume and vwap_complete else None
        closes = [bar["close"] for bar in minutes]
        ema9_series = _ema(closes, 9) if len(closes) >= 9 else []
        ema9 = ema9_series[-1] if ema9_series else None
        ema20_series = _ema(closes, 20) if len(closes) >= 20 else []
        ema20 = ema20_series[-1] if ema20_series else None
        rsi = _rsi(closes) if len(closes) >= 15 else None
        raw_status = snapshot.get("tradingStatus") or {}
        status_at = _time(raw_status.get("t")) if isinstance(raw_status, dict) else None
        status_code = str(raw_status.get("sc", "")) if isinstance(raw_status, dict) else ""
        halt_codes = {"2", "F", "H", "Q", "P"}
        known_status = bool(status_at and status_at <= now + _CLOCK_SKEW and status_at.astimezone(_NY).date() == session_date
                            and status_code in halt_codes | {"3", "T"})
        trading_status = {"available": known_status, "code": status_code if known_status else None,
                          "reason": (raw_status.get("rm") or raw_status.get("sm")) if known_status else "Trading status unavailable; no current-session status event has been received.",
                          "at": _iso(status_at) if known_status else None,
                          "halted": status_code in halt_codes if known_status else None}
        raw_bands = snapshot.get("priceBands") or {}
        bands_at = _time(raw_bands.get("t")) if isinstance(raw_bands, dict) else None
        valid_bands = bool(bands_at and bands_at <= now + _CLOCK_SKEW and bands_at.astimezone(_NY).date() == session_date
                           and _number(raw_bands.get("u"), 0.000001, 1e9) and _number(raw_bands.get("d"), 0.000001, 1e9)
                           and raw_bands["d"] <= raw_bands["u"])
        price_bands = {"available": valid_bands, "upper": raw_bands["u"] if valid_bands else None,
                       "lower": raw_bands["d"] if valid_bands else None, "at": _iso(bands_at) if valid_bands else None}
        provider_daily = snapshot.get("dailyBar") if isinstance(snapshot.get("dailyBar"), dict) else {}
        provider_daily_time = _time(provider_daily.get("t"))
        valid_daily_volume = (provider_daily_time is not None and provider_daily_time <= now
                              and provider_daily_time.astimezone(_NY).date() == session_date
                              and _number(provider_daily.get("v"), 0, 1000000000000))
        day_volume = provider_daily["v"] if valid_daily_volume else None
        day_volume_at = _time(snapshot.get("_daily_received_at") or snapshot.get("_received_at"))
        if not valid_daily_volume or day_volume_at is None or day_volume_at > now:
            day_volume_at = None
        day_volume_basis = "Provider total day volume including extended hours"
        if not valid_daily_volume:
            extended = snapshot.get("_extended_day") or {}
            extended_as_of = _time(extended.get("as_of")) if isinstance(extended, dict) else None
            if (extended_as_of and extended_as_of <= now and extended_as_of.astimezone(_NY).date() == session_date
                    and _number(extended.get("volume"), 0, 1000000000000)):
                day_volume = extended["volume"]
                day_volume_at = _time(extended.get("received_at"))
                if not _fresh(extended_as_of, now, 120) or day_volume_at is None or day_volume_at > now:
                    day_volume_at = None
                day_volume_basis = "Completed extended-hours minute bars since 04:00 New York"
                warnings.append("Premarket total uses completed extended-hours minute bars. Some volume-only trades are excluded from these bars, so this may understate total trading until provider daily volume is available.")
        day_volume_fresh = day_volume is not None and _fresh(day_volume_at, now, 120)
        day_relative_volume = day_volume / screening["avg_daily_volume"] if day_volume_fresh and screening["avg_daily_volume"] else None
        trade = snapshot.get("latestTrade") if isinstance(snapshot.get("latestTrade"), dict) else {}
        quote = snapshot.get("latestQuote") if isinstance(snapshot.get("latestQuote"), dict) else {}
        trade_at, quote_at = _time(trade.get("t")), _time(quote.get("t"))
        valid_trade = trade_at is not None and trade_at <= now + _CLOCK_SKEW and _number(trade.get("p"), 0.000001, 1000000000)
        price = trade["p"] if valid_trade else last["close"] if last else None
        price_at = trade_at if valid_trade else volume_at
        valid_quote = (quote_at is not None and quote_at <= now + _CLOCK_SKEW
                       and _number(quote.get("bp"), 0.000001, 1000000000)
                       and _number(quote.get("ap"), 0.000001, 1000000000)
                       and quote["ap"] >= quote["bp"])
        spread = (quote["ap"] - quote["bp"]) / ((quote["ap"] + quote["bp"]) / 2) * 100 if valid_quote else None
        opening = minutes[0]["open"] if minutes and minutes[0]["t"] == session_open else None
        gap = _pct(opening, prior_close)
        change = _pct(price, prior_close)
        technical_close = last["close"] if last else None
        technical_change = _pct(technical_close, prior_close)
        float_info = asset.get("float") if isinstance(asset.get("float"), dict) else {}
        float_date = _date(float_info.get("as_of"))
        shares = float_info.get("shares")
        valid_float = (_number(shares, 1, 10000000000000) and int(shares) == shares
                       and float_date is not None and float_date <= now.date()
                       and float_info.get("source") in ("FMP", "Manual", "Synthetic"))
        if valid_float and ((source == "demo") != (float_info["source"] == "Synthetic")):
            valid_float = False
        if not valid_float:
            shares = None
            warnings.append("Float unavailable: a dated, sourced float share count is required; outstanding shares are not float.")
        elif float_info["source"] == "Manual":
            warnings.append("Float is a dated manual entry, not provider verified.")
        raw_previous = snapshot.get("prevDailyBar") or {}
        raw_previous_close = raw_previous.get("c") if isinstance(raw_previous, dict) else None
        if prior_close and _number(raw_previous_close, 0.000001, 1000000000) and abs(raw_previous_close / prior_close - 1) > 0.2:
            warnings.append("Possible corporate action: raw previous close differs from the split-adjusted reference by more than 20%; verify the issuer's split history.")
        if source == "demo":
            warnings.append("Synthetic historical simulation; prices, volume and float are invented.")
        elif feed == "iex":
            warnings.append("IEX volume covers one exchange, not consolidated market volume.")
        if not known_status:
            warnings.append(trading_status["reason"])
        if trading_status["halted"]:
            blockers.append("Trading is halted, paused, or awaiting full trading resumption according to the current-session status event.")
        warnings.append("Company news is not evaluated by this technical setup score.")
        if not valid_session:
            blockers.append("A valid exchange session and previous session are required.")
        if not market_open:
            blockers.append("Regular market session is closed.")
        if source not in ("demo", "alpaca") or (source == "demo" and feed != "synthetic") or (source == "alpaca" and feed not in ("iex", "sip")):
            blockers.append("An identified real-time feed or explicit synthetic simulation is required.")
        fresh_trade = valid_trade and _fresh(trade_at, now, 30)
        fresh_quote = valid_quote and _fresh(quote_at, now, 30)
        fresh_volume = _fresh(volume_at, now, 120)
        stale = not (fresh_trade and fresh_quote and fresh_volume)
        if not fresh_trade:
            blockers.append("A valid trade from the past 30 seconds is required.")
        if not fresh_quote:
            blockers.append("A valid two-sided quote from the past 30 seconds is required.")
        if not fresh_volume:
            blockers.append("Completed minute volume is missing or more than 120 seconds old.")
        if invalid_minutes:
            blockers.append("Malformed regular-session minute bars were excluded; volume history may be incomplete.")
        if gap_minutes:
            warnings.append("{} regular-session minute(s) had no bars (no trades or a trading halt); session volume and VWAP use the minutes received.".format(gap_minutes))
        # Recent listings can alert; no alert condition uses the 30-session baseline.
        if not valid_calendar_history:
            blockers.append("The exchange calendar of prior sessions is unavailable or invalid.")
        elif not full_history:
            warnings.append("Fewer than thirty prior completed daily sessions (often a recent listing); the 30-session volume baseline and session RVOL are unavailable.")
        elif not average_30d:
            blockers.append("The prior 30-session average volume must be positive.")
        if prior_close is None:
            blockers.append("The split-adjusted previous-session close is unavailable.")
        if opening is None:
            warnings.append("Gap unavailable: the exact regular-session opening minute has not been received.")
            blockers.append("The regular-session opening minute is missing; session VWAP and volume may be incomplete.")
        if not contiguous:
            blockers.append("Twenty-one contiguous completed regular-session minutes are required.")
        # The volume minimum counts regular-session trading only; premarket volume is excluded.
        # Summing the minute bars present is a lower bound, so a gap cannot let a symbol pass falsely.
        regular_volume = math.fsum(bar["volume"] for bar in minutes) if minutes else None
        if regular_volume is None or regular_volume < config["min_session_volume"]:
            blockers.append("Regular-session volume is below the configured minimum or unavailable; premarket volume is excluded.")
        if price is None or not config["min_price"] <= price <= config["max_price"]:
            blockers.append("Latest price is outside the configured range or unavailable.")
        if technical_close is None or not config["min_price"] <= technical_close <= config["max_price"]:
            blockers.append("Completed minute close is outside the configured price range or unavailable.")
        if vwap is None:
            blockers.append("Session VWAP requires actual VWAP values for every positive-volume minute since the 4 a.m. pre-market open.")
        above_vwap = vwap is not None and technical_close is not None and technical_close > vwap
        ema_trend = ema9 is not None and ema20 is not None and ema9 > ema20
        rising = len(ema9_series) >= 2 and ema9_series[-2] is not None and ema9 > ema9_series[-2]
        rsi_ok = rsi is not None and 50 <= rsi <= 75
        volume_ok = minute_rvol is not None and minute_rvol >= _PARTICIPATION_RVOL
        breakout = len(minutes) >= 6 and technical_close > max(bar["high"] for bar in minutes[-6:-1])
        positive = technical_change is not None and technical_change > 0
        conditions = [
            ("Above session VWAP", above_vwap, 20, "Completed minute close is above session VWAP, which includes pre-market trading from 4 a.m."),
            ("EMA trend", ema_trend, 20, "Nine-minute EMA is above the twenty-minute EMA."),
            ("Rising EMA", rising, 10, "Nine-minute EMA rose from the preceding completed minute."),
            ("RSI momentum", rsi_ok, 15, "Fourteen-minute Wilder RSI is between 50 and 75 inclusive."),
            ("Minute participation", volume_ok, 15, "Latest completed minute volume / preceding twenty-minute average is at least 1.5×."),
            ("Five-minute breakout", breakout, 10, "Completed minute close exceeds the preceding five completed minutes' highs."),
            ("Positive session", positive, 10, "Completed minute close is above the split-adjusted previous-session close."),
        ]
        signals = [{"name": name, "points": points if bool(condition) else 0,
                    "max_points": points, "description": description}
                   for name, condition, points, description in conditions]
        score = sum(signal["points"] for signal in signals)
        if not above_vwap:
            blockers.append("Completed minute close must be above session VWAP.")
        if not ema_trend:
            blockers.append("Nine-minute EMA must be above twenty-minute EMA.")
        if not config["alerts_enabled"]:
            blockers.append("Setup alerts are disabled in monitor settings.")
        eligible = not blockers
        signal = "Strong buy" if eligible and score >= config["strong_buy_score"] else "Buy" if eligible and score >= config["buy_score"] else "Watch"
        checks = [
            {"name": "Session volume", "actual": regular_volume, "required": config["min_session_volume"], "passed": regular_volume is not None and regular_volume >= config["min_session_volume"], "unit": "shares"},
            {"name": "Buy score", "actual": score, "required": config["buy_score"], "passed": score >= config["buy_score"], "unit": "points"},
        ]
        # The same complete-bar calculations power the chart and score. VWAP
        # becomes unavailable at a missing minute or missing positive VWAP.
        chart, cumulative_volume, cumulative_value = [], premarket_volume, premarket_value
        chart_coverage = has_opening and not invalid_minutes and premarket_ok
        for index, bar in enumerate(minutes):
            if bar["volume"] > 0:
                chart_coverage = chart_coverage and bar["vwap"] is not None
                cumulative_volume += bar["volume"]
                cumulative_value += (bar["vwap"] or 0) * bar["volume"]
            chart.append({"t": _iso(bar["t"]), "open": bar["open"], "high": bar["high"], "low": bar["low"],
                          "close": bar["close"], "volume": bar["volume"],
                          "vwap": cumulative_value / cumulative_volume if chart_coverage and cumulative_volume else None,
                          "ema9": ema9_series[index] if ema9_series else None,
                          "ema20": ema20_series[index] if ema20_series else None})
        rows.append({
            "symbol": symbol, "name": asset.get("name") or symbol,
            "source": source, "feed": feed, "price": price, "price_at": _iso(price_at),
            "decision_at": _iso(now),
            "planning_quote": capture_planning_quote(quote, source, feed),
            "quote_at": _iso(quote_at) if valid_quote else None,
            "volume_at": _iso(volume_at), "session_date": str(session_date) if session_date else None,
            "day_volume": day_volume, "day_volume_at": _iso(day_volume_at),
            "day_volume_fresh": day_volume_fresh, "day_volume_basis": day_volume_basis, "volume_filter_basis": "regular_session", "day_volume_partial": not valid_daily_volume and day_volume is not None,
            "day_relative_volume": day_relative_volume, "spread_fresh": bool(fresh_quote),
            "spread": quote["ap"] - quote["bp"] if valid_quote else None,
            **screening,
            "session_volume": session_volume, "volume_30d_total": total_30d,
            "avg_volume_30d": average_30d, "relative_volume": relative_volume,
            "minute_relative_volume": minute_rvol, "float_shares": shares,
            "float_as_of": float_info["as_of"] if valid_float else None,
            "float_source": float_info["source"] if valid_float else None,
            "float_turnover": session_volume / shares if shares and session_volume is not None else None,
            "gap_pct": gap, "change_pct": change, "spread_pct": spread,
            "vwap": vwap, "ema9": ema9, "ema20": ema20, "rsi": rsi,
            "signal_score": score, "signal": signal, "alert_eligible": eligible,
            "eligibility": {"eligible": eligible, "primary_blocker": blockers[0] if blockers else
                            ("Score %s; requires %s points for Buy." % (score, config["buy_score"]) if score < config["buy_score"] else None),
                            "checks": checks},
            "trading_status": trading_status, "price_bands": price_bands,
            "signal_bar_at": _iso(last["t"]) if last else None,
            "reasons": [name for name, condition, points, description in conditions if condition],
            "blockers": blockers, "warnings": warnings, "stale": stale,
            "market_open": market_open,
            "chart": chart,
            "volume_history": [{"date": bar["date"], "volume": bar["volume"]} for bar in history],
            "signals": signals,
        })
    rank_rows(rows)
    return rows


def demo_bundle(symbols, step=0):
    """A reproducible historical simulation, advancing one minute per step.

    The service advances a step every three wall-clock seconds. Minute prices
    follow a fixed path, so advancing never rewrites an earlier completed bar.
    """
    config = validate_monitor_config({"symbols": symbols})
    if isinstance(step, bool) or not isinstance(step, int) or step < 0:
        raise ValueError("Demo step must be a nonnegative integer.")
    session_date = date(2025, 5, 14)
    session_open = datetime(2025, 5, 14, 13, 30, tzinfo=_UTC)
    session_close = session_open + timedelta(hours=6, minutes=30)
    now = session_open + timedelta(minutes=40 + step, seconds=10)
    dates, cursor = [], session_date - timedelta(days=1)
    while len(dates) < 280:
        if cursor.weekday() < 5 and cursor != date(2025, 4, 18):
            dates.append(cursor)
        cursor -= timedelta(days=1)
    dates.reverse()
    assets = []
    for asset_index, symbol in enumerate(config["symbols"]):
        base = 1.8 + asset_index * 0.11
        prior_close = base * 0.98
        daily = []
        for index, day in enumerate(dates):
            offset = index - (len(dates) - 35)
            close = prior_close * (1 - (34 - offset) * 0.0006)
            daily.append({"date": day.isoformat(), "open": close * 0.995,
                          "high": close * 1.025, "low": close * 0.975,
                          "close": close, "volume": max(100000, 900000 + offset * 5000 + asset_index * 10000)})
        minutes, previous_close = [], base
        for index in range(min(390, 40 + step)):
            close = base + index * 0.0008 + 0.0003 * math.sin(index * 0.7)
            if index >= 45:
                close += (index - 44) * 0.006
            volume = 18000 + (index % 5) * 500
            if index >= 42:
                volume = min(1500000, 38000 * (1.1 ** min(index - 42, 38)))
            high = max(previous_close, close) + (0.009 if index < 45 else 0.0003)
            low = min(previous_close, close) - 0.001
            minutes.append({"t": _iso(session_open + index * _MINUTE),
                            "open": previous_close, "high": high, "low": low,
                            "close": close, "volume": round(volume),
                            "vwap": (previous_close + close) / 2})
            previous_close = close
        latest = minutes[-1]
        assets.append({"symbol": symbol, "name": "{} · Synthetic momentum lab".format(symbol),
                       "sector": "Synthetic", "exchange": "SIMULATED", "bars": daily,
                       "minutes": minutes,
                       "snapshot": {"latestTrade": {"t": _iso(now - timedelta(seconds=1)), "p": latest["close"], "s": 100},
                                    "latestQuote": {"t": _iso(now - timedelta(seconds=1)),
                                                    "bp": latest["close"] - 0.001, "ap": latest["close"] + 0.001,
                                                    "bs": 10000, "as": 10000, "_received_at": _iso(now)},
                                    "dailyBar": {"t": _iso(session_open), "o": minutes[0]["open"],
                                                 "h": max(bar["high"] for bar in minutes),
                                                 "l": min(bar["low"] for bar in minutes),
                                                 "c": latest["close"], "v": sum(bar["volume"] for bar in minutes)},
                                    "_daily_received_at": _iso(now), "_extended_day": {"minutes": []},
                                    "prevDailyBar": {"c": prior_close}},
                       "float": {"shares": 8500000 + asset_index * 1000000, "as_of": "2025-05-13", "source": "Synthetic"}})
    benchmark_bars = []
    for index, day in enumerate(dates):
        close = 400 + index *0.2 + math.sin(index *0.3) *2
        benchmark_bars.append({"date": day.isoformat(), "open": close *0.999,
                               "high": close *1.005, "low": close *0.995,
                               "close": close, "volume": 50000000 + index *10000})
    return {"source": "demo", "feed": "synthetic", "as_of": _iso(now),
            "benchmark_bars": benchmark_bars,
            "warnings": ["Synthetic historical simulation: one market minute advances every three seconds. No real securities or prices are represented."],
            "session": {"date": session_date.isoformat(), "open": _iso(session_open),
                        "close": _iso(session_close), "previous_date": "2025-05-13",
                        "prior_dates": [day.isoformat() for day in dates[-30:]]},
            "assets": assets}
