Six exit rules across six stocks — September 20, 2026

All 36 first-pass cases completed. Only FTFT traded: one September 14 entry, evaluated under six alternative exits. SES, TE, GRAB, RR and SERV submitted no orders under any rule. Adding stocks therefore did not add an executed opportunity or establish traded performance across stocks. The six FTFT exits all profited on the previously exposed entry, with the 1-ATR target producing the largest observed nominal profit, $51.194. That observation does not establish an optimal or stable-profit exit.

Net account P&L after modeled costs, in dollars:

| Stock | 0.5-ATR target | 1-ATR target | Early breakeven | 0.5-ATR trail | 0.25-ATR trail | Two-minute exit |
|---|---:|---:|---:|---:|---:|---:|
| FTFT | +9.154 | +51.194 | +24.574 | +7.164 | +7.164 | +35.754 |
| SES | 0 — no trade | 0 — no trade | 0 — no trade | 0 — no trade | 0 — no trade | 0 — no trade |
| TE | 0 — no trade | 0 — no trade | 0 — no trade | 0 — no trade | 0 — no trade | 0 — no trade |
| GRAB | 0 — no trade | 0 — no trade | 0 — no trade | 0 — no trade | 0 — no trade | 0 — no trade |
| RR | 0 — no trade | 0 — no trade | 0 — no trade | 0 — no trade | 0 — no trade | 0 — no trade |
| SERV | 0 — no trade | 0 — no trade | 0 — no trade | 0 — no trade | 0 — no trade | 0 — no trade |

Every FTFT rule bought 199 shares at $4.951 on September 14 at 14:00:37.683404484 UTC (09:00 Chicago / 10:00 Eastern). Each deployed $985.448 including the $0.199 entry fee, leaving $14.552 settled cash. The entry request used all affordable cash at its cap; that does not guarantee exactly $1,000 is spent at the actual fill. Each alternative ultimately sold all 199 shares and paid $0.199 in exit fees. The five other stocks bought zero shares and each account ended with $1,000. They have no trade-return estimate.

| FTFT rule | Exit request after entry | Fully sold after entry | Weighted sale price | Ending settled cash | Return on $985.448 deployed | Observed marked drawdown |
|---|---:|---:|---:|---:|---:|---:|
| 0.5-ATR target | 45.088 s | 46.089 s | $4.999000 | $1,009.154 | 0.9289% | $30.646 |
| 1-ATR target | 95.529 s | 96.750 s | $5.210256 | $1,051.194 | 5.1950% | $30.646 |
| Early breakeven | 59.379 s | 60.931 s | $5.076487 | $1,024.574 | 2.4937% | $30.646 |
| 0.5-ATR trail | 52.006 s | 53.008 s | $4.989000 | $1,007.164 | 0.7270% | $30.646 |
| 0.25-ATR trail | 45.532 s | 46.570 s | $4.989000 | $1,007.164 | 0.7270% | $30.646 |
| Two-minute exit | 120.000 s | 121.450 s | $5.132668 | $1,035.754 | 3.6282% | $35.820 |

Account returns on starting capital are respectively 0.9154%, 5.1194%, 2.4574%, 0.7164%, 0.7164% and 3.5754%; these differ from returns on deployed cash. Every realized hold was shorter than 15 minutes. The six nominal cases recorded zero valuation-unknown seconds while exposed under the model's freshness convention. Observed drawdown remains a lower bound on full intraday drawdown, not a loss guarantee. No account-drawdown threshold was applied.

The original FTFT stop was $4.59 and target $5.68. The two modified targets were $5.08 and $5.19. The protective rules ended with stops $4.96, $4.97 and $5.03. Target or stop levels were triggers, not guaranteed sale prices: for example, the $5.08 target led to a $4.999 fill after modeled observation/routing delay. Exit-fill counts were 1, 3, 4, 1, 1 and 8. These causal fills are not retrospective sales at each rule's most favorable price.

The no-trade outcomes are explained by the following confirmed-alert rejections. Counts are per rule and identical across all six rules for each untraded stock; do not multiply them into independent opportunities.

| Stock | Confirmed alerts | Empty permitted entry range | Initial reward/risk rejection | Stale planning quote | Too late to enter | Orders / trades |
|---|---:|---:|---:|---:|---:|---:|
| SES | 26 | 2 | 17 | 6 | 1 | 0 / 0 |
| TE | 28 | 22 | 0 | 4 | 2 | 0 / 0 |
| GRAB | 23 | 17 | 0 | 4 | 2 | 0 / 0 |
| RR | 7 | 4 | 0 | 3 | 0 | 0 / 0 |
| SERV | 4 | 3 | 0 | 1 | 0 | 0 / 0 |

