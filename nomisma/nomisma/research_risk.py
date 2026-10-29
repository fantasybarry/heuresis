"""Offline liquidation-equity observation and fixed-dollar research guard.

The immutable replay supplies signals, fills, fees and execution latency. This
versioned subclass observes quotes at their modeled availability, values only
fresh compatible holdings, and optionally adds a permanent $100 drawdown
latch to a $1,000 engineering account. It cannot guarantee a loss bound.
"""

from copy import deepcopy
from decimal import Decimal
import heapq
from pathlib import Path
from typing import Any, Optional

from . import calibration, calibration_data, replay


MODEL_ID = "research-equity-guard-v1"
INITIAL_CAPITAL = Decimal("1000")
DRAWDOWN_AMOUNT = Decimal("100")
FRESH_NS = 5 * replay.NS
_ZERO = Decimal(0)


class _GuardedReplay(replay._Replay):
    """Additional observer/control hooks; frozen execution methods stay intact."""

    def __init__(self, dataset: dict, config: dict, guard_enabled: bool = True):
        super().__init__(dataset, config)
        self.guard_enabled = guard_enabled
        self.observed_quotes = {}
        self.equity_events = []
        self.equity_samples = 0
        self.peak_equity = self.cash
        self.max_observed_drawdown = _ZERO
        self.breached = False
        self.breach_at = None
        self.breach_equity = None
        self.breach_floor = None
        self.unknown_intervals = []
        self.unknown_since = None
        self.unknown_samples = 0
        self._incoming_session = None
        self._unknown_basis = {}
        self._updating_risk = False
        self._last_event_signature = None
        self._last_valuation = None

    def _risk_timer(self, stamp: int, kind: str, symbol: str, payload: dict) -> None:
        self.timer_sequence += 1
        priority = -2 if kind == "risk_quote" else -1
        heapq.heappush(self.timers, (stamp, priority, self.timer_sequence, kind, symbol, payload))

    def _valuation(self) -> dict:
        equity = self.cash
        position_risk = _ZERO
        unknown, marks = {}, {}
        for symbol, position in sorted(self.positions.items()):
            observed = self.observed_quotes.get(symbol)
            reason = self._unknown_basis.get(symbol) or self.frozen_symbols.get(symbol)
            if reason is None and observed is None:
                reason = "No quote is available at the modeled observation time."
            if reason is None and not observed["valid"]:
                reason = observed["invalid_reason"]
            if reason is None and not 0 <= self.now - observed["event_ns"] <= FRESH_NS:
                reason = "Newest observed quote is more than five event-time seconds old."
            if reason is not None:
                unknown[symbol] = reason
                continue
            quantity = position["quantity"]
            net_bid = max(_ZERO, observed["bid"] - self.costs["stop_slippage"]) - self.costs["exit_per_share"]
            net_stop = max(_ZERO, position["stop"] - self.costs["stop_slippage"]) - self.costs["exit_per_share"]
            mark_value, stop_value = quantity * net_bid, quantity * net_stop
            original_risk = quantity * position["_risk_per_share"]
            guard_risk = max(original_risk, max(_ZERO, mark_value - stop_value))
            equity += mark_value
            position_risk += guard_risk
            marks[symbol] = {"quantity": quantity, "bid": observed["bid"],
                "quote_event_at": replay._iso(observed["event_ns"]),
                "modeled_observed_at": replay._iso(observed["observed_ns"]),
                "age_seconds": (self.now - observed["event_ns"]) / replay.NS,
                "net_liquidation_value": mark_value, "net_stop_value": stop_value,
                "original_risk_reservation": original_risk, "guard_risk": guard_risk}
        pending_risk = sum((order["_risk_reserved"] for order in self.pending.values()), _ZERO)
        return {"complete": not unknown, "equity": None if unknown else equity,
                "marks": marks, "unknown_symbols": unknown,
                "position_guard_risk": None if unknown else position_risk,
                "pending_risk": pending_risk}

    def _sample(self, reason: str, *, emit: bool = True) -> dict:
        valuation = self._valuation()
        self.equity_samples += 1
        if valuation["complete"]:
            equity = valuation["equity"]
            self.peak_equity = max(self.peak_equity, equity)
            drawdown = self.peak_equity - equity
            self.max_observed_drawdown = max(self.max_observed_drawdown, drawdown)
            if self.unknown_since is not None:
                self.unknown_intervals.append({"start": replay._iso(self.unknown_since), "end": replay._iso(self.now),
                    "duration_seconds": (self.now - self.unknown_since) / replay.NS, "open_at_end": False})
                self.unknown_since = None
            headroom = DRAWDOWN_AMOUNT - drawdown
            allowance = max(_ZERO, headroom - valuation["position_guard_risk"] - valuation["pending_risk"])
            if not self.breached and equity <= self.peak_equity - DRAWDOWN_AMOUNT:
                self.breached = True
                self.breach_at, self.breach_equity = self.now, equity
                self.breach_floor = self.peak_equity - DRAWDOWN_AMOUNT
        else:
            self.unknown_samples += 1
            if self.unknown_since is None:
                self.unknown_since = self.now
            drawdown = headroom = allowance = None
        valuation.update(peak_equity=self.peak_equity, floor=self.peak_equity - DRAWDOWN_AMOUNT,
                         drawdown=drawdown, headroom=headroom, new_risk_allowance=allowance,
                         guard_latched=self.breached)
        self._last_valuation = valuation
        if self.guard_enabled and not self._updating_risk and (self.breached or not valuation["complete"]):
            self._updating_risk = True
            try:
                for symbol in list(self.pending):
                    self._cancel(symbol, "drawdown_guard_cancel" if self.breached else "unknown_equity_cancel")
                if self.breached:
                    for symbol in list(self.positions):
                        self._trigger_exit(symbol, "peak_dollar_drawdown")
            finally:
                self._updating_risk = False
            # Cancellation changes only pending risk, not cash or equity.
            valuation["pending_risk"] = sum((order["_risk_reserved"] for order in self.pending.values()), _ZERO)
            if valuation["complete"]:
                valuation["new_risk_allowance"] = max(_ZERO, valuation["headroom"] - valuation["position_guard_risk"] - valuation["pending_risk"])
        event = replay._json({"at": replay._iso(self.now), "reason": reason, "cash": self.cash,
            "liquidation_equity": valuation["equity"], "complete": valuation["complete"],
            "peak_equity": self.peak_equity, "drawdown_dollars": drawdown,
            "equity_floor": valuation["floor"], "headroom": headroom,
            "position_guard_risk": valuation["position_guard_risk"],
            "pending_risk": valuation["pending_risk"],
            "new_risk_allowance": valuation["new_risk_allowance"],
            "guard_latched": self.breached, "unknown_symbols": valuation["unknown_symbols"],
            "positions": {symbol: position["quantity"] for symbol, position in sorted(self.positions.items())}})
        signature = {key: value for key, value in event.items() if key not in ("at", "reason")}
        if emit and (reason != "observed_quote" or signature != self._last_event_signature):
            event["sequence"] = len(self.equity_events) + 1
            self.equity_events.append(event)
            self._last_event_signature = signature
        return valuation

    def _observe_quote(self, symbol: str, raw: dict) -> None:
        stamp = replay._ns(raw["t"])
        valid = replay._quote_valid(raw) and raw.get("halted") is not True
        self.observed_quotes[symbol] = {"event_ns": stamp, "observed_ns": self.now,
            "valid": valid, "bid": replay._d(raw["bp"]) if valid else None,
            "invalid_reason": "Known halt invalidates liquidation valuation." if raw.get("halted") is True
                              else "Newest observed quote is invalid or has unsupported conditions."}
        if valid:
            expires = stamp + FRESH_NS + 1
            if expires > self.now:
                self._risk_timer(expires, "risk_stale", symbol, {"event_ns": stamp})
        if symbol in self.positions:
            self._sample("observed_quote")

    def _quote(self, symbol: str, raw: dict, opened: int, closed: int) -> None:
        # A provider event affects observer state only when its modeled receipt
        # occurs. Frozen fills retain the declared zero fill-report latency.
        delay = self.config["timing"]["quote_delay_seconds"] * replay.NS
        if delay:
            self._risk_timer(self.now + delay, "risk_quote", symbol, raw)
        else:
            self._observe_quote(symbol, raw)
        if self.guard_enabled and self.pending:
            self._sample("execution_check", emit=False)
        super()._quote(symbol, raw, opened, closed)

    def _control_timer(self, kind: str, symbol: str, ident: Any) -> None:
        if kind == "risk_quote":
            self._observe_quote(symbol, ident)
        elif kind == "risk_stale":
            observed = self.observed_quotes.get(symbol)
            if (observed is not None and observed["event_ns"] == ident["event_ns"]
                    and symbol in self.positions):
                self._sample("quote_stale")
        else:
            super()._control_timer(kind, symbol, ident)

    def _snapshot(self, kind: str, symbol: str = "", **details: Any) -> None:
        if kind == "session_open" and self._incoming_session is not None:
            # The frozen engine drains prior-session timers before this hook.
            # Apply the new basis here, never to an earlier pending observation.
            supplied = {asset["symbol"]: asset for asset in self._incoming_session["assets"]}
            for held in self.positions:
                asset = supplied.get(held, {})
                quality = asset.get("quality", {})
                factor = quality.get("daily_split_to_session_factor")
                if factor is None or factor != self.share_factors.get(held):
                    self._unknown_basis[held] = "Held share basis changed or is unavailable; liquidation valuation is unknown."
                elif quality.get("data_blockers"):
                    self._unknown_basis[held] = "Session data is excluded; held liquidation valuation is unavailable."
            while self.timers and self.timers[0][0] == self.now and self.timers[0][1] < 0:
                _, _, _, timer_kind, timer_symbol, payload = heapq.heappop(self.timers)
                self._control_timer(timer_kind, timer_symbol, payload)
        super()._snapshot(kind, symbol, **details)
        self._sample("ledger:" + kind)

    def _context(self, marks: dict) -> Optional[dict]:
        if not self.guard_enabled:
            return super()._context(marks)
        valuation = self._sample("decision_context")
        if not valuation["complete"] or valuation["equity"] <= 0:
            return None
        observed_marks = {symbol: {"bid": quote["bid"]} for symbol, quote in self.observed_quotes.items() if quote["valid"]}
        context = super()._context(observed_marks)
        if context is None:
            return None
        equity = valuation["equity"]
        allowance = _ZERO if self.breached else valuation["new_risk_allowance"]
        _, original_risk, _ = self._totals(observed_marks)
        caps = {"risk_budget": Decimal("25"),
                "day_risk_remaining": max(_ZERO, Decimal("100") - self.loss_debits - original_risk),
                "portfolio_risk_remaining": max(_ZERO, Decimal("75") - original_risk)}
        for key, cap in caps.items():
            context[key] = float(min(replay._d(context[key]), cap, allowance))
        for key in ("cash", "risk_budget", "day_risk_remaining", "portfolio_risk_remaining",
                    "max_position_notional", "gross_notional_remaining"):
            context[key] = float(min(replay._d(context[key]), equity))
        context["equity"] = float(equity)
        return context

    def _session(self, session: dict) -> None:
        self._incoming_session = session
        try:
            super()._session(session)
            self._sample("session_observation_end")
        finally:
            self._incoming_session = None

    def equity_report(self) -> dict:
        intervals = deepcopy(self.unknown_intervals)
        if self.unknown_since is not None:
            intervals.append({"start": replay._iso(self.unknown_since), "end": replay._iso(self.now),
                "duration_seconds": (self.now - self.unknown_since) / replay.NS, "open_at_end": True})
        valuation = self._valuation()
        return replay._json({"schema_version": 1, "model_id": MODEL_ID,
            "guard": {"enabled": self.guard_enabled, "mode": "peak_dollar_drawdown",
                      "amount": DRAWDOWN_AMOUNT, "initial_capital": self.account["initial_cash"],
                      "permanent_across_sessions": True},
            "valuation": "Cash plus complete fresh bid liquidation proceeds after exit displacement and fees; no pending-cash deduction.",
            "final_liquidation_equity": valuation["equity"], "final_complete": valuation["complete"],
            "final_unknown_symbols": valuation["unknown_symbols"], "final_marks": valuation["marks"],
            "running_peak_equity": self.peak_equity, "equity_floor": self.peak_equity - DRAWDOWN_AMOUNT,
            "max_observed_drawdown_dollars": self.max_observed_drawdown,
            "full_intraday_drawdown": None, "observed_drawdown_is_lower_bound": True,
            "threshold_observed": self.breached, "guard_latched": self.guard_enabled and self.breached,
            "breach_at": replay._iso(self.breach_at) if self.breach_at is not None else None,
            "breach_equity": self.breach_equity, "breach_floor": self.breach_floor,
            "maximum_observed_overshoot": max(_ZERO, self.max_observed_drawdown - DRAWDOWN_AMOUNT),
            "sample_count": self.equity_samples, "unknown_sample_count": self.unknown_samples,
            "unknown_interval_count": len(intervals),
            "unknown_duration_seconds": sum(interval["duration_seconds"] for interval in intervals),
            "unknown_intervals": intervals, "events": self.equity_events,
            "limitations": ["Observed-threshold control does not guarantee a $100 maximum loss; gaps, delays and liquidity can overshoot.",
                "Unknown held marks cancel pending entries and block new risk; they do not invent liquidation prices or force an unvalued exit.",
                "Historical halt coverage and original receipts remain unavailable; fresh quote valuation is conditional, not verified executable value.",
                "Equity observation adds no market-wide universe, holdout validation, live deployment or paper orders.",
                "Passive mode observes the threshold but leaves every frozen execution and planning behavior unchanged."]})


