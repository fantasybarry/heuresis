import tempfile
import os
import json
import socket
import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from unittest.mock import patch

import launch


class LauncherTests(unittest.TestCase):
    def test_local_bind_probe_distinguishes_free_and_occupied_ports(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            port = listener.getsockname()[1]
            self.assertFalse(launch.port_available(port))
        self.assertTrue(launch.port_available(port))

    def test_loopback_health_ignores_proxy_environment(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                data = json.dumps({"app":"nomisma", "status":"ok", "data_directory":"local"}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with patch.dict(os.environ, {"http_proxy":"http://127.0.0.1:1", "HTTP_PROXY":"http://127.0.0.1:1",
                                         "no_proxy":"", "NO_PROXY":""}), \
                    patch("urllib.request.getproxies", side_effect=AssertionError("Local health checks must bypass proxy discovery")):
                self.assertEqual(launch.health(server.server_port)["app"], "nomisma")
        finally:
            server.shutdown()
            worker.join(timeout=3)
            server.server_close()

    def test_reuses_ready_workspace_without_starting_another_process(self):
        with tempfile.TemporaryDirectory() as directory:
            status = {"app": "nomisma", "status": "ok", "data_directory": directory}
            with patch.object(launch, "health", return_value=status), patch.object(launch.subprocess, "Popen") as start, \
                    patch.object(launch.webbrowser, "open") as browser:
                self.assertEqual(launch.launch(8765, directory), "http://127.0.0.1:8765/#live")
            start.assert_not_called()
            browser.assert_called_once()

    def test_wrong_workspace_or_occupied_port_does_not_launch_or_open(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(launch, "health", return_value={"data_directory": str(Path(directory) / "other")}), \
                    patch.object(launch.webbrowser, "open") as browser, patch.object(launch.subprocess, "Popen") as start:
                with self.assertRaisesRegex(RuntimeError, "different"):
                    launch.launch(8765, directory)
                start.assert_not_called()
                browser.assert_not_called()
            with patch.object(launch, "health", return_value=None), patch.object(launch, "port_open", return_value=True), \
                    patch.object(launch.subprocess, "Popen") as start:
                with self.assertRaisesRegex(RuntimeError, "occupied"):
                    launch.launch(8765, directory)
                start.assert_not_called()

    def test_waits_for_health_before_opening_browser(self):
        with tempfile.TemporaryDirectory() as directory:
            status = {"data_directory": directory}
            with patch.object(launch, "health", side_effect=[None, None, status]), \
                    patch.object(launch, "port_open", return_value=False), patch.object(launch.time, "sleep"), \
                    patch.object(launch.subprocess, "Popen") as start, patch.object(launch.webbrowser, "open") as browser:
                start.return_value.poll.return_value = None
                launch.launch(8765, directory)
                if os.name == "nt":
                    self.assertEqual(start.call_args.kwargs["creationflags"], launch.subprocess.CREATE_NO_WINDOW)
                else:
                    self.assertTrue(start.call_args.kwargs["start_new_session"])
                browser.assert_called_once_with("http://127.0.0.1:8765/#live")

    def test_failure_reports_log_without_opening_browser(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(launch, "health", return_value=None), patch.object(launch, "port_open", return_value=False), \
                    patch.object(launch.subprocess, "Popen") as start, patch.object(launch.webbrowser, "open") as browser:
                start.return_value.poll.return_value = 1
                with self.assertRaisesRegex(RuntimeError, "nomisma.log"):
                    launch.launch(8765, directory)
                browser.assert_not_called()
