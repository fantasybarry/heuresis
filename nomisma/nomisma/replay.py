"""Deterministic, offline historical-replay-v1 engineering experiment.

This adapter deliberately models availability; historical provider event times
are not original application receipts. Final historical bars can contain later
revisions. No network, account lookup, live monitor, or broker is used here.
"""

from bisect import bisect_right
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
import hashlib
import heapq
import json
import math
import re
from typing import Any, Dict, Optional

from .monitor_metrics import DEFAULT_MONITOR_CONFIG, build_rows, validate_monitor_config
from .planning_data import capture_planning_quote
from .trade_plan import DEFAULT_POLICY, build_trade_plan, validate_plan_settings


MODEL_ID = "historical-replay-v1"
NS = 1_000_000_000
MINUTE = 60 * NS
_ZERO = Decimal(0)
_STAMP = re.compile(r"^(.*?)(?:\.(\d{1,9}))?(Z|[+-]\d\d:\d\d)$")


def default_replay_config() -> Dict[str, Any]:
    """An explicit artificial account/cost fixture, never user preferences."""
    monitor = deepcopy(DEFAULT_MONITOR_CONFIG)
    monitor.update(source="alpaca", symbols=["FTFT", "SES", "TE"])
    return {
        "model_id": MODEL_ID,
        "monitor": monitor,
        "policy": deepcopy(DEFAULT_POLICY),
        "account": {"initial_cash": 10000, "risk_per_trade": 25,
                    "daily_loss_allowance": 100, "portfolio_risk_limit": 75,
                    "max_position_notional": 1000, "gross_notional_limit": 3000},
        "costs": {"entry_fixed": 0, "exit_fixed": 0,
                  "entry_per_share": .001, "exit_per_share": .001,
                  "entry_slippage": .001, "stop_slippage": .001,
                  "target_slippage": .001},
        "timing": {"bar_delay_seconds": 1, "quote_delay_seconds": 1,
                   "trade_delay_seconds": 1, "routing_delay_seconds": 1},
    }


def _ns(value: str) -> int:
    """Parse UTC nanoseconds without float timestamps or microsecond loss."""
    if not isinstance(value, str):
        raise ValueError("Replay timestamps must be timezone-aware ISO strings.")
    match = _STAMP.fullmatch(value)
    if not match:
        raise ValueError("Replay timestamp must include a timezone and at most nine fractional digits.")
    base, fraction, zone = match.groups()
    try:
        stamp = datetime.fromisoformat(base + zone.replace("Z", "+00:00"))
        delta = stamp.astimezone(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)
    except (ValueError, OverflowError):
        raise ValueError("Invalid replay timestamp.") from None
    return (delta.days * 86400 + delta.seconds) * NS + int((fraction or "").ljust(9, "0"))


def _iso(value: int) -> str:
    seconds, fraction = divmod(value, NS)
    base = datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    return base + ("." + str(fraction).zfill(9).rstrip("0") if fraction else "") + "Z"


def _d(value: Any) -> Decimal:
    return Decimal(str(value))


def _json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _json(item) for key, item in value.items() if not key.startswith("_")}
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    return value


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def _finite(value: Any, positive: bool = False) -> bool:
    return (type(value) in (int, float) and math.isfinite(value)
            and (value > 0 if positive else value >= 0))


def _config(payload: Optional[Dict[str, Any]], symbols: list) -> dict:
    result = default_replay_config()
    result["monitor"]["symbols"] = list(symbols)
    if payload is not None:
        if not isinstance(payload, dict) or set(payload) - set(result):
            raise ValueError("Unsupported replay configuration.")
        for key, value in payload.items():
            if isinstance(result[key], dict):
                if not isinstance(value, dict) or set(value) - set(result[key]):
                    raise ValueError("Unsupported replay {} settings.".format(key))
                result[key].update(deepcopy(value))
            else:
                result[key] = value
    if result["model_id"] != MODEL_ID:
        raise ValueError("Unsupported replay model version.")
    result["monitor"] = validate_monitor_config(result["monitor"])
    if set(result["monitor"]["symbols"]) != set(symbols) or result["monitor"]["source"] != "alpaca":
        raise ValueError("Replay monitor must evaluate the complete Alpaca dataset cohort.")
    validated = validate_plan_settings({"policy": result["policy"], "costs": result["costs"]})
    result["policy"], result["costs"] = validated["policy"], validated["costs"]
    if any(result["costs"][key] != 0 for key in ("entry_fixed", "exit_fixed")):
        raise ValueError("This version supports only the specified zero fixed-fee fixture.")
    if any(not _finite(value) or value > 1e12 for value in result["account"].values()):
        raise ValueError("Account fixture values must be finite nonnegative amounts.")
    if result["account"]["initial_cash"] <= 0:
        raise ValueError("Initial cash must be positive.")
    if any(type(value) is not int or not 0 <= value <= 60 for value in result["timing"].values()):
        raise ValueError("Modeled timing delays must be integer seconds from zero to sixty.")
    return result


