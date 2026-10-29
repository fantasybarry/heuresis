# Graph Report - heuresis  (2026-09-21)

## Corpus Check
- 116 files · ~167,984 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 17 file(s) not represented in the graph (top: .toml 6, .css 3, (none) 2)

## Summary
- 2158 nodes · 5449 edges · 106 communities (82 shown, 24 thin omitted)
- Extraction: 96% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 189 edges (avg confidence: 0.87)
- Token cost: unavailable for host-agent semantic extraction (the agent tool exposes no usage counts); AST extraction uses 0 LLM tokens.

## Community Hubs (Navigation)
- Daily Screener Interface
- Historical Data Acquisition
- Trade Plan Construction
- Live Monitor Interface
- Windows Application Shell
- Market Data Seed Tests
- Candidate Discovery Tests
- Settlement Calendar
- Market Data Streaming
- Cash and Exit Tests
- Intraday Metric Tests
- Shared Python Dependencies
- Replay Chronology
- Calibration Catalogs
- Daily Screening Rules
- Planning Evidence Capture
- Trade Plan Validation
- Replay Module Dependencies
- Research Service Scheduling
- Replay Event Engine
- Intraday Metrics
- macOS Application Lifecycle
- Drawdown Guard Simulation
- Server Storage Dependencies
- Market Data Providers
- Application Settings Tests
- Live Monitor State
- Liquidity Volatility Ranking
- Alert Journal Tests
- Windows Packaging
- Research Workspace Storage
- Monitor Refresh Tests
- Research Capture Tests
- Candidate Discovery
- Browser Verification Tools
- Research Command Tools
- macOS WebView Callbacks
- macOS Packaging
- Local Service Hosting
- WebSocket Protocol Tests
- Workspace Launcher
- Desktop Host Tests
- HTTP API Tests
- Workspace Restore Tests
- Replay Archive Tests
- Calibration Comparison Metrics
- Calibration Command Workflow
- Technical Indicator Calculations
- Windows Installation Verification
- Full Allocation Exit Simulation
- Settled Cash Simulation
- Calibration Metric Tests
- Windows Build Tests
- Alpaca Provider Tests
- macOS Downloads
- Windows Bridge Tests
- Monitor Refresh Control
- Discovery Restore Validation
- Trade Planner Interface
- Square Root Diffusion
- Clean Source Export
- Replay Research Contracts
- Windows Dependency Lock
- Discovery Schedule Tests
- Entry Quality Research
- Calibration Archive Tests
- macOS Menu Authorization
- Cash Allocation Contracts
- Desktop Service Lifecycles
- Mean Reversion Equation
- Event Intensity Equation
- Replay Execution Diagnostics
- Replay Archive Commands
- Inventory Adjusted Pricing
- Calibration Checkpoint Tests
- CSV Import Validation
- Research Workspace Contracts
- Windows Icon Generation
- Holding Period Research
- macOS Framework Integration
- Frozen Planning Evidence
- Windows Notification Bridge
- Entry Selection Diagnosis
- Early Exit Research
- macOS Build Tests
- Stock Classification Tests
- Monitor API Tests
- Alert Source Isolation Checks
- Provider Transport Tests
- Live Monitoring Contract
- Market Ranking Methodology
- Monitor Timestamp Handling
- Independent Validation Research
- Full Allocation Exit Experiments
- Research Checkpoint Tests
- Alert Refresh Checks
- Windows Project Configuration
- Subscription Limit Handling
- Entry Price Feasibility
- Full Allocation Checkpoint Tests
- Cash Replay Checkpoint Tests
- Market Calendar Tests
- Windows Release Workflow
- Parameter Grid Tests

## God Nodes (most connected - your core abstractions)
1. `Application` - 63 edges
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
- `Heuresis overview and quick-start` --references--> `Nomisma local research workspace`  [AMBIGUOUS]
  README.md → nomisma/README.md
