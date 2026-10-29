Holding-period investigation — September 20, 2026

Holding until one minute before the close produced a much larger simulated profit on this FTFT entry, but only in a counterfactual that disabled both the original stop and target. Merely extending the original maximum holding time did not help: the existing stop still exited first. The 5, 10, 15, 30 and 60-minute timer-only exits all lost money. Longer was not consistently better.

The fixed pre-close exit earned $642.964 net under nominal assumptions, $642.168 with doubled costs and $649.934 with doubled timing delays. It required holding nearly six hours and passing through a worst observed conditional net mark of −$132.136 nominally. That mark is not an executable loss estimate or full-account drawdown, and unobserved prices during coverage gaps could have been worse. The user's $100 account-drawdown condition remains discarded; the loss is descriptive evidence, not a reinstated limit.

The entry is the same archived 199 FTFT shares at $4.951 on September 14 at 14:00:37.683404484 UTC (09:00:37.683 Chicago / 10:00:37.683 Eastern), costing $985.448 including the $0.199 entry fee. Cost stress preserves its own original $4.952 entry and doubled fees. Initial capital remains $1,000; this is an exit-only conditional comparison, not a new sizing, entry, cash-settlement or full-account replay.

All 42 results are shown below. Every result includes the modeled entry/exit fees and adverse execution displacement. A requested deadline does not guarantee liquidation at that timestamp or price.

With the original $4.59 stop and $5.68 target retained:

| Maximum hold | Nominal net P&L | Doubled costs | Doubled delays |
|---|---:|---:|---:|
| 2 minutes | +$35.754 | +$34.958 | +$39.004 |
| 5 minutes | −$50.056 | −$50.852 | −$48.556 |
| 10 minutes | −$46.316 | −$47.112 | −$46.316 |
| 15 minutes | −$76.906 | −$77.702 | −$84.376 |
| 30 minutes | −$76.906 | −$77.702 | −$84.376 |
| 60 minutes | −$76.906 | −$77.702 | −$84.376 |
| Close minus 60 seconds | −$76.906 | −$77.702 | −$84.376 |

The original stop requested sale after 727.588547403 seconds (12 minutes 7.589 seconds) and finished selling after 729.041615279 seconds. It fired before the original 15-minute maximum, so longer 30-minute, 60-minute and pre-close deadlines leave the exact same stop execution and loss. Extending a maximum also cannot override the earlier profit/protection exits from the prior exit-rule investigation.

With all price exits disabled and sale requested only at the timer:

| Requested holding period | Nominal net P&L | Doubled costs | Doubled delays | Worst observed nominal net mark before request |
|---|---:|---:|---:|---:|
| 2 minutes | +$35.754 | +$34.958 | +$39.004 | −$30.646 |
| 5 minutes | −$50.056 | −$50.852 | −$48.556 | −$68.456 |
| 10 minutes | −$46.316 | −$47.112 | −$46.316 | −$68.456 |
| 15 minutes | −$63.726 | −$64.522 | −$65.706 | −$86.366 |
| 30 minutes | −$44.576 | −$45.372 | −$44.576 | −$112.236 |
| 60 minutes | −$105.016 | −$105.812 | −$104.766 | −$132.136 |
| Close minus 60 seconds | +$642.964 | +$642.168 | +$649.934 | −$132.136 |

The near-close request was fixed at 19:59:00 UTC / 15:59 Eastern, 21,502.316595516 seconds after entry (5 hours 58 minutes 22.317 seconds). After routing, seven eligible future fills sold all 199 shares between 19:59:01.150468689 and 19:59:01.782870281 UTC at a weighted price of $8.183974874. Nominal total entry/exit fees were $0.398. The replay did not assume a sale of all shares at a prior quote, retrospective peak, or closing print. All 42 cases fully closed within the session; no residual shares required an invented closing sale.

The larger doubled-delay profit reflects favorable subsequent price movement on this particular path. It is sensitivity evidence, not a worst-case bound or proof that delay improves a strategy. Costs and timing were stressed separately; no combined stress was added.

The earlier report's roughly $5.23 peak concerned the earlier holding window. It was not the full-day high. Later prices near $8.18 explain the larger pre-close outcome without contradicting the earlier exit measurements. No retrospective highest-price exit was selected in this experiment.

The diagnostic reuses the frozen prior execution engine and replaces its timer. Retained controls use fresh observed quotes, stop-before-target priority and the same first-trigger latch. Timer-only explicitly ignores both stop and target; original levels remain stored as inactive provenance. Both families preserve quote and routing delays, strictly future eligible raw quote fills, 25% cumulative displayed-bid capacity, partial fills and session-close boundaries. No application strategy or existing result was changed.

