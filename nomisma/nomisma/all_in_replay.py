"""Cash-only requested sizing and three causal exit policies, offline only.

This additive experiment deliberately removes financial-risk sizing, planning
liquidity caps and the account drawdown latch. Settled funding, one daily entry,
actual future quote capacity and initial entry-quality gates remain explicit.
"""

from bisect import bisect_right
from copy import deepcopy
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, localcontext
import math
from pathlib import Path
from typing import Optional

from . import calibration, calibration_data, cash_replay, replay, trade_plan
from .cash_calendar import load_calendar
from .monitor_metrics import build_rows
from .planning_data import capture_planning_quote


MODEL_ID = "all-in-settled-cash-replay-v1"
EXIT_RULES = ("fixed_15m", "breakeven_1atr", "trail_1atr")
PINNED = {
    "replay.py": "d00fde6fbb4a6e543d5f98e2b585d7f96f39427e282ea18e7758b9b8ab452939",
    "research_risk.py": "f39ac4a9361c9862f6d2ad2460b09ae46e85ae6d3f52b0cc4d750d772a65e40b",
    "cash_replay.py": "a1eecfc14dbe5b7afd2242a6d22a439bc60188bc771d9a4bcd46c885bdad66fe",
    "cash_calendar.py": "86eca799d2ce466153d0e24f09485970b288d5cbcdfbf6962a4fff83971e5055",
    "trade_plan.py": "a71f3361615e2793e2b072a5e9ef1c98ab032b5e2346a63afa1a742dbd943d65",
}
IGNORED_ACCOUNT_FIELDS = ("risk_per_trade", "daily_loss_allowance", "portfolio_risk_limit",
                          "max_position_notional", "gross_notional_limit")
_ZERO = Decimal(0)
NS, MINUTE = replay.NS, replay.MINUTE
_ns, _iso, _d, _json = replay._ns, replay._iso, replay._d, replay._json
_quote_valid, _confirmation = replay._quote_valid, replay._confirmation


def effective_policy() -> dict:
    return {"account_drawdown_limit": None, "financial_risk_sizing": False,
            "planning_liquidity_cap": False, "actual_quote_capacity_retained": True,
            "sizing_caps": ["available_settled_cash"],
            "ignored_account_fields": list(IGNORED_ACCOUNT_FIELDS),
            "ignored_planning_policy_fields": ["participation_rate"],
            "quote_capacity_fraction_usage": "Future executable display only; never caps requested quantity.",
            "initial_reward_risk_gate": "Retained initial stop/2R scenario gate; protective exits need not realize 2R.",
            "stable_profit_accepted_configuration": None}