- `Windows x64 build and verification` --implements--> `Pinned Windows packaging toolchain`  [INFERRED]
  .github/workflows/nomisma-windows.yml → nomisma/desktop/WINDOWS.md
- `Stage 1 consolidated research synthesis` --semantically_similar_to--> `Consolidated research findings and questions`  [INFERRED] [semantically similar]
  nomisma/temporary/stage1.md → nomisma/temporary/research_findings_and_questions.md
- `LiveMonitor` --uses--> `LiveSubscriptionLimit`  [INFERRED]
  nomisma/nomisma/monitor.py → nomisma/nomisma/live_data.py
- `MonitorTests` --uses--> `LiveSubscriptionLimit`  [INFERRED]
  nomisma/tests/test_monitor.py → nomisma/nomisma/live_data.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Original alert evidence, frozen planning and separate observed outcomes** — nomisma_live_contract_frozen_alert_evidence, nomisma_trade_planner_frozen_inputs, nomisma_api_contract_planner_api, nomisma_methodology_observed_outcomes [EXTRACTED 1.00]
- **Frozen, reproducible offline research evidence** — nomisma_replay_spec_archive_verified_cli, nomisma_calibration_spec_continuous_account, nomisma_research_followthrough_spec_bounded_evidence_capture, nomisma_all_in_exits_spec_registered_execution [INFERRED 0.85]
- **Application distribution separated from credentials and research state** — nomisma_api_contract_workspace_backup_restore, nomisma_desktop_readme_macos_build, nomisma_desktop_windows_clean_source_export, nomisma_desktop_windows_owned_service_lifecycle [INFERRED 0.85]
- **Repeated counterfactuals on the September 14 FTFT entry** — nomisma_temporary_task09_20_all_affordable_sizing, nomisma_temporary_task09_20_early_exits_eight_rules, nomisma_temporary_task09_20_holding_period_timer_only, nomisma_temporary_task09_20_cross_stock_15m_timer_deadline, nomisma_temporary_task09_20_six_rules_six_stocks_cohort [INFERRED 0.95]
- **Prespecification and independent validation requirements** — nomisma_temporary_task09_18_chronological_validation, nomisma_temporary_task09_19_evidence_expansion, nomisma_temporary_stage1_registered_priorities, nomisma_temporary_research_findings_and_questions_entry_quality [INFERRED 0.95]

## Communities (106 total, 24 thin omitted)

### Community 0 - "Daily Screener Interface"
Cohesion: 0.10
Nodes (80): addSymbol(), api(), applyJob(), avatar(), average(), bindEvents(), booleanFields, bootstrap() (+72 more)

### Community 1 - "Historical Data Acquisition"
Cohesion: 0.05
Nodes (51): collections, _Archive, _bars(), _basis(), download_dataset(), _events(), _http(), _json_bytes() (+43 more)

### Community 2 - "Trade Plan Construction"
Cohesion: 0.05
Nodes (48): build_all_in_plan(), Reuse frozen market/geometry validation, then size only by settled cash.…, evaluate_plan(), freeze_plan(), Planner, Local research planning service; never submits or manages broker orders., Evaluate with a separate, explicitly synthetic account clock for demos. A…, Keep a reproducible model result separate from the alert's observations. (+40 more)

### Community 3 - "Live Monitor Interface"
Cohesion: 0.11
Nodes (61): accept(), acknowledge(), applyDiscoveryJob(), bind(), candidateSelection(), compareRows(), diagnose(), discover() (+53 more)

### Community 4 - "Windows Application Shell"
Cohesion: 0.06
Nodes (35): Button, CoreWebView2DownloadStartingEventArgs, CoreWebView2WebMessageReceivedEventArgs, Nomisma.Desktop, Form, FormClosingEventArgs, Label, MenuStrip (+27 more)

### Community 5 - "Market Data Seed Tests"
Cohesion: 0.07
Nodes (16): bar(), calendar(), FloatTests, dict, object, ScreeningHistoryTests, SeedTests, blocked() (+8 more)

