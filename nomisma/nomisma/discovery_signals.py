"""Opportunity detection for the first discovery study (DISCOVERY_STUDY_SPEC.md).

Minute timestamps are bar starts; a bar is usable once start + 1 minute has passed.
A candidate minute m is excluded from its own resistance. Missing minutes are never
synthesized. ATR14 is Wilder's, seeded by the mean of the first 14 true ranges, over
the session's bars through m (extended hours included), as in trade_plan.py.
"""

from bisect import bisect_left
import csv
from datetime import datetime, time, timedelta
import gzip
import json
from pathlib import Path
from urllib.parse import quote

from . import discovery_data as data

ARMS = ("b3", "b6", "c", "d")
FIRST = {"b3": timedelta(minutes=15), "b6": timedelta(minutes=30), "c": timedelta(0), "d": timedelta(0)}
PRIMARY_END, CUTOFF = time(11, 0), time(13, 0)
WINDOW = timedelta(minutes=15)
PREMARKET_START = time(4, 0)
MAX_MISSING_PREMARKET = 10
STOP_ATR = 1.5
ONE = timedelta(minutes=1)


def tick(price):
    return 0.0001 if price < 1 else 0.01


def by_day(bars):
    """Group provider bars by New York date, adding the bar-start datetime as "m"."""
    days = {}
    for bar in sorted(bars, key=lambda bar: bar["t"]):
        moment = datetime.fromtimestamp(bar["t"] / 1000, data.NY)
        days.setdefault(moment.date().isoformat(), []).append(dict(bar, m=moment))
    return days


def session_bars(bars, close):
    """One day's bars from 04:00 whose minute completes by the session close."""
    return [bar for bar in bars if bar["m"].time() >= PREMARKET_START and bar["m"] + ONE <= close]


