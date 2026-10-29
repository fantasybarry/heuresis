"""Pure historical liquidity/volatility measurements and transparent ranking.

Daily calculations exclude the active session. Missing history is unavailable,
never replaced by a shorter lookback with the same label.
"""

from datetime import date, timedelta
import math

from .engine import _number


RANKING_WEIGHTS = {"day_volume": 15, "avg_volume_3m": 10, "avg_daily_volume": 10,
                   "day_relative_volume": 20, "spread_pct": 15, "beta": 10, "atr_pct": 20}


def _date(value):
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _bars(values, session):
    found, conflicts = {}, set()
    for value in values if isinstance(values, (list, tuple)) else []:
        if not isinstance(value, dict):
            continue
        day = _date(value.get("date"))
        if day is None or day >= session or day.weekday() >= 5:
            continue
        if (not all(_number(value.get(field), 0, math.inf) for field in ("open", "high", "low", "close", "volume"))
                or any(value[field] <= 0 for field in ("open", "high", "low", "close"))
                or value["low"] > min(value["open"], value["close"])
                or value["high"] < max(value["open"], value["close"])):
            continue
        normalized = {field: value[field] for field in ("open", "high", "low", "close", "volume")}
        normalized["date"] = day.isoformat()
        if day in found and found[day] != normalized:
            conflicts.add(day)
        found[day] = normalized
    return [found[day] for day in sorted(found) if day not in conflicts]


def history_metrics(bars, benchmark_bars, session_date, previous_session_date=None):
    """Compute completed-session metrics; callers may supply the exchange's prior date.

    Beta pairs one-session simple returns with SPY, using identical start/end
    dates. ATR is seeded by the first 14 true ranges, then Wilder-smoothed.
    """
    session = _date(session_date)
    if session is None:
        raise ValueError("Historical metrics need a valid session date.")
    stock, benchmark = _bars(bars, session), _bars(benchmark_bars, session)
    expected = _date(previous_session_date)
    if previous_session_date is not None and (expected is None or expected >= session):
        raise ValueError("The previous session must precede the active session.")
    if expected is None:
        # Without an exchange calendar, stay conservative instead of declaring
        # an old stock/SPY pair current merely because both feeds stopped early.
        # Callers supply previous_session_date to account for exchange holidays.
        expected = session - timedelta(days=1)
        while expected.weekday() >= 5:
            expected -= timedelta(days=1)
    expected_text = expected.isoformat()
    result = {"avg_volume_3m": None, "avg_daily_volume": None, "beta": None, "beta_observations": 0,
              "atr": None, "atr_pct": None, "history_as_of": stock[-1]["date"] if stock else None,
              "history_expected_as_of": expected_text, "history_sessions": len(stock), "metric_availability": {}}
    availability = result["metric_availability"]
    current = bool(stock and stock[-1]["date"] == expected_text)
    stale_reason = "History does not reach the previous exchange session ({}).".format(expected_text)
    stock_dates = {bar["date"] for bar in stock}
    stock_by_date = {bar["date"]: bar for bar in stock}
    benchmark_current = bool(benchmark and benchmark[-1]["date"] == expected_text)

    def available(field, reason):
        availability[field] = {"available": result[field] is not None,
                               "reason": None if result[field] is not None else reason}

    for field, count in (("avg_volume_3m", 63), ("avg_daily_volume", 20)):
        benchmark_dates = [bar["date"] for bar in benchmark[-count:]]
        complete = benchmark_current and len(benchmark_dates) == count and all(day in stock_dates for day in benchmark_dates)
        if current and complete:
            result[field] = sum(stock_by_date[day]["volume"] for day in benchmark_dates) / count
        available(field, stale_reason if not current else "Need {} complete prior sessions of stock volume and current SPY session coverage.".format(count))

    benchmark_dates = {bar["date"] for bar in benchmark}
    continuous = (benchmark_current and len(benchmark) >= 15 and stock_dates <= benchmark_dates
                  and all(bar["date"] in stock_dates for bar in benchmark if stock and bar["date"] >= stock[0]["date"]))
    if current and len(stock) >= 15 and continuous:
        ranges = [max(bar["high"] - bar["low"], abs(bar["high"] - prior["close"]),
                      abs(bar["low"] - prior["close"])) for prior, bar in zip(stock, stock[1:])]
        atr = sum(ranges[:14]) / 14
        for true_range in ranges[14:]:
            atr = (13 * atr + true_range) / 14
        result["atr"], result["atr_pct"] = atr, 100 * atr / stock[-1]["close"]
    available("atr", stale_reason if not current else "Need at least 15 continuous prior daily bars for Wilder ATR(14).")
    available("atr_pct", availability["atr"]["reason"])

    if current and benchmark_current:
        market_returns = {(previous["date"], bar["date"]): bar["close"] / previous["close"] - 1
                          for previous, bar in zip(benchmark, benchmark[1:])}
        aligned = [(bar["close"] / previous["close"] - 1, market_returns[(previous["date"], bar["date"])])
                   for previous, bar in zip(stock, stock[1:])
                   if (previous["date"], bar["date"]) in market_returns][-252:]
        result["beta_observations"] = len(aligned)
        if len(aligned) >= 60:
            stock_mean = sum(value[0] for value in aligned) / len(aligned)
            market_mean = sum(value[1] for value in aligned) / len(aligned)
            variance = sum((value[1] - market_mean) ** 2 for value in aligned)
            if variance > 1e-18:
                result["beta"] = sum((value[0] - stock_mean) * (value[1] - market_mean)
                                     for value in aligned) / variance
    beta_reason = (stale_reason if not current else "SPY history does not reach the previous exchange session."
                   if not benchmark_current else "Need at least 60 aligned daily returns with nonzero SPY variance.")
    available("beta", beta_reason)
    return result


