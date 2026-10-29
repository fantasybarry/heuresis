#!/usr/bin/env python3
"""Run one versioned cash-account experiment against a local development catalog."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import resource
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nomisma import calibration, cash_replay
from nomisma.replay_data import file_sha256 as sha, write_new


def execute(catalog, config_path, calendar, variant, output):
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Cash replay output must be new or empty.")
    identity = cash_replay.source_hashes()
    inputs = {str(Path(p)): sha(p) for p in (catalog, config_path, calendar, __file__)}
    config = json.loads(Path(config_path).read_text())
    started_at = datetime.now(timezone.utc).isoformat()
    start = time.monotonic()
    result = cash_replay.run_catalog_cash(Path(catalog), config, Path(calendar), variant)
    if identity != cash_replay.source_hashes() or any(sha(p) != digest for p, digest in inputs.items()):
        raise ValueError("Source or registered input changed during execution.")
    metrics = calibration.session_metrics(result)
    output.mkdir(parents=True, exist_ok=True)
    write_new(output / "config.json", config)
    write_new(output / "result.json", result)
    write_new(output / "metrics.json", metrics)
    execution = {"started_at": started_at, "finished_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": time.monotonic() - start, "variant": variant,
        "research_only": True, "trading_execution_authorized": False,
        "source_sha256": identity, "input_sha256": inputs,
        "result_sha256": sha(output / "result.json"), "metrics_sha256": sha(output / "metrics.json"),
        "max_rss_native": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "max_rss_unit": "bytes on macOS; KiB on Linux", "python_version": sys.version}
    write_new(output / "execution.json", execution)
    return {"summary": result["summary"], "variant": variant,
            "output": str(output), "elapsed_seconds": execution["elapsed_seconds"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--calendar", required=True)
    parser.add_argument("--variant", choices=cash_replay.VARIANTS, required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(execute(args.catalog, args.config, args.calendar, args.variant, args.output)))


if __name__ == "__main__":
    main()
