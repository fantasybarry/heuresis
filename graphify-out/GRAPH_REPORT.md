# Graph Report - heuresis  (2026-11-02)

## Corpus Check
- 145 files · ~197,010 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 25 file(s) not represented in the graph (top: .toml 6, (none) 3, .css 3)

## Summary
- 2499 nodes · 6075 edges · 135 communities (98 shown, 37 thin omitted)
- Extraction: 96% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 240 edges (avg confidence: 0.87)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `b5dae56d`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- app.js
- simultaneous_session_bounds
- trade_plan.py
- live.js
- MainWindow
- dict
- DiscoveryTests
- _Replay
- live_data.py
- cash_calendar.py
- row
- server.py
- json
- calibration.py
- screen
- __init__.py
- market
- host.py
- Application
- quote
- discovery_data.py
- AppDelegate
- _GuardedReplay
- Nomisma — first discovery study
- providers.py
- ApplicationTests
- LiveMonitor
- discovery_replay.py
- MonitorTests
- build_windows.py
- Store
- during_request
- ResearchDataTests
- research.py
- generate_icon.py
- tools/all_in_replay.py
- .webView
- launch.py
- DevTools
- WebSocketTests
- test_all_in_replay.py
- DesktopHostTests
- prepare_plan_inputs
- StorageTests
- ReplayDataTests
- run
- calibrate.py
- SDL.md - SDL-MCP Agent Workflow
- build_desktop.py
- Nomisma live-trading handoff — October 29, 2026
- replay.py
- cash_result
- WindowsBuildTests
- AlpacaTests
- .download
- bridge.test.cjs
- Pool
- check_alert_source_isolation
- planner.js
- HTTPTests
- planner_check.py
- .snapshot
- Microsoft.Web.WebView2
- Proposed next plan
- pool.py
- Monitoring and screening methodology
- .isTrusted
- _WebSocket
- Nomisma
- research_findings_and_questions.md
- Task 09/17 — Historical replay pilot
- task09_17.md
- Handoff: Nomisma discovery study, 2026-10-22
- CheckpointTests
- CSVTests
- filters-dialog
- discovery_signals.py
- replay_data.py
- App.swift
- run_catalog_cash
- DesktopNotification
- history_metrics
- Task09_17 — investigation of the negative cash-account results
- DesktopBuildTests
- InstrumentTests
- make_catalog
- Cash-account allocation pilot, 18 September 2026
- TransportTests
- Workspace shell and research navigation
- methodology-view
- September 18 execution update — actual $1,000 account
- check_windows.py
- _d
- CheckpointTests
- test_cash_calendar.py
- Nomisma.Windows.csproj
- research_data.py
- test_discovery_replay.py
- AllInCliTests
- argparse
- Task 09_19 — proposed priorities and simulation improvements
- Windows x64 build and verification
- _AllInReplay
- readable
- real_spreads
- Historical replay pilot
- All-in cash allocation and exit comparison — September 20, 2026
- Nomisma implementation contract
- Research follow-through, 18 September 2026
- make_handler
- DiscoveryScheduleTests
- Historical replay calibration: development experiment v1
- 4. Runtime Output Control
- DemoTests
- parent_archive
- Q: Give a concise overview of heuresis, its purpose, main components, architecture, and workflows
- ._validate_backup
- Replay
- Heuresis
- settings-dialog
- quote_at
- PoolTest
- Massive
- Nomisma agent coordination
- run_catalog_all_in
- WindowsVerificationTests
- MonitorHTTPTests
- test_cash_replay.py
- CalendarTests
- CandleTests
- CashCliTests
- CandidateTests

## God Nodes (most connected - your core abstractions)
1. `Application` - 64 edges
2. `AppDelegate` - 58 edges
3. `MonitorTests` - 55 edges
4. `row()` - 45 edges
5. `fixture()` - 44 edges
6. `MainWindow` - 40 edges
7. `bind()` - 40 edges
8. `screen()` - 39 edges
9. `LiveMonitor` - 39 edges
10. `Store` - 37 edges

