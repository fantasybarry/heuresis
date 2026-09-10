"""Read-only intraday Alpaca data and a small, verified RFC 6455 client.

References:
https://docs.alpaca.markets/us/docs/real-time-stock-pricing-data
https://docs.alpaca.markets/us/docs/streaming-market-data
https://docs.alpaca.markets/us/reference/stockbars
https://site.financialmodelingprep.com/developer/docs/stable/shares-float

No orders, account mutations, delayed-feed substitution, or reconnects here.
The monitor owns reconnect/reseed policy. Credentials never enter callbacks.
"""

import base64
from collections import OrderedDict
from datetime import date, datetime, time as daytime, timedelta, timezone
import hashlib
import json
import math
import os
import re
import socket
import ssl
import struct
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo

from . import providers


_NY = ZoneInfo("America/New_York")
_STREAM_HOST = "stream.data.alpaca.markets"
_CHANNELS = ("trades", "quotes", "bars", "updatedBars", "dailyBars")
_FRAME_LIMIT = 1024 * 1024
_MESSAGE_LIMIT = 2 * _FRAME_LIMIT
_HTTP_WORKERS = threading.BoundedSemaphore(2)
_FLOAT_CACHE = OrderedDict()
_FLOAT_LOCK = threading.Lock()
_FLOAT_TTL = 24 * 60 * 60
_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class _Cancelled(ValueError):
    pass


def _now():
    return datetime.now(timezone.utc)


def _check_stop(stop_event):
    if stop_event is not None and stop_event.is_set():
        raise _Cancelled("Live market data loading stopped.")


def live_provider_status():
    status = providers.provider_status()
    status["float_configured"] = bool(os.environ.get("FMP_API_KEY", "").strip())
    return status


def _credentials():
    status = live_provider_status()
    if not status["alpaca_configured"]:
        raise ValueError("Set ALPACA_API_KEY and ALPACA_SECRET_KEY in the project .env before starting live data.")
    if status["feed"] not in ("iex", "sip"):
        raise ValueError("ALPACA_FEED must be iex or sip; this monitor requires a real-time feed.")
    paper = os.environ.get("ALPACA_PAPER", "true").strip().lower()
    if paper not in ("true", "false"):
        raise ValueError("ALPACA_PAPER must be true or false.")
    return status, {"APCA-API-KEY-ID": os.environ["ALPACA_API_KEY"].strip(),
                    "APCA-API-SECRET-KEY": os.environ["ALPACA_SECRET_KEY"].strip(),
                    "Accept": "application/json", "User-Agent": "Nomisma/1.0"}, (
        "https://paper-api.alpaca.markets" if paper == "true" else "https://api.alpaca.markets")


def _symbols(values):
    if not isinstance(values, (list, tuple)) or not 1 <= len(values) <= 20:
        raise ValueError("Live monitoring requires between 1 and 20 ticker symbols.")
    return list(dict.fromkeys(providers._symbol(value) for value in values))


def _cancellable_call(function, stop_event, *args):
    """Stop promptly without changing the existing fixed-host GET transport.

    Its bounded HTTP retry can finish in a daemon worker after cancellation.
    The shared two-worker cap also bounds abandoned requests during repeated
    start/stop cycles. An abandoned result can never reach the monitor.
    """
    _check_stop(stop_event)
    deadline = time.monotonic() + 125
    while not _HTTP_WORKERS.acquire(timeout=0.1):
        _check_stop(stop_event)
        if time.monotonic() >= deadline:
            raise ValueError("Market data transport is busy; retry shortly.")
    done = threading.Event()
    result = []

    def work():
        try:
            result.append((True, function(*args)))
        except Exception as error:
            result.append((False, error))
        finally:
            _HTTP_WORKERS.release()
            done.set()

    threading.Thread(target=work, name="nomisma-market-get", daemon=True).start()
    while not done.wait(0.1):
        _check_stop(stop_event)
        if time.monotonic() >= deadline:
            raise ValueError("Market data request timed out. Retry shortly.")
    _check_stop(stop_event)
    success, value = result[0]
    if success:
        return value
    if isinstance(value, providers.ProviderError):
        raise value from None
    # Do not surface arbitrary exceptions that can contain request URLs/keys.
    raise ValueError("Market data request failed. Check network and provider access.") from None


def _get_json(url, params, headers, stop_event=None):
    return _cancellable_call(providers._get_json, stop_event, url, params, headers)


