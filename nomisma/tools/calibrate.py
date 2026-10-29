#!/usr/bin/env python3
"""Run the registered historical calibration development experiment offline."""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys
import time

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from nomisma.replay_data import digest, file_sha256 as file_hash, write_json  # noqa: E402


def event(name, **fields):
    print(json.dumps({"event": name, "at": datetime.now(timezone.utc).isoformat(), **fields}, allow_nan=False), flush=True)


def source_hashes():
    paths = sorted((PROJECT / "nomisma").glob("*.py")) + [Path(__file__).resolve()]
    return {str(path.relative_to(PROJECT)): file_hash(path) for path in paths}


def registration(path):
    value = json.loads(Path(path).read_text())
    expected_grid = {"stop_atr_multiple": [1, 1.5, 2], "reward_multiple": [2, 2.5, 3], "hold_minutes": [5, 15, 30]}
    if value.get("schema_version") != 1 or value.get("grid") != expected_grid:
        raise ValueError("Unsupported experiment registration or parameter family.")
    if value.get("selection_allowed") is not False or value.get("holdout_dates") != [] or value.get("partition") != "development_only":
        raise ValueError("This runner supports registered development experiments only.")
    dates = value.get("development_dates", [])
    if not dates or dates != sorted(set(dates)):
        raise ValueError("Development dates must be nonempty, unique and chronological.")
    if file_hash(PROJECT / "CALIBRATION_SPEC.md") != value.get("spec_sha256"):
        raise ValueError("Registered specification changed.")
    if file_hash(PROJECT / "nomisma/replay.py") != value.get("frozen_engine_sha256"):
        raise ValueError("Frozen replay engine changed.")
    config_path = PROJECT / value["base_config_path"]
    config = json.loads(config_path.read_text())
    if file_hash(config_path) != value["base_config_file_sha256"] or digest(config) != value["base_config_sha256"]:
        raise ValueError("Frozen base configuration changed.")
    if config["monitor"]["symbols"] != value["symbols"]:
        raise ValueError("Configuration cohort differs from registration.")
    return value, config


def checkpoint(output, key, config, identity, execute):
    """Resume only a complete, hash-verified result from the exact frozen inputs."""
    from nomisma.calibration import session_metrics
    directory = output / key
    manifest_path = directory / "manifest.json"
    result_path, metrics_path = directory / "result.json", directory / "metrics.json"
    config_path = directory / "config.json"
    expected = {"experiment": identity, "policy_id": key, "config_sha256": digest(config)}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("identity") != expected:
            raise ValueError("Checkpoint inputs/source differ: " + key)
        if file_hash(result_path) != manifest.get("result_sha256") or file_hash(metrics_path) != manifest.get("metrics_sha256"):
            raise ValueError("Checkpoint artifacts changed: " + key)
        if (file_hash(config_path) != manifest.get("config_file_sha256") or
                digest(json.loads(config_path.read_text())) != expected["config_sha256"]):
            raise ValueError("Checkpoint configuration changed: " + key)
        event("candidate_reused", policy_id=key)
        return {"id": key, "config": config, "metrics": json.loads(metrics_path.read_text()),
                "run_fingerprint": manifest["result_run_fingerprint"]}
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("Incomplete candidate output preserved; use a new output directory: " + str(directory))
    event("candidate_started", policy_id=key)
    start = time.monotonic()
    result = execute(config)
    metrics = session_metrics(result)
    if source_hashes() != identity["source_sha256"]:
        raise RuntimeError("Source changed during replay; result was not checkpointed.")
    write_json(result_path, result)
    write_json(metrics_path, metrics)
    write_json(config_path, config)
    manifest = {"identity": expected, "result_sha256": file_hash(result_path),
                "metrics_sha256": file_hash(metrics_path), "config_sha256": digest(config),
                "config_file_sha256": file_hash(config_path),
                "result_run_fingerprint": result["run_fingerprint"],
                "seconds": time.monotonic() - start, "summary": result["summary"]}
    write_json(manifest_path, manifest)
    event("candidate_complete", policy_id=key, seconds=manifest["seconds"], summary=result["summary"])
    return {"id": key, "config": config, "metrics": metrics, "run_fingerprint": result["run_fingerprint"]}


