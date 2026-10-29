"""Frozen, decision-time inputs for the research trade planner; no I/O.

Quote sizes are not universally 100-share lots. Alpaca's dated change takes
precedence over its older stream schema for SIP quotes from 2025-11-03:
https://docs.alpaca.markets/us/changelog/marketdata-bid-and-ask-size-display-change
Older SIP and IEX sizes deliberately remain unnormalized.
"""

import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .engine import _number


_NY = ZoneInfo("America/New_York")
_MINUTE = timedelta(minutes=1)
_SIP_SHARES_FROM = date(2025, 11, 3)
_SYMBOL = re.compile(r"[A-Z][A-Z0-9]{0,9}(?:[.\-][A-Z0-9]{1,4})?\Z")
QUOTE_MAX_AGE_SECONDS = 5


def _time(value):
    """UTC datetime from RFC3339 text or an aware datetime; None when invalid or naive."""
    try:
        if isinstance(value, str):
            # Alpaca uses nanoseconds; Python 3.9 fromisoformat needs microseconds.
            value = re.sub(r"(\.\d{6})\d+(?=Z|[+-]\d\d:\d\d$)", r"\1", value)
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if not isinstance(value, datetime) or value.utcoffset() is None:
            return None
        return value.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def _iso(value):
    return value.isoformat() if value is not None else None


def _shares(value):
    return int(value) if _number(value, 0, 1e12) and int(value) == value else None


def _provenance(source, feed):
    return ((source == "demo" and feed == "synthetic")
            or (source == "alpaca" and feed in ("sip", "iex")))


def capture_planning_quote(raw, source, feed):
    """Copy documented quote evidence without inventing receipt times or units.

    The caller records _received_at when the original quote is accepted. A
    later render must never replace that time with the rendering time.
    Invalid values become explicit nulls, making downstream checks fail.
    """
    raw = raw if isinstance(raw, dict) else {}
    event_at, received_at = _time(raw.get("t")), _time(raw.get("_received_at"))
    synthetic = source == "demo" and feed == "synthetic"
    sip_shares = (source == "alpaca" and feed == "sip" and event_at is not None
                  and event_at.astimezone(_NY).date() >= _SIP_SHARES_FROM)
    unit = "shares" if synthetic or sip_shares else "unknown"
    basis = ("Explicit synthetic share quantities." if synthetic else
             "Alpaca SIP shares convention effective 2025-11-03." if sip_shares else
             "Share conversion unverified for this feed and quote date; raw sizes retained.")
    sizes = {side: raw.get(key) if _number(raw.get(key), -1e12, 1e12) else None
             for side, key in (("bid", "bs"), ("ask", "as"))}
    return {
        "schema_version": 1,
        "bid": raw.get("bp") if _number(raw.get("bp"), 0.000001, 1e9) else None,
        "ask": raw.get("ap") if _number(raw.get("ap"), 0.000001, 1e9) else None,
        "bid_size_raw": sizes["bid"], "ask_size_raw": sizes["ask"],
        "bid_size_shares": _shares(sizes["bid"]) if unit == "shares" else None,
        "ask_size_shares": _shares(sizes["ask"]) if unit == "shares" else None,
        "size_unit": unit, "size_basis": basis,
        "event_at": _iso(event_at), "received_at": _iso(received_at),
        "source": source if isinstance(source, str) else None,
        "feed": feed if isinstance(feed, str) else None,
    }


