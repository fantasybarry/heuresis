# Nomisma research handoff — October 6, 2026

## Start here

The latest formula-correction experiment is complete and independently audited. It is **not a completed parameter-fitting study or evidence of a profitable strategy**. The fully corrected version made **$15.228 from one FTFT trade across nine previously examined sessions**; eight sessions had no trade. Both `selected_config` and `expected_gain_forecast` remain `null`.

The user requested this handoff before ending the conversation. No further backtest or application change was requested in this final turn. The next substantive task is to establish broker-realistic execution and broader, unseen stock-selection evidence before selecting parameters or forecasting gains.

- Workspace: `/Users/barry/heuresis`
- Project: `/Users/barry/heuresis/nomisma`
- Main evidence: [coordinator-report.json](../nomisma/artifacts/geometry-repair-700-20261004/coordinator-report.json)
- Latest study directory: `nomisma/artifacts/geometry-repair-700-20261004/`
- Earlier investigation: [prior coordinator report](../nomisma/artifacts/entry-investigation-700-20261004/coordinator-report.json) and [math audit](../nomisma/artifacts/entry-investigation-700-20261004/math-audit.json)

Read the latest coordinator report first, then its registration and verification artifacts. Do not start by rerunning the historical study.

## math

### Scope and current status

The broad mathematical source/specification review and report-formatting tasks from this conversation are **complete**. No implementation task is currently running, and no approval question is pending. The two validation gaps below remain uncorrected in the audited source; the legacy entry limitation is deliberately preserved in its original experiment.

This section records the October 4 broad audit and its October 6 handoff checks. It is separate from the later, narrower $700 geometry-correction experiment described elsewhere in this document. Preserve both sets of evidence and their different scopes; this audit does not supersede the existing account, broker, or research decisions.

- **Reviewed project:** `/Users/barry/heuresis/nomisma`, explicitly selected by the user over the older research-workspace checkout.
- **Coordinator workspace:** `/Users/barry/orca/workspaces/heuresis/research`.
- **Coordination:** follow `/Users/barry/heuresis/nomisma/AGENTS.md`. The user restricted this conversation to the specialist **researcher**; no other specialist ran for this broad audit. That restriction does not rewrite the contributor list of the separate experiment below.
- **Agent setup:** the available agent tool could not directly select a saved TOML profile. The coordinator spawned `researcher` and explicitly supplied the actual `.codex/agents/researcher.toml` instructions and read-only boundary.
- **Source identity:** the working tree was based on `c78e61255adb92f3b5b4ff8a72eeace95dcbc4d8`, with existing modified and untracked files. The manifest, not that commit alone, identifies the audited content.

### Completed tasks and evidence

Researcher reviewed indicators and scoring, signal timing and observed outcomes, planner geometry and partial-fill sizing, replay execution/accounting, calibration and bootstrap statistics, settlement/cash accounting, equity guards, and all-in exit policies. Supporting data, browser, CLI and persistence calculations were included in the report's coverage inventory.

**Conclusion:** no high-severity arithmetic defect was found in the ordinary validated paths examined. The equations agree with their declared models, subject to the three findings below. This is bounded source-review evidence, not a claim that every possible input or historical result is correct.

| Completed check | Recorded result |
| --- | --- |
| Existing core mathematical suites, run by coordinator | 240 tests passed in 9.580 seconds |
| Existing data, timing and outcome suites, run by coordinator | 184 tests passed in 3.540 seconds |
| Total existing tests | **424 passed**; monitor HTTP integration class excluded |
| Researcher partial-fill reward/risk enumeration | 20,200 quantity/entry combinations; fixture minimum net RR 1.5 |
| Coordinator counterexamples | Three findings reproduced; saved assertions passed |
| Report formatting | Contents, finding overview, subsections, tables and equation spacing; findings and calculations preserved |
| Source modifications by this audit | None; only local review artifacts created |
| Historical backtests or parameter fitting in this audit | None |

