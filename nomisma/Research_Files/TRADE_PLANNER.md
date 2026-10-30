# Built-in intraday research planner

The model `intraday-research-v1` creates a conditional research scenario after a confirmed Buy or Strong buy alert. It reports an entry band, stop, target range, hypothetical whole-share quantity, and a maximum holding duration. It never submits orders, observes actual fills, manages positions, predicts the price peak, or asserts calibrated profitability. All default parameters are unvalidated research assumptions.

The mathematical specification was derived by the configured **researcher**, corrected through independent **reviewer** review, and implemented by **developer**. **data_engineer** owns the frozen input contract. The coordinator integrates persistence, HTTP, and UI. Infrastructure and final risk reports describe evidence for the version actually tested.

## In the app

Choose **Model & sizing settings** on Live monitor. The default policy can calculate price levels with suitable alert evidence. Numeric sizing also needs all account and cost inputs and verified quote quantities. Enter equity, cash, remaining dollar-risk budgets, notional limits, and your complete current positions. Explicitly confirm the context; it expires after five minutes. Fees and adverse-execution amounts require explicit values, including zero where justified. Clearing account context disables numeric sizing.

Open **Analyze trade plan** on an alert, or **Open trade plan** in saved alert evidence. New alerts automatically freeze their model output and assumptions. **Analyze current data** evaluates a fresh monitored row using current settings; it neither rewrites the saved analysis nor starts a monitor. Its output is temporary. Older alerts have no original model output, and Nomisma does not invent one. Source/feed must match the active monitor.

Each plan uses the manually supplied context independently. It does not reserve balances across multiple recommendations or track broker positions; do not add hypothetical quantities together as if they formed a managed portfolio. Updated settings never renew the account timestamp without explicit complete confirmation.

For the synthetic demo, current account assumptions are hypothetical scenario inputs. Their five-minute age is checked against the actual alert/request receipt, then a copy is projected onto the simulated session clock. The original wall-clock confirmation stays in the saved settings. Stale/future confirmation disables sizing. This is not historical account evidence.

## Inputs and data provenance

`planning_data.prepare_plan_inputs(alert)` reads only the frozen row, original session, and alert identity. Rows include `decision_at` and `planning_quote`. A quote contains bid/ask, raw and normalized sizes, unit basis, event time, original receipt time, source, and feed. REST receipt is recorded when its response arrives; streaming receipt is recorded when its event is accepted. Rendering never renews quote receipt time.

The input must have matching source/feed/symbol/session, original eligibility, at least 15 contiguous regular-session completed minute bars from the exact open, valid OHLC/share volume, and a latest completed bar no more than 120 seconds old. Quote event and receipt must precede decision time and the quote must be at most five seconds old. Crossed, malformed, future or stale quotes, gaps, duplicate/out-of-order bars and known halts block analysis. Unknown halt coverage remains explicit. No imputation or historical receipt reconstruction occurs.

