#!/usr/bin/env python3
"""Optional real-Chrome integration check. Uses an isolated temporary database.

Run from the project: python3 -B tools/browser_check.py --output ../../artifacts/nomisma
Requires a locally installed Chromium/Chrome; no Python or JS packages needed.
"""

import argparse
import base64
import copy
from datetime import datetime, timedelta, timezone
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
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nomisma.server import Application, make_handler
from nomisma.monitor_metrics import demo_bundle


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

    configured = list(app.monitor.config["symbols"])
    client.evaluate("document.querySelector('#live-scan').click()")
    client.wait("document.querySelector('#live-scan').textContent === 'Scanning…'")
    client.wait("document.querySelector('#live-scan').textContent === 'Scan now' && !document.querySelector('#live-stop').classList.contains('hidden')", seconds=60)
    expected = [row["symbol"] for row in app.discovery_snapshot()["latest"]["result"]["rows"]][:50]
    assert expected and app.monitor.config["symbols"] == expected and app.monitor.status["running"]
    client.evaluate("document.querySelector('#live-stop').click()")
    client.wait("document.querySelector('#live-connection').textContent.includes('stopped')")
    app.monitor.save_config({"symbols": configured})
    print("PASS radar scan loads qualified candidates and starts the monitor")

    client.wait("document.querySelectorAll('#live-table [data-live-candles]').length > 0")
    client.evaluate("document.querySelector('#live-table [data-live-candles]').click()")
    client.wait("document.querySelector('#live-report-dialog').open && document.querySelector('#live-report-dialog').classList.contains('candle-full')")
    client.evaluate("document.querySelector('[data-live-candle-full]').click()")
    client.wait("!document.querySelector('#live-report-dialog').open")
    print("PASS radar rows open full-screen candles")

    client.evaluate("location.hash = 'dashboard'")
    client.wait("document.querySelectorAll('#results-table [data-candles]').length > 0")
    symbol = client.evaluate("document.querySelector('#results-table [data-candles]').dataset.candles")
    client.evaluate("document.querySelector('#results-table [data-candles]').click()")
    client.wait("document.querySelector('#live-report-dialog').open && document.querySelector('#live-report-dialog').classList.contains('candle-full')")
    assert client.evaluate("document.querySelector('#live-report-data .live-candle-full h3').textContent").startswith(symbol + " Candles")
    client.evaluate("document.querySelector('[data-live-tf=\"1Day\"]').click()")
    client.wait("document.querySelector('[data-live-tf=\"1Day\"]').getAttribute('aria-pressed') === 'true'")
    client.evaluate("document.querySelector('[data-live-candle-full]').click()")
    client.wait("!document.querySelector('#live-report-dialog').open && !document.querySelector('#live-report-dialog').classList.contains('candle-full')")
    client.evaluate("location.hash = 'live'")
    print("PASS daily screener opens full-screen candles with selectable timeframes")



METRIC_SORT_FIELDS = ("liquidity_volatility_score", "day_volume", "avg_volume_3m", "avg_daily_volume",
                      "day_relative_volume", "spread_pct", "beta", "atr", "atr_pct")


def check_metric_columns(client, table):
    expected = ["Avg vol (3M)", "Avg daily vol (20D)", "Day RVOL", "Bid–ask spread", "Beta", "ATR (14)"]
    assert client.evaluate("%s.every(label => document.querySelector(%s).textContent.includes(label))" %
                           (json.dumps(expected), json.dumps(table))), "Research metric columns are missing"
    for metric in ("avg_volume_3m", "avg_daily_volume", "day_relative_volume", "spread_pct", "beta", "atr"):
        assert client.evaluate("!!document.querySelector(%s)" % json.dumps(table + ' td[data-metric="' + metric + '"]')), metric
    volume_cell = client.evaluate("document.querySelector(%s)?.outerHTML || null" % json.dumps(table + ' td[data-metric="day_volume"]'))
    assert client.evaluate("!!document.querySelector(%s)" % json.dumps(table + ' td[data-metric="day_volume"][data-label="Total day volume"]')), "Total day volume label is missing; actual cell: " + repr(volume_cell)