On **October 6**, the handoff writer rechecked all **82 source-manifest hashes**: none changed or disappeared. The formatted report also matches its saved checksum. These checks do not cover files added outside that manifest, including the separate experiment's adapters. Saved logs still record the 240/184 passing tests; no tests or backtests were rerun for this handoff.

Artifact directory: `/Users/barry/orca/workspaces/heuresis/research/artifacts/math-review-20261004/`.

| Artifact | Purpose |
| --- | --- |
| [REPORT.md](/Users/barry/orca/workspaces/heuresis/research/artifacts/math-review-20261004/REPORT.md) | Full attributed findings, derivations, examples, coverage and limitations |
| [reproduce_findings.py](/Users/barry/orca/workspaces/heuresis/research/artifacts/math-review-20261004/reproduce_findings.py) | Runnable synthetic counterexamples; imports the reviewed source and test fixtures |
| [reproduced-findings.json](/Users/barry/orca/workspaces/heuresis/research/artifacts/math-review-20261004/reproduced-findings.json) | Saved counterexample outputs |
| [math-tests.log](/Users/barry/orca/workspaces/heuresis/research/artifacts/math-review-20261004/math-tests.log) | Exact command and 240-test result |
| [data-timing-tests.log](/Users/barry/orca/workspaces/heuresis/research/artifacts/math-review-20261004/data-timing-tests.log) | Exact command and 184-test result |
| [source-manifest.json](/Users/barry/orca/workspaces/heuresis/research/artifacts/math-review-20261004/source-manifest.json) | Hashes identifying 82 audited files |
| [source-status.txt](/Users/barry/orca/workspaces/heuresis/research/artifacts/math-review-20261004/source-status.txt) | Pre-existing working-tree changes at audit time |
| [verification.json](/Users/barry/orca/workspaces/heuresis/research/artifacts/math-review-20261004/verification.json) | Original verification, formatting checks and current report checksum |

### Unresolved findings and stuck problems

There is no unresolved tool failure blocking this review. The remaining work is mathematical validation remediation and empirical evidence collection, neither performed by this conversation.

1. **Documented legacy limitation — impossible entries reserve capacity.** `trade_plan.py:387` can return a positive-sized `wait` plan when `trigger > cap - entry_displacement`; `replay.py:465` submits it. A complete-history example requires an impossible ask interval of [$2.01, $2.00] yet sizes 200 shares. A separate end-to-end synthetic replay reserves $205.10 cash and $12.30 risk for one order that expires without filling. Other opportunities can therefore lose access to reserved capacity. `cash_replay.py` and `all_in_replay.py` already reject the empty interval; `research_validation.audit_replay` explicitly diagnoses legacy orders. Preserve the frozen legacy experiment and distinguish any corrected version.
2. **Low-severity planner boundary gap — missing opening prefix.** `trade_plan._validated_market` checks within-session contiguity but does not require the first bar to equal `session_open`. Omitting the first 70 bars of the reproduced 90-bar history changes ATR from 0.25806078220643697 to 0.04, stop from 1.62 to 1.95, and quantity from **53 to 200**. The ordinary `planning_data.py:171` adapter rejects this input, so do not portray it as a demonstrated live-alert bypass. The direct helper's fixture also starts late.
3. **Low-severity split-volume validation gap.** `replay_data.py:254` skips its scale check when raw volume is zero. Identical raw/adjusted prices with raw volume 0 and adjusted volume 100 return factor 1 with no error, despite exceeding the existing one-share tolerance. No actual archive was inspected for contamination.

The audit did not establish original historical receipt/revision/halts reconstruction, fitted execution costs or capacity assumptions, a marketwide point-in-time universe, sufficient independent samples, stationarity, an untouched holdout, optimal parameters, or expected gains. External provider and settlement contracts were not reacquired for this source review. Archived historical performance outputs were not independently recalculated.

### Next steps

