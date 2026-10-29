"""Pure, deterministic post-alert research planning; never places orders.

The intraday-research-v1 specification is deliberately uncalibrated. Monetary
arithmetic uses Decimal; JSON numbers are emitted only at the output boundary.
Tick size, adverse execution displacement and affine fees are explicit research
assumptions. A stop is a scenario price, not a guaranteed loss limit.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR, localcontext
import re
from typing import Any, Dict, Optional


DEFAULT_POLICY = {
    "atr_period": 14,
    "breakout_bars": 5,
    "stop_atr_multiple": 1.5,
    "reward_multiple": 2,
    "chase_atr_multiple": 0.25,
    "hold_minutes": 15,
    "entry_valid_seconds": 120,
    "close_buffer_seconds": 300,
    "min_net_rr": 1.5,
    "participation_rate": 0.01,
    "quote_capacity_fraction": 0.25,
    "tick_size": 0.01,
}
_CONTEXT_DOLLARS = (
    "equity", "cash", "risk_budget", "day_risk_remaining",
    "portfolio_risk_remaining", "max_position_notional", "gross_notional_remaining",
)
_CONTEXT_FIELDS = set(_CONTEXT_DOLLARS) | {"as_of", "positions"}
_COST_FIELDS = (
    "entry_fixed", "entry_per_share", "exit_fixed", "exit_per_share",
    "entry_slippage", "stop_slippage", "target_slippage",
)
_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9./-]{0,14}\Z")
_LIMIT = Decimal("1e15")
_PRICE_LIMIT = Decimal("1e9")
# JSON numbers lose decimal detail; this floor preserves ticks at the price cap.
_MINIMUM_TICK = Decimal("0.000001")
_ZERO = Decimal(0)


def default_plan_settings() -> Dict[str, Any]:
    """Return independent research defaults; do not invent costs or an account."""
    return {"policy": deepcopy(DEFAULT_POLICY), "context": None, "costs": None}


def _number(value: Any, name: str, maximum: Decimal = _LIMIT) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError("{} must be a finite nonnegative number.".format(name))
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, OverflowError):
        raise ValueError("{} must be a finite nonnegative number.".format(name)) from None
    if not number.is_finite() or number < 0 or number > maximum:
        raise ValueError("{} must be finite and between 0 and {}.".format(name, maximum))
    return number


def _timestamp(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or len(value) > 50:
        raise ValueError("{} must be an ISO timestamp with a timezone.".format(name))
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError()
        return stamp.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise ValueError("{} must be an ISO timestamp with a timezone.".format(name)) from None


def _validate_policy(policy: Dict[str, Any]) -> None:
    ranges = {
        "stop_atr_multiple": (0, 10, False), "reward_multiple": (0, 10, False),
        "chase_atr_multiple": (0, 2, True), "min_net_rr": (0, 10, False),
        "participation_rate": (0, 0.1, False),
        "quote_capacity_fraction": (0, 1, False), "tick_size": (0, 1, False),
    }
    for key, (low, high, inclusive) in ranges.items():
        value = _number(policy[key], key)
        if value > Decimal(str(high)) or (value < low if inclusive else value <= low):
            raise ValueError("{} is outside its supported research range.".format(key))
    if _number(policy["tick_size"], "tick_size") < _MINIMUM_TICK:
        raise ValueError("tick_size must be at least 0.000001 for JSON price representability.")
    for key, expected in (("atr_period", 14), ("breakout_bars", 5)):
        if type(policy[key]) is not int or policy[key] != expected:
            raise ValueError("{} must equal {}.".format(key, expected))
    for key, low, high in (("entry_valid_seconds", 1, 300), ("close_buffer_seconds", 0, 900)):
        if type(policy[key]) is not int or not low <= policy[key] <= high:
            raise ValueError("{} must be an integer from {} to {}.".format(key, low, high))
    if type(policy["hold_minutes"]) is not int or policy["hold_minutes"] not in (5, 15, 30):
        raise ValueError("hold_minutes must be 5, 15 or 30.")


def validate_plan_settings(payload: Any, current: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Validate partial settings, merging objects but replacing positions whole.

    Missing account/cost fields remain missing and disable sizing. Numeric
    magnitudes above 1e15 are unsupported, a resource/serialization bound.
    The research tick must be at least 0.000001 so JSON numbers preserve
    price geometry up to the supported 1e9 market-price bound.
    """
    if not isinstance(payload, dict) or set(payload) - {"policy", "context", "costs"}:
        raise ValueError("Plan settings support only policy, context and costs.")
    result = default_plan_settings() if current is None else validate_plan_settings(current)
    for key, fields in (("policy", set(DEFAULT_POLICY)), ("context", _CONTEXT_FIELDS),
                        ("costs", set(_COST_FIELDS))):
        if key not in payload:
            continue
        value = payload[key]
        if value is None and key != "policy":
            result[key] = None
            continue
        if not isinstance(value, dict) or set(value) - fields:
            raise ValueError("{} contains unsupported settings.".format(key))
        result[key] = dict(result[key] or {}, **deepcopy(value))
    _validate_policy(result["policy"])
    context = result["context"]
    if context is not None:
        for key in _CONTEXT_DOLLARS:
            if context.get(key) is not None:
                _number(context[key], "context." + key)
        if context.get("equity") is not None:
            equity = _number(context["equity"], "context.equity")
            if equity <= 0:
                raise ValueError("context.equity must be positive.")
            for key in _CONTEXT_DOLLARS:
                if context.get(key) is not None and _number(context[key], key) > equity:
                    raise ValueError("context.{} cannot exceed equity.".format(key))
        if context.get("as_of") is not None:
            _timestamp(context["as_of"], "context.as_of")
        positions = context.get("positions")
        if positions is not None:
            if not isinstance(positions, dict) or len(positions) > 10000:
                raise ValueError("context.positions must be a complete symbol-to-share object.")
            for symbol, quantity in positions.items():
                if not isinstance(symbol, str) or not _SYMBOL.fullmatch(symbol):
                    raise ValueError("context.positions contains an invalid symbol.")
                if type(quantity) is not int or not 0 <= quantity <= _LIMIT:
                    raise ValueError("Position quantities must be nonnegative whole shares.")
    if result["costs"] is not None:
        for key, value in result["costs"].items():
            if value is not None:
                _number(value, "costs." + key)
    return _json_numbers(result)


