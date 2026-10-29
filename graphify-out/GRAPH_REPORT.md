# Graph Report - heuresis  (2026-10-29)

## Corpus Check
- 145 files · ~193,390 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 27 file(s) not represented in the graph (top: .toml 6, (none) 3, .css 3)

## Summary
- 2506 nodes · 6070 edges · 147 communities (115 shown, 32 thin omitted)
- Extraction: 96% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 248 edges (avg confidence: 0.87)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `c3ed4486`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- app.js
- simultaneous_session_bounds
- planner_check.py
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
- run_catalog_all_in
- screen
- replay.py
- market
- host.py
- Application
- quote
- discovery_data.py
- AppDelegate
- _GuardedReplay
- math
- providers.py
- ApplicationTests
- LiveMonitor
- discovery_replay.py
- MonitorTests
- build_windows.py
- Store
- .prepare_stream
- ResearchDataTests
- research.py
- browser_check.py
- tools/all_in_replay.py
- .webView
- launch.py
- DevTools
- WebSocketTests
- Historical replay pilot
- DesktopHostTests
- prepare_plan_inputs
- StorageTests
- ReplayDataTests
- run
- calibrate.py
- SDL.md - SDL-MCP Agent Workflow
- build_desktop.py
- Proposed validation and parameter-calibration plan
- monitor_metrics.py
- cash_result
- WindowsBuildTests
- AlpacaTests
- .download
- bridge.test.cjs
- pool.py
- check_alert_source_isolation
- planner.js
- Linear drift term κ(θ − v) dt
- Nomisma research handoff — October 6, 2026
- Intraday monitoring implementation contract
- Microsoft.Web.WebView2
- Nomisma — first discovery study
- Consolidated research findings and questions
- All-in cash-account simulation and exit comparison
- .isTrusted
- _check_stop
- Nomisma
- Linear drift term θ(μ − z) dt
- Exponential term αe^(−β(t − tᵢ))
- Historical replay pilot and account-model updates
- Nomisma for Windows 11 Pro
- Subtracted adjustment qγσ²(T − t)
- CheckpointTests
- CSVTests
- filters-dialog
- discovery_signals.py
- replay_data.py
- App.swift
- _canonical
- DesktopNotification
- history_metrics
- Earlier profit-taking investigation
- DesktopBuildTests
- InstrumentTests
- make_catalog
- Entry quality as the next research priority
- TransportTests
- Workspace shell and research navigation
- Monitoring and screening methodology
- validate_monitor_config
- check_windows.py
- _CashReplay
- CheckpointTests
- test_cash_calendar.py
- Nomisma.Windows.csproj
- research_data.py
- test_discovery_replay.py
- AllInCliTests
- test_desktop_host.py
- _StreamEvidence
- Windows x64 build and verification
- _json
- .handle
- hypotheses
- test_replay.py
- All-in cash allocation and exit comparison — September 20, 2026
- Nomisma implementation contract
- Cash-account allocation pilot, 18 September 2026
- .snapshot
- DiscoveryScheduleTests
- Research follow-through, 18 September 2026
- Built-in intraday research planner
- Historical replay calibration: development experiment v1
- parent_archive
- _cancellable_call
- Q: Give a concise overview of heuresis, its purpose, main components, architecture, and workflows
- ._validate_backup
- Sharing one Alpaca feed between two machines
- Replay
- Heuresis
- settings-dialog
- test_planning_data.py
- PoolTest
- TRADE_PLANNER.md
- Massive
- Nomisma agent coordination
- Handoff: Nomisma discovery study, 2026-10-22
- replay_pilot.py
- rank_rows
- WindowsVerificationTests
- AGENTS.md
- _confirmation
- Research extensions (September 2026)
- MonitorHTTPTests
- CashReplayIntegrationTests
- CalendarTests
- 2. Retrieval Ladder
- .__init__
- 3. File And Edit Rules
- CandleTests
- CashCliTests
- .test_explicit_refresh_is_async_and_preserves_stream_events_and_alert_dedup
- CandidateTests

## God Nodes (most connected - your core abstractions)
1. `Application` - 64 edges
2. `AppDelegate` - 58 edges
3. `MonitorTests` - 55 edges
4. `row()` - 45 edges
5. `fixture()` - 44 edges
6. `MainWindow` - 40 edges
7. `screen()` - 39 edges
8. `LiveMonitor` - 39 edges
9. `Store` - 37 edges
10. `build_rows()` - 35 edges

## Surprising Connections (you probably didn't know these)
- `Pitfalls` --references--> `hypotheses()`  [INFERRED]
  handoff/10_22_HANDOFF.md → nomisma/nomisma/discovery_replay.py