1. Read the linked report and distinguish its base-source findings from the separate geometry-repair adapter results before planning changes. Recheck source hashes when resuming; do not blindly apply an old finding to a different version.
2. If implementing the two validation corrections, make the smallest shared-boundary changes: require the exact opening prefix in the pure planner, and apply the existing split-volume tolerance even when raw volume is zero. Trace callers first. Cover full versus truncated history, zero/zero volume, zero/100 volume, and the existing valid cases. Update direct planner fixtures to supply the documented opening history.
3. If changing legacy entry admission, register a new engine/experiment version that rejects `trigger > cap - entry_displacement` before reserving cash or risk. Keep old results and their diagnostic classification intact; reuse the already-correct cash/all-in rule where appropriate.
4. Run affected tests and update evidence for the exact changed version. Preserve the original audit report, logs and counterexamples as historical evidence; add a separate remediation result instead of rewriting them as though the original source passed new checks.
5. Follow the existing handoff's broker-aware, chronological, unseen-data research steps before any fitting or forecast claim. This audit adds no trading authorization. Only `researcher` is authorized as a specialist in this conversation; expanding roles requires updated user direction.

To inspect current behavior without changing source:

```sh
python3 -B /Users/barry/orca/workspaces/heuresis/research/artifacts/math-review-20261004/reproduce_findings.py
```

### Pitfalls

- The saved counterexample assertions describe **current defective or legacy behavior**, not desired post-fix behavior. They may intentionally fail after remediation; retain the original evidence and write the corrected regression checks separately.
- Do not confuse this audit's **424 tests** with the separate geometry experiment's **71 tests**, or combine their claims without checking versions and scopes.
- Do not interpret synthetic account settings, such as $10,000 equity in fixtures, as the user's actual account. The existing $700 and IBKR decisions elsewhere in this file remain authoritative.
- Do not treat passing tests, a mathematically valid RR bound, or 20,200 enumerated cases as proof of fills, profitability or trading readiness. Fee envelopes and execution assumptions are part of the model.
- Keep the missing-prefix finding's adapter protection and the empty-interval finding's known legacy status visible. Neither finding means every normal path is broken.
- For replay probes, align monitor symbols with fixture symbols. An initial default-cohort mismatch was a setup error; the saved reproduction uses a compatible sparse configuration.
- Report formatting changed `REPORT.md` and its checksum in `verification.json`, not the mathematical conclusions. Refresh the checksum after future formatting edits without relabeling old test results as newly executed.
- Do not overwrite existing dirty source, source snapshots, frozen experiment artifacts, or other sections of this handoff. This turn inserts only this `math` section.
- Operational environment statements in older sections are historical. For this turn, the supplied environment reports unrestricted filesystem/network access and approval policy `never`; verify the actual environment again when resuming.

## User requirements and decisions

| Item | Agreed scope |
|---|---|
| Research priority | Stock selection and entry signals first; stop/target parameters later |
| Desired universe | Entire eligible U.S.-listed common-stock market |
| Price range | $0.10–$10; higher-priced opportunities may be proposed to the user when justified by liquidity and opportunity |
| Account | **$700 cash account**; this supersedes earlier $10,000 simulation assumptions |
| Broker | **IBKR Pro — Fixed** |
| Data provider | Alpaca supplies Nomisma market data; it is not the user's execution broker |
| Capital deployment | Request nearly all affordable settled cash in one symbol, in whole shares |
| Trading frequency | At most one positively filled entry episode per session; no-trade sessions are allowed |
| Risk | Planned-loss ceiling of 10% of current equity, initially $70; reject an excessive full-size request rather than reducing its size to satisfy risk |
| Overnight | No planned overnight holding |
| Primary objective | Highest arithmetic mean net session return, including no-trade sessions, after modeled costs |
| Desired product output | Explain planned holding duration and potential/expected net gain, with supporting evidence and uncertainty |

The 10% figure is the recorded **planned-loss limit**, not an expected return or a guaranteed maximum realized loss. A 15-minute timer is the current tested exit policy, not a fitted optimal holding period or a prediction of when profit will occur.

