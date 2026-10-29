#!/usr/bin/env python3
"""Run one immutable offline all-in settled-cash exit-policy comparison."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import resource
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nomisma import all_in_replay, calibration
from nomisma.replay_data import file_sha256 as sha, write_new


def execute(catalog, config_path, calendar, exit_rule, output):
    output = Path(output)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("All-in replay output must be new or empty.")
    if exit_rule not in all_in_replay.EXIT_RULES:
        raise ValueError("Unknown registered all-in exit rule.")
    identity = all_in_replay.source_hashes()
    inputs = {str(Path(path)): sha(path) for path in (catalog, config_path, calendar, __file__)}
    config = json.loads(Path(config_path).read_text())
    started_at, started = datetime.now(timezone.utc).isoformat(), time.monotonic()
    result = all_in_replay.run_catalog_all_in(Path(catalog), config, Path(calendar), exit_rule)
    if identity != all_in_replay.source_hashes() or any(sha(path) != digest for path, digest in inputs.items()):
        raise ValueError("Source or registered input changed during execution.")
    metrics = calibration.session_metrics(result)
    output.mkdir(parents=True, exist_ok=True)
    write_new(output / "config.json", config)
    write_new(output / "result.json", result)
    write_new(output / "metrics.json", metrics)
    execution = {"started_at": started_at, "finished_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": time.monotonic() - started, "exit_rule": exit_rule,
        "research_only": True, "trading_execution_authorized": False,
        "effective_policy": all_in_replay.effective_policy(),
        "source_sha256": identity, "input_sha256": inputs,
        "result_sha256": sha(output / "result.json"), "metrics_sha256": sha(output / "metrics.json"),
        "max_rss_native": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "max_rss_unit": "bytes on macOS; KiB on Linux", "python_version": sys.version}
    write_new(output / "execution.json", execution)
    return {"summary": result["summary"], "exit_rule": exit_rule,
            "output": str(output), "elapsed_seconds": execution["elapsed_seconds"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--calendar", required=True)
    parser.add_argument("--exit-rule", choices=all_in_replay.EXIT_RULES, required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(execute(args.catalog, args.config, args.calendar, args.exit_rule, args.output)))


if __name__ == "__main__":
    main()
