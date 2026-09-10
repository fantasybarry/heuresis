#!/usr/bin/env python3
"""Start or reuse this local workspace, then open its ready browser interface."""

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

PROJECT = Path(__file__).resolve().parent


def health(port):
    try:
        with urlopen("http://127.0.0.1:%d/api/health" % port, timeout=1) as response:
            result = json.load(response)
        return result if isinstance(result, dict) and result.get("app") == "nomisma" and result.get("status") == "ok" else None
    except (OSError, URLError, ValueError):
        return None


def port_open(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=.5):
            return True
    except OSError:
        return False


def check_workspace(status, directory):
    if Path(status.get("data_directory", "")).resolve() != directory:
        raise RuntimeError("This port is serving a different Nomisma workspace. Use --port with a free port.")


def launch(port, directory, open_browser=True):
    directory = Path(directory).expanduser().resolve()
    status = health(port)
    if status:
        check_workspace(status, directory)
    else:
        if port_open(port):
            raise RuntimeError("Port %d is occupied. If this is an older Nomisma server, stop it first; otherwise choose --port 8766." % port)
        directory.mkdir(parents=True, exist_ok=True)
        log_path = directory / "nomisma.log"
        if log_path.exists() and log_path.stat().st_size > 2 * 1024 * 1024:
            log_path.replace(directory / "nomisma.previous.log")
        with log_path.open("ab") as output:
            log_path.chmod(0o600)
            process_options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
            process = subprocess.Popen([sys.executable, "-B", str(PROJECT / "run.py"), "--port", str(port),
                                        "--data-dir", str(directory)], cwd=PROJECT,
                                       stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                                       **process_options)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            status = health(port)
            if status:
                check_workspace(status, directory)
                break
            if process.poll() is not None:
                raise RuntimeError("Nomisma could not start. See %s for details." % log_path)
            time.sleep(.2)
        else:
            process.terminate()
            raise RuntimeError("Nomisma did not become ready within 30 seconds. See %s." % log_path)
    url = "http://127.0.0.1:%d/#live" % port
    if open_browser:
        webbrowser.open(url)
    return url


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", type=Path, default=PROJECT / "data")
    parser.add_argument("--no-browser", action="store_true", help="Start/reuse Nomisma without opening a browser")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    try:
        print("Nomisma is ready at " + launch(args.port, args.data_dir, not args.no_browser))
        print("The local server stays running after this launcher closes. Start market monitoring in the app.")
        return 0
    except (OSError, RuntimeError) as exc:
        print("Nomisma: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
