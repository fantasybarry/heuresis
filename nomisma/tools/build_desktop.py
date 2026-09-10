#!/usr/bin/env python3
"""Build a self-contained, locally signed macOS Nomisma application.

Requires Apple's command-line developer tools only on the machine doing the
build. The finished application includes Python and needs no developer tools.
No package installation, data migration, or credential copying is performed.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import plistlib
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
CACHED_RUNTIME = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/python"
APP_ID = "com.heuresis.nomisma"
STATIC_SUFFIXES = {".html", ".css", ".js", ".svg", ".png", ".jpg", ".jpeg", ".ico", ".woff", ".woff2"}
STDLIB_EXCLUDES = {"site-packages", "__pycache__", "test", "tests", "idlelib", "tkinter", "turtledemo", "ensurepip"}


def run(*args: object, **kwargs: object) -> subprocess.CompletedProcess:
    return subprocess.run([str(arg) for arg in args], check=True, text=True, **kwargs)


def clean_python_environment() -> dict[str, str]:
    return {key: value for key, value in os.environ.items()
            if not key.startswith(("PYTHON", "DYLD_"))}


def copy_backend(project: Path, destination: Path) -> list[str]:
    """Copy an explicit source allowlist; user data and secrets never enter an app."""
    files = [project / "run.py", project / "launch.py", project / "desktop/host.py"]
    files.extend(path for path in (project / "nomisma").rglob("*.py")
                 if "__pycache__" not in path.parts)
    files.extend(path for path in (project / "nomisma/static").rglob("*")
                 if path.is_file() and path.suffix.lower() in STATIC_SUFFIXES
                 and not any(part.startswith(".") for part in path.relative_to(project).parts))
    copied = []
    for source in sorted(set(files)):
        if not source.is_file():
            raise RuntimeError(f"Required application source is missing: {source}")
        if source.is_symlink() or project.resolve() not in source.resolve().parents:
            raise RuntimeError(f"Refusing application source outside the project: {source}")
        relative = source.relative_to(project)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(relative.as_posix())
    return copied


def workspace_config(project: Path, portable: bool = False) -> dict[str, str]:
    if portable:
        return {}
    return {"data_directory": str((project / "data").resolve()),
            "env_file": str((project / ".env").resolve()),
            "project_directory": str(project.resolve())}


def copy_python(runtime: Path, destination: Path) -> dict:
    executable = runtime / "bin/python3"
    if not executable.is_file():
        raise RuntimeError("A standalone Python runtime is required. Use --python-runtime PATH "
                           "with a relocatable Python distribution containing bin/python3 and lib/python3.x.")
    probe = run(executable, "-I", "-c", "import json,sys,sysconfig,platform; "
                "print(json.dumps(dict(version=list(sys.version_info[:3]), "
                "stdlib=sysconfig.get_path('stdlib'), architecture=platform.machine())))",
                capture_output=True, env=clean_python_environment())
    metadata = json.loads(probe.stdout)
    version = metadata["version"]
    if tuple(version) < (3, 9):
        raise RuntimeError("Nomisma requires Python 3.9 or later.")
    if metadata["architecture"] != platform.machine():
        raise RuntimeError("The Python runtime architecture must match this Mac.")
    stdlib = Path(metadata["stdlib"]).resolve()
    if stdlib.parent != (runtime / "lib").resolve():
        raise RuntimeError("Python must have a standalone lib/python3.x layout; a system framework or venv is not relocatable.")
    (destination / "bin").mkdir(parents=True)
    shutil.copy2(executable.resolve(), destination / "bin/python3")

    def ignore(directory: str, names: list[str]) -> list[str]:
        return [name for name in names if name in STDLIB_EXCLUDES
                or name.endswith((".pyc", ".pyo", ".a"))
                or name.startswith(("_tkinter.", "config-"))]

    shutil.copytree(stdlib, destination / "lib" / stdlib.name, ignore=ignore)
    for library in (runtime / "lib").glob("*.dylib"):
        if not any(part in library.name.lower() for part in ("tcl", "tk9", "tk8")):
            shutil.copy2(library, destination / "lib" / library.name)
    metadata.pop("stdlib")
    (destination / "runtime.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata


def mach_o_files(directory: Path) -> list[Path]:
    magic_values = {b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"}
    found = []
    for path in directory.rglob("*"):
        if path.is_file() and not path.is_symlink():
            with path.open("rb") as handle:
                if handle.read(4) in magic_values:
                    found.append(path)
    return found


def validate_runtime(runtime: Path) -> None:
    """Reject external library dependencies and prove imports after relocation."""
    for binary in mach_o_files(runtime):
        linkage = run("/usr/bin/otool", "-L", binary, capture_output=True).stdout
        for line in linkage.splitlines()[1:]:
            library = line.strip().split(" (", 1)[0]
            # The first dylib entry may be its own install name.
            if library.startswith("/") and not library.startswith(("/usr/lib/", "/System/Library/")):
                raise RuntimeError(f"Runtime is not self-contained: {binary.name} links to {library}")
    with tempfile.TemporaryDirectory(prefix="nomisma-runtime-relocation-") as folder:
        relocated = Path(folder) / "Python Runtime"
        shutil.copytree(runtime, relocated)
        check = run(relocated / "bin/python3", "-I", "-B", "-c",
                    "import json,sys,ssl,sqlite3,zoneinfo,urllib.request,socket,hashlib,ctypes,multiprocessing; "
                    "from pathlib import Path; "
                    "assert Path(sys.prefix).resolve() == Path(sys.argv[1]).resolve(), sys.prefix; "
                    "assert all(not p or not Path(p).is_absolute() or "
                    "Path(sys.argv[1]).resolve() in Path(p).resolve().parents for p in sys.path), sys.path; "
                    "assert sqlite3.connect(':memory:').execute('select 1').fetchone() == (1,); "
                    "assert zoneinfo.ZoneInfo('America/New_York'); "
                    "assert ssl.create_default_context().get_ca_certs(); "
                    "print(json.dumps(dict(version=sys.version.split()[0],prefix=sys.prefix)))",
                    relocated, capture_output=True, env=clean_python_environment(), cwd=folder)
        print("Verified relocated Python:", check.stdout.strip())


ICON_SWIFT = r'''
import AppKit
import Foundation
let output = CommandLine.arguments[1]
for size in [16, 32, 64, 128, 256, 512, 1024] {
    let pixels = CGFloat(size)
    let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: size, pixelsHigh: size,
                                  bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true,
                                  isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: bitmap)
    let transform = NSAffineTransform()
    transform.scale(by: pixels / 1024)
    transform.concat()
    let rect = NSRect(x: 72, y: 72, width: 880, height: 880)
    let rounded = NSBezierPath(roundedRect: rect, xRadius: 192, yRadius: 192)
    let shadow = NSShadow()
    shadow.shadowColor = NSColor.black.withAlphaComponent(0.20)
    shadow.shadowBlurRadius = 30
    shadow.shadowOffset = NSSize(width: 0, height: -10)
    NSGraphicsContext.saveGraphicsState()
    shadow.set()
    NSColor(calibratedRed: 0.08, green: 0.19, blue: 0.15, alpha: 1).setFill()
    rounded.fill()
    NSGraphicsContext.restoreGraphicsState()
    NSGradient(starting: NSColor(calibratedRed: 0.22, green: 0.41, blue: 0.30, alpha: 1),
               ending: NSColor(calibratedRed: 0.08, green: 0.18, blue: 0.15, alpha: 1))!.draw(in: rounded, angle: -75)
    let rim = NSBezierPath(roundedRect: rect.insetBy(dx: 2, dy: 2), xRadius: 190, yRadius: 190)
    NSColor.white.withAlphaComponent(0.15).setStroke()
    rim.lineWidth = 3
    rim.stroke()
    // An N monogram drawn as clean vector geometry.
    let n = NSBezierPath()
    n.move(to: NSPoint(x: 282, y: 292))
    n.line(to: NSPoint(x: 282, y: 732))
    n.line(to: NSPoint(x: 387, y: 732))
    n.line(to: NSPoint(x: 637, y: 463))
    n.line(to: NSPoint(x: 637, y: 732))
    n.line(to: NSPoint(x: 742, y: 732))
    n.line(to: NSPoint(x: 742, y: 292))
    n.line(to: NSPoint(x: 637, y: 292))
    n.line(to: NSPoint(x: 387, y: 560))
    n.line(to: NSPoint(x: 387, y: 292))
    n.close()
    NSColor(calibratedRed: 0.95, green: 0.96, blue: 0.89, alpha: 1).setFill()
    n.fill()
    let accent = NSBezierPath(roundedRect: NSRect(x: 282, y: 222, width: 460, height: 14), xRadius: 7, yRadius: 7)
    NSColor(calibratedRed: 0.69, green: 0.78, blue: 0.48, alpha: 1).setFill()
    accent.fill()
    NSGraphicsContext.restoreGraphicsState()
    let data = bitmap.representation(using: .png, properties: [:])!
    try data.write(to: URL(fileURLWithPath: output).appendingPathComponent("\(size).png"))
}
'''


def build_icon(destination: Path, working: Path, compiler_flags: list[str] | None = None) -> None:
    source = working / "Icon.swift"
    source.write_text(ICON_SWIFT)
    generator = working / "make-icon"
    run("xcrun", "swiftc", *(compiler_flags or []), source, "-o", generator, "-framework", "AppKit")
    pngs = working / "pngs"
    pngs.mkdir()
    run(generator, pngs)
    iconset = working / "Nomisma.iconset"
    iconset.mkdir()
    for size in (16, 32, 128, 256, 512):
        shutil.copy2(pngs / f"{size}.png", iconset / f"icon_{size}x{size}.png")
        shutil.copy2(pngs / f"{size * 2}.png", iconset / f"icon_{size}x{size}@2x.png")
    run("/usr/bin/iconutil", "-c", "icns", "-o", destination, iconset)


def replace_bundle(staged: Path, destination: Path) -> None:
    """Replace only our own bundle, and restore the previous build on failure."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise RuntimeError(f"Refusing to replace a symbolic link: {destination}")
    if destination.exists():
        try:
            with (destination / "Contents/Info.plist").open("rb") as handle:
                identity = plistlib.load(handle).get("CFBundleIdentifier")
        except (OSError, ValueError, plistlib.InvalidFileException):
            identity = None
        if identity != APP_ID:
            raise RuntimeError(f"Refusing to replace a different application or directory: {destination}")
    backup = destination.with_name(f".{destination.name}.previous-{uuid.uuid4().hex}")
    had_previous = destination.exists()
    if had_previous:
        destination.rename(backup)
    try:
        staged.rename(destination)
    except BaseException:
        if had_previous:
            backup.rename(destination)
        raise
    if had_previous:
        shutil.rmtree(backup)


