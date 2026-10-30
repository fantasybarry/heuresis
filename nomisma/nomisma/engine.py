"""Deterministic, explainable end-of-day technical screening.

Scores are a hand-authored ranking of historical technical conditions, not
estimated probabilities or a backtested trading strategy. Price returns exclude
dividends. EMA is seeded with SMA; RSI and ATR use Wilder's smoothing. Sources:
https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/RSI
https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/atr
https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/macd
https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/ema
"""

import math
import re
from collections import Counter
from datetime import date, datetime, timezone


DEFAULT_FILTERS = {
    "min_price": 10,
    "max_price": 1000,
    "min_avg_volume": 500000,
    "min_relative_volume": 1.0,
    "min_rsi": 45,
    "max_rsi": 75,
    "min_score": 55,
    "above_sma50": True,
    "above_sma200": False,
    "positive_macd": False,
    "min_return_20d": 0,
    "max_atr_pct": 10,
    "sectors": [],
}


def _preset(identifier, name, description, **changes):
    filters = dict(DEFAULT_FILTERS, sectors=[])
    filters.update(changes)
    return {"id": identifier, "name": name, "description": description, "filters": filters}


PRESETS = [
    _preset("balanced", "Balanced bullish", "Liquid stocks with constructive trend and momentum."),
    _preset("momentum", "Momentum leaders", "Established uptrends with stronger participation.",
            min_score=70, min_relative_volume=1.25, above_sma200=True,
            positive_macd=True, min_return_20d=3),
    _preset("early", "Early strength", "A wider search for improving momentum; mixed trends are allowed.",
            min_score=40, min_relative_volume=0.8, min_rsi=40, max_rsi=70,
            above_sma50=False, positive_macd=True, min_return_20d=-3),
    _preset("steady", "Steady trends", "Liquid long-term trends with lower daily price ranges.",
            min_score=60, min_avg_volume=1000000, min_relative_volume=0.8,
            max_rsi=68, above_sma200=True, max_atr_pct=4),
]

_BOUNDS = {
    "min_price": (0, 10000000), "max_price": (0.01, 10000000),
    "min_avg_volume": (0, 1000000000000), "min_relative_volume": (0, 1000),
    "min_rsi": (0, 100), "max_rsi": (0, 100), "min_score": (0, 100),
    "min_return_20d": (-100, 100000), "max_atr_pct": (0, 1000),
}
_BOOLEAN_FIELDS = ("above_sma50", "above_sma200", "positive_macd")
_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9./-]{0,14}\Z")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")