def _stamp(raw):
    if not isinstance(raw, str):
        raise ValueError("Invalid timestamp.")
    # Alpaca uses nanoseconds; Python 3.9 fromisoformat needs microseconds.
    raw = re.sub(r"(\.\d{6})\d+(?=Z|[+-]\d\d:\d\d$)", r"\1", raw)
    stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("Timestamp requires timezone.")
    return stamp.astimezone(timezone.utc)


def _session(calendar, now):
    if not isinstance(calendar, list):
        raise ValueError("Alpaca returned an invalid exchange calendar.")
    sessions = {}
    today = now.astimezone(_NY).date()
    for entry in calendar:
        try:
            day = providers._date(entry["date"])
            opening = datetime.combine(day, daytime.fromisoformat(entry["open"]), _NY)
            closing = datetime.combine(day, daytime.fromisoformat(entry["close"]), _NY)
            if opening >= closing or closing - opening > timedelta(hours=6, minutes=30):
                raise ValueError("Invalid session hours.")
        except (ValueError, KeyError, TypeError, AttributeError):
            raise ValueError("Alpaca returned invalid exchange session hours.") from None
        if day <= today:
            if day in sessions and sessions[day] != (opening, closing):
                raise ValueError("Alpaca returned conflicting exchange session hours.")
            sessions[day] = (opening, closing)
    days = sorted(sessions)
    if len(days) < 2:
        raise ValueError("Alpaca calendar does not contain a current and previous trading session.")
    day = days[-1]
    opening, closing = sessions[day]
    return {"date": day.isoformat(), "open": opening.isoformat(),
            "close": closing.isoformat(), "previous_date": days[-2].isoformat(),
            "prior_dates": [prior.isoformat() for prior in days[:-1][-30:]]}, set(days)


def _history(symbols, session, calendar_days, now, feed, headers, stop_event, timeframe):
    day = date.fromisoformat(session["date"])
    opening, closing = _stamp(session["open"]), _stamp(session["close"])
    if timeframe == "1Day":
        start = datetime.combine(day - timedelta(days=90), daytime.min, _NY)
        end = datetime.combine(day, daytime.min, _NY) - timedelta(microseconds=1)
    else:
        start = opening
        end = min(now.replace(second=0, microsecond=0), closing) - timedelta(microseconds=1)
        if end < start:
            return {symbol: [] for symbol in symbols}
    params = {"symbols": ",".join(symbols), "timeframe": timeframe,
              "start": start.isoformat(), "end": end.isoformat(), "limit": 10000,
              "adjustment": "split", "feed": feed, "sort": "asc", "asof": session["date"]}
    collected = {symbol: {} for symbol in symbols}
    tokens = set()
    for page in range(100):
        _check_stop(stop_event)
        payload = _get_json("https://data.alpaca.markets/v2/stocks/bars", params, headers, stop_event)
        if not isinstance(payload, dict) or not isinstance(payload.get("bars"), dict):
            raise ValueError("Alpaca returned an invalid intraday history response.")
        for symbol, bars in payload["bars"].items():
            if symbol not in collected or not isinstance(bars, list):
                raise ValueError("Alpaca returned unexpected history symbols or bars.")
            for raw in bars:
                try:
                    stamp = _stamp(raw["t"])
                    bar_day = stamp.astimezone(_NY).date()
                    if timeframe == "1Day":
                        if not day - timedelta(days=90) <= bar_day < day or bar_day not in calendar_days:
                            continue
                        key = bar_day.isoformat()
                    else:
                        if (stamp < opening or stamp + timedelta(minutes=1) > min(now, closing)
                                or stamp.second != 0 or stamp.microsecond != 0):
                            continue
                        key = stamp.isoformat()
                    bar = providers._bar(bar_day.isoformat(), {
                        "open": raw["o"], "high": raw["h"], "low": raw["l"],
                        "close": raw["c"], "volume": raw["v"]}, symbol)
                    if timeframe != "1Day":
                        bar.pop("date")
                        bar["t"] = key
                        vwap = raw.get("vw")
                        if vwap is not None:
                            if isinstance(vwap, bool) or not math.isfinite(float(vwap)) or not 0 < float(vwap) <= 1e15:
                                raise ValueError("Invalid VWAP.")
                            vwap = float(vwap)
                        bar["vwap"] = vwap
                except (ValueError, KeyError, TypeError, AttributeError, OverflowError):
                    raise ValueError("Alpaca returned an invalid {} bar for {}.".format(timeframe, symbol)) from None
                existing = collected[symbol].get(key)
                if existing is not None and existing != bar:
                    raise ValueError("Alpaca returned conflicting history bars for {}.".format(symbol))
                collected[symbol][key] = bar
        token = payload.get("next_page_token")
        if token is None or token == "":
            break
        if not isinstance(token, str) or len(token) > 10000 or token in tokens:
            raise ValueError("Alpaca returned an invalid or repeated history page token.")
        tokens.add(token)
        params["page_token"] = token
    else:
        raise ValueError("Alpaca history exceeded the pagination limit; no partial seed was used.")
    return {symbol: [items[key] for key in sorted(items)] for symbol, items in collected.items()}


