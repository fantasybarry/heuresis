import argparse
import hashlib
import json
import stat
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools import build_windows


class WindowsBuildTests(unittest.TestCase):
    def test_backend_allowlist_excludes_secrets_databases_mac_sources_and_caches(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder) / "project"
            target = Path(folder) / "backend"
            expected = {"run.py", "launch.py", "desktop/host.py", "nomisma/server.py", "nomisma/static/index.html"}
            excluded = {".env", "data/nomisma.sqlite3", "desktop/App.swift", "nomisma/.private/hidden.py",
                        "nomisma/static/.env", "nomisma/static/private.json", "nomisma/__pycache__/cached.py"}
            for name in expected | excluded:
                path = project / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("test")
            self.assertEqual(set(build_windows.copy_backend(project, target)), expected)
            self.assertEqual({p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()}, expected)

    def test_backend_symlink_cannot_include_external_data(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder) / "source"
            (project / "desktop").mkdir(parents=True)
            (project / "run.py").write_text("")
            (project / "desktop/host.py").write_text("")
            private = Path(folder) / "private"
            private.write_text("secret")
            try:
                (project / "launch.py").symlink_to(private)
            except OSError:
                self.skipTest("Creating symlinks requires Windows Developer Mode")
            with self.assertRaisesRegex(RuntimeError, "outside the project"):
                build_windows.copy_backend(project, Path(folder) / "target")

    def test_versions_cannot_inject_nsis_or_output_paths(self):
        self.assertEqual(build_windows.validate_version("1.20.300"), "1.20.300")
        for value in ("1.0", "1.0.0-beta", "../1.0.0", "1.0.0\n", "01.0.0", "10000.0.0"):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                build_windows.validate_version(value)

    def test_archive_paths_reject_traversal_windows_streams_and_nsis_syntax(self):
        for name in ("../outside", "/root/file", "C:/file", "file:secret", "a\\..\\b", "a//b", "$INSTDIR/file", 'a"b'):
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                build_windows.safe_relative(name)

    def test_malicious_archive_does_not_extract_outside_destination(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "payload.zip"
            with zipfile.ZipFile(archive, "w") as zipped:
                zipped.writestr("../secret", "payload")
            with self.assertRaises(RuntimeError):
                build_windows.extract_verified_archive(archive, Path(folder) / "output")
            self.assertFalse((Path(folder) / "secret").exists())

    def test_archive_symlinks_and_case_collisions_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "payload.zip"
            entry = zipfile.ZipInfo("linked")
            entry.create_system = 3
            entry.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(archive, "w") as zipped:
                zipped.writestr(entry, "../private")
            with self.assertRaises(RuntimeError):
                build_windows.extract_verified_archive(archive, Path(folder) / "links")
            with zipfile.ZipFile(archive, "w") as zipped:
                zipped.writestr("FILE", "one")
                zipped.writestr("file", "two")
            with self.assertRaises(RuntimeError):
                build_windows.extract_verified_archive(archive, Path(folder) / "case")

    def test_cached_dependency_is_rehashed_before_use(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder)
            artifact = cache / "runtime.zip"
            artifact.write_bytes(b"official artifact")
            expected = hashlib.sha256(artifact.read_bytes()).hexdigest()
            self.assertEqual(build_windows.download_verified("https://www.python.org/runtime.zip", expected, cache), artifact)
            artifact.write_bytes(b"modified artifact")
            with self.assertRaisesRegex(RuntimeError, "checksum failed"):
                build_windows.download_verified("https://www.python.org/runtime.zip", expected, cache)

    def test_pe_header_checks_native_architecture(self):
        with tempfile.TemporaryDirectory() as folder:
            executable = Path(folder) / "Nomisma.exe"
            content = bytearray(72)
            content[:2] = b"MZ"
            struct.pack_into("<I", content, 0x3C, 64)
            content[64:68] = b"PE\0\0"
            struct.pack_into("<H", content, 68, 0x8664)
            executable.write_bytes(content)
            self.assertEqual(build_windows.require_pe(executable, 0x8664), 0x8664)
            with self.assertRaisesRegex(RuntimeError, "architecture"):
                build_windows.require_pe(executable, 0x14C)
            executable.write_bytes(b"not a Windows binary")
            with self.assertRaisesRegex(RuntimeError, "Windows executable"):
                build_windows.require_pe(executable)

    def test_manifest_has_hashes_and_no_local_workspace_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            application = Path(folder)
            (application / "resources").mkdir()
            (application / "resources/workspace.json").write_text("{}\n")
            (application / "Nomisma.exe").write_bytes(b"binary")
            files = build_windows.write_manifest(application, "1.0.0")
            self.assertIn(".nomisma-install-id", files)
            raw = (application / "bundle-manifest.json").read_text()
            self.assertNotIn(folder, raw)
            manifest = json.loads(raw)
            self.assertEqual(manifest["application_id"], build_windows.APP_ID)
            self.assertEqual(manifest["files"][0]["sha256"], hashlib.sha256(b"binary").hexdigest())

    def test_manifest_refuses_private_user_data(self):
        with tempfile.TemporaryDirectory() as folder:
            application = Path(folder)
            for name in (".env", "nomisma.sqlite3", "settings.db"):
                path = application / name
                path.write_text("private")
                with self.subTest(name=name), self.assertRaisesRegex(RuntimeError, "Private data"):
                    build_windows.write_manifest(application, "1.0.0")
                path.unlink()

    def test_uninstaller_deletes_only_literal_owned_files_and_empty_directories(self):
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / "uninstall.nsh"
            build_windows.write_uninstall_list(["Nomisma.exe", "resources/backend/run.py"], script)
            result = script.read_text()
            self.assertIn('Delete "$INSTDIR\\resources\\backend\\run.py"', result)
            self.assertLess(result.index('RMDir "$INSTDIR\\resources\\backend"'), result.index('RMDir "$INSTDIR\\resources"'))
            self.assertNotIn("RMDir /r", result)
            self.assertNotIn("$LOCALAPPDATA", result)
            with self.assertRaises(RuntimeError):
                build_windows.write_uninstall_list(["../user-file"], script)

    def test_redistribution_licenses_are_copied_from_resolved_packages(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project, packages, application = root / "source", root / "packages", root / "app"
            (project / "desktop/windows/obj").mkdir(parents=True)
            dependencies = ["Microsoft.NETCore.App.Host.win-x64", "Microsoft.NETCore.App.Runtime.win-x64",
                            "Microsoft.WindowsDesktop.App.Runtime.win-x64"]
            for name in ["Microsoft.Web.WebView2"] + dependencies:
                package = packages / name.lower() / "1.0.0"
                package.mkdir(parents=True)
                (package / "LICENSE.txt").write_text(f"License for {name}")
                (package / "NOTICE.txt").write_text("Notice")
                (package / "unrelated-file").write_text("do not distribute")
            assets = {"packageFolders": {str(packages): {}}, "libraries": {"Microsoft.Web.WebView2/1.0.0": {}},
                      "project": {"frameworks": {"net10.0-windows": {
                          "downloadDependencies": [{"name": name, "version": "[1.0.0, 1.0.0]"} for name in dependencies]}}}}
            (project / "desktop/windows/obj/project.assets.json").write_text(json.dumps(assets))
            build_windows.preserve_licenses(project, application)
            files = list((application / "licenses").rglob("*"))
            self.assertEqual(len([path for path in files if path.name == "LICENSE.txt"]), 4)
            self.assertFalse(any(path.name == "unrelated-file" for path in files))
            self.assertNotIn(str(packages), (application / "licenses/README.txt").read_text())


if __name__ == "__main__":
    unittest.main()
