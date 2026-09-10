import json
import os
import queue
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

from desktop import host


class DesktopHostTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def test_existing_research_is_used_without_copying_credentials(self):
        project = self.root / "project"
        project.mkdir()
        (project / "run.py").write_text("pass")
        config = {"project_directory": str(project), "data_directory": str(project / "data"), "env_file": str(project / ".env")}
        data, environment = host.workspace_paths(config, home=self.root)
        self.assertEqual(data, project / "data")
        self.assertEqual(environment, project / ".env")
        self.assertFalse(environment.exists())

    def test_portable_app_uses_application_support(self):
        config = {"project_directory": str(self.root / "missing"), "data_directory": str(self.root / "missing/data"),
                  "env_file": str(self.root / "missing/.env")}
        data, environment = host.workspace_paths(config, home=self.root)
        self.assertEqual(data, host.support_directory(home=self.root) / "data")
        self.assertEqual(environment.parent, data.parent)
        self.assertEqual(environment.name, ".env")

    def test_existing_database_still_works_without_source_checkout(self):
        data = self.root / "data"
        data.mkdir()
        (data / "nomisma.sqlite3").touch()
        config = {"data_directory": str(data), "env_file": str(self.root / ".env")}
        self.assertEqual(host.workspace_paths(config)[0], data)

    def test_explicit_test_workspace_and_env_override_personal_config(self):
        data, environment = host.workspace_paths({}, self.root / "isolated", self.root / "isolated.env")
        self.assertEqual(data, self.root / "isolated")
        self.assertEqual(environment, self.root / "isolated.env")
        with self.assertRaises(ValueError):
            host.workspace_paths({"data_directory": "relative"})

    def test_reuses_matching_server_before_considering_another_free_port(self):
        with patch.object(host.launcher, "health", side_effect=lambda port: {"data_directory": str(self.root)} if port == 8767 else None), \
                patch.object(host.launcher, "port_open", return_value=False):
            self.assertEqual(host.choose_port(self.root), (8767, False))

    def test_never_reuses_another_workspaces_server(self):
        with patch.object(host.launcher, "health", side_effect=lambda port: {"data_directory": str(self.root / "other")} if port == 8765 else None), \
                patch.object(host.launcher, "port_open", return_value=False):
            self.assertEqual(host.choose_port(self.root), (8766, True))

    def test_busy_preferred_port_fails_without_replacing_existing_process(self):
        with patch.object(host.launcher, "health", return_value=None), patch.object(host.launcher, "port_open", return_value=True):
            with self.assertRaisesRegex(RuntimeError, "No local port"):
                host.choose_port(self.root, 8765)

    def test_start_emits_no_keys_and_leaves_reused_environment_untouched(self):
        with patch.object(host, "choose_port", return_value=(8765, False)), \
                patch.object(host, "load_environment") as environment, \
                patch.object(host.launcher, "launch", return_value="http://127.0.0.1:8765/#live") as launch:
            result = host.start(data_directory=self.root, env_file=self.root / ".env")
            launch.assert_called_once_with(8765, self.root, open_browser=False)
            environment.assert_not_called()
        self.assertFalse(result["owned_server"])
        self.assertEqual(json.loads((self.root / ".desktop-server.json").read_text()), {"port": 8765})
        if os.name != "nt":
            self.assertEqual((self.root / ".desktop-server.json").stat().st_mode & 0o777, 0o600)

    def test_new_server_loads_separate_environment_file(self):
        with patch.object(host, "choose_port", return_value=(8766, True)), \
                patch.object(host, "load_environment") as environment, \
                patch.object(host.launcher, "launch", return_value="http://127.0.0.1:8766/#live"):
            result = host.start(data_directory=self.root, env_file=self.root / ".env")
        environment.assert_called_once_with(self.root / ".env")
        self.assertTrue(result["owned_server"])

    def test_windows_uses_per_user_local_appdata(self):
        data, environment = host.workspace_paths({}, home=self.root, platform="win32")
        self.assertEqual(data, self.root / "AppData/Local/Nomisma/data")
        self.assertEqual(environment, self.root / "AppData/Local/Nomisma/.env")
        custom = self.root / "Custom Local"
        self.assertEqual(host.support_directory(platform="win32", environ={"LOCALAPPDATA":str(custom)}), custom / "Nomisma")

    def test_empty_non_object_configuration_is_rejected(self):
        for configuration in ([], "", False):
            with self.subTest(configuration=configuration), self.assertRaises(ValueError):
                host.workspace_paths(configuration)

    def test_managed_server_reuses_without_ownership_and_stops_on_parent_exit(self):
        """Exercise the real native-app protocol, HTTP readiness and shutdown."""
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        data = self.root / "Managed Workspace"
        empty_environment = self.root / "empty.env"
        empty_environment.write_text("")
        environment = {key:value for key,value in os.environ.items()
                       if not key.startswith(("ALPACA_", "FMP_", "PYTHON"))}
        command = [sys.executable, "-B", str(Path(host.__file__).resolve()), "--managed", "--data-dir", str(data),
                   "--env-file", str(empty_environment), "--port", str(port)]
        with tempfile.TemporaryFile(mode="w+b") as errors:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=errors, text=True, env=environment)
            try:
                ready = queue.Queue()
                reader = threading.Thread(target=lambda: ready.put(process.stdout.readline()), daemon=True)
                reader.start()
                result = json.loads(ready.get(timeout=20))
                self.assertTrue(result["owned_server"])
                self.assertEqual(result["desktop_api"], 1)
                with urlopen("http://127.0.0.1:%d/api/health" % port, timeout=3) as response:
                    self.assertEqual(Path(json.load(response)["data_directory"]).resolve(), data)
                with urlopen("http://127.0.0.1:%d/api/monitor" % port, timeout=3) as response:
                    self.assertFalse(json.load(response)["status"]["running"])
                reused = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                        env=environment, timeout=10, check=True)
                self.assertFalse(json.loads(reused.stdout)["owned_server"])
                self.assertIsNone(process.poll(), "The second window must not stop the first window's service")
                process.stdin.close()
                process.stdin = None
                remaining, _ = process.communicate(timeout=15)
                self.assertEqual(process.returncode, 0)
                self.assertEqual(remaining, "", "stdout is only the readiness record")
                self.assertIsNone(host.launcher.health(port))
                self.assertTrue((data / "nomisma.sqlite3").is_file())
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=10)