def resistance(arm, bars, times, m, open_):
    """Resistance at candidate minute m from bars strictly before m; None if undefined."""
    def high(lo, hi):
        chosen = bars[bisect_left(times, lo):bisect_left(times, hi)]
        return max(bar["h"] for bar in chosen) if chosen else None

    if arm in ("b3", "b6"):
        boundary = open_ + timedelta(minutes=5 * ((m - open_) // timedelta(minutes=5)))
        return high(boundary - timedelta(minutes=15 if arm == "b3" else 30), boundary)
    if arm == "c":
        return high(datetime.combine(m.date(), PREMARKET_START, data.NY), open_)
    lo = m - timedelta(minutes=30)
    if lo < open_:
        present = bisect_left(times, open_) - bisect_left(times, lo)
        if (open_ - lo) // ONE - present > MAX_MISSING_PREMARKET:
            return None  # insufficient premarket
    return high(lo, m)


def atr14(bars):
    ranges = [max(b["h"] - b["l"], abs(b["h"] - a["c"]), abs(b["l"] - a["c"])) for a, b in zip(bars, bars[1:])]
    if len(ranges) < 14:
        return None
    atr = sum(ranges[:14]) / 14
    for value in ranges[14:]:
        atr = (13 * atr + value) / 14
    return atr


def opportunities(bars, open_, close):
    """Fresh crossings per arm, one active 15-minute opportunity per arm, through the cutoff."""
    cutoff = min(datetime.combine(open_.date(), CUTOFF, data.NY), close - timedelta(minutes=30))
    found, active, times = [], {}, [bar["m"] for bar in bars]
    for index, bar in enumerate(bars):
        m = bar["m"]
        if index == 0 or m < open_ or m + ONE > cutoff:
            continue
        price, prior = bar["c"], bars[index - 1]["c"]
        if price <= prior or not data.MIN_PRICE <= price <= data.MAX_PRICE:
            continue  # a fresh crossing needs prior <= level < price
        for arm in ARMS:
            if m < open_ + FIRST[arm] or (arm in active and m < active[arm] + WINDOW):
                continue
            level = resistance(arm, bars, times, m, open_)
            if level is None or not prior <= level < price:
                continue
            active[arm] = m
            atr = atr14(bars[:index + 1])
            stop = level + tick(level) - STOP_ATR * atr if atr else None
            found.append({"arm": arm, "minute": m.strftime("%H:%M"), "index": index,
                          "window": "primary" if m + ONE <= datetime.combine(m.date(), PRIMARY_END, data.NY) else "secondary",
                          "resistance": level, "prior_close": prior, "close": price, "volume": bar["v"],
                          "atr": atr, "stop": stop,
                          "stop_pct": (price - stop) / price if stop and stop > 0 else None})
    return found


def _calendar(root):
    """Alpaca exchange calendar for the discovery period, archived once as raw bytes."""
    path = Path(root) / "reference" / "calendar.json.gz"
    if not path.exists():
        from . import live_data
        _, headers, account_url = live_data._credentials()
        entries = live_data._get_json(account_url + "/v2/calendar", {
            "start": data.DISCOVERY[0].isoformat(), "end": data.DISCOVERY[1].isoformat()}, headers)
        path.write_bytes(gzip.compress(json.dumps(entries).encode()))
    sessions = {}
    for entry in json.loads(gzip.decompress(path.read_bytes())):
        day = datetime.strptime(entry["date"], "%Y-%m-%d").date()
        sessions[entry["date"]] = tuple(datetime.combine(day, datetime.strptime(entry[k], "%H:%M").time(), data.NY)
                                        for k in ("open", "close"))
    return sessions


def stock_days(root, month, stats):
    """Yield (ticker, day, open, close, session bars) for universe stock-days in a discovery month."""
    base = data.readable(root, "discovery")
    sessions = _calendar(root)
    with gzip.open(base / "universe.csv.gz", "rt") as handle:
        universe = {}
        for row in csv.DictReader(handle):
            if row["date"].startswith(month):
                universe.setdefault(row["ticker"], set()).add(row["date"])
    folder = base / "raw" / "minute" / month
    stats.update(tickers=len(universe), missing=0, disk=0, stock_days=0, bars=0,
                 sessions=sum(1 for day in sessions if day.startswith(month)), year_sessions=len(sessions))
    for ticker in sorted(universe):
        safe = quote(ticker, safe="")
        files = [folder / (safe + ".json.gz")]
        if not files[0].exists():
            stats["missing"] += 1
            continue
        while (folder / ("%s.%d.json.gz" % (safe, len(files)))).exists():
            files.append(folder / ("%s.%d.json.gz" % (safe, len(files))))
        stats["disk"] += sum(path.stat().st_size for path in files)
        days = by_day(bar for path in files for bar in (data._load(path).get("results") or []))
        for day in sorted(universe[ticker]):
            if day in sessions:
                open_, close = sessions[day]
                bars = session_bars(days.get(day, []), close)
                stats["stock_days"] += 1
                stats["bars"] += len(bars)
                yield ticker, day, open_, close, bars


def pilot(root=data.ROOT, month="2025-10"):
    """Spec step 4 counts: opportunities per arm and window, projected to the discovery year."""
    base = data.readable(root, "discovery")
    gone = {t for t, last in data.delisted(root).items() if last <= data.DISCOVERY[1].isoformat()}
    rows, stats = [], {}
    for ticker, day, open_, close, bars in stock_days(root, month, stats):
        for found in opportunities(bars, open_, close):
            rows.append(dict(found, ticker=ticker, date=day, delisted=ticker in gone))
    month_sessions, year_sessions = stats["sessions"], stats["year_sessions"]
    summary = {"month": month, "sessions": month_sessions, "year_sessions": year_sessions,
               "tickers": stats["tickers"], "tickers_missing_minute_data": stats["missing"],
               "stock_days": stats["stock_days"],
               "bars_per_stock_day": round(stats["bars"] / stats["stock_days"], 1) if stats["stock_days"] else 0,
               "minute_bytes_month": stats["disk"], "arms": {}}
    for arm in ARMS:
        primary = [r for r in rows if r["arm"] == arm and r["window"] == "primary"]
        summary["arms"][arm] = {
            "primary": len(primary),
            "secondary": sum(1 for r in rows if r["arm"] == arm and r["window"] == "secondary"),
            "primary_with_valid_stop": sum(1 for r in primary if r["stop_pct"]),
            "primary_projected_year": round(len(primary) * year_sessions / month_sessions) if month_sessions else 0,
            "primary_delisted_share": round(sum(r["delisted"] for r in primary) / len(primary), 3) if primary else None,
            "primary_median_stop_pct": sorted(r["stop_pct"] for r in primary if r["stop_pct"])[
                len([r for r in primary if r["stop_pct"]]) // 2] if any(r["stop_pct"] for r in primary) else None}
    fields = ["date", "ticker", "arm", "minute", "window", "resistance", "prior_close", "close", "volume",
              "atr", "stop", "stop_pct", "delisted"]
    with gzip.open(base / ("pilot-%s-opportunities.csv.gz" % month), "wt", newline="") as handle:
        writer = csv.DictWriter(handle, fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    (base / ("pilot-%s-summary.json" % month)).write_text(json.dumps(summary, indent=2) + "\n")
    return summary
