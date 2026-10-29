#!/usr/bin/env python3
"""Archive and replay a declared historical research cohort; never places orders."""

import argparse
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from nomisma.replay_data import canonical, digest, file_sha256, write_json  # noqa: E402


def source_hashes():
    paths = [
        "nomisma/replay.py", "nomisma/replay_data.py", "nomisma/trade_plan.py",
        "nomisma/monitor_metrics.py", "nomisma/engine.py", "nomisma/screening_metrics.py",
        "nomisma/planning_data.py", "nomisma/live_data.py", "nomisma/providers.py",
        "tools/replay_pilot.py",
    ]
    return {name: file_sha256(PROJECT / name) for name in paths}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    config_parser = commands.add_parser("config", help="Write explicit engineering fixture assumptions")
    config_parser.add_argument("--output", required=True, type=Path)
    download = commands.add_parser("download", help="Archive read-only Alpaca historical data")
    download.add_argument("--output", required=True, type=Path)
    download.add_argument("--symbols", required=True, help="Comma-separated fixed development cohort")
    download.add_argument("--dates", required=True, help="Comma-separated completed session dates")
    download.add_argument("--max-requests", type=int, default=250)
    download.add_argument("--resume-from", type=Path, help="Reuse verified pages from a matching archive into a new directory")
    replay = commands.add_parser("run", help="Run entirely offline from a verified archive")
    replay.add_argument("--dataset", required=True, type=Path)
    replay.add_argument("--config", required=True, type=Path)
    replay.add_argument("--output", required=True, type=Path)
    replay.add_argument("--verify-repeat", action="store_true", help="Replay twice and require identical results")
    args = parser.parse_args(argv)

    if args.command == "config":
        from nomisma.replay import default_replay_config
        if args.output.exists():
            raise ValueError("Configuration already exists; use a new path to preserve the frozen experiment.")
        write_json(args.output, default_replay_config())
        print(json.dumps({"configuration": str(args.output), "purpose": "engineering_fixture"}))
        return 0

    if args.command == "download":
        from run import load_environment
        from nomisma.replay_data import download_dataset
        load_environment(PROJECT / ".env")
        path = download_dataset(
            args.output, [s.strip().upper() for s in args.symbols.split(",") if s.strip()],
            [s.strip() for s in args.dates.split(",") if s.strip()],
            max_requests=args.max_requests,
            resume_from=args.resume_from,
        )
        print(json.dumps({"dataset": str(path)}))
        return 0

    from nomisma.replay_data import load_dataset
    from nomisma.replay import run_replay
    sources_before = source_hashes()
    dataset = load_dataset(args.dataset)
    config = json.loads(args.config.read_text())
    dataset_digest = file_sha256(args.dataset)
    result = run_replay(dataset, config)
    result_digest = digest(result)
    if args.verify_repeat:
        repeated = run_replay(dataset, config)
        if digest(repeated) != result_digest:
            raise RuntimeError("Identical frozen inputs produced different replay results.")
    if source_hashes() != sources_before:
        raise RuntimeError("Replay source changed during execution; run again against a stable version.")
    if file_sha256(args.dataset) != dataset_digest:
        raise RuntimeError("Dataset changed during execution; restore the verified archive before running.")

    args.output.mkdir(parents=True, exist_ok=True)
    write_json(args.output / "result.json", result)
    write_json(args.output / "summary.json", result["summary"])
    write_json(args.output / "config.json", config)
    for key in ("decisions", "orders", "trades", "fills", "ledger", "unresolved"):
        if isinstance(result.get(key), list):
            with (args.output / (key + ".jsonl")).open("w") as handle:
                for row in result[key]:
                    handle.write(canonical(row).decode() + "\n")
    evidence = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "source_sha256": sources_before,
        "config_sha256": digest(config),
        "dataset_file_sha256": dataset_digest,
        "result_sha256": result_digest,
        "repeat_identical": True if args.verify_repeat else None,
        "research_only": True,
        "calibrated": False,
    }
    write_json(args.output / "run_manifest.json", evidence)
    print(json.dumps({"summary": result["summary"], "result_sha256": result_digest,
                      "repeat_identical": evidence["repeat_identical"],
                      "output": str(args.output)}, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError) as error:
        print("Replay pilot: " + str(error), file=sys.stderr)
        raise SystemExit(1)
