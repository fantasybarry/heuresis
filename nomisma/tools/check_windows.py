#!/usr/bin/env python3
"""Verify Windows release artifacts on a clean Windows test account.

Installs, starts the real WebView2 application with isolated research data, and
uninstalls it. Refuses to run if Nomisma already exists in this Windows profile.
No API keys are needed. Use the GitHub Actions Windows runner or a disposable VM.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit
import uuid
import zipfile


ARTIFACT_NAME = re.compile(r"Nomisma-(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)-win-x64-(setup\.exe|portable\.zip)")
SMOKE_FLAGS = ("success", "owned_server", "page_loaded", "bridge_ready", "health_ok", "backend_stopped")


def verified_artifacts(directory: Path) -> tuple[Path, Path]:
    """Verify exactly one installer/archive pair before executing any package."""
    entries = {}
    for line in (directory / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r"([a-fA-F0-9]{64})  (.+)", line)
        if not match or not ARTIFACT_NAME.fullmatch(match[2]) or match[2] in entries:
            raise ValueError("Invalid or duplicate release checksum entry.")
        path = directory / match[2]
        if not path.is_file() or path.is_symlink():
            raise ValueError("A release artifact is missing or is a symbolic link.")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != match[1].lower():
            raise ValueError("A release artifact failed its SHA256 checksum.")
        entries[match[2]] = path
    installers = [path for name, path in entries.items() if name.endswith("-setup.exe")]
    archives = [path for name, path in entries.items() if name.endswith("-portable.zip")]
    if len(entries) != 2 or len(installers) != 1 or len(archives) != 1:
        raise ValueError("Expected exactly one installer and one portable archive.")
    if installers[0].name.removesuffix("-setup.exe") != archives[0].name.removesuffix("-portable.zip"):
        raise ValueError("Installer and portable archive versions differ.")
    return installers[0], archives[0]


def verify_archive(path: Path) -> int:
    """Check public packages for an empty workspace config and private artifacts."""
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(set(names)) != len(names):
            raise ValueError("Portable archive contains duplicate paths.")
        for name in names:
            relative = PurePosixPath(name)
            if relative.is_absolute() or ".." in relative.parts or "\\" in name:
                raise ValueError("Portable archive contains an unsafe path.")
            if not relative.parts or relative.parts[0] != "Nomisma":
                raise ValueError("Portable archive must have a single Nomisma folder.")
            parts = {part.lower() for part in relative.parts}
            if parts.intersection({".git", ".env", "data", "backups", "__pycache__"}) or relative.suffix.lower() in {".sqlite", ".sqlite3", ".db", ".key", ".pem"}:
                raise ValueError("Portable archive contains private data or development files.")
        required = {"Nomisma/Nomisma.exe", "Nomisma/resources/python/python.exe",
                    "Nomisma/resources/backend/desktop/host.py", "Nomisma/resources/workspace.json"}
        if not required.issubset(names):
            raise ValueError("Portable archive is missing an application component.")
        if json.loads(archive.read("Nomisma/resources/workspace.json")) != {}:
            raise ValueError("The release must not contain a developer workspace path.")
        return len(names)


def clean_environment() -> dict[str, str]:
    return {key: value for key, value in os.environ.items()
            if not key.upper().startswith(("ALPACA_", "FMP_", "APCA_", "PYTHON", "DYLD_"))}


def run_process(command: list[str], timeout: float = 180) -> None:
    with subprocess.Popen(command, stdin=subprocess.DEVNULL, env=clean_environment()) as process:
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Terminate only the process we created and its children, never by name.
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=15, check=False)
            process.kill()
            process.wait(timeout=10)
            raise RuntimeError("A Windows verification process exceeded its time limit.") from None
        if code != 0:
            raise RuntimeError("A Windows verification process failed with exit code %s." % code)


def validate_smoke_result(result: dict, data_directory: Path) -> int:
    if any(result.get(field) is not True for field in SMOKE_FLAGS):
        raise ValueError("The native application did not pass every startup and shutdown check.")
    if result.get("platform") != "windows" or not result.get("webview_version"):
        raise ValueError("The result does not identify a running Windows WebView2 application.")
    if Path(result.get("data_directory", "")).resolve() != data_directory.resolve():
        raise ValueError("The native application used an unexpected research directory.")
    parsed = urlsplit(result.get("url", ""))
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.username or parsed.password or not parsed.port:
        raise ValueError("The native application reported an unexpected server address.")
    return parsed.port


def wait_until(predicate, message: str, timeout: float = 15) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.2)
    raise RuntimeError(message)


def port_closed(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return False
    except OSError:
        return True


def check(artifacts: Path, output: Path) -> dict:
    if sys.platform != "win32":
        raise RuntimeError("Run this verification on a clean Windows machine or GitHub's Windows runner.")
    local = Path(os.environ["LOCALAPPDATA"]).resolve()
    installation = local / "Programs/Nomisma"
    profile = local / "Nomisma"
    if installation.exists() or profile.exists():
        raise RuntimeError("This profile already contains Nomisma. Use a clean Windows test account; nothing was changed.")
    if output.exists():
        raise RuntimeError("The verification output directory already exists. Choose a new empty path.")
    installer, archive = verified_artifacts(artifacts)
    count = verify_archive(archive)
    output.mkdir(parents=True)
    report = {"success": False, "archive_files": count, "checksums_verified": True}
    marker = profile / "data/verification-research-marker.txt"
    marker_text = "Nomisma installer preservation check " + uuid.uuid4().hex
    app = installation / "Nomisma.exe"
    uninstaller = installation / "Uninstall.exe"
    try:
        run_process([str(installer), "/S"])
        if not app.is_file() or not uninstaller.is_file():
            raise RuntimeError("The installer did not create Nomisma.exe and Uninstall.exe.")
        report["installed"] = True
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(marker_text, encoding="utf-8")
        data_directory = output / "research data"
        for label in ("first-launch", "second-launch"):
            result_file = output / (label + ".json")
            run_process([str(app), "--smoke-test", "--data-dir", str(data_directory),
                         "--result-file", str(result_file)])
            result = json.loads(result_file.read_text(encoding="utf-8-sig"))
            port = validate_smoke_result(result, data_directory)
            wait_until(lambda: port_closed(port), "The application left its isolated server running.")
            report[label] = result
        # Reinstalling the same build exercises the existing-install upgrade path.
        run_process([str(installer), "/S"])
        if not app.is_file() or marker.read_text(encoding="utf-8") != marker_text:
            raise RuntimeError("Reinstalling did not preserve the application and research marker.")
        report["reinstall_preserved_data"] = True
        run_process([str(uninstaller), "/S"])
        # NSIS briefly copies the uninstaller to Temp, so its initial process can
        # exit before file removal completes. Poll the actual installation.
        wait_until(lambda: not installation.exists(), "Uninstallation did not remove the application folder.", timeout=30)
        if marker.read_text(encoding="utf-8") != marker_text:
            raise RuntimeError("Uninstallation changed the research marker.")
        report["uninstalled"] = True
        report["uninstall_preserved_data"] = True
        report["success"] = True
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        (output / "verification.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if report["success"]:
            # Only remove the exact test marker and then empty directories.
            # Never recursively delete an application or user profile here.
            marker.unlink()
            for folder in (marker.parent, profile):
                try:
                    folder.rmdir()
                except OSError:
                    pass
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, default=Path("dist/windows"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = check(args.artifacts.resolve(), args.output.resolve())
    except (OSError, RuntimeError, ValueError, KeyError, zipfile.BadZipFile) as error:
        print("Windows verification failed: %s" % error, file=sys.stderr)
        return 1
    print(json.dumps({"success": report["success"], "report": str(args.output / "verification.json")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
