"""Versioned offline development comparison over immutable session catalogs.

Candidates remain fixed throughout each continuous replay. This module adds no
execution rules and does not modify the pinned historical replay engine. Its
ranking is an exposed-data diagnostic, never a calibrated trading selection.
"""

from copy import deepcopy
from datetime import date
from decimal import Decimal
import hashlib
from itertools import product
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from . import calibration_data, replay


ADAPTER_VERSION = "calibration-stream-v1"
COMPARISON_VERSION = "calibration-development-v1"
PINNED_REPLAY_SHA256 = "138c8c0c0e973272a657d7e2ffb54e5ce1f6322e5ca29b2dc164a6d6120819be"
GRID = {"stop_atr_multiple": (1, 1.5, 2), "reward_multiple": (2, 2.5, 3),
        "hold_minutes": (5, 15, 30)}
_ZERO = Decimal(0)
_ONE = Decimal(1)


def replay_source_sha256() -> str:
    return hashlib.sha256(Path(replay.__file__).read_bytes()).hexdigest()


def _dates(values: Iterable[str], name: str) -> list:
    if not isinstance(values, (list, tuple)) or not values:
        raise ValueError(name + " must be a nonempty chronological date list.")
    try:
        normalized = [date.fromisoformat(value).isoformat() for value in values]
    except (TypeError, ValueError):
        raise ValueError(name + " must contain ISO calendar dates.") from None
    if normalized != list(values) or normalized != sorted(set(normalized)):
        raise ValueError(name + " must contain unique dates in chronological order.")
    return normalized


def generate_candidates(base: dict) -> list:
    """Return exactly 27 independent configs, changing only the three grid keys."""
    if not isinstance(base, dict) or not isinstance(base.get("policy"), dict):
        raise ValueError("A frozen replay configuration with a policy is required.")
    # Validate without replacing the caller's frozen representation with defaults.
    validated = replay._config(base, base.get("monitor", {}).get("symbols", []))
    if validated["costs"]["stop_slippage"] != validated["costs"]["target_slippage"]:
        raise ValueError("Frozen replay requires equal stop and target displacement.")
    candidates = []
    for stop, reward, holding in product(*GRID.values()):
        config = deepcopy(base)
        config["policy"].update(stop_atr_multiple=stop, reward_multiple=reward, hold_minutes=holding)
        candidates.append({"id": "k{:g}-r{:g}-h{:02d}".format(stop, reward, holding), "config": config})
    return candidates


def _validate_session(session: dict, symbols: list, previous_close: Optional[int]) -> int:
    """Mirror the unchanged run_replay entry contract across streamed sessions."""
    if not isinstance(session, dict) or not isinstance(session.get("assets"), list):
        raise ValueError("Each session must contain assets.")
    opened, closed = replay._ns(session.get("open")), replay._ns(session.get("close"))
    if opened >= closed or previous_close is not None and opened <= previous_close:
        raise ValueError("Dataset sessions must be unique, chronological and nonoverlapping.")
    if opened % replay.MINUTE or closed % replay.MINUTE:
        raise ValueError("Exchange sessions must align with minute boundaries.")
    if not isinstance(session.get("date"), str) or session["date"] < "2025-11-03":
        raise ValueError("SIP shares convention requires session dates on or after 2025-11-03.")
    asset_symbols = [asset.get("symbol") for asset in session["assets"] if isinstance(asset, dict)]
    if (len(asset_symbols) != len(session["assets"]) or len(set(asset_symbols)) != len(asset_symbols)
            or set(asset_symbols) - set(symbols)):
        raise ValueError("Session assets must be unique members of the declared cohort.")
    return closed


