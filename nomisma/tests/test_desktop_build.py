import json
import plistlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import build_desktop


class DesktopBuildTests(unittest.TestCase):
    def test_backend_allowlist_excludes_secrets_data_and_caches(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder) / "project"
            destination = Path(folder) / "backend"
            expected = {"run.py", "launch.py", "desktop/host.py", "nomisma/server.py", "nomisma/static/index.html"}
            excluded = {".env", "data/nomisma.sqlite3", "nomisma/.env", "nomisma/static/.env",
                        "nomisma/static/private.json", "nomisma/__pycache__/cached.py", "tests/test_server.py"}
            for name in expected | excluded:
                path = project / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("example")
            self.assertEqual(set(build_desktop.copy_backend(project, destination)), expected)
            self.assertEqual({path.relative_to(destination).as_posix() for path in destination.rglob("*") if path.is_file()}, expected)

    def test_rejects_symlinked_backend_source(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder) / "project"
            (project / "desktop").mkdir(parents=True)
            for name in ("run.py", "launch.py", "desktop/host.py"):
                (project / name).write_text("")
            secret = Path(folder) / "secret"
            secret.write_text("private")
            (project / "launch.py").unlink()
            try:
                (project / "launch.py").symlink_to(secret)
            except OSError as error:
                if getattr(error, "winerror", None) == 1314:
                    self.skipTest("Windows developer mode or symlink privilege is not available")
                raise
            with self.assertRaisesRegex(RuntimeError, "outside the project"):
                build_desktop.copy_backend(project, Path(folder) / "backend")

    def test_workspace_configuration_contains_paths_only_and_portable_has_none(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            (project / ".env").write_text("SECRET=never-copy-this")
            config = build_desktop.workspace_config(project)
            self.assertEqual(config, {"data_directory": str((project / "data").resolve()),
                                      "env_file": str((project / ".env").resolve()),
                                      "project_directory": str(project.resolve())})
            self.assertNotIn("never-copy-this", json.dumps(config))
            self.assertEqual(build_desktop.workspace_config(project, portable=True), {})

    def test_refuses_to_replace_unrelated_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "Nomisma.app"
            staged = Path(folder) / "New.app"
            target.mkdir()
            staged.mkdir()
            (target / "valuable.txt").write_text("keep")
            with self.assertRaisesRegex(RuntimeError, "different application"):
                build_desktop.replace_bundle(staged, target)
            self.assertEqual((target / "valuable.txt").read_text(), "keep")
            self.assertTrue(staged.exists())

    def test_application_replacement_rolls_back_when_rename_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "Nomisma.app"
            (target / "Contents").mkdir(parents=True)
            with (target / "Contents/Info.plist").open("wb") as handle:
                plistlib.dump({"CFBundleIdentifier": build_desktop.APP_ID}, handle)
            (target / "old.txt").write_text("old build")
            with self.assertRaises(FileNotFoundError):
                build_desktop.replace_bundle(Path(folder) / "missing.app", target)
            self.assertEqual((target / "old.txt").read_text(), "old build")
            self.assertEqual(list(Path(folder).iterdir()), [target])

    def test_python_environment_does_not_leak_runtime_overrides(self):
        with patch.dict(build_desktop.os.environ, {"PYTHONHOME": "/bad", "PYTHONPATH": "/also-bad",
                                                 "DYLD_LIBRARY_PATH": "/wrong", "PATH": "/usr/bin"}, clear=True):
            self.assertEqual(build_desktop.clean_python_environment(), {"PATH": "/usr/bin"})


if __name__ == "__main__":
    unittest.main()