Across these five stocks, 48 of 88 confirmed alerts had an empty admissible entry interval. For example, GRAB's September 3 19:27:01 UTC plan had a $3.47 trigger and $3.47 cap; positive $0.001 entry displacement makes the permitted ask range impossible. RR and SERV also had plans with equal trigger and cap. Changing an exit cannot create an executable entry under that geometry. These accounts had no funding or inter-stock competition blocks. FTFT generated four orders per rule, of which three expired without a fill and one filled the entry. There is still only one distinct underlying executed episode and one active entry date.

The comparison covers FTFT, SES, TE, GRAB, RR and SERV on September 3, 4, 8, 9, 10, 11, 14, 15 and 16. Each stock/rule combination is a separate alternative $1,000 cash account. The 36 accounts are alternative comparisons, not simultaneous investments from one account or a combined portfolio. Cash continues across dates with T+1 settlement and one filled entry episode per day. Every admissible entry requests all affordable settled cash; actual quote capacity can limit the fill. Capital is not reset each morning.

Qualifying buy signals, confirmation, price/liquidity filters, quote freshness, structural entry feasibility and the original reward/risk admission remain unchanged. No entries are forced. The former $100 account-drawdown control remains removed. The original >=1.5 reward/risk gate uses the original stop/2R geometry as a common entry filter; the modified exits do not promise that payoff.

| Rule | Exit behavior |
|---|---|
| 0.5-ATR target | Set a cost-inclusive target at entry plus 0.5 frozen ATR, rounded up to the price grid and capped by the original target. |
| 1-ATR target | Same calculation with 1 ATR. |
| Early breakeven | Once net marked gain reaches 0.5 ATR, raise the stop to cost-inclusive breakeven, rounded up. |
| 0.5-ATR trail | Arm at the same 0.5-ATR gain, then trail the highest valid observed bid by 0.5 ATR, with a breakeven floor. |
| 0.25-ATR trail | Same activation, with a tighter 0.25-ATR trailing distance. |
| Two-minute exit | Request exit after 120 seconds unless the original stop or target triggers earlier. |

All rules start from the original stop; protective rules may raise it. The protective and timed rules retain the original target. Five rules have a 900-second exit-request deadline; the two-minute rule uses 120 seconds. Every rule keeps the original 15-minute planning admission and closing buffer. Routing and partial fills determine actual completion time, so an exit request is not a guaranteed immediate sale. No six-hour or overnight completion is allowed. Any position unresolved at the session close stops that account branch, retains exposure, and leaves completed-account P&L unavailable and later dates unevaluated.

Nominal modeled fees and adverse price displacement are each $0.001 per share on entry and exit, with no fixed fee. Bar, quote and trade receipt delays and routing delay are each one second. These are research assumptions, not verified broker execution costs.

The additions were selected before their test-period quotes, trades or exit outcomes were acquired. The deterministic daily screen expanded to 1,024 candidates from a retrospective current-assets snapshot. Of those, 164 passed the pre-period daily filters; the top twelve by median dollar volume received minute-coverage checks. Selection prices and liquidity used only July 23–September 2, and minute checks used August 31–September 2.

| Addition | September 2 price | Median daily volume | Pre-period RTH minutes, out of 1,170 | Test-period missing RTH minutes |
|---|---:|---:|---:|---:|
| GRAB | $3.53 | 35,746,542.5 shares | 1,170 | 0 |
| SERV | $4.87 | 4,300,524.5 shares | 1,165 | 61 |
| RR | $1.85 | 5,683,346.0 shares | 1,158 | 52 |

The initial strict requirement of all 390 RTH minutes on all three pre-period dates produced only GRAB. That three-stock selection requirement failed and its evidence is preserved. To fulfill the coverage-based exploratory comparison, selection was explicitly amended before test-period acquisition: require at least 21 consecutive minutes from the open on each pre-period date, then rank by minimum daily coverage, total coverage, pre-period dollar volume and symbol. This selected GRAB, SERV and RR. They are the strongest coverage candidates among the tested preflight set, not a claim about all market stocks. Runtime data checks and entry gates were not relaxed.

The new catalog contains 811,858 quotes and 1,570,170 trades across 27 stock-days. All 27 share-basis factors are 1, with no asset or benchmark warmup/basis blockers. Five crossed quotes remain explicit invalidations. Missing minutes remain explicit without synthetic bars or fills. Across all six stocks there are 934 missing RTH minutes: FTFT 761, SES 60, TE zero, GRAB zero, RR 52 and SERV 61. Complete minute bars do not establish complete original receipt, halt or executable-depth information.