def run_catalog_guarded(catalog_path: Path, config: dict, dates: Optional[list] = None, *,
                        guard_enabled: bool = True) -> dict:
    """Stream immutable development sessions with an optional offline risk guard."""
    if type(guard_enabled) is not bool:
        raise ValueError("guard_enabled must be boolean.")
    if calibration.replay_source_sha256() != calibration.PINNED_REPLAY_SHA256:
        raise ValueError("Pinned replay engine hash differs; research adapter requires review.")
    catalog = calibration_data.load_catalog(catalog_path)
    selected = calibration._dates(dates if dates is not None else
        [entry["date"] for entry in catalog["sessions"] if entry["partition"] == "development"], "Requested dates")
    entries = {entry["date"]: entry for entry in catalog["sessions"]}
    if set(selected) - set(entries) or any(entries[day]["partition"] != "development" for day in selected):
        raise ValueError("Requested sessions must be declared development dates; sealed holdouts are unavailable.")
    metadata = deepcopy(catalog.get("dataset_metadata"))
    if (not isinstance(metadata, dict) or metadata.get("schema_version") != 1
            or (metadata.get("source"), metadata.get("feed")) != ("alpaca", "sip")
            or metadata.get("symbols") != catalog["symbols"]):
        raise ValueError("Catalog replay metadata/provenance differs from its cohort.")
    configured = replay._config(config, catalog["symbols"])
    if replay._d(configured["account"]["initial_cash"]) != INITIAL_CAPITAL:
        raise ValueError("This registered risk observer requires the $1000 engineering account.")
    if configured["costs"]["stop_slippage"] != configured["costs"]["target_slippage"]:
        raise ValueError("Frozen replay requires equal exit displacement.")
    metadata["sessions"] = []
    engine = _GuardedReplay(metadata, configured, guard_enabled)
    completed, previous_close = [], None
    for session in calibration_data.iter_sessions(catalog_path, selected):
        if len(completed) >= len(selected) or session.get("date") != selected[len(completed)]:
            raise ValueError("Session iterator differs from requested chronological dates.")
        previous_close = calibration._validate_session(session, catalog["symbols"], previous_close)
        engine._session(session)
        completed.append(session["date"])
        del session
    if completed != selected:
        raise ValueError("Session iterator omitted requested dates.")
    result = engine.run()
    result["summary"]["sessions"] = len(completed)
    result["streaming"] = {"adapter_version": MODEL_ID, "engine_sha256": calibration.PINNED_REPLAY_SHA256,
        "catalog_sha256": catalog["catalog_sha256"], "session_dates": completed,
        "session_hashes": {day: entries[day]["sha256"] for day in completed},
        "state_policy": "One pinned replay subclass across sessions; observer and guard are separately versioned research additions."}
    result["dataset_fingerprint"] = replay._fingerprint(result["streaming"])
    result["equity_report"] = engine.equity_report()
    result.pop("run_fingerprint", None)
    result["run_fingerprint"] = replay._fingerprint(result)
    return result