def _quote_valid(raw: dict) -> bool:
    # Normal regular-market quote condition. Other codes are preserved in the
    # archive, but must not silently establish executable liquidity.
    conditions = raw.get("c", [])
    return (not raw.get("_invalid_reason") and conditions == ["R"]
            and _finite(raw.get("bp"), True) and _finite(raw.get("ap"), True)
            and raw["bp"] <= raw["ap"]
            and all(_finite(raw.get(key)) and int(raw[key]) == raw[key] for key in ("bs", "as")))


def _records(records: list, kind: str) -> tuple:
    """Stable per-nanosecond snapshot: the last provider ordinal wins."""
    if not isinstance(records, list):
        raise ValueError("{} must be a list.".format(kind))
    ordered = []
    for index, raw in enumerate(records):
        if not isinstance(raw, dict):
            raise ValueError("{} records must be objects.".format(kind))
        ordinal = raw.get("_ordinal", index)
        if type(ordinal) is not int or ordinal < 0:
            raise ValueError("Provider ordinal must be a nonnegative integer.")
        ordered.append((_ns(raw.get("t")), ordinal, index, raw))
    ordered.sort(key=lambda item: item[:3])
    collapsed = []
    for stamp, ordinal, index, raw in ordered:
        if collapsed and collapsed[-1][0] == stamp:
            collapsed[-1] = (stamp, raw)
        else:
            collapsed.append((stamp, raw))
    return [item[0] for item in collapsed], [item[1] for item in collapsed]


def _confirmation(state: dict, row: dict, expected_bar: int, config: dict) -> Optional[str]:
    """Session-scoped monitor confirmation without persistence or wall clock."""
    actual = _ns(row["signal_bar_at"]) if row.get("signal_bar_at") else None
    rank = {"Buy": 1, "Strong buy": 2}.get(row["signal"], 0) if row["alert_eligible"] else 0
    if actual != expected_bar:
        rank = 0
    previous = state.get("bar")
    contiguous = previous is not None and expected_bar - previous == MINUTE
    prior_rank = state.get("candidate_rank", 0)
    for key, required in (("buy_streak", 1), ("strong_streak", 2)):
        state[key] = state.get(key, 0) + 1 if contiguous and rank >= required and prior_rank >= required else int(rank >= required)
    state.update(bar=expected_bar, candidate_rank=rank)
    if rank == 0:
        state["armed"] = True
    required = config["confirmation_bars"]
    confirmed = (2 if rank == 2 and state["strong_streak"] >= required else
                 1 if rank >= 1 and state["buy_streak"] >= required else 0)
    elapsed = expected_bar - state["last_alert_bar"] if "last_alert_bar" in state else 10 ** 30
    if confirmed and (confirmed > state.get("last_alert_rank", 0) or
                      state.get("armed", True) and elapsed >= config["cooldown_seconds"] * NS):
        state.update(last_alert_bar=expected_bar, last_alert_rank=confirmed, armed=False)
        return "Strong buy" if confirmed == 2 else "Buy"
    return None


