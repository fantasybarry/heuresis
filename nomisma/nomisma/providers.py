"""Validated daily market data sources. No trading or order endpoints are used.

Alpaca references:
https://docs.alpaca.markets/us/reference/stockbars
https://docs.alpaca.markets/us/reference/legacycalendar
https://docs.alpaca.markets/us/reference/get-v2-assets-1
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import date, datetime, time as daytime, timedelta, timezone
import io
import json
import math
import os
import random
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo


MAX_CSV_BYTES = 20 * 1024 * 1024
MAX_RESPONSE_BYTES = 32 * 1024 * 1024
MAX_CUSTOM_SYMBOLS = 1000
# About 310 daily bars × 32 symbols fits one 10,000-bar page, so most batches need a single request.
BATCH_SIZE = 32
FETCH_WORKERS = 16
DEMO_AS_OF = "2025-12-31"
_NY = ZoneInfo("America/New_York")
_SYMBOL = re.compile(r"[A-Z][A-Z0-9]{0,9}(?:[.\-][A-Z0-9]{1,4})?\Z")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_HOSTS = {"data.alpaca.markets", "paper-api.alpaca.markets", "api.alpaca.markets"}

# An explicit starter universe, not an index membership claim. Metadata is
# maintained locally because Alpaca's assets endpoint does not supply sectors.
_CURATED = (
    ("NVDA", "NVIDIA", "Technology", "NASDAQ", 138, 42000000),
    ("MSFT", "Microsoft", "Technology", "NASDAQ", 432, 24000000),
    ("AAPL", "Apple", "Technology", "NASDAQ", 224, 48000000),
    ("AVGO", "Broadcom", "Technology", "NASDAQ", 186, 20000000),
    ("AMD", "Advanced Micro Devices", "Technology", "NASDAQ", 154, 37000000),
    ("CRM", "Salesforce", "Technology", "NYSE", 282, 6500000),
    ("ORCL", "Oracle", "Technology", "NYSE", 158, 10000000),
    ("ADBE", "Adobe", "Technology", "NASDAQ", 478, 3400000),
    ("NOW", "ServiceNow", "Technology", "NYSE", 884, 1500000),
    ("PANW", "Palo Alto Networks", "Technology", "NASDAQ", 188, 5400000),
    ("GOOGL", "Alphabet", "Communication Services", "NASDAQ", 182, 26000000),
    ("META", "Meta Platforms", "Communication Services", "NASDAQ", 546, 15000000),
    ("NFLX", "Netflix", "Communication Services", "NASDAQ", 738, 3800000),
    ("DIS", "Walt Disney", "Communication Services", "NYSE", 104, 10000000),
    ("AMZN", "Amazon", "Consumer Discretionary", "NASDAQ", 198, 34000000),
    ("TSLA", "Tesla", "Consumer Discretionary", "NASDAQ", 264, 76000000),
    ("HD", "Home Depot", "Consumer Discretionary", "NYSE", 378, 3800000),
    ("LOW", "Lowe's", "Consumer Discretionary", "NYSE", 246, 2600000),
    ("JPM", "JPMorgan Chase", "Financials", "NYSE", 226, 8700000),
    ("GS", "Goldman Sachs", "Financials", "NYSE", 526, 2200000),
    ("V", "Visa", "Financials", "NYSE", 302, 6100000),
    ("MA", "Mastercard", "Financials", "NYSE", 494, 2300000),
    ("BAC", "Bank of America", "Financials", "NYSE", 43, 34000000),
    ("WFC", "Wells Fargo", "Financials", "NYSE", 65, 15000000),
    ("LLY", "Eli Lilly", "Health Care", "NYSE", 784, 2900000),
    ("UNH", "UnitedHealth Group", "Health Care", "NYSE", 548, 3200000),
    ("ABBV", "AbbVie", "Health Care", "NYSE", 184, 5500000),
    ("JNJ", "Johnson & Johnson", "Health Care", "NYSE", 158, 6900000),
    ("MRK", "Merck", "Health Care", "NYSE", 108, 8700000),
    ("ISRG", "Intuitive Surgical", "Health Care", "NASDAQ", 512, 1700000),
    ("COST", "Costco", "Consumer Staples", "NASDAQ", 898, 2100000),
    ("WMT", "Walmart", "Consumer Staples", "NASDAQ", 92, 16000000),
    ("PG", "Procter & Gamble", "Consumer Staples", "NYSE", 168, 5800000),
    ("KO", "Coca-Cola", "Consumer Staples", "NYSE", 64, 12000000),
    ("XOM", "Exxon Mobil", "Energy", "NYSE", 118, 16000000),
    ("CVX", "Chevron", "Energy", "NYSE", 152, 7400000),
    ("COP", "ConocoPhillips", "Energy", "NYSE", 111, 5500000),
    ("SLB", "SLB", "Energy", "NYSE", 43, 11000000),
    ("CAT", "Caterpillar", "Industrials", "NYSE", 362, 2700000),
    ("GE", "GE Aerospace", "Industrials", "NYSE", 182, 4700000),
    ("RTX", "RTX", "Industrials", "NYSE", 118, 4300000),
    ("UBER", "Uber Technologies", "Industrials", "NYSE", 78, 17000000),
    ("LIN", "Linde", "Materials", "NASDAQ", 452, 1700000),
    ("FCX", "Freeport-McMoRan", "Materials", "NYSE", 44, 13000000),
    ("NEE", "NextEra Energy", "Utilities", "NYSE", 76, 8500000),
    ("CEG", "Constellation Energy", "Utilities", "NASDAQ", 226, 2800000),
    ("AMT", "American Tower", "Real Estate", "NYSE", 208, 2300000),
    ("PLD", "Prologis", "Real Estate", "NYSE", 116, 3400000),
)
CURATED_SYMBOLS = tuple(item[0] for item in _CURATED)
_METADATA = {item[0]: {"symbol": item[0], "name": item[1], "sector": item[2],
                        "exchange": item[3]} for item in _CURATED}
_METADATA["SPY"] = {"symbol": "SPY", "name": "SPDR S&P 500 ETF Trust",
                    "sector": "ETF", "exchange": "ARCA"}


class ProviderError(ValueError):
    """A user-actionable market data failure, with no credential contents."""


def _now():
    return datetime.now(timezone.utc)


def provider_status():
    """Return connection readiness, never keys or other credential values."""
    return {
        "alpaca_configured": bool(os.environ.get("ALPACA_API_KEY", "").strip()
                                  and os.environ.get("ALPACA_SECRET_KEY", "").strip()),
        "feed": os.environ.get("ALPACA_FEED", "iex").strip().lower(),
    }


def _symbol(value):
    if not isinstance(value, str):
        raise ValueError("Symbols must be ticker strings.")
    value = value.strip().upper()
    if not _SYMBOL.fullmatch(value):
        raise ValueError("Invalid ticker; use letters, numbers, and an optional share-class dot or hyphen.")
    return value


def _date(value):
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        raise ValueError("Dates must use YYYY-MM-DD.")
    return date.fromisoformat(value)


def _bar(day, values, context):
    result = {"date": day}
    for field in ("open", "high", "low", "close", "volume"):
        raw = values.get(field)
        if isinstance(raw, bool):
            raise ValueError("{}: {} must be numeric.".format(context, field))
        try:
            number = float(raw)
        except (ValueError, TypeError, OverflowError):
            raise ValueError("{}: {} must be numeric.".format(context, field)) from None
        if not math.isfinite(number) or number < 0 or (field != "volume" and number == 0):
            raise ValueError("{}: prices must be positive and volume nonnegative; all values must be finite.".format(context))
        if number > 1e15:
            raise ValueError("{}: {} is outside supported bounds.".format(context, field))
        if field == "volume" and not number.is_integer():
            raise ValueError("{}: volume must be a whole number of shares.".format(context))
        result[field] = int(number) if field == "volume" else number
    if not (result["low"] <= result["open"] <= result["high"]
            and result["low"] <= result["close"] <= result["high"]):
        raise ValueError("{}: low/high must contain both open and close.".format(context))
    return result


def parse_csv(text):
    """Import validated prior-date daily OHLCV, retaining SPY as the benchmark.

    A CSV cannot establish whether today's bar is final. Require dates earlier
    than today in New York; feed and split-adjustment provenance stay explicit.
    """
    if not isinstance(text, str):
        raise ValueError("CSV must be UTF-8 text.")
    if len(text) > MAX_CSV_BYTES or len(text.encode("utf-8")) > MAX_CSV_BYTES:
        raise ValueError("CSV exceeds the 20 MB limit.")
    if "\x00" in text:
        raise ValueError("CSV contains a null character.")
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")), strict=True)
    required = {"symbol", "date", "open", "high", "low", "close", "volume"}
    allowed = required | {"name", "sector", "exchange"}
    try:
        headers = reader.fieldnames
        if not headers:
            raise ValueError("CSV is empty; include symbol,date,open,high,low,close,volume headers.")
        headers = [header.strip().lower() for header in headers]
        if len(set(headers)) != len(headers):
            raise ValueError("CSV headers must be unique.")
        if required - set(headers):
            raise ValueError("CSV is missing required headers: {}.".format(
                ", ".join(sorted(required - set(headers)))))
        if set(headers) - allowed:
            raise ValueError("Unknown CSV headers: {}.".format(
                ", ".join(sorted(set(headers) - allowed))))
        reader.fieldnames = headers
        assets = {}
        today = _now().astimezone(_NY).date()
        seen = set()
        for row in reader:
            context = "CSV line {}".format(reader.line_num)
            if None in row or any(value is None for value in row.values()):
                raise ValueError("{}: column count does not match the header.".format(context))
            row = {key: value.strip() for key, value in row.items()}
            symbol = _symbol(row["symbol"])
            day = _date(row["date"])
            if day >= today:
                raise ValueError("{}: CSV dates must be earlier than today in New York, so incomplete daily bars cannot enter a scan.".format(context))
            if day.weekday() >= 5:
                raise ValueError("{}: daily US equity bars cannot be dated on a weekend.".format(context))
            key = (symbol, day)
            if key in seen:
                raise ValueError("{}: duplicate date {} for {}.".format(context, day, symbol))
            seen.add(key)
            bar = _bar(day.isoformat(), row, context)
            if symbol not in assets:
                if len(assets) >= 20000:
                    raise ValueError("CSV contains too many symbols (maximum 20,000).")
                assets[symbol] = {"symbol": symbol, "name": symbol, "sector": "Unknown",
                                  "exchange": "Unknown", "bars": []}
            asset = assets[symbol]
            for field in ("name", "sector", "exchange"):
                value = row.get(field, "")
                if not value:
                    continue
                if len(value) > 160 or any(ord(character) < 32 for character in value):
                    raise ValueError("{}: {} is too long or contains control characters.".format(context, field))
                default = symbol if field == "name" else "Unknown"
                if asset[field] not in (default, value):
                    raise ValueError("{}: inconsistent {} for {}.".format(context, field, symbol))
                asset[field] = value
            asset["bars"].append(bar)
    except csv.Error as error:
        raise ValueError("Malformed CSV near line {}: {}.".format(reader.line_num, error)) from None
    if not assets:
        raise ValueError("CSV has no data rows.")
    for asset in assets.values():
        asset["bars"].sort(key=lambda bar: bar["date"])
    as_of = max(asset["bars"][-1]["date"] for asset in assets.values())
    benchmark = assets.pop("SPY", None)
    warnings = ["Imported CSV: feed coverage and corporate-action adjustments are unverified. Use consistently split-adjusted OHLCV from one source.",
                "CSV accepts prior-date bars only; exchange holiday validity is the responsibility of the data source."]
    if benchmark is None:
        warnings.append("No SPY bars were imported; benchmark-relative strength is unavailable.")
    if not assets:
        raise ValueError("CSV must include at least one equity other than the SPY benchmark.")
    return {"source": "csv", "label": "Imported daily bars", "feed": "imported",
            "as_of": as_of, "warnings": warnings,
            "assets": [assets[symbol] for symbol in sorted(assets)], "benchmark": benchmark}


def demo_dataset():
    """An explicitly synthetic, reproducible historical research playground."""
    holidays = {"2024-11-28", "2024-12-25", "2025-01-01", "2025-01-09",
                "2025-01-20", "2025-02-17", "2025-04-18", "2025-05-26",
                "2025-06-19", "2025-07-04", "2025-09-01", "2025-11-27",
                "2025-12-25"}
    days = []
    current = date.fromisoformat(DEMO_AS_OF)
    while len(days) < 300:
        if current.weekday() < 5 and current.isoformat() not in holidays:
            days.append(current.isoformat())
        current -= timedelta(days=1)
    days.reverse()

    def series(index, price, volume, benchmark=False):
        generator = random.Random(7319 + index * 397)
        bars = []
        current_price = price * 0.68
        profile = index % 8
        trend = 0.00065 if benchmark else (0.0016, 0.0012, 0.0008, 0.0002, -0.0006, 0.0010, -0.0002, 0.0014)[profile]
        for position, day in enumerate(days):
            swing = math.sin(position * 0.73 + index) * (0.004 if benchmark else 0.008)
            noise = generator.gauss(0, 0.004 if benchmark else 0.008)
            daily_return = trend + swing + noise
            if not benchmark and position > 274:
                daily_return += (0.0012, 0.0009, 0.0015, -0.0005, -0.002, 0.0008, -0.001, 0.001)[profile]
            if position == len(days) - 1:
                daily_return = 0.0031 if benchmark else (0.016, 0.009, 0.013, -0.008, -0.017, 0.006, -0.004, 0.021)[profile]
            opening = current_price * (1 + generator.gauss(0, 0.0018))
            closing = max(1.0, current_price * (1 + daily_return))
            spread = generator.uniform(0.003, 0.009)
            turnover = volume * generator.uniform(0.78, 1.2)
            if position == len(days) - 1:
                turnover = volume * (1.11 if benchmark else (1.82, 1.42, 2.12, 0.76, 1.68, 1.24, 0.89, 2.43)[profile])
            bars.append({"date": day, "open": round(opening, 4),
                         "high": round(max(opening, closing) * (1 + spread), 4),
                         "low": round(min(opening, closing) * (1 - spread), 4),
                         "close": round(closing, 4), "volume": round(turnover)})
            current_price = closing
        return bars

    assets = []
    for index, item in enumerate(_CURATED):
        assets.append(dict(_METADATA[item[0]], bars=series(index, item[4], item[5])))
    return {"source": "demo", "label": "Synthetic demonstration · not market data",
            "feed": "synthetic", "as_of": DEMO_AS_OF,
            "warnings": ["All demo prices, volumes, rankings, and benchmark values are invented for product demonstration, not actual quotes or recommendations.",
                         "The demo is fixed at December 31, 2025. Connect Alpaca or import historical bars for research with real data."],
            "assets": assets,
            "benchmark": dict(_METADATA["SPY"], bars=series(100, 592, 56000000, True))}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        # Never forward authentication headers to a redirect destination.
        raise ProviderError("Alpaca returned an unexpected redirect; no credentials were forwarded.")


def _get_json(url, params, headers):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in _HOSTS or parsed.port is not None or parsed.username or parsed.password:
        raise ProviderError("Market data requests must use a fixed Alpaca HTTPS host.")
    request = Request(url + "?" + urlencode(params), headers=headers, method="GET")
    opener = build_opener(_NoRedirect())
    for attempt in range(3):
        try:
            with opener.open(request, timeout=30) as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise ProviderError("Alpaca response exceeded the supported size.")
            try:
                return json.loads(body)
            except (ValueError, UnicodeError):
                raise ProviderError("Alpaca returned an invalid JSON response.") from None
        except HTTPError as error:
            code = error.code
            retry_after = error.headers.get("Retry-After", "") if error.headers else ""
            error.close()
            if code in (429, 500, 502, 503, 504) and attempt < 2:
                delay = min(float(retry_after), 20) if retry_after.isdigit() else 2 ** (attempt + 1)
                time.sleep(delay)
                continue
            if code == 401:
                raise ProviderError("Alpaca authentication failed. Check server-side API keys and ALPACA_PAPER (true for paper-account keys).") from None
            if code == 403:
                raise ProviderError("Alpaca denied access. Check your market data subscription and ALPACA_FEED; SIP requires appropriate access.") from None
            if code == 429:
                raise ProviderError("Alpaca rate limit reached after retries. Wait briefly and run the scan again.") from None
            raise ProviderError("Alpaca request failed (HTTP {}). Check the requested symbols and account access.".format(code)) from None
        except (URLError, TimeoutError, OSError):
            if attempt < 2:
                time.sleep(2 ** (attempt + 1))
                continue
            raise ProviderError("Could not reach Alpaca after three attempts. Check network connectivity and try again.") from None


def _completed_session(calendar, now):
    if not isinstance(calendar, list):
        raise ProviderError("Alpaca returned an invalid market calendar.")
    completed = []
    for entry in calendar:
        try:
            session = _date(entry["date"])
            closing = daytime.fromisoformat(entry["close"])
            close_at = datetime.combine(session, closing, _NY)
        except (ValueError, TypeError, KeyError):
            raise ProviderError("Alpaca calendar contains an invalid session or closing time.") from None
        if close_at + timedelta(minutes=30) <= now:
            completed.append(session)
    if not completed:
        raise ProviderError("Alpaca calendar contains no completed market session. A session must be closed for at least 30 minutes.")
    return max(completed)


def _asset_metadata(symbol):
    return dict(_METADATA.get(symbol, {"symbol": symbol, "name": symbol,
                                      "sector": "Unknown", "exchange": "Unknown"}))


def fetch_alpaca(universe="curated", symbols=None, progress=None):
    """Fetch a universe's split-adjusted bars through the last completed session.

    Uses paper-account API credentials by default; ALPACA_PAPER=false selects
    the live-account metadata host. Both modes only issue GET requests.
    """
    status = provider_status()
    if not status["alpaca_configured"]:
        raise ProviderError("Set ALPACA_API_KEY and ALPACA_SECRET_KEY in the server environment or project .env before using Alpaca.")
    feed = status["feed"]
    if feed not in ("iex", "sip"):
        raise ValueError("ALPACA_FEED must be iex or sip for US daily equity screening.")
    paper = os.environ.get("ALPACA_PAPER", "true").strip().lower()
    if paper not in ("true", "false"):
        raise ValueError("ALPACA_PAPER must be true or false.")
    if universe not in ("curated", "custom", "all"):
        raise ValueError("Universe must be curated, custom, or all.")
    metadata = {}
    if universe == "custom":
        if not isinstance(symbols, (list, tuple)) or not symbols:
            raise ValueError("Custom universe requires a nonempty list of ticker symbols.")
        if len(symbols) > MAX_CUSTOM_SYMBOLS:
            raise ValueError("Custom universe is limited to 1,000 symbols.")
        requested = sorted({_symbol(value) for value in symbols})
    elif universe == "curated":
        requested = list(CURATED_SYMBOLS)
    else:
        requested = []
    trading_url = "https://paper-api.alpaca.markets" if paper == "true" else "https://api.alpaca.markets"
    headers = {"APCA-API-KEY-ID": os.environ["ALPACA_API_KEY"].strip(),
               "APCA-API-SECRET-KEY": os.environ["ALPACA_SECRET_KEY"].strip(),
               "Accept": "application/json", "User-Agent": "Nomisma/1.0"}

    def report(message):
        if progress is not None:
            progress(message)

    report("Checking the exchange calendar for the last completed session…")
    now = _now()
    today = now.astimezone(_NY).date()
    calendar = _get_json(trading_url + "/v2/calendar",
                         {"start": (today - timedelta(days=21)).isoformat(),
                          "end": today.isoformat()}, headers)
    completed = _completed_session(calendar, now)
    warnings = []
    if feed == "iex":
        warnings.append("IEX covers a single exchange. Prices and volumes are not consolidated US market data; average-volume filters use IEX-only shares and may exclude otherwise liquid stocks. Use SIP for consolidated coverage when your subscription permits.")
    if universe == "all":
        report("Loading active tradable US equities from Alpaca…")
        listing = _get_json(trading_url + "/v2/assets",
                            {"status": "active", "asset_class": "us_equity"}, headers)
        if not isinstance(listing, list):
            raise ProviderError("Alpaca returned an invalid assets response.")
        unsupported = 0
        for asset in listing:
            if not isinstance(asset, dict):
                raise ProviderError("Alpaca returned an invalid asset record.")
            if (asset.get("status") != "active" or asset.get("tradable") is not True
                    or asset.get("class", "us_equity") != "us_equity"
                    or asset.get("exchange") not in ("NASDAQ", "NYSE", "AMEX", "ARCA")):
                continue
            try:
                symbol = _symbol(asset.get("symbol"))
            except ValueError:
                unsupported += 1
                continue
            metadata[symbol] = _asset_metadata(symbol)
            metadata[symbol].update(name=str(asset.get("name") or symbol)[:160],
                                    exchange=asset["exchange"])
        requested = sorted(metadata)
        warnings.append("The all-equities universe includes active tradable NASDAQ, NYSE, AMEX and ARCA listings with a stocks-only classification filter. It is not every US security.")
        if unsupported:
            warnings.append("Skipped {} listing symbols with unsupported ticker formats.".format(unsupported))
    from . import instruments
    allowed = instruments.stock_symbols()
    requested = [symbol for symbol in requested if symbol in allowed]
    warnings.append("Stocks only: funds, derivatives and unverified instruments are excluded.")
    if not requested:
        raise ProviderError("The selected universe contains no supported symbols.")
    if len(requested) > 20000:
        raise ProviderError("Alpaca returned more than 20,000 symbols; narrow the universe.")
    requested = [symbol for symbol in requested if symbol != "SPY"]
    if not requested:
        raise ValueError("Select at least one equity other than the SPY benchmark.")
    all_symbols = sorted(set(requested) | {"SPY"})
    collected = {symbol: {} for symbol in all_symbols}
    start = completed - timedelta(days=450)
    end = datetime.combine(completed + timedelta(days=1), daytime.min, _NY) - timedelta(seconds=1)
    # A just-completed session is safe to use, but requesting its future local
    # midnight can exceed a feed's entitlement window. Daily bars are stamped
    # at the session's start, so ending at least 30 minutes behind now still
    # includes the completed daily bar (also on early-close days).
    end = min(end, now - timedelta(minutes=30))
    batches = [all_symbols[index:index + BATCH_SIZE] for index in range(0, len(all_symbols), BATCH_SIZE)]

    def fetch_batch(batch):
        found = {symbol: {} for symbol in batch}
        params = {"symbols": ",".join(batch), "timeframe": "1Day",
                  "start": start.isoformat(), "end": end.isoformat(),
                  "limit": 10000, "adjustment": "split", "feed": feed,
                  "sort": "asc", "asof": completed.isoformat()}
        seen_tokens = set()
        for page in range(100):
            payload = _get_json("https://data.alpaca.markets/v2/stocks/bars", params, headers)
            if not isinstance(payload, dict) or not isinstance(payload.get("bars"), dict):
                raise ProviderError("Alpaca returned an invalid bars response.")
            for symbol, bars in payload["bars"].items():
                if symbol not in found or not isinstance(bars, list):
                    raise ProviderError("Alpaca returned an unexpected symbol or invalid bar collection.")
                for raw in bars:
                    try:
                        stamp = datetime.fromisoformat(raw["t"].replace("Z", "+00:00"))
                        if stamp.tzinfo is None:
                            raise ValueError("Bar timestamp must include a timezone.")
                        day = stamp.astimezone(_NY).date()
                        # Enforce the completed session even if the upstream
                        # service returns a bar outside the requested interval.
                        if day > completed or day < start:
                            continue
                        bar = _bar(day.isoformat(), {"open": raw["o"], "high": raw["h"],
                                                     "low": raw["l"], "close": raw["c"],
                                                     "volume": raw["v"]}, symbol)
                    except (ValueError, KeyError, TypeError, AttributeError):
                        raise ProviderError("Alpaca returned an invalid daily bar for {}.".format(symbol)) from None
                    previous = found[symbol].get(bar["date"])
                    if previous is not None and previous != bar:
                        raise ProviderError("Alpaca returned conflicting daily bars for {} on {}.".format(symbol, bar["date"]))
                    found[symbol][bar["date"]] = bar
            token = payload.get("next_page_token")
            if token is None or token == "":
                return found
            if not isinstance(token, str) or token in seen_tokens or len(token) > 10000:
                raise ProviderError("Alpaca returned an invalid or repeated pagination token.")
            seen_tokens.add(token)
            params["page_token"] = token
        raise ProviderError("Alpaca pagination exceeded 100 pages for one batch; scan stopped without partial results.")

    # Batches download in parallel; a scan stays far below Alpaca's per-minute request limit.
    report("Fetching daily bars for {:,} symbols · 0 of {} batches…".format(len(all_symbols), len(batches)))
    executor = ThreadPoolExecutor(max_workers=FETCH_WORKERS, thread_name_prefix="nomisma-bars")
    try:
        futures = [executor.submit(fetch_batch, batch) for batch in batches]
        for done, future in enumerate(as_completed(futures), 1):
            collected.update(future.result())
            report("Fetching daily bars for {:,} symbols · {} of {} batches…".format(len(all_symbols), done, len(batches)))
    finally:
        # A failed batch stops the scan without waiting for the batches still queued.
        executor.shutdown(wait=False, cancel_futures=True)
    assets = []
    for symbol in requested:
        asset = dict(metadata.get(symbol) or _asset_metadata(symbol))
        asset["bars"] = [collected[symbol][day] for day in sorted(collected[symbol])]
        assets.append(asset)
    if not any(asset["bars"] for asset in assets):
        raise ProviderError("Alpaca returned no completed daily bars for the selected symbols. Check tickers and feed access.")
    missing = [asset["symbol"] for asset in assets if not asset["bars"]]
    if missing:
        warnings.append("No completed bars for {} symbol(s): {}{}. These are excluded by the history requirement.".format(
            len(missing), ", ".join(missing[:20]), "…" if len(missing) > 20 else ""))
    benchmark_bars = [collected["SPY"][day] for day in sorted(collected["SPY"])]
    benchmark = dict(_METADATA["SPY"], bars=benchmark_bars) if benchmark_bars else None
    if benchmark is None:
        warnings.append("SPY benchmark bars were unavailable; benchmark-relative strength cannot be computed.")
    if any(asset["sector"] == "Unknown" for asset in assets):
        warnings.append("Sector classifications are available for the maintained starter universe only. Other symbols are Unknown and will not pass named-sector filters.")
    warnings.append("Daily bars are split-adjusted, not dividend-adjusted. Returns represent price changes, not total returns.")
    report("Daily data ready through {}; calculating indicators…".format(completed.isoformat()))
    return {"source": "alpaca", "label": "Alpaca · {} daily bars".format(feed.upper()),
            "feed": feed, "as_of": completed.isoformat(), "warnings": warnings,
            "assets": assets, "benchmark": benchmark}