def run_catalog(catalog_path: Path, config: dict, dates: Optional[list] = None, *,
                expected_engine_sha256: str = PINNED_REPLAY_SHA256) -> Dict[str, Any]:
    """Preserve one engine/account across lazily verified chronological sessions.

    Only one source session is retained at a time. Decisions and ledgers remain
    in memory as the inspectable result. The finalizer receives no sessions so
    it cannot replay them a second time. Catalog provenance replaces the full
    dataset fingerprint; all behavioral outputs are unchanged.
    """
    actual_hash = replay_source_sha256()
    if expected_engine_sha256 != PINNED_REPLAY_SHA256 or actual_hash != PINNED_REPLAY_SHA256:
        raise ValueError("Pinned replay engine hash differs; this adapter must be reviewed/versioned before use.")
    catalog = calibration_data.load_catalog(catalog_path)
    selected = (_dates(dates, "Requested dates") if dates is not None else
                [entry["date"] for entry in catalog["sessions"] if entry["partition"] == "development"])
    selected = _dates(selected, "Requested dates")
    entries = {entry["date"]: entry for entry in catalog["sessions"]}
    if set(selected) - set(entries):
        raise ValueError("Requested dates are absent from the catalog.")
    if any(entries[day]["partition"] != "development" for day in selected):
        raise ValueError("Sealed holdout outcomes cannot be opened by this development adapter.")
    metadata = deepcopy(catalog.get("dataset_metadata"))
    if not isinstance(metadata, dict) or metadata.get("schema_version") != 1:
        raise ValueError("Unsupported replay dataset schema.")
    if metadata.get("source") != "alpaca" or metadata.get("feed") != "sip":
        raise ValueError("This historical pilot requires archived Alpaca SIP provenance.")
    symbols = metadata.get("symbols")
    if not isinstance(symbols, list) or not symbols or len(set(symbols)) != len(symbols):
        raise ValueError("Dataset must declare a unique nonempty symbol cohort.")
    if symbols != catalog["symbols"]:
        raise ValueError("Catalog and dataset metadata cohorts differ.")
    configured = replay._config(config, symbols)
    if configured["costs"]["stop_slippage"] != configured["costs"]["target_slippage"]:
        raise ValueError("This market-exit fixture requires equal stop and target displacement.")
    metadata["sessions"] = []
    engine = replay._Replay(metadata, configured)
    completed, previous_close = [], None
    for session in calibration_data.iter_sessions(catalog_path, selected):
        if len(completed) >= len(selected) or session.get("date") != selected[len(completed)]:
            raise ValueError("Session iterator differs from requested chronological dates.")
        previous_close = _validate_session(session, symbols, previous_close)
        engine._session(session)
        completed.append(session["date"])
        del session  # Release caller reference before iterator parses the next file.
    if completed != selected:
        raise ValueError("Session iterator omitted requested dates.")
    result = engine.run()
    result["summary"]["sessions"] = len(completed)
    provenance = {"adapter_version": ADAPTER_VERSION, "engine_sha256": actual_hash,
                  "catalog_sha256": catalog["catalog_sha256"], "session_dates": completed,
                  "sessions": [{key: entries[day][key] for key in
                                ("date", "sha256", "source_id", "source_dataset_sha256", "source_manifest_sha256")}
                               for day in completed],
                  "state_policy": "One unchanged engine and fixed candidate across every selected session; no reset or stitched switching.",
                  "fingerprint_basis": "Catalog metadata hash and selected immutable session/source hashes; differs from full dataset JSON fingerprint."}
    result["dataset_fingerprint"] = replay._fingerprint(provenance)
    result["streaming"] = provenance
    result.pop("run_fingerprint", None)
    result["run_fingerprint"] = replay._fingerprint(result)
    return result


def semantic_result(result: dict) -> dict:
    """Exact parity projection: omit only known provenance/fingerprint changes."""
    return {key: deepcopy(value) for key, value in result.items()
            if key not in ("dataset_fingerprint", "run_fingerprint", "streaming")}


def _money(value: Any) -> Optional[Decimal]:
    if type(value) not in (int, float, Decimal):
        return None
    number = Decimal(str(value))
    return number if number.is_finite() else None


def _flat(boundary: dict) -> bool:
    return (isinstance(boundary.get("positions"), dict) and not boundary["positions"]
            and isinstance(boundary.get("pending_symbols"), list) and not boundary["pending_symbols"]
            and _money(boundary.get("cash_reserved")) == 0
            and _money(boundary.get("scenario_risk_reserved")) == 0)