def check_candidate_metrics(client, app):
    """Compare real browser ordering with numeric saved result values."""
    check_metric_columns(client, ".live-candidate-table")
    assert client.evaluate("!!document.querySelector('#live-candidate-sort') && !!document.querySelector('.live-ranking-details')")
    rows = app.discovery_snapshot()["latest"]["result"]["rows"]
    client.evaluate("Array.from(document.querySelectorAll('[data-live-candidate]')).slice(0,3).forEach(field => field.click())")
    selected = set(client.evaluate("Array.from(document.querySelectorAll('[data-live-candidate]:checked'), field => field.dataset.liveCandidate)"))
    for metric in METRIC_SORT_FIELDS:
        expected = [row["symbol"] for row in sorted(rows, key=lambda row: (
            row.get(metric) is None, -(row[metric] if row.get(metric) is not None else 0), row["symbol"]))]
        client.evaluate("document.querySelector('#live-candidate-sort').value = %s; document.querySelector('#live-candidate-sort').dispatchEvent(new Event('change', {bubbles:true}))" % json.dumps(metric))
        actual = client.evaluate("Array.from(document.querySelectorAll('[data-live-candidate]'), field => field.dataset.liveCandidate)")
        assert actual == expected, "Candidate numeric sort failed: " + metric
        assert set(client.evaluate("Array.from(document.querySelectorAll('[data-live-candidate]:checked'), field => field.dataset.liveCandidate)")) == selected, "Sorting changed selected candidates"
    client.evaluate("document.querySelector('#live-candidate-sort').value = 'liquidity_volatility_score'; document.querySelector('#live-candidate-sort').dispatchEvent(new Event('change', {bubbles:true})); document.querySelectorAll('[data-live-candidate]:checked').forEach(field => field.click())")


def check_metric_null_sorting(client, app):
    """Exercise decimal, zero, and unavailable values in an isolated stopped snapshot."""
    snapshot = app.monitor.snapshot()
    assert not snapshot["status"]["running"] and snapshot["rows"]
    fixture = copy.deepcopy(snapshot)
    fixture["alerts"] = []
    fixture["rows"] = []
    # Alphabetic order deliberately differs from numeric order, and zero must
    # remain a real value while unavailable data belongs at the bottom.
    for symbol, value in (("SORTC", 12.5), ("SORTA", 2), ("SORTD", 0), ("SORTB", None)):
        row = copy.deepcopy(snapshot["rows"][0])
        row.update(symbol=symbol, name="Synthetic browser sorting fixture",
                   day_volume_fresh=value is not None, volume_partial=False, day_volume_partial=False)
        for metric in METRIC_SORT_FIELDS:
            row[metric] = value
        fixture["rows"].append(row)
    fixture["config"]["symbols"] = [row["symbol"] for row in fixture["rows"]]
    fixture["rows"][0].update(day_volume_fresh=False, day_volume_partial=True)
    fixture["rows"][1]["day_volume_partial"] = True

    def check_volume_notes(selector):
        for symbol, expected in (("SORTC", "Stale volume"), ("SORTA", "Partial volume"),
                                 ("SORTD", ""), ("SORTB", "")):
            cell = client.evaluate("""(() => {
              const cell = document.querySelector(%s).closest('tr').querySelector('[data-metric=day_volume]');
              return {text:cell.textContent, title:cell.title, note:cell.querySelector('small')?.textContent || ''};
            })()""" % json.dumps(selector % symbol))
            assert cell['note'] == expected, 'Volume provenance label mismatch: ' + repr((symbol, cell))
            if symbol == 'SORTC':
                assert 'no volume or day RVOL ranking points' in cell['title']
            if symbol == 'SORTB':
                assert '—' in cell['text'] and 'Unavailable' in cell['title']

    def serve_snapshot(compact=False):
        result = copy.deepcopy(fixture)
        if compact:
            for row in result["rows"]:
                row.pop("chart", None)
                row.pop("volume_history", None)
        return result

    try:
        with patch.object(app.monitor, "snapshot", side_effect=serve_snapshot):
            client.call("Page.reload")
            client.wait("document.querySelectorAll('#live-table [data-live-symbol]').length === 4")
            check_metric_columns(client, ".live-stocks")
            assert client.evaluate("!document.querySelector('#live-extra-columns').checked && !!document.querySelector('#live-ranking-note')")
            for metric in METRIC_SORT_FIELDS:
                client.evaluate("document.querySelector('#live-sort').value = %s; document.querySelector('#live-sort').dispatchEvent(new Event('change'))" % json.dumps(metric))
                actual = client.evaluate("Array.from(document.querySelectorAll('#live-table [data-live-symbol]'), field => field.dataset.liveSymbol)")
                assert actual == ["SORTC", "SORTA", "SORTD", "SORTB"], "Radar decimal/zero/null sort failed: " + metric
            assert client.evaluate("document.querySelector('[data-live-symbol=SORTB]').closest('tr').querySelector('[data-metric=beta]').textContent.includes('—')")
            assert client.evaluate("!document.querySelector('[data-live-symbol=SORTD]').closest('tr').querySelector('[data-metric=beta]').textContent.includes('—')")
            client.evaluate("document.querySelector('#live-sort').value = 'symbol'; document.querySelector('#live-sort').dispatchEvent(new Event('change'))")
            assert client.evaluate("Array.from(document.querySelectorAll('#live-table [data-live-symbol]'), field => field.dataset.liveSymbol)") == ["SORTA", "SORTB", "SORTC", "SORTD"]
            check_volume_notes('#live-table [data-live-symbol="%s"]')

            candidates = copy.deepcopy(app.discovery_snapshot())
            candidate_rows = copy.deepcopy(fixture['rows'])
            for row in candidate_rows[:2]:
                row.update(volume_partial=True, day_volume_partial=False,
                           volume_basis='completed_extended_minutes', volume_at='2026-09-11T15:37:00Z',
                           volume_received_at='2026-09-11T15:45:00Z')
            candidates.update(job=None, latest={'id':'volume-annotation-fixture', 'running':False,
                'result':{'source':'demo', 'feed':'synthetic', 'rows':candidate_rows, 'coverage':{}, 'warnings':[]}})
            with patch.object(app, 'discovery_snapshot', return_value=candidates):
                client.evaluate("document.querySelector('#live-discover').click()")
                client.wait("document.querySelectorAll('[data-live-candidate]').length === 4")
                check_volume_notes('[data-live-candidate="%s"]')
                title = client.evaluate("document.querySelector('[data-live-candidate=SORTC]').closest('tr').querySelector('[data-metric=day_volume]').title")
                assert 'Completed minutes through 11:37:00' in title and '11:45:00' not in title, title
                assert 'partial total may undercount' in title
                client.evaluate("document.querySelector('#live-discovery-dialog').close()")
    finally:
        client.call("Page.reload")
        client.wait("document.querySelectorAll('#live-table [data-live-symbol]').length === %d" % len(snapshot["rows"]))
    print("PASS candidate/radar metric visibility, numeric ranking, selection persistence, and decimal/zero/null sorting")
    print("PASS radar/candidate stale and partial volume labels, missing/zero display, and actual fallback-minute provenance")