def load_live_seed(symbols, progress=None, stop_event=None):
    """Fetch prior sessions and every completed regular-session minute."""
    _check_stop(stop_event)
    symbols = _symbols(symbols)
    status, headers, account_url = _credentials()
    now = _now()
    today = now.astimezone(_NY).date()

    def report(message):
        _check_stop(stop_event)
        if progress:
            progress(message)

    report("Loading exchange session hours…")
    calendar = _get_json(account_url + "/v2/calendar", {
        "start": (today - timedelta(days=100)).isoformat(), "end": today.isoformat()}, headers, stop_event)
    session, calendar_days = _session(calendar, now)
    warnings = ["Technical setup alerts apply only during regular exchange hours. Trading halt detection is not guaranteed."]
    if status["feed"] == "iex":
        warnings.append("IEX covers one exchange; its prices and volumes are not consolidated US market data. Use entitled SIP for consolidated coverage.")
    report("Loading split-adjusted volume history…")
    daily = _history(symbols, session, calendar_days, now, status["feed"], headers, stop_event, "1Day")
    floats = {}
    if status["float_configured"]:
        for symbol in symbols:
            report("Loading dated float for {}…".format(symbol))
            try:
                floats[symbol] = _cancellable_call(fetch_float, stop_event, symbol)
            except _Cancelled:
                raise
            except ValueError:
                warnings.append("{}: FMP float could not be loaded; prices remain available.".format(symbol))
            if floats.get(symbol) is None:
                warnings.append("{}: no dated share float is available; a dated manual value can be entered.".format(symbol))
    report("Loading all completed regular-session minutes…")
    now = _now()
    minutes = _history(symbols, session, calendar_days, now, status["feed"], headers, stop_event, "1Min")
    report("Loading current quotes and trades…")
    snapshots = _get_json("https://data.alpaca.markets/v2/stocks/snapshots", {
        "symbols": ",".join(symbols), "feed": status["feed"]}, headers, stop_event)
    snapshots_received_at = _now().isoformat()
    if not isinstance(snapshots, dict) or any(key not in symbols for key in snapshots):
        raise ValueError("Alpaca returned invalid stock snapshots.")
    assets = []
    for symbol in symbols:
        snapshot = snapshots.get(symbol) or {}
        if not isinstance(snapshot, dict):
            raise ValueError("Alpaca returned an invalid stock snapshot.")
        snapshot = dict(snapshot, _received_at=snapshots_received_at)
        asset = dict(providers._asset_metadata(symbol), bars=daily[symbol], minutes=minutes[symbol],
                     snapshot=snapshot, float=floats.get(symbol))
        if len(daily[symbol]) < 30:
            warnings.append("{} has fewer than 30 prior trading sessions; volume baselines and alerts are unavailable.".format(symbol))
        assets.append(asset)
    _check_stop(stop_event)
    return {"source": "alpaca", "feed": status["feed"], "as_of": _now().isoformat(),
            "session": session, "warnings": warnings, "assets": assets}


class _NoFloatRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        raise ValueError("FMP returned an unexpected redirect; credentials were not forwarded.")