## Surprising Connections (you probably didn't know these)
- `4. Runtime Output Control` --references--> `digest()`  [INFERRED]
  SDL.md → nomisma/nomisma/replay_data.py
- `Pitfalls` --references--> `utcnow()`  [INFERRED]
  nomisma/Research_Files/handoff/10_29_HANDOFF.md → nomisma/nomisma/monitor.py
- `Stuck / open problems` --references--> `ProviderError`  [INFERRED]
  nomisma/Research_Files/handoff/10_29_HANDOFF.md → nomisma/nomisma/providers.py
- `2. Banner stuck after a server restart — `nomisma/static/app.js` `pollStatus`` --references--> `pollStatus()`  [INFERRED]
  nomisma/Research_Files/handoff/10_29_HANDOFF.md → nomisma/nomisma/static/app.js
- `Locations` --references--> `load_environment()`  [INFERRED]
  nomisma/Research_Files/handoff/10_29_HANDOFF.md → nomisma/run.py

## Import Cycles
- None detected.

## Communities (135 total, 37 thin omitted)

### Community 0 - "app.js"
Cohesion: 0.10
Nodes (78): api(), applyJob(), avatar(), average(), bindEvents(), booleanFields, bootstrap(), changeClass() (+70 more)

### Community 1 - "simultaneous_session_bounds"
Cohesion: 0.07
Nodes (29): collections, audit_replay(), Research diagnostics; neither parameter selection nor a trading service. The…, Retain every decision/order and distinguish impossible entry intervals., Paired circular blocks within each disjoint validation fold. panel: {policy_id:…, simultaneous_session_bounds(), Completed experiment, Completed tasks and evidence (+21 more)

### Community 2 - "trade_plan.py"
Cohesion: 0.09
Nodes (29): build_all_in_plan(), Reuse frozen market/geometry validation, then size only by settled cash.…, Planner, _base(), build_trade_plan(), _calculate(), target(), default_plan_settings() (+21 more)

### Community 3 - "live.js"
Cohesion: 0.07
Nodes (78): accept(), acknowledge(), applyDiscoveryJob(), bind(), candidateSelection(), candleBody(), candleChart(), candleHover() (+70 more)

### Community 4 - "MainWindow"
Cohesion: 0.06
Nodes (35): Button, CoreWebView2DownloadStartingEventArgs, CoreWebView2WebMessageReceivedEventArgs, Nomisma.Desktop, Form, FormClosingEventArgs, Label, MenuStrip (+27 more)

### Community 5 - "dict"
Cohesion: 0.07
Nodes (16): bar(), calendar(), FloatTests, dict, object, ScreeningHistoryTests, SeedTests, blocked() (+8 more)

### Community 6 - "DiscoveryTests"
Cohesion: 0.06
Nodes (11): calendar(), DiagnosticTests, DiscoveryTests, get(), get(), history(), get(), get() (+3 more)

### Community 7 - "_Replay"
Cohesion: 0.19
Nodes (6): _json(), Decimal, _quote_valid(), Stable per-nanosecond snapshot: the last provider ordinal wins., _records(), _Replay

### Community 8 - "live_data.py"
Cohesion: 0.08
Nodes (34): base64, concurrent_futures, _cancellable_call(), _Cancelled, _check_stop(), extended_day_volumes(), fetch_float(), _get_json() (+26 more)

### Community 9 - "cash_calendar.py"
Cohesion: 0.16
Nodes (22): _catalog_digest(), _canonical(), create_calendar(), _dates(), _day(), _digest(), load_calendar(), _path() (+14 more)

### Community 10 - "row"
Cohesion: 0.12
Nodes (5): fixture(), IntradayVolumeTests, PriceAndFloatTests, row(), SetupSafetyTests

### Community 11 - "server.py"
Cohesion: 0.10
Nodes (33): copy, datetime, http_client, http_server, logging, mimetypes, LiveSubscriptionLimit, A rejected symbol list needs user action, not repeated reconnection. (+25 more)

### Community 12 - "json"
Cohesion: 0.14
Nodes (23): contextlib, gzip, hashlib, importlib_util, json, Small, transaction-based local persistence for Nomisma., Immutable all-in replay checkpoints and source identity contracts., Checkpoint behavior protects reproducibility of the expensive offline sweep. (+15 more)

### Community 13 - "calibration.py"
Cohesion: 0.22
Nodes (17): itertools, _aggregate(), compare_candidates(), compact(), compare_metrics(), _dates(), _diagnostic_best(), _flat() (+9 more)

### Community 14 - "screen"
Cohesion: 0.09
Nodes (27): _atr(), _clamp(), _date(), _ema(), _filter_failures(), _metadata(), _metrics(), _percent() (+19 more)

### Community 15 - "__init__.py"
Cohesion: 0.19
Nodes (10): decimal, heapq, Immutable development catalogs and bounded session-by-session acquisition. This…, Nomisma: explainable daily equity screening, part of Heuresis., Offline liquidation-equity observation and fixed-dollar research guard. The…, Catalog lineage, selective loading, and bounded acquisition contracts., Pinned streaming parity and exposed-development metric/selection contracts., Conditional liquidation equity, observed-threshold control and passive parity. (+2 more)

### Community 16 - "market"
Cohesion: 0.13
Nodes (6): market(), NumericalFixtureTests, PlanStateTests, Researcher numerical fixtures and safety boundaries; no I/O or orders., settings(), ValidationTests

### Community 17 - "host.py"
Cohesion: 0.18
Nodes (19): errno, choose_port(), launch_lock(), main(), _matches(), Own one local service; release database handles when the app exits. The HTTP…, Resolve a desktop workspace and start/reuse its loopback backend. stdout is a…, Serialize desktop launches for one database, including port selection. (+11 more)

### Community 18 - "Application"
Cohesion: 0.12
Nodes (6): Exception, Application, loop(), BusyError, default_discovery_state(), Replace the radar's symbols with the search's top results; an active monitor…

### Community 19 - "quote"
Cohesion: 0.15
Nodes (18): _confirmation(), _iso(), _ns(), Session-scoped monitor confirmation without persistence or wall clock., Parse UTC nanoseconds without float timestamps or microsecond loss., Replay all archived sessions and cohort symbols chronologically, offline., run_replay(), accounting_engine() (+10 more)

### Community 20 - "discovery_data.py"
Cohesion: 0.12
Nodes (30): build_universe(), delisted(), delisted_check(), fetch_grouped(), fetch_minutes(), fetch_tickers(), _load(), manifest() (+22 more)

### Community 21 - "AppDelegate"
Cohesion: 0.08
Nodes (19): AppDelegate, Process, Notification, NSApplicationDelegate, NSButton, NSMenuItemValidation, NSObject, NSProgressIndicator (+11 more)

### Community 22 - "_GuardedReplay"
Cohesion: 0.13
Nodes (9): _GuardedReplay, Any, Additional observer/control hooks; frozen execution methods stay intact., drain(), engine(), GuardControlTests, LiquidationEquityTests, observe() (+1 more)

### Community 23 - "Nomisma — first discovery study"
Cohesion: 0.09
Nodes (22): Acquisition sequence and gates, Candle features (frozen), Condition search (post hoc), Continuation outcome, Data sources, Entry comparison, Evaluation, Execution (+14 more)

### Community 24 - "providers.py"
Cohesion: 0.11
Nodes (29): csv, io, _parse(), Stocks-only eligibility from Nasdaq Trader's public symbol directories.…, Return a fresh verified stock allowlist; never send provider credentials., require_stocks(), stock_symbols(), _asset_metadata() (+21 more)

### Community 25 - "ApplicationTests"
Cohesion: 0.10
Nodes (5): default_settings(), validate_settings(), ApplicationTests, SettingsTests, patch

### Community 26 - "LiveMonitor"
Cohesion: 0.19
Nodes (5): LiveMonitor, on_status(), Repair missing minute history without rolling back newer events., Only complete, contiguous future windows from matching provenance., utcnow()

### Community 27 - "discovery_replay.py"
Cohesion: 0.11
Nodes (32): _bootstrap_low(), candle(), _cutoff(), _day_bars(), exit_variants(), export_losers(), hypotheses(), managed_trade() (+24 more)

### Community 28 - "MonitorTests"
Cohesion: 0.09
Nodes (3): timestamp(), MonitorTests, loading()

### Community 29 - "build_windows.py"
Cohesion: 0.17
Nodes (26): build(), compile_installer(), copy_backend(), download_verified(), extract_verified_archive(), main(), prepare_python(), preserve_licenses() (+18 more)

### Community 30 - "Store"
Cohesion: 0.16
Nodes (3): A transactionally consistent SQLite snapshot, even during a scan., Validate fully, retain a safety copy, then atomically restore rows. The caller…, Store

### Community 32 - "ResearchDataTests"
Cohesion: 0.11
Nodes (6): calendar(), requester(), ResearchDataTests, limited(), checked(), stream()

### Community 33 - "research.py"
Cohesion: 0.18
Nodes (21): _stamp(), _calendar(), _candidate(), default_discovery(), diagnose(), discover(), _extend_missing_day_volume(), _phase() (+13 more)

### Community 34 - "generate_icon.py"
Cohesion: 0.38
Nodes (5): inside_polygon(), main(), png(), Rebuild Nomisma.ico from the app's simple N monogram (stdlib only)., zlib

### Community 35 - "tools/all_in_replay.py"
Cohesion: 0.16
Nodes (15): desktop, source_hashes(), source_hashes(), Write a pretty-printed JSON file that must not already exist., write_new(), execute(), main(), Run one immutable offline all-in settled-cash exit-policy comparison. (+7 more)

### Community 36 - ".webView"
Cohesion: 0.11
Nodes (16): Any, String, UNAuthorizationStatus, UNNotification, UNNotificationPresentationOptions, UNNotificationResponse, UNUserNotificationCenter, Void (+8 more)

### Community 37 - "launch.py"
Cohesion: 0.15
Nodes (10): check_workspace(), health(), launch(), main(), port_available(), port_open(), Start or reuse this local workspace, then open its ready browser interface., Check a local bind without Windows' refused-connection timeout. Windows needs… (+2 more)

### Community 39 - "WebSocketTests"
Cohesion: 0.19
Nodes (4): FakeSocket, frame(), sent_frame(), WebSocketTests

### Community 40 - "test_all_in_replay.py"
Cohesion: 0.22
Nodes (9): AllInIntegrationTests, AllInSizingTests, engine(), enter(), observe(), plan(), ProtectiveExitTests, All-in requested sizing, settled funding and causal protective exits. (+1 more)

### Community 42 - "prepare_plan_inputs"
Cohesion: 0.25
Nodes (5): prepare_plan_inputs(), _provenance(), Validate original alert evidence; return diagnostics and a finite schema. No…, fixture(), PlanningInputTests

### Community 43 - "StorageTests"
Cohesion: 0.13
Nodes (4): demo_dataset(), An explicitly synthetic, reproducible historical research playground., StorageTests, record_connection()

### Community 44 - "ReplayDataTests"
Cohesion: 0.14
Nodes (4): fixture(), ReplayDataTests, malformed(), count()

### Community 45 - "run"
Cohesion: 0.22
Nodes (6): browser_endpoint(), check_alert_refresh(), check_live(), Exercise real browser events against the isolated synthetic monitor., Explicit refresh must work even when the background event stream is idle., run()

### Community 46 - "calibrate.py"
Cohesion: 0.13
Nodes (34): create_catalog(), download_development(), _new_directory(), Sequentially download a declared development batch using frozen importer.…, Split verified replay archives into one-session files; return catalog path.…, _validate_dates(), generate_candidates(), Path (+26 more)

### Community 47 - "SDL.md - SDL-MCP Agent Workflow"
Cohesion: 0.07
Nodes (24): Code-context workflow, Claude in heuresis, Codex in heuresis, Signals, 1. Start Every Task, 2. Retrieval Ladder, 3. File And Edit Rules, 5. Memory And Indexing (+16 more)

### Community 48 - "build_desktop.py"
Cohesion: 0.20
Nodes (20): build(), build_icon(), clean_python_environment(), copy_backend(), copy_python(), install_bundle(), mach_o_files(), main() (+12 more)

### Community 49 - "Nomisma live-trading handoff — October 29, 2026"
Cohesion: 0.11
Nodes (18): 2. Banner stuck after a server restart — `nomisma/static/app.js` `pollStatus`, 4. Trade log — `nomisma/data/trade_log.csv` (git-ignored), 5. Replay work preserved, Background: replay findings and user decisions (from 10/28–29), Completed, Completed today, Current state (as of 11:30 ET, 10/29), Discovery study handoff — October 29, 2026 (+10 more)

### Community 50 - "replay.py"
Cohesion: 0.10
Nodes (35): bisect, math, Cash-only requested sizing and three causal exit policies, offline only. This…, Versioned offline cash-account and single-entry allocation experiment. The…, _number(), True for a finite non-bool int/float within [minimum, maximum]., build_rows(), _daily() (+27 more)

### Community 51 - "cash_result"
Cohesion: 0.24
Nodes (4): boundary(), cash_result(), ComparisonTests, MetricTests

### Community 53 - "AlpacaTests"
Cohesion: 0.23
Nodes (5): AlpacaTests, response(), response(), response(), raw_bar()

### Community 54 - ".download"
Cohesion: 0.20
Nodes (8): Data, Error, HTTPURLResponse, DownloadDestination, URL, URLRequest, URLResponse, WKDownload

### Community 55 - "bridge.test.cjs"
Cohesion: 0.17
Nodes (10): assert, fs, path, test, vm, ref_node_assert, ref_node_fs, ref_node_path (+2 more)

### Community 56 - "Pool"
Cohesion: 0.33
Nodes (3): _line(), Pool, Upstream loop. Errors disconnect workstations; their monitors own retry backoff.

### Community 57 - "check_alert_source_isolation"
Cohesion: 0.33
Nodes (4): check_alert_source_isolation(), inbox(), mark_all(), Persist both sources without starting a market connection or altering earlier…

### Community 58 - "planner.js"
Cohesion: 0.33
Nodes (5): metric(), render(), showAlert(), toggleBusy(), updateExpiry()

### Community 60 - "planner_check.py"
Cohesion: 0.25
Nodes (13): check(), check_arithmetic(), main(), Reproducible offline engineering checks for the research trade planner. All…, Exercise the real local HTTP service and UI against disposable data., Independent flat-range example: minute TR=.04 and five-minute high=2. Original…, run_browser(), run_checks() (+5 more)

### Community 61 - ".snapshot"
Cohesion: 0.15
Nodes (12): Config (metrics module validates; defaults exported), Intraday monitoring implementation contract, Metrics module public API, Monitor service and browser API (root), Normalized provider bundle, Ownership, Provider module public API, Research extensions (September 2026) (+4 more)

### Community 62 - "Microsoft.Web.WebView2"
Cohesion: 0.25
Nodes (10): dependencies, net10.0-windows7.0, net10.0-windows7.0/win-x64, contentHash, requested, resolved, type, Microsoft.Web.WebView2 (+2 more)

### Community 63 - "Proposed next plan"
Cohesion: 0.14
Nodes (14): 1. Explain the missing executions, 2. Freeze the next experiment's rules, 3. Expand data in stages, 4. Measure intraday portfolio risk, 5. Repeat chronological validation, 6. Evaluate one frozen candidate on an untouched holdout, Immediate proposed scope, Investigate entry parameters after the execution audit (+6 more)

### Community 64 - "pool.py"
Cohesion: 0.17
Nodes (11): hmac, One authenticated stream session; root performs reconnect and reseeding., _stream_error(), stream_live(), report_channels(), _symbols(), _Handler, Share one Alpaca stream between workstations. Alpaca allows one real-time… (+3 more)

### Community 65 - "Monitoring and screening methodology"
Cohesion: 0.15
Nodes (13): Alert confirmation, repeats, and delivery, Daily screener: indicators and timing, Daily screener: score composition, Interpretation limits, Intraday score and indicators, Intraday session and price timing, Intraday volume, gap, and float, Liquidity and volatility metrics (+5 more)

### Community 66 - ".isTrusted"
Cohesion: 0.24
Nodes (4): Bool, NSApplication, NSMenuItem, WKFrameInfo

### Community 68 - "Nomisma"
Cohesion: 0.06
Nodes (29): Build or update, Native controls, Nomisma for macOS, Troubleshooting, Alert source fix in 1.2.2, Build locally, Candidate freshness fixes in 1.2.3, Download and install (+21 more)

### Community 70 - "Task 09/17 — Historical replay pilot"
Cohesion: 0.17
Nodes (12): Actual replay results, Completed task list, Data and baseline assumptions, Files and reproducibility, Implementation and actual agents, Implemented and executed, Remaining research tasks, Results (+4 more)

### Community 72 - "task09_17.md"
Cohesion: 0.20
Nodes (7): Affine fees and robust sizing, Built-in intraday research planner, In the app, Inputs and data provenance, Mathematics, Output states, Validation and remaining research

### Community 73 - "Handoff: Nomisma discovery study, 2026-10-22"
Cohesion: 0.22
Nodes (8): Completed, First study: the 39 losers on the arm c, gap ≥40% candidate, Handoff: Nomisma discovery study, 2026-10-22, Locations, Pitfalls, Second study: pre-registered H1 and H2, scored once on 2026-10-22, Stuck or open, Where things stand

### Community 77 - "discovery_signals.py"
Cohesion: 0.13
Nodes (20): day_context(), Stock-day features known at the open: opening gap and premarket dollar volume., replay(), atr14(), by_day(), _calendar(), opportunities(), pilot() (+12 more)

### Community 78 - "replay_data.py"
Cohesion: 0.20
Nodes (14): _Archive, _bars(), _basis(), download_dataset(), _events(), _http(), _now(), Immutable, offline historical replay archives; no monitor or order interfaces.… (+6 more)

### Community 79 - "App.swift"
Cohesion: 0.29
Nodes (5): AppKit, Foundation, NomismaApplication, UserNotifications, WebKit

### Community 80 - "run_catalog_cash"
Cohesion: 0.17
Nodes (15): iter_sessions(), load_catalog(), Read and validate metadata/lineage only; never read session outcomes., Yield one verified requested development session at a time. Omitted dates means…, _safe_file(), _validate_session(), Mirror the unchanged run_replay entry contract across streamed sessions., replay_source_sha256() (+7 more)

### Community 83 - "history_metrics"
Cohesion: 0.15
Nodes (12): _bars(), _date(), history_metrics(), rank_rows(), measured(), Pure historical liquidity/volatility measurements and transparent ranking.…, Assign cross-sectional ranks without hiding rows or changing input order.…, Compute completed-session metrics; callers may supply the exchange's prior… (+4 more)

### Community 84 - "Task09_17 — investigation of the negative cash-account results"
Cohesion: 0.22
Nodes (9): 1. What actually lost money, 2. The alert identified momentum after a substantial rise, 3. Stop and target parameters describe payoff geometry, not probability, 4. Price rounding and execution assumptions removed most alternatives, 5. Single-entry selection made this day's result worse, 6. Costs and capital allocation were secondary to this loss, 7. What the evidence supports next, Task09_17 — investigation of the negative cash-account results (+1 more)

### Community 87 - "make_catalog"
Cohesion: 0.25
Nodes (5): make_catalog(), StreamingTests, two_sessions(), account_config(), AdapterTests

### Community 88 - "Cash-account allocation pilot, 18 September 2026"
Cohesion: 0.25
Nodes (7): Cash-account allocation pilot, 18 September 2026, Cash and settlement, Feasibility and causal selection, Primary rule references, Purpose and scope, Sizing and registered comparisons, Validation and reporting

### Community 92 - "September 18 execution update — actual $1,000 account"
Cohesion: 0.25
Nodes (8): Actual replay results, Confirmed capital and risk, Data and recording results, Files and reproducible evidence, Remaining-task status after execution, September 18 execution update — actual $1,000 account, Verification, resources and independent assessment, Why the old results cannot be read as parameter quality

### Community 93 - "check_windows.py"
Cohesion: 0.21
Nodes (16): check(), clean_environment(), main(), port_closed(), Path, Retain only timing diagnostics, even if native verification failed., Verify Windows release artifacts on a clean Windows test account. Installs,…, Verify exactly one installer/archive pair before executing any package. (+8 more)

### Community 96 - "test_cash_calendar.py"
Cohesion: 0.22
Nodes (6): dataclasses, archive(), calendar(), CashCalendarTests, Settlement follows archived provider dates, with no trading-day extrapolation., row()

### Community 97 - "Nomisma.Windows.csproj"
Cohesion: 0.50
Nodes (3): net10.0-windows, Microsoft.Web.WebView2 (1.0.4191.47), Microsoft.NET.Sdk

### Community 98 - "research_data.py"
Cohesion: 0.12
Nodes (21): acquire_preflight(), _Budget, bounded(), capture_metadata(), _error_code(), _new_directory(), Bounded read-only research acquisition, separate from all trading services.…, Reconstruct transport coverage from hashed event rows, never manifest claims. (+13 more)

### Community 99 - "test_discovery_replay.py"
Cohesion: 0.24
Nodes (5): bars(), OutcomeTest, Entry gating, deadline exit and wick exit of the discovery replay on synthetic…, ReclaimTest, TradeTest

### Community 101 - "argparse"
Cohesion: 0.27
Nodes (7): argparse, SourceExportTests, allowed_source(), export_source(), main(), Export current Nomisma source for a fresh GitHub repository, without history.…, zipfile

### Community 102 - "Task 09_19 — proposed priorities and simulation improvements"
Cohesion: 0.25
Nodes (8): Execution order and ownership, Export record, Priority 1 — verify prices and the execution contract, Priority 2 — improve diagnostics and execution realism, Priority 3 — register and expand the evidence, Priority 4 — test entry and exit hypotheses, Requirements and existing baseline, Task 09_19 — proposed priorities and simulation improvements

### Community 106 - "readable"
Cohesion: 0.33
Nodes (7): The only gate to study data; holdout stays sealed until finalists are committed., readable(), conditions(), percent(), Post-hoc quintile scan of decision-time features over liquid primary fills, per…, Month-by-month gross percent per arm: all liquid primary fills, in play, and…, tally()

### Community 107 - "real_spreads"
Cohesion: 0.25
Nodes (9): _half_spread(), Alpaca RFC 3339 timestamp (nanoseconds, Z) to an aware datetime., Relative half-spread of the NBBO in force at moment (else the first valid quote…, Cached half-spread lookup at a New York minute; raw Alpaca SIP quotes are…, Net returns of liquid in-play primary fills using measured Alpaca SIP spreads…, real_spreads(), _spreads(), spread_at() (+1 more)

### Community 108 - "Historical replay pilot"
Cohesion: 0.29
Nodes (7): Archived inputs and historical clock, Frozen development experiment, Historical replay pilot, Later research, Required evidence, Running the pilot, Simulated orders and shared portfolio

### Community 109 - "All-in cash allocation and exit comparison — September 20, 2026"
Cohesion: 0.22
Nodes (8): All-in cash allocation and exit comparison — September 20, 2026, Authorized change and scope, Causal event ordering, Entry allocation and actual execution, Equity observation with no account drawdown control, Required checks and bounded execution, Review and attribution, Three fixed exit policies

### Community 110 - "Nomisma implementation contract"
Cohesion: 0.20
Nodes (8): Built-in planner API, Data (`nomisma/providers.py`), Engine (`nomisma/engine.py`), Nomisma implementation contract, Other research extensions, Research and workspace extensions, Server API (root implements), UI (frontend agent owns static files)

### Community 111 - "Research follow-through, 18 September 2026"
Cohesion: 0.29
Nodes (6): Conditional liquidation equity and guard, Confirmed account constraint, Data stages and evidence limits, Decision funnel and parameter evidence, Research follow-through, 18 September 2026, Verification and resource profile

### Community 112 - "make_handler"
Cohesion: 0.14
Nodes (19): _credentials(), fetch_candles(), fetch_market_pulse(), live_provider_status(), _number(), Latest OHLCV bars (or those before an ISO time) at one timeframe, extended…, Latest price and day change for the index ETFs and the largest stocks, plus…, MonitorBusy (+11 more)

### Community 114 - "Historical replay calibration: development experiment v1"
Cohesion: 0.33
Nodes (5): Frozen experiment, Historical replay calibration: development experiment v1, Replay and scoring, Selection and sensitivity, Verification

### Community 115 - "4. Runtime Output Control"
Cohesion: 0.50
Nodes (3): 4. Runtime Output Control, Execute First, Query Only Needed Output

### Community 119 - "Q: Give a concise overview of heuresis, its purpose, main components, architecture, and workflows"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Give a concise overview of heuresis, its purpose, main components, architecture, and workflows, Source Nodes

### Community 120 - "._validate_backup"
Cohesion: 0.27
Nodes (8): default_discovery_settings(), validate_discovery_settings(), Read only known table data; never execute schema from an upload., decode(), finite(), invalid(), discovery_job(), stamp()

### Community 126 - "PoolTest"
Cohesion: 0.31
Nodes (3): fake_stream(), PoolTest, on_event()

### Community 128 - "Massive"
Cohesion: 0.29
Nodes (4): Massive, _NoRedirect, HTTPRedirectHandler, Paced GET transport returning raw response bytes.

### Community 129 - "Nomisma agent coordination"
Cohesion: 0.25
Nodes (7): Delegation procedure, Final reporting, Main agent responsibilities, Nomisma agent coordination, Task routing, Trading boundaries, Workflow for substantial strategy changes

### Community 131 - "run_catalog_all_in"
Cohesion: 0.24
Nodes (10): effective_policy(), Path, Stream one predeclared fixed exit policy through settled-cash sessions., run_catalog_all_in(), _config(), default_replay_config(), _fingerprint(), _finite() (+2 more)

### Community 138 - "test_cash_replay.py"
Cohesion: 0.19
Nodes (8): CashAccountingTests, CashPolicyTests, CashReplayIntegrationTests, engine(), fill_entry(), fill_exit(), plan(), Cash conservation, settlement availability, causal allocation and risk edges.

## Knowledge Gaps
- **232 isolated node(s):** `AppKit`, `Foundation`, `WebKit`, `UserNotifications`, `ExitCode` (+227 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 785 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **37 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Completed today` connect `Nomisma live-trading handoff — October 29, 2026` to `DiscoveryScheduleTests`, `replay.py`?**
  _High betweenness centrality (0.148) - this node is a cross-community bridge._
- **Why does `2. Banner stuck after a server restart — `nomisma/static/app.js` `pollStatus`` connect `Nomisma live-trading handoff — October 29, 2026` to `app.js`?**
  _High betweenness centrality (0.147) - this node is a cross-community bridge._
- **Why does `pollStatus()` connect `app.js` to `Nomisma live-trading handoff — October 29, 2026`?**
  _High betweenness centrality (0.146) - this node is a cross-community bridge._
- **Are the 9 inferred relationships involving `Application` (e.g. with `LiveMonitor` and `Planner`) actually correct?**
  _`Application` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `MonitorTests` (e.g. with `LiveSubscriptionLimit` and `LiveMonitor`) actually correct?**
  _`MonitorTests` has 4 INFERRED edges - model-reasoned connections that need verification._
- **What connects `AppKit`, `Foundation`, `WebKit` to the rest of the system?**
  _232 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `app.js` be split into smaller, more focused modules?**
  _Cohesion score 0.09866926322622525 - nodes in this community are weakly interconnected._