def check_mobile_candidate_scrolling(client, output):
    """Require usable metric space and reachable columns on a narrow screen."""
    client.evaluate("document.querySelector('#live-candidate-table-wrapper').scrollIntoView({block:'start'}); document.querySelector('#live-candidate-table-wrapper').scrollTop = 0; document.querySelector('#live-candidate-table-wrapper').scrollLeft = 0")
    geometry = client.evaluate("""(() => {
      const viewport = document.querySelector('#live-candidate-table-wrapper');
      const first = viewport.querySelector('tbody td:first-child');
      return {viewportWidth:viewport.clientWidth, firstWidth:first.getBoundingClientRect().width,
              firstPosition:getComputedStyle(first).position};
    })()""")
    assert geometry["firstPosition"] != "sticky" or geometry["viewportWidth"] - geometry["firstWidth"] >= 160, "Sticky candidate symbols leave too little room for metrics: " + repr(geometry)
    client.screenshot(output / "candidate-metrics-mobile-left.png")
    for metric in ("day_volume", "avg_volume_3m", "avg_daily_volume", "day_relative_volume", "spread_pct", "beta", "atr"):
        visible = client.evaluate("""(() => {
          const viewport = document.querySelector('#live-candidate-table-wrapper');
          const cell = viewport.querySelector('tbody [data-metric=%s]');
          let box = cell.getBoundingClientRect(), bounds = viewport.getBoundingClientRect();
          viewport.scrollLeft += box.left - bounds.left - (viewport.clientWidth - box.width) / 2;
          box = cell.getBoundingClientRect();
          const first = viewport.querySelector('tbody td:first-child');
          const left = getComputedStyle(first).position === 'sticky' ? first.getBoundingClientRect().right : bounds.left;
          return {readable:box.left >= left - 1 && box.right <= bounds.left + viewport.clientWidth + 1,
                  cellLeft:box.left, cellRight:box.right, visibleLeft:left,
                  visibleRight:bounds.left + viewport.clientWidth};
        })()""" % metric)
        assert visible["readable"], "Mobile candidate metric cannot be read in full: " + metric + " " + repr(visible)
        if metric == "day_relative_volume":
            client.screenshot(output / "candidate-metrics-mobile-middle.png")
    client.evaluate("document.querySelector('#live-candidate-table-wrapper').scrollLeft = document.querySelector('#live-candidate-table-wrapper').scrollWidth")
    client.screenshot(output / "candidate-metrics-mobile-right.png")
    client.evaluate("document.querySelector('#live-candidate-table-wrapper').scrollLeft = 0")
    selection = client.evaluate("""(() => {
      const field = document.querySelector('[data-live-candidate]');
      const before = field.checked; field.click(); const after = field.checked; field.click();
      return {before,after,restored:field.checked};
    })()""")
    assert selection["before"] != selection["after"] and selection["restored"] == selection["before"], "Candidate selection stopped working after horizontal scrolling"
    assert client.evaluate("document.documentElement.scrollWidth <= innerWidth && document.querySelector('#live-discovery-dialog').scrollWidth <= document.querySelector('#live-discovery-dialog').clientWidth"), "Mobile candidate scrolling overflows the page or dialog"
    print("PASS mobile candidate metrics remain fully readable while scrolling; selection and viewport preserved")


