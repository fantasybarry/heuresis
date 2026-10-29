"""Offline, explicitly bounded settlement dates from an archived Alpaca calendar.

The provider's ``settlement_date`` is authoritative for this research artifact;
it is never inferred from the next trading/replay session. Calendar dates do not
establish broker cash-posting times. Release at 09:30 America/New_York on the
settlement date is a separate, explicit RTH-only simulation assumption.

Primary references:
https://docs.alpaca.markets/us/reference/legacycalendar
https://www.sec.gov/exams/educationhelpguidesfaqs/t1-faq
No network, credentials, accounts, or order interfaces are used here.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
from types import MappingProxyType
from zoneinfo import ZoneInfo


_SCHEMA = 1
_RELEASE_POLICY = {
    "timezone": "America/New_York",
    "local_time": "09:30:00",
    "basis": "Modeled RTH-only release; actual broker posting time is unknown.",
}
_DOCUMENTATION = [
    "https://docs.alpaca.markets/us/reference/legacycalendar",
    "https://www.sec.gov/exams/educationhelpguidesfaqs/t1-faq",
]


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _digest(manifest):
    return _sha(_canonical({key: value for key, value in manifest.items() if key != "calendar_sha256"}))


def _day(value):
    if not isinstance(value, str):
        raise ValueError("Calendar dates must be ISO YYYY-MM-DD strings.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("Calendar dates must be ISO YYYY-MM-DD strings.") from error
    if parsed.isoformat() != value:
        raise ValueError("Calendar dates must be ISO YYYY-MM-DD strings.")
    return parsed


def _dates(values):
    if not isinstance(values, (list, tuple)) or not values:
        raise ValueError("Supply a nonempty explicit list or tuple of trading dates.")
    for value in values:
        _day(value)
    result = tuple(values)
    if result != tuple(sorted(set(result))):
        raise ValueError("Trading dates must be unique and chronological.")
    return result


def _path(value):
    path = Path(value).absolute()
    for part in (path,) + tuple(path.parents):
        if part.is_symlink():
            raise ValueError("Calendar source and output paths must not use symbolic links.")
    return path.resolve()


def _raw_path(directory, relative):
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("Calendar raw page path must stay within its archive.")
    return _path(directory / relative)


def _provider_rows(rows, request):
    if not isinstance(rows, list) or not rows:
        raise ValueError("Archived calendar must be a nonempty array.")
    start, end = _day(request.get("start")), _day(request.get("end"))
    if start > end or request.get("date_type", "TRADING") != "TRADING":
        raise ValueError("Source must declare valid inclusive trading-date bounds.")
    by_date = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Malformed archived calendar record.")
        day, settlement = _day(row.get("date")), _day(row.get("settlement_date"))
        if not start <= day <= end or day.weekday() >= 5 or settlement.weekday() >= 5 or settlement <= day:
            raise ValueError("Invalid provider trade or settlement date.")
        try:
            opening, closing = time.fromisoformat(row["open"]), time.fromisoformat(row["close"])
        except (KeyError, ValueError, TypeError) as error:
            raise ValueError("Invalid provider trading hours.") from error
        if opening.tzinfo is not None or closing.tzinfo is not None or opening >= closing:
            raise ValueError("Invalid provider trading hours.")
        if row["date"] in by_date:
            raise ValueError("Duplicate provider calendar date.")
        by_date[row["date"]] = row
    if list(by_date) != sorted(by_date):
        raise ValueError("Provider calendar is not chronological.")
    return by_date


def _read_source(manifest_path, expected_manifest_sha256=None, expected_raw_sha256=None):
    path = _path(manifest_path)
    manifest_bytes = path.read_bytes()
    if expected_manifest_sha256 is not None and _sha(manifest_bytes) != expected_manifest_sha256:
        raise ValueError("Source manifest hash mismatch.")
    archive = json.loads(manifest_bytes)
    if archive.get("status") != "complete" or archive.get("kind") != "current_research_metadata":
        raise ValueError("A complete archived research metadata manifest is required.")
    item = archive.get("items", {}).get("calendar", {})
    pages = [row for row in archive.get("pages", []) if row.get("path") == item.get("page_path")]
    if len(pages) != 1 or pages[0].get("url") != "https://api.alpaca.markets/v2/calendar":
        raise ValueError("Calendar page provenance is missing or ambiguous.")
    page = pages[0]
    if expected_raw_sha256 is not None and page.get("sha256") != expected_raw_sha256:
        raise ValueError("Calendar raw page does not match its pinned hash.")
    compressed = _raw_path(path.parent, page.get("path")).read_bytes()
    if _sha(compressed) != page.get("sha256"):
        raise ValueError("Calendar raw page hash mismatch.")
    body = gzip.decompress(compressed)
    if _sha(body) != page.get("body_sha256") or len(body) != page.get("response_bytes"):
        raise ValueError("Calendar raw body hash or byte count mismatch.")
    rows = _provider_rows(json.loads(body), page.get("params", {}))
    retrieved = page.get("retrieved_at")
    try:
        timestamp = datetime.fromisoformat(retrieved.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError("Source calendar retrieval timestamp is missing or invalid.") from error
    if timestamp.tzinfo is None or retrieved != item.get("received_at") or item.get("records") != len(rows):
        raise ValueError("Source calendar retrieval or record metadata is inconsistent.")
    return rows, {
        "manifest_sha256": _sha(manifest_bytes), "raw_page_path": page["path"],
        "raw_page_sha256": page["sha256"], "raw_body_sha256": page["body_sha256"],
        "request": page["params"], "url": page["url"], "retrieved_at": retrieved,
        "historical_available_at": None, "provider_record_count": len(rows),
    }


def _selection(rows, trade_dates):
    dates = _dates(trade_dates)
    if any(day not in rows for day in dates):
        raise ValueError("Registered trading date is missing from the archived provider calendar.")
    if dates != tuple(day for day in rows if dates[0] <= day <= dates[-1]):
        raise ValueError("Registered coverage must include every provider trading date within its bounds.")
    selected = [rows[day] for day in dates]
    coverage = {
        "trade_start": dates[0], "trade_end": dates[-1], "trade_dates": list(dates),
        "last_settlement_date": max(row["settlement_date"] for row in selected),
        "outside_coverage": "reject; no extrapolation",
    }
    return selected, coverage


@dataclass(frozen=True)
class SettlementCalendar:
    """Validated immutable mapping. Construct through :func:`load_calendar`."""

    trade_dates: tuple
    calendar_sha256: str
    file_sha256: str
    last_settlement_date: str
    _settlements: object

    def __post_init__(self):
        object.__setattr__(self, "trade_dates", _dates(self.trade_dates))
        object.__setattr__(self, "_settlements", MappingProxyType(dict(self._settlements)))
        if tuple(self._settlements) != self.trade_dates:
            raise ValueError("Calendar mapping and registered trade dates differ.")
        for trade_date, settlement in self._settlements.items():
            if _day(settlement) <= _day(trade_date) or _day(settlement).weekday() >= 5:
                raise ValueError("Invalid settlement date.")
        if self.last_settlement_date != max(self._settlements.values()):
            raise ValueError("Calendar settlement coverage differs from its mapping.")

    def validate_dates(self, trade_dates):
        """Validate an explicit chronological replay subset before execution."""
        dates = _dates(trade_dates)
        for day in dates:
            self.settlement_date(day)
        return dates

    def settlement_date(self, trade_date):
        """Return the archived provider date; reject weekends and uncovered dates."""
        _day(trade_date)
        if trade_date not in self._settlements:
            raise ValueError("Trade date {} is outside registered calendar coverage.".format(trade_date))
        return self._settlements[trade_date]

    def release_at(self, trade_date):
        """Return modeled 09:30 Eastern settlement release as UTC ISO text."""
        settlement = _day(self.settlement_date(trade_date))
        local = datetime.combine(settlement, time(9, 30), tzinfo=ZoneInfo("America/New_York"))
        return local.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def create_calendar(source_manifest_path, output_path, trade_dates, *, expected_raw_sha256):
    """Create a new calendar file from a caller-pinned, verified local raw page.

    This function refuses overwrite and never downloads missing data. Source
    references are relative to the derived artifact for workspace portability;
    the referenced source manifest and page are reverified on every load.
    """
    if not isinstance(expected_raw_sha256, str) or len(expected_raw_sha256) != 64:
        raise ValueError("An explicit expected raw page SHA256 is required.")
    source_path, output = _path(source_manifest_path), _path(output_path)
    rows, source = _read_source(source_path, expected_raw_sha256=expected_raw_sha256)
    selected, coverage = _selection(rows, trade_dates)
    source["manifest_path"] = os.path.relpath(source_path, output.parent)
    manifest = {
        "schema_version": _SCHEMA, "status": "complete", "kind": "cash_settlement_calendar",
        "source": source, "coverage": coverage, "rows": selected,
        "mapping_basis": "Explicit archived Alpaca settlement_date; never next trading or replay date.",
        "release_policy": dict(_RELEASE_POLICY), "documentation": list(_DOCUMENTATION),
    }
    manifest["calendar_sha256"] = _digest(manifest)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as handle:
        handle.write(_canonical(manifest))
    load_calendar(output)
    return output


def load_calendar(path):
    """Verify derived metadata, pinned source manifest/raw hashes and exact rows."""
    path = _path(path)
    content = path.read_bytes()
    manifest = json.loads(content)
    if (manifest.get("schema_version") != _SCHEMA or manifest.get("status") != "complete"
            or manifest.get("kind") != "cash_settlement_calendar"
            or manifest.get("calendar_sha256") != _digest(manifest)):
        raise ValueError("Calendar metadata is incomplete, unsupported, or its hash differs.")
    if manifest.get("release_policy") != _RELEASE_POLICY:
        raise ValueError("Unsupported calendar cash-release policy.")
    source = manifest.get("source", {})
    source_reference = source.get("manifest_path")
    if not isinstance(source_reference, str) or not source_reference or Path(source_reference).is_absolute():
        raise ValueError("Calendar must reference a local relative source manifest path.")
    rows, verified_source = _read_source(path.parent / source_reference,
                                         expected_manifest_sha256=source.get("manifest_sha256"),
                                         expected_raw_sha256=source.get("raw_page_sha256"))
    verified_source["manifest_path"] = source_reference
    if verified_source != source:
        raise ValueError("Calendar source provenance differs from its archived evidence.")
    selected, coverage = _selection(rows, manifest.get("coverage", {}).get("trade_dates"))
    if selected != manifest.get("rows") or coverage != manifest.get("coverage"):
        raise ValueError("Calendar rows or coverage differ from the archived provider mapping.")
    return SettlementCalendar(tuple(coverage["trade_dates"]), manifest["calendar_sha256"],
                              _sha(content), coverage["last_settlement_date"],
                              {row["date"]: row["settlement_date"] for row in selected})