## Current tasks and status

| Task | Status |
|---|---|
| Investigate suspected formula problems | Completed for the narrow geometry/admission issues below |
| Test proposed corrections | Completed: four frozen alternatives, identical original research costs |
| Independently verify replay and arithmetic | Completed |
| Separate IBKR base-commission sensitivity | Completed on recorded fills; full broker replay remains open |
| Explain the JSON report to the user | Completed; returns are fractions, `arm` means formula version, `null` means not established |
| Find best stock-selection/entry parameters | **Open**; no validated winner |
| Fit stops, targets, or holding periods | **Open**; no new parameter sweep in this experiment |
| Produce expected-gain forecasts | **Open**; insufficient evidence |
| Change application behavior or deploy trading | Not performed; research artifacts only |

No unanswered broker-plan question remains. Do not ask the user again whether the broker is Alpaca or which IBKR plan they use.

## Completed experiment

### Scope and frozen assumptions

- Six retrospective symbols: **FTFT, GRAB, RR, SERV, SES, TE**. This is not the entire eligible market.
- Nine 2026 sessions: **September 3, 4, 8, 9, 10, 11, 14, 15, 16**. All were already exposed to investigation; none is an untouched holdout.
- Four alternative $700 accounts, each shared across all six symbols. Never treat each symbol as having its own $700.
- Selection remained the first feasible chronological confirmed signal, with alphabetical ties at the same time. This was not highest-score ranking or selection of the eventual day's best stock.
- Exit: protective stop or a timer 15 minutes after the first entry fill. No active profit target, trailing stop, or breakeven rule.
- Preserved the earlier entry-window restriction: original order expiry must be no later than session close minus **65 minutes**, even in this 15-minute experiment. Do not silently replace it with a 15-minute cutoff when reproducing results.
- Frozen costs: $0.001/share entry fee, $0.001/share exit fee, $0.001/share modeled entry and exit price displacement, no fixed fees. These are research assumptions, not IBKR-calibrated costs.
- Modeled bar/quote/trade/routing delays: 1 second each; quote capacity: 25%. Settlement and available-cash behavior reuse the existing calendar/cash engine.

### Formula versions

Let `A` be causal completed-minute Wilder ATR14 and `H` the highest high of the latest five completed supplied minutes. For the corrected planning grid, valid prices are positive multiples of $0.0001 below $1 and $0.01 at/above $1. `nextValid` is strictly greater; `floorValid` and `ceilValid` must handle crossings of $1 correctly.

| Arm | Meaning |
|---|---|
| `original` | Exact previous 15-minute model, cent grid, forced cap allowance, and legacy target-based admission |
| `no_rr` | Same geometry; remove all inactive-target reward/admission checks |
| `valid_grid` | Also use the finer planning grid; retain the absolute $0.02 minimum cap allowance |
| `bounded_cap` | Also remove forced cap widening; reject an empty executable entry band |

Corrected formulas:

```text
E = nextValid(H)
S = floorValid(E - 1.5*A)
C_valid_grid = max(floorValid(E + 0.25*A), ceilValid(E + 0.02))
C_bounded_cap = floorValid(E + 0.25*A)

Require 0 < S < E <= C.
Executable ask interval = [E, C - 0.001]; reject if empty.
Q = floor(available_settled_cash / (C + 0.001))
Planned loss = Q * (C - max(0, S - 0.001) + 0.002)
Require planned loss <= 0.10 * current economic equity.
```

The stop remains anchored to the trigger, not re-anchored to the actual entry fill. Raw market quotes and simulated fill prices are not rounded to the planning grid. This declared offline grid does not establish complete IBKR instrument/order-type admission rules.

### Results

| Arm | Net P&L | Ending cash | Mean net session return | Trades | No-trade sessions |
|---|---:|---:|---:|---:|---:|
| `original` | -$39.157 | $660.843 | -0.629991% | 6 | 3 |
| `no_rr` | -$39.157 | $660.843 | -0.629991% | 6 | 3 |
| `valid_grid` | -$11.873 | $688.127 | -0.188117% | 6 | 3 |
| `bounded_cap` | +$15.228 | $715.228 | +0.241714% | 1 | 8 |