- `4. Runtime Output Control` --references--> `digest()`  [INFERRED]
  SDL.md → nomisma/nomisma/replay_data.py
- `Unresolved findings and stuck problems` --references--> `audit_replay()`  [INFERRED]
  handoff/10_06_HANDOFF.md → nomisma/nomisma/research_validation.py
- `Unresolved findings and stuck problems` --references--> `_validated_market()`  [INFERRED]
  handoff/10_06_HANDOFF.md → nomisma/nomisma/trade_plan.py
- `Pitfalls` --references--> `load_environment()`  [INFERRED]
  handoff/10_22_HANDOFF.md → nomisma/run.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Repeated counterfactuals on the September 14 FTFT entry** — nomisma_temporary_task09_20_all_affordable_sizing, nomisma_temporary_task09_20_early_exits_eight_rules, nomisma_temporary_task09_20_holding_period_timer_only, nomisma_temporary_task09_20_cross_stock_15m_timer_deadline, nomisma_temporary_task09_20_six_rules_six_stocks_cohort [INFERRED 0.95]
- **Prespecification and independent validation requirements** — nomisma_temporary_task09_18_chronological_validation, nomisma_temporary_task09_19_evidence_expansion, nomisma_temporary_stage1_registered_priorities, nomisma_temporary_research_findings_and_questions_entry_quality [INFERRED 0.95]

## Communities (147 total, 32 thin omitted)

### Community 0 - "app.js"
Cohesion: 0.10
Nodes (80): addSymbol(), api(), applyJob(), avatar(), average(), bindEvents(), booleanFields, bootstrap() (+72 more)

