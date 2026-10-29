"""Minute-bar replay and cost sweep for the discovery study (spec step 6).

Entry fills at the open of the first bar starting at or after the decision time and
before the admission cutoff; no bar means no fill. Five or more missing minutes
before that bar are treated as a suspected halt, and an open more than 2% above the
deciding close as an unfilled limit; both keep their counterfactual fill. The stop is
fixed at the signal. From the entry bar on, the first low at/below the stop exits at
min(open, stop); otherwise the position exits at the close of the bar ending at entry
+ 15 minutes, or at the next print after it when that minute has no bar, or the last
bar before the session close. Costs are one-way fractions on both sides. Minute bars
cannot show halts; the longest gap between bars during the hold is recorded instead.
"""

from bisect import bisect_left
import csv
from datetime import datetime, timedelta, timezone
import gzip
import json
import random
from urllib.parse import quote

from . import discovery_data as data
from . import discovery_signals as signals

COSTS = (0.0, 0.005, 0.01, 0.02, 0.03)
LIQUID_DOLLARS = 20000
HOLD = timedelta(minutes=15)
HALT_GAP = timedelta(minutes=5)
LIMIT = 0.02  # the spec's widest limit, ask + 2%, proxied by the deciding close
ONE = signals.ONE
POLICIES = ("immediate", "delayed")


def candle(bars, times, i, atr, prefix):
    bar = bars[i]
    span = bar["h"] - bar["l"]
    base = sum(b["v"] for b in bars[bisect_left(times, bar["m"] - timedelta(minutes=20)):i]) / 20
    ratio = (lambda value: value / span) if span > 0 else (lambda value: None)
    return {prefix + "upper": ratio(bar["h"] - max(bar["o"], bar["c"])),
            prefix + "lower": ratio(min(bar["o"], bar["c"]) - bar["l"]),
            prefix + "body": ratio(abs(bar["c"] - bar["o"])),
            prefix + "close_loc": ratio(bar["c"] - bar["l"]),
            prefix + "range_atr": span / atr if atr else None,
            # Prior 20 clock minutes; minutes without trades count as zero volume.
            prefix + "vol_ratio": bar["v"] / base if base else None}


def outcome(bars, times, i, level, stop, atr):
    """Continuation label and move features over the 15 minutes after the signal minute."""
    m, breakout = bars[i]["m"], bars[i]["c"]
    window = list(range(i + 1, bisect_left(times, m + ONE + HOLD)))
    row = {"continuation": None, "advance_atr": None, "pullback_depth_atr": None, "pullback_minutes": None}
    row.update(candle(bars, times, i, atr, "b_"))
    if not window:
        return row
    ok, streak, pullback, recovery = bars[window[-1]]["c"] > breakout, 0, None, None
    previous = bars[i]["m"]
    for j in window:
        bar = bars[j]
        ok = ok and bar["l"] > stop
        # A minute without a bar keeps the last close, so missing minutes extend a streak at/below resistance.
        missed = (bar["m"] - previous) // ONE - 1 if streak else 0
        previous = bar["m"]
        if bar["c"] <= level:
            streak += missed + 1
            pullback = j if pullback is None else pullback
            ok = ok and streak <= 2
        else:
            ok = ok and streak + missed <= 2
            if streak and recovery is None:
                recovery = j
                ok = ok and bar["c"] > breakout  # a weak first recovery cannot be repaired later
            streak = 0
    if streak:
        ok = ok and streak + (m + HOLD - previous) // ONE <= 2
    row["continuation"] = ok
    rise = range(i, pullback if pullback is not None else window[-1] + 1)
    peak = max(rise, key=lambda j: bars[j]["h"])
    row["advance_atr"] = (bars[peak]["h"] - level) / atr
    if pullback is not None:
        last = recovery if recovery is not None else window[-1]
        row["pullback_depth_atr"] = (bars[peak]["h"] - min(bars[j]["l"] for j in range(peak, last + 1))) / atr
        row.update(candle(bars, times, pullback, atr, "p_"))
        if recovery is not None:
            row["pullback_minutes"] = (bars[recovery]["m"] - bars[peak]["m"]) // ONE
            row.update(candle(bars, times, recovery, atr, "r_"))
    return row


