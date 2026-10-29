"""Local research planning service; never submits or manages broker orders."""

import copy
import uuid
from datetime import datetime, timezone

from .planning_data import prepare_plan_inputs
from .trade_plan import build_trade_plan, default_plan_settings, validate_plan_settings


def evaluate_plan(alert, settings):
    """Evaluate with a separate, explicitly synthetic account clock for demos.

    A current manual balance is a demo scenario input, never historical account
    evidence. Validate its age against the real alert/request receipt before
    projecting it onto the simulation clock. Original settings remain intact.
    """
    inputs = prepare_plan_inputs(alert)
    evaluation_settings = copy.deepcopy(settings)
    context = evaluation_settings.get("context")
    if inputs.get("source") == "demo" and context:
        try:
            confirmed = datetime.fromisoformat(context["as_of"].replace("Z", "+00:00"))
            received = datetime.fromisoformat(alert["created_at"].replace("Z", "+00:00"))
            age = (received - confirmed).total_seconds()
            if confirmed.tzinfo is None or received.tzinfo is None or not 0 <= age <= 300:
                evaluation_settings["context"] = None
            else:
                context["as_of"] = inputs.get("decision_at")
        except (KeyError, AttributeError, TypeError, ValueError, OverflowError):
            evaluation_settings["context"] = None
    result = build_trade_plan(inputs, evaluation_settings)
    if inputs.get("source") == "demo":
        result["warnings"].append("Demo account assumptions are checked at the real request time and projected onto the simulated session; they are not historical account evidence.")
    return result


def freeze_plan(alert, settings, kind="original_alert"):
    """Keep a reproducible model result separate from the alert's observations."""
    settings = validate_plan_settings(settings)
    return {"schema_version": 1, "analysis_id": uuid.uuid4().hex, "kind": kind,
            "alert_id": alert.get("id"), "settings": copy.deepcopy(settings),
            "result": evaluate_plan(alert, settings)}


class Planner:
    def __init__(self, store, monitor):
        self.store = store
        self.monitor = monitor

    def settings(self):
        return validate_plan_settings(self.store.get("planning_settings", default_plan_settings()))

    def save_settings(self, payload):
        if not isinstance(payload, dict) or set(payload) - {"policy", "context", "costs", "confirm_context"}:
            raise ValueError("Supply planning policy, account context, or cost assumptions.")
        update = copy.deepcopy(payload)
        confirm = update.pop("confirm_context", False)
        if type(confirm) is not bool:
            raise ValueError("Account confirmation must be true or false.")
        if "context" in update and update["context"] is not None:
            if not confirm:
                raise ValueError("Confirm your current cash, positions, and risk budgets when updating account context.")
            if not isinstance(update["context"], dict):
                raise ValueError("Account context must be an object.")
            required = {"equity", "cash", "risk_budget", "day_risk_remaining", "portfolio_risk_remaining",
                        "max_position_notional", "gross_notional_remaining", "positions"}
            if not required <= set(update["context"]) or any(update["context"][key] is None for key in required):
                raise ValueError("Confirm the complete balances, positions, and remaining risk budgets together.")
            # Confirmation is a user action, never an automatic monitor refresh.
            update["context"]["as_of"] = datetime.now(timezone.utc).isoformat()
        elif confirm:
            raise ValueError("Supply the complete account context to confirm it.")
        with self.monitor.lock:
            settings = validate_plan_settings(update, self.settings())
            self.store.set("planning_settings", settings)
        return {"settings": settings}

    def alert_plan(self, identifier):
        alert = self.store.monitor_alert(identifier)
        if alert is None:
            return None
        return {"alert_id": alert["id"], "symbol": alert.get("symbol"),
                "source": alert.get("source"), "feed": alert.get("feed"),
                "plan": alert.get("trade_plan"),
                "viewed_at": datetime.now(timezone.utc).isoformat(),
                "message": None if alert.get("trade_plan") else
                    "This older alert has no original model analysis. Its original plan cannot be reconstructed."}

    def analyze(self, payload):
        if not isinstance(payload, dict) or set(payload) != {"alert_id"} or not isinstance(payload["alert_id"], str):
            raise ValueError("Supply the saved alert_id to analyze its stock using current monitored data.")
        alert = self.store.monitor_alert(payload["alert_id"])
        if alert is None:
            raise ValueError("Saved alert not found.")
        with self.monitor.lock:
            if not self.monitor.status["running"] or self.monitor.status["connection"] not in ("live", "demo"):
                raise ValueError("Start the matching monitor before requesting a current analysis.")
            bundle = self.monitor.bundle
            if not bundle or (bundle["source"], bundle["feed"]) != (alert.get("source"), alert.get("feed")):
                raise ValueError("Current monitor source and feed must match the saved alert.")
            # Recompute with this decision's clock, rather than reuse a cached row.
            self.monitor._refresh_rows()
            row = copy.deepcopy(next((row for row in self.monitor.rows if row["symbol"] == alert["symbol"]), None))
            if row is None:
                raise ValueError("This stock is not currently monitored. Add it to the matching monitor first.")
            if row.get("signal") not in ("Buy", "Strong buy"):
                row["alert_eligible"] = False
            current = {"id": alert["id"], "symbol": alert["symbol"], "source": bundle["source"],
                       "feed": bundle["feed"], "session_date": row.get("session_date"),
                       "level": row.get("signal"), "market_time": row.get("signal_bar_at"),
                       "created_at": datetime.now(timezone.utc).isoformat(),
                       "snapshot": row, "session": copy.deepcopy(bundle["session"])}
            plan = freeze_plan(current, self.settings(), kind="current_reanalysis")
        return {"alert_id": alert["id"], "symbol": alert["symbol"], "source": alert["source"],
                "feed": alert["feed"], "plan": plan,
                "viewed_at": datetime.now(timezone.utc).isoformat(),
                "message": "Current analysis is temporary. The original saved alert and model analysis are unchanged."}