def run(args):
    from nomisma.calibration import generate_candidates, run_catalog, compare_metrics
    from nomisma.calibration_data import load_catalog
    study, base = registration(args.registration)
    catalog = load_catalog(args.catalog)
    if catalog["symbols"] != study["symbols"] or [row["date"] for row in catalog["sessions"]] != study["development_dates"]:
        raise ValueError("Catalog dates/cohort differ from the registered experiment.")
    if any(row["partition"] != "development" for row in catalog["sessions"]):
        raise ValueError("This development sweep cannot access holdout entries.")
    identity = {"registration_sha256": file_hash(args.registration), "catalog_sha256": catalog["catalog_sha256"],
                "catalog_file_sha256": file_hash(args.catalog), "base_config_sha256": digest(base),
                "source_sha256": source_hashes()}
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    identity_path = output / "experiment.json"
    if identity_path.exists():
        if json.loads(identity_path.read_text()) != identity:
            raise ValueError("Output directory belongs to different frozen inputs/source.")
    elif any(output.iterdir()):
        raise ValueError("Unrecognized nonempty output directory.")
    else:
        write_json(identity_path, identity)
    start = time.monotonic()
    execute = lambda config: run_catalog(args.catalog, config, study["development_dates"])
    candidates = generate_candidates(base)
    rows = [checkpoint(output / "candidates", row["id"], row["config"], identity, execute) for row in candidates]
    folds = [{"id": fold["id"], "train_dates": fold["train"], "validation_dates": fold["validation"]} for fold in study["folds"]]
    comparison = compare_metrics(rows, study["development_dates"], folds)
    write_json(output / "comparison.json", comparison)
    baseline = next(row for row in candidates if digest(row["config"]) == digest(base))
    leader_id = comparison["diagnostic_best_observed"]
    if isinstance(leader_id, dict):
        leader_id = leader_id.get("candidate_id", leader_id.get("id", leader_id.get("policy_id")))
    requested = [("fixed_baseline", baseline)]
    if leader_id is not None:
        requested.append(("diagnostic_best_observed", next(row for row in candidates if row["id"] == leader_id)))
    stress = []
    for scenario in ("double_costs", "double_timing_delays"):
        for role, row in requested:
            config = deepcopy(row["config"])
            section = "costs" if scenario == "double_costs" else "timing"
            config[section] = {key: 2 * value for key, value in config[section].items()}
            key = row["id"] + "--" + scenario
            tested = checkpoint(output / "stress", key, config, identity, execute)
            stress.append({"role": role, "base_policy_id": row["id"], "scenario": scenario, **tested})
    if source_hashes() != identity["source_sha256"] or file_hash(args.registration) != identity["registration_sha256"] or file_hash(args.catalog) != identity["catalog_file_sha256"]:
        raise RuntimeError("Frozen experiment input/source changed during execution.")
    # Recheck all metadata and normalized session bytes, including resumed results.
    refreshed = load_catalog(args.catalog)
    for row in refreshed["sessions"]:
        if file_hash(args.catalog.resolve().parent / row["path"]) != row["sha256"]:
            raise RuntimeError("A normalized session changed during execution.")
    report = {"schema_version": 1, "research_only": True, "calibration_status": comparison["calibration_status"],
              "candidate_for_holdout": None, "selected_config": None, "comparison": comparison,
              "stress": stress, "registration": study, "identity": identity,
              "completed_at": datetime.now(timezone.utc).isoformat(), "invocation_seconds": time.monotonic() - start,
              "python": platform.python_version(), "platform": platform.platform()}
    write_json(output / "report.json", report)
    event("experiment_complete", output=str(output), calibration_status=report["calibration_status"],
          diagnostic_best_observed=leader_id, selected_config=None, invocation_seconds=report["invocation_seconds"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    download = commands.add_parser("download", help="Acquire only the registered earlier development sessions")
    download.add_argument("--registration", required=True, type=Path)
    download.add_argument("--output", required=True, type=Path)
    catalog = commands.add_parser("catalog", help="Split verified parent archives into immutable session files")
    catalog.add_argument("--sources", required=True, nargs="+", type=Path)
    catalog.add_argument("--output", required=True, type=Path)
    sweep = commands.add_parser("run", help="Run/resume 27 offline candidates, folds and sensitivity diagnostics")
    sweep.add_argument("--registration", required=True, type=Path)
    sweep.add_argument("--catalog", required=True, type=Path)
    sweep.add_argument("--output", required=True, type=Path)
    parity = commands.add_parser("parity", help="Compare streaming output to the original archived baseline")
    parity.add_argument("--catalog", required=True, type=Path)
    parity.add_argument("--baseline", required=True, type=Path)
    parity.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.command == "download":
        from run import load_environment
        from nomisma.calibration_data import download_development
        study, _ = registration(args.registration)
        dates = study["acquire_dates"]
        if not set(dates).issubset(study["development_dates"]) or len(dates) * study["request_limit_per_new_session"] > study["request_limit_total"]:
            raise ValueError("Acquisition exceeds registered date or request limits.")
        load_environment(PROJECT / ".env")
        paths = download_development(args.output, study["symbols"], dates, study["request_limit_per_new_session"])
        event("download_complete", paths=[str(path) for path in paths])
    elif args.command == "catalog":
        from nomisma.calibration_data import create_catalog
        event("catalog_complete", path=str(create_catalog(args.sources, args.output)))
    elif args.command == "parity":
        from nomisma.calibration import run_catalog, semantic_result
        if args.output.exists():
            raise ValueError("Parity evidence already exists; use a new output path.")
        baseline = json.loads(args.baseline.read_text())
        dates = [row["session_date"] for row in baseline["ledger"] if row["event"] == "session_open"]
        before = source_hashes()
        result = run_catalog(args.catalog, baseline["config"], dates)
        equal = semantic_result(result) == semantic_result(baseline)
        evidence = {"identical_semantics": equal, "dates": dates, "source_sha256": before,
                    "source_unchanged": before == source_hashes(), "baseline_file_sha256": file_hash(args.baseline),
                    "original_semantic_sha256": digest(semantic_result(baseline)),
                    "streaming_semantic_sha256": digest(semantic_result(result)), "summary": result["summary"]}
        write_json(args.output, evidence)
        if not equal or not evidence["source_unchanged"]:
            raise RuntimeError("Streaming parity failed; see preserved evidence.")
        event("parity_complete", **evidence)
    else:
        run(args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError, KeyError) as error:
        print("Calibration: " + str(error), file=sys.stderr)
        raise SystemExit(1)
