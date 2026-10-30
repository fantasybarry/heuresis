Cross-stock 15-minute qualifying-entry test — September 20, 2026

The qualifying-entry replay produced one FTFT trade and no SES or TE trades. The nominal 15-minute FTFT exit lost $63.726 after costs and ended with $936.274 from the initial $1,000. SES and TE each stayed at $1,000 because none of their confirmed alerts passed all entry checks. Their trade returns are unavailable, not zero-return trades or evidence of superior stock performance.

This implements the user's requested fifteen-minute intraday comparison and explicit choice to keep qualifying buy signals. It tests the three available stocks across nine dates, but it does not establish cross-stock traded performance: there is still only one underlying traded entry. Six-hour and overnight holding were excluded. The previous $100 account-drawdown requirement remains removed.

Each stock represents a separate alternative $1,000 cash account, not a simultaneous allocation from one account or a combined $3,000 portfolio. Cash and T+1 settlement continue across September 3, 4, 8, 9, 10, 11, 14, 15 and 16; capital is not reset each morning. Buy signals, confirmation, admission, one filled entry per date and actual quote-capacity constraints are unchanged. All affordable settled cash is requested when an entry is admissible.

Nominal timer-only results:

| Stock | Completed trades | Shares bought | Cash deployed including entry fee | Net account P&L | Ending settled cash | Return on traded entry cost |
|---|---:|---:|---:|---:|---:|---:|
| FTFT | 1 | 199 | $985.448 | −$63.726 | $936.274 | -6.4667% |
| SES | 0 | 0 | $0.000 | $0.000 | $1,000.000 | N/A — no trade |
| TE | 0 | 0 | $0.000 | $0.000 | $1,000.000 | N/A — no trade |

The primary rule requests sale exactly 900 seconds after the actual entry fill, with original stop/target price exits disabled for this comparison. The reference retains those price exits with a fifteen-minute maximum. All unique scenario results are shown below; the SES/TE zeros describe flat-account P&L without a trade.

| Stock | 15-minute timer: nominal | Timer: doubled costs | Timer: doubled delays | Original stop/target reference: nominal |
|---|---:|---:|---:|---:|
| FTFT | −$63.726 | −$64.522 | −$65.706 | −$76.906 |
| SES | $0.000 | $0.000 | $0.000 | $0.000 |
| TE | $0.000 | $0.000 | $0.000 | $0.000 |

FTFT's timed exit reduced the nominal loss by $13.180 relative to the original stop exit, but every tested cost/timing fixture remained negative. Changing the maximum while keeping the original stop still exits earlier at that stop. The retained reward/risk entry gate is an admission filter; it does not promise that the timer-only exit achieves the original reward/risk ratio.

The FTFT entry was 199 shares at $4.951 on September 14 at 14:00:37.683404484 UTC (09:00:37.683 Chicago / 10:00:37.683 Eastern). It deployed $985.448 including the $0.199 entry fee, leaving $14.552 settled cash. The nominal exit request occurred at 14:15:37.683404484 UTC and six future quote-linked fills completed at 14:15:39.033048496 UTC, 901.349644012 seconds after entry. Weighted sale price was $4.632768844; total entry/exit fees were $0.398. The account return was −6.3726%; return on the actual deployed entry cost was −6.4667%.

The doubled-cost exit also finished after 901.349644012 seconds; doubled timing finished after 902.961352871 seconds. Fifteen minutes denotes the sale request, with routing and available capacity determining completion. Every unique historical case completed all nine dates and had zero residual shares. The adapter would stop a branch at an unresolved session close and leave later dates unevaluated rather than invent a sale or continue overnight.

Nominal observed peak-to-trough marked-equity drawdown was $141.290, with peak marked equity $1,054.924. This is distinct from the final loss versus starting capital and is not a guaranteed full intraday drawdown measurement. No $100 threshold or account-risk sizing was applied. There were no valuation-unknown intervals while the nominal or doubled-cost FTFT position was open under the model's freshness convention; doubled timing recorded 0.748023096 seconds of unknown equity. These observations do not establish continuously executable liquidity.

The nominal qualifying-entry exclusions explain why the other stocks supplied no trades. Stress fixtures can change the mix of rejection reasons: doubled-cost SES has 19 reward/risk failures. Independent accounts eliminated competition for cash; admission rejections still prevented entries:

| Stock | Confirmed alerts | Reward/risk rejection | Empty admissible entry-price interval | Stale planning quote | Too late in session | Orders submitted |
|---|---:|---:|---:|---:|---:|---:|
| SES | 26 | 17 | 2 | 6 | 1 | 0 |
| TE | 28 | 0 | 22 | 4 | 2 | 0 |

Both SES and TE remained untraded in all three primary fixtures and their nominal reference runs. Their entry restrictions were not relaxed to manufacture observations. For example, two archived TE plans had a $4.39 trigger and $4.39 cap; a positive $0.001 entry displacement makes that ask interval impossible. FTFT generated four nominal orders, of which three expired without a fill and one entered the traded position.

Nominal daily activity below uses confirmed alerts / filled entry episodes. A confirmed alert still needs an admissible plan and an executable future quote.

