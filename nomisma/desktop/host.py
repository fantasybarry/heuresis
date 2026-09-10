#!/usr/bin/env python3
"""Resolve a desktop workspace and start/reuse its loopback backend.

stdout is a single JSON readiness record for the native shell. macOS launches
a detached service. Windows uses --managed: this process serves the workspace
until its owning app closes stdin, then closes its monitor and HTTP server.
"""

import argparse
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
import errno
import json
import os
from pathlib import Path
import sys
import threading
import time

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import launch as launcher
from run import load_environment


def support_directory(home=None, platform=None, environ=None):
    base = Path(home or Path.home())
    if (platform or sys.platform) == "win32":
        environment = os.environ if environ is None else environ
        local = environment.get("LOCALAPPDATA") if home is None else None
        parent = Path(local) if local and Path(local).is_absolute() else base / "AppData" / "Local"
        return parent / "Nomisma"
    return base / "Library" / "Application Support" / "Nomisma"


def workspace_paths(config=None, data_directory=None, env_file=None, home=None, platform=None):
    config = {} if config is None else config
    if not isinstance(config, dict):
        raise ValueError("The desktop workspace configuration must be an object.")
    for key in ("project_directory", "data_directory", "env_file"):
        if key in config and (not isinstance(config[key], str) or not Path(config[key]).is_absolute()):
            raise ValueError("Desktop workspace paths must be absolute paths.")
    support = support_directory(home, platform)
    project = Path(config["project_directory"]) if config.get("project_directory") else None
    configured_data = Path(config["data_directory"]) if config.get("data_directory") else None
    # Existing research data remains usable even if its source checkout moved.
    existing_workspace = bool(configured_data and ((configured_data / "nomisma.sqlite3").is_file()
                                                   or (project and (project / "run.py").is_file())))
    if data_directory is not None:
        data = Path(data_directory).expanduser().resolve()
    else:
        data = (configured_data if existing_workspace else support / "data").resolve()
    if env_file is not None:
        environment = Path(env_file).expanduser().resolve()
    elif existing_workspace and config.get("env_file"):
        environment = Path(config["env_file"]).resolve()
    else:
        environment = support / ".env"
    return data, environment.resolve()


@contextmanager
def launch_lock(directory, timeout=10):
    """Serialize desktop launches for one database, including port selection."""
    descriptor = os.open(str(directory / ".desktop-launch.lock"), os.O_CREAT | os.O_RDWR, 0o600)
    deadline = time.monotonic() + timeout
    try:
        if os.name == "nt":
            import msvcrt
            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")
        else:
            import fcntl
        while True:
            try:
                if os.name == "nt":
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as error:
                if error.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise
                if time.monotonic() >= deadline:
                    raise RuntimeError("Another Nomisma window is starting this workspace. Wait a moment and retry.")
                time.sleep(.1)
        yield
    finally:
        os.close(descriptor)


def _matches(status, directory):
    return bool(status and status.get("data_directory")
                and Path(status["data_directory"]).resolve() == directory)


def choose_port(directory, preferred=None):
    registry = directory / ".desktop-server.json"
    candidates = []
    if preferred is not None:
        candidates.append(preferred)
    else:
        try:
            saved = json.loads(registry.read_text()).get("port")
            if type(saved) is int and 1 <= saved <= 65535:
                candidates.append(saved)
        except (OSError, ValueError, AttributeError):
            pass
        candidates.extend(range(8765, 8796))
    free, occupied = [], []
    for port in dict.fromkeys(candidates):
        if launcher.port_available(port):
            free.append(port)
        else:
            occupied.append(port)
    # Never connect to unused ports: on Windows, even a loopback refusal can
    # wait for the socket timeout. Check only occupied ports, concurrently, so
    # unrelated local services cannot add one timeout per candidate in series.
    if occupied:
        with ThreadPoolExecutor(max_workers=min(8, len(occupied))) as probes:
            statuses = probes.map(launcher.health, occupied)
            for port, status in zip(occupied, statuses):
                if _matches(status, directory):
                    return port, False
    if not free:
        raise RuntimeError("No local port is available for this workspace. Close another local server and retry.")
    return free[0], True


def start(config=None, data_directory=None, env_file=None, port=None, home=None):
    directory, environment = workspace_paths(config, data_directory, env_file, home)
    directory.mkdir(parents=True, exist_ok=True)
    with launch_lock(directory):
        selected, owned = choose_port(directory, port)
        if owned:
            load_environment(environment)
        url = launcher.launch(selected, directory, open_browser=False)
        write_registry(directory, selected)
    return {"url": url, "data_directory": str(directory), "env_file": str(environment),
            "owned_server": owned, "desktop_api": 1}


def write_registry(directory, port):
    # This registry contains only the selected loopback port, never keys.
    registry = directory / ".desktop-server.json"
    temporary = directory / ".desktop-server.json.tmp"
    descriptor = os.open(str(temporary), os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        json.dump({"port": port}, handle)
    temporary.replace(registry)


def run_managed(config=None, data_directory=None, env_file=None, port=None,
                input_stream=None, output_stream=None):
    """Own one local service; release database handles when the app exits.

    The HTTP service runs in this process, so even a forced process exit cannot
    orphan a child Python server and leave installed runtime files locked.
    Reusing a preexisting service never takes ownership of it.
    """
    from http.server import ThreadingHTTPServer
    from nomisma.server import Application, make_handler

    source = sys.stdin if input_stream is None else input_stream
    output = sys.stdout if output_stream is None else output_stream
    directory, environment = workspace_paths(config, data_directory, env_file)
    directory.mkdir(parents=True, exist_ok=True)
    app = server = worker = None
    try:
        with launch_lock(directory):
            selected, owned = choose_port(directory, port)
            if owned:
                load_environment(environment)
                app = Application(directory)
                server = ThreadingHTTPServer(("127.0.0.1", selected), make_handler(app))
                app.start_scheduler()
                worker = threading.Thread(target=server.serve_forever, daemon=True, name="nomisma-desktop-http")
                worker.start()
            write_registry(directory, selected)
            result = {"url": "http://127.0.0.1:%d/#live" % selected,
                      "data_directory": str(directory), "env_file": str(environment),
                      "owned_server": owned, "desktop_api": 1}
            print(json.dumps(result), file=output, flush=True)
        if owned:
            # EOF is sent by the native app on close/restart. Any byte also
            # requests shutdown; no command parser or remote shutdown exists.
            source.read(1)
        return result
    finally:
        if app is not None:
            app.stop_event.set()
            app.monitor.close()
        if server is not None:
            if worker is not None and worker.is_alive():
                server.shutdown()
                worker.join(timeout=5)
            server.server_close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--port", type=int)
    parser.add_argument("--managed", action="store_true", help="Keep the local service alive until the owning app closes stdin")
    args = parser.parse_args()
    if args.port is not None and not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    try:
        config = json.loads(args.config.read_text()) if args.config else {}
        if args.managed:
            run_managed(config, args.data_dir, args.env_file, args.port)
            return 0
        result = start(config, args.data_dir, args.env_file, args.port)
        print(json.dumps(result), flush=True)
        return 0
    except (OSError, RuntimeError, ValueError):
        # Never echo environment contents, authentication values, or arbitrary
        # configuration strings into a native error dialog.
        print("Nomisma could not start. Check that its data folder is writable, its .env uses KEY=value entries, and a local port is available. Startup details may be in the data folder's nomisma.log.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