The six exit rules were chosen because they previously profited on the exposed FTFT entry. They are outcome-selected candidates, not six independently validated strategies. Membership in the additional-stock universe is retrospective, historical bars are final versions, and original receipt/halt information remains unknown. The matrix is nominal-only; prior FTFT stress results do not establish new-stock cost or timing robustness. Rules and repeats reuse opportunities, so 36 cells are not 36 independent observations. This experiment cannot establish stable profit, an optimal rule or an accepted trading configuration. No-trade account P&L can be zero, but trade-return estimates remain unavailable.

The new study is isolated in [artifacts/six-rule-six-stock-20260920](../artifacts/six-rule-six-stock-20260920). Relevant records include the [specification](../artifacts/six-rule-six-stock-20260920/specification.md), [data selection and acquisition report](../artifacts/six-rule-six-stock-20260920/data/data-report.md), [independent source review](../artifacts/six-rule-six-stock-20260920/pre-execution-review.md), and [frozen registration](../artifacts/six-rule-six-stock-20260920/registration.json). Registration SHA256: `211e78ef3a640182efabe178feb3ced6002dbdb137324595e4d25f3b108e06b7`.

Validation completed: all 84 targeted tests passed (19 all-in, 21 cash, 21 replay, 11 prior-adapter and 12 new-adapter tests). Six FTFT archived-result parity checks passed before expansion. All 42 registered evaluations completed, comprising 36 unique nominal accounts and six fresh FTFT repeats. Each repeat result exactly matched its first pass. Only the six FTFT accounts were repeated; no cost/timing expansion was run. All 42 accounts completed all nine dates with no residual positions or unevaluated later dates.

The separate audit passed all 97 aggregate checks with zero failures. Across the 42 outputs, including repeats, it reconciled 946 ledger rows, 48 modeled fills, 36 settlement transfers and 8,070 saved equity events. These repeated accounting observations do not enlarge the underlying trade sample. Source/entry logic was reviewed and recorded decisions were reconciled; the audit does not independently recompute the entire monitoring score. Main separately matched all 36 report rows and the six FTFT durations, quantities, deployed cash and drawdown figures to the audit.

All 3,215 frozen inputs and 2,735 protected prior files remained unchanged. The serial model batches spanned 958.585 seconds of wall time, with 894.247 seconds summed batch runtime and peak process memory of 1,186,332,672 bytes. The independent audit took 25.686 seconds. No test, model or audit failure was recorded. New files are confined to this report and the new study folder; previous task reports and research artifacts were preserved.

Evidence: [84 tests](../artifacts/six-rule-six-stock-20260920/execution-tests.json), [42 evaluations](../artifacts/six-rule-six-stock-20260920/execution-report.json), [six exact repeats](../artifacts/six-rule-six-stock-20260920/execution-repeat-verification.json), [independent audit](../artifacts/six-rule-six-stock-20260920/execution-validation.json), [prior-file preservation](../artifacts/six-rule-six-stock-20260920/execution-preservation-after.json), [detailed execution summary](../artifacts/six-rule-six-stock-20260920/execution-summary.json), and [277-file execution inventory](../artifacts/six-rule-six-stock-20260920/execution-evidence-inventory.json). Audit SHA256: `e74581dd8c49a191bb4676e7bcf65df909461dc915f9154dec7e6beeb9518d0c`.

The actual risk officer's [final independent assessment](../artifacts/six-rule-six-stock-20260920/risk-assessment.md) approves release of the verified offline experiment and descriptive report only. The officer independently checked all frozen and execution-inventory hashes, reconciled the ledger/fill/settlement/equity counts above, verified six byte-identical repeats, and confirmed the no-trade outcomes and single underlying entry. No material defect remains. A trading configuration or stable-profit conclusion is not accepted.

Main also verified the [277-file execution inventory](../artifacts/six-rule-six-stock-20260920/execution-evidence-inventory.json), all 3,215 frozen files and the 2,735 prior files: 3,484 distinct files hashed with zero mismatches. The final report and risk documents are anchored separately in [reporting-inventory.json](../artifacts/six-rule-six-stock-20260920/reporting-inventory.json), after execution. Earlier execution snapshots retain their then-pending risk status; the later assessment above supplies the final scoped decision.

Actual specialist assignments: researcher specified the six rules and experiment; data_engineer selected and acquired the additions and verified provenance; developer implemented the isolated adapter and synthetic tests; reviewer independently checked final sources, data lineage and execution/audit logic; infra_engineer executed the frozen tests, replays and independent reconciliation; risk_officer assessed the exact validation evidence. Main owns scope, integration and this report. No application source or prior task report was edited, and no paper or live orders were submitted.
