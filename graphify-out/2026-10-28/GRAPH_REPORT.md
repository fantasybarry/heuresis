# Graph Report - heuresis  (2026-10-28)

## Corpus Check
- 145 files · ~192,879 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 27 file(s) not represented in the graph (top: .toml 6, (none) 3, .css 3)

## Summary
- 2500 nodes · 6056 edges · 143 communities (108 shown, 35 thin omitted)
- Extraction: 96% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 246 edges (avg confidence: 0.87)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `c3ed4486`
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
- quote
- live_data.py
- cash_calendar.py
- row
- json
- _Replay
- run_catalog
- screen
- replay.py
- market
- _AllInReplay
- Application
- engine
- discovery_data.py
- AppDelegate
- _GuardedReplay
- server.py
- fetch_alpaca
- ApplicationTests
- LiveMonitor
- discovery_replay.py
- MonitorTests
- build
- Store
- .prepare_stream
- ResearchDataTests
- research.py
- check_metric_null_sorting
- tools/all_in_replay.py
- .webView
- engine
- _canonical
- WebSocketTests
- launch
- DesktopHostTests
- make_handler
- StorageTests
- ReplayDataTests
- session_metrics
- calibrate.py
- SDL.md - SDL-MCP Agent Workflow
- build_desktop.py
- replay_pilot.py
- monitor_metrics.py
- cash_result
- WindowsBuildTests
- AlpacaTests
- .download
- bridge.test.cjs
- pool.py
- download_dataset
- planner.js
- Linear drift term κ(θ − v) dt
- Nomisma research handoff — October 6, 2026
- test_cash_calendar.py
- Microsoft.Web.WebView2
- Nomisma — first discovery study
- Consolidated research findings and questions
- check_windows.py
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
- replay
- _json
- App.swift
- real_spreads
- DesktopNotification
- .wait_for_refresh
- Earlier profit-taking investigation
- DesktopBuildTests
- InstrumentTests
- make_catalog
- WindowsVerificationTests
- TransportTests
- Workspace shell and research navigation
- Monitoring and screening methodology
- demo_bundle
- parent_archive
- planner_check.py
- CheckpointTests
- run
- Nomisma.Windows.csproj
- research_data.py
- test_discovery_replay.py
- AllInCliTests
- CashCliTests
- _StreamEvidence
- Windows x64 build and verification
- _symbol
- .handle
- DevTools
- opportunities
- All-in cash allocation and exit comparison — September 20, 2026
- Nomisma implementation contract
- Cash-account allocation pilot, 18 September 2026
- Historical replay pilot
- DiscoveryScheduleTests
- Research follow-through, 18 September 2026
- Built-in intraday research planner
- Historical replay calibration: development experiment v1
- Completed experiment
- generate_icon.py
- Q: Give a concise overview of heuresis, its purpose, main components, architecture, and workflows
- ._validate_backup
- Sharing one Alpaca feed between two machines
- Replay
- Heuresis
- settings-dialog
- check_alert_source_isolation
- PoolTest
- Massive
- Proposed validation and parameter-calibration plan
- All-in cash-account simulation and exit comparison
- Nomisma for macOS
- CashReplayIntegrationTests
- stream_live
- validate_discovery_settings
- .snapshot
- 4. Runtime Output Control
- MonitorHTTPTests
- math
- CalendarTests
- Entry quality as the next research priority
- CandidateTests
- CandleTests

## God Nodes (most connected - your core abstractions)
1. `Application` - 64 edges
2. `AppDelegate` - 58 edges
3. `MonitorTests` - 54 edges
4. `row()` - 44 edges
5. `fixture()` - 43 edges
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

## Communities (143 total, 35 thin omitted)

### Community 0 - "app.js"
Cohesion: 0.10
Nodes (80): addSymbol(), api(), applyJob(), avatar(), average(), bindEvents(), booleanFields, bootstrap() (+72 more)