def _json_numbers(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _json_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_numbers(item) for item in value]
    return value


def _floor(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


def _down(value: Decimal, tick: Decimal) -> Decimal:
    return Decimal(_floor(value / tick)) * tick


def _up(value: Decimal, tick: Decimal) -> Decimal:
    return (value / tick).to_integral_value(rounding=ROUND_CEILING) * tick


def _base(inputs: Any, policy: Dict[str, Any]) -> Dict[str, Any]:
    inputs = inputs if isinstance(inputs, dict) else {}
    return {
        "schema_version": 1, "model_id": "intraday-research-v1", "research_only": True,
        "calibration_status": "unvalidated", "symbol": inputs.get("symbol"),
        "source": inputs.get("source"), "feed": inputs.get("feed"),
        "as_of": inputs.get("decision_at"), "expires_at": None, "status": "unavailable",
        "levels": dict.fromkeys(("atr", "entry_trigger", "entry_max", "stop",
                                 "target_at_trigger", "target_at_max", "hold_minutes")),
        "sizing": {"quantity": None, "notional_max": None, "risk_reserved": None,
                   "cash_required": None, "robust_net_rr": None, "limiting_caps": {}},
        "policy": deepcopy(policy), "reasons": [],
        "warnings": [
            "Research only: these parameters have not been fitted or validated for trading.",
            "Tick size is a research rounding assumption, not a verified venue increment.",
            "Holding time is a maximum from the first fill, not a forecast of a price peak.",
            "Stops, quote capacity and execution costs are hypothetical; fills and losses are not guaranteed.",
        ],
    }


def _validated_market(inputs: Dict[str, Any]) -> Any:
    """Defend the pure public boundary as well as the upstream normalizer."""
    if inputs.get("schema_version") != 1 or type(inputs.get("schema_version")) is not int:
        raise ValueError("Unsupported planning input schema.")
    if not isinstance(inputs.get("symbol"), str) or not _SYMBOL.fullmatch(inputs["symbol"]):
        raise ValueError("Invalid planning symbol.")
    if (inputs.get("source"), inputs.get("feed")) not in (("alpaca", "sip"), ("alpaca", "iex"), ("demo", "synthetic")):
        raise ValueError("Planning source and feed must have supported provenance.")
    if inputs.get("eligible") is not True:
        raise ValueError("Instrument eligibility is unavailable or ineligible.")
    if inputs.get("halted") is True:
        raise ValueError("The instrument is halted.")
    now = _timestamp(inputs.get("decision_at"), "decision_at")
    opened = _timestamp(inputs.get("session_open"), "session_open")
    closed = _timestamp(inputs.get("session_close"), "session_close")
    if not opened <= now < closed:
        raise ValueError("Decision must be within the regular exchange session.")
    raw = inputs.get("minutes")
    if not isinstance(raw, list) or not 15 <= len(raw) <= 10000:
        raise ValueError("At least 15 completed contiguous minute bars are required for minute ATR.")
    bars = []
    previous = None
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Each minute bar must be an object.")
        stamp = _timestamp(item.get("t"), "minute.t")
        if stamp.second or stamp.microsecond or stamp < opened or stamp + timedelta(minutes=1) > now:
            raise ValueError("Minute bars must be completed, aligned and within the decision session.")
        if previous is not None and stamp - previous != timedelta(minutes=1):
            raise ValueError("Minute bars must be ordered, unique and contiguous.")
        values = {key: _number(item.get(key), "minute." + key, _PRICE_LIMIT)
                  for key in ("open", "high", "low", "close")}
        if min(values.values()) <= 0 or values["low"] > min(values["open"], values["close"]) or values["high"] < max(values["open"], values["close"]):
            raise ValueError("Minute OHLC prices must be positive and consistent.")
        values["volume"] = _number(item.get("volume"), "minute.volume")
        bars.append(values)
        previous = stamp
    if not 0 <= (now - previous - timedelta(minutes=1)).total_seconds() <= 120:
        raise ValueError("Latest completed minute is more than 120 seconds old at the decision.")
    quote = inputs.get("quote")
    if not isinstance(quote, dict):
        raise ValueError("A contemporaneous normalized quote is required.")
    if (type(quote.get("schema_version")) is not int or quote.get("schema_version") != 1
            or quote.get("source") != inputs.get("source") or quote.get("feed") != inputs.get("feed")):
        raise ValueError("Quote schema or provenance does not match the alert.")
    event = _timestamp(quote.get("event_at"), "quote.event_at")
    received = _timestamp(quote.get("received_at"), "quote.received_at")
    if not event <= received <= now or not 0 <= (now - event).total_seconds() <= 5 or not 0 <= (now - received).total_seconds() <= 5:
        raise ValueError("Quote timestamps must be ordered and within five seconds of the decision.")
    bid = _number(quote.get("bid"), "quote.bid", _PRICE_LIMIT)
    ask = _number(quote.get("ask"), "quote.ask", _PRICE_LIMIT)
    if not 0 < bid <= ask:
        raise ValueError("Quote prices must be positive and not crossed.")
    return now, closed, bars, quote, ask


def _no_trade(result: Dict[str, Any], reason: str) -> Dict[str, Any]:
    result["status"] = "no_trade"
    result["sizing"].update(quantity=0, notional_max=0, risk_reserved=0, cash_required=0)
    result["reasons"].append(reason)
    return _json_numbers(result)


def build_trade_plan(inputs: Any, settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build a hypothetical long-only intraday plan without clocks, I/O or orders.

    All quotes and minute bars are decision-time observations. The normalized
    input's validity gate is mandatory; account freshness uses that same time.
    """
    settings = validate_plan_settings({} if settings is None else settings)
    result = _base(inputs, settings["policy"])
    if not isinstance(inputs, dict):
        result["reasons"].append("Planning inputs must be an object.")
        return result
    for warning in inputs.get("warnings", []) if isinstance(inputs.get("warnings"), list) else []:
        if isinstance(warning, str) and warning not in result["warnings"]:
            result["warnings"].append(warning)
    if inputs.get("valid") is not True:
        blockers = inputs.get("blockers")
        result["reasons"] = [item for item in blockers if isinstance(item, str)] if isinstance(blockers, list) else []
        if not result["reasons"]:
            result["reasons"].append("Decision-time market inputs are unavailable or invalid.")
        return result
    try:
        with localcontext() as decimal_context:
            decimal_context.prec = 50
            return _calculate(inputs, settings, result)
    except (ValueError, InvalidOperation, OverflowError, ZeroDivisionError) as error:
        result["status"] = "unavailable"
        result["sizing"].update(quantity=None, notional_max=None, risk_reserved=None, cash_required=None)
        result["reasons"].append(str(error) or "Planning inputs could not be evaluated.")
        return _json_numbers(result)


def _calculate(inputs: Dict[str, Any], settings: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    now, closed, bars, quote, ask = _validated_market(inputs)
    if inputs.get("halted") is not False:
        result["warnings"].append("Halt status is unknown; a current quote does not establish trading eligibility at execution.")
    policy = settings["policy"]
    p = {key: Decimal(str(value)) for key, value in policy.items()}
    ranges = [max(bar["high"] - bar["low"], abs(bar["high"] - prior["close"]),
                  abs(bar["low"] - prior["close"])) for prior, bar in zip(bars, bars[1:])]
    atr = sum(ranges[:14], _ZERO) / 14
    for true_range in ranges[14:]:
        atr = (13 * atr + true_range) / 14
    if atr <= 0:
        raise ValueError("Minute ATR must be positive.")
    breakout = max(bar["high"] for bar in bars[-5:])
    tick = p["tick_size"]
    trigger = Decimal(_floor(breakout / tick) + 1) * tick
    maximum = _down(trigger + p["chase_atr_multiple"] * atr, tick)
    stop = _down(trigger - p["stop_atr_multiple"] * atr, tick)

    def target(entry: Decimal) -> Decimal:
        return _up(entry + p["reward_multiple"] * (entry - stop), tick)

    if not 0 < stop < trigger <= maximum < target(maximum):
        raise ValueError("The assumed price increment produces invalid entry/stop/target geometry.")
    # Validate the numbers that callers actually receive, not only their exact
    # Decimal precursors. A collapsed breakout must never produce a sized plan.
    levels = _json_numbers({"atr": atr, "entry_trigger": trigger, "entry_max": maximum,
                            "stop": stop, "target_at_trigger": target(trigger),
                            "target_at_max": target(maximum), "hold_minutes": policy["hold_minutes"]})
    if (not levels["entry_trigger"] > float(breakout)
            or not 0 < levels["stop"] < levels["entry_trigger"] <= levels["entry_max"] < levels["target_at_max"]
            or not levels["target_at_trigger"] > levels["entry_trigger"]):
        raise ValueError("Price geometry cannot be represented safely as JSON numbers.")
    result["levels"].update(levels)
    expiry = min(now + timedelta(seconds=policy["entry_valid_seconds"]),
                 closed - timedelta(seconds=policy["close_buffer_seconds"], minutes=policy["hold_minutes"]))
    result["expires_at"] = expiry.isoformat()
    if expiry <= now:
        result["status"] = "expired"
        result["reasons"].append("There is insufficient session time for the holding limit and closing buffer.")
        return _json_numbers(result)

    missing = []
    context, costs = settings["context"], settings["costs"]
    if context is None or any(context.get(key) is None for key in _CONTEXT_FIELDS):
        missing.append("A complete, explicitly confirmed account context is required for numeric sizing.")
    elif not 0 <= (now - _timestamp(context["as_of"], "context.as_of")).total_seconds() <= 300:
        missing.append("Account context is stale or future-dated; confirm it within five minutes of the decision.")
    if costs is None or any(costs.get(key) is None for key in _COST_FIELDS):
        missing.append("Explicit entry/exit fees and execution displacement assumptions are required for numeric sizing.")
    if len(bars) < 20:
        missing.append("Twenty completed minute volumes are required for numeric liquidity sizing.")
    sizes = []
    if quote.get("size_unit") == "shares" and isinstance(quote.get("size_basis"), str) and quote["size_basis"].strip():
        for key in ("bid_size_shares", "ask_size_shares"):
            if quote.get(key) is None:
                break
            sizes.append(_number(quote[key], "quote." + key))
    if len(sizes) != 2:
        missing.append("Verified bid and ask sizes in shares are required for numeric liquidity sizing.")
    if missing:
        result["status"] = "levels_only"
        result["reasons"].extend(missing)
        return _json_numbers(result)
    if context["positions"].get(inputs["symbol"], 0) > 0:
        return _no_trade(result, "An existing position in this symbol prevents a second entry.")
    c = {key: Decimal(str(value)) for key, value in costs.items()}
    account = {key: Decimal(str(context[key])) for key in _CONTEXT_DOLLARS}
    fixed = c["entry_fixed"] + c["exit_fixed"]
    per_share = c["entry_per_share"] + c["exit_per_share"]
    stop_execution = max(_ZERO, stop - c["stop_slippage"])
    # This lower bound covers ALL accepted entry prices and partial quantities.
    # At q=1 fixed costs/share are greatest; at E_trigger the reward/risk ratio
    # is smallest. Upward target rounding can only improve this bound.
    numerator = p["reward_multiple"] * (trigger - stop) - c["target_slippage"] - per_share - fixed
    denominator = trigger - stop_execution + per_share + fixed
    robust_rr = numerator / denominator
    result["sizing"]["robust_net_rr"] = robust_rr
    if numerator <= 0 or robust_rr < p["min_net_rr"]:
        return _no_trade(result, "The conservative reward/risk bound fails for permitted entry prices or partial fills.")

    risk_budget = min(account["risk_budget"], account["day_risk_remaining"], account["portfolio_risk_remaining"])
    risk_cap = max(0, _floor((risk_budget - fixed) / (maximum - stop_execution + per_share)))
    cash_cap = max(0, _floor((account["cash"] - c["entry_fixed"]) / (maximum + c["entry_per_share"])))
    notional_cap = max(0, _floor(min(account["max_position_notional"], account["gross_notional_remaining"]) / maximum))
    volumes = sorted(bar["volume"] for bar in bars[-20:])
    median_volume = (volumes[9] + volumes[10]) / 2
    liquidity_cap = max(0, _floor(min(p["participation_rate"] * median_volume,
                                    p["quote_capacity_fraction"] * sizes[0],
                                    p["quote_capacity_fraction"] * sizes[1])))
    caps = {"risk": risk_cap, "cash": cash_cap, "notional": notional_cap, "liquidity": liquidity_cap}
    result["sizing"]["limiting_caps"] = caps
    quantity = min(caps.values())
    if quantity <= 0:
        return _no_trade(result, "Risk, cash, notional or observed liquidity capacity is exhausted.")
    result["sizing"].update(quantity=quantity, notional_max=quantity * maximum,
                            risk_reserved=quantity * (maximum - stop_execution + per_share) + fixed,
                            cash_required=quantity * (maximum + c["entry_per_share"]) + c["entry_fixed"])
    if ask < trigger:
        result["status"] = "wait"
        result["reasons"].append("The observed ask is below the entry trigger; wait for a qualifying breakout.")
    elif ask + c["entry_slippage"] > maximum:
        result["status"] = "wait"
        result["reasons"].append("The observed ask plus assumed entry displacement exceeds the entry cap.")
    else:
        result["status"] = "conditional"
        result["reasons"].append("The observed ask fits the conditional entry range under the stated assumptions.")
    return _json_numbers(result)