def rank_rows(rows):
    """Assign cross-sectional ranks without hiding rows or changing input order.

    Percentiles use average ranks for ties; a lone available value receives
    100%. Missing metrics and nonpositive beta earn zero points. The full
    100-point denominator remains fixed, so incomplete rows are not inflated.
    """
    percentiles = {}
    def measured(row, field):
        if field == "spread_pct" and row.get("spread_fresh") is False:
            return False
        if field in ("day_volume", "day_relative_volume") and row.get("day_volume_fresh") is False:
            return False
        return _number(row.get(field), -math.inf, math.inf) if field == "beta" else _number(row.get(field), 0, math.inf)

    for field in RANKING_WEIGHTS:
        values = sorted(row[field] for row in rows if measured(row, field)
                        and (field != "beta" or row[field] > 0))
        ranks = {}
        for index, value in enumerate(values):
            ranks.setdefault(value, []).append(index)
        percentiles[field] = {value: (1 if len(values) == 1 else (positions[0] + positions[-1]) / 2 / (len(values) - 1))
                              for value, positions in ranks.items()}
        if field == "spread_pct":
            percentiles[field] = {value: 1 - percentile if len(values) > 1 else 1
                                  for value, percentile in percentiles[field].items()}
    for row in rows:
        components, missing, score = {}, [], 0.0
        for field, weight in RANKING_WEIGHTS.items():
            value = row.get(field)
            known = measured(row, field)
            percentile = percentiles[field].get(value, 0) if known else 0
            points = percentile * weight
            if not known:
                missing.append(field)
            components[field] = {"value": value if known else None, "weight": weight,
                                 "available": known, "percentile": round(percentile * 100, 2),
                                 "points": round(points, 2)}
            score += points
        row.update(liquidity_volatility_score=round(score, 2), ranking_components=components,
                   ranking_available_metrics=len(RANKING_WEIGHTS) - len(missing), ranking_missing_metrics=missing,
                   ranking_metric_coverage_pct=round(100 * (len(RANKING_WEIGHTS) - len(missing)) / len(RANKING_WEIGHTS), 1))
    # Rank is simply total day volume, highest first; stale or missing volume ranks last.
    for index, row in enumerate(sorted(rows, key=lambda item: (-(item["day_volume"] if measured(item, "day_volume") else -1), item["symbol"]))):
        row["rank"] = index + 1
    return rows
