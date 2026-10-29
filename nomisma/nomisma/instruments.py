"""Stocks-only eligibility from Nasdaq Trader's public symbol directories.

https://www.nasdaqtrader.com/Trader.aspx?id=SymbolDirDefs
Unknown instruments fail closed. SPY may still be loaded separately as a benchmark.
"""
import csv
import io
import re
import threading
import time
from urllib.request import Request, urlopen

from .providers import ProviderError

_LOCK = threading.Lock()
_CACHE = None
_TTL = 3600
_BASE = "https://www.nasdaqtrader.com/dynamic/SymDir/"
_EXCLUDED = re.compile(r"\b(etf|etn|fund|trust|warrants?|rights?|units?|preferred|preference|notes?|bonds?|debentures?|nextshares)\b", re.I)
_STOCK = re.compile(r"\b(common (stock|shares)|ordinary shares|american depositary (shares|receipts)|american depository (shares|receipts)|ADR|ADS)\b", re.I)


def _parse(text, nasdaq):
    reader = csv.DictReader(io.StringIO(text), delimiter="|")
    symbol_key = "Symbol" if nasdaq else "ACT Symbol"
    if not {symbol_key, "Security Name", "ETF", "Test Issue"}.issubset(reader.fieldnames or []):
        raise ValueError("Invalid stock classification directory.")
    result = set()
    for row in reader:
        name = row.get("Security Name") or ""
        if (row.get("ETF") != "N" or row.get("Test Issue") != "N"
                or row.get("NextShares") == "Y" or _EXCLUDED.search(name) or not _STOCK.search(name)):
            continue
        for key in (symbol_key, "CQS Symbol", "NASDAQ Symbol"):
            symbol = row.get(key) or ""
            if re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", symbol):
                result.add(symbol)
    if not result:
        raise ValueError("Empty stock classification directory.")
    return result


def stock_symbols():
    """Return a fresh verified stock allowlist; never send provider credentials."""
    global _CACHE
    with _LOCK:
        if _CACHE and 0 <= time.monotonic() - _CACHE[0] < _TTL:
            return _CACHE[1]
        result = set()
        try:
            for filename, nasdaq in (("nasdaqlisted.txt", True), ("otherlisted.txt", False)):
                request = Request(_BASE + filename, headers={"User-Agent": "Nomisma stocks-only screener"})
                with urlopen(request, timeout=15) as response:
                    body = response.read(4_000_001)
                if len(body) > 4_000_000:
                    raise ValueError("Oversized directory.")
                result.update(_parse(body.decode("utf-8"), nasdaq))
        except Exception:
            raise ProviderError("Stocks-only classification is unavailable. Check your connection and try again; unverified products are excluded.") from None
        _CACHE = (time.monotonic(), frozenset(result))
        return _CACHE[1]


def require_stocks(symbols):
    rejected = sorted(set(symbols) - stock_symbols())
    if rejected:
        raise ProviderError("Stocks only: remove unverified or non-stock symbols: " + ", ".join(rejected) + ".")