Current SIP quote sizes are already **shares**, effective November 3, 2025, per [Alpaca's dated size-change notice](https://docs.alpaca.markets/us/changelog/marketdata-bid-and-ask-size-display-change). The generic stream schema's older round-lot description must not cause a multiplication by 100. Older SIP and unverified IEX size conversions remain unknown; synthetic quantities are explicitly invented shares. Known zero capacity remains zero. Unknown quantities withhold numeric sizing while preserving otherwise valid price-level analysis.

Frozen current snapshots establish the evidence for that decision. The system still lacks a complete historical event/revision archive and executable future paths. Existing 5/15/30-minute journal observations are not fills or a strategy backtest.

## Mathematics

Prices and volatility are dollars per share, quantities are whole shares, and risk/cash/notional budgets are dollars. Arithmetic is Decimal internally. The assumed price grid is an editable research input, not a verified exchange increment; grids below $0.000001 are unsupported and serialization must preserve strict price ordering.

For completed minute j, `TR = max(high-low, abs(high-prior_close), abs(low-prior_close))`. Seed ATR14 with the 14 true ranges across the first 15 bars, then use `(13*previous_ATR + TR)/14`. Daily ATR is not used. Let A be this minute ATR and B the highest high of the latest five completed bars.

With research grid delta, stop multiplier k, chase allowance c and reward multiple r:

```text
entry_trigger = delta * (floor(B / delta) + 1)
entry_max     = round_down(entry_trigger + c*A)
stop          = round_down(entry_trigger - k*A)
target(e)     = round_up(e + r*(e-stop))
```

Require `0 < stop < entry_trigger <= entry_max < target(entry_max)` and positive finite ATR. The target range displays the trigger-price and cap-price scenarios. Real lower-bound price improvement is not enforceable by a buy limit; these are conditional scenarios, not an executable guarantee.

Default research settings are k=1.5, r=2, c=0.25, 15-minute hold, two-minute entry validity, five-minute pre-close buffer, 1.5 minimum net reward/risk, 1% recent minute-volume capacity and 25% displayed quote-size capacity. Holding alternatives are 5/15/30 minutes. None is an empirically fitted optimum.

Entry expires at `min(decision + validity, session_close - buffer - holding_duration)`. If already expired, no quantity is supplied. The hold clock would start at the first fill; subsequent fills must not reset it. Stop/target exits would use bid triggers. A halt or partial exit can leave exposure beyond the intended deadline; this planner does not claim liquidation.

### Affine fees and robust sizing

The explicit fee envelopes are `entry_fee(q)=a0+a1*q`, `exit_fee(q)=b0+b1*q`, with all components nonnegative. These envelopes must cover the entire entry/exit including any partial-fill charges. Set `F=a0+b0`, `C=a1+b1`, `Ps=max(0, stop-g)` where g is assumed adverse stop execution, and u assumed target-exit displacement.

```text
loss(q,e) = q*(e-Ps+C) + F
R = min(risk_budget, remaining_daily_risk, remaining_portfolio_risk)
Q_risk     = max(0, floor((R-F)/(entry_max-Ps+C)))
Q_cash     = max(0, floor((cash-a0)/(entry_max+a1)))
Q_notional = floor(min(max_position_notional, remaining_gross)/entry_max)
Q_liquid   = floor(min(participation*median(last20_minute_volumes),
                      quote_fraction*bid_shares, quote_fraction*ask_shares))
Q          = max(0, min(Q_risk, Q_cash, Q_notional, Q_liquid))
```

Nonnegative affine fees make loss and entry cash strictly increasing with q. Their maximum over possible partial fills is therefore the full-Q reservation, satisfying the independent review's cash and risk requirements.

The conservative reward/risk bound must pass before any positive quantity:

```text
numerator = r*(entry_trigger-stop) - u - C - F
denominator = entry_trigger-Ps + C + F
robust_net_rr = numerator / denominator
```

Require positive numerator and ratio at least the configured minimum. This checks the lower entry boundary and a one-share partial. Under the supported nonnegative cost envelopes, unrounded net reward/risk increases with entry price and quantity; upward target rounding only improves the bound. Checking only the cap-price target is incorrect. The model counts ask/bid sides rather than adding another full spread charge.

Account context must be complete, explicit, nonnegative, at most five minutes old and not future-dated. Equity is positive and each dollar limit cannot exceed it. An existing holding in the symbol prevents adding a position. At least 20 volumes and known share capacities are required for sizing. No risk parameter is optimized from historical profits.

## Output states

Every output says `research_only=true`, `calibration_status=unvalidated`, and carries a model/schema version, decision time, policy, reasons and warnings.

| State | Meaning | Quantity |
| --- | --- | --- |
| unavailable | Evidence, known-halt safety checks, or geometry fails validation | null |
| expired | Full holding window cannot fit before the cutoff | null |
| levels_only | Account, costs, or capacity are missing/stale | null |
| no_trade | Known holding, failed reward/risk or exhausted budget/capacity | 0 |
| wait | Hypothetical size exists; current ask condition does not pass | positive |
| conditional | Hypothetical size and current ask/slippage condition pass | positive |

The UI updates expiry while the modal is open and after background resume. Stored output remains frozen; displayed prices preserve sub-cent increments. Stops and liquidity caps are scenarios, not guaranteed loss or fill limits.

## Validation and remaining research

`python3 -B -m unittest discover -s tests -v` covers math, normalization, immutable snapshots, current reanalysis, settings confirmation, source separation, backup validation and HTTP origin protections.

`python3 -B tools/planner_check.py --browser --output artifacts/planner-check` runs independent invented scenarios, enumerates partial-fill comparisons, checks repeated deterministic execution and optional isolated Chrome desktop/mobile flows, and records source hashes/environment. This is synthetic engineering validation, **not a historical strategy backtest**. It requires no real account credentials or real database changes.

The initially inspected local history contained 57 real SIP alerts across three sessions; the later feasibility audit covered 78 across four sessions. Neither establishes optimal parameters or profitability. A future fit requires executable quote paths, availability-versioned features/labels, realistic latency/impact, complete cohort and missing-outcome accounting, chronological portfolio replay and independently held-out periods. Prespecify acceptable loss/drawdown, precision, sample/coverage and stability gates before inspecting results. The corrected proposed 27-policy research family is k in {1,1.5,2}, r in {2,2.5,3}, h in {5,15,30}; r=1 cannot pass the current 1.5 minimum net reward/risk gate, and r=1.5 leaves no room for relevant positive costs. Larger values still need to pass the actual gate. Expanding the search expands the multiple-testing burden. No automatic fitting or trading-readiness approval is part of this release. The separate fixed-policy engineering pilot is specified in [REPLAY_SPEC.md](REPLAY_SPEC.md).