### Community 1 - "simultaneous_session_bounds"
Cohesion: 0.22
Nodes (6): audit_replay(), Retain every decision/order and distinguish impossible entry intervals., Paired circular blocks within each disjoint validation fold. panel: {policy_id:…, simultaneous_session_bounds(), FunnelTests, InferenceTests

### Community 2 - "trade_plan.py"
Cohesion: 0.07
Nodes (40): build_all_in_plan(), Reuse frozen market/geometry validation, then size only by settled cash.…, Planner, _base(), build_trade_plan(), _calculate(), target(), default_plan_settings() (+32 more)

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
Nodes (10): calendar(), DiagnosticTests, DiscoveryTests, get(), get(), history(), get(), dict (+2 more)

### Community 7 - "quote"
Cohesion: 0.15
Nodes (18): _confirmation(), _iso(), _ns(), Session-scoped monitor confirmation without persistence or wall clock., Parse UTC nanoseconds without float timestamps or microsecond loss., Replay all archived sessions and cohort symbols chronologically, offline., run_replay(), accounting_engine() (+10 more)

### Community 8 - "live_data.py"
Cohesion: 0.18
Nodes (19): _credentials(), extended_day_volumes(), fetch_candles(), _get_json(), _history(), load_live_seed(), load_snapshots(), _LoadStop (+11 more)

### Community 9 - "cash_calendar.py"
Cohesion: 0.17
Nodes (18): create_calendar(), _dates(), _day(), load_calendar(), _path(), _provider_rows(), Offline, explicitly bounded settlement dates from an archived Alpaca calendar.…, Validated immutable mapping. Construct through :func:`load_calendar`. (+10 more)

### Community 10 - "row"
Cohesion: 0.11
Nodes (6): fixture(), IntradayVolumeTests, PriceAndFloatTests, Hand-checked intraday calculations and alert safety boundaries; no I/O., row(), SetupSafetyTests

### Community 11 - "json"
Cohesion: 0.12
Nodes (27): contextlib, gzip, http_client, http_server, importlib_util, json, evaluate_plan(), Evaluate with a separate, explicitly synthetic account clock for demos. A… (+19 more)

### Community 12 - "_Replay"
Cohesion: 0.16
Nodes (10): _config(), _d(), _fingerprint(), _finite(), Any, Decimal, _quote_valid(), Stable per-nanosecond snapshot: the last provider ordinal wins. (+2 more)

### Community 13 - "run_catalog"
Cohesion: 0.15
Nodes (21): iter_sessions(), load_catalog(), Read and validate metadata/lineage only; never read session outcomes., Yield one verified requested development session at a time. Omitted dates means…, _safe_file(), _validate_dates(), _validate_session(), _dates() (+13 more)

### Community 14 - "screen"
Cohesion: 0.11
Nodes (24): collections, _atr(), _clamp(), _date(), _ema(), _filter_failures(), _metadata(), _metrics() (+16 more)

### Community 15 - "replay.py"
Cohesion: 0.17
Nodes (20): bisect, copy, decimal, hashlib, heapq, itertools, Cash-only requested sizing and three causal exit policies, offline only. This…, Immutable development catalogs and bounded session-by-session acquisition. This… (+12 more)

### Community 16 - "market"
Cohesion: 0.14
Nodes (5): market(), NumericalFixtureTests, PlanStateTests, settings(), ValidationTests

### Community 18 - "Application"
Cohesion: 0.11
Nodes (7): Exception, provider_status(), Return connection readiness, never keys or other credential values., Application, loop(), BusyError, Replace the radar's symbols with the search's top results; an active monitor…

### Community 19 - "engine"
Cohesion: 0.22
Nodes (8): AllInIntegrationTests, AllInSizingTests, engine(), enter(), observe(), plan(), ProtectiveExitTests, drain()

### Community 20 - "discovery_data.py"
Cohesion: 0.14
Nodes (27): build_universe(), delisted(), delisted_check(), fetch_grouped(), fetch_minutes(), fetch_tickers(), _load(), manifest() (+19 more)

### Community 21 - "AppDelegate"
Cohesion: 0.08
Nodes (19): AppDelegate, Process, Notification, NSApplicationDelegate, NSButton, NSMenuItemValidation, NSObject, NSProgressIndicator (+11 more)

### Community 22 - "_GuardedReplay"
Cohesion: 0.13
Nodes (9): _GuardedReplay, Any, Additional observer/control hooks; frozen execution methods stay intact., drain(), engine(), GuardControlTests, LiquidationEquityTests, observe() (+1 more)

### Community 23 - "server.py"
Cohesion: 0.09
Nodes (35): csv, datetime, desktop, io, logging, math, mimetypes, Opportunity detection for the first discovery study (DISCOVERY_STUDY_SPEC.md).… (+27 more)

### Community 24 - "fetch_alpaca"
Cohesion: 0.12
Nodes (19): _parse(), Return a fresh verified stock allowlist; never send provider credentials., require_stocks(), stock_symbols(), _asset_metadata(), _bar(), _completed_session(), fetch_alpaca() (+11 more)

### Community 25 - "ApplicationTests"
Cohesion: 0.09
Nodes (5): default_settings(), validate_settings(), ApplicationTests, SettingsTests, patch

### Community 26 - "LiveMonitor"
Cohesion: 0.19
Nodes (5): LiveMonitor, on_status(), Repair missing minute history without rolling back newer events., Only complete, contiguous future windows from matching provenance., utcnow()

### Community 27 - "discovery_replay.py"
Cohesion: 0.12
Nodes (29): candle(), _cutoff(), _day_bars(), exit_variants(), export_losers(), hypotheses(), managed_trade(), _net() (+21 more)

### Community 29 - "build"
Cohesion: 0.17
Nodes (22): build(), compile_installer(), copy_backend(), download_verified(), extract_verified_archive(), prepare_python(), preserve_licenses(), CompletedProcess (+14 more)

### Community 30 - "Store"
Cohesion: 0.15
Nodes (3): A transactionally consistent SQLite snapshot, even during a scan., Validate fully, retain a safety copy, then atomically restore rows. The caller…, Store

### Community 31 - ".prepare_stream"
Cohesion: 0.11
Nodes (3): timestamp(), during_request(), during_request()

### Community 32 - "ResearchDataTests"
Cohesion: 0.11
Nodes (6): calendar(), requester(), ResearchDataTests, limited(), checked(), stream()

### Community 33 - "research.py"
Cohesion: 0.19
Nodes (20): _stamp(), _candidate(), default_discovery(), diagnose(), discover(), _extend_missing_day_volume(), _phase(), _positive() (+12 more)

### Community 34 - "check_metric_null_sorting"
Cohesion: 0.22
Nodes (8): check_candidate_metrics(), check_metric_columns(), check_metric_null_sorting(), check_mobile_candidate_scrolling(), check_workspace_improvements(), Compare real browser ordering with numeric saved result values., Exercise decimal, zero, and unavailable values in an isolated stopped snapshot., Require usable metric space and reachable columns on a narrow screen.

### Community 35 - "tools/all_in_replay.py"
Cohesion: 0.18
Nodes (15): effective_policy(), Path, Stream one predeclared fixed exit policy through settled-cash sessions., run_catalog_all_in(), source_hashes(), source_hashes(), Write a pretty-printed JSON file that must not already exist., write_new() (+7 more)

### Community 36 - ".webView"
Cohesion: 0.11
Nodes (16): Any, String, UNAuthorizationStatus, UNNotification, UNNotificationPresentationOptions, UNNotificationResponse, UNUserNotificationCenter, Void (+8 more)

### Community 37 - "engine"
Cohesion: 0.27
Nodes (6): CashAccountingTests, CashPolicyTests, engine(), fill_entry(), fill_exit(), plan()

### Community 38 - "_canonical"
Cohesion: 0.22
Nodes (12): _catalog_digest(), create_catalog(), download_development(), _new_directory(), Sequentially download a declared development batch using frozen importer.…, Split verified replay archives into one-session files; return catalog path.…, _canonical(), _digest() (+4 more)

### Community 39 - "WebSocketTests"
Cohesion: 0.19
Nodes (4): FakeSocket, frame(), sent_frame(), WebSocketTests

### Community 40 - "launch"
Cohesion: 0.18
Nodes (6): check_workspace(), health(), launch(), main(), port_open(), LauncherTests

### Community 42 - "make_handler"
Cohesion: 0.06
Nodes (36): concurrent_futures, errno, Completed, First study: the 39 losers on the arm c, gap ≥40% candidate, Handoff: Nomisma discovery study, 2026-10-22, Locations, Pitfalls, Second study: pre-registered H1 and H2, scored once on 2026-10-22 (+28 more)

### Community 43 - "StorageTests"
Cohesion: 0.14
Nodes (4): demo_dataset(), An explicitly synthetic, reproducible historical research playground., StorageTests, record_connection()

### Community 44 - "ReplayDataTests"
Cohesion: 0.14
Nodes (4): fixture(), ReplayDataTests, malformed(), count()

### Community 45 - "session_metrics"
Cohesion: 0.21
Nodes (14): _aggregate(), compare_candidates(), compact(), compare_metrics(), _diagnostic_best(), _flat(), _money(), Any (+6 more)

### Community 46 - "calibrate.py"
Cohesion: 0.22
Nodes (20): generate_candidates(), Exact parity projection: omit only known provenance/fingerprint changes., Return exactly 27 independent configs, changing only the three grid keys., semantic_result(), digest(), file_sha256(), Atomically replace a pretty-printed JSON file., sha256() (+12 more)

### Community 47 - "SDL.md - SDL-MCP Agent Workflow"
Cohesion: 0.05
Nodes (31): Code-context workflow, Claude in heuresis, Codex in heuresis, Delegation procedure, Final reporting, Main agent responsibilities, Nomisma agent coordination, Task routing (+23 more)

### Community 48 - "build_desktop.py"
Cohesion: 0.20
Nodes (20): build(), build_icon(), clean_python_environment(), copy_backend(), copy_python(), install_bundle(), mach_o_files(), main() (+12 more)

### Community 49 - "replay_pilot.py"
Cohesion: 0.29
Nodes (9): canonical(), load_dataset(), Read only, verify every archived artifact before returning dataset., default_replay_config(), An explicit artificial account/cost fixture, never user preferences., main(), Archive and replay a declared historical research cohort; never places orders., source_hashes() (+1 more)

### Community 50 - "monitor_metrics.py"
Cohesion: 0.05
Nodes (47): Config (metrics module validates; defaults exported), Intraday monitoring implementation contract, Metrics module public API, Normalized provider bundle, Ownership, Provider module public API, Research extensions (September 2026), UI (+39 more)

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
Nodes (16): hmac, LiveSubscriptionLimit, A rejected symbol list needs user action, not repeated reconnection., _symbols(), _Handler, _line(), Pool, Share one Alpaca stream between workstations. Alpaca allows one real-time… (+8 more)

### Community 57 - "download_dataset"
Cohesion: 0.20
Nodes (11): _Archive, _bars(), _basis(), download_dataset(), _events(), _now(), Infer latest split scale on the replay session, then undo future scale., Download a bounded retrospective cohort; return dataset.json path.… (+3 more)

### Community 58 - "planner.js"
Cohesion: 0.33
Nodes (5): metric(), render(), showAlert(), toggleBusy(), updateExpiry()

### Community 59 - "Linear drift term κ(θ − v) dt"
Cohesion: 0.18
Nodes (12): Cox–Ingersoll–Ross square-root process, dv = κ(θ − v) dt + ξ√v dW, Possible Heston variance-process interpretation, Drift coefficient κ, Linear drift term κ(θ − v) dt, Mean reversion toward θ when κ > 0, Nonnegative domain required by real-valued √v, State-dependent diffusion term ξ√v dW (+4 more)

### Community 60 - "Nomisma research handoff — October 6, 2026"
Cohesion: 0.22
Nodes (9): Coordination and retrieval instructions, Current tasks and status, Nomisma research handoff — October 6, 2026, Pitfalls for the next coordinator, Recommended next steps, Start here, Stuck problems and missing evidence, User requirements and decisions (+1 more)

### Community 61 - "test_cash_calendar.py"
Cohesion: 0.22
Nodes (6): dataclasses, archive(), calendar(), CashCalendarTests, Settlement follows archived provider dates, with no trading-day extrapolation., row()

### Community 62 - "Microsoft.Web.WebView2"
Cohesion: 0.25
Nodes (10): dependencies, net10.0-windows7.0, net10.0-windows7.0/win-x64, contentHash, requested, resolved, type, Microsoft.Web.WebView2 (+2 more)

### Community 63 - "Nomisma — first discovery study"
Cohesion: 0.09
Nodes (22): Acquisition sequence and gates, Candle features (frozen), Condition search (post hoc), Continuation outcome, Data sources, Entry comparison, Evaluation, Execution (+14 more)

### Community 64 - "Consolidated research findings and questions"
Cohesion: 0.21
Nodes (15): Current simulated research scope, Consolidated research findings and questions, Registered research priorities and unresolved requirements, Stage 1 consolidated research synthesis, Cross-stock fifteen-minute qualifying-entry study, Fifteen-minute exit-request deadline, Exposed pre-close analysis and incomplete adverse marks, Holding-period investigation (+7 more)

### Community 65 - "check_windows.py"
Cohesion: 0.23
Nodes (15): check(), clean_environment(), main(), port_closed(), Path, Retain only timing diagnostics, even if native verification failed., Verify Windows release artifacts on a clean Windows test account. Installs,…, Verify exactly one installer/archive pair before executing any package. (+7 more)

### Community 66 - ".isTrusted"
Cohesion: 0.24
Nodes (4): Bool, NSApplication, NSMenuItem, WKFrameInfo

### Community 67 - "_check_stop"
Cohesion: 0.16
Nodes (10): _cancellable_call(), _Cancelled, _check_stop(), load_floats(), load_one(), report(), ValueError, Stop promptly without changing the existing fixed-host GET transport. Its… (+2 more)

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

### Community 77 - "replay"
Cohesion: 0.22
Nodes (9): _bootstrap_low(), day_context(), Stock-day features known at the open: opening gap and premarket dollar volume., Lower 90% bound (5th percentile) of the mean, resampling whole sessions., Per arm, policy, window and liquidity: participation, mean R per trade and per…, HYPOTHESES pass rules for one cost column., replay(), summarize() (+1 more)

### Community 79 - "App.swift"
Cohesion: 0.29
Nodes (5): AppKit, Foundation, NomismaApplication, UserNotifications, WebKit

### Community 80 - "real_spreads"
Cohesion: 0.25
Nodes (9): _half_spread(), Alpaca RFC 3339 timestamp (nanoseconds, Z) to an aware datetime., Relative half-spread of the NBBO in force at moment (else the first valid quote…, Cached half-spread lookup at a New York minute; raw Alpaca SIP quotes are…, Net returns of liquid in-play primary fills using measured Alpaca SIP spreads…, real_spreads(), _spreads(), spread_at() (+1 more)

### Community 84 - "Earlier profit-taking investigation"
Cohesion: 0.20
Nodes (10): ATR payoff geometry versus hit probability, FTFT September 14 breakout reversal, Cost-adjusted exit formulas, Eight earlier-exit counterfactuals, FINRA order-types guide, Early-exit payoff and admission mismatch, Earlier profit-taking investigation, SEC stop-order bulletin (+2 more)

### Community 87 - "make_catalog"
Cohesion: 0.25
Nodes (5): make_catalog(), StreamingTests, two_sessions(), account_config(), AdapterTests

### Community 91 - "Monitoring and screening methodology"
Cohesion: 0.14
Nodes (14): Alert confirmation, repeats, and delivery, Daily screener: indicators and timing, Daily screener: score composition, Interpretation limits, Intraday score and indicators, Intraday session and price timing, Intraday volume, gap, and float, Liquidity and volatility metrics (+6 more)

### Community 92 - "demo_bundle"
Cohesion: 0.21
Nodes (5): demo_bundle(), Return a fresh validated configuration; never coerce numeric strings., A reproducible historical simulation, advancing one minute per step. The…, validate_monitor_config(), MonitorConfigTests

### Community 94 - "planner_check.py"
Cohesion: 0.08
Nodes (29): argparse, base64, port_available(), Start or reuse this local workspace, then open its ready browser interface., Check a local bind without Windows' refused-connection timeout. Windows needs…, serve(), main(), Launch Nomisma or run one saved screen, without installing dependencies. (+21 more)

### Community 96 - "run"
Cohesion: 0.25
Nodes (5): check_alert_refresh(), check_live(), Exercise real browser events against the isolated synthetic monitor., Explicit refresh must work even when the background event stream is idle., run()

### Community 97 - "Nomisma.Windows.csproj"
Cohesion: 0.50
Nodes (3): net10.0-windows, Microsoft.Web.WebView2 (1.0.4191.47), Microsoft.NET.Sdk

### Community 98 - "research_data.py"
Cohesion: 0.22
Nodes (15): acquire_preflight(), _Budget, capture_metadata(), _error_code(), _new_directory(), Bounded read-only research acquisition, separate from all trading services.…, Bounded callback capture with hashed start, attempt and terminal evidence. Byte…, GET only clock/calendar/assets/actions; no account, position or order API. (+7 more)

### Community 99 - "test_discovery_replay.py"
Cohesion: 0.24
Nodes (5): bars(), OutcomeTest, Entry gating, deadline exit and wick exit of the discovery replay on synthetic…, ReclaimTest, TradeTest

### Community 104 - "_symbol"
Cohesion: 0.33
Nodes (5): fetch_float(), _NoFloatRedirect, HTTPRedirectHandler, Return actual, provider-dated float shares; never substitute outstanding., _symbol()

### Community 106 - ".handle"
Cohesion: 0.15
Nodes (17): quote_sample(), Step 4 disk projection: Alpaca SIP quotes and trades for sampled listed primary…, The only gate to study data; holdout stays sealed until finalists are committed., readable(), conditions(), percent(), Post-hoc quintile scan of decision-time features over liquid primary fills, per…, Month-by-month gross percent per arm: all liquid primary fills, in play, and… (+9 more)

### Community 108 - "opportunities"
Cohesion: 0.33
Nodes (5): atr14(), opportunities(), Resistance at candidate minute m from bars strictly before m; None if undefined., Fresh crossings per arm, one active 15-minute opportunity per arm, through the…, resistance()

### Community 109 - "All-in cash allocation and exit comparison — September 20, 2026"
Cohesion: 0.25
Nodes (8): All-in cash allocation and exit comparison — September 20, 2026, Authorized change and scope, Causal event ordering, Entry allocation and actual execution, Equity observation with no account drawdown control, Required checks and bounded execution, Review and attribution, Three fixed exit policies

### Community 110 - "Nomisma implementation contract"
Cohesion: 0.25
Nodes (8): Built-in planner API, Data (`nomisma/providers.py`), Engine (`nomisma/engine.py`), Nomisma implementation contract, Other research extensions, Research and workspace extensions, Server API (root implements), UI (frontend agent owns static files)

### Community 111 - "Cash-account allocation pilot, 18 September 2026"
Cohesion: 0.25
Nodes (7): Cash-account allocation pilot, 18 September 2026, Cash and settlement, Feasibility and causal selection, Primary rule references, Purpose and scope, Sizing and registered comparisons, Validation and reporting

### Community 112 - "Historical replay pilot"
Cohesion: 0.25
Nodes (7): Archived inputs and historical clock, Frozen development experiment, Historical replay pilot, Later research, Required evidence, Running the pilot, Simulated orders and shared portfolio

### Community 114 - "Research follow-through, 18 September 2026"
Cohesion: 0.29
Nodes (6): Conditional liquidation equity and guard, Confirmed account constraint, Data stages and evidence limits, Decision funnel and parameter evidence, Research follow-through, 18 September 2026, Verification and resource profile

### Community 115 - "Built-in intraday research planner"
Cohesion: 0.29
Nodes (7): Affine fees and robust sizing, Built-in intraday research planner, In the app, Inputs and data provenance, Mathematics, Output states, Validation and remaining research

### Community 116 - "Historical replay calibration: development experiment v1"
Cohesion: 0.33
Nodes (5): Frozen experiment, Historical replay calibration: development experiment v1, Replay and scoring, Selection and sensitivity, Verification

### Community 117 - "Completed experiment"
Cohesion: 0.40
Nodes (5): Completed experiment, Formula versions, IBKR Pro Fixed sensitivity, Results, Scope and frozen assumptions

### Community 118 - "generate_icon.py"
Cohesion: 0.38
Nodes (5): inside_polygon(), main(), png(), Rebuild Nomisma.ico from the app's simple N monogram (stdlib only)., zlib

### Community 119 - "Q: Give a concise overview of heuresis, its purpose, main components, architecture, and workflows"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: Give a concise overview of heuresis, its purpose, main components, architecture, and workflows, Source Nodes

### Community 120 - "._validate_backup"
Cohesion: 0.38
Nodes (6): Read only known table data; never execute schema from an upload., decode(), finite(), invalid(), discovery_job(), stamp()

### Community 121 - "Sharing one Alpaca feed between two machines"
Cohesion: 0.25
Nodes (8): Before you start, Daily order, Machine A — runs the pool and uses the data, Machine B — uses the data, Security, Sharing one Alpaca feed between two machines, Troubleshooting, What to expect

### Community 125 - "check_alert_source_isolation"
Cohesion: 0.33
Nodes (4): check_alert_source_isolation(), inbox(), mark_all(), Persist both sources without starting a market connection or altering earlier…

### Community 126 - "PoolTest"
Cohesion: 0.31
Nodes (3): fake_stream(), PoolTest, on_event()

### Community 128 - "Massive"
Cohesion: 0.29
Nodes (4): Massive, _NoRedirect, HTTPRedirectHandler, Paced GET transport returning raw response bytes.

### Community 129 - "Proposed validation and parameter-calibration plan"
Cohesion: 0.29
Nodes (7): Chronological selection and untouched holdout, Exposed development leader k1-r2.5-h30, Eligibility and fill funnel audit, The Probability of Backtest Overfitting, Proposed validation and parameter-calibration plan, SES and TE admission rejections, Outcome-selected exit rules and dependent comparisons

### Community 130 - "All-in cash-account simulation and exit comparison"
Cohesion: 0.40
Nodes (5): All-affordable settled-cash sizing, breakeven_1atr exit policy, fixed_15m exit policy, All-in cash-account simulation and exit comparison, trail_1atr exit policy

### Community 131 - "Nomisma for macOS"
Cohesion: 0.50
Nodes (4): Build or update, Native controls, Nomisma for macOS, Troubleshooting

### Community 133 - "stream_live"
Cohesion: 0.33
Nodes (5): One authenticated stream session; root performs reconnect and reseeding., _stream_error(), stream_live(), report_channels(), on_event()

### Community 135 - ".snapshot"
Cohesion: 0.22
Nodes (7): Monitor service and browser API (root), live_provider_status(), MonitorBusy, ValueError, Reload the active source without restarting the stream or alert tracker., get(), get()

### Community 136 - "4. Runtime Output Control"
Cohesion: 0.50
Nodes (3): 4. Runtime Output Control, Execute First, Query Only Needed Output

### Community 138 - "math"
Cohesion: 0.33
Nodes (6): Completed tasks and evidence, math, Next steps, Pitfalls, Scope and current status, Unresolved findings and stuck problems

### Community 140 - "Entry quality as the next research priority"
Cohesion: 0.50
Nodes (4): Entry quality as the next research priority, Unresolved selection for one shared account, First feasible confirmed-alert selection, Eleven entries and ten added losing opportunities

## Ambiguous Edges - Review These
- `Possible Heston variance-process interpretation` → `dv = κ(θ − v) dt + ξ√v dW`  [AMBIGUOUS]
  nomisma/reference/HSK3howbMAARiJ9.jpeg · relation: conceptually_related_to
- `Possible restriction to past events tᵢ < t` → `Sum of exponential contributions`  [AMBIGUOUS]
  nomisma/reference/HSK5WZCbAAEW2Ic.jpeg · relation: conceptually_related_to

## Knowledge Gaps
- **213 isolated node(s):** `AppKit`, `Foundation`, `WebKit`, `UserNotifications`, `ExitCode` (+208 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 775 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **35 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Possible Heston variance-process interpretation` and `dv = κ(θ − v) dt + ξ√v dW`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `Possible restriction to past events tᵢ < t` and `Sum of exponential contributions`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `Intraday monitoring implementation contract` connect `monitor_metrics.py` to `.snapshot`, `TRADE_PLANNER.md`?**
  _High betweenness centrality (0.135) - this node is a cross-community bridge._
- **Why does `Research extensions (September 2026)` connect `monitor_metrics.py` to `SDL.md - SDL-MCP Agent Workflow`, `.snapshot`?**
  _High betweenness centrality (0.123) - this node is a cross-community bridge._
- **Why does `rank_rows()` connect `monitor_metrics.py` to `research.py`?**
  _High betweenness centrality (0.060) - this node is a cross-community bridge._
- **Are the 9 inferred relationships involving `Application` (e.g. with `LiveMonitor` and `Planner`) actually correct?**
  _`Application` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `MonitorTests` (e.g. with `LiveSubscriptionLimit` and `LiveMonitor`) actually correct?**
  _`MonitorTests` has 4 INFERRED edges - model-reasoned connections that need verification._