def _aggregate(rows: list) -> dict:
    invalid = [row["date"] for row in rows if not row["valid"]]
    valid = bool(rows) and not invalid
    mean_return, compounded, drawdown = None, None, None
    if valid:
        returns = [_money(row["session_return"]) for row in rows]
        mean_return = sum(returns, _ZERO) / len(returns)
        compounded = _ONE
        for value in returns:
            compounded *= _ONE + value
        compounded -= _ONE
        peak = _money(rows[0]["open_cash"])
        drawdown = _ZERO
        for row in rows:
            cash = _money(row["close_cash"])
            peak = max(peak, cash)
            drawdown = max(drawdown, (peak - cash) / peak)
    return replay._json({"valid": valid, "session_count": len(rows), "invalid_dates": invalid,
        "mean_session_return": mean_return, "compounded_session_return": compounded,
        "net_pnl": sum((_money(row["close_cash"]) - _money(row["open_cash"]) for row in rows), _ZERO) if valid else None,
        "total_net_pnl": sum((_money(row["close_cash"]) - _money(row["open_cash"]) for row in rows), _ZERO) if valid else None,
        "session_close_drawdown": drawdown, "full_intraday_drawdown": None,
        "opened_trades": sum(row.get("opened_trades", 0) for row in rows),
        "closed_trades": sum(row.get("closed_trades", 0) for row in rows),
        "fill_count": sum(row.get("fill_count", 0) for row in rows),
        "fees": sum((_money(row.get("fees", 0)) or _ZERO for row in rows), _ZERO),
        "traded_days": sum(bool(row.get("traded_symbols")) for row in rows),
        "traded_symbols": sorted({symbol for row in rows for symbol in row.get("traded_symbols", [])}),
        "no_trade_days": sum(row.get("fill_count", 0) == 0 for row in rows),
        "interpretation": "Equal-weight arithmetic mean of flat-boundary session returns; closing-cash drawdown excludes intraday paths."})


def session_metrics(result: dict) -> dict:
    """Match session boundaries by date; never score cash alone during exposure."""
    if not isinstance(result, dict) or not isinstance(result.get("ledger"), list):
        raise ValueError("Replay result with an account ledger is required.")
    boundaries = {}
    for row in result["ledger"]:
        if row.get("event") in ("session_open", "session_end"):
            day = row.get("session_date")
            _dates([day], "Ledger session date")
            boundaries.setdefault(day, {"session_open": [], "session_end": []})[row["event"]].append(row)
    for decision in result.get("decisions", []):
        day = decision.get("session_date")
        if day is not None:
            boundaries.setdefault(day, {"session_open": [], "session_end": []})
    for day in result.get("streaming", {}).get("session_dates", []):
        boundaries.setdefault(day, {"session_open": [], "session_end": []})
    rows = []
    for day in sorted(boundaries):
        pair = boundaries[day]
        problems = []
        if len(pair["session_open"]) != 1 or len(pair["session_end"]) != 1:
            problems.append("Exactly one session_open and session_end ledger row are required.")
        opening = pair["session_open"][0] if len(pair["session_open"]) == 1 else {}
        closing = pair["session_end"][0] if len(pair["session_end"]) == 1 else {}
        cash_open, cash_close = _money(opening.get("cash")), _money(closing.get("cash"))
        if cash_open is None or cash_open <= 0:
            problems.append("Opening cash must be finite and positive.")
        if cash_close is None or cash_close < 0:
            problems.append("Closing cash must be finite and nonnegative.")
        if not _flat(opening) or not _flat(closing):
            problems.append("Both session boundaries must be flat with no pending cash or scenario-risk reservations.")
        try:
            opened, closed = replay._ns(opening.get("at")), replay._ns(closing.get("at"))
            if opened >= closed:
                raise ValueError()
        except (TypeError, ValueError):
            opened = closed = None
            problems.append("Session boundary timestamps must be valid and ordered.")
        fills = [fill for fill in result.get("fills", []) if opened is not None
                 and opened <= replay._ns(fill["at"]) < closed]
        fee_values = [_money(fill.get("fee")) for fill in fills]
        if any(value is None or value < 0 for value in fee_values):
            problems.append("Fill fees must be finite nonnegative amounts.")
        closed_trades = [trade for trade in result.get("trades", []) if opened is not None
                         and trade.get("status") == "closed" and trade.get("exit_at")
                         and opened <= replay._ns(trade["exit_at"]) < closed]
        valid = not problems
        rows.append(replay._json({"date": day, "valid": valid, "invalid_reasons": problems,
            "open_at": opening.get("at"), "close_at": closing.get("at"),
            "open_cash": cash_open, "close_cash": cash_close,
            "open_flat": _flat(opening), "close_flat": _flat(closing),
            "session_return": (cash_close - cash_open) / cash_open if valid else None,
            "net_session_pnl": cash_close - cash_open if valid else None,
            "opened_trades": len({fill["parent_id"] for fill in fills if fill.get("side") == "buy"}),
            "closed_trades": len(closed_trades), "fill_count": len(fills),
            "fees": sum((value for value in fee_values if value is not None), _ZERO),
            "traded_symbols": sorted({fill["symbol"] for fill in fills}),
            "unresolved_at_close": deepcopy(closing.get("positions", {})),
            "pending_at_close": deepcopy(closing.get("pending_symbols", []))}))
    return {"sessions": rows, "aggregate": _aggregate(rows),
            "final_unresolved": deepcopy(result.get("unresolved", [])),
            "return_unit": "fraction (0.01 = 1%)", "full_intraday_drawdown": None}