The original version exactly reproduced the prior archived 15-minute economic record. Removing unused reward/risk admission alone also produced exactly the same economic record. Both controls passed before interpreting the corrected versions.

The finer-grid version improved by $27.284, entirely on two sessions. The changed SES trades filled only **75/1120** and **25/1072** requested shares, deploying **$44.955** and **$15.5675**. Both lost money. Much of the apparent improvement reflects reduced exposure, not established better prediction.

The fully corrected version's only entry was FTFT on **September 14**:

- First fill: `2026-09-14T15:15:30.198679439Z`; **148 requested and filled shares**.
- Entry $4.681; trigger $4.68; cap $4.70; stop $4.53.
- Cash deployed including original entry fee: **$692.936**.
- Requested planned loss: **$25.604**, about **3.66%** of $700 equity.
- Exit requested at 15 minutes; final exit completed at **903.9429 seconds**, about **15 minutes 4 seconds**. Two exit fills.
- Net P&L: **+$15.228** under original research costs.

The bounded cap creates an implicit execution-feasibility filter. Away from grid crossings, the band requires `floor(0.25*A/tick)*tick >= entry_slippage`. At prices at/above $1 with a $0.01 tick and $0.001 displacement, minute ATR must be at least **$0.04**. This excludes some winners as well as losers; it is not demonstrated predictive skill.

### IBKR Pro Fixed sensitivity

The separate check used the published base-commission formula recorded during the October 4 investigation:

```text
base commission per recorded order = min(max(0.005 * executed_quantity, 1),
                                         0.01 * executed_notional)
```

Source: [IBKR stock commissions](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php). This handoff did not refresh the schedule. Validate effective historical dates and all applicable fees before a broker-calibrated rerun.

The frozen registration still says the broker question was pending. That is historical provenance: the later IBKR Pro Fixed clarification informed the separate sensitivity only. Preserve the registration rather than rewriting it to look as though the broker was known before the primary run.

| Arm | Recorded P&L after substituting base commissions, before other fees |
|---|---:|
| `original` / `no_rr` | -$56.471 |
| `valid_grid` | -$19.605800 |
| `bounded_cap` | +$13.524 |

These are **same-fill calculations**, not a new IBKR simulation. Quantities, fills, and future cash paths were not recomputed. Partial fills were grouped by parent order rather than charged a new minimum per fill. The FTFT trade incurs two $1 base commissions instead of $0.296 original explicit fees.

Changing fees also changes affordability: four of the eight submitted `bounded_cap` requests exceed available cash when funded at their caps with these base commissions, although its sole filled request passes. A complete fee model must enter sizing and cash reservation before admission. Additional regulatory charges, historical effective-date proof, final billing rounding, and routing calibration remain missing.

## Verification and evidence

Recorded completed-study checks:

- **71 unique tests passed**: 12 new adapter/runner tests, 55 inherited cash/replay tests, 4 independent audit tests.
- Four separate commission-formula assertions passed; these are not counted in the 71.
- Independent audit reconciled **160 raw-bar geometry calculations, 83 submitted orders, and 45 fills**, with no mismatches.
- All nine sessions valid in each arm; all accounts flat at session close.
- Original-vs-archived and no-RR-vs-original economic comparisons passed.
- Historical runtime about **21 minutes 6 seconds**, peak memory about **1.54 GiB**, exit code 0.
- `graphify update .` completed after the research-code changes; no graph topology changes were detected.

Handoff-day checks on October 6: all **13 report-linked artifact hashes** and all **50 source/input hashes** in the run identity still match. Saved logs report the 12/55/4 passing tests. No backtest or test suite was rerun to write this document. This document adds no implementation changes, so it does not require another code-graph refresh.

Key artifacts, relative to `nomisma/artifacts/geometry-repair-700-20261004/`:

