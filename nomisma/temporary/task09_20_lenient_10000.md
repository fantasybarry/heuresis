Lenient entry comparison with $10,000 cash — September 20, 2026

Completed the six-stock, six-exit simulation with $10,000 starting settled cash per alternative account. Leniency increased participation from one stock/one entry to five stocks/11 distinct entries. Of the 36 primary combinations, 3 were profitable, 27 lost money and 6 had no trades. All 10 newly added entry opportunities lost money under every tested exit rule. The change made the simulation more active, but did not improve profitability on these dates.

The same nine development dates were replayed: September 3, 4, 8, 9, 10, 11, 14, 15 and 16, 2026. Each table cell is a separate account continuing across those dates. These are alternative outcomes, not a combined portfolio, and their profits must not be summed as the return of one $10,000 account.

Each cell below shows net account P&L after modeled costs, followed by return on initial $10,000 capital. Dollar values are rounded to cents; exact values remain in the machine-readable results.

| Exit rule | FTFT | SES | TE | GRAB | RR | SERV |
|---|---:|---:|---:|---:|---:|---:|
| Net target 0.5 ATR | −$15.65 (-0.1565%) | −$37.16 (-0.3716%) | −$274.55 (-2.7455%) | −$147.34 (-1.4734%) | $0.00 (0.0000%) | −$9.70 (-0.0970%) |
| Net target 1 ATR | +$184.60 (+1.8460%) | −$37.16 (-0.3716%) | −$274.55 (-2.7455%) | −$147.34 (-1.4734%) | $0.00 (0.0000%) | −$22.20 (-0.2220%) |
| Breakeven after 0.5 ATR | +$41.10 (+0.4110%) | −$37.16 (-0.3716%) | −$274.55 (-2.7455%) | −$147.34 (-1.4734%) | $0.00 (0.0000%) | −$9.70 (-0.0970%) |
| Trail 0.5 ATR | −$9.40 (-0.0940%) | −$37.16 (-0.3716%) | −$274.55 (-2.7455%) | −$147.34 (-1.4734%) | $0.00 (0.0000%) | −$9.70 (-0.0970%) |
| Trail 0.25 ATR | −$9.15 (-0.0915%) | −$37.16 (-0.3716%) | −$274.55 (-2.7455%) | −$147.34 (-1.4734%) | $0.00 (0.0000%) | −$9.70 (-0.0970%) |
| Two-minute limit | +$128.85 (+1.2885%) | −$28.54 (-0.2854%) | −$187.17 (-1.8717%) | −$86.09 (-0.8609%) | $0.00 (0.0000%) | −$12.95 (-0.1295%) |

All six policies executed the same entry timestamps for each stock; later quantities can differ because earlier P&L changes available cash. The 66 primary trade records represent 11 distinct stock/time opportunities repeated across six policies, not 66 independent observations. Repeats add no new observations.

| Stock | Distinct entries per policy | Entry dates in September | Total actual shares bought per policy | Net P&L range across six exits |
|---|---:|---|---:|---:|
| FTFT | 2 | 11, 14 | 1850 | −$15.65 to +$184.60 |
| SES | 1 | 14 | 1650 | −$37.16 to −$28.54 |
| TE | 4 | 03, 04, 10, 15 | 7232–7246 | −$274.55 to −$187.17 |
| GRAB | 2 | 04, 14 | 6139–6149 | −$147.34 to −$86.09 |
| RR | 0 | None | 0 | $0.00 to $0.00 |
| SERV | 2 | 08, 14 | 925 | −$22.20 to −$9.70 |

The control comparisons use the same two-minute policy throughout. The first change isolates starting capital; the second measures the combined effects of the wider entry cap and lower admission ratio. It does not separate those two entry changes.

