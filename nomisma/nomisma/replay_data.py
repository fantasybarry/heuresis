"""Immutable, offline historical replay archives; no monitor or order interfaces.

The REST retrieval clock is provenance, not original market-data availability.
Native quote/trade nanoseconds survive normalization. Raw response bytes and
request parameters are archived before interpretation, including rejected data.
"""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener
from zoneinfo import ZoneInfo

from . import live_data, providers
from .engine import _number

_NY = ZoneInfo("America/New_York")
_DATA = "https://data.alpaca.markets/v2/stocks/"
_SCHEMA = 1
_MAX_BYTES = 64 * 1024 * 1024


def timestamp_ns(value):
    """RFC3339 -> integer nanoseconds without float or microsecond collapse."""
    if not isinstance(value, str):
        raise ValueError("Timestamp must be RFC3339 text.")
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})", value)
    if not match:
        raise ValueError("Timestamp must include a timezone and at most nanoseconds.")
    stamp = datetime.fromisoformat(match[1] + match[3].replace("Z", "+00:00"))
    delta = stamp.astimezone(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (delta.days * 86400 + delta.seconds) * 10**9 + int((match[2] or "").ljust(9, "0"))


def _now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def digest(value):
    return sha256(canonical(value))


def file_sha256(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def write_json(path, value):
    """Atomically replace a pretty-printed JSON file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
    temporary.replace(path)


def write_new(path, value):
    """Write a pretty-printed JSON file that must not already exist."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


_canonical, _sha = canonical, sha256


def _http(url, params, headers):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in ("data.alpaca.markets", "paper-api.alpaca.markets", "api.alpaca.markets") or parsed.port or parsed.username or parsed.password:
        raise ValueError("Only fixed Alpaca HTTPS hosts are supported.")
    request = Request(url + "?" + urlencode(params), headers=headers, method="GET")
    try:
        with build_opener(providers._NoRedirect()).open(request, timeout=45) as response:
            body = response.read(_MAX_BYTES + 1)
    except HTTPError as error:
        code = error.code
        error.close()
        raise ValueError("Historical data request failed (HTTP {}).".format(code)) from None
    except (URLError, OSError, TimeoutError):
        raise ValueError("Historical data request failed; network unavailable.") from None
    if len(body) > _MAX_BYTES:
        raise ValueError("Historical data response exceeds archive limit.")
    return body


class _Archive:
    def __init__(self, directory, max_requests, requester, headers, reuse_directory=None, reuse_pages=None):
        self.directory, self.max_requests = directory, max_requests
        self.requester, self.headers = requester, headers
        self.pages, self.requests = [], 0
        self.reuse_directory = reuse_directory
        self.reuse_pages = reuse_pages or []
        self.reused_count = self.network_count = 0
        self.quality = []
        (directory / "raw").mkdir()

    def request(self, url, params):
        if self.requests >= self.max_requests:
            raise ValueError("Historical archive request budget exhausted; dataset is incomplete.")
        self.requests += 1
        relative = "raw/{:05d}.json.gz".format(self.requests)
        if self.requests <= len(self.reuse_pages):
            record = self.reuse_pages[self.requests - 1]
            if record.get("url") != url or record.get("params") != params:
                raise ValueError("Cached archive request sequence differs from the requested experiment.")
            old_path = record.get("path")
            if not isinstance(old_path, str) or Path(old_path).is_absolute() or ".." in Path(old_path).parts:
                raise ValueError("Cached archive has an invalid raw path.")
            source = (self.reuse_directory / old_path).resolve()
            if self.reuse_directory not in source.parents:
                raise ValueError("Cached archive raw file escapes its directory.")
            compressed = source.read_bytes()
            if _sha(compressed) != record.get("sha256"):
                raise ValueError("Cached archive raw response hash mismatch.")
            body = gzip.decompress(compressed)
            if _sha(body) != record.get("body_sha256"):
                raise ValueError("Cached archive raw response hash mismatch.")
            (self.directory / relative).write_bytes(compressed)
            self.pages.append(dict(record, path=relative, reused=True))
            self.reused_count += 1
            return json.loads(body)
        started = _now()
        self.network_count += 1
        response = self.requester(url, dict(params), self.headers)
        body = response if isinstance(response, bytes) else _canonical(response)
        compressed = gzip.compress(body, mtime=0)
        (self.directory / relative).write_bytes(compressed)
        self.pages.append({"path": relative, "sha256": _sha(compressed), "body_sha256": _sha(body),
                           "url": url, "params": dict(params), "requested_at": started,
                           "retrieved_at": _now(), "original_received_at": None,
                           "response_bytes": len(body)})
        try:
            return json.loads(body)
        except (ValueError, UnicodeError):
            raise ValueError("Archived historical response is not JSON.") from None

    def paged(self, endpoint, symbols, params):
        collected = {symbol: [] for symbol in symbols}
        params = dict(params, symbols=",".join(symbols), limit=10000, sort="asc")
        tokens, ordinal = set(), 0
        while True:
            payload = self.request(_DATA + endpoint, params)
            groups = payload.get(endpoint) if isinstance(payload, dict) else None
            if not isinstance(groups, dict):
                raise ValueError("Historical {} response has no symbol mapping.".format(endpoint))
            for symbol, records in groups.items():
                if symbol not in collected or not isinstance(records, list):
                    raise ValueError("Unexpected historical symbol or record list.")
                for record in records:
                    ordinal += 1
                    if not isinstance(record, dict):
                        self.quality.append({"kind": "malformed_record", "endpoint": endpoint, "symbol": symbol,
                                             "ordinal": ordinal, "session_date": params.get("asof")})
                        if endpoint in ("quotes", "trades"):
                            raise ValueError("Historical {} contains an unorderable non-object event; archive is incomplete.".format(endpoint))
                        continue
                    collected[symbol].append(dict(record, _ordinal=ordinal))
            token = payload.get("next_page_token")
            if token in (None, ""):
                break
            if not isinstance(token, str) or len(token) > 10000 or token in tokens:
                raise ValueError("Historical pagination token repeated or invalid.")
            tokens.add(token)
            params["page_token"] = token
        return collected


def _bars(records, lower_ns, upper_ns, quality, context, daily=False):
    result, seen = [], {}
    for raw in records:
        reason = None
        try:
            stamp = timestamp_ns(raw.get("t"))
            if not lower_ns <= stamp < upper_ns:
                reason = "out_of_bounds_bar"
            elif not all(_number(raw.get(key), 0.000001) for key in ("o", "h", "l", "c")) or not _number(raw.get("v")):
                reason = "invalid_bar_numbers"
            elif raw["l"] > min(raw["o"], raw["c"]) or raw["h"] < max(raw["o"], raw["c"]) or raw["v"] != int(raw["v"]):
                reason = "invalid_bar_geometry_or_volume"
            elif not daily and stamp % (60 * 10**9):
                reason = "unaligned_minute"
            elif raw.get("vw") is not None and not _number(raw["vw"], 0.000001):
                reason = "invalid_vwap"
        except (ValueError, KeyError, TypeError):
            reason = "malformed_bar"
        if reason:
            quality.append(dict(context, kind=reason, ordinal=raw.get("_ordinal"), t=raw.get("t")))
            continue
        item = {key: raw[short] for key, short in (("open", "o"), ("high", "h"), ("low", "l"), ("close", "c"), ("volume", "v"))}
        if daily:
            item["date"] = live_data._stamp(raw["t"]).astimezone(_NY).date().isoformat()
            key = item["date"]
        else:
            item.update(t=raw["t"], vwap=raw.get("vw"))
            key = stamp
        if key in seen:
            kind = "duplicate_bar" if seen[key] == item else "conflicting_bar"
            quality.append(dict(context, kind=kind, t=raw["t"]))
            if kind == "conflicting_bar":
                raise ValueError("Conflicting historical bars in {}.".format(context))
            continue
        seen[key] = item
        result.append(item)
    return sorted(result, key=lambda b: b["date"] if daily else timestamp_ns(b["t"]))


def _events(records, endpoint, lower_ns, upper_ns, quality, context):
    result, identities, exact_trades = [], set(), set()
    for raw in records:
        reason, stamp = None, None
        try:
            stamp = timestamp_ns(raw.get("t"))
            if not lower_ns <= stamp < upper_ns:
                reason = "out_of_bounds_" + endpoint
            elif endpoint == "quotes":
                if not all(_number(raw.get(key), 0.000001) for key in ("bp", "ap")):
                    reason = "invalid_quote_prices"
                elif raw["ap"] < raw["bp"]:
                    reason = "crossed_quote"
                elif not all(_number(raw.get(key)) and int(raw[key]) == raw[key] for key in ("bs", "as")):
                    reason = "invalid_quote_sizes"
            elif not _number(raw.get("p"), 0.000001) or not _number(raw.get("s"), 1) or int(raw["s"]) != raw["s"]:
                reason = "invalid_trade"
        except (ValueError, KeyError, TypeError):
            reason = "malformed_" + endpoint
        if reason:
            quality.append(dict(context, kind=reason, ordinal=raw.get("_ordinal"), t=raw.get("t")))
            if stamp is not None and lower_ns <= stamp < upper_ns:
                result.append(dict(raw, _invalid_reason=reason))
            continue
        # Trade IDs can be reused within an exchange/session. Only an identical
        # complete native record is a duplicate; preserve distinct observations.
        identity = (raw.get("x"), raw.get("i")) if endpoint == "trades" and raw.get("i") is not None else None
        if identity is not None:
            native = _canonical({key: value for key, value in raw.items() if key != "_ordinal"})
            if native in exact_trades:
                quality.append(dict(context, kind="duplicate_trade_identity", ordinal=raw["_ordinal"], t=raw["t"]))
                continue
            exact_trades.add(native)
            if identity in identities:
                quality.append(dict(context, kind="reused_trade_id_preserved", ordinal=raw["_ordinal"], t=raw["t"]))
            identities.add(identity)
        result.append(raw)
    return sorted(result, key=lambda r: (timestamp_ns(r["t"]), r["_ordinal"]))


def _basis(raw, adjusted, session_open_ns=None):
    """Infer latest split scale on the replay session, then undo future scale."""
    keyed = {timestamp_ns(bar["t"]): bar for bar in adjusted}
    if not raw or len(keyed) != len(raw):
        return None, "Missing raw/split session bars for share-basis verification."
    first = next((bar for bar in raw if session_open_ns is None or timestamp_ns(bar["t"]) >= session_open_ns), None)
    if first is None or timestamp_ns(first["t"]) not in keyed:
        return None, "No matched regular-session minute for basis normalization."
    factor = Decimal(str(first["close"])) / Decimal(str(keyed[timestamp_ns(first["t"])]["close"]))
    for bar in raw:
        other = keyed.get(timestamp_ns(bar["t"]))
        if other is None:
            return None, "Raw/split session timestamps do not match."
        for key in ("open", "high", "low", "close"):
            ratio = Decimal(str(bar[key])) / Decimal(str(other[key]))
            if abs(ratio / factor - 1) > Decimal("0.00001"):
                return None, "Raw/split session price scale is inconsistent."
        if bar["volume"] and abs(Decimal(str(other["volume"])) / factor - Decimal(str(bar["volume"]))) > max(Decimal(1), Decimal(str(bar["volume"])) * Decimal("0.00001")):
            return None, "Raw/split session volume scale is inconsistent."
    return factor, None


def _rescale_daily(records, factor):
    return [dict(bar, **{key: float(Decimal(str(bar[key])) * factor) for key in ("open", "high", "low", "close")},
                 volume=int((Decimal(str(bar["volume"])) / factor).to_integral_value())) for bar in records]


def download_dataset(output_dir, symbols, session_dates, max_requests=250, requester=None, resume_from=None):
    """Download a bounded retrospective cohort; return dataset.json path.

    requester(url, params, headers) may return bytes or a JSON object for tests.
    Existing output is refused. Errors preserve manifest status=incomplete and
    every successfully retrieved response; they never yield a usable dataset.
    """
    symbols = sorted({providers._symbol(symbol) for symbol in symbols})
    days = sorted({providers._date(day).isoformat() for day in session_dates})
    if not symbols or not days or type(max_requests) is not int or max_requests < 1:
        raise ValueError("Supply symbols, session dates, and a positive request budget.")
    if any(date.fromisoformat(day) >= datetime.now(_NY).date() for day in days):
        raise ValueError("Only prior completed sessions can enter the historical pilot.")
    directory = Path(output_dir).resolve()
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("Archive directory must be new or empty; existing data is immutable.")
    directory.mkdir(parents=True, exist_ok=True)
    if requester is None:
        status, headers, account_url = live_data._credentials()
        if status["feed"] != "sip":
            raise ValueError("This historical pilot requires the SIP feed.")
        requester = _http
    else:
        headers, account_url = {}, "https://paper-api.alpaca.markets"
    reuse_directory, reuse_pages = None, []
    if resume_from is not None:
        reuse_directory = Path(resume_from).resolve()
        old_manifest = json.loads((reuse_directory / "manifest.json").read_bytes())
        if (reuse_directory == directory or old_manifest.get("schema_version") != _SCHEMA
                or old_manifest.get("symbols") != symbols or old_manifest.get("session_dates") != days
                or not isinstance(old_manifest.get("pages"), list)):
            raise ValueError("Cached archive must be a separate matching cohort/session archive.")
        reuse_pages = old_manifest["pages"]
    archive = _Archive(directory, max_requests, requester, headers, reuse_directory, reuse_pages)
    manifest = {"schema_version": _SCHEMA, "status": "incomplete", "created_at": _now(),
                "source": "alpaca", "feed": "sip", "symbols": symbols, "session_dates": days,
                "max_requests": max_requests, "pages": archive.pages, "quality": archive.quality,
                "original_received_at": None, "availability": "Unknown historical receipt; modeled by replay only."}
    try:
        start = (date.fromisoformat(days[0]) - timedelta(days=100)).isoformat()
        calendar = archive.request(account_url + "/v2/calendar", {"start": start, "end": days[-1]})
        if not isinstance(calendar, list):
            raise ValueError("Historical calendar is not a list.")
        quote_conditions = {tape: archive.request(_DATA + "meta/conditions/quote", {"tape": tape}) for tape in ("A", "B", "C")}
        if not all(isinstance(mapping, dict) for mapping in quote_conditions.values()):
            raise ValueError("Quote condition metadata is not a mapping.")
        sessions = []
        for day in days:
            clock = datetime.combine(date.fromisoformat(day), time(23), _NY)
            session, calendar_days = live_data._session(calendar, clock)
            if session["date"] != day or len(session["prior_dates"]) != 30:
                raise ValueError("Requested date lacks a session and 30 prior calendar dates.")
            session["benchmark_bars"], session["assets"] = [], []
            all_symbols = sorted(set(symbols) | {"SPY"})
            beginning = datetime.combine(date.fromisoformat(day), time(4), _NY).isoformat()
            ending = datetime.combine(date.fromisoformat(day), time(20), _NY).isoformat()
            daily_start = datetime.combine(date.fromisoformat(day) - timedelta(days=100), time.min, _NY).isoformat()
            daily_end = datetime.combine(date.fromisoformat(day), time.min, _NY).isoformat()
            base = {"start": beginning, "end": ending, "feed": "sip", "asof": day, "timeframe": "1Min"}
            raw = archive.paged("bars", all_symbols, dict(base, adjustment="raw"))
            split = archive.paged("bars", all_symbols, dict(base, adjustment="split"))
            daily = archive.paged("bars", all_symbols, {"start": daily_start, "end": daily_end, "feed": "sip",
                                "asof": day, "timeframe": "1Day", "adjustment": "split"})
            event_params = {"start": session["open"], "end": session["close"], "feed": "sip", "asof": day}
            quotes = archive.paged("quotes", symbols, event_params)
            trades = archive.paged("trades", symbols, event_params)
            open_ns, close_ns = timestamp_ns(session["open"]), timestamp_ns(session["close"])
            for symbol in all_symbols:
                context = {"symbol": symbol, "session_date": day}
                minutes = _bars(raw[symbol], timestamp_ns(beginning), timestamp_ns(ending), archive.quality, dict(context, adjustment="raw"))
                split_minutes = _bars(split[symbol], timestamp_ns(beginning), timestamp_ns(ending), archive.quality, dict(context, adjustment="split"))
                prior = _bars(daily[symbol], timestamp_ns(daily_start), timestamp_ns(daily_end), archive.quality, dict(context, adjustment="split_daily"), daily=True)
                factor, error = _basis(minutes, split_minutes, open_ns)
                blockers = [error] if error else []
                scaled = _rescale_daily(prior, factor) if factor is not None else []
                missing_daily = sorted(set(session["prior_dates"]) - {bar["date"] for bar in scaled})
                if missing_daily:
                    blockers.append("Missing prior daily baseline sessions: " + ", ".join(missing_daily))
                actual = {timestamp_ns(bar["t"]) for bar in minutes if open_ns <= timestamp_ns(bar["t"]) < close_ns}
                missing = [datetime.fromtimestamp(stamp // 10**9, timezone.utc).isoformat() for stamp in range(open_ns, close_ns, 60 * 10**9) if stamp not in actual]
                quality = {"missing_rth_minutes": missing, "missing_prior_dates": missing_daily,
                           "halt_coverage": "unknown", "original_receipt_coverage": "unknown",
                           "corporate_action_coverage": "retrospective split scale checked; not archived as-of action truth; dividends/spinoffs not adjusted",
                           "price_basis": "raw session prices; split daily history rebased to this session",
                           "basis_anchor": "first matched regular-session minute; later bars integrity-only",
                           "daily_split_to_session_factor": str(factor) if factor is not None else None,
                           "data_blockers": blockers}
                if symbol == "SPY":
                    session["benchmark_bars"] = scaled
                    session["benchmark_quality"] = quality
                if symbol in symbols:
                    asset = {"symbol": symbol, "daily": scaled, "minutes": minutes,
                             "quotes": _events(quotes[symbol], "quotes", open_ns, close_ns, archive.quality, context),
                             "trades": _events(trades[symbol], "trades", open_ns, close_ns, archive.quality, context),
                             "quality": quality, "float": None}
                    if any(record.get("session_date") == day and record.get("symbol") == symbol and record.get("kind") in ("malformed_quotes", "malformed_trades") for record in archive.quality):
                        asset["quality"]["data_blockers"].append("Unordered malformed market events; historical timeline incomplete.")
                    session["assets"].append(asset)
            session["archived_bounds"] = {"minutes_start": beginning, "minutes_end_exclusive": ending,
                                           "events_start": session["open"], "events_end_exclusive": session["close"]}
            sessions.append(session)
        dataset = {"schema_version": _SCHEMA, "source": "alpaca", "feed": "sip", "symbols": symbols,
                   "manifest": "manifest.json", "sessions": sessions, "quote_conditions": quote_conditions,
                   "provenance": {"cohort_selection": "Retrospective engineering cohort selected from prior alerts; not a representative point-in-time universe.",
                                  "bar_versions": "Final historical REST bars, not original arrival revisions.",
                                  "original_received_at": None, "historical_float_available": False,
                                  "quote_size_unit": "shares", "quote_size_basis": "Alpaca SIP convention effective 2025-11-03",
                                  "event_order": "Exact native timestamp nanoseconds, then archived response ordinal; no cross-channel causal ordering implied.",
                                  "corporate_actions": "Split daily bars scaled to the contemporaneous raw session basis using paired raw/split minute bars; dividend and spinoff treatment unavailable."}}
        if archive.requests < len(reuse_pages):
            raise ValueError("Cached archive contains unconsumed requests; experiment sequence changed.")
        data = _canonical(dataset)
        (directory / "dataset.json").write_bytes(data)
        manifest.update(status="complete", completed_at=_now(), dataset={"path": "dataset.json", "sha256": _sha(data)})
        return directory / "dataset.json"
    except Exception as error:
        manifest["failure"] = str(error) if isinstance(error, ValueError) else type(error).__name__
        raise
    finally:
        manifest["request_count"] = archive.requests
        manifest["reused_page_count"] = archive.reused_count
        manifest["network_request_count"] = archive.network_count
        (directory / "manifest.json").write_bytes(_canonical(manifest))


def load_dataset(path):
    """Read only, verify every archived artifact before returning dataset."""
    path = Path(path).resolve()
    if path.is_dir():
        path = path / "dataset.json"
    directory = path.parent
    manifest = json.loads((directory / "manifest.json").read_bytes())
    if manifest.get("schema_version") != _SCHEMA or manifest.get("status") != "complete":
        raise ValueError("Historical archive manifest is incomplete or unsupported.")
    for record in [manifest.get("dataset", {})] + manifest.get("pages", []):
        relative = record.get("path")
        if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("Archive manifest contains an invalid file path.")
        target = (directory / relative).resolve()
        if directory not in target.parents:
            raise ValueError("Archive artifact escapes its directory.")
        content = target.read_bytes()
        if _sha(content) != record.get("sha256"):
            raise ValueError("Archive hash mismatch: " + relative)
        if "body_sha256" in record and _sha(gzip.decompress(content)) != record["body_sha256"]:
            raise ValueError("Raw response body hash mismatch: " + relative)
    if manifest["dataset"]["path"] != path.name:
        raise ValueError("Requested dataset differs from manifest.")
    dataset = json.loads(path.read_bytes())
    if dataset.get("schema_version") != _SCHEMA or dataset.get("symbols") != manifest.get("symbols"):
        raise ValueError("Dataset schema or cohort differs from manifest.")
    return dataset
