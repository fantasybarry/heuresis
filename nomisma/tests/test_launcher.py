import tempfile
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import launch


class LauncherTests(unittest.TestCase):
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