### Community 6 - "Candidate Discovery Tests"
Cohesion: 0.06
Nodes (10): calendar(), DiagnosticTests, DiscoveryTests, get(), get(), history(), get(), dict (+2 more)

### Community 7 - "Settlement Calendar"
Cohesion: 0.08
Nodes (28): dataclasses, _canonical(), create_calendar(), _dates(), _day(), _digest(), load_calendar(), _path() (+20 more)

### Community 8 - "Market Data Streaming"
Cohesion: 0.08
Nodes (36): _cancellable_call(), _Cancelled, _check_stop(), _credentials(), extended_day_volumes(), fetch_float(), _get_json(), _history() (+28 more)

### Community 9 - "Cash and Exit Tests"
Cohesion: 0.10
Nodes (15): AllInIntegrationTests, AllInSizingTests, engine(), enter(), observe(), plan(), ProtectiveExitTests, CashAccountingTests (+7 more)

### Community 10 - "Intraday Metric Tests"
Cohesion: 0.12
Nodes (5): fixture(), IntradayVolumeTests, PriceAndFloatTests, row(), SetupSafetyTests

### Community 11 - "Shared Python Dependencies"
Cohesion: 0.12
Nodes (25): gzip, hashlib, importlib_util, io, json, Nomisma: explainable daily equity screening, part of Heuresis., Immutable all-in replay checkpoints and source identity contracts., Checkpoint behavior protects reproducibility of the expensive offline sweep. (+17 more)

### Community 12 - "Replay Chronology"
Cohesion: 0.15
Nodes (18): _confirmation(), _iso(), _ns(), Session-scoped monitor confirmation without persistence or wall clock., Parse UTC nanoseconds without float timestamps or microsecond loss., Replay all archived sessions and cohort symbols chronologically, offline., run_replay(), accounting_engine() (+10 more)

### Community 13 - "Calibration Catalogs"
Cohesion: 0.11
Nodes (36): Path, Stream one predeclared fixed exit policy through settled-cash sessions., run_catalog_all_in(), source_hashes(), _canonical(), _catalog_digest(), create_catalog(), download_development() (+28 more)

### Community 14 - "Daily Screening Rules"
Cohesion: 0.14
Nodes (16): _filter_failures(), _finite_number(), _metadata(), Reject malformed histories as a whole; never silently repair price data., Screen supplied completed bars, returning only JSON-safe values. eligible_count…, Merge partial filters with defaults, validating without coercing strings., screen(), _today() (+8 more)

### Community 15 - "Planning Evidence Capture"
Cohesion: 0.13
Nodes (15): capture_planning_quote(), _iso(), _number(), prepare_plan_inputs(), _provenance(), Frozen, decision-time inputs for the research trade planner; no I/O. Quote…, Copy documented quote evidence without inventing receipt times or units. The…, Validate original alert evidence; return diagnostics and a finite schema. No… (+7 more)

### Community 16 - "Trade Plan Validation"
Cohesion: 0.13
Nodes (6): market(), NumericalFixtureTests, PlanStateTests, Researcher numerical fixtures and safety boundaries; no I/O or orders., settings(), ValidationTests

### Community 17 - "Replay Module Dependencies"
Cohesion: 0.14
Nodes (19): bisect, copy, decimal, heapq, Cash-only requested sizing and three causal exit policies, offline only. This…, Versioned offline cash-account and single-entry allocation experiment. The…, Deterministic, offline historical-replay-v1 engineering experiment. This…, Offline liquidation-equity observation and fixed-dollar research guard. The… (+11 more)

### Community 18 - "Research Service Scheduling"
Cohesion: 0.12
Nodes (4): Exception, Application, loop(), BusyError

### Community 19 - "Replay Event Engine"
Cohesion: 0.16
Nodes (12): _config(), _d(), default_replay_config(), _finite(), _json(), Any, Decimal, _quote_valid() (+4 more)

### Community 20 - "Intraday Metrics"
Cohesion: 0.14
Nodes (24): math, _ema(), Aligned EMA series; the first period-1 entries have no value., build_rows(), _daily(), _date(), demo_bundle(), _fresh() (+16 more)