def _subset(metrics: dict, dates: list) -> dict:
    by_date = {row["date"]: row for row in metrics["sessions"]}
    rows = [by_date.get(day, {"date": day, "valid": False,
                            "invalid_reasons": ["Requested date is absent from replay metrics."]}) for day in dates]
    return {"sessions": deepcopy(rows), "aggregate": _aggregate(rows)}


def _diagnostic_best(candidates: list, key: str) -> Optional[str]:
    scored = [candidate for candidate in candidates if candidate[key]["valid"]]
    return min(scored, key=lambda item: (-_money(item[key]["mean_session_return"]), item["id"]))["id"] if scored else None


def compare_candidates(results: Any, development_dates: list, folds: list) -> dict:
    """Extract one full result at a time, then compare compact session metrics.

    ``results`` accepts an iterable of ``{id, config, result}`` or an ID mapping.
    Each fold is ``{id, train_dates, validation_dates}``. All fold outcomes are
    exposed development diagnostics; no realized accounts are stitched across
    a changing fold-selected policy.
    """
    if isinstance(results, dict):
        results = ({"id": key, "config": value.get("config"), "result": value} for key, value in results.items())
    def compact():
        for item in results:
            result = item.get("result")
            if not isinstance(result, dict):
                raise ValueError("Each candidate must contain a replay result.")
            config = item.get("config") or result.get("config")
            if result.get("config") is not None and result["config"] != config:
                raise ValueError("Candidate config differs from its replay result.")
            row = {"id": item.get("id"), "config": config,
                   "metrics": session_metrics(result), "run_fingerprint": result.get("run_fingerprint")}
            del result, item
            yield row
            del row
    return compare_metrics(compact(), development_dates, folds)