def check_workspace_improvements(client, app, output):
    symbols = ["QA%02d" % index for index in range(51)]
    client.evaluate("document.querySelector('#live-discover').click()")
    client.wait("document.querySelector('#live-discovery-dialog').open && !document.querySelector('#live-discovery-fields').disabled")
    assert client.evaluate("document.querySelector('#live-schedule-time').value === '09:15'")
    client.evaluate("""(() => {
      const f = document.querySelector('#live-discovery-form').elements;
      f.source.value = 'demo'; f.universe.value = 'custom';
      f.universe.dispatchEvent(new Event('change'));
      f.symbols.value = %s;
      f.min_price.value = '0'; f.max_price.value = '1000';
      f.min_day_volume.value = '0'; f.min_change_pct.value = '-100'; f.limit.value = '100';
      document.querySelector('#live-schedule-enabled').checked = true;
      document.querySelector('#live-schedule-form').requestSubmit();
    })()""" % json.dumps(','.join(symbols)))
    client.wait("document.querySelector('#live-schedule-summary').textContent.includes('09:15') && !document.querySelector('#live-save-schedule').disabled")
    assert app.discovery_settings()['schedule'] == {'enabled': True, 'time': '09:15', 'timezone': 'America/New_York'}
    assert app.settings()['schedule']['enabled'] is False
    client.evaluate("document.querySelector('#live-discovery-form').requestSubmit()")
    client.wait("document.querySelectorAll('[data-live-candidate]').length === 51", seconds=20)
    check_candidate_metrics(client, app)
    client.evaluate("Array.from(document.querySelectorAll('[data-live-candidate]')).slice(0,50).forEach(field => field.click())")
    assert client.evaluate("document.querySelector('#live-candidate-selection').textContent.includes('50 of 50') && document.querySelectorAll('[data-live-candidate]')[50].disabled")
    client.screenshot(output / 'candidate-schedule-desktop.png')
    client.evaluate("document.querySelector('#live-use-candidates').click()")
    client.wait("!document.querySelector('#live-discovery-dialog').open")
    assert len(app.monitor.config['symbols']) == 50
    assert not app.monitor.status['running']
    client.call('Page.reload')
    client.wait("document.querySelector('#live-start') && !document.querySelector('#live-start').disabled")
    client.evaluate("document.querySelector('#live-discover').click()")
    client.wait("document.querySelectorAll('[data-live-candidate]').length === 51 && !document.querySelector('#live-discovery-fields').disabled")
    assert client.evaluate("document.querySelector('#live-schedule-enabled').checked && document.querySelector('#live-schedule-time').value === '09:15'")
    assert not app.monitor.status['running']
    client.evaluate("document.querySelector('#live-discovery-dialog').close(); document.querySelector('#live-start').click()")
    client.wait("document.querySelectorAll('#live-table [data-live-symbol]').length === 50", seconds=20)
    client.wait("!document.querySelector('#live-refresh').disabled")
    selected = list(app.monitor.config['symbols'])
    client.evaluate("document.querySelector('#live-refresh').click()")
    client.wait("document.querySelector('#live-refresh-status').textContent.includes('Data refreshed') && !document.querySelector('#live-refresh').disabled")
    assert app.monitor.status['running']
    assert app.monitor.config['symbols'] == selected
    assert app.monitor.snapshot()['status']['refresh']['state'] == 'completed'
    compact = app.monitor.snapshot(compact=True)
    assert all('chart' not in row and 'volume_history' not in row for row in compact['rows'])
    client.evaluate("document.querySelector('#live-search').value = %s; document.querySelector('#live-search').dispatchEvent(new Event('input'))" % json.dumps(selected[0]))
    client.wait("document.querySelectorAll('#live-table [data-live-symbol]').length === 1")
    client.evaluate("document.querySelector('#live-search').value = ''; document.querySelector('#live-search').dispatchEvent(new Event('input')); document.querySelector('#live-table [data-live-symbol]').click()")
    client.wait("document.querySelector('#live-report-data svg') && document.querySelectorAll('#live-history-details tbody tr').length === 30")
    assert client.evaluate("!document.querySelector('#live-print').disabled")
    client.evaluate("document.querySelector('#live-report-dialog').close()")
    assert not client.evaluate("document.documentElement.scrollWidth > innerWidth")
    client.screenshot(output / 'radar-50-desktop.png')
    client.call('Emulation.setDeviceMetricsOverride', {'width':390, 'height':844, 'deviceScaleFactor':1, 'mobile':True})
    assert client.evaluate("document.documentElement.scrollWidth <= innerWidth")
    client.screenshot(output / 'radar-50-mobile.png')
    client.evaluate("document.querySelector('#live-discover').click()")
    client.wait("!document.querySelector('#live-discovery-fields').disabled")
    assert client.evaluate("document.querySelector('#live-discovery-dialog').scrollWidth <= document.querySelector('#live-discovery-dialog').clientWidth")
    client.screenshot(output / 'candidate-schedule-mobile.png')
    check_mobile_candidate_scrolling(client, output)
    client.evaluate("document.querySelector('#live-discovery-dialog').close(); document.querySelector('#live-stop').click()")
    client.wait("document.querySelector('#live-connection').textContent.includes('stopped')")
    assert client.evaluate("document.querySelector('#live-refresh').disabled")
    client.evaluate("document.querySelector('#live-config').click(); document.querySelector('#live-symbols').value = %s; document.querySelector('#live-config-form').requestSubmit()" % json.dumps(','.join(symbols)))
    client.wait("document.querySelector('#live-config-error').textContent.includes('50 unique symbols')")
    client.evaluate("document.querySelector('#live-config-dialog').close()")
    client.call('Emulation.setDeviceMetricsOverride', {'width':1440, 'height':1050, 'deviceScaleFactor':1, 'mobile':False})
    check_metric_null_sorting(client, app)
    print('PASS saved candidate schedule/results, 50-symbol selection/radar, refresh, compact reports, 51-symbol rejection, and mobile layouts')