### Community 21 - "macOS Application Lifecycle"
Cohesion: 0.08
Nodes (19): AppDelegate, Process, Notification, NSApplicationDelegate, NSButton, NSMenuItemValidation, NSObject, NSProgressIndicator (+11 more)

### Community 22 - "Drawdown Guard Simulation"
Cohesion: 0.13
Nodes (9): _GuardedReplay, Any, Additional observer/control hooks; frozen execution methods stay intact., drain(), engine(), GuardControlTests, LiquidationEquityTests, observe() (+1 more)

### Community 23 - "Server Storage Dependencies"
Cohesion: 0.15
Nodes (23): contextlib, datetime, http_client, http_server, mimetypes, monitor_csv(), csv_export(), make_handler() (+15 more)

### Community 24 - "Market Data Providers"
Cohesion: 0.13
Nodes (25): csv, _parse(), Stocks-only eligibility from Nasdaq Trader's public symbol directories.…, Return a fresh verified stock allowlist; never send provider credentials., require_stocks(), stock_symbols(), _asset_metadata(), _bar() (+17 more)

### Community 25 - "Application Settings Tests"
Cohesion: 0.09
Nodes (5): default_settings(), validate_settings(), ApplicationTests, SettingsTests, patch

### Community 26 - "Live Monitor State"
Cohesion: 0.19
Nodes (5): LiveMonitor, on_status(), Repair missing minute history without rolling back newer events., Only complete, contiguous future windows from matching provenance., utcnow()

### Community 27 - "Liquidity Volatility Ranking"
Cohesion: 0.15
Nodes (13): _bars(), _date(), history_metrics(), _number(), rank_rows(), measured(), Pure historical liquidity/volatility measurements and transparent ranking.…, Assign cross-sectional ranks without hiding rows or changing input order.… (+5 more)

### Community 29 - "Windows Packaging"
Cohesion: 0.17
Nodes (26): build(), compile_installer(), copy_backend(), download_verified(), extract_verified_archive(), main(), prepare_python(), preserve_licenses() (+18 more)

### Community 30 - "Research Workspace Storage"
Cohesion: 0.16
Nodes (3): A transactionally consistent SQLite snapshot, even during a scan., Validate fully, retain a safety copy, then atomically restore rows. The caller…, Store

### Community 32 - "Research Capture Tests"
Cohesion: 0.11
Nodes (6): calendar(), requester(), ResearchDataTests, limited(), checked(), stream()

### Community 33 - "Candidate Discovery"
Cohesion: 0.20
Nodes (19): _stamp(), _calendar(), _candidate(), diagnose(), discover(), _extend_missing_day_volume(), _phase(), _positive() (+11 more)

### Community 34 - "Browser Verification Tools"
Cohesion: 0.13
Nodes (18): base64, browser_endpoint(), check_candidate_metrics(), check_live(), check_metric_columns(), check_metric_null_sorting(), check_mobile_candidate_scrolling(), check_workspace_improvements() (+10 more)

### Community 35 - "Research Command Tools"
Cohesion: 0.13
Nodes (18): desktop, execute(), main(), Run one immutable offline all-in settled-cash exit-policy comparison., sha(), write_new(), execute(), main() (+10 more)

### Community 36 - "macOS WebView Callbacks"
Cohesion: 0.11
Nodes (16): Any, String, UNAuthorizationStatus, UNNotification, UNNotificationPresentationOptions, UNNotificationResponse, UNUserNotificationCenter, Void (+8 more)

### Community 37 - "macOS Packaging"
Cohesion: 0.20
Nodes (20): build(), build_icon(), clean_python_environment(), copy_backend(), copy_python(), install_bundle(), mach_o_files(), main() (+12 more)

### Community 38 - "Local Service Hosting"
Cohesion: 0.18
Nodes (19): concurrent_futures, errno, logging, choose_port(), launch_lock(), main(), _matches(), Own one local service; release database handles when the app exits. The HTTP… (+11 more)