def fetch_float(symbol):
    """Return actual, provider-dated float shares; never substitute outstanding."""
    symbol = providers._symbol(symbol)
    key = os.environ.get("FMP_API_KEY", "").strip()
    if not key:
        return None
    cache_key = (symbol, hashlib.sha256(key.encode("utf-8")).digest())
    with _FLOAT_LOCK:
        cached = _FLOAT_CACHE.get(cache_key)
        if cached is not None and time.monotonic() - cached[0] < _FLOAT_TTL:
            _FLOAT_CACHE.move_to_end(cache_key)
            return dict(cached[1]) if cached[1] is not None else None
    request = Request("https://financialmodelingprep.com/stable/shares-float?" + urlencode({
        "symbol": symbol, "apikey": key}), headers={"Accept": "application/json",
        "User-Agent": "Nomisma/1.0"}, method="GET")
    try:
        with build_opener(_NoFloatRedirect()).open(request, timeout=10) as response:
            body = response.read(1024 * 1024 + 1)
        if len(body) > 1024 * 1024:
            raise ValueError("Oversized float response.")
        payload = json.loads(body)
    except HTTPError as error:
        code = error.code
        error.close()
        raise ValueError("FMP float request failed (HTTP {}); check float-data access.".format(code)) from None
    except (URLError, OSError, ValueError, UnicodeError, RecursionError):
        raise ValueError("FMP float is unavailable; check network and float-data access.") from None
    if not isinstance(payload, list):
        raise ValueError("FMP returned an invalid float response.")
    results = []
    for row in payload:
        if not isinstance(row, dict) or row.get("symbol") != symbol:
            continue
        try:
            raw = row.get("floatShares")
            if isinstance(raw, bool):
                continue
            shares = float(raw)
            if not math.isfinite(shares) or not shares.is_integer() or not 0 < shares <= 1e13:
                continue
            source_date = row.get("date")
            if not isinstance(source_date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[ T].+)?", source_date):
                continue
            as_of = date.fromisoformat(source_date[:10])
            if as_of > _now().astimezone(_NY).date():
                continue
        except (ValueError, TypeError, OverflowError):
            continue
        results.append({"shares": int(shares), "as_of": as_of.isoformat(), "source": "FMP"})
    result = max(results, key=lambda row: row["as_of"]) if results else None
    with _FLOAT_LOCK:
        _FLOAT_CACHE[cache_key] = (time.monotonic(), result)
        _FLOAT_CACHE.move_to_end(cache_key)
        while len(_FLOAT_CACHE) > 256:
            _FLOAT_CACHE.popitem(last=False)
    return dict(result) if result is not None else None


