#!/usr/bin/env python3
"""Reproducible offline engineering checks for the research trade planner.

All market/account values in this tool are invented. This is a scenario replay,
not a historical strategy backtest, parameter fit, or evidence of profitability.
No broker connection, credentials, existing database, or order API is used.
"""

import argparse
import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import platform
try:
    import resource
except ImportError:  # Optional on Windows; arithmetic/HTTP/browser checks still run.
    resource = None
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from nomisma.replay_data import digest, file_sha256  # noqa: E402


def source_hashes():
    paths = sorted(set(ROOT.glob("nomisma/**/*.py")) | set(ROOT.glob("nomisma/static/*"))
                   | set(ROOT.glob("tests/*.py"))
                   | {Path(__file__).resolve(), ROOT / "tools/browser_check.py", ROOT / "tools/build_desktop.py",
                      ROOT / "run.py", ROOT / "launch.py", ROOT / "desktop/host.py", ROOT / "desktop/App.swift"})
    return {str(path.relative_to(ROOT)): file_sha256(path)
            for path in paths if path.is_file()}


def synthetic_alert(count=30):
    """Independent flat-range example: minute TR=.04 and five-minute high=2.

    Original receipt/event times are explicit. Quotes use synthetic share
    quantities, so provider-dependent historical lot conventions cannot leak
    into this example. The intentionally invented symbol is never fetched.
    """
    from nomisma.planning_data import capture_planning_quote
    opening = datetime(2026, 9, 15, 13, 30, tzinfo=timezone.utc)
    decision = opening + timedelta(minutes=count, seconds=1)
    bars = [{"t": (opening + timedelta(minutes=index)).isoformat(),
             "open": 1.98, "high": 2.0, "low": 1.96, "close": 1.98,
             "volume": 20000} for index in range(count)]
    quote = capture_planning_quote({
        "bp": 2.00, "ap": 2.01, "bs": 1000, "as": 1000,
        "t": (decision - timedelta(milliseconds=500)).isoformat(),
        "_received_at": (decision - timedelta(milliseconds=100)).isoformat(),
    }, "demo", "synthetic")
    return {
        "id": "synthetic-planner-check", "symbol": "FIXTURE", "source": "demo",
        "feed": "synthetic", "session_date": "2026-09-15", "level": "Buy",
        "created_at": decision.isoformat(), "market_time": bars[-1]["t"],
        "session": {"date": "2026-09-15", "open": opening.isoformat(),
                    "close": (opening + timedelta(hours=6, minutes=30)).isoformat()},
        "snapshot": {"symbol": "FIXTURE", "source": "demo", "feed": "synthetic",
                     "session_date": "2026-09-15", "signal": "Buy", "alert_eligible": True,
                     "signal_bar_at": bars[-1]["t"], "decision_at": decision.isoformat(),
                     "trading_status": {"halted": False}, "chart": bars,
                     "planning_quote": quote},
    }


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def synthetic_settings(alert):
    from nomisma.trade_plan import default_plan_settings
    settings = default_plan_settings()
    settings["context"] = {
        "as_of": alert["snapshot"]["decision_at"], "equity": 10000, "cash": 2000,
        "risk_budget": 25, "day_risk_remaining": 100, "portfolio_risk_remaining": 100,
        "max_position_notional": 1000, "gross_notional_remaining": 2000, "positions": {},
    }
    settings["costs"] = {"entry_fixed": 0, "entry_per_share": .002,
                         "exit_fixed": 0, "exit_per_share": .002,
                         "entry_slippage": 0, "stop_slippage": .01, "target_slippage": .005}
    return settings