The adverse mark uses the original 199 shares and subtracts entry price, per-share entry/exit fees and exit displacement from each fresh valid post-entry bid before the exit request. It does not model selling all shares at that quote, include later execution-period exposure, or measure peak-to-trough account drawdown. Four source RTH-minute slots start at 18:45, 18:46, 18:47 and 18:48 UTC (nominally 18:45–18:49); this is a missing-minute declaration, not a measured exact quote-outage interval. Original receipt times, halt truth and executable depth remain unavailable. The observed minimum does not bound unobserved losses. The risk officer independently measured a 300.000116055-second gap between adjacent valid archived FTFT quote events at 18:44:20.666982939 and 18:49:20.667098994 UTC, with no valid quote inside 18:45–18:49. This describes archived observations, not a confirmed halt or provider outage.

The close-minus-60-seconds horizon was proposed before path extraction, initially kept descriptive, and finally included after later intraday marks had been inspected. All seven horizons were frozen before these model executions, but this remains exposed exploratory analysis. One stock, date and entry cannot establish an optimal holding period or stable profitability. The 42 policy/scenario cells are correlated counterfactuals, not 42 independent trades. No policy or parameter is selected or accepted, and no confidence interval is claimed.

The next useful simulation is a separately frozen comparison of short timed exits, price-based profit protection and the pre-close timer on additional independent entry opportunities. Evaluate net expectancy, interim adverse exposure, completed sales and losses across those entries before changing the strategy. A next-day extension would require a separately specified carry model: local September 15–16 regular-session data exists, but continuous overnight execution and exposure were not modeled here.

Actual work: the coordinator wrote the small isolated wrapper and tests after developer and reviewer activation both failed with the agent thread-limit error. The actual researcher supplied and independently reviewed the mathematical and causal contract. The coordinator reviewed the execution gates and independent audit implementation. The actual infrastructure engineer executes and audits the results; the actual risk officer reviews final evidence. No unavailable specialist is credited with work. No application edits, paper orders or live orders occurred.

Research sources and reproducibility: [specification](../artifacts/holding-period-investigation-20260920/specification.md), [implementation](../artifacts/holding-period-investigation-20260920/diagnostic.py), [synthetic tests](../artifacts/holding-period-investigation-20260920/test_diagnostic.py), [pre-execution review](../artifacts/holding-period-investigation-20260920/pre-execution-review.md), [fixed registration](../artifacts/holding-period-investigation-20260920/registration.json), [path observations](../artifacts/holding-period-investigation-20260920/path-observations.md), and [all first-pass outcomes](../artifacts/holding-period-investigation-20260920/execution-attempt-01/first). Registration SHA-256: `d501f8927fc34982b158b7f73a4ea37897153e6da6407e40cab4ad0352bc552b`.

Validation completed successfully: 27 synthetic tests (16 frozen prior tests plus 11 wrapper tests), six exact archived baseline comparisons, all 42 cases repeated identically, and 318/318 independent audit checks. The audit independently reconstructed all 142 first-matrix sale fills, control requests, fees, P&L and observed marks. All 2,470 pre-existing files and 28 frozen inputs remained unchanged. The 84 diagnostic calls took 219.333 seconds; the independent audit took 15.854 seconds. No execution or audit failure occurred. Application tests were not rerun because application sources did not change.

Execution evidence: [summary](../artifacts/holding-period-investigation-20260920/execution-summary.md), [complete detailed matrix](../artifacts/holding-period-investigation-20260920/execution-summary.json), [independent audit](../artifacts/holding-period-investigation-20260920/execution-attempt-01/independent-validation.json), [six baseline comparisons](../artifacts/holding-period-investigation-20260920/execution-attempt-01/baseline-parity.json), [exact repeat](../artifacts/holding-period-investigation-20260920/execution-attempt-01/matrix-repeat.json), [preservation](../artifacts/holding-period-investigation-20260920/execution-final-preservation.json), and [111-file execution inventory](../artifacts/holding-period-investigation-20260920/execution-evidence-inventory.json). Inventory SHA-256: `d5ac9612a3483cba1ecd8859e6720a2699d216f7f94ec6199c878fb4ce9532e6`. The coordinator report and later risk assessment are outside this execution inventory.

The actual risk officer independently verified all 42 repeats, 142 quote-linked fills, cumulative capacity, adverse marks, 28 frozen hashes and the 111-file execution inventory, and found no material defect. The [final assessment](../artifacts/holding-period-investigation-20260920/risk-assessment.md) approves the verified offline diagnostic and descriptive report only; it does not accept a trading configuration or establish stable profit. Prior task reports and simulation artifacts remain preserved.