def check_alert_source_isolation(client, app, output):
    """Persist both sources without starting a market connection or altering earlier fixtures."""
    url = client.evaluate("location.href")
    capture = client.call('Page.addScriptToEvaluateOnNewDocument', {'source': """
      window.alertAckRequests = [];
      const originalFetch = window.fetch.bind(window);
      window.fetch = (input, options) => {
        if (String(input).includes('/api/monitor/alerts/ack') && options?.body) {
          window.alertAckRequests.push(JSON.parse(options.body));
        }
        return originalFetch(input, options);
      };
    """})['identifier']
    client.call('Page.navigate', {'url':'about:blank'})
    with tempfile.TemporaryDirectory(prefix='nomisma-alert-browser-') as temporary:
        isolated = Application(Path(temporary) / 'data')
        isolated.monitor.save_config({'source':'alpaca', 'symbols':['MARKETA', 'MARKETB']})

        def save_alert(identifier, source, symbol, fresh=False):
            when = datetime.now(timezone.utc) - (timedelta() if fresh else timedelta(minutes=5))
            isolated.store.save_monitor_alert({
                'id':identifier, 'created_at':when.isoformat(), 'market_time':when.isoformat(),
                'session_date':when.date().isoformat(), 'source':source,
                'feed':'synthetic' if source == 'demo' else 'sip', 'symbol':symbol,
                'level':'Buy', 'price':2.5, 'score':75, 'reasons':[], 'acknowledged':False,
            }, {})

        def inbox(ids, unread, source):
            expression = """JSON.stringify(Array.from(document.querySelectorAll(
              '#live-alerts [data-live-alert]'), el => el.dataset.liveAlert).sort()) === %s
              && document.querySelector('#live-alert-count').textContent.trim() === %s""" % (
                  json.dumps(json.dumps(sorted(ids), separators=(',', ':'))), json.dumps(str(unread)))
            client.wait(expression)
            assert client.evaluate("document.querySelector('#live-ack-all').disabled") == (unread == 0)
            text = client.evaluate("document.querySelector('#live-alerts').textContent")
            note = client.evaluate("document.querySelector('#live-notification-note').textContent")
            if source == 'alpaca':
                assert 'Synthetic demo' not in text and 'Demo alerts are synthetic' not in note
                assert 'Alpaca setups' in note
            else:
                assert 'Demo alerts are synthetic' in note

        def switch_source(source):
            client.evaluate("""document.querySelector('#live-config').click();
              document.querySelector('#live-source').value = %s;
              document.querySelector('#live-source').dispatchEvent(new Event('change', {bubbles:true}));
              document.querySelector('#live-config-form').requestSubmit();""" % json.dumps(source))
            client.wait("!document.querySelector('#live-config-dialog').open")
            assert isolated.monitor.config['source'] == source
            assert not isolated.monitor.status['running']

        def mark_all(source, ids):
            client.evaluate("document.querySelector('#live-ack-all').click()")
            inbox(ids, 0, source)
            assert client.evaluate('alertAckRequests.at(-1)') == {'all':True, 'source':source}
            assert all(isolated.store.monitor_alert(identifier)['acknowledged'] for identifier in ids)

        try:
            with patch.object(app, 'store', isolated.store), patch.object(app, 'monitor', isolated.monitor):
                save_alert('source-demo-a', 'demo', 'DEMOSA')
                save_alert('source-demo-b', 'demo', 'DEMOSB')
                client.call('Page.navigate', {'url':url})
                client.wait("document.querySelector('#live-alerts h3')?.textContent === 'No market alerts yet'")
                inbox([], 0, 'alpaca')
                client.evaluate("document.querySelector('#live-alerts').scrollIntoView({block:'center'})")
                client.screenshot(output / 'alpaca-inbox-demo-history-hidden.png')

                save_alert('source-market-a', 'alpaca', 'MARKETA')
                save_alert('source-market-b', 'alpaca', 'MARKETB')
                market_ids = ['source-market-a', 'source-market-b']
                demo_ids = ['source-demo-a', 'source-demo-b']
                inbox(market_ids, 2, 'alpaca')
                switch_source('demo')
                inbox(demo_ids, 2, 'demo')
                switch_source('alpaca')
                inbox(market_ids, 2, 'alpaca')
                mark_all('alpaca', market_ids)
                assert not any(isolated.store.monitor_alert(identifier)['acknowledged'] for identifier in demo_ids)
                switch_source('demo')
                inbox(demo_ids, 2, 'demo')
                mark_all('demo', demo_ids)
                switch_source('alpaca')
                inbox(market_ids, 0, 'alpaca')

                # Simulate a cached/older backend that sends mixed alerts and a stale
                # status source. The UI must use config.source for all alert behavior.
                original_snapshot = isolated.monitor.snapshot
                phase = {'message':'Mixed-source baseline'}

                def mixed_snapshot(*args, **kwargs):
                    result = original_snapshot(*args, **kwargs)
                    result['alerts'] = isolated.store.monitor_alerts()
                    result['status'].update(running=True, connection='live', message=phase['message'],
                                            source='demo' if result['config']['source'] == 'alpaca' else 'alpaca')
                    return result

                with patch.object(isolated.monitor, 'snapshot', mixed_snapshot):
                    client.call('Page.reload')
                    client.wait("document.querySelector('#live-status-message')?.textContent === 'Mixed-source baseline'")
                    inbox(market_ids, 0, 'alpaca')
                    announcement = client.evaluate("document.querySelector('#live-announcement').textContent")
                    save_alert('source-demo-new', 'demo', 'DEMOSNEW', fresh=True)
                    phase['message'] = 'Hidden demo alert received'
                    client.wait("document.querySelector('#live-status-message').textContent === 'Hidden demo alert received'")
                    inbox(market_ids, 0, 'alpaca')
                    assert client.evaluate("document.querySelector('#live-announcement').textContent") == announcement

                    # Changing source must establish a baseline, even when previously
                    # hidden records are recent enough to qualify for notifications.
                    isolated.monitor.save_config({'source':'demo'})
                    phase['message'] = 'Demo source selected'
                    client.wait("document.querySelector('#live-status-message').textContent === 'Demo source selected'")
                    inbox(demo_ids + ['source-demo-new'], 1, 'demo')
                    assert client.evaluate("document.querySelector('#live-announcement').textContent") == announcement
                    isolated.monitor.save_config({'source':'alpaca'})
                    phase['message'] = 'Alpaca source selected'
                    client.wait("document.querySelector('#live-status-message').textContent === 'Alpaca source selected'")
                    inbox(market_ids, 0, 'alpaca')
                    save_alert('source-market-new', 'alpaca', 'MARKETNEW', fresh=True)
                    phase['message'] = 'New Alpaca alert received'
                    client.wait("document.querySelector('#live-announcement').textContent.includes('MARKETNEW')")
                    inbox(market_ids + ['source-market-new'], 1, 'alpaca')
                    client.evaluate("document.querySelector('#live-alerts').scrollIntoView({block:'center'})")
                    client.screenshot(output / 'alpaca-inbox-mixed-source-filtered.png')

                client.evaluate("document.querySelector('#live-journal').click()")
                client.wait("document.querySelectorAll('#live-journal-results [data-live-alert]').length === 6")
                journal_ids = client.evaluate("Array.from(document.querySelectorAll('#live-journal-results [data-live-alert]'), el => el.dataset.liveAlert)")
                assert set(journal_ids) == set(market_ids + demo_ids + ['source-demo-new', 'source-market-new'])
                journal = client.evaluate("document.querySelector('#live-journal-results').textContent")
                assert 'Synthetic demo' in journal and 'Alpaca' in journal
                assert isolated.store.monitor_alerts_total() == 6
                client.screenshot(output / 'research-journal-both-alert-sources.png')
                assert not isolated.monitor.status['running'], 'The fixture must never start a provider connection.'
        finally:
            client.call('Page.removeScriptToEvaluateOnNewDocument', {'identifier':capture})
            client.call('Page.navigate', {'url':url})
            client.wait("document.querySelector('#live-start') && !document.querySelector('#live-start').disabled")
            isolated.stop_event.set()
            isolated.monitor.close()
    print('PASS source-specific alert inbox/counts/copy, source switching, scoped Mark read, mixed-source journal, and old-backend notification isolation')


