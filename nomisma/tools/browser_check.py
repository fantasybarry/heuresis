#!/usr/bin/env python3
"""Optional real-Chrome integration check. Uses an isolated temporary database.

Run from the project: python3 -B tools/browser_check.py --output ../../artifacts/nomisma
Requires a locally installed Chromium/Chrome; no Python or JS packages needed.
"""

import argparse
import base64
import http.client
import json
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlparse
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nomisma.server import Application, make_handler


class DevTools:
    """Minimal RFC6455 text transport for local Chrome's debugging endpoint."""
    def __init__(self, url):
        address = urlparse(url)
        self.socket = socket.create_connection((address.hostname, address.port), timeout=15)
        nonce = base64.b64encode(os.urandom(16)).decode()
        request = ("GET %s HTTP/1.1\r\nHost: %s:%s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                   "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n") % (address.path, address.hostname, address.port, nonce)
        self.socket.sendall(request.encode())
        response = b""
        while not response.endswith(b"\r\n\r\n"):
            response += self.read(1)
        if b" 101 " not in response.split(b"\r\n")[0]:
            raise RuntimeError("Chrome debugging WebSocket handshake failed")
        self.identifier = 0
        self.errors = []

    def read(self, size):
        output = bytearray()
        while len(output) < size:
            chunk = self.socket.recv(size - len(output))
            if not chunk:
                raise RuntimeError("Chrome debugging connection closed")
            output.extend(chunk)
        return bytes(output)

    def send(self, body, opcode=1):
        mask = os.urandom(4)
        header = bytes([0x80 | opcode])
        size = len(body)
        if size < 126:
            header += bytes([0x80 | size])
        elif size <= 65535:
            header += bytes([0x80 | 126]) + struct.pack("!H", size)
        else:
            header += bytes([0x80 | 127]) + struct.pack("!Q", size)
        self.socket.sendall(header + mask + bytes(value ^ mask[index % 4] for index, value in enumerate(body)))

    def receive(self):
        message = bytearray()
        while True:
            first, second = self.read(2)
            size = second & 127
            if size == 126:
                size = struct.unpack("!H", self.read(2))[0]
            elif size == 127:
                size = struct.unpack("!Q", self.read(8))[0]
            if size > 32 * 1024 * 1024:
                raise RuntimeError("Debug response too large")
            mask = self.read(4) if second & 128 else None
            body = self.read(size)
            if mask:
                body = bytes(value ^ mask[index % 4] for index, value in enumerate(body))
            opcode = first & 15
            if opcode == 8:
                raise RuntimeError("Chrome debugging connection closed")
            if opcode == 9:
                self.send(body, opcode=10)
                continue
            message.extend(body)
            if first & 128:
                return json.loads(message)

    def call(self, method, params=None):
        self.identifier += 1
        self.send(json.dumps({"id": self.identifier, "method": method, "params": params or {}}).encode())
        while True:
            result = self.receive()
            if result.get("method") == "Runtime.exceptionThrown":
                self.errors.append(result["params"])
            if result.get("method") == "Log.entryAdded" and result["params"]["entry"]["level"] == "error":
                self.errors.append(result["params"]["entry"])
            if result.get("id") == self.identifier:
                if "error" in result:
                    raise RuntimeError(str(result["error"]))
                return result.get("result", {})

    def evaluate(self, expression):
        result = self.call("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True})
        if "exceptionDetails" in result:
            raise AssertionError(str(result["exceptionDetails"]))
        return result["result"].get("value")

    def wait(self, expression, seconds=10):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self.evaluate("Boolean(" + expression + ")"):
                return
            time.sleep(0.1)
        raise AssertionError("Timed out waiting for " + expression)

    def screenshot(self, path):
        result = self.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        path.write_bytes(base64.b64decode(result["data"]))


def browser_endpoint(port):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
    try:
        connection.request("GET", "/json/list")
        targets = json.loads(connection.getresponse().read())
        return next(target["webSocketDebuggerUrl"] for target in targets if target["type"] == "page")
    finally:
        connection.close()


def check_live(client, app, server_port, output, temporary):
    """Exercise real browser events against the isolated synthetic monitor."""
    # A test-only notification stand-in proves opt-in and demo suppression
    # without requesting OS permissions or issuing desktop notifications.
    client.call("Page.addScriptToEvaluateOnNewDocument", {"source": """
      window.notificationChecks = {requests:0, delivered:0};
      window.Notification = class {
        static permission = 'default';
        static async requestPermission() { notificationChecks.requests++; this.permission = 'granted'; return 'granted'; }
        constructor() { notificationChecks.delivered++; }
      };
    """})
    client.call("Page.navigate", {"url": "http://127.0.0.1:%d/" % server_port})
    client.wait("document.querySelector('#live-start') && !document.querySelector('#live-start').disabled")
    assert client.evaluate("!document.querySelector('#live-view').classList.contains('hidden')")
    assert client.evaluate("notificationChecks.requests === 0 && notificationChecks.delivered === 0")
    client.evaluate("document.querySelector('#live-config').click()")
    client.wait("document.querySelector('#live-config-dialog').open")
    client.evaluate("document.querySelector('#live-config-form [name=min_price]').value = '.6'; document.querySelector('#live-config-form').requestSubmit()")
    client.wait("!document.querySelector('#live-config-dialog').open")
    assert app.monitor.config["min_price"] == .6
    client.evaluate("document.querySelector('#live-notifications').click(); document.querySelector('#live-start').click()")
    client.wait("document.querySelectorAll('#live-table [data-live-symbol]').length === 3")
    client.wait("document.querySelector('#live-connection').textContent.includes('Synthetic')")
    client.evaluate("document.querySelector('#live-config').click()")
    assert client.evaluate("document.querySelector('#live-config-fields').disabled && document.querySelector('#live-save-config').disabled")
    client.evaluate("document.querySelector('#live-config-dialog').close()")
    print("PASS intraday-first navigation, saved filters, explicit start, and running configuration lock")

    client.evaluate("document.querySelector('#live-table [data-live-symbol]').click()")
    client.wait("document.querySelector('#live-report-dialog').open && document.querySelector('#live-report-data svg')")
    assert client.evaluate("document.querySelectorAll('#live-history-details .live-history-table tbody tr').length === 30")
    assert client.evaluate("['Session volume','Float shares','30-session average volume','30-session total volume','Session relative volume','1-minute relative volume','Opening gap'].every(label => document.querySelector('#live-report-data').textContent.includes(label))")
    assert client.evaluate("document.querySelector('#live-float-edit').classList.contains('hidden')")
    client.screenshot(output / "intraday-stock-report.png")
    client.evaluate("window.print = () => { window.printCheck = document.body.classList.contains('printing-live-report') && document.querySelector('#live-history-details').open; }; document.querySelector('#live-print').click()")
    assert client.evaluate("window.printCheck && !document.body.classList.contains('printing-live-report')")
    client.evaluate("document.body.classList.add('printing-live-report'); document.querySelector('#live-history-details').open = true")
    pdf = base64.b64decode(client.call("Page.printToPDF", {"printBackground": True})["data"])
    assert pdf.startswith(b"%PDF") and len(pdf) > 5000
    (output / "intraday-stock-report.pdf").write_bytes(pdf)
    client.evaluate("document.body.classList.remove('printing-live-report'); document.querySelector('#live-report-dialog').close()")
    print("PASS stock metrics, 30-session history, price chart, and printable PDF report")

    client.wait("document.querySelector('#live-alerts').textContent.includes('Buy setup')", seconds=20)
    client.wait("document.querySelector('#live-alerts').textContent.includes('Strong buy setup')", seconds=20)
    levels = {item["level"] for item in app.store.monitor_alerts()}
    assert levels == {"Buy", "Strong buy"}
    assert len(app.store.monitor_alerts()) == 6
    assert client.evaluate("notificationChecks.requests === 1 && notificationChecks.delivered === 0")
    client.screenshot(output / "intraday-desktop.png")
    assert not client.evaluate("document.documentElement.scrollWidth > innerWidth")
    client.evaluate("document.querySelector('#live-ack-all').click()")
    client.wait("document.querySelector('#live-alert-count').textContent.trim() === '0'")
    assert all(item["acknowledged"] for item in app.store.monitor_alerts())
    downloads = Path(temporary) / "live-downloads"
    downloads.mkdir()
    client.call("Browser.setDownloadBehavior", {"behavior": "allow", "downloadPath": str(downloads)})
    client.evaluate("document.querySelector('#live-export').click()")
    deadline = time.monotonic() + 10
    while not list(downloads.glob("*.csv")):
        if time.monotonic() > deadline:
            raise AssertionError("Intraday CSV export did not download")
        time.sleep(.1)
    exported = next(downloads.glob("*.csv")).read_text(encoding="utf-8-sig")
    assert "day_volume,day_volume_at,session_volume" in exported and "demo,synthetic" in exported
    client.evaluate("document.querySelector('#live-stop').click()")
    client.wait("document.querySelector('#live-connection').textContent.includes('stopped')")
    assert not app.monitor.status["running"]
    assert all(not row["alert_eligible"] for row in app.monitor.snapshot()["rows"])
    print("PASS streaming Buy/Strong buy alerts, no demo desktop notifications, durable acknowledgments, CSV, and stop")

    client.call("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True})
    client.call("Page.reload")
    client.wait("document.querySelectorAll('#live-table [data-live-symbol]').length === 3")
    assert client.evaluate("innerWidth === 390 && document.documentElement.scrollWidth <= innerWidth"), "Intraday mobile viewport overflows"
    client.screenshot(output / "intraday-mobile.png")
    client.evaluate("document.querySelector('#live-table [data-live-symbol]').click()")
    client.wait("document.querySelector('#live-report-dialog').open")
    assert client.evaluate("document.querySelector('#live-report-dialog').getBoundingClientRect().width <= innerWidth")
    client.screenshot(output / "intraday-report-mobile.png")
    client.evaluate("document.querySelector('#live-report-dialog').close(); document.querySelector('#live-config').click()")
    client.wait("document.querySelector('#live-config-dialog').open")
    assert client.evaluate("document.querySelector('#live-config-dialog').getBoundingClientRect().width <= innerWidth")
    client.screenshot(output / "intraday-config-mobile.png")
    client.evaluate("document.querySelector('#live-config-dialog').close()")
    print("PASS mobile intraday dashboard, stock report, and configuration layout")
    client.call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 1050, "deviceScaleFactor": 1, "mobile": False})


def run(output, chrome):
    with tempfile.TemporaryDirectory(prefix="nomisma-browser-") as temporary:
        app = Application(Path(temporary) / "data")
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            debug_port = listener.getsockname()[1]
        process = subprocess.Popen([chrome, "--headless=new", "--no-first-run", "--no-default-browser-check",
                                    "--disable-extensions", "--disable-background-networking",
                                    "--remote-debugging-port=" + str(debug_port),
                                    "--user-data-dir=" + str(Path(temporary) / "chrome"), "about:blank"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        client = None
        try:
            deadline = time.monotonic() + 20
            while True:
                try:
                    client = DevTools(browser_endpoint(debug_port))
                    break
                except (OSError, StopIteration):
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Chrome did not start its debugging endpoint")
                    time.sleep(0.2)
            client.call("Runtime.enable")
            client.call("Log.enable")
            client.call("Page.enable")
            client.call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 1050, "deviceScaleFactor": 1, "mobile": False})
            output.mkdir(parents=True, exist_ok=True)
            check_live(client, app, server.server_port, output, temporary)
            client.call("Page.navigate", {"url": "http://127.0.0.1:%d/#dashboard" % server.server_port})
            client.wait("document.querySelectorAll('#results-table [data-stock]').length > 0")
            assert client.evaluate("!document.querySelector('#demo-banner').classList.contains('hidden')")
            assert not client.evaluate("document.documentElement.scrollWidth > innerWidth")
            output.mkdir(parents=True, exist_ok=True)
            client.screenshot(output / "dashboard-desktop.png")
            print("PASS dashboard: sample results, source disclosure, desktop layout")

            client.evaluate("document.querySelector('#results-table [data-stock]').click()")
            client.wait("document.querySelector('#stock-dialog').open && document.querySelector('#stock-detail svg')")
            client.screenshot(output / "stock-detail.png")
            client.evaluate("document.querySelector('#stock-dialog').close()")
            client.evaluate("document.querySelector('#results-table [data-watch]').click()")
            client.wait("document.querySelector('#watchlist-count').textContent.trim() === '1'")
            client.evaluate("document.querySelector('[data-view=watchlist]').click()")
            client.wait("!document.querySelector('#watchlist-view').classList.contains('hidden')")
            print("PASS stock detail and persistent watchlist interaction")

            client.evaluate("document.querySelector('[data-view=history]').click()")
            client.wait("!document.querySelector('#history-view').classList.contains('hidden') && document.querySelector('#history-results').textContent.includes('2025')")
            client.evaluate("document.querySelector('[data-view=methodology]').click()")
            client.wait("!document.querySelector('#methodology-view').classList.contains('hidden')")
            client.evaluate("document.querySelector('[data-view=dashboard]').click()")
            print("PASS history and methodology navigation")

            client.evaluate("document.querySelector('#edit-filters').click()")
            client.wait("document.querySelector('#filters-dialog').open")
            client.evaluate("document.querySelector('#filters-form [name=min_score]').value = '100'; document.querySelector('#filters-form').requestSubmit()")
            client.wait("!document.querySelector('#filters-dialog').open")
            original = app.store.latest_id()
            client.evaluate("document.querySelector('#run-scan').click()")
            client.wait("document.querySelectorAll('#results-table [data-stock]').length === 0")
            assert app.store.latest_id() != original
            assert app.store.scan()["matched_count"] == 0
            print("PASS filter save, asynchronous scan, and empty results")

            client.evaluate("document.querySelector('#edit-filters').click(); document.querySelector('#reset-filters').click(); document.querySelector('#filters-form').requestSubmit()")
            client.wait("!document.querySelector('#filters-dialog').open")
            client.evaluate("document.querySelector('#run-scan').click()")
            client.wait("document.querySelectorAll('#results-table [data-stock]').length > 0")

            client.evaluate("document.querySelector('#edit-filters').click(); document.querySelector('#save-preset').click()")
            client.wait("document.querySelector('#text-dialog').open")
            client.evaluate("document.querySelector('#text-input').value = 'Browser check strategy'; document.querySelector('#text-form').requestSubmit()")
            client.wait("!document.querySelector('#text-dialog').open")
            assert any(preset["name"] == "Browser check strategy" for preset in app.store.presets())
            client.evaluate("document.querySelector('#filters-dialog').close(); document.querySelector('#connection-button').click()")
            client.wait("document.querySelector('#settings-dialog').open")
            client.evaluate("document.querySelector('#schedule-enabled').checked = true; document.querySelector('#schedule-time').value = '17:15'; document.querySelector('#settings-form').requestSubmit()")
            client.wait("!document.querySelector('#settings-dialog').open")
            assert app.settings()["schedule"] == {"enabled": True, "time": "17:15", "timezone": "America/New_York"}
            print("PASS custom preset and daily schedule persistence")

            client.evaluate("document.querySelector('#connection-button').click(); document.querySelector('#settings-source').value = 'csv'; document.querySelector('#settings-source').dispatchEvent(new Event('change'))")
            root = client.call("DOM.getDocument")["root"]["nodeId"]
            node = client.call("DOM.querySelector", {"nodeId": root, "selector": "#csv-file"})["nodeId"]
            sample = Path(__file__).resolve().parents[1] / "examples" / "sample.csv"
            client.call("DOM.setFileInputFiles", {"nodeId": node, "files": [str(sample)]})
            client.wait("document.querySelector('#import-status').textContent.includes('2 symbols imported')")
            client.evaluate("document.querySelector('#settings-universe').value = 'all'; document.querySelector('#schedule-enabled').checked = false; document.querySelector('#settings-form').requestSubmit()")
            client.wait("!document.querySelector('#settings-dialog').open")
            client.evaluate("document.querySelector('#run-scan').click()")
            client.wait("document.querySelector('#connection-label').textContent.includes('Imported CSV')")
            assert app.store.scan()["source"] == "csv"
            assert app.store.scan()["matched_count"] == 2
            assert client.evaluate("document.querySelector('#demo-banner').classList.contains('hidden')")
            downloads = Path(temporary) / "downloads"
            downloads.mkdir()
            client.call("Browser.setDownloadBehavior", {"behavior": "allow", "downloadPath": str(downloads)})
            client.evaluate("document.querySelector('#export-results').click()")
            deadline = time.monotonic() + 10
            while not list(downloads.glob("*.csv")):
                if time.monotonic() > deadline:
                    raise AssertionError("CSV export did not download")
                time.sleep(0.1)
            exported = next(downloads.glob("*.csv")).read_text(encoding="utf-8-sig")
            assert "Synthetic example:" in exported and "csv,imported" in exported
            client.evaluate("document.querySelector('[data-view=history]').click(); document.querySelector('[data-history]').click()")
            client.wait("document.querySelector('#history-dialog').open && document.querySelector('#history-detail [data-stock]')")
            client.evaluate("document.querySelector('#history-dialog').close(); document.querySelector('[data-view=dashboard]').click()")
            print("PASS real file import, source selection, exported CSV, and historical scan details")

            client.evaluate("document.querySelector('#connection-button').click(); document.querySelector('#settings-source').value = 'demo'; document.querySelector('#settings-source').dispatchEvent(new Event('change')); document.querySelector('#settings-form').requestSubmit()")
            client.wait("!document.querySelector('#settings-dialog').open")
            client.evaluate("document.querySelector('#run-scan').click()")
            client.wait("document.querySelector('#connection-label').textContent.includes('Synthetic demo')")
            client.call("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True})
            client.call("Page.reload")
            client.wait("document.querySelectorAll('#results-table [data-stock]').length > 0")
            mobile_metrics = client.evaluate("({innerWidth,clientWidth:document.documentElement.clientWidth,scrollWidth:document.documentElement.scrollWidth,bodyWidth:document.body.scrollWidth,viewportWidth:visualViewport.width,scale:visualViewport.scale,scrollContainers:[...document.querySelectorAll('.table-scroll')].map(el=>[el.id,el.clientWidth,el.scrollWidth,getComputedStyle(el).overflowX]),overflow:[...document.querySelectorAll('body *')].filter(el=>{const r=el.getBoundingClientRect(); return r.width && r.right > 391}).map(el=>[el.tagName,el.className,el.getBoundingClientRect().right,getComputedStyle(el.parentElement).overflowX]).slice(0,12)})")
            print("Mobile metrics:", mobile_metrics)
            client.screenshot(output / "dashboard-mobile.png")
            assert not client.evaluate("document.documentElement.scrollWidth > innerWidth"), "Mobile document overflows"
            assert mobile_metrics["innerWidth"] == 390, "Mobile viewport unexpectedly scales its content"
            client.evaluate("document.querySelector('#edit-filters').click()")
            client.wait("document.querySelector('#filters-dialog').open")
            assert client.evaluate("document.querySelector('#filters-dialog').getBoundingClientRect().width <= innerWidth")
            client.screenshot(output / "filters-mobile.png")
            client.evaluate("document.querySelector('#filters-dialog').close()")
            print("PASS default restoration and mobile dashboard/filter layout")
            assert not client.errors, "Browser errors: " + json.dumps(client.errors)
            print("PASS no uncaught JavaScript or browser resource errors")
        finally:
            app.monitor.close()
            app.stop_event.set()
            if client:
                client.socket.close()
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("../../artifacts/nomisma"))
    parser.add_argument("--chrome", default=shutil.which("google-chrome") or shutil.which("chromium") or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    args = parser.parse_args()
    run(args.output.resolve(), args.chrome)