### Community 39 - "WebSocket Protocol Tests"
Cohesion: 0.19
Nodes (4): FakeSocket, frame(), sent_frame(), WebSocketTests

### Community 40 - "Workspace Launcher"
Cohesion: 0.15
Nodes (10): check_workspace(), health(), launch(), main(), port_available(), port_open(), Start or reuse this local workspace, then open its ready browser interface., Check a local bind without Windows' refused-connection timeout. Windows needs… (+2 more)

### Community 43 - "Workspace Restore Tests"
Cohesion: 0.14
Nodes (4): demo_dataset(), An explicitly synthetic, reproducible historical research playground., StorageTests, record_connection()

### Community 44 - "Replay Archive Tests"
Cohesion: 0.14
Nodes (4): fixture(), ReplayDataTests, malformed(), count()

### Community 45 - "Calibration Comparison Metrics"
Cohesion: 0.22
Nodes (16): itertools, _aggregate(), compare_candidates(), compact(), compare_metrics(), _diagnostic_best(), _flat(), _money() (+8 more)

### Community 46 - "Calibration Command Workflow"
Cohesion: 0.30
Nodes (16): generate_candidates(), Exact parity projection: omit only known provenance/fingerprint changes., Return exactly 27 independent configs, changing only the three grid keys., semantic_result(), canonical(), checkpoint(), digest(), event() (+8 more)

### Community 47 - "Technical Indicator Calculations"
Cohesion: 0.19
Nodes (10): _atr(), _clamp(), _date(), _metrics(), _percent(), Deterministic, explainable end-of-day technical screening. Scores are a hand-…, _risks(), _rsi() (+2 more)

### Community 48 - "Windows Installation Verification"
Cohesion: 0.23
Nodes (15): check(), clean_environment(), main(), port_closed(), Path, Retain only timing diagnostics, even if native verification failed., Verify Windows release artifacts on a clean Windows test account. Installs,…, Verify exactly one installer/archive pair before executing any package. (+7 more)

### Community 49 - "Full Allocation Exit Simulation"
Cohesion: 0.18
Nodes (3): _AllInReplay, effective_policy(), Observe equity/drawdown without any threshold, budget or latch.

### Community 51 - "Calibration Metric Tests"
Cohesion: 0.24
Nodes (4): boundary(), cash_result(), ComparisonTests, MetricTests

### Community 53 - "Alpaca Provider Tests"
Cohesion: 0.23
Nodes (5): AlpacaTests, response(), response(), response(), raw_bar()

### Community 54 - "macOS Downloads"
Cohesion: 0.20
Nodes (8): Data, Error, HTTPURLResponse, DownloadDestination, URL, URLRequest, URLResponse, WKDownload

### Community 55 - "Windows Bridge Tests"
Cohesion: 0.17
Nodes (10): assert, fs, path, test, vm, ref_node_assert, ref_node_fs, ref_node_path (+2 more)

### Community 56 - "Monitor Refresh Control"
Cohesion: 0.20
Nodes (7): live_provider_status(), MonitorBusy, ValueError, Reload the active source without restarting the stream or alert tracker., during_request(), get(), get()

### Community 57 - "Discovery Restore Validation"
Cohesion: 0.24
Nodes (10): default_discovery(), validate_discovery(), default_discovery_settings(), validate_discovery_settings(), Read only known table data; never execute schema from an upload., decode(), finite(), invalid() (+2 more)

### Community 58 - "Trade Planner Interface"
Cohesion: 0.29
Nodes (8): error(), metric(), render(), request(), showAlert(), showSettings(), toggleBusy(), updateExpiry()

### Community 59 - "Square Root Diffusion"
Cohesion: 0.18
Nodes (12): Cox–Ingersoll–Ross square-root process, dv = κ(θ − v) dt + ξ√v dW, Possible Heston variance-process interpretation, Drift coefficient κ, Linear drift term κ(θ − v) dt, Mean reversion toward θ when κ > 0, Nonnegative domain required by real-valued √v, State-dependent diffusion term ξ√v dW (+4 more)

