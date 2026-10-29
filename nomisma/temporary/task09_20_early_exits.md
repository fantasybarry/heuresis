Earlier profit-taking investigation — September 20, 2026

Several earlier exits produced a profit for the archived FTFT trade that originally lost $76.906. The 1-ATR profit trigger produced $51.194 net under nominal assumptions, $50.398 with doubled costs and $52.934 with doubled delays. Six of eight new rules were positive in all three fixtures. A tighter initial loss stop reduced the loss but did not make it profitable; the conditional two-minute follow-through check did not improve the result.

This is an exit-only diagnostic of one previously exposed entry. The eight rules were frozen before these new comparisons, after the original path and outcome were already known. They do not establish stable profitability, an optimal exit or an accepted trading configuration. The all-in sizing and removal of the $100 account-drawdown requirement remain in place. No application strategy code or prior result was changed.

Validation: 16 synthetic tests passed, all nine original baselines reproduced exactly, 24 new comparisons completed, and the complete 33-cell matrix repeated identically. The independent audit passed 206/206 checks on its first attempt, reconstructing all 33 exit paths and 99 sale fills, including 58 fills in the new-policy comparisons. All cells ended with zero residual shares. The final risk review found no material diagnostic defect or numerical report misstatement.

The entry remains 199 FTFT shares at $4.951 at 09:00:37.683 Chicago / 10:00:37.683 Eastern on September 14, spending $985.448 including the entry fee. Frozen ATR was $0.2346496914; original stop/target were $4.59/$5.68. Cost stress uses its own archived $4.952 entry and fees; timing stress also preserves its original entry. No entry was moved, selected again or repriced.

| Earlier-exit rule | Nominal net P&L | Doubled costs | Doubled delays |
|---|---:|---:|---:|
| Profit target: net 0.5 ATR ($5.08) | +$9.154 | +$8.358 | +$15.874 |
| Profit target: net 1 ATR ($5.19) | +$51.194 | +$50.398 | +$52.934 |
| Breakeven after net 0.5 ATR | +$24.574 | +$23.778 | +$15.124 |
| Arm at 0.5 ATR; trail by 0.5 ATR | +$7.164 | +$6.368 | +$11.144 |
| Arm at 0.5 ATR; trail by 0.25 ATR | +$7.164 | +$6.368 | +$15.624 |
| Initial stop: 1 ATR ($4.71) | −$48.316 | −$49.112 | −$50.546 |
| Unconditional exit after 120 seconds | +$35.754 | +$34.958 | +$39.004 |
| At 120 seconds exit only if net gain <= 0 | −$76.906 | −$77.702 | −$84.376 |

Original fixed exits produced −$76.906 / −$77.702 / −$84.376 across those fixtures. Original breakeven and trailing exits, activated after a full one-ATR gain, each produced −$5.006 / −$5.802 / −$5.526. All new comparisons fully sold 199 shares within the session. Total entry/exit fees were $0.398 nominally and with doubled timing, or $0.796 with doubled costs. P&L includes fees and modeled adverse price displacement.

Longer modeled delays improved several outcomes because of this path's subsequent price movements. The doubled-delay fixture measures sensitivity; it is not a worst-case bound or proof that latency is harmless. No combined cost-plus-timing stress was run.

Nominal execution details use elapsed seconds from entry. Weighted sale prices precede the separate exit fee; they are not trigger prices.

| Rule | Exit requested after (s) | Fully sold after (s) | Weighted sale price | Sale fills |
|---|---:|---:|---:|---:|
| Profit target: net 0.5 ATR ($5.08) | 45.088 | 46.089 | $4.999000 | 1 |
| Profit target: net 1 ATR ($5.19) | 95.529 | 96.750 | $5.210256 | 3 |
| Breakeven after net 0.5 ATR | 59.379 | 60.931 | $5.076487 | 4 |
| Arm at 0.5 ATR; trail by 0.5 ATR | 52.006 | 53.008 | $4.989000 | 1 |
| Arm at 0.5 ATR; trail by 0.25 ATR | 45.532 | 46.570 | $4.989000 | 1 |
| Initial stop: 1 ATR ($4.71) | 265.585 | 266.661 | $4.710206 | 2 |
| Unconditional exit after 120 seconds | 120.000 | 121.450 | $5.132668 | 8 |
| At 120 seconds exit only if net gain <= 0 | 727.589 | 729.042 | $4.566538 | 3 |

The trade path explains the differences:

- At 45.09 seconds, the observed bid first reached $5.08, marking about $25.074 net gain on 199 shares. After receipt/routing delays, the target exit sold at $4.999 and earned $9.154. The initial crossing reversed below the threshold within roughly four milliseconds.
- At 95.53 seconds, the observed bid reached $5.19. The 1-ATR target requested an exit and fully sold by 96.75 seconds, earning $51.194 over three fills: 25 shares at $5.219, 150 at $5.209 and 24 at $5.209. Later execution prices were favorable here; the model did not assume a sale at the retrospective $5.23 peak.
- Earlier breakeven and tighter trailing rules activated on the first smaller rise and sold before the later larger rise. Breakeven benefited from a rebound during execution. Smaller trailing widths did not automatically generate larger profits.
- The unconditional two-minute rule sold while the trade remained profitable, earning $35.754. The conditional rule found $0.156 per share of positive net marked gain at its nominal checkpoint, passed permanently, and later incurred the original loss. A one-time positive-progress check did not protect subsequent gains.
- A tighter $4.71 initial stop sold sooner and reduced nominal loss to $48.316. It still sat below the entry, so it did not lock in profit.