def check_alert_refresh(client, app, output):
    """Explicit refresh must work even when the background event stream is idle."""
    url = client.evaluate('location.href')
    shim = client.call('Page.addScriptToEvaluateOnNewDocument', {'source': """
      window.EventSource = class {
        constructor() { this.readyState = 1; }
        addEventListener() {}
        close() { this.readyState = 2; }
      };
      const originalFetch = window.fetch.bind(window);
      window.alertRefreshChecks = {requests:[], hold:false, fail:false, release:null};
      window.fetch = async (input, options) => {
        const checks = window.alertRefreshChecks;
        const path = new URL(String(input), location.href).pathname;
        checks.requests.push({path, method:options?.method || 'GET'});
        if (path === '/api/monitor') {
          if (checks.hold) await new Promise(resolve => { checks.release = resolve; });
          if (checks.fail) throw new Error('Alert refresh test failure');
        }
        return originalFetch(input, options);
      };
    """})['identifier']
    client.call('Page.navigate', {'url':'about:blank'})
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    with tempfile.TemporaryDirectory(prefix='nomisma-refresh-browser-') as temporary:
        isolated = Application(Path(temporary) / 'data')
        isolated.monitor.save_config({'source':'demo', 'symbols':['REFRESHQA']})
        isolated.monitor.bundle = demo_bundle(['REFRESHQA'], step=3)
        isolated.monitor.status.update(running=True, connection='demo', source='demo', feed='synthetic',
                                       session=isolated.monitor.bundle['session'])
        original_worker = isolated.monitor._refresh_worker

        def delayed_refresh(*args):
            entered.set()
            try:
                if release.wait(15):
                    original_worker(*args)
            finally:
                finished.set()

        def save_alert(identifier):
            when = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
            isolated.store.save_monitor_alert({
                'id':identifier, 'created_at':when, 'market_time':when,
                'session_date':when[:10], 'source':'demo', 'feed':'synthetic', 'symbol':'REFRESHQA',
                'level':'Buy', 'price':2.5, 'score':75, 'reasons':[], 'acknowledged':False,
            }, {})

        def inbox(ids):
            client.wait("JSON.stringify(Array.from(document.querySelectorAll('#live-alerts [data-live-alert]'), el => el.dataset.liveAlert).sort()) === %s && document.querySelector('#live-alert-count').textContent.trim() === %s" %
                        (json.dumps(json.dumps(sorted(ids), separators=(',', ':'))), json.dumps(str(len(ids)))))

        try:
            with patch.object(app, 'store', isolated.store), patch.object(app, 'monitor', isolated.monitor), \
                    patch.object(isolated.monitor, '_refresh_worker', side_effect=delayed_refresh):
                client.call('Page.navigate', {'url':url.split('#')[0] + '#live'})
                client.wait("document.querySelector('#live-refresh') && !document.querySelector('#live-refresh').disabled")
                inbox([])
                client.evaluate("alertRefreshChecks.requests = []; document.querySelector('#live-refresh').click()")
                assert entered.wait(2), 'Provider refresh worker did not start'
                client.wait("document.querySelector('#live-refresh').disabled && document.querySelector('#live-refresh').textContent.includes('Refreshing')")
                save_alert('during-provider-refresh')
                inbox([])
                release.set()
                client.wait("!document.querySelector('#live-refresh').disabled && document.querySelector('#live-refresh-status').textContent.includes('Data refreshed')", seconds=20)
                inbox(['during-provider-refresh'])
                assert isolated.monitor.refresh_status['state'] == 'completed'
                assert isolated.monitor.status['running'] and isolated.monitor.config['symbols'] == ['REFRESHQA']
                requests = client.evaluate('alertRefreshChecks.requests')
                assert sum(item['path'] == '/api/monitor/refresh' for item in requests) == 1
                assert any(item['path'] == '/api/monitor' for item in requests), 'Completion depended on SSE instead of explicit polling'

                client.evaluate("document.querySelector('#live-stop').click()")
                client.wait("document.querySelector('#live-connection').textContent.includes('stopped')")
                assert client.evaluate("!document.querySelector('#live-alert-refresh').disabled")
                save_alert('stopped-inbox-refresh')
                inbox(['during-provider-refresh'])
                client.evaluate("""alertRefreshChecks.requests = []; alertRefreshChecks.hold = true;
                  const button = document.querySelector('#live-alert-refresh');
                  button.click(); button.click();
                  button.dispatchEvent(new MouseEvent('click', {bubbles:true}));""")
                client.wait('alertRefreshChecks.release !== null')
                assert client.evaluate("document.querySelector('#live-alert-refresh').disabled && document.querySelector('#live-alert-refresh').getAttribute('aria-busy') === 'true'")
                assert client.evaluate("alertRefreshChecks.requests.filter(item => item.path === '/api/monitor').length") == 1
                client.evaluate('alertRefreshChecks.hold = false; alertRefreshChecks.release()')
                inbox(['during-provider-refresh', 'stopped-inbox-refresh'])
                client.wait("!document.querySelector('#live-alert-refresh').disabled && document.querySelector('#live-alert-refresh-status').textContent.includes('Checked') && document.querySelector('#live-alert-refresh-status').textContent.includes('1 new setup')")
                assert client.evaluate("document.querySelector('#live-alert-refresh').getAttribute('aria-busy') === 'false'")
                assert client.evaluate("alertRefreshChecks.requests.filter(item => item.path === '/api/monitor').length") == 1
                assert client.evaluate("alertRefreshChecks.requests.every(item => item.method === 'GET')")
                assert not isolated.monitor.status['running']
                assert isolated.monitor.config['symbols'] == ['REFRESHQA']
                client.evaluate("document.querySelector('#live-alert-refresh').click()")
                client.wait("!document.querySelector('#live-alert-refresh').disabled && document.querySelector('#live-alert-refresh-status').textContent.includes('No new setups')")

                before = client.evaluate("document.querySelector('#live-alerts').innerHTML")
                client.evaluate("alertRefreshChecks.fail = true; document.querySelector('#live-alert-refresh').click()")
                client.wait("!document.querySelector('#live-alert-refresh').disabled && (document.querySelector('#live-error').textContent + document.querySelector('#live-alert-refresh-status').textContent).includes('Alert refresh test failure')")
                assert client.evaluate("document.querySelector('#live-alerts').innerHTML") == before
                save_alert('retry-inbox-refresh')
                client.evaluate("alertRefreshChecks.fail = false; document.querySelector('#live-alert-refresh').click()")
                inbox(['during-provider-refresh', 'stopped-inbox-refresh', 'retry-inbox-refresh'])
                client.wait("!document.querySelector('#live-alert-refresh').disabled && document.querySelector('#live-alert-refresh-status').textContent.includes('1 new setup')")
                assert client.evaluate("document.querySelector('#live-error').classList.contains('hidden')")
                assert not isolated.monitor.status['running']
                assert isolated.store.monitor_alerts_total() == 3
                client.evaluate("document.querySelector('#live-alerts').scrollIntoView({block:'center'})")
                client.screenshot(output / 'setup-alert-refresh.png')
        finally:
            release.set()
            if entered.is_set():
                assert finished.wait(3), 'Refresh fixture worker did not stop'
            client.call('Page.removeScriptToEvaluateOnNewDocument', {'identifier':shim})
            client.call('Page.navigate', {'url':url})
            client.wait("document.querySelector('#live-start') && !document.querySelector('#live-start').disabled")
            isolated.stop_event.set()
            isolated.monitor.close()
    print('PASS explicit Refresh data completion without SSE, alerts saved during refresh, stopped inbox Refresh, duplicate suppression, failure preservation, and retry')