| File | Purpose |
|---|---|
| `coordinator-report.json` | Consolidated findings, limits, roles, and artifact hashes |
| `registration.json` | Frozen experimental specification and acceptance criteria |
| `execution/run-identity.json` | Exact interpreter, historical command, configuration and source/input hashes |
| `execution/config.json` | Base configuration; effective adapter/registration overrides also matter |
| `execution/summary.json` | Aggregate outcomes |
| `execution/economic-comparison.json` | Both control comparisons and explicit metadata exclusions |
| `execution/runs/<arm>/result.json` | Detailed per-arm replay record |
| `data/verification.json` | Independent raw-data/execution audit |
| `test-manifest.json` | Test counts and log hashes |
| `ibkr-commission-registration.json` | Separately registered commission check |
| `ibkr-commission-sensitivity.json` | Detailed same-fill commission/funding calculations |
| `coordinator-verification.json` | Coordinator checks |
| `data/final-preservation.json` | Preservation evidence |

Research code added in that study: `execution/adapter.py`, `execution/runner.py`, `execution/test_adapter.py`, `data/audit.py`, and `data/test_audit.py`. Registration, identities, logs, and results accompany them. The experiment did not change application trading behavior or prior study artifacts.

Historical replay invocation, from `/Users/barry/heuresis/nomisma`, is recorded below for provenance only. **Do not run it into the frozen completed study directory.** Use a new study directory with explicit source/version registration for further experiments.

```sh
/Library/Developer/CommandLineTools/usr/bin/python3 -B artifacts/geometry-repair-700-20261004/execution/runner.py run
```

Recorded environment: Python 3.9.6, macOS 26.5.1 arm64, one shared decoder. The runner also has a `prepare` action; do not overwrite existing identities/configuration while trying to inspect results.

## Stuck problems and missing evidence

1. **No demonstrated marketwide selection edge.** The six symbols were chosen retrospectively, and the replay uses first-feasible entry rather than comparing all eligible stocks. Point-in-time common-stock membership and wider causal data are needed.
2. **No untouched evaluation sample.** These nine sessions have already informed investigation. More tuning on them cannot produce an independent validation claim.
3. **No broker-realistic cash/execution replay.** The IBKR overlay does not resize requests, recompute future cash, model all fees, or validate native order behavior.
4. **No credible gain or duration forecast.** One positive corrected trade cannot establish expected payoff, probability of success, or optimal holding period.
5. **Incomplete intraday valuation coverage.** Unknown valuation intervals remain (original/no-RR: 119 each; finer grid: 180; bounded cap: 15). Any observed drawdown is not a complete maximum-drawdown estimate.
6. **Agent capacity was a prior operational limitation.** Reactivating `infra_engineer` for the completed experiment failed at the thread limit; the main coordinator ran the replay. This does not invalidate the recorded run, but do not claim infrastructure-agent execution or formal reviewer/risk-officer sign-off.

These are evidence gaps, not an unresolved coding exception or an outstanding user approval question. The October 6 environment allows workspace writes but restricts network access and has approval policy `never`; verify actual data/tool availability when resuming and do not claim a network failure until tested.

## Recommended next steps