The observed peak net mark was $54.924 at 96.96 seconds, but displayed capacity at that quote covered only 25 shares. Marks cannot be treated as all-share sale proceeds. [The path extraction](../artifacts/early-exit-investigation-20260920/entry-path.md) records exact crossings, reversals, spreads, sizes and source hashes.

Use costs and entry-time volatility to express a repeatable price rule. For actual entry e, frozen ATR A, per-share entry/exit fees a/b, exit displacement g and the research price grid:

```text
breakeven = round_up(e + a + b + g)
profit_trigger(beta) = min(original_target, round_up(e + a + b + g + beta*A))
net_marked_gain = max(0, observed_bid - g) - b - e - a
```

Targets used beta=0.5 or 1. Earlier protection activated at net marked gain >=0.5 ATR. The trailing stop became the greater of its previous level, breakeven, and the highest observed post-entry bid minus 0.5 or 0.25 ATR, rounded down. Stops never decreased; ATR never refreshed. The [specification](../artifacts/early-exit-investigation-20260920/specification.md) defines the complete equations, timer precedence and invalid-quote behavior.

Earlier targets change the payoff distribution. At ideal nominal target/stop execution, the $5.08/$5.19 triggers offer $0.126/$0.236 net reward per share against $0.364 loss at the unchanged stop. Reward/risk is approximately 0.346/0.648. A simplified two-outcome model would need roughly 74.3%/60.7% winners to break even; delayed fills and gaps change those figures. The original >=1.5 reward/risk entry admission was deliberately not rerun in this fixed-entry exercise. Full-strategy integration must revisit entry/payoff admission rather than assume it retains that ratio.

All targets here trigger a market exit after modeled delays. A resting take-profit limit could restrict sale price but requires a separate queue/non-fill model: touching a limit cannot imply an executed sale. The [SEC stop-order bulletin](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-15) explains execution-price limitations; [FINRA's order-types guide](https://www.finra.org/investors/investing/investment-products/stocks/order-types) describes the price/non-execution tradeoff for limits. Neither source calibrates these ATR or time constants.

The next useful research step is a separately specified full-strategy study of fixed profit-taking and earlier gain protection on additional entry opportunities. Freeze entry rules, payoff admission, exit parameters and execution assumptions before untouched evaluation. Measure expectancy after costs, losses, premature exits before later gains, incomplete exits and sensitivity across active dates/symbols. Partial profit-taking is another possible design, but it was not modeled here. Further tuning to this already-known peak would not establish an edge.

The local rescan found no new independent full quote/trade sessions. The same nine exposed September dates remain, with only one originally traded opportunity and 821 missing regular-session minute slots. Actual receipt, halt, revision and broker execution truth are unavailable. Policies and stress fixtures are correlated counterfactuals, not additional trading samples; selected/accepted policy and confidence intervals remain null.

Actual specialist work: researcher defined the rules; developer implemented the isolated diagnostic and synthetic tests; reviewer independently examined specification, code and execution driver; infra_engineer extracted the path and completed parity-gated execution/audit; risk_officer independently verified all 32 frozen hashes, all 33 byte-identical repeats, and quantities, fees, P&L and activation chronology for all 99 sale fills. The coordinator froze inputs and integrated this report. No recursive delegation, application edits, paper orders or live orders occurred.

Files added are this report and the [research artifacts](../artifacts/early-exit-investigation-20260920), including [diagnostic.py](../artifacts/early-exit-investigation-20260920/diagnostic.py), [test_diagnostic.py](../artifacts/early-exit-investigation-20260920/test_diagnostic.py), path extraction, specification, registration, execution driver and evidence. Existing task09_20.md and prior simulation artifacts are preserved. Final registration SHA-256: `8c70a3882d5ea65c63e30ea752f1d8385393146616d23001a1558f4c8af879dd`.

Execution evidence: [summary](../artifacts/early-exit-investigation-20260920/execution-summary.md), [detailed matrix](../artifacts/early-exit-investigation-20260920/execution-summary.json), [independent audit](../artifacts/early-exit-investigation-20260920/execution-attempt-01/independent-validation.json), [nine exact baseline comparisons](../artifacts/early-exit-investigation-20260920/execution-attempt-01/baseline-parity.json), [complete matrix repeat](../artifacts/early-exit-investigation-20260920/execution-attempt-01/matrix-repeat.json), and [execution report](../artifacts/early-exit-investigation-20260920/execution-attempt-01/execution-report.json). The 66 actual diagnostic calls took approximately 133.12 seconds, with 1.134 GB peak process memory. The audit took 9.95 seconds. The execution preserved all 2,350 pre-existing files and the 32 frozen inputs; no implementation or historical-execution failure occurred. These synthetic tests are the checks run for this artifact-only investigation; the application test suite was not rerun because application sources did not change.

Final preservation and execution evidence are frozen in the [88-file inventory](../artifacts/early-exit-investigation-20260920/execution-evidence-inventory.json), SHA-256 `c2760be128a7bbce1b6cea2f3c435d11d5adc033aa2c9060024906ddec583585`. Later coordinator reporting and risk assessment are separate from that execution inventory.

The actual risk officer's [final assessment](../artifacts/early-exit-investigation-20260920/risk-assessment.md) approves release of this verified offline diagnostic and descriptive report. That approval covers the investigation's correctness; stable-profit, full-strategy and trading acceptance remain unsupported. No additional diagnostic rerun is required.