class _WebSocket:
    """Fixed-host, TLS-only websocket with bounded/cancellable wire parsing."""

    def __init__(self, feed, stop_event):
        if feed not in ("iex", "sip"):
            raise ValueError("Unsupported real-time market feed.")
        self.feed = feed
        self.stop_event = stop_event
        self.sock = None
        self.buffer = bytearray()
        self.last_received = time.monotonic()
        self.last_ping = self.last_received
        self.upgraded = False

    def connect(self):
        _check_stop(self.stop_event)
        raw = socket.create_connection((_STREAM_HOST, 443), timeout=5)
        try:
            context = ssl.create_default_context()
            self.sock = context.wrap_socket(raw, server_hostname=_STREAM_HOST, do_handshake_on_connect=False)
            self.sock.settimeout(0.5)
            deadline = time.monotonic() + 10
            while True:
                _check_stop(self.stop_event)
                if time.monotonic() > deadline:
                    raise ValueError("Alpaca TLS handshake timed out.")
                try:
                    self.sock.do_handshake()
                    break
                except (socket.timeout, ssl.SSLWantReadError, ssl.SSLWantWriteError):
                    continue
            key = base64.b64encode(os.urandom(16)).decode("ascii")
            request = ("GET /v2/{} HTTP/1.1\r\nHost: {}\r\nUpgrade: websocket\r\n"
                       "Connection: Upgrade\r\nSec-WebSocket-Key: {}\r\nSec-WebSocket-Version: 13\r\n"
                       "Content-Type: application/json\r\nUser-Agent: Nomisma/1.0\r\n\r\n").format(
                           self.feed, _STREAM_HOST, key)
            self.sock.sendall(request.encode("ascii"))
            while b"\r\n\r\n" not in self.buffer:
                self._receive(deadline)
                if len(self.buffer) > 16384:
                    raise ValueError("Alpaca websocket handshake was too large.")
            header, remainder = bytes(self.buffer).split(b"\r\n\r\n", 1)
            self.buffer = bytearray(remainder)
            lines = header.decode("iso-8859-1").split("\r\n")
            if lines[0].split(" ")[:2] != ["HTTP/1.1", "101"]:
                raise ValueError("Alpaca websocket upgrade failed; check feed and connection access.")
            headers = {}
            for line in lines[1:]:
                name, separator, value = line.partition(":")
                name = name.strip().lower()
                if not separator or name in headers:
                    raise ValueError("Alpaca returned malformed websocket headers.")
                headers[name] = value.strip()
            expected = base64.b64encode(hashlib.sha1((key + _GUID).encode("ascii")).digest()).decode("ascii")
            if (headers.get("upgrade", "").lower() != "websocket"
                    or "upgrade" not in {token.strip().lower() for token in headers.get("connection", "").split(",")}
                    or headers.get("sec-websocket-accept") != expected
                    or headers.get("sec-websocket-extensions") or headers.get("sec-websocket-protocol")):
                raise ValueError("Alpaca websocket handshake verification failed.")
            self.upgraded = True
        except Exception:
            self.close()
            raw.close()
            raise

    def _receive(self, deadline):
        while True:
            _check_stop(self.stop_event)
            current = time.monotonic()
            if current >= deadline:
                raise ValueError("Alpaca websocket response timed out.")
            if self.upgraded and current - self.last_ping >= 20:
                self.send(9, b"nomisma")
                self.last_ping = current
            try:
                chunk = self.sock.recv(8192)
            except (socket.timeout, ssl.SSLWantReadError):
                continue
            if not chunk:
                raise ValueError("Alpaca closed the market data connection.")
            self.last_received = time.monotonic()
            self.buffer.extend(chunk)
            return

    def _take(self, count, deadline):
        while len(self.buffer) < count:
            self._receive(deadline)
        chunk = bytes(self.buffer[:count])
        del self.buffer[:count]
        return chunk

    def send(self, opcode, payload=b""):
        if len(payload) > _MESSAGE_LIMIT or (opcode >= 8 and len(payload) > 125):
            raise ValueError("Outbound websocket message exceeds supported size.")
        mask = os.urandom(4)
        length = len(payload)
        if length < 126:
            header = bytes((0x80 | opcode, 0x80 | length))
        elif length < 65536:
            header = bytes((0x80 | opcode, 0xFE)) + struct.pack("!H", length)
        else:
            header = bytes((0x80 | opcode, 0xFF)) + struct.pack("!Q", length)
        encoded = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        self.sock.sendall(header + mask + encoded)

    def send_json(self, payload):
        self.send(1, json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf-8"))

    def message(self, deadline=None):
        fragmented = None
        chunks = bytearray()
        # A quiet feed is valid; a ping every read cycle checks transport liveness.
        while True:
            _check_stop(self.stop_event)
            current = time.monotonic()
            if current - self.last_ping >= 20:
                self.send(9, b"nomisma")
                self.last_ping = current
            frame_deadline = deadline if deadline is not None else current + 35
            first, second = self._take(2, frame_deadline)
            final, opcode, size = bool(first & 0x80), first & 15, second & 127
            if first & 0x70 or second & 0x80 or opcode not in (0, 1, 2, 8, 9, 10):
                raise ValueError("Alpaca returned an invalid websocket frame.")
            if size == 126:
                size = struct.unpack("!H", self._take(2, frame_deadline))[0]
                if size < 126:
                    raise ValueError("Alpaca returned a noncanonical websocket frame.")
            elif size == 127:
                size = struct.unpack("!Q", self._take(8, frame_deadline))[0]
                if size < 65536:
                    raise ValueError("Alpaca returned a noncanonical websocket frame.")
            if size > _FRAME_LIMIT or (opcode >= 8 and (not final or size > 125)):
                raise ValueError("Alpaca websocket frame exceeds supported bounds.")
            payload = self._take(size, frame_deadline)
            if opcode == 8:
                if len(payload) == 1:
                    raise ValueError("Alpaca returned an invalid websocket close frame.")
                if payload:
                    code = struct.unpack("!H", payload[:2])[0]
                    if code not in (1000, 1001, 1002, 1003, 1007, 1008, 1009, 1010, 1011, 1012, 1013, 1014) and not 3000 <= code <= 4999:
                        raise ValueError("Alpaca returned an invalid websocket close code.")
                    try:
                        payload[2:].decode("utf-8")
                    except UnicodeError:
                        raise ValueError("Alpaca returned an invalid websocket close message.") from None
                self.send(8, payload)
                raise ValueError("Alpaca closed the market data stream; reconnecting is required.")
            if opcode == 9:
                self.send(10, payload)
                continue
            if opcode == 10:
                continue
            if opcode in (1, 2):
                if fragmented is not None:
                    raise ValueError("Alpaca interleaved fragmented websocket messages.")
                fragmented = opcode
            elif fragmented is None:
                raise ValueError("Alpaca sent an unexpected continuation frame.")
            chunks.extend(payload)
            if len(chunks) > _MESSAGE_LIMIT:
                raise ValueError("Alpaca websocket message exceeds supported bounds.")
            if not final:
                continue
            try:
                events = json.loads(chunks.decode("utf-8"), parse_constant=lambda value: None)
            except (ValueError, UnicodeError, RecursionError):
                raise ValueError("Alpaca returned an invalid websocket JSON message.") from None
            if not isinstance(events, list) or any(not isinstance(event, dict) for event in events):
                raise ValueError("Alpaca returned an invalid websocket event collection.")
            return events

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None


def _stream_error(event):
    # Never interpolate upstream text: it may echo credentials or request data.
    meanings = {400: "invalid stream request", 401: "authentication required",
                402: "authentication failed", 403: "duplicate authentication",
                404: "authentication timed out", 405: "subscription symbol limit exceeded",
                406: "connection limit exceeded; stop other sessions using this feed",
                407: "client could not keep up with the stream",
                409: "real-time feed access requires an eligible data subscription",
                410: "requested channel is unavailable", 500: "provider internal error"}
    code = event.get("code")
    reason = meanings.get(code, "provider rejected the streaming session") if isinstance(code, int) else "provider rejected the streaming session"
    return ValueError("Alpaca stream: {}.".format(reason))


def stream_live(symbols, on_event, stop_event, on_status=None):
    """One authenticated stream session; root performs reconnect and reseeding."""
    connection = None
    try:
        _check_stop(stop_event)
        symbols = _symbols(symbols)
        status, headers, unused_account = _credentials()
        if on_status:
            on_status("connecting")
        connection = _WebSocket(status["feed"], stop_event)
        connection.connect()
        connection.send_json({"action": "auth", "key": headers["APCA-API-KEY-ID"],
                              "secret": headers["APCA-API-SECRET-KEY"]})
        authenticated = False
        subscribed = False
        optional_channels = ["statuses", "lulds"]
        optional_pending = None
        optional_confirmed = {"statuses": False, "lulds": False}

        def report_channels(message):
            on_event(dict({"T": "nomisma_subscription", "required": True,
                           "checked_at": _now().isoformat(), "message": message}, **optional_confirmed))

        def subscribe_optional():
            # Entitlements vary by channel. Keep these separate from the price
            # request so a rejected optional channel cannot invalidate its ACK.
            nonlocal optional_pending
            optional_pending = optional_channels.pop(0) if optional_channels else None
            if optional_pending and not stop_event.is_set():
                connection.send_json({"action": "subscribe", optional_pending: symbols})

        deadline = time.monotonic() + 10
        while not stop_event.is_set():
            for event in connection.message(None if subscribed else deadline):
                _check_stop(stop_event)
                kind = event.get("T")
                if kind == "error":
                    if subscribed and optional_pending and event.get("code") in (409, 410):
                        report_channels("{} was not available for this subscription; price data remains connected.".format(optional_pending))
                        subscribe_optional()
                        continue
                    raise _stream_error(event)
                if kind == "success" and event.get("msg") == "authenticated" and not authenticated:
                    authenticated = True
                    connection.send_json(dict({"action": "subscribe"}, **{
                        channel: symbols for channel in _CHANNELS}))
                    deadline = time.monotonic() + 10
                elif kind == "subscription":
                    requested = set(symbols)
                    if (not authenticated or any(not isinstance(event.get(channel), list)
                            or requested != set(value for value in event[channel] if isinstance(value, str))
                            for channel in _CHANNELS)):
                        raise ValueError("Alpaca did not confirm all requested live data subscriptions.")
                    if not subscribed:
                        subscribed = True
                        report_channels("Price subscriptions confirmed; optional trading status and price bands are being checked.")
                        if on_status:
                            on_status("live")
                        subscribe_optional()
                    elif optional_pending:
                        values = event.get(optional_pending)
                        optional_confirmed[optional_pending] = (isinstance(values, list)
                            and (set(symbols).issubset(set(value for value in values if isinstance(value, str)))
                                 or "*" in values))
                        report_channels("{} {}. A channel subscription does not establish a security's current halt status.".format(
                            optional_pending, "confirmed" if optional_confirmed[optional_pending] else "not confirmed"))
                        subscribe_optional()
                elif kind in ("t", "q", "b", "u", "d", "c", "x", "s", "l"):
                    if not subscribed:
                        raise ValueError("Alpaca sent market events before confirming the subscription.")
                    if event.get("S") in symbols:
                        on_event(event)
    except _Cancelled:
        return
    except (OSError, ssl.SSLError):
        if stop_event.is_set():
            return
        raise ValueError("Alpaca stream connection failed. Check network, TLS certificates, and feed access.") from None
    finally:
        if connection is not None:
            connection.close()