1. **Freeze a broker-aware execution specification.** Researcher and data engineer verify IBKR order/grid rules and effective fees. Developer integrates costs into request sizing, cash reservation, settlement, and exits. Verify full and partial fills, cap affordability, minimum commissions, stop gaps, and unresolved exits. Preserve the old study as a control.
2. **Resolve broader data feasibility before fitting.** Build a point-in-time eligible common-stock universe and causal bars/quotes with request metadata, corporate actions, timestamp semantics, coverage checks, and immutable raw responses. Keep the $0.10–$10 default; treat higher-priced exceptions as a separately specified policy.
3. **Register a small stock-selection/entry comparison.** Use the agreed mean net session return objective, one shared $700 cash account, at most one filled entry/day, and abstention. Freeze admission, ranking/tie rules, costs, and the candidate count before inspecting evaluation outcomes. Do not start with a large score-weight search on these nine sessions.
4. **Evaluate chronologically on unseen sessions.** Separate development/selection from an untouched holdout; purge overlapping outcome windows as applicable. Report session-level uncertainty, participation, funding utilization, losses, and dependence between alternatives. Keep a trial ledger.
5. **Only then investigate exit parameters and forecasts.** Distinguish the planned holding deadline from actual exit completion and from a probabilistic return forecast. Assess net stop/timer outcomes and uncertainty before adding an active target or displaying an expected gain.
6. **Follow the project specialist review workflow for substantial changes.** Obtain independent review and exact-version risk assessment before any readiness claim. Paper execution requires a separately scoped user request; no live orders or live deployment are authorized.

## Pitfalls for the next coordinator

- Do not label `bounded_cap` a fitted winner. One trade is all the positive evidence; `selected_config` must remain unset until validation supports selection.
- Do not interpret +0.241714% as a forecast, or average only the traded session. The primary average includes all nine sessions.
- Do not confuse requests with fills: the user wants nearly all capital requested, but simulated liquidity may fill only a small fraction.
- Do not attribute the finer-grid improvement entirely to better stock selection. Exposure changed substantially.
- Do not treat arms as independent observations or as the same entries with different exits. Corrected geometry changes eligibility, timing, and symbols.
- Do not silently widen caps, clip an over-$10 cap, downsize for risk, round raw quotes, re-anchor the stop, change the 65-minute cutoff, or reactivate a target while reproducing this test.
- Do not read base configuration fields alone as the effective policy. Legacy account limits, cent ticks, or RR fields can remain while the registered adapters override or deactivate them.
- Do not treat a planned stop or session-close policy as guaranteed liquidation. Gaps, missing quotes, halts, and insufficient capacity can leave exposure unresolved; do not invent an exit.
- Do not charge every partial fill a fresh minimum commission or merely subtract IBKR fees after the replay when claiming broker-realistic returns.
- Do not use current universe membership, later full-day volume, revised future data, or current snapshots as if they were available at the original decision time. Exact live-alert replay requires original event timing/order and receipt history.
- Keep artifacts immutable and version new studies. Preserve existing dirty workspace files; no reset, broad cleanup, or attribution of all current modifications to this experiment.

## Coordination and retrieval instructions

Read [workspace AGENTS.md](../AGENTS.md) and [Nomisma AGENTS.md](../nomisma/AGENTS.md). The project policy supersedes older coordination guidance in `.codex/agents/agents.md`; preserve agent definitions and use each configured agent's actual name.

Actual completed-experiment contributors:

| Agent | Work performed |
|---|---|
| `researcher` | Mathematical specification, adapter/runner review, independent interpretation and arithmetic |
| `developer` | Local research adapter/runner and 12 tests |
| `data_engineer` | Provenance and independent raw-bar/quote/cash audit, including 4 audit tests |
| Main coordinator | Registration, historical execution, inherited tests, integration, fee sensitivity, and final report |

`infra_engineer` could not reactivate for that experiment. No separate `reviewer` or `risk_officer` sign-off occurred. For this handoff, `researcher` completed a read-only evidence/pitfall review against the final report, registration, and project instructions; its eight key points and the historical broker-pending clarification are incorporated. The main coordinator wrote and verified this document.

Use SDL-MCP first for known code/symbol retrieval. Use focused Graphify queries for unresolved documentation/module relationships, not automatic full graph or full `GRAPH_REPORT.md` reads. Verify current source when indexes are stale or unavailable. After actual code modifications, update the existing graph. No broad architecture rediscovery is needed merely to read these known artifacts.

The workspace currently has many pre-existing modified and untracked files. The October 6 handoff task adds **only this file**. The user prefers actual specialist delegation, investigation before implementation, plain-language results, and explicit limits on claims. Keep future changes surgical and reuse the existing replay/data machinery.