def build_all_in_plan(inputs: dict, policy: dict, costs: dict, context: Optional[dict]) -> dict:
    """Reuse frozen market/geometry validation, then size only by settled cash.

    Passing no account to the frozen geometry function intentionally stops it
    before its financial/liquidity sizing. No invented budgets or quote sizes
    are supplied. The initial robust reward/risk formula is copied unchanged.
    """
    settings = trade_plan.validate_plan_settings({"policy": policy, "costs": costs, "context": None})
    if any(settings["costs"].get(key) is None for key in trade_plan._COST_FIELDS):
        raise ValueError("Complete explicit costs are required.")
    if settings["costs"]["entry_fixed"] != 0 or settings["costs"]["exit_fixed"] != 0:
        raise ValueError("The all-in experiment supports only zero fixed fees.")
    plan = trade_plan.build_trade_plan(inputs, settings)
    plan.update(model_id=MODEL_ID, effective_sizing=effective_policy())
    if plan["status"] in ("unavailable", "expired"):
        return plan
    if context is None:
        plan["status"] = "unavailable"
        plan["reasons"] = ["Complete observed equity and settled-cash funding are unavailable."]
        return plan
    cash = trade_plan._number(context.get("cash"), "available_settled_cash")
    if _ns(context.get("as_of")) != _ns(inputs.get("decision_at")):
        plan["status"] = "unavailable"
        plan["reasons"] = ["Cash context must be computed at the simulated decision time."]
        return plan
    quote = inputs["quote"]
    if (quote.get("size_unit") != "shares" or not quote.get("size_basis")
            or any(type(quote.get(key)) not in (int, float) or not math.isfinite(quote[key]) or quote[key] < 0
                   or int(quote[key]) != quote[key] for key in ("bid_size_shares", "ask_size_shares"))):
        plan["status"] = "unavailable"
        plan["reasons"] = ["Known valid quote share units are required; sizes do not cap requested quantity."]
        return plan
    with localcontext() as decimal_context:
        decimal_context.prec = 50
        c = {key: _d(value) for key, value in settings["costs"].items()}
        p = {key: _d(value) for key, value in settings["policy"].items()}
        trigger, cap, stop = (_d(plan["levels"][key]) for key in ("entry_trigger", "entry_max", "stop"))
        stop_execution = max(_ZERO, stop - c["stop_slippage"])
        per_share = c["entry_per_share"] + c["exit_per_share"]
        numerator = p["reward_multiple"] * (trigger - stop) - c["target_slippage"] - per_share
        denominator = trigger - stop_execution + per_share
        robust_rr = numerator / denominator
        plan["sizing"]["robust_net_rr"] = float(robust_rr)
        plan["reasons"] = []
        if numerator <= 0 or robust_rr < p["min_net_rr"]:
            return trade_plan._no_trade(plan, "The conservative initial reward/risk bound fails for permitted entry prices or partial fills.")
        if trigger > cap - c["entry_slippage"]:
            plan = trade_plan._no_trade(plan, "The admissible ask interval is structurally empty.")
            plan["status"] = "structurally_infeasible_entry"
            return plan
        quantity = max(0, int((cash / (cap + c["entry_per_share"])).to_integral_value(rounding=ROUND_FLOOR)))
        plan["sizing"]["limiting_caps"] = {"cash": quantity}
        if quantity <= 0:
            return trade_plan._no_trade(plan, "Available settled cash cannot fund one whole share and its entry fee.")
        plan["sizing"].update(quantity=quantity, notional_max=quantity * cap,
            risk_reserved=quantity * (cap - stop_execution + per_share),
            cash_required=quantity * (cap + c["entry_per_share"]))
        plan["sizing"]["risk_reservation_usage"] = "Scenario diagnostic only; never an allocation cap or account stop."
        ask = _d(quote["ask"])
        plan["status"] = "conditional" if trigger <= ask and ask + c["entry_slippage"] <= cap else "wait"
        plan["reasons"] = ["Request all affordable whole shares at the entry cap; actual future quote capacity may fill only part."]
        return _json(plan)


