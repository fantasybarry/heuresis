"""Read-only Massive acquisition for the first discovery study (DISCOVERY_STUDY_SPEC.md).

Primary references checked 2026-10-16:
https://massive.com/docs/rest/quickstart
https://massive.com/docs/rest/stocks/aggregates/daily-market-summary
https://massive.com/docs/rest/stocks/tickers/all-tickers
https://massive.com/docs/rest/stocks/aggregates/custom-bars

Prices are requested unadjusted: adjusted history rescales pre-split bars, which
would misstate the $0.10-$10 price at decision time. Raw response bytes are
stored gzipped and never rewritten once complete. Holdout data may be downloaded
but is unreadable here until a FINALISTS file exists.
"""

import csv
from datetime import date, datetime, timedelta
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT / "data" / "discovery"
FINALISTS = PROJECT / "FINALISTS"
HOST = "api.massive.com"
NY = ZoneInfo("America/New_York")
HOLDOUT = (date(2025, 4, 1), date(2025, 9, 30))
DISCOVERY = (date(2025, 10, 1), date(2026, 9, 30))
MIN_PRICE, MAX_PRICE = 0.10, 10.0
INTERVAL = 12.5  # Basic plan: 5 calls/minute.


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        raise RuntimeError("Massive returned an unexpected redirect; no credentials were forwarded.")


class Massive:
    """Paced GET transport returning raw response bytes."""

    def __init__(self, key=None, interval=INTERVAL):
        self.key = (key or os.environ.get("MASSIVE_API_KEY", "")).strip()
        if not self.key:
            raise ValueError("Set MASSIVE_API_KEY in the project .env (free Basic plan at massive.com).")
        self.interval, self.last = interval, 0.0
        self.opener = build_opener(_NoRedirect())

    def __call__(self, path_or_url, params=None):
        url = path_or_url if path_or_url.startswith("https://") else "https://" + HOST + path_or_url
        parts = urlsplit(url)
        if parts.hostname != HOST or parts.port or parts.username:
            raise RuntimeError("Massive requests must use https://" + HOST)
        if params:
            url += ("&" if parts.query else "?") + urlencode(params)
        request = Request(url, headers={"Authorization": "Bearer " + self.key,
                                        "Accept": "application/json", "User-Agent": "Nomisma/1.0"})
        for attempt in range(16):
            time.sleep(max(0.0, self.last + self.interval - time.monotonic()))
            self.last = time.monotonic()
            try:
                with self.opener.open(request, timeout=60) as response:
                    return response.read()
            except HTTPError as error:
                code = error.code
                error.close()
                if code == 429 and attempt < 15:
                    time.sleep(60)
                    continue
                if code in (500, 502, 503, 504) and attempt < 15:
                    time.sleep(2 ** attempt)
                    continue
                if code in (401, 403):
                    raise RuntimeError("Massive denied access (HTTP %s). Check MASSIVE_API_KEY and plan history." % code) from None
                raise RuntimeError("Massive request failed (HTTP %s): %s" % (code, parts.path)) from None
            except (URLError, TimeoutError, OSError):
                if attempt < 15:  # ride out network drops (sleep, Wi-Fi changes) for about 10 minutes
                    time.sleep(min(60, 2 ** attempt))
                    continue
                raise RuntimeError("Could not reach Massive after retries.") from None


def period(day):
    if HOLDOUT[0] <= day <= HOLDOUT[1]:
        return "holdout"
    if DISCOVERY[0] <= day <= DISCOVERY[1]:
        return "discovery"
    raise ValueError("%s is outside the study periods." % day)


def readable(root, name):
    """The only gate to study data; holdout stays sealed until finalists are committed."""
    if name == "holdout" and not FINALISTS.is_file():
        raise PermissionError("Holdout is sealed until a committed FINALISTS file exists.")
    return Path(root) / name