def compare_metrics(rows: Iterable[dict], development_dates: list, folds: list) -> dict:
    """Compare small ``{id,config,metrics,run_fingerprint}`` checkpoint rows."""
    development_dates = _dates(development_dates, "Development dates")
    if not isinstance(folds, list):
        raise ValueError("Folds must be a list.")
    normalized_folds, fold_ids = [], set()
    for fold in folds:
        ident = fold.get("id")
        if not isinstance(ident, str) or not ident or ident in fold_ids:
            raise ValueError("Fold IDs must be unique nonempty strings.")
        train = _dates(fold.get("train_dates"), "Training dates")
        validation = _dates(fold.get("validation_dates"), "Validation dates")
        if train[-1] >= validation[0] or set(train + validation) - set(development_dates):
            raise ValueError("Training must precede validation within the development dates.")
        normalized_folds.append({"id": ident, "train_dates": train, "validation_dates": validation})
        fold_ids.add(ident)
    candidates, ids = [], set()
    for item in rows:
        ident = item.get("id")
        if not isinstance(ident, str) or not ident or ident in ids:
            raise ValueError("Candidate IDs must be unique nonempty strings.")
        ids.add(ident)
        config = item.get("config")
        if not isinstance(config, dict) or not isinstance(config.get("policy"), dict):
            raise ValueError("Candidate config must contain its fixed policy.")
        metrics = item.get("metrics")
        if not isinstance(metrics, dict) or not isinstance(metrics.get("sessions"), list):
            raise ValueError("Each candidate must contain compact session metrics.")
        development = _subset(metrics, development_dates)
        candidate = {"id": ident, "parameters": {key: config["policy"][key] for key in GRID},
                     "config_fingerprint": replay._fingerprint(config),
                     "run_fingerprint": item.get("run_fingerprint"),
                     "development": development["aggregate"], "session_metrics": development["sessions"],
                     "final_unresolved": metrics.get("final_unresolved", []), "folds": []}
        for fold in normalized_folds:
            candidate["folds"].append({"id": fold["id"],
                "training": _subset(metrics, fold["train_dates"])["aggregate"],
                "validation": _subset(metrics, fold["validation_dates"])["aggregate"]})
        candidates.append(candidate)
        del item
    if not candidates:
        raise ValueError("At least one fixed-candidate replay result is required.")
    candidates.sort(key=lambda item: item["id"])
    best = _diagnostic_best(candidates, "development")
    fold_reports = []
    for index, fold in enumerate(normalized_folds):
        rows = [{**candidate["folds"][index], "id": candidate["id"], "fold_id": fold["id"]}
                for candidate in candidates]
        winner = _diagnostic_best(rows, "training")
        chosen = next((item for item in rows if item["id"] == winner), None)
        fold_reports.append({**fold, "diagnostic_training_best_observed": winner,
            "validation_of_training_diagnostic": chosen["validation"] if chosen else None,
            "per_candidate": rows, "policy_application": "Separate continuously replayed fixed policies; no switching or stitched equity curve."})
    neighbor_rows = []
    by_parameters = {tuple(candidate["parameters"][key] for key in GRID): candidate for candidate in candidates}
    if len(by_parameters) != len(candidates):
        raise ValueError("Candidate grid contains duplicate parameter combinations.")
    for candidate in candidates:
        point = tuple(candidate["parameters"][key] for key in GRID)
        neighbors = []
        for axis, values in enumerate(GRID.values()):
            if point[axis] not in values:
                continue
            position = values.index(point[axis])
            for offset in (-1, 1):
                adjacent = position + offset
                if not 0 <= adjacent < len(values):
                    continue
                neighbor_point = list(point)
                neighbor_point[axis] = values[adjacent]
                neighbor = by_parameters.get(tuple(neighbor_point))
                if neighbor is not None:
                    score, other = candidate["development"], neighbor["development"]
                    neighbors.append({"id": neighbor["id"], "valid": other["valid"],
                        "mean_session_return": other["mean_session_return"],
                        "score_difference": (float(_money(score["mean_session_return"]) - _money(other["mean_session_return"]))
                                             if score["valid"] and other["valid"] else None)})
        neighbor_rows.append({"id": candidate["id"], "neighbors": sorted(neighbors, key=lambda item: item["id"])})
    return {"schema_version": 1, "model_id": COMPARISON_VERSION,
        "status": "development_only_insufficient_evidence",
        "calibration_status": "development_only_insufficient_evidence", "development_dates": development_dates,
        "ranking_metric": "Arithmetic mean session return; any invalid scored session makes candidate score invalid.",
        "tie_break": "Lexicographic stable candidate ID.", "candidates": candidates,
        "diagnostic_best_observed": {"candidate_id": best, "posthoc": True,
            "may_be_no_trade_policy": True, "meaning": "Exposed-development descriptive ranking only; not a selected or calibrated configuration."},
        "candidate_for_holdout": None, "selected_config": None,
        "folds": fold_reports, "neighbor_grid": neighbor_rows,
        "stability": {"diagnostic_training_choices": [row["diagnostic_training_best_observed"] for row in fold_reports],
            "distinct_diagnostic_training_choices": len({row["diagnostic_training_best_observed"] for row in fold_reports if row["diagnostic_training_best_observed"]}),
            "confidence": "not_assessed"},
        "confidence_gates": {key: {"status": "not_assessed", "reason": reason} for key, reason in {
            "universe": "Retrospective fixed cohort; no point-in-time market-wide universe.",
            "sample": "Few exposed development sessions; independent effective sample size is insufficiently established.",
            "holdout": "No untouched holdout was evaluated.",
            "acceptance_limits": "Actual user acceptance limits have not been specified.",
            "execution": "Costs, latency, liquidity, original arrivals and halt coverage remain assumptions.",
            "drawdown": "Full intraday equity drawdown is unavailable; closing-cash drawdown is only a limited diagnostic."
        }.items()}}