class _AllInReplay(cash_replay._CashReplay):
    def __init__(self, dataset: dict, config: dict, calendar, exit_rule: str):
        if exit_rule not in EXIT_RULES:
            raise ValueError("Unknown registered all-in exit rule.")
        super().__init__(dataset, config, calendar, "C_single_max")
        self.exit_rule = exit_rule
        self.guard_enabled = False
        self.protection_events = []

    def _sample(self, reason: str, *, emit: bool = True) -> dict:
        """Observe equity/drawdown without any threshold, budget or latch."""
        value = self._valuation()
        self.equity_samples += 1
        if value["complete"]:
            self.peak_equity = max(self.peak_equity, value["equity"])
            drawdown = self.peak_equity - value["equity"]
            self.max_observed_drawdown = max(self.max_observed_drawdown, drawdown)
            if self.unknown_since is not None:
                self.unknown_intervals.append({"start": _iso(self.unknown_since), "end": _iso(self.now),
                    "duration_seconds": (self.now - self.unknown_since) / NS, "open_at_end": False})
                self.unknown_since = None
        else:
            self.unknown_samples += 1
            if self.unknown_since is None:
                self.unknown_since = self.now
            drawdown = None
        event = _json({"at": _iso(self.now), "reason": reason, "cash": self.cash,
            "liquidation_equity": value["equity"], "complete": value["complete"],
            "peak_equity": self.peak_equity, "drawdown_dollars": drawdown,
            "unknown_symbols": value["unknown_symbols"],
            "positions": {symbol: position["quantity"] for symbol, position in sorted(self.positions.items())}})
        signature = {key: item for key, item in event.items() if key not in ("at", "reason")}
        if emit and (reason != "observed_quote" or signature != self._last_event_signature):
            event["sequence"] = len(self.equity_events) + 1
            self.equity_events.append(event)
            self._last_event_signature = signature
        self._last_valuation = value
        return value

    def _context(self, marks: dict) -> Optional[dict]:
        value = self._sample("decision_context")
        if not value["complete"] or value["equity"] <= 0:
            return None
        return _json({"as_of": _iso(self.now), "equity": value["equity"],
            "cash": self._cash_state()["cash_available"],
            "positions": {symbol: position["quantity"] for symbol, position in self.positions.items()}})

    def _submission_blocker(self, symbol: str, plan: dict) -> Optional[str]:
        levels, quantity = plan["levels"], plan["sizing"]["quantity"]
        if _d(levels["entry_trigger"]) > _d(levels["entry_max"]) - self.costs["entry_slippage"]:
            return "structurally_infeasible_entry"
        choice = self._choice_blocker()
        if choice:
            return choice
        if quantity <= 0:
            return "zero_quantity"
        if quantity * (_d(levels["entry_max"]) + self.costs["entry_per_share"]) > self._cash_state()["cash_available"]:
            return "insufficient_settled_cash"
        if not self._valuation()["complete"]:
            return "unknown_equity"
        return None

    def _enter(self, symbol: str, order: dict, raw: dict, capacity: int) -> None:
        super()._enter(symbol, order, raw, capacity)
        position = self.positions[symbol]
        position.update(exit_rule=self.exit_rule, initial_stop=position["stop"],
                        decision_atr=_d(order["plan"]["levels"]["atr"]),
                        protection_armed=False, highest_observed_bid=None,
                        _entry_ns=self.now)
        choice = self.daily_choices[self._day()]
        choice.update(settled_cash_after=self.settled_cash,
                      requested_cash_reservation=order["_cash_reserved"],
                      requested_cash_fraction=order["_cash_reserved"] / choice["settled_cash_before"],
                      filled_cash_fraction=choice["settled_cash_used"] / choice["settled_cash_before"])
        if self.config["timing"]["quote_delay_seconds"] == 0:
            # Zero-delay observation precedes entry in the frozen raw-quote
            # path. Evaluate this now-existing position without observing twice.
            self._evaluate_exit_quote(symbol, raw)

    def _observe_trigger(self, symbol: str, reason: str, raw: dict) -> None:
        # Frozen raw-event stop/target scheduling is replaced for all three
        # policies. The observer hook below adds observation + routing once.
        return

    def _observe_quote(self, symbol: str, raw: dict) -> None:
        super()._observe_quote(symbol, raw)
        self._evaluate_exit_quote(symbol, raw)

    def _evaluate_exit_quote(self, symbol: str, raw: dict) -> None:
        position = self.positions.get(symbol)
        if position is None or position["exit_reason"] or "_entry_ns" not in position:
            return
        observed = self.observed_quotes[symbol]
        if (not observed["valid"] or observed["event_ns"] < position["_entry_ns"]
                or not 0 <= self.now - observed["event_ns"] <= 5 * NS
                or symbol in self._unknown_basis or symbol in self.frozen_symbols):
            return
        bid = observed["bid"]
        if self.now >= position["_deadline"]:
            self._trigger_exit(symbol, "holding_limit")
        elif bid <= position["stop"]:
            self._trigger_exit(symbol, "initial_stop" if position["stop"] == position["initial_stop"] else "protection_stop", raw["t"])
        elif bid >= position["target"]:
            self._trigger_exit(symbol, "target", raw["t"])
        else:
            old_high = position["highest_observed_bid"]
            position["highest_observed_bid"] = bid if old_high is None else max(old_high, bid)
            if self.exit_rule == "fixed_15m":
                return
            gain = max(_ZERO, bid - self.costs["stop_slippage"]) - self.costs["exit_per_share"] - (position["_entry"] + self.costs["entry_per_share"])
            if not position["protection_armed"] and gain < position["decision_atr"]:
                return
            newly_armed = not position["protection_armed"]
            position["protection_armed"] = True
            tick = _d(self.policy["tick_size"])
            breakeven = ((position["_entry"] + self.costs["entry_per_share"] + self.costs["exit_per_share"] + self.costs["stop_slippage"]) / tick).to_integral_value(rounding=ROUND_CEILING) * tick
            raised = max(position["stop"], breakeven)
            if self.exit_rule == "trail_1atr":
                trailing = ((position["highest_observed_bid"] - position["decision_atr"]) / tick).to_integral_value(rounding=ROUND_FLOOR) * tick
                raised = max(raised, trailing)
            if raised > position["stop"] or newly_armed:
                previous = position["stop"]
                position["stop"] = raised
                self.protection_events.append(_json({"sequence": len(self.protection_events) + 1,
                    "at": _iso(self.now), "quote_event_at": raw["t"], "trade_id": position["id"],
                    "symbol": symbol, "exit_rule": self.exit_rule, "previous_stop": previous,
                    "stop": raised, "frozen_atr": position["decision_atr"], "net_gain_per_share": gain,
                    "highest_observed_bid": position["highest_observed_bid"], "newly_armed": newly_armed}))
                self._snapshot("protective_stop_update", symbol, trade_id=position["id"], stop=raised)
            if bid <= position["stop"]:
                self._trigger_exit(symbol, "protection_stop", raw["t"])

    # Explicitly copied frozen decision seam; only the planner call differs.
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
                    plan = build_all_in_plan(market, self.policy, self.config["costs"], context)
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

    def equity_report(self) -> dict:
        intervals = deepcopy(self.unknown_intervals)
        if self.unknown_since is not None:
            intervals.append({"start": _iso(self.unknown_since), "end": _iso(self.now),
                "duration_seconds": (self.now - self.unknown_since) / NS, "open_at_end": True})
        value = self._valuation()
        return _json({"model_id": MODEL_ID, "account_drawdown_limit": None,
            "account_drawdown_control": "disabled; drawdown is observed and never blocks entries or requests liquidation",
            "final_liquidation_equity": value["equity"], "final_complete": value["complete"],
            "final_unknown_symbols": value["unknown_symbols"], "final_marks": value["marks"],
            "running_peak_equity": self.peak_equity,
            "max_observed_drawdown_dollars": self.max_observed_drawdown,
            "full_intraday_drawdown": None, "observed_drawdown_is_lower_bound": True,
            "sample_count": self.equity_samples, "unknown_sample_count": self.unknown_samples,
            "unknown_interval_count": len(intervals), "unknown_intervals": intervals,
            "unknown_duration_seconds": sum(item["duration_seconds"] for item in intervals),
            "events": self.equity_events,
            "limitations": ["Conditional historical quote marks do not establish continuously known equity or executable liquidation value.",
                "No account loss threshold or guarantee applies; concentrated all-in requested exposure can suffer large losses.",
                "Settled-only buying cash remains separate from economic cash, which includes unsettled receivables and payables."]})

    def cash_report(self) -> dict:
        report = super().cash_report()
        report.update(model_id=MODEL_ID, variant=self.exit_rule,
                      allocation_policy="All affordable whole shares using available settled cash at entry cap plus entry fee.",
                      effective_policy=effective_policy(), selected_configuration=None,
                      stable_profit_accepted_configuration=None)
        return report


