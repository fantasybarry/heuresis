"""Planner integration checks use disposable databases and invented market data."""

import copy
from datetime import datetime, timedelta, timezone
import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from nomisma.planner import evaluate_plan, freeze_plan
from nomisma.planning_data import capture_planning_quote
from nomisma.server import Application, make_handler
from nomisma.trade_plan import default_plan_settings


def alert_fixture():
    opening = datetime(2025, 5, 14, 13, 30, tzinfo=timezone.utc)
    decision = opening + timedelta(minutes=30, seconds=1)
    chart = [{"t": (opening + timedelta(minutes=i)).isoformat(), "open": 1.98,
              "high": 2., "low": 1.96, "close": 1.98, "volume": 20000} for i in range(30)]
    row = {"symbol": "FIXTURE", "source": "demo", "feed": "synthetic", "session_date": "2025-05-14",
           "decision_at": decision.isoformat(), "alert_eligible": True, "signal": "Buy", "signal_score": 75,
           "signal_bar_at": chart[-1]["t"], "chart": chart, "price": 2.01, "reasons": [],
           "trading_status": {"halted": False},
           "planning_quote": capture_planning_quote({"bp": 2., "ap": 2.01, "bs": 1000, "as": 1000,
               "t": decision.isoformat(), "_received_at": decision.isoformat()}, "demo", "synthetic")}
    return {"id": "fixture", "symbol": "FIXTURE", "source": "demo", "feed": "synthetic", "level": "Buy",
            "created_at": datetime.now(timezone.utc).isoformat(), "market_time": chart[-1]["t"],
            "session_date": row["session_date"], "snapshot": row,
            "session": {"date": row["session_date"], "open": opening.isoformat(),
                        "close": (opening + timedelta(hours=6, minutes=30)).isoformat()},
            "acknowledged": False}


def account():
    return {"equity": 10000, "cash": 2000, "risk_budget": 25, "day_risk_remaining": 100,
            "portfolio_risk_remaining": 100, "max_position_notional": 1000,
            "gross_notional_remaining": 2000, "positions": {}}


def costs():
    return {"entry_fixed": 0, "entry_per_share": .002, "exit_fixed": 0, "exit_per_share": .002,
            "entry_slippage": 0, "stop_slippage": .01, "target_slippage": .005}


class PlannerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = Application(self.temp.name, seed=False)
        self.addCleanup(self.app.monitor.close)

    def save_fixture(self, settings=None):
        alert = alert_fixture()
        alert["trade_plan"] = freeze_plan(alert, settings or default_plan_settings())
        self.app.store.save_monitor_alert(alert, {})
        return alert

    def test_settings_confirmation_is_explicit_complete_and_not_renewed_by_policy(self):
        for payload in ({"context": account()}, {"confirm_context": True, "context": {"cash": 100}}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.app.planner.save_settings(payload)
        self.assertIsNone(self.app.planner.settings()["context"])
        saved = self.app.planner.save_settings({"context": account(), "confirm_context": True})["settings"]
        confirmed = saved["context"]["as_of"]
        later = self.app.planner.save_settings({"policy": {"hold_minutes": 5}})["settings"]
        self.assertEqual(later["context"]["as_of"], confirmed)
        self.assertIsNone(self.app.planner.save_settings({"context": None})["settings"]["context"])

    def test_original_model_remains_immutable_after_settings_and_outcomes_change(self):
        alert = self.save_fixture()
        original = copy.deepcopy(alert["trade_plan"])
        self.app.planner.save_settings({"policy": {"hold_minutes": 5}})
        self.app.store.update_monitor_outcomes(alert["id"], {})
        self.assertEqual(self.app.planner.alert_plan(alert["id"])["plan"], original)
        self.assertNotIn("trade_plan", self.app.store.monitor_alerts()[0])
        self.assertEqual(self.app.store.monitor_alert(alert["id"])["trade_plan"], original)

    def test_legacy_alert_has_no_reconstructed_original_model(self):
        alert = alert_fixture()
        self.app.store.save_monitor_alert(alert, {})
        result = self.app.planner.alert_plan(alert["id"])
        self.assertIsNone(result["plan"])
        self.assertIn("cannot be reconstructed", result["message"])
        self.assertIsNone(self.app.planner.alert_plan("missing"))

    def test_demo_sizing_uses_explicit_fresh_hypothetical_context_without_mutation(self):
        settings = self.app.planner.save_settings({"context": account(), "confirm_context": True,
                                                  "costs": costs()})["settings"]
        original = copy.deepcopy(settings)
        alert = self.save_fixture(settings)
        result = alert["trade_plan"]["result"]
        self.assertEqual(result["sizing"]["quantity"], 200)
        self.assertEqual(result["sizing"]["robust_net_rr"], 1.5)
        self.assertEqual(settings, original)
        self.assertEqual(alert["trade_plan"]["settings"], original)
        self.assertTrue(any("not historical account evidence" in note for note in result["warnings"]))
        self.assertEqual(result, evaluate_plan(alert, settings))

    def test_demo_does_not_renew_stale_or_future_account_context(self):
        alert = alert_fixture()
        wall_time = datetime.fromisoformat(alert["created_at"])
        for delta in (-301, 1):
            settings = default_plan_settings()
            settings.update(context=dict(account(), as_of=(wall_time + timedelta(seconds=delta)).isoformat()), costs=costs())
            result = evaluate_plan(alert, settings)
            self.assertEqual(result["status"], "levels_only", delta)
            self.assertIsNone(result["sizing"]["quantity"])

    def test_current_analysis_is_separate_and_requires_matching_connected_monitor(self):
        alert = self.save_fixture()
        monitor = self.app.monitor
        with self.assertRaisesRegex(ValueError, "Start"):
            self.app.planner.analyze({"alert_id": alert["id"]})
        monitor.status.update(running=True, connection="demo")
        monitor.bundle = {"source": "demo", "feed": "synthetic", "session": alert["session"]}
        monitor.rows = [copy.deepcopy(alert["snapshot"])]
        with patch.object(monitor, "_refresh_rows"):
            result = self.app.planner.analyze({"alert_id": alert["id"]})
            self.assertEqual(result["plan"]["kind"], "current_reanalysis")
            self.assertEqual(result["plan"]["result"]["status"], "levels_only")
            self.assertEqual(self.app.store.monitor_alert(alert["id"])["trade_plan"], alert["trade_plan"])
            monitor.rows[0]["signal"] = "Watch"
            self.assertEqual(self.app.planner.analyze({"alert_id": alert["id"]})["plan"]["result"]["status"], "unavailable")
            monitor.bundle["feed"] = "sip"
            with self.assertRaisesRegex(ValueError, "source and feed"):
                self.app.planner.analyze({"alert_id": alert["id"]})

    def test_new_confirmed_alert_automatically_freezes_model_and_planner_failure_keeps_alert(self):
        alert = alert_fixture()
        self.app.monitor.bundle = {"session": alert["session"]}
        config = dict(self.app.monitor.config, confirmation_bars=1)
        self.app.monitor._evaluate_alerts([alert["snapshot"]], config)
        saved = self.app.store.monitor_alerts(include_evidence=True)[0]
        self.assertEqual(saved["trade_plan"]["result"]["levels"]["entry_trigger"], 2.01)
        self.assertTrue(saved["trade_plan"]["result"]["research_only"])
        row = copy.deepcopy(alert["snapshot"])
        row["symbol"] = "FAILURE"
        with patch("nomisma.monitor.freeze_plan", side_effect=ValueError("fixture failure")):
            self.app.monitor._evaluate_alerts([row], config)
        saved = next(item for item in self.app.store.monitor_alerts(include_evidence=True) if item["symbol"] == "FAILURE")
        self.assertIn("planning_error", saved)
        self.assertNotIn("trade_plan", saved)

    def test_backup_roundtrip_preserves_model_and_rejects_tampered_calculation(self):
        alert = self.save_fixture()
        content = self.app.store.backup()
        self.app.restore_workspace(content)
        self.assertEqual(self.app.planner.alert_plan(alert["id"])["plan"], alert["trade_plan"])
        self.assertIs(self.app.planner.monitor, self.app.monitor)
        path = Path(self.temp.name) / "tampered.sqlite3"
        path.write_bytes(content)
        changed = copy.deepcopy(alert)
        changed["trade_plan"]["result"]["levels"]["stop"] = 999
        with sqlite3.connect(str(path)) as db:
            db.execute("UPDATE monitor_alerts SET payload=? WHERE id=?", (json.dumps(changed), alert["id"]))
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.app.store.restore_backup(path.read_bytes())
        self.assertEqual(self.app.store.monitor_alert(alert["id"])["trade_plan"], alert["trade_plan"])

    def test_stream_quote_receipt_is_original_arrival_not_later_render(self):
        monitor = self.app.monitor
        now = datetime(2026, 9, 15, 14, tzinfo=timezone.utc)
        monitor.status.update(running=True, connection="live")
        monitor.bundle = {"source": "alpaca", "feed": "sip", "session": {"date": "2026-09-15",
            "open": "2026-09-15T13:30:00Z", "close": "2026-09-15T20:00:00Z"}, "assets": [{"symbol": "FIXTURE"}]}
        event = {"T": "q", "S": "FIXTURE", "bp": 2., "ap": 2.01, "bs": 1000, "as": 1000,
                 "t": "2026-09-15T13:59:59Z"}
        with patch("nomisma.monitor.utcnow", return_value=now):
            monitor._on_event(event, monitor.config, monitor.generation, monitor.stop_event)
        quote = monitor.bundle["assets"][0]["snapshot"]["latestQuote"]
        self.assertEqual(quote["_received_at"], now.isoformat())
        self.assertNotIn("_received_at", event)

    def test_http_planner_routes_validate_origin_and_payload(self):
        alert = self.save_fixture()
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.app))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def request(path, payload=None, origin=None):
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            try:
                headers = {"Content-Type": "application/json"}
                if origin:
                    headers["Origin"] = origin
                connection.request("POST" if payload is not None else "GET", path,
                                   json.dumps(payload) if payload is not None else None, headers)
                response = connection.getresponse()
                return response.status, response.read()
            finally:
                connection.close()
        try:
            status, data = request("/api/planner/alerts/" + alert["id"])
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(data)["plan"], alert["trade_plan"])
            self.assertEqual(request("/api/planner/settings", {"context": account()})[0], 400)
            self.assertEqual(request("/api/planner/settings", {"policy": {"hold_minutes": 5}}, "https://example.com")[0], 403)
            self.assertEqual(request("/api/planner/analyze", {"symbol": "FIXTURE"})[0], 400)
            self.assertEqual(request("/api/planner/alerts/missing")[0], 404)
            self.assertEqual(request("/planner.js")[0], 200)
            self.assertEqual(request("/planner.css")[0], 200)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)