### Community 60 - "Clean Source Export"
Cohesion: 0.27
Nodes (7): argparse, SourceExportTests, allowed_source(), export_source(), main(), Export current Nomisma source for a fresh GitHub repository, without history.…, subprocess

### Community 61 - "Replay Research Contracts"
Cohesion: 0.20
Nodes (11): Nomisma agent coordination policy, infra_engineer, Research and execution boundaries, Continuous-account chronological calibration, Development calibration experiment v1, Development-only selection block, Mocked provider tests and isolated browser verification, Shared-portfolio capacity-limited IOC simulation (+3 more)

### Community 62 - "Windows Dependency Lock"
Cohesion: 0.25
Nodes (10): dependencies, net10.0-windows7.0, net10.0-windows7.0/win-x64, contentHash, requested, resolved, type, Microsoft.Web.WebView2 (+2 more)

### Community 64 - "Entry Quality Research"
Cohesion: 0.24
Nodes (11): Current simulated research scope, Entry quality as the next research priority, Consolidated research findings and questions, Registered research priorities and unresolved requirements, Stage 1 consolidated research synthesis, Eleven entries and ten added losing opportunities, Lenient entry comparison with $10,000 cash, Lenient $10,000 simulation summary (+3 more)

### Community 66 - "macOS Menu Authorization"
Cohesion: 0.24
Nodes (4): Bool, NSApplication, NSMenuItem, WKFrameInfo

### Community 67 - "Cash Allocation Contracts"
Cohesion: 0.27
Nodes (10): All-in cash allocation and exit comparison, Cash-only requested allocation with capacity-limited execution, Causal protective-exit event ordering, fixed_15m, breakeven_1atr and trail_1atr, Ten registered all-in runs, SEC stop-order bulletin, Cash-account allocation pilot, First-feasible single-entry daily selection (+2 more)

### Community 68 - "Desktop Service Lifecycles"
Cohesion: 0.29
Nodes (10): Local service identity verification, Persistent macOS local-service lifecycle, Nomisma macOS native app, macOS bundle build and portable mode, Windows service ownership and persistent user data, Pinned Windows packaging toolchain, Windows startup timing and bounded logs, Nomisma Windows 11 Pro x64 desktop (+2 more)

### Community 69 - "Mean Reversion Equation"
Cohesion: 0.22
Nodes (10): Additive diffusion term σ dW, dz = θ(μ − z) dt + σ dW, Linear drift term θ(μ − z) dt, Mean reversion toward μ when θ > 0, Reference level μ, Ornstein–Uhlenbeck process, Diffusion coefficient σ, State variable z (+2 more)

### Community 70 - "Event Intensity Equation"
Cohesion: 0.20
Nodes (10): Amplitude parameter α, Additive baseline μ, Exponent coefficient β, Exponential decay of positive contributions when β > 0, λ(t) = μ + ∑ αe^(−β(t − tᵢ)), Exponential term αe^(−β(t − tᵢ)), Exponential-kernel Hawkes intensity interpretation, Possible restriction to past events tᵢ < t (+2 more)

### Community 71 - "Replay Execution Diagnostics"
Cohesion: 0.22
Nodes (10): Prospective recording and clock uncertainty, Running-peak drawdown guard and unknown equity, Frozen historical replay pilot, Fifty-share planning liquidity cap, Historical replay pilot and account-model updates, Settled cash and T+1 funding model, Causal order diagnostics and execution-state timing, Registered evidence expansion and controlled hypotheses (+2 more)

### Community 72 - "Replay Archive Commands"
Cohesion: 0.33
Nodes (8): load_dataset(), Read only, verify every archived artifact before returning dataset., canonical(), main(), Archive and replay a declared historical research cohort; never places orders., source_hashes(), write_json(), platform