class _Replay:
    def __init__(self, dataset: dict, config: dict):
        self.dataset, self.config = dataset, config
        self.account = {key: _d(value) for key, value in config["account"].items()}
        self.costs = {key: _d(value) for key, value in config["costs"].items()}
        self.policy = config["policy"]
        self.cash = self.account["initial_cash"]
        self.loss_debits = _ZERO
        self.realized = _ZERO
        self.positions, self.pending, self.marks = {}, {}, {}
        self.orders, self.trades, self.fills, self.ledger, self.decisions = [], [], [], [], []
        self.capacity = {}
        self.quote_rejections = 0
        self.timers = []
        self.timer_sequence = 0
        self.now = 0
        self.frozen_symbols = {}
        self.share_factors = {}

    def _timer(self, stamp: int, kind: str, symbol: str = "", ident: Any = "") -> None:
        self.timer_sequence += 1
        heapq.heappush(self.timers, (stamp, 2 if kind == "decision" else 0,
                                   self.timer_sequence, kind, symbol, ident))

    def _totals(self, marks: Optional[dict] = None) -> tuple:
        pending_cash = sum((order["_cash_reserved"] for order in self.pending.values()), _ZERO)
        risk = sum((order["_risk_reserved"] for order in self.pending.values()), _ZERO)
        risk += sum((position["_risk_per_share"] * position["quantity"] for position in self.positions.values()), _ZERO)
        gross = sum((order["_cap"] * order["quantity"] for order in self.pending.values()), _ZERO)
        for symbol, position in self.positions.items():
            bid = (self.marks if marks is None else marks).get(symbol, {}).get("bid", position["_cap"])
            gross += max(position["_cap"], bid) * position["quantity"]
        return pending_cash, risk, gross

    def _snapshot(self, kind: str, symbol: str = "", **details: Any) -> None:
        pending_cash, risk, gross = self._totals()
        if self.cash < 0 or pending_cash > self.cash or risk < 0:
            raise AssertionError("Replay accounting invariant failed.")
        self.ledger.append(_json({"sequence": len(self.ledger) + 1, "at": _iso(self.now),
            "event": kind, "symbol": symbol or None, "cash": self.cash,
            "cash_reserved": pending_cash, "cash_available": self.cash - pending_cash,
            "scenario_risk_reserved": risk, "gross_exposure": gross,
            "realized_net_pnl": self.realized, "daily_realized_loss_debits": self.loss_debits,
            "positions": {key: value["quantity"] for key, value in sorted(self.positions.items())},
            "pending_symbols": sorted(self.pending), **details}))

    def _context(self, marks: dict) -> Optional[dict]:
        pending_cash, risk, gross = self._totals(marks)
        if any(symbol not in marks or symbol in self.frozen_symbols for symbol in self.positions):
            return None
        equity = self.cash + sum((marks[symbol]["bid"] * position["quantity"]
                                 for symbol, position in self.positions.items()), _ZERO)
        if equity <= 0:
            return None
        values = {"equity": equity, "cash": max(_ZERO, self.cash - pending_cash),
                  "risk_budget": self.account["risk_per_trade"],
                  "day_risk_remaining": max(_ZERO, self.account["daily_loss_allowance"] - self.loss_debits - risk),
                  "portfolio_risk_remaining": max(_ZERO, self.account["portfolio_risk_limit"] - risk),
                  "max_position_notional": self.account["max_position_notional"],
                  "gross_notional_remaining": max(_ZERO, self.account["gross_notional_limit"] - gross)}
        return _json({key: min(value, equity) for key, value in values.items()} | {
            "as_of": _iso(self.now), "positions": {symbol: position["quantity"] for symbol, position in self.positions.items()}})

    def _cancel(self, symbol: str, reason: str) -> None:
        order = self.pending.pop(symbol, None)
        if order is None:
            return
        order.update(status="expired" if reason == "entry_expired" else "cancelled", cancelled_quantity=order["quantity"], terminal_at=_iso(self.now))
        self._snapshot(reason, symbol, order_id=order["id"])

    def _submit(self, symbol: str, plan: dict, decision_id: str) -> None:
        quantity, levels = plan["sizing"]["quantity"], plan["levels"]
        cap, stop = _d(levels["entry_max"]), _d(levels["stop"])
        risk_per_share = cap - max(_ZERO, stop - self.costs["stop_slippage"]) + self.costs["entry_per_share"] + self.costs["exit_per_share"]
        order = {"id": "order-{:06d}".format(len(self.orders) + 1), "decision_id": decision_id,
                 "symbol": symbol, "created_at": _iso(self.now), "quantity": quantity,
                 "active_at": _iso(self.now + self.config["timing"]["routing_delay_seconds"] * NS),
                 "expires_at": plan["expires_at"], "status": "pending", "filled_quantity": 0,
                 "cancelled_quantity": 0, "plan": plan, "_cap": cap,
                 "_active": self.now + self.config["timing"]["routing_delay_seconds"] * NS,
                 "_created": self.now, "_expiry": _ns(plan["expires_at"]),
                 "_cash_reserved": quantity * (cap + self.costs["entry_per_share"]),
                 "_risk_reserved": quantity * risk_per_share, "_risk_per_share": risk_per_share}
        self.orders.append(order)
        self.pending[symbol] = order
        self._timer(order["_expiry"], "expire", symbol, order["id"])
        self._snapshot("entry_reserved", symbol, order_id=order["id"])

    def _bucket(self, symbol: str, side: str, price: Decimal, size: int) -> int:
        key = (symbol, side)
        bucket = self.capacity.get(key)
        if bucket is None or bucket["price"] != price:
            bucket = self.capacity[key] = {"price": price, "consumed": 0}
        total = int((_d(size) * _d(self.policy["quote_capacity_fraction"])).to_integral_value(rounding=ROUND_FLOOR))
        return max(0, total - bucket["consumed"])

    def _consume(self, symbol: str, side: str, quantity: int) -> None:
        self.capacity[(symbol, side)]["consumed"] += quantity

    def _fill(self, symbol: str, side: str, quantity: int, price: Decimal, ident: str, raw: dict) -> str:
        fee = quantity * self.costs["entry_per_share" if side == "buy" else "exit_per_share"]
        fill = {"id": "fill-{:06d}".format(len(self.fills) + 1), "at": _iso(self.now),
                "symbol": symbol, "side": side, "quantity": quantity, "price": price,
                "fee": fee, "parent_id": ident, "quote_event_at": raw["t"],
                "quote_ordinal": raw.get("_ordinal"), "original_received_at": None,
                "execution_basis": "conditional historical quote capacity; zero fill-report latency"}
        self.fills.append(_json(fill))
        return fill["id"]

    def _enter(self, symbol: str, order: dict, raw: dict, capacity: int) -> None:
        quantity = min(order["quantity"], capacity)
        entry = _d(raw["ap"]) + self.costs["entry_slippage"]
        stop = _d(order["plan"]["levels"]["stop"])
        tick = _d(self.policy["tick_size"])
        target = ((entry + _d(self.policy["reward_multiple"]) * (entry - stop)) / tick).to_integral_value(rounding=ROUND_CEILING) * tick
        self.cash -= quantity * (entry + self.costs["entry_per_share"])
        self._consume(symbol, "ask", quantity)
        self.pending.pop(symbol)
        order.update(status="filled" if quantity == order["quantity"] else "partial_ioc", filled_quantity=quantity,
                     cancelled_quantity=order["quantity"] - quantity, terminal_at=_iso(self.now))
        position = {"id": "trade-{:06d}".format(len(self.trades) + 1), "order_id": order["id"],
                    "symbol": symbol, "entry_at": _iso(self.now), "entry_price": entry,
                    "initial_quantity": quantity, "quantity": quantity, "stop": stop,
                    "target": target, "hold_deadline": _iso(self.now + self.policy["hold_minutes"] * MINUTE),
                    "status": "open", "exit_reason": None, "exit_trigger_at": None,
                    "realized_net_pnl": _ZERO, "entry_fee": quantity * self.costs["entry_per_share"],
                    "exit_fees": _ZERO, "exit_fills": [], "_entry": entry, "_cap": order["_cap"],
                    "_risk_per_share": order["_risk_per_share"], "_deadline": self.now + self.policy["hold_minutes"] * MINUTE}
        self.positions[symbol] = position
        self.trades.append(position)
        position["entry_fill_id"] = self._fill(symbol, "buy", quantity, entry, order["id"], raw)
        self._timer(position["_deadline"], "hold", symbol, position["id"])
        self._snapshot("entry_fill", symbol, order_id=order["id"], trade_id=position["id"],
                       filled_quantity=quantity, ioc_cancelled_quantity=order["cancelled_quantity"])

    def _trigger_exit(self, symbol: str, reason: str, quote_event_at: Optional[str] = None) -> None:
        position = self.positions[symbol]
        if position["exit_reason"]:
            return
        delay = self.config["timing"]["routing_delay_seconds"]
        position.update(exit_reason=reason, exit_trigger_at=_iso(self.now),
                        exit_active_at=_iso(self.now + delay * NS), _exit_active=self.now + delay * NS,
                        _exit_trigger=self.now, status="exiting")
        if quote_event_at is not None:
            position["exit_trigger_quote_event_at"] = quote_event_at
        self._snapshot("exit_triggered", symbol, trade_id=position["id"], reason=reason)

    def _observe_trigger(self, symbol: str, reason: str, raw: dict) -> None:
        position = self.positions[symbol]
        if position.get("_trigger_pending"):
            return
        position["_trigger_pending"] = True
        self._timer(self.now + self.config["timing"]["quote_delay_seconds"] * NS,
                    "quote_trigger", symbol, {"trade_id": position["id"],
                    "reason": reason, "quote_event_at": raw["t"]})

    def _control_timer(self, kind: str, symbol: str, ident: Any) -> None:
        if kind == "expire" and self.pending.get(symbol, {}).get("id") == ident:
            self._cancel(symbol, "entry_expired")
        elif kind == "hold" and self.positions.get(symbol, {}).get("id") == ident:
            self._trigger_exit(symbol, "holding_limit")
        elif kind == "quote_trigger" and self.positions.get(symbol, {}).get("id") == ident["trade_id"]:
            self._trigger_exit(symbol, ident["reason"], ident["quote_event_at"])

    def _exit(self, symbol: str, raw: dict, capacity: int) -> None:
        position = self.positions[symbol]
        quantity = min(position["quantity"], capacity)
        if quantity <= 0:
            return
        price = max(_ZERO, _d(raw["bp"]) - self.costs["stop_slippage"])
        # All modeled market exits use the stated 0.001 adverse displacement;
        # reject divergence in config below instead of silently changing this.
        pnl = quantity * (price - position["_entry"] - self.costs["entry_per_share"] - self.costs["exit_per_share"])
        self.cash += quantity * (price - self.costs["exit_per_share"])
        self.realized += pnl
        self.loss_debits += max(_ZERO, -pnl)
        position["realized_net_pnl"] += pnl
        position["exit_fees"] += quantity * self.costs["exit_per_share"]
        position["quantity"] -= quantity
        self._consume(symbol, "bid", quantity)
        position["exit_fills"].append(self._fill(symbol, "sell", quantity, price, position["id"], raw))
        if not position["quantity"]:
            position.update(status="closed", exit_at=_iso(self.now))
            self.positions.pop(symbol)
        self._snapshot("exit_fill", symbol, trade_id=position["id"], quantity=quantity, net_pnl=pnl)

    def _quote(self, symbol: str, raw: dict, opened: int, closed: int) -> None:
        if not _quote_valid(raw):
            self.quote_rejections += 1
            return
        if symbol in self.frozen_symbols:
            return
        bid, ask = _d(raw["bp"]), _d(raw["ap"])
        self.marks[symbol] = {"bid": bid, "at_ns": self.now, "event_at": raw["t"]}
        ask_capacity = self._bucket(symbol, "ask", ask, raw["as"])
        bid_capacity = self._bucket(symbol, "bid", bid, raw["bs"])
        if not opened <= self.now < closed or symbol in self.frozen_symbols:
            return
        position = self.positions.get(symbol)
        if position:
            if position["exit_reason"]:
                if self.now > position["_exit_active"] and self.now > position["_exit_trigger"]:
                    self._exit(symbol, raw, bid_capacity)
            elif bid <= position["stop"]:
                self._observe_trigger(symbol, "stop", raw)
            elif bid >= position["target"]:
                self._observe_trigger(symbol, "target", raw)
            return
        order = self.pending.get(symbol)
        if (order and self.now > order["_active"] and self.now > order["_created"]
                and self.now < order["_expiry"] and ask_capacity > 0
                and ask >= _d(order["plan"]["levels"]["entry_trigger"])
                and ask + self.costs["entry_slippage"] <= order["_cap"]):
            self._enter(symbol, order, raw, ask_capacity)
            if bid <= self.positions[symbol]["stop"]:
                self._observe_trigger(symbol, "stop", raw)

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
                    "as_of": _iso(last_end), "received_at": _iso(last_end + timing["bar_delay_seconds"] * NS), "minutes": minutes}
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
                if symbol in self.positions or symbol in self.pending:
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
                        self._submit(symbol, plan, decision["id"])
                        decision["order_id"] = self.orders[-1]["id"]
            self.decisions.append(_json(decision))

    def _session(self, session: dict) -> None:
        opened, closed = _ns(session["open"]), _ns(session["close"])
        # Pending observations from the preceding session retain their actual
        # modeled timestamps; do not move them to the next opening bell.
        while self.timers and self.timers[0][0] < opened:
            stamp, _, _, kind, symbol, ident = heapq.heappop(self.timers)
            self.now = stamp
            self._control_timer(kind, symbol, ident)
        self.now, self.loss_debits = opened, _ZERO
        self.capacity = {}
        self.session_start_marks = deepcopy(self.marks)
        self._snapshot("session_open", session_date=session["date"])
        streams = {}
        supplied = {asset["symbol"]: asset for asset in session["assets"]}
        for symbol in self.dataset["symbols"]:
            asset = supplied.get(symbol, {})
            qt, quotes = _records(asset.get("quotes", []), "quotes")
            tt, trades = _records(asset.get("trades", []), "trades")
            mt, minutes = _records(asset.get("minutes", []), "minutes")
            quality = asset.get("quality", {})
            data_blockers = list(quality.get("data_blockers", []))
            factor = quality.get("daily_split_to_session_factor")
            if symbol in self.positions and factor != self.share_factors.get(symbol):
                self.frozen_symbols[symbol] = "Unresolved position share basis changed or became unavailable across sessions; no split adjustment is modeled."
            self.share_factors[symbol] = factor
            valid_quotes = [quote for quote in quotes if _quote_valid(quote)]
            streams[symbol] = {"quotes_times": qt, "quotes": quotes, "trades_times": tt,
                               "trades": trades, "minute_times": mt, "minutes": minutes,
                               "data_blockers": data_blockers,
                               "valid_quotes": valid_quotes, "valid_quote_times": [_ns(quote["t"]) for quote in valid_quotes],
                               "daily": [bar for bar in asset.get("daily", []) if bar.get("date", "") < session["date"]]}
        # Bind symbol inside a helper: generator comprehensions otherwise share
        # the enclosing loop variable and corrupt a multi-symbol event stream.
        def events(symbol: str):
            if streams[symbol]["data_blockers"]:
                return
            for index, stamp in enumerate(streams[symbol]["quotes_times"]):
                if opened <= stamp < closed:
                    yield stamp, symbol, index
        quote_events = iter(heapq.merge(*(events(symbol) for symbol in sorted(streams))))
        next_quote = next(quote_events, None)
        delay = self.config["timing"]["bar_delay_seconds"] * NS
        for bar in range(opened, closed, MINUTE):
            decision_at = bar + MINUTE + delay
            self._timer(decision_at, "decision", ident=str(bar))
        self._timer(closed, "session_end")
        horizon = closed + delay
        states = {}
        while next_quote is not None or self.timers and self.timers[0][0] <= horizon:
            timer_time = self.timers[0][0] if self.timers and self.timers[0][0] <= horizon else 10 ** 30
            # Expiry/holding timers precede quotes at equal nanoseconds;
            # minute decisions follow quotes but enforce the receipt cutoff.
            quote_first = (next_quote is not None and (next_quote[0] < timer_time or
                           next_quote[0] == timer_time and self.timers[0][3] == "decision"))
            if quote_first:
                self.now, symbol, index = next_quote
                self._quote(symbol, streams[symbol]["quotes"][index], opened, closed)
                next_quote = next(quote_events, None)
            else:
                stamp, _, _, kind, symbol, ident = heapq.heappop(self.timers)
                self.now = stamp
                if kind == "decision":
                    self._decision(session, streams, states, int(ident))
                elif kind == "session_end":
                    for pending_symbol in list(self.pending):
                        self._cancel(pending_symbol, "session_end_cancel")
                    self._snapshot("session_end", session_date=session["date"], unresolved_symbols=sorted(self.positions))
                else:
                    self._control_timer(kind, symbol, ident)
        self.now = horizon

    def run(self) -> dict:
        for session in self.dataset["sessions"]:
            self._session(session)
        unresolved = []
        for symbol, position in sorted(self.positions.items()):
            mark = None if symbol in self.frozen_symbols else self.marks.get(symbol)
            unresolved.append({"symbol": symbol, "trade_id": position["id"], "quantity": position["quantity"],
                "exit_reason": position["exit_reason"], "last_observed_bid": float(mark["bid"]) if mark else None,
                "last_bid_at": mark["event_at"] if mark else None,
                "mark_age_seconds": (self.now - mark["at_ns"]) / NS if mark else None,
                "reason": self.frozen_symbols.get(symbol, "No admissible quote capacity completed liquidation within the dataset.")})
        closed = [trade for trade in self.trades if trade["status"] == "closed"]
        summary = {"sessions": len(self.dataset["sessions"]), "symbols": self.dataset["symbols"],
            "decisions": len(self.decisions), "alerts": sum(bool(item["alert_level"]) for item in self.decisions),
            "orders": len(self.orders), "entry_fills": sum(item["side"] == "buy" for item in self.fills),
            "exit_fills": sum(item["side"] == "sell" for item in self.fills), "closed_trades": len(closed),
            "expired_orders": sum(item["status"] == "expired" for item in self.orders),
            "partial_entry_orders": sum(item["status"] == "partial_ioc" for item in self.orders),
            "rejected_plans": sum(item["alert_level"] is not None and item["disposition"] not in ("wait", "conditional", "existing_exposure") for item in self.decisions),
            "alerts_blocked_by_exposure": sum(item["disposition"] == "existing_exposure" for item in self.decisions),
            "ineligible_decisions": sum(not item["eligible"] for item in self.decisions),
            "unresolved_positions": len(unresolved), "initial_cash": self.account["initial_cash"],
            "ending_cash": self.cash, "realized_net_pnl": self.realized,
            "total_net_pnl": None if unresolved else self.cash - self.account["initial_cash"],
            "invalid_or_unsupported_quote_snapshots": self.quote_rejections,
            "interpretation": "Engineering fixture only; no profitability or fitted-parameter evidence."}
        result = _json({"schema_version": 1, "model_id": MODEL_ID, "research_only": True,
            "config": self.config, "dataset_fingerprint": _fingerprint(self.dataset),
            "summary": summary, "decisions": self.decisions, "orders": self.orders,
            "trades": self.trades, "fills": self.fills, "ledger": self.ledger, "unresolved": unresolved,
            "warnings": ["Retrospectively selected cohort and sessions; engineering validation only.",
                "Final historical bars may include later revisions; original receipt times and revisions are unavailable.",
                "Historical halt coverage is unknown; quote-capacity fills are conditional assumptions.",
                "Displayed-size replenishment on side-price change, fees, timing and account are artificial fixtures.",
                "No OHLC fills, broker orders, strategy optimization, or live-readiness claim."]})
        result["run_fingerprint"] = _fingerprint(result)
        return result


