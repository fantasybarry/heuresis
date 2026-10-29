"""Immutable development catalogs and bounded session-by-session acquisition.

This module does not change the pilot archive or replay implementation. Catalog
creation verifies each parent archive, then publishes independently hashed
session files. Iteration opens only requested development sessions. Historical
arrival times, halts, and a point-in-time market-wide universe remain unknown.
"""

import json
from pathlib import Path

from . import providers, replay_data
from .replay_data import _canonical, _sha, file_sha256 as _file_hash

_SCHEMA = 1


def _new_directory(output_dir):
    original = Path(output_dir).absolute()
    if original.is_symlink():
        raise ValueError("Catalog output must not be a symbolic link.")
    directory = original.resolve()
    if directory.exists() and (not directory.is_dir() or any(directory.iterdir())):
        raise ValueError("Output directory must be new or empty; existing artifacts are immutable.")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _safe_file(directory, relative):
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("Catalog contains an invalid relative artifact path.")
    target = directory / relative
    current = directory
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Catalog artifacts must not use symbolic links.")
    if directory not in target.resolve().parents:
        raise ValueError("Catalog artifact escapes its directory.")
    return target


def _catalog_digest(catalog):
    return _sha(_canonical({key: value for key, value in catalog.items() if key != "catalog_sha256"}))


def _validate_dates(dates):
    if not isinstance(dates, (list, tuple)) or not dates:
        raise ValueError("Supply an explicit nonempty date list.")
    normalized = [providers._date(value).isoformat() for value in dates]
    if len(set(normalized)) != len(normalized):
        raise ValueError("Duplicate session dates are not allowed.")
    return sorted(normalized)


def _validate_session(session, symbols, declared_date=None):
    if not isinstance(session, dict) or not isinstance(session.get("assets"), list):
        raise ValueError("A normalized session with assets is required.")
    day = providers._date(session.get("date")).isoformat()
    if declared_date is not None and day != declared_date:
        raise ValueError("Session file date differs from its catalog entry.")
    assets = session["assets"]
    if any(not isinstance(asset, dict) for asset in assets):
        raise ValueError("Session contains malformed assets.")
    asset_symbols = [asset.get("symbol") for asset in assets]
    if len(asset_symbols) != len(symbols) or set(asset_symbols) != set(symbols):
        raise ValueError("Every session must contain the exact complete declared cohort.")
    opening = replay_data.timestamp_ns(session.get("open"))
    closing = replay_data.timestamp_ns(session.get("close"))
    if opening >= closing:
        raise ValueError("Session exchange hours are invalid.")
    return day