### Community 73 - "Inventory Adjusted Pricing"
Cohesion: 0.22
Nodes (9): Subtracted adjustment qγσ²(T − t), Avellaneda–Stoikov reservation-price interpretation, Baseline value s, Conditional linear shift from the baseline, r = s − qγσ²(T − t), Multiplier γ, Multiplier q, Squared parameter σ² (+1 more)

### Community 76 - "Research Workspace Contracts"
Cohesion: 0.29
Nodes (8): Nomisma implementation contract, Loopback and origin protection, Asynchronous diagnostics and candidate discovery, Validated SQLite backup and restore, filters-dialog, settings-dialog, Independent persisted research schedules, Archive-verified replay pilot CLI

### Community 77 - "Windows Icon Generation"
Cohesion: 0.32
Nodes (6): inside_polygon(), main(), png(), Rebuild Nomisma.ico from the app's simple N monogram (stdlib only)., struct, zlib

### Community 78 - "Holding Period Research"
Cohesion: 0.25
Nodes (8): Eligibility and fill funnel audit, SES and TE admission rejections, Cross-stock fifteen-minute qualifying-entry study, Fifteen-minute exit-request deadline, Exposed pre-close analysis and incomplete adverse marks, Holding-period investigation, Retained-stop precedence over longer deadlines, Timer-only holding horizons

### Community 79 - "macOS Framework Integration"
Cohesion: 0.29
Nodes (5): AppKit, Foundation, NomismaApplication, UserNotifications, WebKit

### Community 80 - "Frozen Planning Evidence"
Cohesion: 0.38
Nodes (7): Immutable planner API, Frozen alert evidence schema v1, Observed 5/15/30-minute alert outcomes, Bounded historical and prospective evidence capture, Frozen planning inputs and original receipt provenance, intraday-research-v1, Decimal geometry and robust partial-fill sizing

### Community 83 - "Entry Selection Diagnosis"
Cohesion: 0.29
Nodes (7): Unresolved selection for one shared account, ATR payoff geometry versus hit probability, First feasible confirmed-alert selection, FTFT September 14 breakout reversal, Momentum score 85 and entry extension, Cash-account loss diagnosis, Early-exit payoff and admission mismatch

### Community 84 - "Early Exit Research"
Cohesion: 0.29
Nodes (7): Cost-adjusted exit formulas, Eight earlier-exit counterfactuals, FINRA order-types guide, Earlier profit-taking investigation, SEC stop-order bulletin, Profit triggers versus executed proceeds, SERV profitable trigger with losing fills

### Community 88 - "Alert Source Isolation Checks"
Cohesion: 0.33
Nodes (4): check_alert_source_isolation(), inbox(), mark_all(), Persist both sources without starting a market connection or altering earlier…

### Community 90 - "Live Monitoring Contract"
Cohesion: 0.40
Nodes (5): Alpaca seed and WebSocket transport, Intraday monitor contract, Monitor lifecycle and refresh isolation, Complete-history and freshness alert gates, Workspace shell and research navigation

### Community 91 - "Market Ranking Methodology"
Cohesion: 0.50
Nodes (5): Daily screener score, Liquidity/volatility ranking, Nasdaq Trader stocks-only classification, Separate day, session and minute volume provenance, methodology-view

### Community 93 - "Independent Validation Research"
Cohesion: 0.40
Nodes (5): Chronological selection and untouched holdout, Exposed development leader k1-r2.5-h30, The Probability of Backtest Overfitting, Proposed validation and parameter-calibration plan, Outcome-selected exit rules and dependent comparisons

### Community 94 - "Full Allocation Exit Experiments"
Cohesion: 0.50
Nodes (5): All-affordable settled-cash sizing, breakeven_1atr exit policy, fixed_15m exit policy, All-in cash-account simulation and exit comparison, trail_1atr exit policy

### Community 97 - "Windows Project Configuration"
Cohesion: 0.50
Nodes (3): net10.0-windows, Microsoft.Web.WebView2 (1.0.4191.47), Microsoft.NET.Sdk

