#!/usr/bin/env python3
"""Launch Nomisma or run one saved screen, without installing dependencies."""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent


def load_environment(path):
    if not path.is_file():
        return
    for number, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError("Invalid .env entry at line %s. Use KEY=value." % number)
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if key not in {"ALPACA_API_KEY", "ALPACA_SECRET_KEY", "ALPACA_FEED", "ALPACA_PAPER", "FMP_API_KEY", "MASSIVE_API_KEY",
                       "NOMISMA_POOL", "NOMISMA_POOL_TOKEN"}:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


def main():
    parser = argparse.ArgumentParser(description="Nomisma — intraday penny-stock momentum and daily equity screening")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", type=Path, default=PROJECT / "data")
    parser.add_argument("--pool", action="store_true", help="Serve the shared Alpaca stream to workstations on --port")
    parser.add_argument("--scan", action="store_true", help="Run one screen with your saved settings and exit")
    parser.add_argument("--source", choices=["demo", "alpaca", "csv"], help="Override the source for a one-off --scan")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    if args.source and not args.scan:
        parser.error("--source requires --scan; use the app to save default settings")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    try:
        load_environment(PROJECT / ".env")
        if args.pool:
            from nomisma.pool import serve_pool
            serve_pool(args.port)
            return 0
        from nomisma.server import Application, serve
        app = Application(args.data_dir, seed=not args.scan)
        if args.scan:
            settings = app.settings()
            if args.source:
                settings["source"] = args.source
            result = app.run_scan(settings)
            print(json.dumps({key: result[key] for key in ("id", "source", "as_of", "universe_count", "matched_count")}, indent=2))
        else:
            serve(app, args.port)
    except (ValueError, RuntimeError, OSError) as exc:
        print("Nomisma: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