def _number(value, minimum=0, maximum=1e15):
    """True for a finite non-bool int/float within [minimum, maximum]."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value) and minimum <= value <= maximum
    except (OverflowError, ValueError):
        return False


def validate_filters(filters):
    """Merge partial filters with defaults, validating without coercing strings."""
    if not isinstance(filters, dict):
        raise ValueError("Filters must be an object.")
    unknown = set(filters) - set(DEFAULT_FILTERS)
    if unknown:
        raise ValueError("Unknown filter: {}.".format(", ".join(sorted(map(str, unknown)))))
    result = dict(DEFAULT_FILTERS)
    result.update(filters)
    for key, (minimum, maximum) in _BOUNDS.items():
        value = result[key]
        if not _number(value, minimum, maximum):
            raise ValueError("{} must be a finite number between {} and {}.".format(key, minimum, maximum))
    for key in _BOOLEAN_FIELDS:
        if not isinstance(result[key], bool):
            raise ValueError("{} must be true or false.".format(key))
    if result["min_price"] > result["max_price"]:
        raise ValueError("min_price cannot exceed max_price.")
    if result["min_rsi"] > result["max_rsi"]:
        raise ValueError("min_rsi cannot exceed max_rsi.")
    sectors = result["sectors"]
    if not isinstance(sectors, list) or len(sectors) > 100:
        raise ValueError("sectors must be a list of at most 100 sector names.")
    normalized = {}
    for sector in sectors:
        if not isinstance(sector, str) or not sector.strip() or len(sector) > 100:
            raise ValueError("Each sector must be a nonempty name of at most 100 characters.")
        if any(ord(char) < 32 for char in sector):
            raise ValueError("Sector names cannot contain control characters.")
        normalized.setdefault(sector.strip().casefold(), sector.strip())
    result["sectors"] = [normalized[key] for key in sorted(normalized)]
    return result


def _date(value):
    if not isinstance(value, str) or not _DATE.match(value):
        raise ValueError("Dates must use YYYY-MM-DD.")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError("Invalid calendar date: {}.".format(value)) from None


def _today():
    return datetime.now(timezone.utc).date()


def _validated_bars(raw, cutoff):
    """Reject malformed histories as a whole; never silently repair price data."""
    if not isinstance(raw, list):
        raise ValueError("Bars must be a list.")
    bars = []
    previous = None
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Each bar must be an object.")
        session = _date(item.get("date"))
        if session > cutoff:
            raise ValueError("A bar is later than the dataset as_of date.")
        if previous is not None and session <= previous:
            raise ValueError("Bar dates must be unique and strictly increasing.")
        values = {}
        for key in ("open", "high", "low", "close", "volume"):
            value = item.get(key)
            maximum = 1000000000000000 if key == "volume" else 1000000000
            # Plain finite ints and floats pass the range test directly; NaN and infinity fail it.
            # Anything else gets the full check. Validation runs for millions of bars per scan.
            if not ((type(value) is float or type(value) is int) and 0 <= value <= maximum) and not _number(value, 0, maximum):
                raise ValueError("Invalid {} value.".format(key))
            if key != "volume" and value < 0.000001:
                raise ValueError("OHLC prices must be at least $0.000001.")
            values[key] = float(value)
        if values["low"] > min(values["open"], values["close"]) or values["high"] < max(values["open"], values["close"]):
            raise ValueError("OHLC prices are inconsistent.")
        values["date"] = item["date"]
        bars.append(values)
        previous = session
    return bars


def _ema(values, period):
    """Aligned EMA series; the first period-1 entries have no value."""
    if period < 1 or len(values) < period:
        raise ValueError("Not enough observations for EMA.")
    result = [None] * (period - 1)
    value = math.fsum(values[:period]) / period
    result.append(value)
    alpha = 2.0 / (period + 1)
    for current in values[period:]:
        value += alpha * (current - value)
        result.append(value)
    return result


def _rsi(closes, period=14):
    if period < 1 or len(closes) < period + 1:
        raise ValueError("Not enough observations for RSI.")
    changes = [current - previous for previous, current in zip(closes, closes[1:])]
    gain = math.fsum(max(change, 0.0) for change in changes[:period]) / period
    loss = math.fsum(max(-change, 0.0) for change in changes[:period]) / period
    for change in changes[period:]:
        gain = (gain * (period - 1) + max(change, 0.0)) / period
        loss = (loss * (period - 1) + max(-change, 0.0)) / period
    # A completely flat history is neutral, not infinitely strong or weak.
    if loss == 0:
        return 100.0 if gain > 0 else 50.0
    return 100.0 - 100.0 / (1.0 + gain / loss)


def _atr(bars, period=14):
    if period < 1 or len(bars) < period + 1:
        raise ValueError("Not enough observations for ATR.")
    ranges = [max(current["high"] - current["low"],
                  abs(current["high"] - previous["close"]),
                  abs(current["low"] - previous["close"]))
              for previous, current in zip(bars, bars[1:])]
    value = math.fsum(ranges[:period]) / period
    for current in ranges[period:]:
        value = (value * (period - 1) + current) / period
    return value


def _percent(current, previous):
    return (current / previous - 1.0) * 100.0


def _metrics(bars, benchmark):
    closes = [bar["close"] for bar in bars]
    price = closes[-1]
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd_series = [ema12[i] - ema26[i] for i in range(25, len(closes))]
    signal = _ema(macd_series, 9)[-1]
    atr = _atr(bars)
    average_volume = math.fsum(bar["volume"] for bar in bars[-21:-1]) / 20
    return_20d = _percent(price, closes[-21])
    relative_strength = None
    # An exact date match avoids comparing unequal periods when an asset has gaps.
    if benchmark and len(benchmark) >= 21:
        stock_dates = [bar["date"] for bar in bars[-21:]]
        if stock_dates == [bar["date"] for bar in benchmark[-21:]]:
            relative_strength = return_20d - _percent(benchmark[-1]["close"], benchmark[-21]["close"])
    return {
        "rsi": _rsi(closes), "relative_volume": bars[-1]["volume"] / average_volume,
        "avg_volume": average_volume,
        "sma20": math.fsum(closes[-20:]) / 20,
        "sma50": math.fsum(closes[-50:]) / 50,
        "sma200": math.fsum(closes[-200:]) / 200,
        "ema12": ema12[-1], "ema26": ema26[-1],
        "macd": macd_series[-1], "macd_signal": signal,
        "macd_histogram": macd_series[-1] - signal,
        "atr": atr, "atr_pct": atr / price * 100,
        "return_20d": return_20d, "relative_strength": relative_strength,
        "breakout_distance": _percent(price, max(bar["high"] for bar in bars[-21:-1])),
    }


def _clamp(value):
    return min(1.0, max(0.0, value))


def _signals(bars, metrics):
    price = bars[-1]["close"]
    m = metrics
    prior_sma50 = math.fsum(bar["close"] for bar in bars[-51:-1]) / 50
    trend = (10 * (price > m["sma50"]) + 10 * (price > m["sma200"])
             + 10 * (m["sma50"] > m["sma200"]) + 5 * (m["sma50"] > prior_sma50))
    rsi = m["rsi"]
    rsi_points = 10 if 50 <= rsi <= 65 else 7 if 45 <= rsi <= 70 else 3 if 70 < rsi <= 75 else 0
    momentum = rsi_points + 5 * (m["macd"] > 0) + 5 * (m["macd_histogram"] > 0) + 5 * _clamp(m["return_20d"] / 10)
    up_day = price > bars[-2]["close"]
    volume = 20 * _clamp((m["relative_volume"] - 0.5) / 1.5) if up_day else 0
    relative = m["relative_strength"]
    rs_points = 15 * _clamp(relative / 10) if relative is not None else 0
    distance = m["breakout_distance"]
    breakout = 0
    if price > m["sma50"] and m["return_20d"] > 0 and -5 <= distance <= 5:
        breakout = 5 * _clamp(1 + min(0, distance) / 5)
    return [
        {"name": "Trend", "points": round(trend, 2), "max_points": 35,
         "description": "10 each for close above SMA50, close above SMA200 and SMA50 above SMA200; 5 for SMA50 rising since the prior session."},
        {"name": "Momentum", "points": round(momentum, 2), "max_points": 25,
         "description": "RSI: 10 at 50–65, 7 at 45–50 or 65–70, 3 at 70–75, otherwise 0. MACD above zero and above signal: 5 each. Positive 20-session return: 0–5, reaching 5 at +10%."},
        {"name": "Volume", "points": round(volume, 2), "max_points": 20,
         "description": "On a positive close-to-close session, participation earns 0–20 points as volume rises from 0.5× to 2× the prior 20-session average; a flat or down session earns 0."},
        {"name": "Relative strength", "points": round(rs_points, 2), "max_points": 15,
         "description": "0–15 points for outperforming SPY over the same 20 sessions; 15 at +10 percentage points. Missing or misaligned SPY data earns 0 and is flagged."},
        {"name": "Breakout proximity", "points": round(breakout, 2), "max_points": 5,
         "description": "With close above SMA50 and positive 20-session return, 0–5 points from 5% below to the prior 20-session high; 5 through 5% above, then 0 for extension."},
    ]


def _risks(bars, metrics, market):
    m = metrics
    risks = []
    if m["rsi"] > 70:
        risks.append("RSI above 70: momentum is extended and may reverse.")
    if m["atr_pct"] > 5:
        risks.append("ATR exceeds 5% of price: daily swings are elevated.")
    if m["relative_volume"] < 1:
        risks.append("Latest session volume is below its prior 20-session average.")
    if bars[-1]["volume"] == 0:
        risks.append("Latest bar has zero volume; confirm whether the instrument traded.")
    if bars[-1]["close"] <= m["sma200"]:
        risks.append("Price has not cleared its 200-session average.")
    if m["macd_histogram"] < 0:
        risks.append("MACD is below its signal line.")
    if m["breakout_distance"] > 5 or _percent(bars[-1]["close"], m["sma20"]) > 10:
        risks.append("Price is extended above a recent high or short-term average.")
    if m["relative_strength"] is None:
        risks.append("Aligned SPY history is unavailable; relative strength earns 0 of 15 points.")
    elif m["relative_strength"] < 0:
        risks.append("The stock trails SPY over the last 20 sessions.")
    if market is not None and not market["above_sma50"]:
        risks.append("SPY is below its 50-session average: broad-market trend is weak.")
    if any((_date(right["date"]) - _date(left["date"])).days > 7
           for left, right in zip(bars[-51:], bars[-50:])):
        risks.append("Recent history contains a gap longer than 7 calendar days; indicators use observed bars.")
    return risks


def _filter_failures(price, metrics, score, sector, filters):
    m, f = metrics, filters
    checks = [
        ("price", f["min_price"] <= price <= f["max_price"]),
        ("average_volume", m["avg_volume"] >= f["min_avg_volume"]),
        ("relative_volume", m["relative_volume"] >= f["min_relative_volume"]),
        ("rsi", f["min_rsi"] <= m["rsi"] <= f["max_rsi"]),
        ("score", score >= f["min_score"]),
        ("sma50", not f["above_sma50"] or price > m["sma50"]),
        ("sma200", not f["above_sma200"] or price > m["sma200"]),
        ("macd", not f["positive_macd"] or m["macd_histogram"] > 0),
        ("return_20d", m["return_20d"] >= f["min_return_20d"]),
        ("atr", m["atr_pct"] <= f["max_atr_pct"]),
        ("sector", not f["sectors"] or sector.casefold() in {item.casefold() for item in f["sectors"]}),
    ]
    return [reason for reason, passed in checks if not passed]


def _metadata(asset, key, default):
    value = asset.get(key, default)
    return value[:300] if isinstance(value, str) and value.strip() else default


def screen(dataset, filters):
    """Screen supplied completed bars, returning only JSON-safe values.

    eligible_count means histories suitable for computation, before user filters.
    Rejected filter counts are nonexclusive: one stock may fail multiple filters.
    The only clock-dependent behavior is the overall stale-data warning (>5 days).
    positive_macd means MACD above its signal, including a recovery below zero.
    """
    filters = validate_filters(filters)
    if not isinstance(dataset, dict):
        raise ValueError("Dataset must be an object.")
    if dataset.get("source") not in ("demo", "alpaca", "csv"):
        raise ValueError("Dataset source must be demo, alpaca or csv.")
    cutoff = _date(dataset.get("as_of"))
    if cutoff > _today():
        raise ValueError("Dataset as_of cannot be in the future.")
    assets = dataset.get("assets")
    if not isinstance(assets, list):
        raise ValueError("Dataset assets must be a list.")
    provided_warnings = dataset.get("warnings", [])
    if not isinstance(provided_warnings, list) or any(not isinstance(item, str) for item in provided_warnings):
        raise ValueError("Dataset warnings must be a list of strings.")
    warnings = list(dict.fromkeys(provided_warnings))
    if dataset["source"] == "demo":
        warnings.append("Synthetic demonstration data; prices and rankings are fictional, not current market observations.")
    rejected = Counter()
    validated = []
    symbol_counts = Counter(asset.get("symbol", "").strip().upper()
                            for asset in assets if isinstance(asset, dict) and isinstance(asset.get("symbol"), str))
    for asset in assets:
        if not isinstance(asset, dict) or not isinstance(asset.get("symbol"), str):
            rejected["invalid_data"] += 1
            continue
        symbol = asset["symbol"].strip().upper()
        if not _SYMBOL.fullmatch(symbol):
            rejected["invalid_data"] += 1
            continue
        if symbol_counts[symbol] > 1:
            rejected["duplicate_symbol"] += 1
            continue
        try:
            bars = _validated_bars(asset.get("bars"), cutoff)
        except ValueError:
            rejected["invalid_data"] += 1
            continue
        validated.append((asset, symbol, bars))

    benchmark = None
    raw_benchmark = dataset.get("benchmark")
    if raw_benchmark is not None:
        try:
            if not isinstance(raw_benchmark, dict) or raw_benchmark.get("symbol") != "SPY":
                raise ValueError("Benchmark must be SPY.")
            benchmark = _validated_bars(raw_benchmark.get("bars"), cutoff)
        except ValueError:
            warnings.append("SPY benchmark data is invalid and was excluded.")
            benchmark = None

    latest_dates = [bars[-1]["date"] for _, _, bars in validated if bars]
    if benchmark:
        latest_dates.append(benchmark[-1]["date"])
    as_of = max(latest_dates) if latest_dates else cutoff.isoformat()
    if as_of != cutoff.isoformat():
        warnings.append("Latest available bar is {}; dataset requested {}.".format(as_of, cutoff.isoformat()))
    age = (_today() - _date(as_of)).days
    if age > 5:
        warnings.append("Data is stale: the latest session is {} ({} calendar days old).".format(as_of, age))
    if benchmark and benchmark[-1]["date"] != as_of:
        warnings.append("SPY benchmark is older than the latest asset session and was excluded.")
        benchmark = None
    if not benchmark or len(benchmark) < 21:
        warnings.append("SPY history is unavailable or insufficient; relative strength earns 0 of 15 points.")
    market = None
    if benchmark and len(benchmark) >= 50:
        market = {
            "symbol": "SPY", "price": round(benchmark[-1]["close"], 6),
            "change_pct": round(_percent(benchmark[-1]["close"], benchmark[-2]["close"]), 6),
            "return_20d": round(_percent(benchmark[-1]["close"], benchmark[-21]["close"]), 6),
            "above_sma50": benchmark[-1]["close"] > math.fsum(bar["close"] for bar in benchmark[-50:]) / 50,
            "chart": [{"date": bar["date"], "close": round(bar["close"], 6)} for bar in benchmark[-120:]],
        }

    results = []
    eligible = 0
    for asset, symbol, bars in validated:
        if len(bars) < 201:
            rejected["insufficient_history"] += 1
            continue
        if bars[-1]["date"] != as_of:
            rejected["stale_symbol"] += 1
            continue
        if not any(bar["volume"] > 0 for bar in bars[-21:-1]):
            rejected["unavailable_volume"] += 1
            continue
        try:
            metrics = _metrics(bars, benchmark)
        except (ArithmeticError, ValueError):
            rejected["invalid_data"] += 1
            continue
        if any(value is not None and not _number(value, -math.inf, math.inf) for value in metrics.values()):
            rejected["invalid_data"] += 1
            continue
        signals = _signals(bars, metrics)
        score = round(sum(signal["points"] for signal in signals), 2)
        sector = _metadata(asset, "sector", "Unknown")
        eligible += 1
        failures = _filter_failures(bars[-1]["close"], metrics, score, sector, filters)
        if failures:
            rejected.update(failures)
            continue
        if (0 <= metrics["breakout_distance"] <= 5 and metrics["relative_volume"] >= 1.5
                and bars[-1]["close"] > metrics["sma50"] and bars[-1]["close"] > bars[-2]["close"]):
            setup = "Volume breakout"
        elif signals[0]["points"] >= 30 and signals[1]["points"] >= 12:
            setup = "Trend continuation"
        elif metrics["macd_histogram"] > 0 and metrics["return_20d"] > 0:
            setup = "Momentum building"
        else:
            setup = "Mixed signals"
        results.append({
            "symbol": symbol, "name": _metadata(asset, "name", symbol), "sector": sector,
            "exchange": _metadata(asset, "exchange", "Unknown"),
            "price": round(bars[-1]["close"], 6),
            "change_pct": round(_percent(bars[-1]["close"], bars[-2]["close"]), 6),
            "score": score, "setup": setup, "as_of": as_of,
            "metrics": {key: round(value, 6) if value is not None else None for key, value in metrics.items()},
            "signals": signals, "risks": _risks(bars, metrics, market),
            "chart": [{"date": bar["date"], "close": round(bar["close"], 6), "volume": bar["volume"]} for bar in bars[-120:]],
        })
    results.sort(key=lambda item: (-item["score"], item["symbol"]))
    if rejected["invalid_data"]:
        warnings.append("{} symbols excluded for invalid, unordered, duplicate-date or future bars.".format(rejected["invalid_data"]))
    if rejected["duplicate_symbol"]:
        warnings.append("{} duplicate symbol entries were excluded to avoid ambiguous histories.".format(rejected["duplicate_symbol"]))
    if rejected["stale_symbol"]:
        warnings.append("{} symbols excluded because their latest bar predates {}.".format(rejected["stale_symbol"], as_of))
    return {
        "as_of": as_of, "source": dataset["source"],
        "label": _metadata(dataset, "label", dataset["source"].title()),
        "feed": _metadata(dataset, "feed", dataset["source"]),
        "warnings": list(dict.fromkeys(warnings)), "universe_count": len(assets),
        "eligible_count": eligible, "matched_count": len(results),
        "rejected": dict(sorted((key, count) for key, count in rejected.items() if count)),
        "results": results, "market": market, "filters": filters,
    }
