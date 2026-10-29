import copy
from datetime import datetime, timedelta, timezone
import http.client
from http.server import ThreadingHTTPServer
import json
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from nomisma.monitor import LiveMonitor, MonitorBusy, monitor_csv, timestamp
from nomisma.monitor_metrics import build_rows, demo_bundle
from nomisma.server import Application, make_handler
from nomisma.storage import Store


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.monitor = LiveMonitor(self.store)
        self.addCleanup(self.monitor.close)

    def row(self, minute=0, level="Buy", eligible=True, symbol="DEMO"):
        stamp = datetime(2026, 9, 8, 15, 0, tzinfo=timezone.utc) + timedelta(minutes=minute)
        return {"symbol": symbol, "source": "demo", "feed": "synthetic", "session_date": "2026-09-08",
                "signal_bar_at": stamp.isoformat(), "signal": level, "alert_eligible": eligible,
                "price": 2.35, "signal_score": 85 if level == "Strong buy" else 75,
                "reasons": ["Completed minute close above VWAP"]}

    def test_nanosecond_provider_timestamps_remain_usable_on_python39(self):
        self.assertEqual(timestamp("2026-09-08T15:00:01.123456789Z").microsecond, 123456)
        self.assertIsNone(timestamp(None))

    def evaluate(self, minute, level="Buy", eligible=True):
        self.monitor._evaluate_alerts([self.row(minute, level, eligible)], self.monitor.config)

    def test_confirm_distinct_minutes_then_no_duplicate_notification(self):
        self.evaluate(0)
        self.evaluate(0)
        self.assertEqual(self.store.monitor_alerts(), [])
        self.evaluate(1)
        self.assertEqual(len(self.store.monitor_alerts()), 1)
        for minute in range(2, 15):
            self.evaluate(minute)
        self.assertEqual(len(self.store.monitor_alerts()), 1)

    def test_upgrade_can_alert_inside_cooldown_after_confirmation(self):
        self.evaluate(0)
        self.evaluate(1)
        self.evaluate(2, "Strong buy")
        self.assertEqual(len(self.store.monitor_alerts()), 1)
        self.evaluate(3, "Strong buy")
        self.assertEqual([a["level"] for a in self.store.monitor_alerts()], ["Strong buy", "Buy"])
        self.evaluate(4, "Buy")
        self.assertEqual(len(self.store.monitor_alerts()), 2)

    def test_mixed_buy_then_strong_confirms_buy_before_strong_upgrade(self):
        self.evaluate(0, "Buy")
        self.evaluate(1, "Strong buy")
        self.assertEqual([item["level"] for item in self.store.monitor_alerts()], ["Buy"])
        self.evaluate(2, "Strong buy")
        self.assertEqual([item["level"] for item in self.store.monitor_alerts()], ["Strong buy", "Buy"])

    def test_rearm_requires_reset_and_cooldown(self):
        self.evaluate(0)
        self.evaluate(1)
        self.evaluate(2, "Watch", False)
        self.evaluate(3)
        self.evaluate(4)
        self.assertEqual(len(self.store.monitor_alerts()), 1)
        self.evaluate(5)
        self.assertEqual(len(self.store.monitor_alerts()), 1)
        self.evaluate(6)
        self.assertEqual(len(self.store.monitor_alerts()), 2)

    def test_gap_between_bars_resets_confirmation(self):
        self.evaluate(0)
        self.evaluate(2)
        self.assertEqual(self.store.monitor_alerts(), [])
        self.evaluate(3)
        self.assertEqual(len(self.store.monitor_alerts()), 1)

    def test_stale_and_disabled_alerts_do_not_notify(self):
        self.evaluate(0, eligible=False)
        self.evaluate(1, eligible=False)
        self.assertEqual(self.store.monitor_alerts(), [])
        self.monitor.config["alerts_enabled"] = False
        self.evaluate(2)
        self.evaluate(3)
        self.assertEqual(self.store.monitor_alerts(), [])

    def test_restart_preserves_dedup_and_does_not_auto_start(self):
        self.evaluate(0)
        self.evaluate(1)
        another = LiveMonitor(self.store)
        self.addCleanup(another.close)
        another._evaluate_alerts([self.row(1), self.row(2)], another.config)
        self.assertEqual(len(self.store.monitor_alerts()), 1)
        self.assertFalse(another.snapshot()["status"]["running"])

    def test_legacy_tracker_migrates_only_to_saved_alert_feed(self):
        self.evaluate(0)
        self.evaluate(1)
        state = self.store.get("monitor_alert_tracker")["demo:synthetic:DEMO:2026-09-08"]
        self.store.set("monitor_alert_tracker", {"demo:DEMO:2026-09-08": state})
        another = LiveMonitor(self.store)
        another._evaluate_alerts([self.row(2)], another.config)
        self.assertEqual(self.store.monitor_alerts_total(), 1)
        self.assertIn("demo:synthetic:DEMO:2026-09-08", another.tracker)
        self.assertNotIn("demo:iex:DEMO:2026-09-08", another.tracker)

    def test_alert_acknowledgment_persists(self):
        self.evaluate(0)
        self.evaluate(1)
        identifier = self.store.monitor_alerts()[0]["id"]
        self.store.acknowledge_monitor_alerts(identifier)
        self.assertTrue(Store(self.temp.name).monitor_alerts()[0]["acknowledged"])
        with self.assertRaises(ValueError):
            self.store.acknowledge_monitor_alerts("nonexistent")

    def test_snapshot_scopes_to_configured_source_before_newer_demo_alert_limit(self):
        self.store.save_monitor_alert({"id": "older-real", "source": "alpaca", "feed": "iex",
            "created_at": "2026-09-08T15:00:00+00:00", "snapshot": {"price": 2.5}}, {})
        for number in range(105):
            self.store.save_monitor_alert({"id": "newer-demo-%03d" % number,
                "source": "demo", "feed": "synthetic", "created_at": "2026-09-09T15:00:00+00:00"}, {})
        self.assertEqual(len(self.monitor.snapshot()["alerts"]), 100)
        self.monitor.save_config({"source": "alpaca"})
        for compact in (False, True):
            snapshot = self.monitor.snapshot(compact=compact)
            self.assertFalse(snapshot["status"]["running"])
            self.assertEqual([row["id"] for row in snapshot["alerts"]], ["older-real"])
        self.assertEqual(self.store.monitor_alerts_total(), 106)
        self.assertEqual(self.store.monitor_alert("older-real")["snapshot"], {"price": 2.5})
        self.monitor.save_config({"source": "demo"})
        self.assertTrue(all(row["source"] == "demo" for row in self.monitor.snapshot()["alerts"]))

    def test_configuration_persists_and_live_credentials_are_required(self):
        self.monitor.save_config({"symbols": ["aapl"], "buy_score": 70})
        self.assertEqual(LiveMonitor(self.store).config["symbols"], ["AAPL"])
        with patch("nomisma.monitor.live_provider_status", return_value={"alpaca_configured": False}), self.assertRaisesRegex(ValueError, "not configured"):
            self.monitor.start({"source": "alpaca"})
        self.assertFalse(self.monitor.status["running"])

    def test_changed_stopped_config_clears_old_source_and_rows(self):
        self.monitor.bundle = demo_bundle(["DEMO"])
        self.monitor.status.update(source="demo", feed="synthetic")
        self.assertTrue(self.monitor.snapshot()["rows"])
        self.monitor.save_config({"source": "alpaca", "symbols": ["AAPL"]})
        snapshot = self.monitor.snapshot()
        self.assertEqual(snapshot["status"]["source"], "alpaca")
        self.assertIsNone(snapshot["status"]["feed"])
        self.assertIsNone(snapshot["status"]["session"])
        self.assertEqual(snapshot["rows"], [])

    def test_demo_start_stop_and_old_generation_callbacks(self):
        self.monitor.start({"source": "demo"})
        deadline = time.monotonic() + 2
        while not self.monitor.snapshot()["rows"] and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(self.monitor.snapshot()["rows"])
        with self.assertRaises(MonitorBusy):
            self.monitor.start()
        with self.assertRaises(MonitorBusy):
            self.monitor.save_config({"min_price": 1})
        old_generation, old_stop = self.monitor.generation, self.monitor.stop_event
        self.monitor.stop()
        self.monitor._set_status(old_generation, old_stop, "live", "Incorrect update")
        self.assertEqual(self.monitor.status["connection"], "stopped")
        self.assertTrue(all(not row["alert_eligible"] for row in self.monitor.snapshot()["rows"]))

    def test_manual_float_validation_and_persistence(self):
        value = self.monitor.set_float({"symbol": "AAPL", "shares": 15000000, "as_of": "2025-12-31"})
        self.assertEqual(value["source"], "Manual")
        self.assertEqual(self.store.get("monitor_float_overrides")["AAPL"]["shares"], 15000000)
        for payload in ({"symbol": "AAPL", "shares": -1, "as_of": "2025-12-31"},
                        {"symbol": "AAPL", "shares": float("nan"), "as_of": "2025-12-31"},
                        {"symbol": "AAPL", "shares": 12.5, "as_of": "2025-12-31"},
                        {"symbol": "AAPL", "shares": 12, "as_of": "2999-01-01"}):
            with self.assertRaises(ValueError):
                self.monitor.set_float(payload)
        self.monitor.set_float({"symbol": "AAPL", "shares": None})
        self.assertNotIn("AAPL", self.store.get("monitor_float_overrides"))

    def prepare_stream(self):
        bundle = demo_bundle(["DEMO"], step=3)
        bundle["source"] = "alpaca"
        bundle["feed"] = "iex"
        self.monitor.bundle = bundle
        self.monitor.status.update(running=True, connection="live", source="alpaca", feed="iex")
        self.monitor.config["source"] = "alpaca"
        return bundle, timestamp(bundle["as_of"])

    def wait_for_refresh(self):
        deadline = time.monotonic() + 2
        while self.monitor.snapshot(compact=True)["status"]["refresh"]["state"] == "loading" and time.monotonic() < deadline:
            time.sleep(0.01)
        return self.monitor.snapshot(compact=True)["status"]["refresh"]

    def test_refresh_rejects_stopped_and_connecting_without_starting_or_changing_source(self):
        original = copy.deepcopy(self.monitor.config)
        with patch("nomisma.monitor.load_live_seed") as load, patch("nomisma.monitor.stream_live") as stream:
            with self.assertRaisesRegex(MonitorBusy, "Start monitoring"):
                self.monitor.refresh()
            self.monitor.status.update(running=True, connection="loading")
            with self.assertRaisesRegex(MonitorBusy, "Wait"):
                self.monitor.refresh()
        self.assertEqual(self.monitor.config, original)
        load.assert_not_called()
        stream.assert_not_called()

    def test_explicit_refresh_is_async_and_preserves_stream_events_and_alert_dedup(self):
        bundle, now = self.prepare_stream()
        refreshed = copy.deepcopy(bundle)
        self.monitor.tracker["existing"] = {"bar": "saved"}
        generation, stop = self.monitor.generation, self.monitor.stop_event
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def loading(*args, **kwargs):
            entered.set()
            release.wait(2)
            return refreshed

        with patch("nomisma.monitor.load_live_seed", side_effect=loading) as load, \
                patch("nomisma.monitor.stream_live") as stream:
            result = self.monitor.refresh()
            self.assertEqual(result["status"]["refresh"]["state"], "loading")
            self.assertTrue(entered.wait(1))
            with self.assertRaisesRegex(MonitorBusy, "already running"):
                self.monitor.refresh()
            with patch("nomisma.monitor.utcnow", return_value=now):
                self.monitor._on_event({"T": "t", "S": "DEMO", "t": (now + timedelta(seconds=1)).isoformat(), "p": 3.21},
                                      self.monitor.config, generation, stop)
            release.set()
            self.assertEqual(self.wait_for_refresh()["state"], "completed")
            self.assertTrue(load.call_args.kwargs["refresh"])
        stream.assert_not_called()
        self.assertEqual(bundle["assets"][0]["snapshot"]["latestTrade"]["p"], 3.21)
        self.assertEqual(self.monitor.tracker, {"existing": {"bar": "saved"}})
        self.assertEqual(self.store.monitor_alerts(), [])
        self.assertEqual(self.monitor.generation, generation)
        self.assertIs(self.monitor.stop_event, stop)
        self.assertFalse(stop.is_set())

    def test_stop_cancels_pending_refresh_and_late_result_cannot_install(self):
        bundle, _ = self.prepare_stream()
        fresh = copy.deepcopy(bundle)
        fresh["assets"][0]["float"] = {"shares": 999, "source": "FMP", "as_of": "2025-05-13"}
        original = copy.deepcopy(bundle)
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def loading(*args, **kwargs):
            entered.set()
            release.wait(2)
            finished.set()
            return fresh

        with patch("nomisma.monitor.load_live_seed", side_effect=loading):
            self.monitor.refresh()
            self.assertTrue(entered.wait(1))
            self.monitor.stop()
            release.set()
            self.assertTrue(finished.wait(1))
        self.assertEqual(self.monitor.snapshot()["status"]["refresh"]["state"], "cancelled")
        self.assertEqual(self.monitor.bundle, original)
        self.assertFalse(self.monitor.status["running"])

    def test_refresh_failure_is_sanitized_and_keeps_existing_data(self):
        bundle, _ = self.prepare_stream()
        original = copy.deepcopy(bundle)
        with patch("nomisma.monitor.load_live_seed", side_effect=ValueError("https://provider/?key=private-secret")):
            self.monitor.refresh()
            status = self.wait_for_refresh()
        self.assertEqual(status["state"], "error")
        self.assertNotIn("private-secret", status["error"])
        self.assertEqual(self.monitor.bundle, original)
        self.assertEqual(self.monitor.status["connection"], "live")

    def test_refresh_cannot_replace_current_feed(self):
        bundle, _ = self.prepare_stream()
        wrong = copy.deepcopy(bundle)
        wrong["feed"] = "sip"
        with patch("nomisma.monitor.load_live_seed", return_value=wrong):
            self.monitor.refresh()
            self.assertEqual(self.wait_for_refresh()["state"], "error")
        self.assertEqual(self.monitor.bundle["feed"], "iex")

    def test_provider_subscription_limit_stops_instead_of_reseeding_forever(self):
        from nomisma.live_data import LiveSubscriptionLimit
        bundle, _ = self.prepare_stream()
        with patch("nomisma.monitor.load_live_seed", return_value=bundle) as load, \
                patch("nomisma.monitor.stream_live", side_effect=LiveSubscriptionLimit("Reduce the symbol list.")) as stream:
            self.monitor._worker(self.monitor.config, self.monitor.generation, self.monitor.stop_event)
        self.assertEqual(load.call_count, 1)
        self.assertEqual(stream.call_count, 1)
        self.assertEqual(self.monitor.status["connection"], "error")
        self.assertFalse(self.monitor.status["running"])
        self.assertIn("Reduce", self.monitor.status["error"])

    def test_demo_refresh_keeps_current_minute_and_alert_history(self):
        self.monitor.bundle = demo_bundle(["DEMO"], step=10)
        self.monitor.status.update(running=True, connection="demo")
        original = copy.deepcopy(self.monitor.bundle)
        with patch("nomisma.monitor.load_live_seed") as load:
            self.monitor.refresh()
            self.assertEqual(self.wait_for_refresh()["state"], "completed")
        self.assertEqual(self.monitor.bundle, original)
        self.assertEqual(self.store.monitor_alerts(), [])
        load.assert_not_called()

    def test_compact_fifty_symbol_snapshot_omits_charts_but_detail_keeps_them(self):
        symbols = ["S%s" % index for index in range(50)]
        self.monitor.save_config({"symbols": symbols})
        self.monitor.bundle = demo_bundle(symbols, step=20)
        full = self.monitor.snapshot()
        compact = self.monitor.snapshot(compact=True)
        self.assertEqual(compact["limits"]["max_symbols"], 50)
        self.assertEqual(len(compact["rows"]), 50)
        self.assertLess(len(json.dumps(compact)), len(json.dumps(full)) * 0.3)
        self.assertTrue(all("chart" not in row and "volume_history" not in row for row in compact["rows"]))
        details = self.monitor.row_detail("s0")
        self.assertEqual(details["chart"], full["rows"][0]["chart"])
        details["chart"].clear()
        self.assertTrue(self.monitor.row_detail("S0")["chart"])
        self.assertIsNone(self.monitor.row_detail("UNKNOWN"))

    def test_premarket_volume_continues_across_open_and_corrections_replace_not_add(self):
        bundle, _ = self.prepare_stream()
        asset = bundle["assets"][0]
        opening = timestamp(bundle["session"]["open"])
        premarket = opening - timedelta(minutes=1)
        original = {"t": premarket.isoformat(), "open": 2, "high": 2.1, "low": 1.9, "close": 2, "volume": 600, "vwap": 2}
        asset["minutes"] = []
        asset["snapshot"]["dailyBar"]["t"] = (opening - timedelta(days=1)).isoformat()
        asset["snapshot"]["_extended_day"] = {"volume": 600, "as_of": opening.isoformat(),
            "received_at": opening.isoformat(), "minutes": [original]}
        event = {"T": "b", "S": "DEMO", "t": opening.isoformat(), "o": 2, "h": 2.1, "l": 1.9, "c": 2, "v": 100, "vw": 2}
        now = opening + timedelta(minutes=1)
        with patch("nomisma.monitor.utcnow", return_value=now):
            self.monitor._on_event(event, self.monitor.config, self.monitor.generation, self.monitor.stop_event)
            self.assertEqual(self.monitor.snapshot()["rows"][0]["day_volume"], 700)
            self.monitor._on_event(dict(event, T="u", v=150), self.monitor.config, self.monitor.generation, self.monitor.stop_event)
            current = self.monitor.snapshot()["rows"][0]
            self.assertEqual(current["day_volume"], 750)
            self.assertEqual(current["session_volume"], 150)
            self.monitor._on_event({"T": "d", "S": "DEMO", "t": opening.isoformat(), "v": 900},
                                   self.monitor.config, self.monitor.generation, self.monitor.stop_event)
            self.assertEqual(self.monitor.snapshot()["rows"][0]["day_volume"], 900)
        self.assertEqual(self.store.monitor_alerts(), [])

    def test_refresh_preserves_new_premarket_minutes_and_installs_benchmark_history(self):
        bundle, _ = self.prepare_stream()
        opening = timestamp(bundle["session"]["open"])
        now = opening - timedelta(minutes=1)
        minute = {"t": (now - timedelta(minutes=1)).isoformat(), "open": 2, "high": 2.1,
                  "low": 1.9, "close": 2, "volume": 600, "vwap": 2}
        asset = bundle["assets"][0]
        asset["snapshot"]["_extended_day"] = {"volume": 600, "as_of": now.isoformat(), "received_at": now.isoformat(), "minutes": [minute]}
        refreshed = copy.deepcopy(bundle)
        refreshed["benchmark_bars"] = [{"date": "2025-05-13", "close": 500}]

        def during_request(*args, **kwargs):
            event = {"T": "u", "S": "DEMO", "t": minute["t"], "o": 2, "h": 2.1, "l": 1.9, "c": 2, "v": 700, "vw": 2}
            with patch("nomisma.monitor.time.monotonic", return_value=101), patch("nomisma.monitor.utcnow", return_value=now):
                self.monitor._on_event(event, self.monitor.config, self.monitor.generation, self.monitor.stop_event)
            return refreshed

        with patch("nomisma.monitor.load_live_seed", side_effect=during_request), patch("nomisma.monitor.time.monotonic", return_value=100):
            self.assertTrue(self.monitor._reload_seed(self.monitor.config, self.monitor.generation,
                                                     self.monitor.stop_event, self.monitor.connection_epoch))
        self.assertEqual(asset["snapshot"]["_extended_day"]["volume"], 700)
        self.assertEqual(bundle["benchmark_bars"], refreshed["benchmark_bars"])

    def test_updated_bar_replaces_volume_without_double_counting(self):
        bundle, now = self.prepare_stream()
        original = copy.deepcopy(bundle["assets"][0]["minutes"][-1])
        size = len(bundle["assets"][0]["minutes"])
        event = {"T": "u", "S": "DEMO", "t": original["t"], "o": original["open"], "h": original["high"],
                 "l": original["low"], "c": original["close"], "v": original["volume"] + 7, "vw": original["vwap"]}
        with patch("nomisma.monitor.utcnow", return_value=now):
            self.monitor._on_event(event, self.monitor.config, self.monitor.generation, self.monitor.stop_event)
            self.monitor._on_event(event, self.monitor.config, self.monitor.generation, self.monitor.stop_event)
        minutes = bundle["assets"][0]["minutes"]
        self.assertEqual(len(minutes), size)
        self.assertEqual(minutes[-1]["volume"], original["volume"] + 7)
        self.assertEqual(self.store.monitor_alerts(), [])

    def test_old_trade_cannot_overwrite_newer_price(self):
        bundle, now = self.prepare_stream()
        snapshot = bundle["assets"][0]["snapshot"]
        snapshot["latestTrade"] = {"t": now.isoformat(), "p": 2.5}
        with patch("nomisma.monitor.utcnow", return_value=now):
            self.monitor._on_event({"T": "t", "S": "DEMO", "t": (now-timedelta(seconds=5)).isoformat(), "p": 1.0},
                                   self.monitor.config, self.monitor.generation, self.monitor.stop_event)
        self.assertEqual(snapshot["latestTrade"]["p"], 2.5)

    def test_session_rollover_uses_new_york_day_not_utc_midnight(self):
        bundle, now = self.prepare_stream()
        bundle["session"].update(date="2026-01-06", open="2026-01-06T09:30:00-05:00", close="2026-01-06T16:00:00-05:00")
        after_hours = datetime(2026, 1, 7, 0, 30, tzinfo=timezone.utc)
        event = {"T": "t", "S": "DEMO", "t": after_hours.isoformat(), "p": 2.5}
        with patch("nomisma.monitor.utcnow", return_value=after_hours):
            self.monitor._on_event(event, self.monitor.config, self.monitor.generation, self.monitor.stop_event)
        self.assertEqual(bundle["assets"][0]["snapshot"]["latestTrade"]["t"], event["t"])
        next_day = after_hours + timedelta(hours=12)
        event["t"] = next_day.isoformat()
        with patch("nomisma.monitor.utcnow", return_value=next_day), self.assertRaisesRegex(ValueError, "new trading session"):
            self.monitor._on_event(event, self.monitor.config, self.monitor.generation, self.monitor.stop_event)

    def test_bar_arriving_just_before_lagging_local_clock_ends_its_minute_is_evaluated(self):
        bundle, _ = self.prepare_stream()
        last = bundle["assets"][0]["minutes"][-1]
        stamp = timestamp(last["t"]) + timedelta(minutes=1)
        event = {"T": "b", "S": "DEMO", "t": stamp.isoformat(), "o": last["close"], "h": last["close"],
                 "l": last["close"], "c": last["close"], "v": last["volume"], "vw": last["close"]}
        arrival = stamp + timedelta(minutes=1) - timedelta(milliseconds=100)
        with patch("nomisma.monitor.utcnow", return_value=arrival), patch.object(self.monitor, "_evaluate_alerts") as evaluate:
            self.monitor._on_event(event, self.monitor.config, self.monitor.generation, self.monitor.stop_event)
        self.assertEqual(bundle["assets"][0]["minutes"][-1]["t"], event["t"])
        evaluate.assert_called_once()

    def test_replayed_completed_bars_do_not_trigger_seeded_latest_setup(self):
        bundle, now = self.prepare_stream()
        original = bundle["assets"][0]["minutes"][0]
        event = {"T": "b", "S": "DEMO", "t": original["t"], "o": original["open"], "h": original["high"],
                 "l": original["low"], "c": original["close"], "v": original["volume"], "vw": original["vwap"]}
        self.monitor.config["confirmation_bars"] = 1
        with patch("nomisma.monitor.utcnow", return_value=now):
            self.monitor._on_event(event, self.monitor.config, self.monitor.generation, self.monitor.stop_event)
        self.assertEqual(self.store.monitor_alerts(), [])

    def test_reconnect_pauses_alert_eligibility(self):
        bundle, now = self.prepare_stream()
        self.monitor.status["connection"] = "reconnecting"
        with patch("nomisma.monitor.utcnow", return_value=now):
            snapshot = self.monitor.snapshot()
        self.assertTrue(all(not row["alert_eligible"] for row in snapshot["rows"]))

    def test_reconciliation_repairs_gaps_preserving_newer_stream_events(self):
        bundle, now = self.prepare_stream()
        refreshed = copy.deepcopy(bundle)
        asset = bundle["assets"][0]
        missing = asset["minutes"].pop(4)
        last = asset["minutes"][-1]
        last["volume"] += 99
        last_stamp = timestamp(last["t"])
        asset["snapshot"]["latestTrade"] = {"t": (now + timedelta(seconds=1)).isoformat(), "p": 3.2}
        asset["snapshot"]["_daily_received_at"] = (now + timedelta(seconds=1)).isoformat()
        asset["snapshot"]["dailyBar"]["v"] = 987654
        self.monitor.minute_versions[("DEMO", last_stamp)] = 101
        self.monitor.set_float({"symbol": "DEMO", "shares": 12345, "as_of": "2025-05-13"})
        with patch("nomisma.monitor.load_live_seed", return_value=refreshed), \
             patch("nomisma.monitor.time.monotonic", return_value=100), \
             patch.object(self.monitor.stop_event, "wait", return_value=True):
            self.monitor._reconcile(self.monitor.config, self.monitor.generation, self.monitor.stop_event, self.monitor.connection_epoch)
        self.assertIn(missing, asset["minutes"])
        self.assertEqual(asset["minutes"][-1]["volume"], last["volume"])
        self.assertEqual(asset["snapshot"]["latestTrade"]["p"], 3.2)
        self.assertEqual(asset["snapshot"]["dailyBar"]["v"], 987654)
        self.assertEqual(asset["float"]["shares"], 12345)
        self.assertEqual(self.store.monitor_alerts(), [])

    def test_reconciliation_restores_daily_history_without_rolling_back_inflight_daily_stream(self):
        bundle, now = self.prepare_stream()
        refreshed = copy.deepcopy(bundle)
        bundle["assets"][0]["bars"].pop()
        refreshed["assets"][0]["snapshot"]["dailyBar"]["v"] = 800
        refreshed["assets"][0]["snapshot"]["_received_at"] = (now + timedelta(seconds=2)).isoformat()

        def during_request(*args, **kwargs):
            event = {"T": "d", "S": "DEMO", "t": now.isoformat(), "v": 1000}
            with patch("nomisma.monitor.time.monotonic", return_value=101), patch("nomisma.monitor.utcnow", return_value=now):
                self.monitor._on_event(event, self.monitor.config, self.monitor.generation, self.monitor.stop_event)
            return refreshed

        with patch("nomisma.monitor.load_live_seed", side_effect=during_request), \
             patch("nomisma.monitor.time.monotonic", return_value=100), \
             patch.object(self.monitor.stop_event, "wait", return_value=True):
            self.monitor._reconcile(self.monitor.config, self.monitor.generation, self.monitor.stop_event, self.monitor.connection_epoch)
        self.assertEqual(bundle["assets"][0]["bars"], refreshed["assets"][0]["bars"])
        self.assertEqual(bundle["assets"][0]["snapshot"]["dailyBar"]["v"], 1000)

    def test_refresh_cannot_restore_trade_cancelled_or_corrected_during_request(self):
        for kind, identifier_key in (("x", "i"), ("c", "oi")):
            with self.subTest(event=kind):
                bundle, now = self.prepare_stream()
                snapshot = bundle["assets"][0]["snapshot"]
                snapshot["latestTrade"] = {"t": now.isoformat(), "p": 2.5, "i": 77}
                refreshed = copy.deepcopy(bundle)

                def during_request(*args, **kwargs):
                    event = {"T": kind, "S": "DEMO", "t": now.isoformat(), identifier_key: 77}
                    with patch("nomisma.monitor.time.monotonic", return_value=101), patch("nomisma.monitor.utcnow", return_value=now):
                        self.monitor._on_event(event, self.monitor.config, self.monitor.generation, self.monitor.stop_event)
                    self.assertNotIn("latestTrade", snapshot)
                    return refreshed

                with patch("nomisma.monitor.load_live_seed", side_effect=during_request), \
                        patch("nomisma.monitor.time.monotonic", return_value=100):
                    self.assertTrue(self.monitor._reload_seed(self.monitor.config, self.monitor.generation,
                                                             self.monitor.stop_event, self.monitor.connection_epoch, force=True))
                self.assertNotIn("latestTrade", snapshot)
                self.assertEqual(self.store.monitor_alerts(), [])

    def test_inflight_refresh_preserves_received_trade_and_quote_even_with_later_rest_timestamp(self):
        for kind, field in (("t", "latestTrade"), ("q", "latestQuote")):
            with self.subTest(event=kind):
                bundle, now = self.prepare_stream()
                refreshed = copy.deepcopy(bundle)
                refreshed["assets"][0]["snapshot"][field]["t"] = (now + timedelta(seconds=1)).isoformat()
                event = {"T": kind, "S": "DEMO", "t": now.isoformat(), "p": 3.2, "bp": 3.19, "ap": 3.21}
                accepted_at = now + timedelta(milliseconds=250)
                refresh_at = now + timedelta(seconds=2)
                expected = dict(event, _received_at=accepted_at.isoformat()) if kind == "q" else event
                if kind == "q":
                    refreshed["assets"][0]["snapshot"][field]["_received_at"] = refresh_at.isoformat()

                def during_request(*args, **kwargs):
                    # Equal monotonic clock ticks still count as in-flight.
                    with patch("nomisma.monitor.time.monotonic", return_value=100), patch("nomisma.monitor.utcnow", return_value=accepted_at):
                        self.monitor._on_event(event, self.monitor.config, self.monitor.generation, self.monitor.stop_event)
                    self.assertEqual(bundle["assets"][0]["snapshot"][field], expected)
                    return refreshed

                with patch("nomisma.monitor.load_live_seed", side_effect=during_request), \
                        patch("nomisma.monitor.time.monotonic", return_value=100), \
                        patch("nomisma.monitor.utcnow", return_value=refresh_at):
                    self.assertTrue(self.monitor._reload_seed(self.monitor.config, self.monitor.generation,
                                                             self.monitor.stop_event, self.monitor.connection_epoch))
                # Preserve the entire streamed event and its original quote
                # receipt; refresh must neither remove nor restamp metadata.
                self.assertEqual(bundle["assets"][0]["snapshot"][field], expected)

    def test_refresh_updated_at_never_rolls_back_newer_stream_receipt(self):
        bundle, now = self.prepare_stream()
        refreshed = copy.deepcopy(bundle)
        refreshed["as_of"] = now.isoformat()
        later = now + timedelta(seconds=1)

        def during_request(*args, **kwargs):
            with patch("nomisma.monitor.utcnow", return_value=later):
                self.monitor._on_event({"T": "t", "S": "DEMO", "t": later.isoformat(), "p": 3.2},
                                      self.monitor.config, self.monitor.generation, self.monitor.stop_event)
            return refreshed

        with patch("nomisma.monitor.load_live_seed", side_effect=during_request):
            self.assertTrue(self.monitor._reload_seed(self.monitor.config, self.monitor.generation,
                                                     self.monitor.stop_event, self.monitor.connection_epoch))
        self.assertEqual(self.monitor.status["updated_at"], later.isoformat())
        newer = later + timedelta(seconds=1)
        refreshed["as_of"] = newer.isoformat()
        with patch("nomisma.monitor.load_live_seed", return_value=refreshed):
            self.monitor._reload_seed(self.monitor.config, self.monitor.generation,
                                      self.monitor.stop_event, self.monitor.connection_epoch)
        self.assertEqual(self.monitor.status["updated_at"], newer.isoformat())

    def test_reconciliation_from_old_connection_cannot_replace_new_seed(self):
        bundle, now = self.prepare_stream()
        old = copy.deepcopy(bundle)
        old["assets"][0]["minutes"][-1]["volume"] = 1
        expected = bundle["assets"][0]["minutes"][-1]["volume"]

        def reconnect(*args, **kwargs):
            self.monitor.connection_epoch += 1
            return old

        with patch("nomisma.monitor.load_live_seed", side_effect=reconnect):
            self.monitor._reconcile(self.monitor.config, self.monitor.generation, self.monitor.stop_event, self.monitor.connection_epoch)
        self.assertEqual(bundle["assets"][0]["minutes"][-1]["volume"], expected)

    def test_csv_provenance_and_formula_protection(self):
        row = dict(self.row(), float_source="=BAD()", float_shares=None)
        content = monitor_csv({"rows": [row]}).decode("utf-8-sig")
        self.assertIn("'=BAD()", content)
        self.assertIn("demo,synthetic", content)

    def journal_alert(self):
        self.monitor.config.update(confirmation_bars=1)
        self.monitor.bundle = demo_bundle(["DEMO"], step=10)
        row = build_rows(self.monitor.bundle, self.monitor.config, now=self.monitor.bundle["as_of"])[0]
        self.assertTrue(row["alert_eligible"])
        self.monitor._evaluate_alerts([row], self.monitor.config)
        identifier = self.store.monitor_alerts()[0]["id"]
        return self.store.monitor_alert(identifier), row

    def test_alert_evidence_is_frozen_and_list_omits_heavy_evidence(self):
        alert, row = self.journal_alert()
        self.assertTrue(alert["snapshot"]["confirmation"]["confirmed"])
        self.assertEqual(alert["schema_version"], 1)
        self.assertNotIn("snapshot", self.store.monitor_alerts()[0])
        row["chart"][0]["close"] = 999
        self.monitor.config["min_price"] = 99
        saved = self.store.monitor_alert(alert["id"])
        self.assertEqual(saved["snapshot"], alert["snapshot"])
        self.assertEqual(saved["config"], alert["config"])
        restored = Store(tempfile.mkdtemp(dir=self.temp.name))
        restored.restore_backup(self.store.backup())
        self.assertEqual(restored.monitor_alert(alert["id"]), saved)

    def test_outcomes_use_complete_future_window_and_signal_close(self):
        alert, row = self.journal_alert()
        self.monitor.bundle = demo_bundle(["DEMO"], step=15)
        future = self.monitor.bundle["assets"][0]["minutes"]
        future[49]["low"] = alert["reference_price"] * .5  # signal bar is outside future window
        future[52]["low"] = alert["reference_price"] * .9
        self.monitor.refresh_outcomes()
        detail = self.monitor.alert_detail(alert["id"])
        observed = detail["outcomes"]["5"]
        self.assertEqual(observed["status"], "observed")
        self.assertAlmostEqual(observed["adverse_excursion_pct"], -10)
        self.assertAlmostEqual(observed["close_change_pct"], (future[54]["close"] / alert["reference_price"] - 1) * 100)
        self.assertEqual(detail["outcomes"]["15"]["status"], "pending")
        self.assertEqual(detail["snapshot"], alert["snapshot"])

    def test_outcomes_ignore_future_data_until_it_is_completed(self):
        alert, row = self.journal_alert()
        bundle = demo_bundle(["DEMO"], step=40)
        bundle["as_of"] = demo_bundle(["DEMO"], step=11)["as_of"]
        outcomes = self.monitor._observations(alert, bundle)
        self.assertEqual(outcomes["5"]["status"], "pending")
        self.assertIsNone(outcomes["5"]["close_change_pct"])

    def test_outcome_gap_can_repair_but_feed_and_session_cannot_mix(self):
        alert, row = self.journal_alert()
        bundle = demo_bundle(["DEMO"], step=40)
        original = copy.deepcopy(bundle)
        bundle["assets"][0]["minutes"].pop(52)
        self.assertEqual(self.monitor._observations(alert, bundle)["5"]["status"], "unavailable")
        self.assertEqual(self.monitor._observations(alert, original)["5"]["status"], "observed")
        original["feed"] = "iex"
        self.assertNotEqual(self.monitor._observations(alert, original)["5"]["status"], "observed")
        original["feed"] = "synthetic"
        original["session"]["date"] = "2025-05-15"
        self.assertNotEqual(self.monitor._observations(alert, original)["5"]["status"], "observed")

    def test_outcomes_past_session_close_and_legacy_alerts_are_unavailable(self):
        alert, row = self.journal_alert()
        alert["session"]["close"] = (timestamp(alert["reference_at"]) + timedelta(minutes=10)).isoformat()
        self.assertEqual(self.monitor._observations(alert, self.monitor.bundle)["15"]["status"], "unavailable")
        legacy = dict(alert)
        legacy.pop("reference_price")
        self.assertEqual(self.monitor._observations(legacy, self.monitor.bundle)["5"]["status"], "unavailable")

    def test_optional_channel_evidence_and_status_events_are_retained(self):
        bundle, now = self.prepare_stream()
        event = {"T": "nomisma_subscription", "required": True, "statuses": True, "lulds": False,
                 "checked_at": now.isoformat(), "message": "Optional channel status"}
        self.monitor._on_event(event, self.monitor.config, self.monitor.generation, self.monitor.stop_event)
        self.assertTrue(self.monitor.status["channel_subscriptions"]["statuses"])
        with patch("nomisma.monitor.utcnow", return_value=now):
            self.monitor._on_event({"T": "s", "S": "DEMO", "t": now.isoformat(), "sc": "H", "sm": "Halted"},
                                   self.monitor.config, self.monitor.generation, self.monitor.stop_event)
        self.assertEqual(bundle["assets"][0]["snapshot"]["tradingStatus"]["sc"], "H")


class MonitorHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.app = Application(cls.temp.name, seed=False)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.app))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.app.monitor.close()
        cls.app.stop_event.set()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        cls.temp.cleanup()

    def request(self, path, payload=None, origin=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        headers = {"Content-Type": "application/json"}
        if origin:
            headers["Origin"] = origin
        try:
            connection.request("GET" if payload is None else "POST", path, json.dumps(payload) if payload is not None else None, headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_monitor_status_and_config(self):
        status, body = self.request("/api/monitor")
        self.assertEqual(status, 200)
        self.assertIn("provider_status", body)
        self.assertEqual(self.request("/api/monitor/config", {"buy_score": 999})[0], 400)

    def test_cross_origin_stream_and_mutation_blocked(self):
        self.assertEqual(self.request("/api/monitor/events", origin="https://evil.example")[0], 403)
        self.assertEqual(self.request("/api/monitor/start", {}, origin="https://evil.example")[0], 403)

    def test_sse_has_real_event_framing(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request("GET", "/api/monitor/events")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertIn("text/event-stream", response.getheader("Content-Type"))
            self.assertEqual(response.readline(), b"event: monitor\n")
            payload = response.readline()
            self.assertTrue(payload.startswith(b"data: "))
            self.assertIn("rows", json.loads(payload[6:]))
            self.assertEqual(response.readline(), b"\n")
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