def run_replay(dataset: dict, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Replay all archived sessions and cohort symbols chronologically, offline."""
    if not isinstance(dataset, dict) or dataset.get("schema_version") != 1:
        raise ValueError("Unsupported replay dataset schema.")
    if dataset.get("source") != "alpaca" or dataset.get("feed") != "sip":
        raise ValueError("This historical pilot requires archived Alpaca SIP provenance.")
    symbols, sessions = dataset.get("symbols"), dataset.get("sessions")
    if not isinstance(symbols, list) or not symbols or len(set(symbols)) != len(symbols):
        raise ValueError("Dataset must declare a unique nonempty symbol cohort.")
    if not isinstance(sessions, list) or not sessions:
        raise ValueError("Dataset must contain sessions.")
    previous_close = None
    for session in sessions:
        if not isinstance(session, dict) or not isinstance(session.get("assets"), list):
            raise ValueError("Each session must contain assets.")
        opened, closed = _ns(session.get("open")), _ns(session.get("close"))
        if opened >= closed or previous_close is not None and opened <= previous_close:
            raise ValueError("Dataset sessions must be unique, chronological and nonoverlapping.")
        if opened % MINUTE or closed % MINUTE:
            raise ValueError("Exchange sessions must align with minute boundaries.")
        previous_close = closed
        if not isinstance(session.get("date"), str) or session["date"] < "2025-11-03":
            raise ValueError("SIP shares convention requires session dates on or after 2025-11-03.")
        asset_symbols = [asset.get("symbol") for asset in session["assets"] if isinstance(asset, dict)]
        if len(asset_symbols) != len(session["assets"]) or len(set(asset_symbols)) != len(asset_symbols) or set(asset_symbols) - set(symbols):
            raise ValueError("Session assets must be unique members of the declared cohort.")
    configured = _config(config, symbols)
    if configured["costs"]["stop_slippage"] != configured["costs"]["target_slippage"]:
        raise ValueError("This market-exit fixture requires equal stop and target displacement.")
    return _Replay(dataset, configured).run()