def trade(bars, k, decision, stop, cutoff, limit=None, level=None, wick=None, target=None):
    """Fill at bar k's open, then fixed stop or 15-minute time exit.

    A suspected halt or an open above limit is not a fill, but its counterfactual path is
    kept. With level and wick, a bar closing at/below level whose upper wick is at least
    that share of its range exits at the next bar's open. A high at/above target exits
    there (at the open if it gaps above); the stop is checked first within a minute.
    """
    if k >= len(bars) or bars[k]["m"] >= cutoff:
        return {"status": "no_fill"}
    entry, start = bars[k]["o"], bars[k]["m"]
    if entry <= stop:
        return {"status": "entry_at_or_below_stop"}
    status = "suspected_halt" if start - decision >= HALT_GAP else "above_limit" if limit and entry > limit else "filled"
    result = {"status": status, "entry": entry, "entry_delay": (start - decision) // ONE, "max_gap": 0,
              "entry_at": start.strftime("%H:%M")}
    last = k
    for j in range(k, len(bars)):
        bar = bars[j]
        if bar["m"] >= start + HOLD:
            if bars[last]["m"] + ONE < start + HOLD:  # the deadline minute has no bar: exit at the next print
                return dict(result, exit=bar["o"], exit_reason="time", exit_at=bar["m"].strftime("%H:%M"))
            break
        if j > k:
            result["max_gap"] = max(result["max_gap"], (bar["m"] - bars[j - 1]["m"]) // ONE - 1)
        if bar["l"] <= stop:
            return dict(result, exit=min(bar["o"], stop), exit_reason="stop", exit_at=bar["m"].strftime("%H:%M"))
        if target and bar["h"] >= target:
            return dict(result, exit=max(bar["o"], target), exit_reason="target", exit_at=bar["m"].strftime("%H:%M"))
        last = j
        span = bar["h"] - bar["l"]
        if (wick and bar["c"] <= level and span > 0 and j + 1 < len(bars)
                and (bar["h"] - max(bar["o"], bar["c"])) / span >= wick):
            return dict(result, exit=bars[j + 1]["o"], exit_reason="wick", exit_at=bars[j + 1]["m"].strftime("%H:%M"))
    return dict(result, exit=bars[last]["c"], exit_reason="time", exit_at=(bars[last]["m"] + ONE).strftime("%H:%M"))


def net_r(entry, exit_, stop, cost):
    paid = entry * (1 + cost)
    return (exit_ * (1 - cost) - paid) / (paid - stop * (1 - cost))


def day_context(bars, open_, prior_close):
    """Stock-day features known at the open: opening gap and premarket dollar volume."""
    first = bars[bisect_left([bar["m"] for bar in bars], open_)] if bars and bars[-1]["m"] >= open_ else None
    opening = first["o"] if first and first["m"] == open_ else None  # exact opening minute only
    return {"gap_pct": 100 * (opening / prior_close - 1) if opening and prior_close else None,
            "premarket_dollars": sum(bar["v"] * bar.get("vw", bar["c"]) for bar in bars if bar["m"] < open_)}


def _cutoff(open_, close):
    return min(open_.replace(hour=signals.CUTOFF.hour, minute=signals.CUTOFF.minute), close - timedelta(minutes=30))


def replay_day(bars, open_, close, context=None):
    cutoff = _cutoff(open_, close)
    times = [bar["m"] for bar in bars]
    for found in signals.opportunities(bars, open_, close):
        i, level, stop, atr = found.pop("index"), found["resistance"], found["stop"], found["atr"]
        row = dict(found, dollar_volume=found["volume"] * found["close"], **(context or {}))
        row["liquid"] = row["dollar_volume"] >= LIQUID_DOLLARS
        if not stop or stop <= 0:
            row.update({p + "_status": "no_stop" for p in POLICIES})
            yield row
            continue
        row.update(outcome(bars, times, i, level, stop, atr))
        decision = bars[i]["m"] + ONE
        immediate = trade(bars, i + 1, decision, stop, cutoff, bars[i]["c"] * (1 + LIMIT))
        confirm = i + 1
        if confirm >= len(bars) or bars[confirm]["c"] <= level:
            delayed = {"status": "confirmation_failed"}
        elif bars[confirm]["l"] <= stop:
            delayed = {"status": "stopped_while_waiting"}
        else:
            delayed = trade(bars, confirm + 1, bars[confirm]["m"] + ONE, stop, cutoff, bars[confirm]["c"] * (1 + LIMIT))
        for name, result in (("immediate", immediate), ("delayed", delayed)):
            row.update({name + "_" + key: value for key, value in result.items()})
            if result["status"] == "filled":
                for cost in COSTS:
                    row["%s_r%g" % (name, cost * 100)] = net_r(result["entry"], result["exit"], stop, cost)
        yield row


def _bootstrap_low(by_session, reps=1000, seed=0):
    """Lower 90% bound (5th percentile) of the mean, resampling whole sessions."""
    days = [(sum(values), len(values)) for values in by_session.values()]
    if len(days) < 2:
        return None
    rng, means = random.Random(seed), []
    for _ in range(reps):
        picks = [days[rng.randrange(len(days))] for _ in days]
        count = sum(n for _, n in picks)
        means.append(sum(total for total, _ in picks) / count if count else 0)
    means.sort()
    return means[int(0.05 * reps)]


def summarize(rows):
    """Per arm, policy, window and liquidity: participation, mean R per trade and per opportunity."""
    groups, no_stop = {}, {}
    for row in rows:
        if row.get("immediate_status") == "no_stop":  # untradeable under the spec; reported, not scored
            no_stop[row["arm"]] = no_stop.get(row["arm"], 0) + 1
            continue
        for policy in POLICIES:
            key = (row["arm"], policy, row["window"], "liquid" if row["liquid"] else "illiquid")
            groups.setdefault(key, []).append(row)
    summary = []
    for (arm, policy, window, liquidity), members in sorted(groups.items()):
        filled = [r for r in members if r.get(policy + "_status") == "filled"]
        labeled = [r for r in members if r.get("continuation") is not None]
        entry = {"arm": arm, "policy": policy, "window": window, "liquidity": liquidity,
                 "opportunities": len(members), "filled": len(filled),
                 "participation": round(len(filled) / len(members), 3),
                 "continuation_rate": round(sum(r["continuation"] for r in labeled) / len(labeled), 3) if labeled else None}
        for cost in COSTS:
            column = "%s_r%g" % (policy, cost * 100)
            per_trade = [r[column] for r in filled]
            by_session = {}
            for r in members:  # an unfilled opportunity contributes 0 R
                by_session.setdefault(r["date"], []).append(r.get(column, 0.0))
            label = "%g%%" % (cost * 100)
            entry["mean_r_trade@" + label] = round(sum(per_trade) / len(per_trade), 4) if per_trade else None
            entry["mean_r_opportunity@" + label] = round(sum(map(sum, by_session.values())) / len(members), 4)
            entry["win_rate@" + label] = round(sum(r > 0 for r in per_trade) / len(per_trade), 3) if per_trade else None
            if cost in (0.0, 0.02):
                low = _bootstrap_low(by_session)
                entry["boot_low90_opportunity@" + label] = round(low, 4) if low is not None else None
        summary.append(entry)
    return {"groups": summary, "no_stop_by_arm": no_stop}


def replay(root=data.ROOT, month="2025-10", name="replay"):
    base = data.readable(root, "discovery")
    gone = {t for t, last in data.delisted(root).items() if last <= data.DISCOVERY[1].isoformat()}
    # Previous-session closes from the unadjusted universe; a stock out of range that day has none.
    closes, previous = {}, {}
    with gzip.open(base / "universe.csv.gz", "rt") as handle:
        for r in csv.DictReader(handle):
            closes[(r["ticker"], r["date"])] = float(r["close"])
    days = sorted(signals._calendar(root))
    previous = dict(zip(days[1:], days))
    rows, stats = [], {}
    for ticker, day, open_, close, bars in signals.stock_days(root, month, stats):
        context = day_context(bars, open_, closes.get((ticker, previous.get(day))))
        for row in replay_day(bars, open_, close, context):
            rows.append(dict(row, ticker=ticker, date=day, delisted=ticker in gone))
    fields = sorted({key for row in rows for key in row})
    with gzip.open(base / ("%s-%s.csv.gz" % (name, month)), "wt", newline="") as handle:
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        writer.writerows(rows)
    summary = summarize(rows)
    (base / ("%s-%s-summary.json" % (name, month))).write_text(json.dumps(summary, indent=2) + "\n")
    return summary


# Known at the signal minute's close; advance/pullback/recovery features are not.
DECISION_FEATURES = ("gap_pct", "premarket_dollars", "minutes_from_open", "close", "dollar_volume", "stop_pct", "margin_pct",
                     "b_upper", "b_lower", "b_body", "b_close_loc", "b_range_atr", "b_vol_ratio")


def percent(row, policy, cost):
    return 100 * (float(row[policy + "_exit"]) * (1 - cost) / (float(row[policy + "_entry"]) * (1 + cost)) - 1)


def conditions(root=data.ROOT, month="2025-10", policy="immediate", cost=0.005, bins=5):
    """Post-hoc quintile scan of decision-time features over liquid primary fills, per arm."""
    base = data.readable(root, "discovery")
    with gzip.open(base / ("replay-%s.csv.gz" % month), "rt") as handle:
        rows = [r for r in csv.DictReader(handle) if r["window"] == "primary" and r["liquid"] == "True"
                and r.get(policy + "_status") == "filled"]
    for r in rows:
        hour, minute = map(int, r["minute"].split(":"))
        r["minutes_from_open"] = hour * 60 + minute - 570
        r["margin_pct"] = 100 * (float(r["close"]) / float(r["resistance"]) - 1)
        r["gross"], r["net"] = percent(r, policy, 0), percent(r, policy, cost)
    cells = []
    for arm in signals.ARMS:
        members = [r for r in rows if r["arm"] == arm]
        for feature in DECISION_FEATURES:
            valued = sorted(((float(r[feature]), r) for r in members if r[feature] not in ("", None)),
                            key=lambda pair: pair[0])
            for b in range(bins):
                chunk = [r for _, r in valued[b * len(valued) // bins:(b + 1) * len(valued) // bins]]
                if not chunk:
                    continue
                by_session = {}
                for r in chunk:
                    by_session.setdefault(r["date"], []).append(r["net"])
                labeled = [r["continuation"] == "True" for r in chunk if r["continuation"]]
                low = _bootstrap_low(by_session)
                cells.append({"arm": arm, "feature": feature, "bin": b + 1, "n": len(chunk),
                              "range": [round(float(chunk[0][feature]), 4), round(float(chunk[-1][feature]), 4)],
                              "gross_pct": round(sum(r["gross"] for r in chunk) / len(chunk), 3),
                              "net_pct@%g%%" % (cost * 100): round(sum(r["net"] for r in chunk) / len(chunk), 3),
                              "boot_low90_net": round(low, 3) if low is not None else None,
                              "continuation_rate": round(sum(labeled) / len(labeled), 3) if labeled else None})
    cells.sort(key=lambda c: -c["gross_pct"])
    (base / ("conditions-%s.json" % month)).write_text(json.dumps(cells, indent=2) + "\n")
    return cells


def quote_name(ticker):
    return quote(ticker, safe="")


def _stamp(text):
    """Alpaca RFC 3339 timestamp (nanoseconds, Z) to an aware datetime."""
    whole, _, frac = text.rstrip("Z").partition(".")
    return datetime.fromisoformat(whole + "." + (frac[:6] or "0").ljust(6, "0") + "+00:00")


def _half_spread(quotes, moment):
    """Relative half-spread of the NBBO in force at moment (else the first valid quote after it)."""
    valid = [(_stamp(q["t"]), q) for q in quotes if q.get("bp", 0) > 0 and q.get("ap", 0) >= q.get("bp", 0)]
    before = [q for t, q in valid if t <= moment]
    chosen = before[-1] if before else next((q for t, q in valid if t > moment), None)
    return (chosen["ap"] - chosen["bp"]) / (chosen["ap"] + chosen["bp"]) if chosen else None


def _spreads(base):
    """Cached half-spread lookup at a New York minute; raw Alpaca SIP quotes are archived once."""
    import time as clock
    from . import live_data, providers
    cache, headers = {}, []

    def spread_at(ticker, day, hhmm):
        key = (ticker, day, hhmm)
        if key not in cache:
            moment = datetime.strptime(day + hhmm, "%Y-%m-%d%H:%M").replace(tzinfo=data.NY)
            path = base / "raw" / "alpaca-spreads" / ("%s-%s-%s.json.gz" % (quote_name(ticker), day, hhmm.replace(":", "")))
            if not path.exists():
                if not headers:  # credentials only when a download is needed
                    headers.append(live_data._credentials()[1])
                clock.sleep(0.31)  # Alpaca free plan: 200 calls/minute
                page = providers._get_json("https://data.alpaca.markets/v2/stocks/%s/quotes" % quote_name(ticker), {
                    "start": (moment - timedelta(seconds=30)).isoformat(), "end": (moment + timedelta(seconds=5)).isoformat(),
                    "feed": "sip", "limit": 10000}, headers[0])
                data._save(path, json.dumps(page).encode())
            cache[key] = _half_spread(data._load(path).get("quotes") or [], moment.astimezone(timezone.utc))
        return cache[key]
    return spread_at


def real_spreads(root=data.ROOT, months=("2025-10",), gap=20.0, premarket=1e6, policy="immediate", arms=signals.ARMS):
    """Net returns of liquid in-play primary fills using measured Alpaca SIP spreads at entry and exit."""
    base = data.readable(root, "discovery")
    rows = []
    for month in months:
        with gzip.open(base / ("replay-%s.csv.gz" % month), "rt") as handle:
            rows += [r for r in csv.DictReader(handle) if r["window"] == "primary" and r["liquid"] == "True"
                     and r["arm"] in arms and r.get(policy + "_status") == "filled" and r["gap_pct"]
                     and float(r["gap_pct"]) >= gap and float(r["premarket_dollars"]) >= premarket]
    spread_at = _spreads(base)

    results = []
    for r in rows:
        entry_half, exit_half = spread_at(r["ticker"], r["date"], r[policy + "_entry_at"]), spread_at(r["ticker"], r["date"], r[policy + "_exit_at"])
        if entry_half is None or exit_half is None:
            continue
        entry, exit_ = float(r[policy + "_entry"]), float(r[policy + "_exit"])
        results.append({"arm": r["arm"], "date": r["date"], "gross": 100 * (exit_ / entry - 1),
                        "net": 100 * (exit_ * (1 - exit_half) / (entry * (1 + entry_half)) - 1),
                        "spread_entry": 200 * entry_half, "spread_exit": 200 * exit_half})
    summary = {"rule": {"gap_pct_min": gap, "premarket_dollars_min": premarket, "policy": policy},
               "trades_selected": len(rows), "trades_with_quotes": len(results), "arms": {}}
    for arm in arms:
        chosen = [x for x in results if x["arm"] == arm]
        if not chosen:
            continue
        by_session = {}
        for x in chosen:
            by_session.setdefault(x["date"], []).append(x["net"])
        low = _bootstrap_low(by_session)
        spreads = sorted(x["spread_entry"] for x in chosen)
        summary["arms"][arm] = {"n": len(chosen), "sessions": len(by_session),
                                "gross_pct": round(sum(x["gross"] for x in chosen) / len(chosen), 3),
                                "net_pct_real_spread": round(sum(x["net"] for x in chosen) / len(chosen), 3),
                                "boot_low90_net": round(low, 3) if low is not None else None,
                                "median_entry_spread_pct": round(spreads[len(spreads) // 2], 3),
                                "win_rate_net": round(sum(x["net"] > 0 for x in chosen) / len(chosen), 3)}
    name = months[0] if len(months) == 1 else "%s_%s-gap%g" % (months[0], months[-1], gap)
    (base / ("spreads-%s.json" % name)).write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def tally(root=data.ROOT, policy="immediate"):
    """Month-by-month gross percent per arm: all liquid primary fills, in play, and gap >= 40% in play."""
    base = data.readable(root, "discovery")
    rules = (("all", lambda r: True),
             ("in_play", lambda r: r["gap_pct"] and float(r["gap_pct"]) >= 20 and float(r["premarket_dollars"]) >= 1e6),
             ("gap40", lambda r: r["gap_pct"] and float(r["gap_pct"]) >= 40 and float(r["premarket_dollars"]) >= 1e6))
    table = {}
    for path in sorted(base.glob("replay-????-??.csv.gz")):
        month = path.name[7:14]
        with gzip.open(path, "rt") as handle:
            rows = [r for r in csv.DictReader(handle) if r["window"] == "primary" and r["liquid"] == "True"
                    and r.get(policy + "_status") == "filled"]
        for arm in signals.ARMS:
            for name, rule in rules:
                chosen = [percent(r, policy, 0) for r in rows if r["arm"] == arm and rule(r)]
                cell = table.setdefault((arm, name), {"months": {}, "values": []})
                cell["months"][month] = (len(chosen), sum(chosen) / len(chosen) if chosen else None)
                cell["values"] += chosen
    lines = []
    for (arm, name), cell in sorted(table.items()):
        months = " ".join("%s:%+.2f(%d)" % (m[2:], v, n) if v is not None else "%s:-(0)" % m[2:]
                          for m, (n, v) in sorted(cell["months"].items()))
        pooled = sum(cell["values"]) / len(cell["values"]) if cell["values"] else float("nan")
        positive = sum(1 for n, v in cell["months"].values() if v is not None and v > 0)
        lines.append("%-3s %-8s pooled %+.3f%% n=%-6d positive months %d/%d | %s" % (
            arm, name, pooled, len(cell["values"]), positive, len(cell["months"]), months))
    (base / "tally.txt").write_text("\n".join(lines) + "\n")
    return lines


def managed_trade(bars, k, stop, atr, rule):
    """trade() with an upward-only stop, updated only from completed bars (no intrabar look-ahead)."""
    entry, start = bars[k]["o"], bars[k]["m"]
    current, high = stop, entry
    for j in range(k, len(bars)):
        if bars[j]["m"] >= start + HOLD:  # as trade(): a missing deadline minute exits at the next print
            return (bars[j - 1]["c"] if bars[j - 1]["m"] + ONE >= start + HOLD else bars[j]["o"]), "time"
        if bars[j]["l"] <= current:
            return min(bars[j]["o"], current), "stop"
        high = max(high, bars[j]["h"])
        if rule == "breakeven_1r" and high >= entry + (entry - stop):
            current = max(current, entry)
        elif rule.startswith("trail_"):
            current = max(current, high - float(rule[6:-3]) * atr)
    return bars[-1]["c"], "time"


def simulate(trades, cost, start=2440.0, risk=0.041):
    """One-account path: earliest entry per session (alphabetical ties), whole shares, fixed-ratio risk."""
    import math
    first = {}
    for t in sorted(trades, key=lambda t: (t["date"], t["entry_at"], t["ticker"])):
        first.setdefault(t["date"], t)
    equity, peak, drawdown, results = start, start, 0.0, []
    for day, t in sorted(first.items()):
        paid = t["entry"] * (1 + cost)
        shares = math.floor(min(equity / paid, risk * equity / (paid - t["stop"] * (1 - cost))))
        pnl = shares * (t["exit"] * (1 - cost) - paid)
        equity += pnl
        peak, drawdown = max(peak, equity), min(drawdown, equity - peak)
        results.append(dict(t, shares=shares, pnl=pnl))
    return {"end": equity, "pnl": equity - start, "drawdown": drawdown, "trades": results}


def _day_bars(base, sessions, day, ticker):
    folder = base / "raw" / "minute" / day[:7]
    safe = quote_name(ticker)
    files = [folder / (safe + ".json.gz")]
    while (folder / ("%s.%d.json.gz" % (safe, len(files)))).exists():
        files.append(folder / ("%s.%d.json.gz" % (safe, len(files))))
    return signals.session_bars(signals.by_day(
        bar for path in files for bar in (data._load(path).get("results") or [])).get(day, []), sessions[day][1])


# Post hoc follow-up to the October 2025-March 2026 loss investigation (spec: "Loss follow-up").
EXPLORATION = tuple("2025-%02d" % m for m in (10, 11, 12)) + tuple("2026-%02d" % m for m in range(1, 7))
CONFIRMATION = "2026-07"
CANDIDATE_CHANGES = data.PROJECT / "CANDIDATE_CHANGES"
STOPS = {"S0": 1.5, "S1": 2.5, "S2": 3.5, "S3": None}  # ATR multiples; S3 has no stop, a diagnostic bound


def stop_variants(root=data.ROOT, months=EXPLORATION, arm="c", gap=40.0, premarket=1e6, wick=None,
                  costs=(0.005, 0.01, 0.02)):
    """The candidate rule's liquid primary opportunities under each stop in STOPS, immediate entry.

    Mean net percent per filled trade at each one-way cost, with the session-bootstrap lower 90% bound,
    positive months, the mean without the single best trade, and what happened to S0's five best trades.
    """
    if max(months) >= CONFIRMATION and not CANDIDATE_CHANGES.is_file():
        raise PermissionError("July-September 2026 tests committed changes; commit CANDIDATE_CHANGES first.")
    base = data.readable(root, "discovery")
    sessions = signals._calendar(root)
    cohort = []
    for month in months:
        with gzip.open(base / ("replay-%s.csv.gz" % month), "rt") as handle:
            cohort += [r for r in csv.DictReader(handle) if r["arm"] == arm and r["window"] == "primary"
                       and r["liquid"] == "True" and r["stop"] and r["gap_pct"]
                       and float(r["gap_pct"]) >= gap and float(r["premarket_dollars"]) >= premarket]
    trades = {name: [] for name in STOPS}
    for r in cohort:
        bars = _day_bars(base, sessions, r["date"], r["ticker"])
        i = next(j for j, bar in enumerate(bars) if bar["m"].strftime("%H:%M") == r["minute"])
        level, atr = float(r["resistance"]), float(r["atr"])
        for name, multiple in STOPS.items():
            stop = level + signals.tick(level) - multiple * atr if multiple else 0.0
            t = trade(bars, i + 1, bars[i]["m"] + ONE, stop, _cutoff(*sessions[r["date"]]),
                      bars[i]["c"] * (1 + LIMIT), level, wick)
            row = {"date": r["date"], "ticker": r["ticker"], "minute": r["minute"], "stop": stop, **t}
            for cost in costs if "entry" in t else ():
                row["net@%g" % (cost * 100)] = 100 * (t["exit"] * (1 - cost) / (t["entry"] * (1 + cost)) - 1)
            trades[name].append(row)
    label = "net@%g" % (costs[0] * 100)
    best = sorted((t for t in trades["S0"] if t["status"] == "filled"), key=lambda t: -t[label])[:5]
    summary = {"months": list(months), "arm": arm, "gap_min": gap, "premarket_min": premarket, "wick": wick,
               "opportunities": len(cohort), "variants": {}}
    for name, rows in trades.items():
        filled = [t for t in rows if t["status"] == "filled"]
        statuses, reasons = {}, {}
        for t in rows:
            statuses[t["status"]] = statuses.get(t["status"], 0) + 1
        for t in filled:
            reasons[t["exit_reason"]] = reasons.get(t["exit_reason"], 0) + 1
        entry = {"atr_multiple": STOPS[name], "statuses": statuses, "exit_reasons": reasons}
        for cost in costs:
            key = "net@%g" % (cost * 100)
            values = sorted(t[key] for t in filled)
            by_session, by_month = {}, {}
            for t in filled:
                by_session.setdefault(t["date"], []).append(t[key])
                by_month.setdefault(t["date"][:7], []).append(t[key])
            skipped = [t[key] for t in rows if t["status"] in ("suspected_halt", "above_limit")]
            low = _bootstrap_low(by_session)
            entry[key] = {"n": len(values), "mean": round(sum(values) / len(values), 3) if values else None,
                          "median": round(values[len(values) // 2], 3) if values else None,
                          "boot_low90": round(low, 3) if low is not None else None,
                          "mean_without_best": round(sum(values[:-1]) / (len(values) - 1), 3) if len(values) > 1 else None,
                          "positive_months": "%d/%d" % (sum(sum(v) > 0 for v in by_month.values()), len(by_month)),
                          "skipped_counterfactual_mean": round(sum(skipped) / len(skipped), 3) if skipped else None}
        lookup = {(t["date"], t["ticker"], t["minute"]): t for t in rows}
        entry["s0_best_five"] = [{"date": b["date"], "ticker": b["ticker"], "s0": round(b[label], 2),
                                  "here": round(lookup[(b["date"], b["ticker"], b["minute"])].get(label, float("nan")), 2)}
                                 for b in best]
        summary["variants"][name] = entry
    s0 = summary["variants"]["S0"][label]["mean"]
    for name, entry in summary["variants"].items():
        result = entry[label]
        months_up, months_all = map(int, result["positive_months"].split("/"))
        entry["passes_exploration"] = bool(
            name != "S0" and result["mean"] is not None and s0 is not None and result["mean"] > s0
            and (result["boot_low90"] or 0) > 0 and 3 * months_up >= 2 * months_all and (result["mean_without_best"] or 0) > 0)
    name = "stop-variants-%s_%s%s.json" % (months[0], months[-1], "-wick%g" % wick if wick else "")
    (base / name).write_text(json.dumps(summary, indent=2) + "\n")
    return summary, trades


# Second study, pre-registered in HYPOTHESES; scoring refuses to run before that file exists.
HYPOTHESES = data.PROJECT / "HYPOTHESES"
SECOND_STUDY = EXPLORATION + ("2026-07", "2026-08", "2026-09")


def reclaim(bars, i, level, cutoff, wick=0.5):
    """H1: first pullback close at/below level, then a reclaim close above it; trade from the next open."""
    window = range(i + 1, bisect_left([bar["m"] for bar in bars], bars[i]["m"] + ONE + HOLD))
    pullback = next((j for j in window if bars[j]["c"] <= level), None)
    if pullback is None:
        return {"status": "no_pullback"}
    bar = bars[pullback]
    span = bar["h"] - bar["l"]
    if span > 0 and (bar["h"] - max(bar["o"], bar["c"])) / span >= wick:
        return {"status": "wick_skip"}
    streak, previous = 1, bar["m"]
    for j in range(pullback + 1, window.stop):
        missed = (bars[j]["m"] - previous) // ONE - 1  # silent minutes keep the last close, at/below level
        previous = bars[j]["m"]
        if bars[j]["c"] > level:
            if streak + missed > 2:
                return {"status": "failed_reclaim"}
            low = min(b["l"] for b in bars[pullback:j + 1])
            stop, target = low - signals.tick(low), max(b["h"] for b in bars[i:pullback])
            t = trade(bars, j + 1, bars[j]["m"] + ONE, stop, cutoff, bars[j]["c"] * (1 + LIMIT), target=target)
            if t.get("entry", 0) >= target:
                return {"status": "entry_at_or_above_target"}
            return dict(t, stop=stop, target=target)
        streak += missed + 1
        if streak > 2:
            return {"status": "failed_reclaim"}
    return {"status": "no_reclaim"}


def _net(entry, exit_, entry_cost, exit_cost):
    return 100 * (exit_ * (1 - exit_cost) / (entry * (1 + entry_cost)) - 1)


def _verdict(trades, key, price_split=True):
    """HYPOTHESES pass rules for one cost column."""
    values = sorted(t[key] for t in trades)
    if len(values) < 2:
        return {"n": len(values), "pass": False}
    by_session, by_month, groups = {}, {}, {}
    for t in trades:
        by_session.setdefault(t["date"], []).append(t[key])
        by_month.setdefault(t["date"][:7], []).append(t[key])
        if price_split:
            groups.setdefault("price<2" if t["price"] < 2 else "price>=2", []).append(t[key])
        groups.setdefault("9:30-10:00" if t["minute"] < "10:00" else "10:00-11:00", []).append(t[key])
        groups.setdefault("%sQ%d" % (t["date"][:4], (int(t["date"][5:7]) - 1) // 3 + 1), []).append(t[key])
    total, low = sum(values), _bootstrap_low(by_session)
    up = sum(sum(v) > 0 for v in by_month.values())
    quarters = [sum(v) for g, v in groups.items() if "Q" in g]
    required = (["price<2", "price>=2"] if price_split else []) + ["9:30-10:00", "10:00-11:00"]
    checks = {"boot_low90_above_zero": low is not None and low > 0,
              "two_thirds_months_positive": 3 * up >= 2 * len(by_month),
              "positive_without_best": sum(values[:-1]) > 0,
              "every_group_positive": all(g in groups for g in required) and all(sum(v) > 0 for v in groups.values()),
              "no_quarter_over_half": total > 0 and max(quarters) <= total / 2}
    return {"n": len(values), "mean": round(total / len(values), 3), "median": round(values[len(values) // 2], 3),
            "boot_low90": round(low, 3) if low is not None else None, "mean_without_best": round(sum(values[:-1]) / (len(values) - 1), 3),
            "positive_months": "%d/%d" % (up, len(by_month)),
            "groups": {g: {"n": len(v), "mean": round(sum(v) / len(v), 3)} for g, v in sorted(groups.items())},
            "checks": checks, "pass": all(checks.values())}


def hypotheses(root=data.ROOT, months=SECOND_STUDY, which=("H1", "H2"), name="replay-v2"):
    """Score H1 (pullback and reclaim) and H2 (cheaper to trade) exactly as committed in HYPOTHESES."""
    if not HYPOTHESES.is_file():
        raise PermissionError("Commit HYPOTHESES before scoring H1 or H2.")
    base = data.readable(root, "discovery")
    sessions = signals._calendar(root)
    cohort = []
    for month in months:
        with gzip.open(base / ("%s-%s.csv.gz" % (name, month)), "rt") as handle:
            cohort += [r for r in csv.DictReader(handle) if r["arm"] == "c" and r["window"] == "primary"
                       and r["liquid"] == "True" and r["stop"] and r["gap_pct"]
                       and float(r["gap_pct"]) >= 20 and float(r["premarket_dollars"]) >= 1e6]
    spread_at, summary, trades = _spreads(base), {"months": list(months), "cohort": len(cohort)}, {}
    for h in which:
        rows = []
        for r in cohort:
            if h == "H1":
                bars = _day_bars(base, sessions, r["date"], r["ticker"])
                i = next(j for j, bar in enumerate(bars) if bar["m"].strftime("%H:%M") == r["minute"])
                t = reclaim(bars, i, float(r["resistance"]), _cutoff(*sessions[r["date"]]))
            elif float(r["close"]) >= 2 and float(r["dollar_volume"]) >= 1e5:
                t = {key[len("immediate_"):]: value for key, value in r.items() if key.startswith("immediate_")}
            else:
                continue
            row = {"date": r["date"], "ticker": r["ticker"], "minute": r["minute"], "price": float(r["close"]),
                   "gap40": float(r["gap_pct"]) >= 40, "status": t["status"], "exit_reason": t.get("exit_reason")}
            if t["status"] == "filled":
                entry, exit_ = float(t["entry"]), float(t["exit"])
                for cost in (0.005, 0.01, 0.02):
                    row["net@%g" % (cost * 100)] = _net(entry, exit_, cost, cost)
                if h == "H2":  # Alpaca has no quotes for delisted symbols
                    halves = (None, None) if r["delisted"] == "True" else (
                        spread_at(r["ticker"], r["date"], t["entry_at"]), spread_at(r["ticker"], r["date"], t["exit_at"]))
                    row["quoted"] = None not in halves
                    row["net@spread"] = _net(entry, exit_, *(halves if row["quoted"] else (0.005, 0.005)))
            rows.append(row)
        filled = [t for t in rows if t["status"] == "filled"]
        keys = (["net@spread"] if h == "H2" else []) + ["net@0.5", "net@1", "net@2"]
        statuses, reasons = {}, {}
        for t in rows:
            statuses[t["status"]] = statuses.get(t["status"], 0) + 1
        for t in filled:
            reasons[t["exit_reason"]] = reasons.get(t["exit_reason"], 0) + 1
        summary[h] = {"opportunities": len(rows), "statuses": statuses, "exit_reasons": reasons,
                      "decides": keys[0], "pass": _verdict(filled, keys[0], h == "H1")["pass"],
                      **{key: _verdict(filled, key, h == "H1") for key in keys},
                      "gap40_subgroup": _verdict([t for t in filled if t["gap40"]], keys[0], h == "H1")}
        if h == "H2":
            summary[h]["quoted_fills"] = sum(t["quoted"] for t in filled)
        trades[h] = rows
    (base / ("hypotheses-%s_%s.json" % (months[0], months[-1]))).write_text(json.dumps(summary, indent=2) + "\n")
    return summary, trades


def exit_variants(root=data.ROOT, months=("2025-10", "2025-11", "2025-12"), arm="c", gap=40.0,
                  premarket=1e6, rules=("fixed", "breakeven_1r", "trail_1.5atr", "trail_3atr"), cost=0.0025):
    """Replay one rule's liquid primary immediate fills under alternative stop management."""
    base = data.readable(root, "discovery")
    selected = []
    for month in months:
        with gzip.open(base / ("replay-%s.csv.gz" % month), "rt") as handle:
            selected += [r for r in csv.DictReader(handle) if r["arm"] == arm and r["window"] == "primary"
                         and r["liquid"] == "True" and r.get("immediate_status") == "filled" and r["gap_pct"]
                         and float(r["gap_pct"]) >= gap and float(r["premarket_dollars"]) >= premarket]
    sessions = signals._calendar(root)
    trades = {rule: [] for rule in rules}
    for r in selected:
        day_bars = _day_bars(base, sessions, r["date"], r["ticker"])
        k = next(i for i, bar in enumerate(day_bars) if bar["m"].strftime("%H:%M") == r["immediate_entry_at"])
        for rule in rules:
            exit_, reason = managed_trade(day_bars, k, float(r["stop"]), float(r["atr"]), rule)
            trades[rule].append({"date": r["date"], "ticker": r["ticker"], "entry_at": r["immediate_entry_at"],
                                 "entry": float(r["immediate_entry"]), "exit": exit_, "stop": float(r["stop"]),
                                 "reason": reason, "check": float(r["immediate_exit"])})
    return {rule: simulate(trades[rule], cost) for rule in rules}, trades


def export_losers(root=data.ROOT, months=("2025-10",), cost=0.0025):
    """CSV of the candidate rule's losing account trades with entry context, for outside investigation."""
    base = data.readable(root, "discovery")
    results, _ = exit_variants(root, months=months, rules=("fixed",), cost=cost)
    replayed = {}
    for month in months:
        with gzip.open(base / ("replay-%s.csv.gz" % month), "rt") as handle:
            for r in csv.DictReader(handle):
                if r["arm"] == "c" and r["window"] == "primary":
                    replayed[(r["date"], r["ticker"], r["immediate_entry_at"])] = r
    losers = []
    for t in results["fixed"]["trades"]:
        if t["pnl"] > 0:
            continue
        r = replayed[(t["date"], t["ticker"], t["entry_at"])]
        losers.append({
            "date": t["date"], "ticker": t["ticker"], "signal_minute": r["minute"],
            "entry_time": r["immediate_entry_at"], "exit_time": r["immediate_exit_at"],
            "exit_reason": r["immediate_exit_reason"], "premarket_high": r["resistance"],
            "signal_close": r["close"], "entry_price": t["entry"], "exit_price": t["exit"], "stop": t["stop"],
            "stop_pct": round(100 * (t["entry"] - t["stop"]) / t["entry"], 3), "shares": t["shares"],
            "pnl_usd": round(t["pnl"], 2), "return_pct_gross": round(100 * (t["exit"] / t["entry"] - 1), 3),
            "r_net": round(net_r(t["entry"], t["exit"], t["stop"], cost), 3),
            "gap_pct": round(float(r["gap_pct"]), 2), "premarket_dollars": round(float(r["premarket_dollars"])),
            "signal_dollar_volume": round(float(r["dollar_volume"])), "atr14": r["atr"],
            "entry_delay_min": r["immediate_entry_delay"], "max_gap_min_in_hold": r["immediate_max_gap"],
            "continuation_label": r["continuation"], "advance_atr": r["advance_atr"],
            "pullback_depth_atr": r["pullback_depth_atr"],
            **{key: r[key] for key in ("b_upper", "b_lower", "b_body", "b_close_loc", "b_range_atr", "b_vol_ratio")},
            "minute_bars_file": str(base / "raw" / "minute" / t["date"][:7] / (quote_name(t["ticker"]) + ".json.gz"))})
    path = base / ("losers-%s_%s.csv" % (months[0], months[-1]))
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, list(losers[0]))
        writer.writeheader()
        writer.writerows(losers)
    return path, losers