def create_catalog(sources, output_dir):
    """Split verified replay archives into one-session files; return catalog path.

    Sources must use exactly one fixed cohort. All imported sessions are exposed
    development inputs, never an independent holdout. Incomplete creation leaves
    an explicit build_status.json and no usable catalog.json.
    """
    if not isinstance(sources, (list, tuple)) or not sources:
        raise ValueError("Supply one or more verified parent archive paths.")
    directory = _new_directory(output_dir)
    (directory / "sessions").mkdir()
    (directory / "sources").mkdir()
    status = {"status": "incomplete", "completed_source_count": 0}
    catalog = {"schema_version": _SCHEMA, "status": "complete", "source": "alpaca", "feed": "sip",
               "symbols": None, "sessions": [], "sources": [],
               "dataset_metadata": None,
               "provenance": {"universe": "Fixed retrospective development cohort declared in symbols; no point-in-time market-wide membership.",
                              "original_receipt_times": "unknown", "halt_coverage": "unknown",
                              "historical_float": "unavailable", "bar_versions": "final historical REST versions",
                              "default_partition": "development", "holdout_status": "none; no imported session is claimed untouched"}}
    dates_seen, source_paths = set(), set()
    try:
        for index, source in enumerate(sources):
            original = Path(source).absolute()
            if original.is_dir():
                original = original / "dataset.json"
            if original.is_symlink() or (original.parent / "manifest.json").is_symlink():
                raise ValueError("Parent archive files must not be symbolic links.")
            source = original.resolve()
            if source in source_paths:
                raise ValueError("Duplicate parent archive path.")
            source_paths.add(source)
            manifest_path = source.parent / "manifest.json"
            manifest_bytes = manifest_path.read_bytes()
            manifest_hash = _sha(manifest_bytes)
            parent = json.loads(manifest_bytes)
            # Existing loader verifies normalized bytes plus every compressed
            # original page and its uncompressed body before exposing a session.
            dataset = replay_data.load_dataset(source)
            if dataset.get("source") != "alpaca" or dataset.get("feed") != "sip":
                raise ValueError("Calibration catalog requires archived Alpaca SIP data.")
            symbols = dataset.get("symbols")
            if not isinstance(symbols, list) or not symbols or len(symbols) != len(set(symbols)):
                raise ValueError("Archive must declare a unique cohort.")
            if catalog["symbols"] is None:
                catalog["symbols"] = list(symbols)
                catalog["dataset_metadata"] = {key: value for key, value in dataset.items() if key not in ("sessions", "manifest")}
            elif symbols != catalog["symbols"]:
                raise ValueError("Parent archives have different cohorts or cohort order.")
            sessions = dataset.get("sessions")
            if not isinstance(sessions, list) or not sessions:
                raise ValueError("Parent dataset contains no normalized sessions.")
            session_dates = [_validate_session(session, symbols) for session in sessions]
            if session_dates != sorted(set(session_dates)) or session_dates != parent.get("session_dates"):
                raise ValueError("Parent archive dates are duplicated, out of order, or differ from its manifest.")
            if dates_seen.intersection(session_dates):
                raise ValueError("Duplicate session date across parent archives.")
            dates_seen.update(session_dates)
            source_id = "source-{:04d}".format(index + 1)
            copied_manifest = "sources/{}-manifest.json".format(source_id)
            (directory / copied_manifest).write_bytes(manifest_bytes)
            source_hash = parent["dataset"]["sha256"]
            catalog["sources"].append({"source_id": source_id, "archive_dataset_path": str(source),
                                       "dataset_sha256": source_hash, "manifest_path": copied_manifest,
                                       "manifest_sha256": manifest_hash, "session_dates": session_dates,
                                       "verified_raw_page_count": len(parent.get("pages", [])),
                                       "verification": "all raw page/body and normalized dataset hashes verified at catalog creation"})
            for session in sessions:
                relative = "sessions/{}.json".format(session["date"])
                payload = _canonical(session)
                (directory / relative).write_bytes(payload)
                catalog["sessions"].append({"date": session["date"], "path": relative, "sha256": _sha(payload),
                                            "source_id": source_id, "source_dataset_sha256": source_hash,
                                            "source_manifest_sha256": manifest_hash, "partition": "development",
                                            "exposed": True, "exposure_basis": "Conservatively treated as exposed development; outcome access is not tracked."})
                del payload
            if _file_hash(source) != source_hash or _file_hash(manifest_path) != manifest_hash:
                raise ValueError("Parent archive changed while building the catalog.")
            status["completed_source_count"] += 1
            del session, sessions, dataset
        catalog["sessions"].sort(key=lambda row: row["date"])
        catalog["catalog_sha256"] = _catalog_digest(catalog)
        (directory / "catalog.json").write_bytes(_canonical(catalog))
        status.update(status="complete", session_count=len(catalog["sessions"]))
        return directory / "catalog.json"
    except Exception as error:
        status["failure"] = str(error) if isinstance(error, (ValueError, OSError)) else type(error).__name__
        raise
    finally:
        (directory / "build_status.json").write_bytes(_canonical(status))