def run(output, chrome, alerts_only=False):
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
            if alerts_only:
                client.call('Page.navigate', {'url':'http://127.0.0.1:%d/#live' % server.server_port})
                client.wait("document.querySelector('#live-start') && !document.querySelector('#live-start').disabled")
                check_alert_refresh(client, app, output)
                check_alert_source_isolation(client, app, output)
                assert not client.errors, 'Browser errors: ' + json.dumps(client.errors)
                print('PASS no uncaught JavaScript or browser resource errors')
                return
            check_live(client, app, server.server_port, output, temporary)
            check_workspace_improvements(client, app, output)
            check_alert_refresh(client, app, output)
            check_alert_source_isolation(client, app, output)
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
            client.wait("document.querySelector('#results-table [data-watch]').classList.contains('saved')")
            print("PASS stock detail and persistent watchlist interaction")

            client.evaluate("document.querySelector('[data-view=history]').click()")
            client.wait("!document.querySelector('#history-view').classList.contains('hidden') && document.querySelector('#history-results').textContent.includes('2025')")
            client.evaluate("document.querySelector('[data-view=dashboard]').click()")
            print("PASS history navigation")

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
    parser.add_argument("--alerts-only", action="store_true", help="Run only the isolated alert refresh and source regressions.")
    args = parser.parse_args()
    run(args.output.resolve(), args.chrome, alerts_only=args.alerts_only)