def prepare_plan_inputs(alert):
    """Validate original alert evidence; return diagnostics and a finite schema.

    No fallback to today's quotes, signal-bar times, alert creation wall clock,
    daily ATR, filled missing minutes, or reconstructed historical receipts.
    Missing sizes affect sizing only; invalid price/time evidence is blocking.
    """
    alert = alert if isinstance(alert, dict) else {}
    snapshot = alert.get("snapshot")
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    session = alert.get("session")
    session = session if isinstance(session, dict) else {}
    source, feed, symbol = (alert.get(key) for key in ("source", "feed", "symbol"))
    decision = _time(snapshot.get("decision_at"))
    opening, closing = _time(session.get("open")), _time(session.get("close"))
    blockers, warnings = [], []
    eligible = snapshot.get("alert_eligible") is True
    status = snapshot.get("trading_status")
    status = status if isinstance(status, dict) else {}
    halted = status.get("halted") if type(status.get("halted")) is bool else None
    result = {
        "schema_version": 1, "valid": False, "blockers": blockers, "warnings": warnings,
        "symbol": symbol if isinstance(symbol, str) else None,
        "source": source if isinstance(source, str) else None,
        "feed": feed if isinstance(feed, str) else None,
        "decision_at": _iso(decision), "session_open": _iso(opening), "session_close": _iso(closing),
        "eligible": eligible, "halted": halted, "minutes": [],
        "quote": capture_planning_quote({}, source, feed),
    }
    if not isinstance(symbol, str) or not _SYMBOL.fullmatch(symbol):
        blockers.append("A valid original alert symbol is required.")
    if (not _provenance(source, feed)
            or any(snapshot.get(key) != alert.get(key) for key in ("symbol", "source", "feed"))):
        blockers.append("Original alert and snapshot symbol/source/feed must match a supported feed.")
    if not eligible or alert.get("level") not in ("Buy", "Strong buy"):
        blockers.append("An originally eligible Buy or Strong buy alert is required.")
    if halted:
        blockers.append("The frozen evidence identifies a trading halt or pause.")
    elif halted is None:
        warnings.append("Trading halt status is unavailable in the original evidence.")
    if source == "demo":
        warnings.append("Synthetic research example; prices and share quantities are invented.")
    elif feed == "iex":
        warnings.append("IEX is a single-exchange feed, not consolidated market data.")

    session_date = session.get("date")
    valid_session = (isinstance(session_date, str) and opening is not None and closing is not None
                     and opening < closing and closing - opening <= timedelta(hours=6, minutes=30)
                     and opening.astimezone(_NY).date().isoformat() == session_date
                     and closing.astimezone(_NY).date().isoformat() == session_date
                     and snapshot.get("session_date") == session_date
                     and alert.get("session_date") == session_date)
    if not valid_session:
        blockers.append("Matching original regular-session dates and exchange hours are required.")
    if decision is None:
        blockers.append("Original decision time is missing; historical evidence cannot be reconstructed.")
    elif not valid_session or not opening <= decision < closing:
        blockers.append("Original decision time must be inside its regular exchange session.")

    bars = snapshot.get("chart")
    normalized = []
    bar_errors = []
    if not isinstance(bars, list) or not 15 <= len(bars) <= 390:
        bar_errors.append("At least 15 and at most 390 original completed minute bars are required.")
    if isinstance(bars, list) and len(bars) <= 390:
        prior = None
        for index, bar in enumerate(bars):
            if not isinstance(bar, dict):
                bar_errors.append("Minute {} is malformed.".format(index + 1))
                continue
            stamp = _time(bar.get("t"))
            values = {key: bar.get(key) for key in ("open", "high", "low", "close", "volume")}
            good_numbers = (all(_number(values[key], 0.000001, 1e9) for key in ("open", "high", "low", "close"))
                            and _number(values["volume"], 0, 1e12) and int(values["volume"]) == values["volume"])
            if (not good_numbers or values["low"] > min(values["open"], values["close"])
                    or values["high"] < max(values["open"], values["close"])):
                bar_errors.append("Minute {} has invalid OHLC prices or share volume.".format(index + 1))
                continue
            if (stamp is None or stamp.second or stamp.microsecond or not valid_session or decision is None
                    or stamp < opening or stamp + _MINUTE > min(decision, closing)):
                bar_errors.append("Minute {} is not a completed, aligned original-session bar.".format(index + 1))
                continue
            if (index == 0 and stamp != opening) or (prior is not None and stamp - prior != _MINUTE):
                bar_errors.append("Minute history must begin at session open and be ordered, unique and contiguous.")
            prior = stamp
            normalized.append(dict(values, t=stamp.isoformat()))
        if normalized and decision is not None:
            last = _time(normalized[-1]["t"])
            if not 0 <= (decision - last - _MINUTE).total_seconds() <= 120:
                bar_errors.append("Latest completed minute is more than 120 seconds old at the decision.")
            if (last != _time(alert.get("market_time"))
                    or last != _time(snapshot.get("signal_bar_at"))):
                bar_errors.append("Original signal timestamps must match the latest completed minute.")
    if bar_errors:
        blockers.extend(dict.fromkeys(bar_errors))
    else:
        result["minutes"] = normalized

    frozen_quote = snapshot.get("planning_quote")
    if (not isinstance(frozen_quote, dict) or type(frozen_quote.get("schema_version")) is not int
            or frozen_quote.get("schema_version") != 1):
        blockers.append("Original frozen quote evidence is missing or uses an unsupported schema.")
    else:
        # Normalize only the fields frozen in this alert. Missing raw quantities
        # must not be invented from a claimed normalized size.
        quote = capture_planning_quote({
            "bp": frozen_quote.get("bid"), "ap": frozen_quote.get("ask"),
            "bs": frozen_quote.get("bid_size_raw"), "as": frozen_quote.get("ask_size_raw"),
            "t": frozen_quote.get("event_at"), "_received_at": frozen_quote.get("received_at"),
        }, source, feed)
        result["quote"] = quote
        if (frozen_quote.get("source") != source or frozen_quote.get("feed") != feed):
            blockers.append("Frozen quote source/feed do not match the original alert.")
        for key in ("size_unit", "bid_size_shares", "ask_size_shares"):
            if (frozen_quote.get(key) != quote[key]
                    or type(frozen_quote.get(key)) is bool):
                blockers.append("Frozen quote share normalization does not match its documented feed/date convention.")
                quote["bid_size_shares"] = quote["ask_size_shares"] = None
                break
        event, receipt = _time(quote["event_at"]), _time(quote["received_at"])
        if quote["bid"] is None or quote["ask"] is None or quote["ask"] < quote["bid"]:
            blockers.append("A valid uncrossed original two-sided quote is required.")
        if (decision is None or event is None or receipt is None or not event <= receipt <= decision
                or not 0 <= (decision - event).total_seconds() <= QUOTE_MAX_AGE_SECONDS):
            blockers.append("Quote event and receipt must precede the decision and be at most 5 seconds old.")
        if quote["bid_size_shares"] is None or quote["ask_size_shares"] is None:
            warnings.append("Quote sizes in shares are unavailable or invalid; numeric position sizing is unavailable.")
    result["blockers"] = list(dict.fromkeys(blockers))
    result["valid"] = not blockers
    return result