| Stock | Strict $1,000: P&L / account return | Strict $10,000: P&L / account return | Lenient $10,000: P&L / account return |
|---|---:|---:|---:|
| FTFT | +$35.754 (+3.5754%) | +$185.95 (+1.8595%) | +$128.85 (+1.2885%) |
| SES | $0.00 (0.0000%) | $0.00 (0.0000%) | −$28.54 (-0.2854%) |
| TE | $0.00 (0.0000%) | $0.00 (0.0000%) | −$187.17 (-1.8717%) |
| GRAB | $0.00 (0.0000%) | $0.00 (0.0000%) | −$86.09 (-0.8609%) |
| RR | $0.00 (0.0000%) | $0.00 (0.0000%) | $0.00 (0.0000%) |
| SERV | $0.00 (0.0000%) | $0.00 (0.0000%) | −$12.95 (-0.1295%) |

For FTFT, strict $10,000 cash requested 1,999 shares but filled 950 and cancelled 1,049. It deployed $4,704.40 (47.044% of starting capital), versus 199 shares and $985.448 (98.5448%) in the original $1,000 account. Available quote capacity was unchanged. The larger position needed 18 exit fills instead of 8, with completion at 123.501 versus 121.450 seconds. Profit rose from $35.754 to $185.950, while account return fell from 3.5754% to 1.8595%. Returns on actual deployed entry cost were 3.6282% and 3.9527%, respectively. This was a fresh chronological replay, not tenfold scaling. See the [independent control review](../artifacts/lenient-entry-10000-20260920/control-review.md).

Leniency added the September 11 FTFT trade, which lost $57.10 under every rule before profit protection activated. Therefore the two-minute FTFT account fell from strict +$185.95 to lenient +$128.85. SES never reached its target or protection threshold. TE and GRAB hit their original stops under all five longer-limit policies. The two-minute alternatives reduced losses for those three stocks but remained negative.

SERV demonstrates why reaching a profit trigger does not guarantee a profitable sale. On September 14, a $4.42 observation triggered its 0.5-ATR target or armed-and-triggered its protective stops. After modeled observation/routing delays, 625 shares sold in three fills at $4.409 against a $4.411 entry. Including fees, the trade lost $2.50. SERV’s three protection rules did activate; their matching outcomes do not imply otherwise. The saved highest_observed_bid field omits a terminal target-trigger quote, so it is not a complete post-entry price maximum. See [original-cohort review](../artifacts/lenient-entry-10000-20260920/original-cohort-output-review.md) and [additional-cohort review](../artifacts/lenient-entry-10000-20260920/additional-cohort-output-review.md).

RR still had no fills: each policy submitted four orders that expired unfilled, while three other plans failed the unchanged five-second quote-freshness gate. A recorded expiry alone does not establish which combination of price, capacity or timing prevented execution. Its account P&L is zero and its trade-return estimate is null.

The following actual entry allocations use the two-minute accounts, one row per distinct opportunity. Requested and cancelled quantities refer to the filled order; unfilled orders are separately retained in the full results. Cash used includes the entry fee; percentages use initial $10,000 capital, not cumulative turnover.

| Stock / entry date | Requested | Filled | Cancelled | Cash used | Initial capital used | Trade net P&L | Entry to completed exit, seconds |
|---|---:|---:|---:|---:|---:|---:|---:|
| FTFT / 2026-09-11 | 3245 | 900 | 2345 | $2,755.800 | 27.5580% | −$57.10 | 75.692 |
| FTFT / 2026-09-14 | 1988 | 950 | 1038 | $4,704.400 | 47.0440% | +$185.95 | 123.501 |
| SES / 2026-09-14 | 16103 | 1650 | 14453 | $993.300 | 9.9330% | −$28.54 | 127.372 |
| TE / 2026-09-03 | 2216 | 2216 | 0 | $9,954.272 | 99.5427% | −$75.34 | 121.320 |
| TE / 2026-09-04 | 2133 | 2133 | 0 | $9,880.056 | 98.8006% | −$51.77 | 130.999 |
| TE / 2026-09-10 | 2073 | 650 | 1423 | $3,082.300 | 30.8230% | −$28.60 | 21.386 |
| TE / 2026-09-15 | 2247 | 2247 | 0 | $9,801.414 | 98.0141% | −$31.46 | 121.462 |
| GRAB / 2026-09-04 | 2906 | 2906 | 0 | $9,944.332 | 99.4433% | −$40.68 | 133.987 |
| GRAB / 2026-09-14 | 3243 | 3243 | 0 | $9,897.636 | 98.9764% | −$45.40 | 121.524 |
| SERV / 2026-09-08 | 1999 | 300 | 1699 | $1,494.600 | 14.9460% | −$4.20 | 125.339 |
| SERV / 2026-09-14 | 2255 | 625 | 1630 | $2,757.500 | 27.5750% | −$8.75 | 123.355 |

