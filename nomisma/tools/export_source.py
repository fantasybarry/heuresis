#!/usr/bin/env python3
"""Export current Nomisma source for a fresh GitHub repository, without history.

The archive preserves this repository's nomisma/ project layout and includes
the Windows workflow at .github/workflows/. It excludes credentials, research
data, built applications, developer caches and the .git directory.
"""

import argparse
import hashlib
from pathlib import Path, PurePosixPath
import subprocess
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
DENIED_PARTS = {".git", "data", "backups", "dist", "build", "artifacts", "__pycache__", "bin", "obj",
                "node_modules", ".venv", ".vs", ".idea"}
SOURCE_SUFFIXES = {".py", ".cs", ".csproj", ".swift", ".nsi", ".nsh", ".ico", ".png", ".svg",
                   ".html", ".css", ".js", ".cjs", ".json", ".md", ".txt", ".toml", ".yml", ".yaml",
                   ".ps1", ".command", ".xml", ".manifest", ".resx", ".props", ".targets"}


def allowed_source(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        return False
    if name in {".gitignore", "README.md", ".github/workflows/nomisma-windows.yml"}:
        return True
    if path.parts[0] != "nomisma" or any(part in DENIED_PARTS for part in path.parts):
        return False
    if path.name.startswith(".env"):
        return path.name == ".env.example"
    if any(part.startswith(".") for part in path.parts[1:]) and path.name != ".gitignore":
        return False
    return (path.name == ".gitignore" or path.suffix.lower() in SOURCE_SUFFIXES
            or path.suffix.lower() == ".csv" and path.parts[:2] == ("nomisma", "examples"))


def export_source(repository, destination):
    repository = Path(repository).resolve()
    destination = Path(destination).resolve()
    paths = subprocess.run(["git", "-C", str(repository), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                           text=True, capture_output=True, check=True).stdout.split("\0")
    selected = sorted({name for name in paths if allowed_source(name) and (repository / name).is_file()})
    required = {"nomisma/run.py", "nomisma/desktop/host.py", "nomisma/desktop/windows/Nomisma.Windows.csproj",
                "nomisma/tools/build_windows.py", ".github/workflows/nomisma-windows.yml"}
    if not required.issubset(selected):
        raise RuntimeError("Required Windows source or workflow files are missing from the export.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in selected:
            source = repository / name
            if source.is_symlink() or repository not in source.resolve().parents:
                raise RuntimeError("Source exports cannot contain symlinks or files outside the repository.")
            archive.write(source, name)
    checksum = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(destination.suffix + ".sha256").write_text(checksum + "  " + destination.name + "\n")
    return len(selected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=PROJECT / "dist/Nomisma-source.zip")
    args = parser.parse_args()
    repository = Path(subprocess.run(["git", "-C", str(PROJECT), "rev-parse", "--show-toplevel"],
                                     text=True, capture_output=True, check=True).stdout.strip())
    count = export_source(repository, args.output)
    print("Exported %d source files to %s" % (count, args.output.resolve()))


if __name__ == "__main__":
    main()