def install_bundle(source: Path, destination: Path | None = None) -> Path:
    destination = destination or Path.home() / "Applications/Nomisma.app"
    if source != destination:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".nomisma-install-", dir=destination.parent) as directory:
            staged = Path(directory) / "Nomisma.app"
            shutil.copytree(source, staged, symlinks=True)
            run("/usr/bin/codesign", "--verify", "--deep", "--strict", staged, capture_output=True)
            replace_bundle(staged, destination)
    run("/usr/bin/codesign", "--verify", "--deep", "--strict", destination, capture_output=True)
    return destination


def build(args: argparse.Namespace) -> Path:
    if sys.platform != "darwin":
        raise RuntimeError("This builder requires macOS.")
    if platform.machine() not in ("arm64", "x86_64"):
        raise RuntimeError(f"Unsupported Mac architecture: {platform.machine()}")
    output = args.output.expanduser().absolute()
    if output.suffix != ".app":
        raise RuntimeError("The output path must end in .app.")
    output.parent.mkdir(parents=True, exist_ok=True)
    overlay = args.sdk_overlay
    cached_overlay = PROJECT / "build/sdk-repair/overlay.json"
    if overlay is None and cached_overlay.is_file():
        sdk = Path(run("xcrun", "--show-sdk-path", capture_output=True).stdout.strip())
        required_headers = ["CoreData.framework/Headers/NSPersistentStoreCoordinator.h",
                            "CoreServices.framework/Frameworks/CarbonCore.framework/Headers/Folders.h"]
        if any(not (sdk / "System/Library/Frameworks" / header).is_file() for header in required_headers):
            overlay = cached_overlay
    compiler_flags = ["-vfsoverlay", str(overlay.expanduser().resolve())] if overlay else []
    if overlay:
        print(f"Using SDK header overlay: {overlay}", flush=True)
    with tempfile.TemporaryDirectory(prefix=".nomisma-build-", dir=output.parent) as directory:
        working = Path(directory)
        if overlay:
            # Keep repaired SDK modules separate from any stale system cache.
            compiler_flags.extend(["-module-cache-path", str(working / "swift-module-cache")])
        app = working / "Nomisma.app"
        contents = app / "Contents"
        resources = contents / "Resources"
        (contents / "MacOS").mkdir(parents=True)
        resources.mkdir()
        sources = copy_backend(PROJECT, resources / "backend")
        print("Copying standalone Python runtime…", flush=True)
        runtime = copy_python(args.python_runtime.expanduser().resolve(), resources / "python")
        validate_runtime(resources / "python")
        (resources / "workspace.json").write_text(json.dumps(workspace_config(PROJECT, args.portable), indent=2) + "\n")
        (resources / "build.json").write_text(json.dumps({"python": runtime, "backend_files": sources}, indent=2) + "\n")
        info = {"CFBundleIdentifier": APP_ID, "CFBundleName": "Nomisma", "CFBundleDisplayName": "Nomisma",
                "CFBundleExecutable": "Nomisma", "CFBundlePackageType": "APPL", "CFBundleInfoDictionaryVersion": "6.0",
                "CFBundleShortVersionString": "1.0.0", "CFBundleVersion": "1", "CFBundleIconFile": "Nomisma",
                "LSMinimumSystemVersion": "13.0", "LSApplicationCategoryType": "public.app-category.finance",
                "NSHighResolutionCapable": True, "NSPrincipalClass": "NSApplication",
                "NSSupportsAutomaticGraphicsSwitching": True,
                "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True}}
        with (contents / "Info.plist").open("wb") as handle:
            plistlib.dump(info, handle)
        print("Compiling the native Mac window and icon…", flush=True)
        run("xcrun", "swiftc", *compiler_flags, "-parse-as-library", "-O", "-target", f"{platform.machine()}-apple-macos13.0",
            PROJECT / "desktop/App.swift", "-o", contents / "MacOS/Nomisma",
            "-framework", "AppKit", "-framework", "WebKit", "-framework", "UserNotifications")
        build_icon(resources / "Nomisma.icns", working, compiler_flags)
        print("Signing and verifying the application…", flush=True)
        for binary in mach_o_files(resources / "python"):
            run("/usr/bin/codesign", "--force", "--sign", "-", binary, capture_output=True)
        run("/usr/bin/codesign", "--force", "--sign", "-", "--identifier", APP_ID, app, capture_output=True)
        run("/usr/bin/codesign", "--verify", "--deep", "--strict", app, capture_output=True)
        replace_bundle(app, output)
    if args.install:
        installed = install_bundle(output)
        print(f"Installed: {installed}")
    size = sum(path.stat().st_size for path in output.rglob("*") if path.is_file()) / 1024 / 1024
    print(f"Built: {output} ({size:.1f} MB, {platform.machine()}, Python {'.'.join(map(str, runtime['version']))})")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=PROJECT / "dist/Nomisma.app")
    parser.add_argument("--python-runtime", type=Path, default=Path(os.environ.get("NOMISMA_PYTHON_RUNTIME", CACHED_RUNTIME)),
                        help="Standalone Python prefix (default: Codex's cached runtime)")
    parser.add_argument("--install", action="store_true", help="Also install into ~/Applications/Nomisma.app")
    parser.add_argument("--portable", action="store_true", help="Use Application Support storage instead of linking this workspace")
    parser.add_argument("--sdk-overlay", type=Path, help="Optional Clang VFS overlay for an incomplete local SDK")
    args = parser.parse_args()
    try:
        build(args)
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(f"Build failed: {error}", file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