def check_arithmetic(result):
    expected_levels = {"atr": .04, "entry_trigger": 2.01, "entry_max": 2.02,
                       "stop": 1.95, "target_at_trigger": 2.13, "target_at_max": 2.16,
                       "hold_minutes": 15}
    for key, expected in expected_levels.items():
        check(result["levels"][key] == expected, "Incorrect independent arithmetic: " + key)
    expected_sizing = {"quantity": 200, "notional_max": 404, "risk_reserved": 16.8,
                       "cash_required": 404.4, "robust_net_rr": 1.5}
    for key, expected in expected_sizing.items():
        check(result["sizing"][key] == expected, "Incorrect independent sizing: " + key)
    check(result["sizing"]["limiting_caps"] == {"risk": 297, "cash": 989,
                                               "notional": 495, "liquidity": 200},
          "Independent share caps differ")
    # Enumerate every allowed entry tick and whole-share partial quantity.
    # These are scenario calculations, not simulated executions or P&L.
    observed_rr = []
    for entry, target in ((Decimal("2.01"), Decimal("2.13")),
                          (Decimal("2.02"), Decimal("2.16"))):
        for quantity in range(1, 201):
            loss = quantity * (entry - Decimal("1.94") + Decimal(".004"))
            reward = quantity * (target - entry - Decimal(".005") - Decimal(".004"))
            cash = quantity * (entry + Decimal(".002"))
            check(loss <= Decimal("16.8"), "Partial fill exceeds reserved modeled loss")
            check(cash <= Decimal("404.4"), "Partial fill exceeds reserved cash")
            observed_rr.append(reward / loss)
    check(min(observed_rr) == Decimal("1.5"), "Partial-fill reward/risk floor differs")


def run_checks(report):
    from nomisma.planning_data import prepare_plan_inputs
    from nomisma.trade_plan import build_trade_plan, default_plan_settings
    alert = synthetic_alert()
    original = digest(alert)
    inputs = prepare_plan_inputs(alert)
    check(inputs["valid"], "Independent synthetic original evidence should validate: " + str(inputs["blockers"]))
    settings = synthetic_settings(alert)
    result = build_trade_plan(inputs, settings)
    check(result == build_trade_plan(copy.deepcopy(inputs), copy.deepcopy(settings)), "Model results must be deterministic")
    check(digest(alert) == original, "Preprocessing/model must not mutate original evidence")
    check(result["research_only"] is True, "Planner must remain research only")
    check(result["calibration_status"] == "unvalidated", "Synthetic evidence must not mark calibration complete")
    check(result["status"] == "conditional", "Valid synthetic scenario should be conditional")
    check_arithmetic(result)
    report["fixture"] = {"raw_alert": alert, "inputs": inputs, "settings": settings, "result": result}
    report["deterministic_result_sha256"] = digest(result)
    report["checks"].append("independent raw alert -> preprocessing -> deterministic research model output")
    report["checks"].append("independent Decimal arithmetic and all 400 entry/partial-fill combinations")
    report["scenarios"] = []

    def scenario(name, expected, change_alert=None, change_settings=None):
        raw, config = copy.deepcopy(alert), copy.deepcopy(settings)
        if change_alert:
            change_alert(raw)
        if change_settings:
            change_settings(config)
        value = build_trade_plan(prepare_plan_inputs(raw), config)
        report["scenarios"].append({"name": name, "expected_status": expected,
                                     "result": value, "input_sha256": digest(raw)})
        check(value["status"] == expected, name + ": expected " + expected + ", got " + value["status"])
        check(value["research_only"] and value["calibration_status"] == "unvalidated",
              name + ": research/calibration boundary changed")
        if expected in ("unavailable", "levels_only", "expired"):
            check(value["sizing"]["quantity"] is None, name + ": numeric sizing should be unavailable")
        if expected == "no_trade":
            check(value["sizing"]["quantity"] == 0, name + ": rejected scenario must not carry a position")

    scenario("threshold rejects worse trigger-price ratio", "no_trade",
             change_settings=lambda s: s["policy"].update(min_net_rr=1.55))
    scenario("fixed fees reject one-share partial risk ratio", "no_trade",
             change_settings=lambda s: s["costs"].update(entry_fixed=.01))
    scenario("risk budget exhausted", "no_trade", change_settings=lambda s: s["context"].update(risk_budget=0))
    scenario("cash exhausted", "no_trade", change_settings=lambda s: s["context"].update(cash=0))
    scenario("existing position prevents duplicate entry", "no_trade",
             change_settings=lambda s: s["context"]["positions"].update(FIXTURE=1))
    scenario("cost assumptions absent", "levels_only", change_settings=lambda s: s.update(costs=None))
    scenario("account context absent", "levels_only", change_settings=lambda s: s.update(context=None))
    scenario("stale account context", "levels_only",
             change_settings=lambda s: s["context"].update(as_of="2026-09-15T13:55:00+00:00"))
    scenario("future account context", "levels_only",
             change_settings=lambda s: s["context"].update(as_of="2026-09-15T14:00:02+00:00"))
    scenario("quote prices unavailable", "unavailable",
             change_alert=lambda a: a["snapshot"].pop("planning_quote"))
    scenario("missing share sizes", "levels_only",
             change_alert=lambda a: a["snapshot"]["planning_quote"].update(ask_size_raw=None, ask_size_shares=None))
    scenario("zero share capacity", "no_trade",
             change_alert=lambda a: a["snapshot"]["planning_quote"].update(ask_size_raw=0, ask_size_shares=0))
    scenario("future quote receipt", "unavailable",
             change_alert=lambda a: a["snapshot"]["planning_quote"].update(received_at="2026-09-15T14:00:02+00:00"))
    scenario("stale quote event", "unavailable",
             change_alert=lambda a: a["snapshot"]["planning_quote"].update(event_at="2026-09-15T13:59:54+00:00"))
    scenario("halted instrument", "unavailable",
             change_alert=lambda a: a["snapshot"]["trading_status"].update(halted=True))
    scenario("minute gap", "unavailable", change_alert=lambda a: a["snapshot"]["chart"].pop(4))
    scenario("ask below trigger", "wait",
             change_alert=lambda a: a["snapshot"]["planning_quote"].update(bid=1.98, ask=1.99))
    scenario("ask above entry cap", "wait",
             change_alert=lambda a: a["snapshot"]["planning_quote"].update(ask=2.03))
    scenario("entry displacement beyond entry cap", "wait",
             change_settings=lambda s: s["costs"].update(entry_slippage=.02))
    report["checks"].append("19 rejection, missing-data, account, liquidity and execution-assumption scenarios")

    report["timeline"] = []
    for count, expected in ((15, "levels_only"), (20, "conditional"), (30, "conditional"),
                            (60, "conditional"), (180, "conditional"), (369, "conditional"),
                            (370, "expired"), (389, "expired")):
        raw = synthetic_alert(count)
        value = build_trade_plan(prepare_plan_inputs(raw), synthetic_settings(raw))
        check(value["status"] == expected, "Minute {} timeline status differs".format(count))
        report["timeline"].append({"completed_minutes": count, "decision_at": value["as_of"],
                                    "status": value["status"], "expires_at": value["expires_at"]})
    report["checks"].append("eight chronological synthetic decision points including session expiry")
    start = time.perf_counter()
    for unused in range(100):
        check(build_trade_plan(inputs, settings) == result, "Repeated model run differs")
    report["model_100_runs_seconds"] = time.perf_counter() - start