### Community 98 - "Subscription Limit Handling"
Cohesion: 0.50
Nodes (3): LiveSubscriptionLimit, ValueError, A rejected symbol list needs user action, not repeated reconnection.

### Community 99 - "Entry Price Feasibility"
Cohesion: 0.50
Nodes (4): Empty admissible entry-price interval, Alpaca order documentation, Versioned broker price and entry-execution contract, Lenient entry-cap and reward-risk geometry

### Community 103 - "Windows Release Workflow"
Cohesion: 1.00
Nodes (3): Windows x64 build and verification, Tagged Windows release, Clean source export and GitHub release workflow

## Ambiguous Edges - Review These
- `Heuresis overview and quick-start` → `Nomisma local research workspace`  [AMBIGUOUS]
  README.md · relation: references
- `dv = κ(θ − v) dt + ξ√v dW` → `Possible Heston variance-process interpretation`  [AMBIGUOUS]
  nomisma/reference/HSK3howbMAARiJ9.jpeg · relation: conceptually_related_to
- `Sum of exponential contributions` → `Possible restriction to past events tᵢ < t`  [AMBIGUOUS]
  nomisma/reference/HSK5WZCbAAEW2Ic.jpeg · relation: conceptually_related_to

## Knowledge Gaps
- **56 isolated node(s):** `AppKit`, `Foundation`, `WebKit`, `UserNotifications`, `ExitCode` (+51 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 555 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **24 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Heuresis overview and quick-start` and `Nomisma local research workspace`?**
  _Edge tagged AMBIGUOUS (relation: references) - confidence is low._
- **What is the exact relationship between `dv = κ(θ − v) dt + ξ√v dW` and `Possible Heston variance-process interpretation`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `Sum of exponential contributions` and `Possible restriction to past events tᵢ < t`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `DesktopHostTests` connect `Desktop Host Tests` to `Research Command Tools`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._
- **Why does `Store` connect `Research Workspace Storage` to `Workspace Restore Tests`, `Research Service Scheduling`, `Server Storage Dependencies`, `Discovery Restore Validation`, `Alert Journal Tests`?**
  _High betweenness centrality (0.035) - this node is a cross-community bridge._
- **Why does `ResearchDataTests` connect `Research Capture Tests` to `Shared Python Dependencies`?**
  _High betweenness centrality (0.034) - this node is a cross-community bridge._
- **Are the 9 inferred relationships involving `Application` (e.g. with `LiveMonitor` and `Planner`) actually correct?**
  _`Application` has 9 INFERRED edges - model-reasoned connections that need verification._

## Extraction Integrity

- Raw relationships with unresolved endpoints: 522
- Raw relationships with missing endpoint fields: 0
- Self-loop relationships: 22
- Parallel relationships collapsed in directed projection: 174
- Parallel relationships collapsed in this undirected projection: 179

These diagnostics describe raw extraction limitations, not proof of defects in the project. See `graph_health.json` for details.

## Run Notes

- Built from the current working tree, including its existing uncommitted changes.
- Semantic workers: `infra_engineer` (contracts and project documentation), `researcher` (research notes), and `reviewer` (four reference images). The runtime could not select local agent profiles directly; workers received the corresponding project role instructions.
- Agent results were returned inline and validated before merging. Semantic token usage was not exposed; zero placeholders are not measured usage.
- Source code was analyzed statically. No project tests, backtests, or trading execution were run for this graph-building task.
- Graphify recovered from a multiprocessing startup error by completing AST extraction sequentially; no AST source files failed.

## Token Reduction Benchmark

Graphify benchmark estimates query-context size using its own corpus counter; these are not measured host-agent usage counts.

```text
Corpus: 107,900 words → ~143,866 tokens (naive)
Graph: 2,158 nodes, 5,449 edges
Average query cost: ~12,430 tokens
Reduction: 11.6x fewer tokens per query

[7.6x] what is the main entry point
[37.8x] how are errors handled
[11.7x] what connects the data layer to the api
[9.8x] what are the core abstractions
```