### Community 1 - "simultaneous_session_bounds"
Cohesion: 0.17
Nodes (9): collections, audit_replay(), Research diagnostics; neither parameter selection nor a trading service. The…, Retain every decision/order and distinguish impossible entry intervals., Paired circular blocks within each disjoint validation fold. panel: {policy_id:…, simultaneous_session_bounds(), FunnelTests, InferenceTests (+1 more)

### Community 2 - "planner_check.py"
Cohesion: 0.06
Nodes (51): build_all_in_plan(), Reuse frozen market/geometry validation, then size only by settled cash.…, Live monitor orchestration, event reconciliation, and durable setup alerts., evaluate_plan(), freeze_plan(), Planner, Local research planning service; never submits or manages broker orders., Evaluate with a separate, explicitly synthetic account clock for demos. A… (+43 more)

### Community 3 - "live.js"
Cohesion: 0.08
Nodes (69): accept(), acknowledge(), applyDiscoveryJob(), bind(), candidateSelection(), candleBody(), candleChart(), candleHover() (+61 more)

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
Cohesion: 0.20
Nodes (6): _d(), _finite(), Any, Decimal, _quote_valid(), _Replay

### Community 8 - "live_data.py"
Cohesion: 0.14
Nodes (22): concurrent_futures, _credentials(), extended_day_volumes(), _get_json(), _history(), load_live_seed(), load_snapshots(), _LoadStop (+14 more)

### Community 9 - "cash_calendar.py"
Cohesion: 0.16
Nodes (20): dataclasses, create_calendar(), _dates(), _day(), _digest(), load_calendar(), _path(), _provider_rows() (+12 more)

### Community 10 - "row"
Cohesion: 0.11
Nodes (6): fixture(), IntradayVolumeTests, PriceAndFloatTests, Hand-checked intraday calculations and alert safety boundaries; no I/O., row(), SetupSafetyTests

### Community 11 - "server.py"
Cohesion: 0.12
Nodes (26): base64, contextlib, datetime, http_client, http_server, io, mimetypes, csv_export() (+18 more)

### Community 12 - "json"
Cohesion: 0.15
Nodes (19): gzip, hashlib, importlib_util, itertools, json, Immutable all-in replay checkpoints and source identity contracts., Checkpoint behavior protects reproducibility of the expensive offline sweep., Catalog lineage, selective loading, and bounded acquisition contracts. (+11 more)

### Community 13 - "run_catalog_all_in"
Cohesion: 0.10
Nodes (28): effective_policy(), Path, Stream one predeclared fixed exit policy through settled-cash sessions., run_catalog_all_in(), _aggregate(), compare_candidates(), compact(), compare_metrics() (+20 more)

### Community 14 - "screen"
Cohesion: 0.05
Nodes (38): _atr(), _clamp(), _date(), _ema(), _filter_failures(), _metadata(), _metrics(), _percent() (+30 more)

### Community 15 - "replay.py"
Cohesion: 0.18
Nodes (19): bisect, copy, decimal, heapq, math, Cash-only requested sizing and three causal exit policies, offline only. This…, Immutable development catalogs and bounded session-by-session acquisition. This…, Versioned offline development comparison over immutable session catalogs.… (+11 more)

### Community 16 - "market"
Cohesion: 0.06
Nodes (20): AllInIntegrationTests, AllInSizingTests, engine(), enter(), observe(), plan(), ProtectiveExitTests, CashAccountingTests (+12 more)

### Community 17 - "host.py"
Cohesion: 0.15
Nodes (22): argparse, errno, logging, choose_port(), launch_lock(), main(), _matches(), Own one local service; release database handles when the app exits. The HTTP… (+14 more)

### Community 18 - "Application"
Cohesion: 0.14
Nodes (3): Application, loop(), Replace the radar's symbols with the search's top results; an active monitor…

### Community 19 - "quote"
Cohesion: 0.25
Nodes (10): _iso(), _ns(), Stable per-nanosecond snapshot: the last provider ordinal wins., Parse UTC nanoseconds without float timestamps or microsecond loss., Replay all archived sessions and cohort symbols chronologically, offline., _records(), run_replay(), dataset() (+2 more)

### Community 20 - "discovery_data.py"
Cohesion: 0.14
Nodes (27): build_universe(), delisted(), delisted_check(), fetch_grouped(), fetch_minutes(), fetch_tickers(), _load(), manifest() (+19 more)

### Community 21 - "AppDelegate"
Cohesion: 0.08
Nodes (19): AppDelegate, Process, Notification, NSApplicationDelegate, NSButton, NSMenuItemValidation, NSObject, NSProgressIndicator (+11 more)

### Community 22 - "_GuardedReplay"
Cohesion: 0.13
Nodes (9): _GuardedReplay, Any, Additional observer/control hooks; frozen execution methods stay intact., drain(), engine(), GuardControlTests, LiquidationEquityTests, observe() (+1 more)

### Community 23 - "math"
Cohesion: 0.33
Nodes (6): Completed tasks and evidence, math, Next steps, Pitfalls, Scope and current status, Unresolved findings and stuck problems

### Community 24 - "providers.py"
Cohesion: 0.12
Nodes (26): _parse(), Stocks-only eligibility from Nasdaq Trader's public symbol directories.…, Return a fresh verified stock allowlist; never send provider credentials., require_stocks(), stock_symbols(), fetch_candles(), Latest OHLCV bars (or those before an ISO time) at one timeframe, extended…, _asset_metadata() (+18 more)

### Community 25 - "ApplicationTests"
Cohesion: 0.09
Nodes (5): default_settings(), validate_settings(), ApplicationTests, SettingsTests, patch

### Community 26 - "LiveMonitor"
Cohesion: 0.19
Nodes (5): LiveMonitor, on_status(), Repair missing minute history without rolling back newer events., Only complete, contiguous future windows from matching provenance., utcnow()

### Community 27 - "discovery_replay.py"
Cohesion: 0.14
Nodes (23): _bootstrap_low(), candle(), _cutoff(), day_context(), net_r(), outcome(), Minute-bar replay and cost sweep for the discovery study (spec step 6). Entry…, Stock-day features known at the open: opening gap and premarket dollar volume. (+15 more)

### Community 28 - "MonitorTests"
Cohesion: 0.11
Nodes (3): demo_bundle(), A reproducible historical simulation, advancing one minute per step. The…, MonitorTests

### Community 29 - "build_windows.py"
Cohesion: 0.17
Nodes (26): build(), compile_installer(), copy_backend(), download_verified(), extract_verified_archive(), main(), prepare_python(), preserve_licenses() (+18 more)

### Community 30 - "Store"
Cohesion: 0.16
Nodes (3): A transactionally consistent SQLite snapshot, even during a scan., Validate fully, retain a safety copy, then atomically restore rows. The caller…, Store

### Community 31 - ".prepare_stream"
Cohesion: 0.11
Nodes (3): timestamp(), during_request(), during_request()

### Community 32 - "ResearchDataTests"
Cohesion: 0.11
Nodes (6): calendar(), requester(), ResearchDataTests, limited(), checked(), stream()

### Community 33 - "research.py"
Cohesion: 0.18
Nodes (21): _stamp(), _calendar(), _candidate(), default_discovery(), diagnose(), discover(), _extend_missing_day_volume(), _phase() (+13 more)

### Community 34 - "browser_check.py"
Cohesion: 0.13
Nodes (16): inside_polygon(), main(), png(), Rebuild Nomisma.ico from the app's simple N monogram (stdlib only)., check_candidate_metrics(), check_metric_columns(), check_metric_null_sorting(), check_mobile_candidate_scrolling() (+8 more)

### Community 35 - "tools/all_in_replay.py"
Cohesion: 0.23
Nodes (11): source_hashes(), source_hashes(), Write a pretty-printed JSON file that must not already exist., write_new(), execute(), main(), Run one immutable offline all-in settled-cash exit-policy comparison., execute() (+3 more)

### Community 36 - ".webView"
Cohesion: 0.11
Nodes (16): Any, String, UNAuthorizationStatus, UNNotification, UNNotificationPresentationOptions, UNNotificationResponse, UNUserNotificationCenter, Void (+8 more)

### Community 37 - "launch.py"
Cohesion: 0.15
Nodes (10): check_workspace(), health(), launch(), main(), port_available(), port_open(), Start or reuse this local workspace, then open its ready browser interface., Check a local bind without Windows' refused-connection timeout. Windows needs… (+2 more)

### Community 39 - "WebSocketTests"
Cohesion: 0.19
Nodes (4): FakeSocket, frame(), sent_frame(), WebSocketTests

### Community 40 - "Historical replay pilot"
Cohesion: 0.25
Nodes (7): Archived inputs and historical clock, Frozen development experiment, Historical replay pilot, Later research, Required evidence, Running the pilot, Simulated orders and shared portfolio

### Community 42 - "prepare_plan_inputs"
Cohesion: 0.27
Nodes (4): prepare_plan_inputs(), Validate original alert evidence; return diagnostics and a finite schema. No…, fixture(), PlanningInputTests

### Community 43 - "StorageTests"
Cohesion: 0.14
Nodes (4): demo_dataset(), An explicitly synthetic, reproducible historical research playground., StorageTests, record_connection()

### Community 44 - "ReplayDataTests"
Cohesion: 0.14
Nodes (4): fixture(), ReplayDataTests, malformed(), count()

### Community 45 - "run"
Cohesion: 0.25
Nodes (5): check_alert_refresh(), check_live(), Exercise real browser events against the isolated synthetic monitor., Explicit refresh must work even when the background event stream is idle., run()

### Community 46 - "calibrate.py"
Cohesion: 0.19
Nodes (22): generate_candidates(), Path, Exact parity projection: omit only known provenance/fingerprint changes., Return exactly 27 independent configs, changing only the three grid keys., Preserve one engine/account across lazily verified chronological sessions. Only…, replay_source_sha256(), run_catalog(), semantic_result() (+14 more)

### Community 47 - "SDL.md - SDL-MCP Agent Workflow"
Cohesion: 0.17
Nodes (11): 1. Start Every Task, 4. Runtime Output Control, 5. Memory And Indexing, 6. Delegated Exploration, 7. Hook Enforcement, 9. Anti-Patterns, Execute First, Query Only Needed Output (+3 more)

### Community 48 - "build_desktop.py"
Cohesion: 0.20
Nodes (20): build(), build_icon(), clean_python_environment(), copy_backend(), copy_python(), install_bundle(), mach_o_files(), main() (+12 more)

### Community 49 - "Proposed validation and parameter-calibration plan"
Cohesion: 0.29
Nodes (7): Chronological selection and untouched holdout, Exposed development leader k1-r2.5-h30, Eligibility and fill funnel audit, The Probability of Backtest Overfitting, Proposed validation and parameter-calibration plan, SES and TE admission rejections, Outcome-selected exit rules and dependent comparisons

### Community 50 - "monitor_metrics.py"
Cohesion: 0.17
Nodes (23): _number(), True for a finite non-bool int/float within [minimum, maximum]., build_rows(), _daily(), _date(), _fresh(), _minutes(), _ohlcv() (+15 more)

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

### Community 56 - "pool.py"
Cohesion: 0.13
Nodes (15): hmac, LiveSubscriptionLimit, A rejected symbol list needs user action, not repeated reconnection., _symbols(), _Handler, _line(), Pool, Share one Alpaca stream between workstations. Alpaca allows one real-time… (+7 more)

### Community 57 - "check_alert_source_isolation"
Cohesion: 0.33
Nodes (4): check_alert_source_isolation(), inbox(), mark_all(), Persist both sources without starting a market connection or altering earlier…

### Community 58 - "planner.js"
Cohesion: 0.33
Nodes (5): metric(), render(), showAlert(), toggleBusy(), updateExpiry()

### Community 59 - "Linear drift term κ(θ − v) dt"
Cohesion: 0.18
Nodes (12): Cox–Ingersoll–Ross square-root process, dv = κ(θ − v) dt + ξ√v dW, Possible Heston variance-process interpretation, Drift coefficient κ, Linear drift term κ(θ − v) dt, Mean reversion toward θ when κ > 0, Nonnegative domain required by real-valued √v, State-dependent diffusion term ξ√v dW (+4 more)

### Community 60 - "Nomisma research handoff — October 6, 2026"
Cohesion: 0.14
Nodes (14): Completed experiment, Coordination and retrieval instructions, Current tasks and status, Formula versions, IBKR Pro Fixed sensitivity, Nomisma research handoff — October 6, 2026, Pitfalls for the next coordinator, Recommended next steps (+6 more)

### Community 61 - "Intraday monitoring implementation contract"
Cohesion: 0.29
Nodes (7): Config (metrics module validates; defaults exported), Intraday monitoring implementation contract, Metrics module public API, Normalized provider bundle, Ownership, Provider module public API, UI

### Community 62 - "Microsoft.Web.WebView2"
Cohesion: 0.25
Nodes (10): dependencies, net10.0-windows7.0, net10.0-windows7.0/win-x64, contentHash, requested, resolved, type, Microsoft.Web.WebView2 (+2 more)

### Community 63 - "Nomisma — first discovery study"
Cohesion: 0.09
Nodes (22): Acquisition sequence and gates, Candle features (frozen), Condition search (post hoc), Continuation outcome, Data sources, Entry comparison, Evaluation, Execution (+14 more)

### Community 64 - "Consolidated research findings and questions"
Cohesion: 0.21
Nodes (15): Current simulated research scope, Consolidated research findings and questions, Registered research priorities and unresolved requirements, Stage 1 consolidated research synthesis, Cross-stock fifteen-minute qualifying-entry study, Fifteen-minute exit-request deadline, Exposed pre-close analysis and incomplete adverse marks, Holding-period investigation (+7 more)

### Community 65 - "All-in cash-account simulation and exit comparison"
Cohesion: 0.40
Nodes (5): All-affordable settled-cash sizing, breakeven_1atr exit policy, fixed_15m exit policy, All-in cash-account simulation and exit comparison, trail_1atr exit policy

### Community 66 - ".isTrusted"
Cohesion: 0.24
Nodes (4): Bool, NSApplication, NSMenuItem, WKFrameInfo

### Community 67 - "_check_stop"
Cohesion: 0.24
Nodes (6): _Cancelled, _check_stop(), report(), ValueError, Fixed-host, TLS-only websocket with bounded/cancellable wire parsing., _WebSocket

### Community 68 - "Nomisma"
Cohesion: 0.14
Nodes (14): Alert evidence and observed outcomes, Alerts and keeping the monitor running, Built-in trade planner, Connect real-time market data, Daily market data, Daily operation, Daily score, Daily screener workflow (+6 more)

### Community 69 - "Linear drift term θ(μ − z) dt"
Cohesion: 0.22
Nodes (10): Additive diffusion term σ dW, dz = θ(μ − z) dt + σ dW, Linear drift term θ(μ − z) dt, Mean reversion toward μ when θ > 0, Reference level μ, Ornstein–Uhlenbeck process, Diffusion coefficient σ, State variable z (+2 more)

### Community 70 - "Exponential term αe^(−β(t − tᵢ))"
Cohesion: 0.20
Nodes (10): Amplitude parameter α, Additive baseline μ, Exponent coefficient β, Exponential decay of positive contributions when β > 0, λ(t) = μ + ∑ αe^(−β(t − tᵢ)), Exponential term αe^(−β(t − tᵢ)), Exponential-kernel Hawkes intensity interpretation, Possible restriction to past events tᵢ < t (+2 more)

### Community 71 - "Historical replay pilot and account-model updates"
Cohesion: 0.15
Nodes (16): Prospective recording and clock uncertainty, Running-peak drawdown guard and unknown equity, Frozen historical replay pilot, Empty admissible entry-price interval, Momentum score 85 and entry extension, Cash-account loss diagnosis, Fifty-share planning liquidity cap, Historical replay pilot and account-model updates (+8 more)

### Community 72 - "Nomisma for Windows 11 Pro"
Cohesion: 0.18
Nodes (11): Alert source fix in 1.2.2, Build locally, Candidate freshness fixes in 1.2.3, Download and install, Intraday improvements in 1.2.0, Mobile table fix in 1.2.1, Nomisma for Windows 11 Pro, Publish clean source to GitHub (+3 more)

### Community 73 - "Subtracted adjustment qγσ²(T − t)"
Cohesion: 0.22
Nodes (9): Subtracted adjustment qγσ²(T − t), Avellaneda–Stoikov reservation-price interpretation, Baseline value s, Conditional linear shift from the baseline, r = s − qγσ²(T − t), Multiplier γ, Multiplier q, Squared parameter σ² (+1 more)

### Community 77 - "discovery_signals.py"
Cohesion: 0.15
Nodes (17): csv, atr14(), by_day(), _calendar(), opportunities(), pilot(), Opportunity detection for the first discovery study (DISCOVERY_STUDY_SPEC.md).…, Alpaca exchange calendar for the discovery period, archived once as raw bytes. (+9 more)

### Community 78 - "replay_data.py"
Cohesion: 0.20
Nodes (14): _Archive, _bars(), _basis(), download_dataset(), _events(), _http(), _now(), Immutable, offline historical replay archives; no monitor or order interfaces.… (+6 more)

### Community 79 - "App.swift"
Cohesion: 0.29
Nodes (5): AppKit, Foundation, NomismaApplication, UserNotifications, WebKit

### Community 80 - "_canonical"
Cohesion: 0.18
Nodes (16): _catalog_digest(), create_catalog(), download_development(), iter_sessions(), load_catalog(), _new_directory(), Read and validate metadata/lineage only; never read session outcomes., Yield one verified requested development session at a time. Omitted dates means… (+8 more)

### Community 83 - "history_metrics"
Cohesion: 0.24
Nodes (8): _bars(), _date(), history_metrics(), Pure historical liquidity/volatility measurements and transparent ranking.…, Compute completed-session metrics; callers may supply the exchange's prior…, daily_bars(), HistoricalMetricTests, Offline metric formulas, missing-history behavior, and ranking coverage.

### Community 84 - "Earlier profit-taking investigation"
Cohesion: 0.20
Nodes (10): ATR payoff geometry versus hit probability, FTFT September 14 breakout reversal, Cost-adjusted exit formulas, Eight earlier-exit counterfactuals, FINRA order-types guide, Early-exit payoff and admission mismatch, Earlier profit-taking investigation, SEC stop-order bulletin (+2 more)

### Community 87 - "make_catalog"
Cohesion: 0.25
Nodes (5): make_catalog(), StreamingTests, two_sessions(), account_config(), AdapterTests

### Community 88 - "Entry quality as the next research priority"
Cohesion: 0.50
Nodes (4): Entry quality as the next research priority, Unresolved selection for one shared account, First feasible confirmed-alert selection, Eleven entries and ten added losing opportunities

### Community 91 - "Monitoring and screening methodology"
Cohesion: 0.14
Nodes (14): Alert confirmation, repeats, and delivery, Daily screener: indicators and timing, Daily screener: score composition, Interpretation limits, Intraday score and indicators, Intraday session and price timing, Intraday volume, gap, and float, Liquidity and volatility metrics (+6 more)

### Community 92 - "validate_monitor_config"
Cohesion: 0.33
Nodes (3): Return a fresh validated configuration; never coerce numeric strings., validate_monitor_config(), MonitorConfigTests

### Community 93 - "check_windows.py"
Cohesion: 0.23
Nodes (15): check(), clean_environment(), main(), port_closed(), Path, Retain only timing diagnostics, even if native verification failed., Verify Windows release artifacts on a clean Windows test account. Installs,…, Verify exactly one installer/archive pair before executing any package. (+7 more)

### Community 96 - "test_cash_calendar.py"
Cohesion: 0.26
Nodes (5): archive(), calendar(), CashCalendarTests, Settlement follows archived provider dates, with no trading-day extrapolation., row()

### Community 97 - "Nomisma.Windows.csproj"
Cohesion: 0.50
Nodes (3): net10.0-windows, Microsoft.Web.WebView2 (1.0.4191.47), Microsoft.NET.Sdk

### Community 98 - "research_data.py"
Cohesion: 0.19
Nodes (18): acquire_preflight(), _Budget, capture_metadata(), _error_code(), _new_directory(), Bounded read-only research acquisition, separate from all trading services.…, Bounded callback capture with hashed start, attempt and terminal evidence. Byte…, Verify transport coverage, limits and receipt provenance from hashed rows. (+10 more)

### Community 99 - "test_discovery_replay.py"
Cohesion: 0.24
Nodes (5): bars(), OutcomeTest, Entry gating, deadline exit and wick exit of the discovery replay on synthetic…, ReclaimTest, TradeTest

### Community 101 - "test_desktop_host.py"
Cohesion: 0.20
Nodes (9): desktop, SourceExportTests, allowed_source(), export_source(), main(), Export current Nomisma source for a fresh GitHub repository, without history.…, subprocess, urllib_parse (+1 more)

### Community 104 - "_json"
Cohesion: 0.24
Nodes (3): _AllInReplay, Observe equity/drawdown without any threshold, budget or latch., _json()

### Community 106 - ".handle"
Cohesion: 0.15
Nodes (17): quote_sample(), Step 4 disk projection: Alpaca SIP quotes and trades for sampled listed primary…, The only gate to study data; holdout stays sealed until finalists are committed., readable(), conditions(), exit_variants(), export_losers(), managed_trade() (+9 more)

### Community 107 - "hypotheses"
Cohesion: 0.18
Nodes (14): _day_bars(), _half_spread(), hypotheses(), _net(), quote_name(), Alpaca RFC 3339 timestamp (nanoseconds, Z) to an aware datetime., Relative half-spread of the NBBO in force at moment (else the first valid quote…, Cached half-spread lookup at a New York minute; raw Alpaca SIP quotes are… (+6 more)

### Community 108 - "test_replay.py"
Cohesion: 0.32
Nodes (7): _config(), accounting_engine(), accounting_plan(), AccountingTests, observe(), Behavioral evidence for the offline replay's chronology and accounting., Advance the artificial clock to the next modeled quote observation.

### Community 109 - "All-in cash allocation and exit comparison — September 20, 2026"
Cohesion: 0.25
Nodes (8): All-in cash allocation and exit comparison — September 20, 2026, Authorized change and scope, Causal event ordering, Entry allocation and actual execution, Equity observation with no account drawdown control, Required checks and bounded execution, Review and attribution, Three fixed exit policies

### Community 110 - "Nomisma implementation contract"
Cohesion: 0.25
Nodes (8): Built-in planner API, Data (`nomisma/providers.py`), Engine (`nomisma/engine.py`), Nomisma implementation contract, Other research extensions, Research and workspace extensions, Server API (root implements), UI (frontend agent owns static files)

### Community 111 - "Cash-account allocation pilot, 18 September 2026"
Cohesion: 0.25
Nodes (7): Cash-account allocation pilot, 18 September 2026, Cash and settlement, Feasibility and causal selection, Primary rule references, Purpose and scope, Sizing and registered comparisons, Validation and reporting

### Community 112 - ".snapshot"
Cohesion: 0.22
Nodes (7): Monitor service and browser API (root), live_provider_status(), MonitorBusy, ValueError, Reload the active source without restarting the stream or alert tracker., get(), get()

### Community 114 - "Research follow-through, 18 September 2026"
Cohesion: 0.29
Nodes (6): Conditional liquidation equity and guard, Confirmed account constraint, Data stages and evidence limits, Decision funnel and parameter evidence, Research follow-through, 18 September 2026, Verification and resource profile

### Community 115 - "Built-in intraday research planner"
Cohesion: 0.29
Nodes (7): Affine fees and robust sizing, Built-in intraday research planner, In the app, Inputs and data provenance, Mathematics, Output states, Validation and remaining research

### Community 116 - "Historical replay calibration: development experiment v1"
Cohesion: 0.33
Nodes (5): Frozen experiment, Historical replay calibration: development experiment v1, Replay and scoring, Selection and sensitivity, Verification

### Community 118 - "_cancellable_call"
Cohesion: 0.20
Nodes (8): _cancellable_call(), fetch_float(), load_floats(), load_one(), _NoFloatRedirect, HTTPRedirectHandler, Stop promptly without changing the existing fixed-host GET transport. Its…, Return actual, provider-dated float shares; never substitute outstanding.

### Community 119 - "Q: Give a concise overview of heuresis, its purpose, main components, architecture, and workflows"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Give a concise overview of heuresis, its purpose, main components, architecture, and workflows, Source Nodes

### Community 120 - "._validate_backup"
Cohesion: 0.38
Nodes (6): Read only known table data; never execute schema from an upload., decode(), finite(), invalid(), discovery_job(), stamp()

### Community 121 - "Sharing one Alpaca feed between two machines"
Cohesion: 0.25
Nodes (8): Before you start, Daily order, Machine A — runs the pool and uses the data, Machine B — uses the data, Security, Sharing one Alpaca feed between two machines, Troubleshooting, What to expect

### Community 125 - "test_planning_data.py"
Cohesion: 0.31
Nodes (3): quote_at(), QuoteCaptureTests, Causal input evidence, quantity conventions and explicit rejection paths.

### Community 126 - "PoolTest"
Cohesion: 0.31
Nodes (3): fake_stream(), PoolTest, on_event()

### Community 127 - "TRADE_PLANNER.md"
Cohesion: 0.23
Nodes (4): Build or update, Native controls, Nomisma for macOS, Troubleshooting

### Community 128 - "Massive"
Cohesion: 0.29
Nodes (4): Massive, _NoRedirect, HTTPRedirectHandler, Paced GET transport returning raw response bytes.

### Community 129 - "Nomisma agent coordination"
Cohesion: 0.22
Nodes (7): Delegation procedure, Final reporting, Main agent responsibilities, Nomisma agent coordination, Task routing, Trading boundaries, Workflow for substantial strategy changes

### Community 130 - "Handoff: Nomisma discovery study, 2026-10-22"
Cohesion: 0.22
Nodes (8): Completed, First study: the 39 losers on the arm c, gap ≥40% candidate, Handoff: Nomisma discovery study, 2026-10-22, Locations, Pitfalls, Second study: pre-registered H1 and H2, scored once on 2026-10-22, Stuck or open, Where things stand

### Community 131 - "replay_pilot.py"
Cohesion: 0.33
Nodes (8): canonical(), load_dataset(), Read only, verify every archived artifact before returning dataset., default_replay_config(), An explicit artificial account/cost fixture, never user preferences., main(), Archive and replay a declared historical research cohort; never places orders., source_hashes()

### Community 132 - "rank_rows"
Cohesion: 0.47
Nodes (3): rank_rows(), Assign cross-sectional ranks without hiding rows or changing input order.…, RankingTests

### Community 134 - "AGENTS.md"
Cohesion: 0.33
Nodes (3): Code-context workflow, Claude in heuresis, Codex in heuresis

### Community 135 - "_confirmation"
Cohesion: 0.29
Nodes (4): _confirmation(), Session-scoped monitor confirmation without persistence or wall clock., ContractTests, evaluate()

### Community 136 - "Research extensions (September 2026)"
Cohesion: 0.47
Nodes (3): Research extensions (September 2026), Signals, 8. Completion Checklist

### Community 140 - "2. Retrieval Ladder"
Cohesion: 0.33
Nodes (6): 2. Retrieval Ladder, Batched Escalation, Edit Planning Slice, Exploratory Context, Focused Context, Last-Resort Window

### Community 142 - "3. File And Edit Rules"
Cohesion: 0.40
Nodes (5): 3. File And Edit Rules, Batch Indexed Source Edit, Non-Indexed Reads, Non-Indexed Writes, One-Symbol Indexed Source Edit

## Ambiguous Edges - Review These
- `Possible Heston variance-process interpretation` → `dv = κ(θ − v) dt + ξ√v dW`  [AMBIGUOUS]
  nomisma/reference/HSK3howbMAARiJ9.jpeg · relation: conceptually_related_to
- `Possible restriction to past events tᵢ < t` → `Sum of exponential contributions`  [AMBIGUOUS]
  nomisma/reference/HSK5WZCbAAEW2Ic.jpeg · relation: conceptually_related_to

## Knowledge Gaps
- **213 isolated node(s):** `AppKit`, `Foundation`, `WebKit`, `UserNotifications`, `ExitCode` (+208 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 776 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **32 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Possible Heston variance-process interpretation` and `dv = κ(θ − v) dt + ξ√v dW`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `Possible restriction to past events tᵢ < t` and `Sum of exponential contributions`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `Intraday monitoring implementation contract` connect `Intraday monitoring implementation contract` to `.snapshot`, `Research extensions (September 2026)`, `TRADE_PLANNER.md`?**
  _High betweenness centrality (0.136) - this node is a cross-community bridge._
- **Why does `Research extensions (September 2026)` connect `Research extensions (September 2026)` to `.snapshot`, `history_metrics`, `rank_rows`, `Intraday monitoring implementation contract`?**
  _High betweenness centrality (0.124) - this node is a cross-community bridge._
- **Why does `Historical replay pilot and account-model updates` connect `Historical replay pilot and account-model updates` to `Consolidated research findings and questions`, `Historical replay pilot`, `Cash-account allocation pilot, 18 September 2026`, `Research follow-through, 18 September 2026`, `TRADE_PLANNER.md`?**
  _High betweenness centrality (0.066) - this node is a cross-community bridge._
- **Are the 9 inferred relationships involving `Application` (e.g. with `LiveMonitor` and `Planner`) actually correct?**
  _`Application` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `MonitorTests` (e.g. with `LiveSubscriptionLimit` and `LiveMonitor`) actually correct?**
  _`MonitorTests` has 4 INFERRED edges - model-reasoned connections that need verification._