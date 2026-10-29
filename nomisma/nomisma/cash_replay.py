"""Versioned offline cash-account and single-entry allocation experiment.

The economic cash field includes unsettled receivables. Only settled, unreserved
funds finance entries. The frozen signal, fill and equity-observer sources are
pinned; decision/snapshot seams are copied explicitly to avoid global patches.
"""

from bisect import bisect_right
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
import hashlib
import heapq
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from . import calibration, calibration_data, cash_calendar, replay, research_risk
from .cash_calendar import load_calendar
from .monitor_metrics import build_rows
from .planning_data import capture_planning_quote
from .trade_plan import build_trade_plan

MODEL_ID = "cash-account-replay-v1"
VARIANTS = ("A_cash_legacy", "B_single_legacy", "C_single_max")
PINNED_RISK_SHA256 = "f39ac4a9361c9862f6d2ad2460b09ae46e85ae6d3f52b0cc4d750d772a65e40b"
_ZERO = Decimal(0)
NS, MINUTE = replay.NS, replay.MINUTE
_ns, _iso, _d, _json = replay._ns, replay._iso, replay._d, replay._json
_quote_valid, _confirmation = replay._quote_valid, replay._confirmation


class _CashReplay(research_risk._GuardedReplay):
    def __init__(self, dataset: dict, config: dict, calendar, variant: str):
        if variant not in VARIANTS:
            raise ValueError("Unknown registered cash-account variant.")
        super().__init__(dataset, config, guard_enabled=True)
        self.calendar, self.variant = calendar, variant
        self.settled_cash = self.cash
        self.receivables = []
        self.daily_choices = {}
        self._funding_cancellation = False

    def _day(self) -> str:
        return datetime.fromtimestamp(self.now // NS, ZoneInfo("America/New_York")).date().isoformat()

    def _cash_state(self) -> dict:
        unsettled = sum((item["amount"] for item in self.receivables if item["settled_at"] is None), _ZERO)
        payables = sum((max(_ZERO, -item["amount"]) for item in self.receivables if item["settled_at"] is None), _ZERO)
        reserved = sum((order["_cash_reserved"] for order in self.pending.values()), _ZERO)
        return {"settled_cash": self.settled_cash, "unsettled_cash": unsettled,
                "unsettled_payables": payables, "cash_reserved": reserved,
                "cash_available": max(_ZERO, self.settled_cash - reserved - payables),
                "funding_deficit": max(_ZERO, reserved + payables - self.settled_cash)}

    def _choice_blocker(self) -> Optional[str]:
        if self.variant == "A_cash_legacy":
            return None
        if self.pending:
            return "single_pending_entry"
        if self.positions:
            return "single_open_position"
        if self._day() in self.daily_choices:
            return "daily_entry_already_used"
        return None

    def _submission_blocker(self, symbol: str, plan: dict) -> Optional[str]:
        levels, quantity = plan["levels"], plan["sizing"]["quantity"]
        if _d(levels["entry_max"]) - self.costs["entry_slippage"] < _d(levels["entry_trigger"]):
            return "structurally_infeasible_entry"
        choice = self._choice_blocker()
        if choice:
            return choice
        if symbol in self.pending or symbol in self.positions:
            return "existing_exposure"
        if quantity <= 0:
            return "zero_quantity"
        required = quantity * (_d(levels["entry_max"]) + self.costs["entry_per_share"])
        if required > self._cash_state()["cash_available"]:
            return "insufficient_settled_cash"
        if self.breached or not self._valuation()["complete"]:
            return "drawdown_or_unknown_equity"
        return None

    def _submit(self, symbol: str, plan: dict, decision_id: str) -> None:
        reason = self._submission_blocker(symbol, plan)
        if reason:
            raise ValueError("Rejected before reservation: " + reason)
        super()._submit(symbol, plan, decision_id)

    def _enter(self, symbol: str, order: dict, raw: dict, capacity: int) -> None:
        quantity = min(order["quantity"], capacity)
        cost = quantity * (_d(raw["ap"]) + self.costs["entry_slippage"] + self.costs["entry_per_share"])
        state = self._cash_state()
        if quantity <= 0 or cost > state["cash_available"] + order["_cash_reserved"]:
            raise ValueError("Entry is not covered by its settled-cash reservation.")
        self.settled_cash -= cost
        if self.variant != "A_cash_legacy":
            day = self._day()
            if day in self.daily_choices:
                raise AssertionError("A second daily entry was attempted.")
            self.daily_choices[day] = {"symbol": symbol, "order_id": order["id"],
                "first_fill_at": _iso(self.now), "quantity": quantity,
                "requested_quantity": order["quantity"], "settled_cash_used": cost,
                "settled_cash_before": self.settled_cash + cost}
        super()._enter(symbol, order, raw, capacity)

    def _exit(self, symbol: str, raw: dict, capacity: int) -> None:
        quantity = min(self.positions[symbol]["quantity"], capacity)
        if quantity <= 0:
            return
        day = self._day()
        release = self.calendar.release_at(day)
        if _ns(release) <= self.now:
            raise ValueError("Sale settlement must follow the sale.")
        price = max(_ZERO, _d(raw["bp"]) - self.costs["stop_slippage"])
        item = {"id": "receivable-{:06d}".format(len(self.receivables) + 1),
            "fill_id": "fill-{:06d}".format(len(self.fills) + 1),
            "symbol": symbol, "trade_date": day, "sale_at": _iso(self.now),
            "settlement_date": self.calendar.settlement_date(day), "available_at": release,
            "amount": quantity * (price - self.costs["exit_per_share"]), "settled_at": None}
        self.receivables.append(item)
        self._timer(_ns(release), "cash_settlement", ident=len(self.receivables) - 1)
        super()._exit(symbol, raw, capacity)

    def _control_timer(self, kind: str, symbol: str, ident) -> None:
        if kind == "cash_settlement":
            item = self.receivables[ident]
            if item["settled_at"] is not None or self.now != _ns(item["available_at"]):
                raise AssertionError("Duplicate or mistimed settlement.")
            self.settled_cash += item["amount"]
            item["settled_at"] = _iso(self.now)
            self._snapshot("cash_settlement", item["symbol"], receivable_id=item["id"],
                           fill_id=item["fill_id"], settlement_amount=item["amount"])
        else:
            super()._control_timer(kind, symbol, ident)

    def _snapshot(self, kind: str, symbol: str = "", **details) -> None:
        # Preserve the pinned observer's session/basis ordering. Its parent
        # snapshot cannot express signed fee liabilities or settled buying cash.
        if kind == "session_open" and self._incoming_session is not None:
            supplied = {asset["symbol"]: asset for asset in self._incoming_session["assets"]}
            for held in self.positions:
                quality = supplied.get(held, {}).get("quality", {})
                factor = quality.get("daily_split_to_session_factor")
                if factor is None or factor != self.share_factors.get(held):
                    self._unknown_basis[held] = "Held share basis changed or is unavailable; liquidation valuation is unknown."
                elif quality.get("data_blockers"):
                    self._unknown_basis[held] = "Session data is excluded; held liquidation valuation is unavailable."
            while self.timers and self.timers[0][0] == self.now and self.timers[0][1] < 0:
                _, _, _, timer_kind, timer_symbol, payload = heapq.heappop(self.timers)
                self._control_timer(timer_kind, timer_symbol, payload)
        state = self._cash_state()
        if self.cash != state["settled_cash"] + state["unsettled_cash"]:
            raise AssertionError("Economic cash does not reconcile to settlement balances.")
        _, risk, gross = self._totals()
        if risk < 0 or state["cash_reserved"] < 0:
            raise AssertionError("Negative reservation.")
        self.ledger.append(_json({"sequence": len(self.ledger) + 1, "at": _iso(self.now),
            "event": kind, "symbol": symbol or None, "cash": self.cash, **state,
            "scenario_risk_reserved": risk, "gross_exposure": gross,
            "realized_net_pnl": self.realized, "daily_realized_loss_debits": self.loss_debits,
            "positions": {key: value["quantity"] for key, value in sorted(self.positions.items())},
            "pending_symbols": sorted(self.pending), **details}))
        if state["funding_deficit"] > 0 and self.pending and not self._funding_cancellation:
            self._funding_cancellation = True
            try:
                for pending_symbol in list(self.pending):
                    self._cancel(pending_symbol, "funding_deficit_cancel")
            finally:
                self._funding_cancellation = False
        self._sample("ledger:" + kind)

    def _context(self, marks: dict) -> Optional[dict]:
        if self.variant != "C_single_max":
            context = super()._context(marks)
            if context is not None:
                context["cash"] = float(min(self._cash_state()["cash_available"], _d(context["equity"])))
            return context
        valuation = self._sample("decision_context")
        if not valuation["complete"] or valuation["equity"] <= 0:
            return None
        allowance = _ZERO if self.breached else valuation["new_risk_allowance"]
        equity = valuation["equity"]
        cash = min(self._cash_state()["cash_available"], equity)
        risk = min(allowance, equity)
        return _json({"equity": equity, "cash": cash, "risk_budget": risk,
            "day_risk_remaining": risk, "portfolio_risk_remaining": risk,
            "max_position_notional": cash, "gross_notional_remaining": cash,
            "as_of": _iso(self.now),
            "positions": {symbol: p["quantity"] for symbol, p in self.positions.items()}})

    def _decision(self, session: dict, streams: dict, states: dict, expected_bar: int) -> None:
        assets = []
        decision_marks = deepcopy(self.session_start_marks)
        timing = self.config["timing"]
        for symbol in sorted(streams):
            stream = streams[symbol]
            def latest(kind: str, delay: int) -> Optional[dict]:
                index = bisect_right(stream[kind + "_times"], self.now - delay * NS) - 1
                return stream[kind][index] if index >= 0 else None
            quote, trade = latest("quotes", timing["quote_delay_seconds"]), latest("trades", timing["trade_delay_seconds"])
            if trade and trade.get("_invalid_reason"):
                trade = None
            mark_index = bisect_right(stream["valid_quote_times"], self.now - timing["quote_delay_seconds"] * NS) - 1
            if mark_index >= 0:
                mark = stream["valid_quotes"][mark_index]
                decision_marks[symbol] = {"bid": _d(mark["bp"]), "at_ns": _ns(mark["t"]), "event_at": mark["t"]}
            quote = deepcopy(quote or {})
            if quote:
                quote["_received_at"] = _iso(_ns(quote["t"]) + timing["quote_delay_seconds"] * NS)
            if quote and not _quote_valid(quote):
                quote = {}
            complete_count = bisect_right(stream["minute_times"], self.now - MINUTE - timing["bar_delay_seconds"] * NS)
            minutes = stream["minutes"][:complete_count]
            snapshot = {"latestQuote": quote, "latestTrade": trade or {}}
            if minutes:
                last_end = _ns(minutes[-1]["t"]) + MINUTE
                snapshot["_extended_day"] = {"volume": sum(bar["volume"] for bar in minutes),
                    "as_of": _iso(last_end), "received_at": _iso(last_end + timing["bar_delay_seconds"] * NS)}
            assets.append({"symbol": symbol, "minutes": minutes, "bars": stream["daily"], "snapshot": snapshot})
        bundle = {"source": "alpaca", "feed": "sip", "session": session,
                  "assets": assets, "benchmark_bars": session.get("benchmark_bars", [])}
        rows = build_rows(bundle, self.config["monitor"], now=_iso(self.now))
        asset_map = {asset["symbol"]: asset for asset in assets}
        for row in sorted(rows, key=lambda item: item["symbol"]):
            symbol = row["symbol"]
            blockers = streams[symbol]["data_blockers"]
            if blockers or symbol in self.frozen_symbols:
                row["blockers"] += blockers + ([self.frozen_symbols[symbol]] if symbol in self.frozen_symbols else [])
                row.update(alert_eligible=False, signal="Watch")
            level = _confirmation(states.setdefault(symbol, {}), row, expected_bar, self.config["monitor"])
            decision = {"id": "decision-{:06d}".format(len(self.decisions) + 1), "at": _iso(self.now),
                "session_date": session["date"], "symbol": symbol, "expected_bar_at": _iso(expected_bar),
                "signal_bar_at": row["signal_bar_at"], "signal": row["signal"], "score": row["signal_score"],
                "eligible": row["alert_eligible"], "blockers": row["blockers"], "alert_level": level,
                "confirmation": deepcopy(states[symbol]),
                "disposition": "session_closed" if self.now >= _ns(session["close"]) else "no_alert",
                "inputs": {key: row.get(key) for key in ("price", "price_at", "quote_at", "session_volume", "day_volume", "minute_relative_volume", "vwap", "ema9", "ema20", "rsi")}}
            if level:
                choice_blocker = self._choice_blocker()
                if choice_blocker:
                    decision.update(disposition=choice_blocker, reason=choice_blocker)
                elif symbol in self.positions or symbol in self.pending:
                    decision.update(disposition="existing_exposure", reason="An existing position or pending entry blocks a second entry.")
                else:
                    raw_quote = asset_map[symbol]["snapshot"]["latestQuote"]
                    quote = capture_planning_quote(raw_quote, "alpaca", "sip")
                    market = {"schema_version": 1, "valid": True, "eligible": row["alert_eligible"],
                        "symbol": symbol, "source": "alpaca", "feed": "sip", "halted": None,
                        "decision_at": _iso(self.now), "session_open": session["open"], "session_close": session["close"],
                        "minutes": [{key: bar[key] for key in ("t", "open", "high", "low", "close", "volume")} for bar in row["chart"]],
                        "quote": quote, "warnings": ["Historical replay adapter: quote receipt is modeled as event plus configured delay; original receipt is unknown."]}
                    context = self._context(decision_marks)
                    plan = build_trade_plan(market, {"policy": self.policy, "costs": self.config["costs"], "context": context})
                    decision.update(disposition=plan["status"], plan=plan, account_context=context,
                                    planning_quote={**quote, "original_received_at": None, "receipt_basis": "modeled"},
                                    portfolio_marks={key: {"bid": mark["bid"], "event_at": mark["event_at"], "age_seconds": (self.now - mark["at_ns"]) / NS} for key, mark in decision_marks.items() if key in self.positions})
                    if plan["status"] in ("wait", "conditional") and plan["sizing"]["quantity"]:
                        reason = self._submission_blocker(symbol, plan)
                        if reason:
                            decision.update(disposition=reason, reason=reason)
                        else:
                            self._submit(symbol, plan, decision["id"])
                            decision["order_id"] = self.orders[-1]["id"]
            self.decisions.append(_json(decision))

    def cash_report(self) -> dict:
        return _json({"model_id": MODEL_ID, "variant": self.variant,
            "economic_cash": self.cash, **self._cash_state(),
            "receivables": self.receivables, "daily_choices": self.daily_choices,
            "selection_policy": "First qualifying feasible alert chronologically; alphabetical same-time ties; first positive IOC fill commits the date.",
            "single_entry_enabled": self.variant != "A_cash_legacy",
            "maximum_allocation_enabled": self.variant == "C_single_max",
            "settlement_posting_assumption": "09:30 America/New_York on the provider settlement date; actual broker posting unverified.",
            "cash_definition": "cash/ending_cash are economic cash including signed unsettled proceeds; cash_available is unreserved settled funding after payables.",
            "selected_configuration": None, "acceptance_status": "development_only_insufficient_evidence"})


def source_hashes() -> dict:
    # Include local transitive research/planner dependencies, not just overrides.
    paths = sorted(Path(__file__).parent.glob("*.py"))
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def run_catalog_cash(catalog_path: Path, config: dict, calendar_path: Path,
                     variant: str = "C_single_max", dates: Optional[list] = None) -> dict:
    """Stream existing exposed development sessions, with no network access."""
    identity = source_hashes()
    if (identity["replay.py"] != calibration.PINNED_REPLAY_SHA256 or
            identity["research_risk.py"] != PINNED_RISK_SHA256):
        raise ValueError("Frozen replay or risk observer source changed; review required.")
    calendar = load_calendar(calendar_path)
    catalog = calibration_data.load_catalog(catalog_path)
    selected = calibration._dates(dates if dates is not None else
        [entry["date"] for entry in catalog["sessions"] if entry["partition"] == "development"], "Requested dates")
    entries = {entry["date"]: entry for entry in catalog["sessions"]}
    if set(selected) - set(entries) or any(entries[day]["partition"] != "development" for day in selected):
        raise ValueError("Only declared development sessions are available.")
    calendar.validate_dates(selected)
    metadata = deepcopy(catalog.get("dataset_metadata"))
    if (not isinstance(metadata, dict) or metadata.get("schema_version") != 1
            or (metadata.get("source"), metadata.get("feed")) != ("alpaca", "sip")
            or metadata.get("symbols") != catalog["symbols"]):
        raise ValueError("Catalog metadata differs from its cohort.")
    configured = replay._config(config, catalog["symbols"])
    if _d(configured["account"]["initial_cash"]) != Decimal(1000):
        raise ValueError("The registered cash-account study starts with $1000.")
    if configured["costs"]["stop_slippage"] != configured["costs"]["target_slippage"]:
        raise ValueError("Frozen exit execution requires equal exit displacements.")
    metadata["sessions"] = []
    engine = _CashReplay(metadata, configured, calendar, variant)
    completed, previous_close = [], None
    for session in calibration_data.iter_sessions(catalog_path, selected):
        if len(completed) >= len(selected) or session.get("date") != selected[len(completed)]:
            raise ValueError("Session iterator differs from the registered chronology.")
        previous_close = calibration._validate_session(session, catalog["symbols"], previous_close)
        engine._session(session)
        completed.append(session["date"])
        del session
    if completed != selected:
        raise ValueError("Session iterator omitted requested dates.")
    result = engine.run()
    result["model_id"] = MODEL_ID
    result["summary"]["sessions"] = len(completed)
    result["streaming"] = {"adapter_version": MODEL_ID, "source_sha256": identity,
        "catalog_sha256": catalog["catalog_sha256"], "session_dates": completed,
        "calendar_sha256": hashlib.sha256(Path(calendar_path).read_bytes()).hexdigest(),
        "session_hashes": {day: entries[day]["sha256"] for day in completed},
        "state_policy": "Continuous cash, settlement, positions and peak-drawdown state across development sessions."}
    result["dataset_fingerprint"] = replay._fingerprint(result["streaming"])
    result["cash_account"] = engine.cash_report()
    result["equity_report"] = engine.equity_report()
    result["equity_report"]["model_id"] = MODEL_ID
    result["equity_report"]["valuation"] = "Economic cash includes unsettled net proceeds; holdings use conditional fresh net bids. Settlement does not change equity."
    result["summary"]["interpretation"] = "Exposed development cash-account diagnostics; no parameter acceptance or guaranteed loss ceiling."
    result.pop("run_fingerprint", None)
    result["run_fingerprint"] = replay._fingerprint(result)
    return result
