"""Share one Alpaca stream between workstations.

Alpaca allows one real-time connection per key (stream error 406), so the pool
holds it and relays each workstation only its own symbols as JSON lines.
Workstations set NOMISMA_POOL=host:port; REST seeding still goes to Alpaca.
"""

import hmac
import json
import os
import queue
import select
import socket
import socketserver
import threading

from .live_data import _MESSAGE_LIMIT, LiveSubscriptionLimit, _symbols, stream_live
from .monitor_metrics import MAX_MONITOR_SYMBOLS


def _line(event):
    return (json.dumps(event, separators=(",", ":")) + "\n").encode()


class Pool:
    def __init__(self, token):
        self.token = token.encode()
        self.lock = threading.Lock()
        self.clients = {}  # outbox -> symbols
        self.symbols = set()
        self.live = False
        self.stop = threading.Event()
        self.changed = threading.Event()

    def _put(self, outbox, line):
        try:
            outbox.put_nowait(line)
        except queue.Full:
            self._close(outbox)

    def _close(self, outbox, line=None):
        # Slow or failed workstations are dropped, never allowed to stall the stream.
        self.clients.pop(outbox, None)
        with outbox.mutex:
            outbox.queue.clear()
        if line:
            outbox.put_nowait(line)
        outbox.put_nowait(None)

    def join(self, outbox, symbols):
        with self.lock:
            if len(set().union(symbols, *self.clients.values())) > MAX_MONITOR_SYMBOLS:
                raise LiveSubscriptionLimit("The data pool is full: workstations together exceed {} symbols.".format(MAX_MONITOR_SYMBOLS))
            self.clients[outbox] = symbols
            if not symbols <= self.symbols:
                # ponytail: resubscribes every workstation on growth; per-symbol subscribe if the gaps matter
                self.changed.set()
                self.stop.set()
            elif self.live:
                self._put(outbox, _line({"T": "nomisma_pool", "state": "live"}))

    def leave(self, outbox):
        with self.lock:
            self.clients.pop(outbox, None)

    def publish(self, event):
        line = _line(event)
        with self.lock:
            for outbox, symbols in list(self.clients.items()):
                if event.get("T") == "nomisma_subscription" or event.get("S") in symbols:
                    self._put(outbox, line)

    def status(self, state):
        with self.lock:
            self.live = state == "live"
            for outbox in list(self.clients):
                self._put(outbox, _line({"T": "nomisma_pool", "state": state}))

    def run(self):
        """Upstream loop. Errors disconnect workstations; their monitors own retry backoff."""
        while True:
            self.changed.wait()
            with self.lock:
                self.changed.clear()
                self.symbols = set().union(*self.clients.values())
                self.stop = stop = threading.Event()
                self.live = False
            if not self.symbols:
                continue
            try:
                stream_live(sorted(self.symbols), self.publish, stop, on_status=self.status)
                if not stop.is_set():
                    raise ValueError("The market stream disconnected.")
            except Exception as exc:
                error = _line({"T": "nomisma_pool", "error": str(exc) if isinstance(exc, ValueError) else "The market connection was interrupted.",
                               "limit": isinstance(exc, LiveSubscriptionLimit)})
                with self.lock:
                    for outbox in list(self.clients):
                        self._close(outbox, error)
                    self.symbols = set()


class _Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


class _Handler(socketserver.StreamRequestHandler):
    timeout = 10

    def handle(self):
        pool = self.server.pool
        outbox = queue.Queue(10000)
        try:
            hello = json.loads(self.rfile.readline(_MESSAGE_LIMIT))
            if not isinstance(hello, dict) or not hmac.compare_digest(str(hello.get("token", "")).encode(), pool.token):
                raise ValueError("The data pool rejected this workstation's token.")
            pool.join(outbox, set(_symbols(hello.get("symbols"))))
        except ValueError as exc:
            self.wfile.write(_line({"T": "nomisma_pool", "error": str(exc), "limit": isinstance(exc, LiveSubscriptionLimit)}))
            return
        except OSError:
            return
        try:
            while True:
                try:
                    line = outbox.get(timeout=1)
                except queue.Empty:
                    # Workstations never write after hello, so a readable socket means it hung up.
                    # Dropping it promptly frees its symbols for a restarted monitor.
                    if select.select([self.request], [], [], 0)[0] and not self.request.recv(1, socket.MSG_PEEK):
                        break
                    continue
                if line is None:
                    break
                self.wfile.write(line)
        except OSError:
            pass
        finally:
            pool.leave(outbox)


def serve_pool(port, host="0.0.0.0"):
    token = os.environ.get("NOMISMA_POOL_TOKEN", "").strip()
    if len(token) < 16:
        raise ValueError("Set NOMISMA_POOL_TOKEN (16+ characters) in .env before sharing market data on the network.")
    pool = Pool(token)
    with _Server((host, port), _Handler) as server:
        server.pool = pool
        threading.Thread(target=pool.run, name="nomisma-pool-upstream", daemon=True).start()
        print("Nomisma data pool listening on %s:%s" % (host, port))
        server.serve_forever()


def stream_pool(symbols, on_event, stop_event, on_status=None):
    """Drop-in for stream_live that reads from the data pool instead of Alpaca."""
    host, _, port = os.environ["NOMISMA_POOL"].strip().rpartition(":")
    symbols = _symbols(symbols)
    if on_status:
        on_status("connecting")
    try:
        with socket.create_connection((host, int(port)), timeout=10) as sock:
            sock.sendall(_line({"token": os.environ.get("NOMISMA_POOL_TOKEN", "").strip(), "symbols": symbols}))
            sock.settimeout(0.5)
            buffer = b""
            while not stop_event.is_set():
                try:
                    chunk = sock.recv(65536)
                except socket.timeout:
                    continue
                if not chunk:
                    raise ValueError("The data pool disconnected.")
                *lines, buffer = (buffer + chunk).split(b"\n")
                if len(buffer) > _MESSAGE_LIMIT:
                    raise ValueError("The data pool sent an oversized message.")
                for raw in lines:
                    event = json.loads(raw)
                    if event.get("T") != "nomisma_pool":
                        on_event(event)
                    elif event.get("error"):
                        raise (LiveSubscriptionLimit if event.get("limit") else ValueError)(event["error"])
                    elif on_status:
                        on_status(event.get("state"))
    except OSError:
        if stop_event.is_set():
            return
        raise ValueError("Could not reach the data pool at %s. Check NOMISMA_POOL and that the pool is running." % os.environ["NOMISMA_POOL"]) from None