def load_catalog(catalog_path):
    """Read and validate metadata/lineage only; never read session outcomes."""
    original = Path(catalog_path).absolute()
    if original.is_symlink():
        raise ValueError("Catalog must not be a symbolic link.")
    path = original.resolve()
    catalog = json.loads(path.read_bytes())
    if catalog.get("schema_version") != _SCHEMA or catalog.get("status") != "complete" or catalog.get("catalog_sha256") != _catalog_digest(catalog):
        raise ValueError("Catalog is incomplete, unsupported, or its metadata hash differs.")
    if catalog.get("source") != "alpaca" or catalog.get("feed") != "sip":
        raise ValueError("Catalog source/feed must be Alpaca SIP.")
    symbols = catalog.get("symbols")
    if not isinstance(symbols, list) or not symbols or len(symbols) != len(set(symbols)):
        raise ValueError("Catalog has an invalid cohort.")
    sources = {}
    for source in catalog.get("sources", []):
        key = source.get("source_id")
        if not isinstance(key, str) or key in sources:
            raise ValueError("Catalog source IDs must be unique.")
        copied = _safe_file(path.parent, source.get("manifest_path"))
        content = copied.read_bytes()
        if _sha(content) != source.get("manifest_sha256"):
            raise ValueError("Parent manifest hash mismatch.")
        manifest = json.loads(content)
        if manifest.get("status") != "complete" or manifest.get("dataset", {}).get("sha256") != source.get("dataset_sha256") or manifest.get("symbols") != symbols or manifest.get("session_dates") != source.get("session_dates"):
            raise ValueError("Copied source manifest does not match catalog lineage.")
        sources[key] = source
    rows = catalog.get("sessions")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Catalog contains no session entries.")
    days = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid catalog session entry.")
        day = providers._date(row.get("date")).isoformat()
        _safe_file(path.parent, row.get("path"))  # No session contents opened.
        source = sources.get(row.get("source_id"))
        if not source or day not in source["session_dates"] or row.get("source_dataset_sha256") != source["dataset_sha256"] or row.get("source_manifest_sha256") != source["manifest_sha256"]:
            raise ValueError("Session lineage differs from parent archive.")
        if row.get("partition") not in ("development", "sealed_holdout"):
            raise ValueError("Unknown catalog partition.")
        days.append(day)
    if days != sorted(set(days)):
        raise ValueError("Catalog dates must be unique and chronological.")
    return catalog


def iter_sessions(catalog_path, dates=None):
    """Yield one verified requested development session at a time.

    Omitted dates means all development entries only. Sealed holdout entries
    cannot be opened through this development interface, even if requested.
    Lineage manifests are metadata; unrequested session files are never read.
    """
    catalog = load_catalog(catalog_path)
    directory = Path(catalog_path).resolve().parent
    selected = set(_validate_dates(dates)) if dates is not None else {row["date"] for row in catalog["sessions"] if row["partition"] == "development"}
    available = {row["date"]: row for row in catalog["sessions"]}
    if selected - set(available):
        raise ValueError("Requested dates are absent from the catalog.")
    if any(available[day]["partition"] != "development" for day in selected):
        raise ValueError("Sealed holdout outcomes cannot be read by the development iterator.")
    for day in sorted(selected):
        row = available[day]
        path = _safe_file(directory, row["path"])
        content = path.read_bytes()
        if _sha(content) != row["sha256"]:
            raise ValueError("Session artifact hash mismatch: " + day)
        session = json.loads(content)
        del content
        _validate_session(session, catalog["symbols"], day)
        yield session
        del session


def download_development(output_dir, symbols, dates, max_requests_per_session=200):
    """Sequentially download a declared development batch using frozen importer.

    Invocation is an acquisition action; the coordinator must freeze the study
    registration before calling. This function never runs automatically on import.
    """
    dates = _validate_dates(dates)
    symbols = [providers._symbol(symbol) for symbol in symbols]
    if not symbols or len(symbols) != len(set(symbols)):
        raise ValueError("Supply a unique explicit cohort.")
    if type(max_requests_per_session) is not int or max_requests_per_session < 1:
        raise ValueError("Per-session request budget must be a positive integer.")
    directory = _new_directory(output_dir)
    batch = {"schema_version": _SCHEMA, "status": "incomplete", "partition": "development",
             "symbols": sorted(symbols), "session_dates": dates,
             "max_requests_per_session": max_requests_per_session,
             "max_requests_total": len(dates) * max_requests_per_session, "archives": []}
    paths = []
    try:
        for day in dates:
            path = replay_data.download_dataset(directory / day, symbols, [day], max_requests=max_requests_per_session)
            paths.append(path)
            batch["archives"].append({"date": day, "dataset_path": str(path), "dataset_sha256": _file_hash(path)})
        batch["status"] = "complete"
        return paths
    except Exception as error:
        batch["failure"] = str(error) if isinstance(error, (ValueError, OSError)) else type(error).__name__
        raise
    finally:
        (directory / "development_batch.json").write_bytes(_canonical(batch))
