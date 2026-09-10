import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from tools import check_windows


class WindowsVerificationTests(unittest.TestCase):
    def test_checksums_require_matching_versions_and_reject_path_escape(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            lines = []
            for name in ("Nomisma-1.0.0-win-x64-setup.exe", "Nomisma-1.0.0-win-x64-portable.zip"):
                (directory / name).write_bytes(name.encode())
                lines.append(hashlib.sha256(name.encode()).hexdigest() + "  " + name)
            manifest = directory / "SHA256SUMS.txt"
            manifest.write_text("\n".join(lines))
            installer, archive = check_windows.verified_artifacts(directory)
            self.assertEqual(installer.suffix, ".exe")
            self.assertEqual(archive.suffix, ".zip")
            manifest.write_text(lines[0].replace("  Nomisma", "  ../Nomisma") + "\n" + lines[1])
            with self.assertRaisesRegex(ValueError, "Invalid"):
                check_windows.verified_artifacts(directory)
            manifest.write_text("\n".join(lines))
            installer.write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "checksum"):
                check_windows.verified_artifacts(directory)

    def test_release_archive_rejects_credentials_and_developer_workspace(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "portable.zip"
            def write_archive(config, extra=None):
                with zipfile.ZipFile(archive, "w") as handle:
                    for name in ("Nomisma.exe", "resources/python/python.exe", "resources/backend/desktop/host.py"):
                        handle.writestr("Nomisma/" + name, b"example")
                    handle.writestr("Nomisma/resources/workspace.json", json.dumps(config))
                    if extra:
                        handle.writestr(extra, "private")
            write_archive({})
            self.assertEqual(check_windows.verify_archive(archive), 4)
            write_archive({"env_file": "/private/.env"})
            with self.assertRaisesRegex(ValueError, "developer workspace"):
                check_windows.verify_archive(archive)
            write_archive({}, "Nomisma/resources/.env")
            with self.assertRaisesRegex(ValueError, "private data"):
                check_windows.verify_archive(archive)
            write_archive({}, "Nomisma/../escape")
            with self.assertRaisesRegex(ValueError, "unsafe path"):
                check_windows.verify_archive(archive)

    def test_native_result_must_prove_isolation_and_shutdown(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary) / "research"
            result = {field: True for field in check_windows.SMOKE_FLAGS}
            result.update(platform="windows", webview_version="150.0.0.0", data_directory=str(data),
                          url="http://127.0.0.1:8765/#live")
            self.assertEqual(check_windows.validate_smoke_result(result, data), 8765)
            with self.assertRaisesRegex(ValueError, "research directory"):
                check_windows.validate_smoke_result(result, data / "wrong")
            result["backend_stopped"] = False
            with self.assertRaisesRegex(ValueError, "every startup"):
                check_windows.validate_smoke_result(result, data)
            result["backend_stopped"] = True
            result["url"] = "https://example.com:8765/"
            with self.assertRaisesRegex(ValueError, "server address"):
                check_windows.validate_smoke_result(result, data)


if __name__ == "__main__":
    unittest.main()