def _save(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    with gzip.open(partial, "wb") as handle:
        handle.write(body)
    partial.replace(path)


def _load(path):
    with gzip.open(path, "rb") as handle:
        return json.loads(handle.read())


def weekdays(start, end):
    day = start
    while day <= end:
        if day.weekday() < 5:
            yield day
        day += timedelta(days=1)


def month_starts(start, end):
    """First weekday of each month in [start, end]."""
    seen = set()
    for day in weekdays(start, end):
        if (day.year, day.month) not in seen:
            seen.add((day.year, day.month))
            yield day


def fetch_grouped(get, root, start, end, progress=print):
    """Unadjusted, non-OTC daily bars for every weekday; holidays return no results."""
    for day in weekdays(start, end):
        path = Path(root) / period(day) / "raw" / "grouped" / (day.isoformat() + ".json.gz")
        if path.exists():
            continue
        body = get("/v2/aggs/grouped/locale/us/market/stocks/" + day.isoformat(),
                   {"adjusted": "false", "include_otc": "false"})
        _save(path, body)
        progress("grouped %s: %s rows" % (day, json.loads(body).get("resultsCount", 0)))


def _pages(get, folder, params, stop=None, progress=print):
    """Fetch every page into folder, then mark it complete; an incomplete folder restarts."""
    if (folder / "complete").exists():
        return
    body, number = get("/v3/reference/tickers", params), 0
    while True:
        _save(folder / ("page-%03d.json.gz" % number), body)
        page = json.loads(body)
        progress("%s page %d: %d tickers" % (folder.name, number, len(page.get("results", []))))
        if not page.get("next_url") or (stop and stop(page)):
            break
        body, number = get(page["next_url"]), number + 1
    (folder / "complete").write_text("")


def fetch_tickers(get, root, start, end, progress=print):
    """Monthly point-in-time common-stock snapshots, plus all CS delisted since start."""
    for day in month_starts(start, end):
        _pages(get, Path(root) / period(day) / "raw" / "tickers" / day.isoformat(),
               {"market": "stocks", "type": "CS", "date": day.isoformat(), "limit": 1000}, progress=progress)
    floor = start.isoformat()
    _pages(get, Path(root) / "reference" / "delisted",
           {"market": "stocks", "type": "CS", "active": "false", "sort": "delisted_utc",
            "order": "desc", "limit": 1000},
           stop=lambda page: any((row.get("delisted_utc") or "9")[:10] < floor for row in page.get("results", [])),
           progress=progress)


def _rows(folder):
    for path in sorted(folder.glob("page-*.json.gz")):
        yield from _load(path).get("results", [])


def delisted(root):
    """{ticker: last trading date} for CS tickers delisted on or after the holdout start."""
    found = {}
    for row in _rows(Path(root) / "reference" / "delisted"):
        last = (row.get("delisted_utc") or "")[:10]
        if last >= HOLDOUT[0].isoformat() and row.get("type") == "CS":
            found[row["ticker"]] = max(last, found.get(row["ticker"], ""))
    return found


def _universe(base, root):
    """([(day, ticker, bar)], skipped) for U.S.-listed CS whose unadjusted daily range meets $0.10-$10.

    The daily range is a superset filter; the exact price is checked at decision time.
    A ticker counts as CS if its month's snapshot or the next month's lists it (mid-month
    listings), or if it was delisted on or after that day.
    """
    snapshots = {}
    for folder in sorted((base / "raw" / "tickers").iterdir()):
        if not (folder / "complete").exists():
            raise RuntimeError("Ticker snapshot %s is incomplete; rerun acquisition." % folder.name)
        snapshots[folder.name[:7]] = {row["ticker"] for row in _rows(folder)}
    gone = delisted(root)
    months = sorted(snapshots)
    rows, skipped = [], 0
    for path in sorted((base / "raw" / "grouped").glob("*.json.gz")):
        day = path.name[:10]
        month = day[:7]
        if month not in snapshots:
            raise RuntimeError("No ticker snapshot for %s." % month)
        later = months[months.index(month) + 1] if month != months[-1] else None
        common = snapshots[month] | snapshots.get(later, set())
        for bar in _load(path).get("results") or []:
            ticker = bar.get("T")
            if ticker not in common and gone.get(ticker, "") < day:
                skipped += ticker not in gone
                continue
            if bar.get("l", 0) <= MAX_PRICE and bar.get("h", 0) >= MIN_PRICE:
                rows.append((day, ticker, bar))
    return rows, skipped


def build_universe(root=ROOT, name="discovery"):
    """Write universe.csv.gz and its summary for a readable period."""
    base = readable(root, name)
    rows, skipped = _universe(base, root)
    output, daily = io.StringIO(), {}
    writer = csv.writer(output)
    writer.writerow(["date", "ticker", "open", "high", "low", "close", "volume", "vwap", "trades"])
    for day, ticker, bar in rows:
        writer.writerow([day, ticker] + [bar.get(k) for k in ("o", "h", "l", "c", "v", "vw", "n")])
        daily[day] = daily.get(day, 0) + 1
    (base / "universe.csv.gz").write_bytes(gzip.compress(output.getvalue().encode()))
    sizes = sorted(daily.values())
    summary = {"sessions": len(daily), "stock_days": sum(sizes), "distinct_tickers": len({r[1] for r in rows}),
               "median_daily": sizes[len(sizes) // 2] if sizes else 0,
               "min_daily": sizes[0] if sizes else 0, "max_daily": sizes[-1] if sizes else 0,
               "non_cs_or_unknown_rows_skipped": skipped}
    (base / "universe_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def delisted_check(get, root=ROOT, count=10, days=14, progress=print):
    """Spec step 2: do unadjusted minute bars exist for CS delisted during discovery?"""
    inside = sorted((last, ticker) for ticker, last in delisted(root).items()
                    if DISCOVERY[0].isoformat() <= last <= DISCOVERY[1].isoformat())
    if not inside:
        raise RuntimeError("No delisted common stocks found in the discovery period.")
    picks = [inside[round(i * (len(inside) - 1) / max(1, count - 1))] for i in range(min(count, len(inside)))]
    report = {"delisted_in_discovery": len(inside), "checked": []}
    for last, ticker in dict.fromkeys(picks):
        end = date.fromisoformat(last)
        path = Path(root) / "discovery" / "raw" / "delisted-check" / ("%s-%s.json.gz" % (ticker, last))
        if not path.exists():
            _save(path, get("/v2/aggs/ticker/%s/range/1/minute/%s/%s" % (
                quote(ticker, safe=""), (end - timedelta(days=days)).isoformat(), last),
                {"adjusted": "false", "sort": "asc", "limit": 50000}))
        bars = _load(path).get("results") or []
        sessions = sorted({datetime.fromtimestamp(bar["t"] / 1000, NY).date().isoformat() for bar in bars})
        report["checked"].append({"ticker": ticker, "delisted": last, "minute_bars": len(bars),
                                  "sessions": len(sessions), "last_session": sessions[-1] if sessions else None})
        progress("%s (delisted %s): %d bars over %d sessions" % (ticker, last, len(bars), len(sessions)))
    report["with_bars"] = sum(1 for row in report["checked"] if row["minute_bars"])
    (Path(root) / "discovery" / "delisted_check.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def fetch_minutes(get, root, start, end, name="discovery", progress=print):
    """Unadjusted extended-hours minute bars for every universe ticker in [start, end].

    One file per ticker; extra pages are saved first and page 0 last, so an existing
    page 0 means the ticker is complete and a rerun resumes cleanly.
    """
    # Acquisition only: the ticker list is computed in memory from type and daily range, so a
    # sealed holdout can be downloaded without writing anything derived from its prices.
    base = Path(root) / name
    folder = base / "raw" / "minute" / start.isoformat()[:7]
    tickers = sorted({ticker for day, ticker, _ in _universe(base, root)[0]
                      if start.isoformat() <= day <= end.isoformat()})
    for number, ticker in enumerate(tickers, 1):
        safe = quote(ticker, safe="")
        if (folder / (safe + ".json.gz")).exists():
            continue
        bodies = [get("/v2/aggs/ticker/%s/range/1/minute/%s/%s" % (safe, start.isoformat(), end.isoformat()),
                      {"adjusted": "false", "sort": "asc", "limit": 50000})]
        while json.loads(bodies[-1]).get("next_url"):
            bodies.append(get(json.loads(bodies[-1])["next_url"]))
        for page in range(len(bodies) - 1, -1, -1):
            _save(folder / (safe + (".json.gz" if page == 0 else ".%d.json.gz" % page)), bodies[page])
        progress("%d/%d %s: %d bars" % (number, len(tickers), ticker,
                                        sum(json.loads(b).get("resultsCount", 0) for b in bodies)))


def quote_sample(root=ROOT, month="2025-10", count=30, minutes=20, progress=print):
    """Step 4 disk projection: Alpaca SIP quotes and trades for sampled listed primary opportunities.

    Alpaca's free plan serves SIP history older than 15 minutes; delisted symbols return nothing.
    """
    from . import live_data, providers
    import random
    _, headers, _ = live_data._credentials()
    base = readable(root, "discovery")
    with gzip.open(base / ("pilot-%s-opportunities.csv.gz" % month), "rt") as handle:
        rows = list(csv.DictReader(handle))
    windows = {(r["ticker"], r["date"], r["minute"]) for r in rows}
    listed = sorted({(r["ticker"], r["date"], r["minute"]) for r in rows
                     if r["window"] == "primary" and r["delisted"] == "False"})
    picks, sizes = random.Random(0).sample(listed, min(count, len(listed))), []
    for ticker, day, minute in picks:
        start = datetime.strptime(day + minute, "%Y-%m-%d%H:%M").replace(tzinfo=NY) + timedelta(minutes=1)
        total = records = 0
        for kind in ("quotes", "trades"):
            params, page_number = {"start": start.isoformat(), "end": (start + timedelta(minutes=minutes)).isoformat(),
                                   "feed": "sip", "limit": 10000}, 0
            while True:
                page = providers._get_json("https://data.alpaca.markets/v2/stocks/%s/%s" % (
                    quote(ticker, safe=""), kind), params, headers)
                path = base / "raw" / "alpaca-sample" / ("%s-%s-%s-%s-%d.json.gz" % (
                    quote(ticker, safe=""), day, minute.replace(":", ""), kind, page_number))
                _save(path, json.dumps(page).encode())
                total += path.stat().st_size
                records += len(page.get(kind) or [])
                if not page.get("next_page_token"):
                    break
                params["page_token"], page_number = page["next_page_token"], page_number + 1
        sizes.append(total)
        progress("%s %s %s: %d records, %d gz bytes" % (ticker, day, minute, records, total))
    summary = json.loads((base / ("pilot-%s-summary.json" % month)).read_text())
    per_year = summary["year_sessions"] / summary["sessions"]
    mean = sum(sizes) / len(sizes) if sizes else 0
    projection = {"sampled_windows": len(sizes), "mean_window_gz_bytes": round(mean),
                  "max_window_gz_bytes": max(sizes, default=0),
                  "unique_windows_projected_year": round(len(windows) * per_year),
                  "quotes_gb_projected": round(mean * len(windows) * per_year / 1e9, 2),
                  # 12 discovery + 6 holdout months of minute bars.
                  "minute_bars_gb_projected": round(summary["minute_bytes_month"] * 18 / 1e9, 2)}
    projection["total_gb_projected"] = round(projection["quotes_gb_projected"] + projection["minute_bars_gb_projected"], 2)
    (base / ("pilot-%s-disk.json" % month)).write_text(json.dumps(projection, indent=2) + "\n")
    return projection


def manifest(root, name):
    """SHA-256 of every raw file in a period; written beside the data and returned."""
    base = Path(root) / name
    digest = {str(path.relative_to(base)): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted((base / "raw").rglob("*.json.gz"))}
    text = json.dumps(digest, indent=2, sort_keys=True) + "\n"
    (base / "MANIFEST.json").write_text(text)
    return hashlib.sha256(text.encode()).hexdigest(), len(digest)