| Date | FTFT alerts / entries | SES alerts / entries | TE alerts / entries |
|---|---:|---:|---:|
| 2026-09-03 | 0 / 0 | 0 / 0 | 9 / 0 |
| 2026-09-04 | 0 / 0 | 0 / 0 | 7 / 0 |
| 2026-09-08 | 0 / 0 | 0 / 0 | 0 / 0 |
| 2026-09-09 | 0 / 0 | 0 / 0 | 3 / 0 |
| 2026-09-10 | 8 / 0 | 5 / 0 | 2 / 0 |
| 2026-09-11 | 2 / 0 | 0 / 0 | 0 / 0 |
| 2026-09-14 | 7 / 1 | 14 / 0 | 3 / 0 |
| 2026-09-15 | 0 / 0 | 6 / 0 | 4 / 0 |
| 2026-09-16 | 0 / 0 | 1 / 0 | 0 / 0 |

The same exposed archive contains 761 missing RTH minute slots for FTFT, 60 for SES and zero for TE. Zero missing minute bars does not establish complete quote freshness or original receipt/halt information. The new report schema preserves data blockers separately from no-signal, rejected-plan, unfilled-order and funding/selection explanations; these classifications can overlap. Known flat-account P&L remains zero even when missing observations limit what the strategy test can establish.

This is retrospective development evidence from three previously selected stocks. The repeated and stress runs reuse the same opportunities and are not additional independent trading samples. The test supports no optimal duration, stable-profit claim, inferential confidence interval or accepted trading configuration. A broader traded comparison requires additional stock/date data containing qualifying, executable entries under the chosen rules.

Actual specialist work: researcher specified the protocol; data_engineer verified source coverage and archived rejection evidence; developer implemented the isolated adapter and eleven focused tests; reviewer independently reviewed the final source and execution/audit logic and resolved a partial-data reporting issue; infra_engineer runs and reconciles the frozen experiments; risk_officer independently checks final evidence. Main owns registration and this report. No application source or prior task report was edited, and no paper or live orders were submitted.

Added files are this report and the [isolated research folder](../artifacts/fifteen-minute-cross-stock-20260920), including [adapter](../artifacts/fifteen-minute-cross-stock-20260920/adapter.py), [tests](../artifacts/fifteen-minute-cross-stock-20260920/test_adapter.py), [specification](../artifacts/fifteen-minute-cross-stock-20260920/specification.md), [data feasibility](../artifacts/fifteen-minute-cross-stock-20260920/data-feasibility.md), [pre-execution review](../artifacts/fifteen-minute-cross-stock-20260920/pre-execution-review.md), [registered jobs](../artifacts/fifteen-minute-cross-stock-20260920/registration-plan.json), and [68-file frozen registration](../artifacts/fifteen-minute-cross-stock-20260920/registration.json). Registration SHA-256: `3dc4a5a4785dbb6430d42ae4ce5e4fb86ba8e9f82cfe982087cbc48dc30637a2`.

Validation completed: all 72 targeted tests passed (19 existing all-in, 21 cash, 21 replay and 11 new adapter tests). The original FTFT reference and all three FTFT timer fixtures passed four archived parity gates before SES/TE execution. All fifteen registered runs completed, covering twelve unique cases and three actual nominal repeats. Every nominal repeat result was identical. All cases finished their nine dates without residual exposure. The separate independent audit passed all 63 aggregate checks and reconciled 30 modeled fills, 365 ledger snapshots and 16,011 saved equity events across the fifteen runs. These repeated observations do not enlarge the underlying trade sample.

All 68 frozen inputs and 2,588 pre-existing files remained unchanged. A transient postprocessing launcher had a Python whitespace syntax error before finalization or auditing began; the error was recorded, only the launcher was corrected, and no model rerun or frozen-source edit was required. All model runs and the subsequently invoked independent audit completed successfully. The targeted tests were appropriate to the isolated adapter; the unrelated full application test suite was not rerun.

Execution evidence: [test results](../artifacts/fifteen-minute-cross-stock-20260920/execution-tests.json), [all runs](../artifacts/fifteen-minute-cross-stock-20260920/execution-report.json), [three exact repeats](../artifacts/fifteen-minute-cross-stock-20260920/execution-repeat-verification.json), [independent audit](../artifacts/fifteen-minute-cross-stock-20260920/execution-validation.json), [prior-file preservation](../artifacts/fifteen-minute-cross-stock-20260920/execution-preservation-after.json), and [recorded launcher failure](../artifacts/fifteen-minute-cross-stock-20260920/execution-finalize-launch-failure-01.json). Audit SHA-256: `61bb5b6c28ad60e47a560806f3ace01ddb71cb4f86ce6c08ce51e0a0aefbc481`.

The actual risk officer's [final independent assessment](../artifacts/fifteen-minute-cross-stock-20260920/risk-assessment.md) approves release of the verified offline experiment and descriptive report. Additional read-only checks reconciled all 365 ledger rows, 30 fills, 25 settlement transfers and 16,010 complete saved equity events, and verified three byte-identical repeats. The remaining saved equity event is explicitly unknown. No material defect remains; a trading configuration or stable-profit conclusion is not accepted.

The final [execution summary](../artifacts/fifteen-minute-cross-stock-20260920/execution-summary.md) and [136-file evidence inventory](../artifacts/fifteen-minute-cross-stock-20260920/execution-evidence-inventory.json) retain the complete execution packet. Model runs spanned 480.725 seconds of wall time, with at most two workers; the independent audit took 22.378 seconds. Inventory SHA-256: `43683c6234644dd0c78d41ae73eaabdba917a1237aedf8c22d3cec7abe4be741`. Main verified every inventory file against its recorded size and hash. This report and the later risk assessment are anchored separately in reporting-inventory.json.