Actual shares are capacity-limited. The simulation requests all affordable whole shares, permits fills up to 25% of the relevant displayed quote capacity, and cancels the unfilled IOC remainder. TE and GRAB can deploy close to their full settled balances; the smaller FTFT, SES and SERV fills are not fixed share caps. Per-trade fractions of current settled cash, fees, and returns on deployed entry cost are recorded separately. Adding entry costs across dates gives turnover, not simultaneous allocation.

| Stock, two-minute account | Submitted orders | Rejected plans | Unfilled orders | Total fees | Observed drawdown | Unknown-equity seconds |
|---|---:|---:|---:|---:|---:|---:|
| FTFT | 8 | 9 | 6 | $3.700 | $203.400 | 9.737 |
| SES | 13 | 13 | 12 | $3.300 | $28.545 | 26.371 |
| TE | 10 | 18 | 6 | $14.492 | $209.644 | 12.693 |
| GRAB | 12 | 11 | 10 | $12.298 | $118.516 | 85.928 |
| RR | 4 | 3 | 4 | $0.000 | $0.000 | 0.000 |
| SERV | 3 | 1 | 1 | $1.850 | $12.950 | 73.113 |

Observed drawdown is a lower bound because positions sometimes lacked a fresh valid valuation quote. The former $100 drawdown limit remains removed. No continuously known maximum-loss guarantee is claimed. All 49 accounts evaluated all nine dates, completed flat, and ended without unsettled cash, pending orders or residual positions. The latest primary exit request occurred at 900 seconds and the latest completed exit at 914.576798083 seconds (SES). The 15-minute setting governs the request; available future quotes and capacity govern completion. No overnight liquidation was used.

Only the following research settings changed.

| Setting | Earlier comparison | New primary comparison |
|---|---|---|
| Initial settled cash per alternative account | $1,000 | $10,000 |
| Maximum entry price | Trigger plus 0.25 minute ATR, rounded down to $0.01 | Larger of the old cap and trigger plus modeled entry displacement plus $0.01, rounded up to $0.01 |
| Minimum original-geometry net reward/risk | 1.5 | 1.0 |
| Exit policies | Same six policies | Unchanged |

With nominal $0.001 entry displacement, the minimum cap is two cents above the trigger. This leaves $0.019 of permitted ask-price allowance. Cap-dependent requested quantity, reservation, target-at-cap and order status are recomputed together. The original stop and frozen minute ATR are unchanged. The reward/risk threshold is an entry geometry filter, not a forecast of the realized payoff under an early exit. The declared [mathematical specification](../artifacts/lenient-entry-10000-20260920/specification.md) was frozen before new outcomes.

The two target rules use cost-adjusted 0.5 or 1 ATR profit triggers. The breakeven rule arms after 0.5 ATR of modeled net gain. The trailing rules arm at the same threshold and use 0.5 or 0.25 ATR widths, with breakeven protection. These five retain the 15-minute exit-request deadline. The two-minute rule requests exit by 120 seconds; original stops can exit earlier under every rule. Targets/stops trigger delayed liquidation and do not guarantee a fill at the displayed level.