def run_browser(report, output, chrome):
    """Exercise the real local HTTP service and UI against disposable data."""
    from nomisma.monitor_metrics import demo_bundle
    from nomisma.planner import freeze_plan
    from nomisma.server import Application, make_handler
    from tools.browser_check import DevTools, browser_endpoint

    with tempfile.TemporaryDirectory(prefix="nomisma-planner-check-") as temporary:
        app = Application(Path(temporary) / "data", seed=False)
        raw = synthetic_alert()
        raw.update(price=2.01, score=75, reasons=["Invented engineering fixture"],
                   config=copy.deepcopy(app.monitor.config))
        raw["trade_plan"] = freeze_plan(raw, synthetic_settings(raw))
        app.store.save_monitor_alert(raw, {})
        # This invented fixture uses the current SIP schema solely to exercise
        # non-demo expiry behavior. It is never fetched or traded.
        subcent = copy.deepcopy(raw)
        subcent.update(id="synthetic-sip-subcent-check", source="alpaca", feed="sip")
        subcent["snapshot"].update(source="alpaca", feed="sip")
        subcent["snapshot"]["planning_quote"].update(source="alpaca", feed="sip")
        subcent_settings = synthetic_settings(subcent)
        subcent_settings["policy"]["tick_size"] = .005
        subcent["trade_plan"] = freeze_plan(subcent, subcent_settings)
        check(subcent["trade_plan"]["result"]["levels"]["entry_trigger"] == 2.005, "Subcent fixture trigger differs")
        app.store.save_monitor_alert(subcent, {})
        original_plan = copy.deepcopy(raw["trade_plan"])
        original_settings = app.planner.settings()
        app.monitor.config.update(symbols=["FIXTURE"], source="demo")
        app.monitor.bundle = demo_bundle(["FIXTURE"], step=20)
        app.monitor.status.update(running=True, connection="demo")
        app.monitor._refresh_rows()
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        process, client = None, None

        def request(path, body=None):
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            try:
                connection.request("GET" if body is None else "POST", path,
                                   body=None if body is None else json.dumps(body),
                                   headers={} if body is None else {"Content-Type": "application/json"})
                response = connection.getresponse()
                return response.status, json.loads(response.read())
            finally:
                connection.close()

        try:
            status, saved = request("/api/planner/alerts/" + raw["id"])
            check(status == 200 and saved["plan"] == original_plan, "HTTP must return frozen original analysis")
            check(request("/api/planner/alerts/missing")[0] == 404, "Unknown saved analysis should be 404")
            context = synthetic_settings(raw)["context"]
            check(request("/api/planner/settings", {"context": context})[0] == 400,
                  "Unconfirmed account mutation must be rejected")
            check(app.planner.settings() == original_settings, "Rejected settings must remain unchanged")
            check(request("/api/planner/settings", {"policy": {"hold_minutes": 30}})[0] == 200,
                  "Valid policy settings must persist")
            check(request("/api/planner/alerts/" + raw["id"])[1]["plan"] == original_plan,
                  "Changing assumptions must not rewrite original analysis")
            status, current = request("/api/planner/analyze", {"alert_id": raw["id"]})
            check(status == 200 and current["plan"]["kind"] == "current_reanalysis", "Current HTTP reanalysis unavailable")
            check(current["plan"]["analysis_id"] != original_plan["analysis_id"], "Current analysis must be distinct")
            check(current["plan"]["result"]["as_of"] == app.monitor.bundle["as_of"], "Current analysis must use current synthetic decision time")
            check(app.store.monitor_alert(raw["id"])["trade_plan"] == original_plan, "Current analysis overwrote original")
            report["http_current_result"] = current["plan"]["result"]
            report["checks"].append("isolated HTTP original/current analysis, setting persistence and unconfirmed-context rejection")

            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                debug_port = listener.getsockname()[1]
            process = subprocess.Popen([
                chrome, "--headless=new", "--no-first-run", "--no-default-browser-check",
                "--disable-extensions", "--disable-background-networking", "--disable-sync",
                "--remote-debugging-port=" + str(debug_port),
                "--user-data-dir=" + str(Path(temporary) / "chrome"), "about:blank"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            deadline = time.monotonic() + 20
            while client is None:
                try:
                    client = DevTools(browser_endpoint(debug_port))
                except (OSError, StopIteration):
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Chrome debugging endpoint did not become ready")
                    time.sleep(.1)
            for method in ("Runtime.enable", "Log.enable", "Page.enable"):
                client.call(method)
            report["environment"]["browser"] = client.call("Browser.getVersion")["product"]
            client.call("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 1050, "deviceScaleFactor": 1, "mobile": False})
            client.call("Page.navigate", {"url": "http://127.0.0.1:%d/" % server.server_port})
            client.wait("document.querySelector('[data-plan-alert]') && document.querySelector('#planner-dialog')")
            client.evaluate("document.querySelector('[data-plan-alert]').click()")
            client.wait("document.querySelector('#planner-dialog').open && document.querySelector('#planner-result').textContent.includes('200 shares')")
            check(client.evaluate("document.querySelector('#planner-result').textContent.includes('Original analysis, frozen with the alert.')"),
                  "Original frozen label missing in browser")
            check(client.evaluate("document.querySelector('#planner-result').textContent.includes('Synthetic demo')"),
                  "Synthetic source label missing")
            client.screenshot(output / "planner-desktop.png")
            client.evaluate("document.querySelector('#planner-current').click()")
            client.wait("document.querySelector('#planner-result').textContent.includes('Current reanalysis, separate from the original alert.')")
            check(app.store.monitor_alert(raw["id"])["trade_plan"] == original_plan, "Browser current analysis overwrote original")
            client.evaluate("document.querySelector('#planner-original').click()")
            client.wait("document.querySelector('#planner-result').textContent.includes('200 shares')")

            client.evaluate("document.querySelector('#planner-dialog [data-planner-settings]').click()")
            client.wait("document.querySelector('#planner-settings-dialog').open && !document.querySelector('#planner-save-settings').disabled")
            check(client.evaluate("document.querySelector('#planner-policy-hold_minutes').value === '30'"), "HTTP policy update not visible in browser")
            # Persist a policy change without claiming to refresh account time.
            client.evaluate("document.querySelector('#planner-policy-hold_minutes').value='15'; document.querySelector('#planner-settings-form').requestSubmit()")
            client.wait("!document.querySelector('#planner-settings-dialog').open")
            check(app.planner.settings()["policy"]["hold_minutes"] == 15, "Browser policy save failed")
            check(app.planner.settings()["context"] is None, "Policy update invented an account context")
            client.evaluate("document.querySelector('#planner-dialog [data-planner-settings]').click()")
            client.wait("document.querySelector('#planner-settings-dialog').open && !document.querySelector('#planner-save-settings').disabled")
            for key, value in context.items():
                if key not in ("as_of", "positions"):
                    client.evaluate("document.querySelector(%s).value = %s" % (json.dumps("#planner-account-" + key), json.dumps(str(value))))
            # Explicit zero assumptions isolate the demo clock integration
            # from strategy-specific cost rejection; zero is not a cost claim.
            for key in synthetic_settings(raw)["costs"]:
                value = 0
                client.evaluate("document.querySelector(%s).value = %s" % (json.dumps("#planner-cost-" + key), json.dumps(str(value))))
            client.evaluate("document.querySelector('#planner-confirm-context').checked=true; document.querySelector('#planner-settings-form').requestSubmit()")
            client.wait("!document.querySelector('#planner-settings-dialog').open")
            confirmed = app.planner.settings()["context"]
            check(confirmed["risk_budget"] == 25 and confirmed["positions"] == {}, "Confirmed account not persisted")
            check(confirmed["as_of"] != context["as_of"], "Account confirmation must record current confirmation time")
            check(app.store.monitor_alert(raw["id"])["trade_plan"] == original_plan, "Account update overwrote original")
            client.evaluate("document.querySelector('#planner-current').click()")
            client.wait("document.querySelector('#planner-result').textContent.includes('Current reanalysis, separate from the original alert.')")
            status, projected = request("/api/planner/analyze", {"alert_id": raw["id"]})
            check(status == 200 and (projected["plan"]["result"]["sizing"]["quantity"] or 0) > 0,
                  "Freshly confirmed demo context should permit numeric scenario sizing with explicit zero fees")
            check(projected["plan"]["settings"]["context"]["as_of"] == confirmed["as_of"],
                  "Saved settings must retain real account-confirmation time")
            check(client.evaluate("document.querySelector('#planner-result').textContent.includes('projected onto the simulated session')"),
                  "Demo clock projection must be explained")
            report["confirmed_demo_result"] = projected["plan"]["result"]
            client.evaluate("document.querySelector('#planner-original').click()")
            client.wait("document.querySelector('#planner-result').textContent.includes('200 shares')")

            client.call("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True})
            check(client.evaluate("document.querySelector('#planner-dialog').getBoundingClientRect().width <= innerWidth && document.documentElement.scrollWidth <= innerWidth"),
                  "Mobile trade-plan viewport overflows")
            client.screenshot(output / "planner-mobile.png")
            client.evaluate("document.querySelector('#planner-dialog [data-planner-settings]').click()")
            client.wait("document.querySelector('#planner-settings-dialog').open && !document.querySelector('#planner-save-settings').disabled")
            check(client.evaluate("document.querySelector('#planner-settings-dialog').getBoundingClientRect().width <= innerWidth"), "Mobile settings overflow")
            client.screenshot(output / "planner-settings-mobile.png")
            client.evaluate("document.querySelector('#planner-clear-context').click()")
            client.wait("document.querySelector('#planner-context-time').textContent.includes('removed')")
            check(app.planner.settings()["context"] is None, "Clear account context failed")
            client.evaluate("document.querySelector('#planner-settings-dialog [data-planner-close]').click()")
            check(not client.errors, "Uncaught browser errors before deliberate rejection: " + json.dumps(client.errors))
            app.monitor.status.update(running=False, connection="stopped")
            client.evaluate("document.querySelector('#planner-current').click()")
            client.wait("!document.querySelector('#planner-error').classList.contains('hidden')")
            check(client.evaluate("document.querySelector('#planner-result').textContent.includes('200 shares')"),
                  "Failed current request must preserve saved displayed analysis")
            expected_errors = [error for error in client.errors
                               if error.get("source") == "network"
                               and error.get("url", "").endswith("/api/planner/analyze")
                               and "status of 400" in error.get("text", "")]
            unexpected_errors = [error for error in client.errors if error not in expected_errors]
            check(not unexpected_errors, "Unexpected browser errors: " + json.dumps(unexpected_errors))
            report["checks"].append("real Chrome original/current navigation, manual account confirmation/removal, desktop/mobile screenshots and stopped-monitor error preservation")
            report["browser_uncaught_errors"] = unexpected_errors
            report["browser_expected_stopped_monitor_rejection"] = expected_errors
            client.evaluate("document.querySelector('#planner-dialog [data-planner-close]').click(); document.querySelector('#live-journal').click()")
            client.wait("document.querySelector('[data-live-alert=synthetic-sip-subcent-check]')")
            client.evaluate("document.querySelector('[data-live-alert=synthetic-sip-subcent-check]').click()")
            client.wait("document.querySelector('#live-evidence-result [data-plan-alert=synthetic-sip-subcent-check]')")
            expiry = subcent["trade_plan"]["result"]["expires_at"]
            client.evaluate("window.__plannerRealNow=Date.now; window.__plannerNow=Date.parse(%s)-1000; Date.now=()=>window.__plannerNow; document.querySelector('#live-evidence-result [data-plan-alert=synthetic-sip-subcent-check]').click()" % json.dumps(expiry))
            client.wait("document.querySelector('#planner-result').textContent.includes('$2.005')")
            text_content = client.evaluate("document.querySelector('#planner-result').textContent")
            check("$2.015" in text_content and "$1.945" in text_content, "Browser lost subcent entry/stop precision")
            check("This entry window has expired" not in text_content, "Clock fixture started already expired")
            client.screenshot(output / "planner-subcent-mobile.png")
            client.evaluate("window.__plannerNow += 2000")
            client.wait("document.querySelector('#planner-result').textContent.includes('This entry window has expired')", seconds=3)
            # Resume handling is checked separately from the timer transition.
            client.evaluate("window.__plannerNow -= 2000; document.dispatchEvent(new Event('visibilitychange'))")
            check(client.evaluate("!document.querySelector('#planner-result').textContent.includes('This entry window has expired')"),
                  "Visibility refresh did not recompute expiry")
            client.evaluate("window.__plannerNow += 2000; document.dispatchEvent(new Event('visibilitychange'))")
            check(client.evaluate("document.querySelector('#planner-result').textContent.includes('This entry window has expired')"),
                  "Visibility resume did not expose expired saved analysis")
            client.evaluate("Date.now=window.__plannerRealNow")
            check(client.errors == expected_errors, "New browser errors during subcent/expiry checks")
            report["checks"].append("explicit-zero-cost confirmed demo sizing, .005-tick price clarity, automatic expiry timer and visibility-resume expiry refresh")
        except Exception:
            if client is not None:
                client.screenshot(output / "planner-browser-failure.png")
            raise
        finally:
            app.monitor.close()
            app.stop_event.set()
            if client:
                client.socket.close()
            if process:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="Report directory; does not use or modify the Nomisma workspace database.")
    parser.add_argument("--browser", action="store_true", help="Also check isolated HTTP and real Chrome UI.")
    parser.add_argument("--chrome", default=shutil.which("google-chrome") or shutil.which("chromium") or
                        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {
        "evidence_type": "synthetic engineering scenario replay",
        "profitability_or_parameter_fitting_evidence": False,
        "environment": {"python": sys.version, "platform": platform.platform(),
                        "machine": platform.machine(), "sqlite": sqlite3.sqlite_version,
                        "dependencies": "Python standard library only", "gpu": "not used"},
        "source_sha256": source_hashes(), "checks": [], "failures": [],
    }
    started = time.perf_counter()
    try:
        run_checks(report)
        if args.browser:
            run_browser(report, args.output, args.chrome)
    except Exception:
        report["failures"].append(traceback.format_exc())
    report["elapsed_seconds"] = time.perf_counter() - started
    if resource is not None:
        report["max_resident_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024)
    else:
        report["resource_usage_note"] = "The optional Python resource module is unavailable; resident memory was not measured."
    report["source_changed_during_run"] = source_hashes() != report["source_sha256"]
    if report["source_changed_during_run"]:
        report["failures"].append("Source files changed during validation; rerun on a stable version.")
    report["passed"] = not report["failures"]
    path = args.output / "planner-check.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(("PASS" if report["passed"] else "FAIL") + " synthetic planner engineering checks: " + str(path))
    for failure in report["failures"]:
        print(failure, file=sys.stderr)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
