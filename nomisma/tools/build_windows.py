#!/usr/bin/env python3
"""Build Windows x64 installer and portable ZIP on Windows, macOS, or Linux.

Build dependencies: Python 3.9+, .NET 10 SDK, NSIS 3. The resulting application
contains its own .NET and Python runtimes. Downloads are pinned and verified;
neither credentials nor a local research database are included.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath


PROJECT = Path(__file__).resolve().parents[1]
APP_ID = "com.heuresis.nomisma.windows"
PYTHON_VERSION = "3.14.7"
PYTHON_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
PYTHON_SHA256 = "d297e5ff019966817ad8502465176139f2d3d840fa4ed84b13bed399a6ab1f15"
TZDATA_VERSION = "2026.3"
TZDATA_URL = "https://files.pythonhosted.org/packages/e5/6d/b53b99a9f2766d095985947a5782f1702cabb129a34f7a802d7197af832f/tzdata-2026.3-py2.py3-none-any.whl"
TZDATA_SHA256 = "dc096730c87af6cab1b171c9d532be840741ff5d459015e7f6947bd7d7e54931"
STATIC_SUFFIXES = {".html", ".css", ".js", ".svg", ".png", ".jpg", ".jpeg", ".ico", ".woff", ".woff2"}


def run(*args: object, **kwargs: object) -> subprocess.CompletedProcess:
    return subprocess.run([str(value) for value in args], check=True, **kwargs)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_version(value: str) -> str:
    if not re.fullmatch(r"(?:0|[1-9][0-9]{0,3})\.(?:0|[1-9][0-9]{0,3})\.(?:0|[1-9][0-9]{0,3})", value):
        raise argparse.ArgumentTypeError("Version must be MAJOR.MINOR.PATCH, each between 0 and 9999.")
    return value


def safe_relative(value: str) -> PurePosixPath:
    """Reject traversal, alternate streams, symlinks, and NSIS metacharacters."""
    if not value or any(char in value for char in ('\\', ':', '\x00', '$', '"', '\n', '\r')):
        raise RuntimeError(f"Unsafe package path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in value.split("/")):
        raise RuntimeError(f"Unsafe package path: {value!r}")
    return path


def download_verified(url: str, expected: str, cache: Path) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    filename = Path(urllib.parse.urlparse(url).path).name
    target = cache / filename
    if target.exists():
        if target.is_symlink() or sha256(target) != expected:
            raise RuntimeError(f"Cached dependency checksum failed: {filename}. Remove it and rebuild.")
        return target
    if urllib.parse.urlparse(url).scheme != "https":
        raise RuntimeError("Runtime dependencies must use HTTPS.")
    print(f"Downloading pinned dependency: {filename}", flush=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".download-", dir=cache)
    try:
        with os.fdopen(descriptor, "wb") as output, urllib.request.urlopen(url, timeout=60) as response:
            parsed = urllib.parse.urlparse(response.url)
            if parsed.scheme != "https" or parsed.hostname not in {"www.python.org", "python.org", "files.pythonhosted.org"}:
                raise RuntimeError("Dependency download redirected outside the official distribution hosts.")
            total = 0
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                total += len(block)
                if total > 64 * 1024 * 1024:
                    raise RuntimeError("Dependency download exceeded the expected size limit.")
                output.write(block)
        if sha256(Path(temporary)) != expected:
            raise RuntimeError(f"Downloaded dependency checksum failed: {filename}")
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return target


def extract_verified_archive(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as zipped:
        total = 0
        seen = set()
        for entry in zipped.infolist():
            value = entry.filename.rstrip("/")
            relative = safe_relative(value)
            key = value.casefold()
            if key in seen or stat.S_ISLNK(entry.external_attr >> 16):
                raise RuntimeError(f"Unsafe or duplicate archive member: {value}")
            seen.add(key)
            total += entry.file_size
            if total > 128 * 1024 * 1024:
                raise RuntimeError("Dependency archive exceeded the extraction size limit.")
            target = destination.joinpath(*relative.parts)
            if target.is_symlink() or (target.exists() and not (entry.is_dir() and target.is_dir())):
                raise RuntimeError(f"Refusing to overwrite extracted dependency: {value}")
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with zipped.open(entry) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)


def copy_backend(project: Path, destination: Path) -> list[str]:
    files = [project / "run.py", project / "launch.py", project / "desktop/host.py"]
    files.extend(path for path in (project / "nomisma").rglob("*.py")
                 if not any(part.startswith(".") or part == "__pycache__"
                            for part in path.relative_to(project).parts))
    files.extend(path for path in (project / "nomisma/static").rglob("*")
                 if path.is_file() and path.suffix.lower() in STATIC_SUFFIXES
                 and not any(part.startswith(".") for part in path.relative_to(project).parts))
    copied = []
    for source in sorted(set(files)):
        if not source.is_file():
            raise RuntimeError(f"Required source is missing: {source}")
        if source.is_symlink() or project.resolve() not in source.resolve().parents:
            raise RuntimeError(f"Refusing source outside the project: {source}")
        relative = source.relative_to(project).as_posix()
        safe_relative(relative)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        copied.append(relative)
    return copied


def prepare_python(destination: Path, cache: Path) -> None:
    extract_verified_archive(download_verified(PYTHON_URL, PYTHON_SHA256, cache), destination)
    packages = destination / "Lib/site-packages"
    extract_verified_archive(download_verified(TZDATA_URL, TZDATA_SHA256, cache), packages)
    # The embeddable distribution intentionally isolates Python from global
    # installs, PATH, PYTHONPATH, and user site packages. Keep that isolation.
    (destination / "python314._pth").write_text(
        "python314.zip\n.\n../backend\nLib/site-packages\n", encoding="utf-8")
    require_pe(destination / "python.exe", machine=0x8664)
    if not (packages / "tzdata/zoneinfo/America/New_York").is_file():
        raise RuntimeError("The bundled Windows timezone database is incomplete.")


def require_pe(path: Path, machine: int | None = None) -> int:
    with path.open("rb") as source:
        if source.read(2) != b"MZ":
            raise RuntimeError(f"Expected Windows executable: {path.name}")
        source.seek(0x3C)
        offset = source.read(4)
        if len(offset) != 4:
            raise RuntimeError(f"Invalid Windows executable: {path.name}")
        source.seek(struct.unpack("<I", offset)[0])
        if source.read(4) != b"PE\0\0":
            raise RuntimeError(f"Invalid Windows executable: {path.name}")
        machine_bytes = source.read(2)
        if len(machine_bytes) != 2:
            raise RuntimeError(f"Invalid Windows executable: {path.name}")
        architecture = struct.unpack("<H", machine_bytes)[0]
    if machine is not None and architecture != machine:
        raise RuntimeError(f"Wrong Windows architecture: {path.name}")
    return architecture


def validate_payload_binaries(application: Path) -> None:
    """Native code must be x64; architecture-neutral CLR assemblies are allowed."""
    for path in application.rglob("*"):
        if path.suffix.lower() not in {".exe", ".dll", ".pyd"}:
            continue
        machine = require_pe(path)
        if machine == 0x8664:
            continue
        if machine == 0x14C:
            with path.open("rb") as source:
                source.seek(0x3C)
                offset = struct.unpack("<I", source.read(4))[0]
                source.seek(offset + 24)
                optional_header = struct.unpack("<H", source.read(2))[0]
                if optional_header == 0x10B:
                    source.seek(offset + 24 + 96 + 14 * 8)
                    clr_header = source.read(8)
                    if len(clr_header) == 8 and struct.unpack("<II", clr_header)[0]:
                        continue
        raise RuntimeError(f"Unexpected native architecture in package: {path.relative_to(application)}")


def preserve_licenses(project: Path, application: Path) -> None:
    assets = json.loads((project / "desktop/windows/obj/project.assets.json").read_text(encoding="utf-8"))
    folders = [Path(folder) for folder in assets["packageFolders"]]
    versions = {name.split("/")[0].lower(): name.split("/")[1] for name in assets["libraries"]}
    for framework in assets["project"]["frameworks"].values():
        for package in framework.get("downloadDependencies", []):
            versions[package["name"].lower()] = package["version"].strip("[]").split(",")[0].strip()
    required = {"microsoft.web.webview2", "microsoft.netcore.app.host.win-x64",
                "microsoft.netcore.app.runtime.win-x64", "microsoft.windowsdesktop.app.runtime.win-x64"}
    for name in sorted(required):
        version = versions.get(name)
        if not version:
            raise RuntimeError(f"Could not identify the bundled dependency license: {name}")
        package = next((folder / name / version for folder in folders if (folder / name / version).is_dir()), None)
        if package is None:
            raise RuntimeError(f"Could not find the restored dependency license: {name}")
        notices = [path for path in package.iterdir() if path.is_file()
                   and (path.name.lower().startswith("license") or "notice" in path.name.lower())]
        if not any(path.name.lower().startswith("license") for path in notices):
            raise RuntimeError(f"Dependency redistribution license is missing: {name}")
        destination = application / "licenses" / f"{name}-{version}"
        destination.mkdir(parents=True)
        for notice in notices:
            shutil.copyfile(notice, destination / notice.name)
    (application / "licenses/README.txt").write_text(
        "Nomisma includes Microsoft .NET, Windows Desktop and WebView2 components.\n"
        "Their redistribution licenses and notices are preserved in this folder.\n"
        "Python's license is resources/python/LICENSE.txt.\n"
        f"tzdata licenses are resources/python/Lib/site-packages/tzdata-{TZDATA_VERSION}.dist-info/licenses/.\n"
        "WebView2 Evergreen Runtime is a separate Microsoft component installed on the PC.\n", encoding="utf-8")


def write_manifest(application: Path, version: str) -> list[str]:
    files = []
    for path in sorted(application.rglob("*")):
        if path.is_symlink():
            raise RuntimeError("The Windows package must not contain symlinks.")
        if not path.is_file():
            continue
        relative = path.relative_to(application).as_posix()
        safe_relative(relative)
        if path.name == ".env" or path.suffix in {".sqlite", ".sqlite3", ".db", ".pdb"}:
            raise RuntimeError(f"Private data or debug symbols in package: {relative}")
        files.append({"path": relative, "sha256": sha256(path), "size": path.stat().st_size})
    manifest = {"application_id": APP_ID, "version": version, "architecture": "win-x64",
                "python_version": PYTHON_VERSION, "tzdata_version": TZDATA_VERSION, "files": files}
    (application / "bundle-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (application / ".nomisma-install-id").write_text(APP_ID, encoding="ascii")
    return [entry["path"] for entry in files] + ["bundle-manifest.json", ".nomisma-install-id"]


def write_uninstall_list(files: list[str], target: Path) -> None:
    """Use only literal packaged paths; never recursively delete an install dir."""
    directories = set()
    lines = []
    for name in sorted(files):
        if name == ".nomisma-install-id":
            continue  # Keep identity until the uninstall section finishes.
        path = safe_relative(name)
        lines.append('Delete "$INSTDIR\\' + str(path).replace("/", "\\") + '"')
        directories.update(parent for parent in path.parents if str(parent) != ".")
    for directory in sorted(directories, key=lambda value: (-len(value.parts), str(value))):
        lines.append('RMDir "$INSTDIR\\' + str(directory).replace("/", "\\") + '"')
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def tool_path(value: str | None, name: str) -> str:
    if value:
        resolved = Path(value).expanduser().resolve()
        if not resolved.is_file():
            raise RuntimeError(f"Build tool does not exist: {resolved}")
        return str(resolved)
    found = shutil.which(name)
    if not found and name == "makensis" and os.name == "nt":
        for variable in ("ProgramFiles(x86)", "ProgramFiles"):
            candidate = Path(os.environ.get(variable, "C:/Program Files (x86)")) / "NSIS/makensis.exe"
            if candidate.is_file():
                return str(candidate)
    if not found:
        raise RuntimeError(f"Install {'.NET 10 SDK' if name == 'dotnet' else 'NSIS 3'} on the build machine, or provide --{name} PATH.")
    return found


def build(args: argparse.Namespace) -> list[Path]:
    dotnet = tool_path(args.dotnet, "dotnet")
    makensis = tool_path(args.makensis, "makensis")
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    cache = PROJECT / "build/windows-cache"
    stem = f"Nomisma-{args.version}-win-x64"
    with tempfile.TemporaryDirectory(prefix=".nomisma-windows-", dir=output) as directory:
        work = Path(directory)
        application = work / "Nomisma"
        env = {key: value for key, value in os.environ.items() if not key.startswith(("PYTHON", "DYLD_"))}
        env["DOTNET_CLI_TELEMETRY_OPTOUT"] = "1"
        env["DOTNET_NOLOGO"] = "1"
        run(dotnet, "publish", PROJECT / "desktop/windows/Nomisma.Windows.csproj",
            "-c", "Release", "-r", "win-x64", "--self-contained", "true",
            "-p:EnableWindowsTargeting=true", "-p:RestoreLockedMode=true", "-p:PublishReadyToRun=false",
            "-p:DebugType=None", "-p:DebugSymbols=false", f"-p:Version={args.version}",
            "-o", application, env=env)
        resources = application / "resources"
        copy_backend(PROJECT, resources / "backend")
        resources.mkdir(parents=True, exist_ok=True)
        (resources / "workspace.json").write_text("{}\n", encoding="utf-8")
        prepare_python(resources / "python", cache)
        for binary in ("Nomisma.exe", "coreclr.dll", "hostfxr.dll"):
            require_pe(application / binary, machine=0x8664)
        if not list(application.rglob("WebView2Loader.dll")):
            raise RuntimeError("WebView2 native loader is missing from the application.")
        validate_payload_binaries(application)
        preserve_licenses(PROJECT, application)
        files = write_manifest(application, args.version)
        uninstall_list = work / "uninstall-files.nsh"
        write_uninstall_list(files, uninstall_list)
        setup = work / f"{stem}-setup.exe"
        defines = {"APP_VERSION": args.version, "APP_FILES": str(application),
                   "OUTPUT_FILE": str(setup), "UNINSTALL_FILES": str(uninstall_list),
                   "APP_ICON": str(PROJECT / "desktop/windows/Nomisma.ico")}
        prefix = "/D" if os.name == "nt" else "-D"
        run(makensis, *(f"{prefix}{key}={value}" for key, value in defines.items()),
            PROJECT / "desktop/windows/installer.nsi")
        require_pe(setup, machine=0x14C)  # NSIS bootstrapper is 32-bit; payload is x64.
        archive = work / f"{stem}-portable.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zipped:
            for name in sorted(files):
                zipped.write(application / name, f"Nomisma/{name}")
        artifacts = []
        for path in (setup, archive):
            destination = output / path.name
            if destination.is_symlink():
                raise RuntimeError(f"Refusing to overwrite symbolic link: {destination}")
            os.replace(path, destination)
            artifacts.append(destination)
        checksums = output / "SHA256SUMS.txt"
        if checksums.is_symlink():
            raise RuntimeError(f"Refusing to overwrite symbolic link: {checksums}")
        checksums.write_text("".join(f"{sha256(path)}  {path.name}\n" for path in artifacts), encoding="ascii")
        artifacts.append(checksums)
    for artifact in artifacts:
        print(f"Built {artifact} ({artifact.stat().st_size:,} bytes)", flush=True)
    return artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=PROJECT / "dist/windows")
    parser.add_argument("--version", type=validate_version, default="1.0.0")
    parser.add_argument("--dotnet", help="Path to the .NET 10 SDK dotnet executable")
    parser.add_argument("--makensis", help="Path to the NSIS makensis executable")
    args = parser.parse_args()
    try:
        build(args)
    except (OSError, RuntimeError, subprocess.CalledProcessError, zipfile.BadZipFile) as error:
        print(f"Windows build failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