The simulation preserves qualifying signals, confirmation, price/liquidity filters, five-second planning quote freshness, missing-data/share-basis/VWAP checks, 120-second entry expiry, 15-minute planning admission and closing buffer. Each modeled entry/exit fee and each adverse displacement remain $0.001 per share, with zero fixed fees and one-second receipt/routing delays. Cash continues across dates under modeled T+1 settlement and one filled entry episode per date. Entries are not forced.

Validation completed: 98 targeted tests passed; all 49 registered evaluations completed; the strict $1,000 historical result matched under 22 parity checks; all six fresh lenient FTFT repeats matched exactly; and all 152 independent audit groups passed. The audit reconstructed entry geometry, sizing, reservations, raw-quote fills, fees, cash, settlement, exit chronology and observed equity. The 49 evaluations comprise 36 primary accounts, six strict $10,000 capital controls, one strict $1,000 parity gate and six FTFT repeats. Only the six FTFT accounts were repeated. Recorded signal/decision consistency was checked; the auditor did not independently rebuild the entire monitoring score.

The seven serial model banks consumed 1079.948 seconds in total; peak measured resident memory was 1,197,801,472 bytes. Both resource gates passed. The standalone audit took 38.029 seconds. No model or audit failure was converted into a passing result, and no additional parameter search was performed. All 3,492 protected prior files and all 3,509 frozen inputs remain unchanged.

The actual risk_officer approved release of this verified offline comparison and found no unresolved material accounting, preservation or reporting defect. Its independent pass reconciled all 49 accounts, 2,521 ledger rows, 497 fills, 80 closed trades, 417 settlement transfers and 16,817 saved equity events. Both main and risk_officer independently rehashed the 3,825 distinct frozen/execution files without mismatches. Profitability and paper/live readiness remain unestablished. See the [final risk assessment](../artifacts/lenient-entry-10000-20260920/risk-assessment.md) and [reporting preservation verification](../artifacts/lenient-entry-10000-20260920/reporting-evidence-verification.json).

Limitations remain material: nine exposed development dates; exit rules previously selected using the known FTFT outcome; retrospective stock membership and a disclosed coverage amendment; 934 missing RTH-minute slots; modeled receipt/route/cash-posting times and unavailable original halt/point-in-time metadata. These are nominal-cost runs, with no new cost/timing stress or untouched holdout. More trades did not create independent validation, and no stable-profit configuration or selected trading policy was accepted.

Actual assignments: researcher specified the math and bounded comparisons; developer implemented the isolated adapter and focused tests; reviewer independently reviewed the frozen implementation, capital controls and completed cohort outputs; infra_engineer ran the registered tests, replays, repeat checks and independent audit; risk_officer assessed the final evidence. Main coordinated and produced this report and reporting checks. The earlier data engineer’s catalog/provenance work was reused; no new ingestion was required.

New files are confined to [artifacts/lenient-entry-10000-20260920](../artifacts/lenient-entry-10000-20260920) and this report. They include the specification, adapter/tests, five account configurations, frozen registration, execution/audit tooling, 49 result sets, summaries, reviews and reporting evidence. Existing application strategy files and earlier reports were preserved.

Full per-cell and per-date quantities, rejected/unfilled orders, fees, deployment, returns on deployed cost, timing, drawdown, unknown intervals and residual checks are available in the [execution summary](../artifacts/lenient-entry-10000-20260920/execution-summary.md), [detailed summary JSON](../artifacts/lenient-entry-10000-20260920/execution-summary.json), [independent audit](../artifacts/lenient-entry-10000-20260920/execution-validation.json) and [reporting arithmetic](../artifacts/lenient-entry-10000-20260920/reporting-analysis.json). The [prior six-stock report](task09_20_six_rules_six_stocks.md) remains unchanged.