def source_hashes() -> dict:
    return cash_replay.source_hashes()


def run_catalog_all_in(catalog_path: Path, config: dict, calendar_path: Path,
                       exit_rule: str = "fixed_15m", dates: Optional[list] = None) -> dict:
    """Stream one predeclared fixed exit policy through settled-cash sessions."""
    identity = source_hashes()
    if any(identity.get(name) != expected for name, expected in PINNED.items()):
        raise ValueError("Frozen all-in dependencies changed; source review required.")
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
        raise ValueError("The registered all-in study starts with $1000 settled cash.")
    if any(configured["policy"][key] != expected for key, expected in
           (("stop_atr_multiple", 1.5), ("reward_multiple", 2), ("hold_minutes", 15), ("entry_valid_seconds", 120))):
        raise ValueError("All three exits require common initial 1.5 ATR/2R/15-minute/120-second entry geometry.")
    if configured["costs"]["stop_slippage"] != configured["costs"]["target_slippage"]:
        raise ValueError("Frozen exit execution requires equal exit displacements.")
    metadata["sessions"] = []
    value = _AllInReplay(metadata, configured, calendar, exit_rule)
    completed, previous_close = [], None
    for session in calibration_data.iter_sessions(catalog_path, selected):
        if len(completed) >= len(selected) or session.get("date") != selected[len(completed)]:
            raise ValueError("Session iterator differs from registered chronology.")
        previous_close = calibration._validate_session(session, catalog["symbols"], previous_close)
        value._session(session)
        completed.append(session["date"])
        del session
    if completed != selected:
        raise ValueError("Session iterator omitted requested dates.")
    result = value.run()
    result.update(model_id=MODEL_ID, exit_rule=exit_rule, effective_policy=effective_policy())
    result["summary"].update(sessions=len(completed), interpretation="Exposed development exit-policy comparison; stable profitability and accepted configuration remain unestablished.")
    result["streaming"] = {"adapter_version": MODEL_ID, "source_sha256": identity,
        "catalog_sha256": catalog["catalog_sha256"], "session_dates": completed,
        "calendar_sha256": calendar.file_sha256,
        "session_hashes": {day: entries[day]["sha256"] for day in completed},
        "state_policy": "Continuous settlement, single-entry allocation and positions; observed drawdown has no account threshold."}
    result["dataset_fingerprint"] = replay._fingerprint(result["streaming"])
    result["cash_account"], result["equity_report"] = value.cash_report(), value.equity_report()
    result["protection_events"] = value.protection_events
    result["stable_profit_accepted_configuration"] = None
    result.pop("run_fingerprint", None)
    result["run_fingerprint"] = replay._fingerprint(result)
    return result
