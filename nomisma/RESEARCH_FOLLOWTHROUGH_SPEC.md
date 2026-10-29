# Research follow-through, 18 September 2026

This additive study executes bounded remaining work from `temporary/task09_17.md`.
It does not change the existing app, replay engine, calibration engine, or prior
experiment artifacts. Registration is in
`artifacts/research-20260918/registration.json`. Earlier outcomes were already
examined; all reuse is development analysis, not an untouched holdout.

## Confirmed account constraint

The user supplied $1,000 capital and clarified: “Maximum total account drawdown
of $100.” Use a **fixed dollar drawdown from the running equity peak**. The
initial equity floor is $900. A later $1,100 peak raises the floor to $1,000.
The $100 allowance does not reset each session and does not increase with equity.

Other frozen fixture limits ($25 per trade, $100 daily realized-loss debit,
$75 reserved portfolio risk, $1,000 maximum position and $3,000 gross ceiling)
remain additional engineering assumptions. Cash availability still applies.
They are not user-confirmed optimal allocations. Fees, slippage, latency and
economic precision requirements have not been established from actual executions.
No minimum profitability target or acceptable estimation error is invented.

## Conditional liquidation equity and guard

Observe each historical quote at event time plus the configured quote delay.
Original historical receipt timestamps remain unknown. The newest observed
invalid quote invalidates the prior valid quote. A quote is fresh through five
seconds of **event age**, then expires at five seconds plus one nanosecond.
The five-second bound is a declared engineering assumption.

For complete marks:

```
position_liquidation = quantity * (max(0, bid - exit_displacement) - exit_fee)
E = cash + sum(position_liquidation)
H = max(initial_capital, all complete observed E so far)
observed_drawdown = H - E
headroom = 100 - observed_drawdown
```

Entry fees are already in cash; do not deduct them again. Pending cash is not
spent and is not subtracted from equity. Fixed fees must remain zero in this
version. Use matching stop/target exit displacement as required by frozen replay.

Sample at holdings/cash ledger changes, observed held-symbol quote changes,
staleness boundaries and session/share-basis boundaries. Invalid, missing or
stale marks, a known halt, or unresolved share basis make held equity unknown.
Flat cash remains valued. Unknown intervals and their duration must be retained;
observed drawdown can underestimate the true maximum during those intervals.
Historical halt coverage remains unknown, so otherwise valid marks are explicitly
conditional on the inherited quote/execution model. Current metadata does not
retroactively certify historical tradability.

For each position reserve the greater of original remaining scenario risk and
current liquidation value less its net stop-scenario liquidation value (floored
at zero). Subtract these position reservations and original pending-order risk
once from headroom before admitting new risk. A rally can make current
mark-to-stop downside much larger than original entry-to-stop risk. Continue
applying all stricter frozen account limits.

Unknown held equity cancels pending entries and blocks new risk. At
`E <= H - 100`, permanently latch a breach, cancel pending entries, block new
orders and request exits using the existing routing delay and quote-capacity
rules. Record gaps, unresolved holdings and overshoot. This is an observed
threshold control, **not a guarantee that losses cannot exceed $100**.
Passive observation must preserve frozen replay semantics. Existing source
hashes are pinned; additions do not modify the historical engine.

## Data stages and evidence limits

- Obtain the 20 exchange sessions ending on or before 2026-09-02. Freeze exact
  calendar dates before requesting bars. Fetch raw/split minute bars, prior daily
  context and SPY for FTFT/SES/TE. Cap 100 requests and 256 MiB retained payload.
  This is a coverage preflight, not a quotes/trades execution dataset.
- Preserve missing minutes, opening-prefix coverage, rolling 21-minute windows,
  invalid records and share-basis checks. No synthetic bars or fills.
- Snapshot current assets, calendar, clock and corporate-action metadata using
  at most eight GETs. Current asset membership becomes evidence only from its
  retrieval time. It does not establish a defensible historical universe.
- Record one 180-second parsed provider callback stream, at most two connection
  attempts, 200,000 records and 128 MiB. Preserve original/updated bars,
  corrections/cancellations, optional status/LULD channel availability,
  callback wall/monotonic timestamps and transport gaps in a verified hash chain.
  Callback receipt is not socket receipt; pre-start state and clock accuracy
  remain unknown. Do not disconnect an existing app stream to obtain access.

The payload budgets cap retained evidence. A response exceeding the budget can
be received before rejection; these are not strict network-bandwidth limits.
Provider availability or entitlement failures are recorded, not treated as
complete captures. No account balances, positions or order endpoints are used.

Primary provider contracts: [stock stream](https://docs.alpaca.markets/us/docs/real-time-stock-pricing-data),
[assets](https://docs.alpaca.markets/us/reference/get-v2-assets-1),
[corporate actions](https://docs.alpaca.markets/us/reference/corporateactions-1),
[minute-bar construction](https://alpaca.markets/learn/stock-minute-bars).

## Decision funnel and parameter evidence

Audit every decision and order. Count nonexclusive eligibility/plan blockers and
distinguish a structurally empty admissible ask interval from an otherwise
feasible unfilled order:

```
entry_trigger <= ask <= entry_max - entry_slippage
```

Do not widen caps, shorten confirmation or relax costs to manufacture fills.
Any revised entry contract must be a separately registered strategy version.

Reuse the registered 27 combinations of stops {1, 1.5, 2} ATR, rewards
{2, 2.5, 3} and holds {5, 15, 30} minutes. Replaying $1,000 requires actual
portfolio runs, not scaling $10,000 P&L. Preserve continuous account state across
the nine available execution sessions. Stress cost and timing separately for
the fixed baseline and the previously exposed diagnostic leader; neither is a
newly selected candidate. No final holdout exists in this evidence set.

Uncertainty uses a complete finite date/policy return panel and disjoint
chronological validation folds. Resample circular five-session blocks within
each fold, paired across every policy. Preserve fold lengths and pool weighted
session means. Across 10,000 seeded replicates use the nearest-rank 95th
percentile of maximum absolute centered mean/paired-baseline-contrast deviations
for simultaneous intervals. This is an approximate conditional bootstrap,
requiring adequate within-fold dependence/stationarity assumptions.

Before emitting intervals require at least two blocks in every fold, eight
complete nonoverlapping blocks overall, three activity-bearing blocks per
candidate, and nondegenerate variation. Do not silently exclude failed trials.
These prespecified engineering screens are not proof of statistical sufficiency.
Failure produces no interval and no selected configuration. Economic, data,
stability, risk and untouched-holdout acceptance remain additional gates.

The current two-session validation folds and one active trading session cannot
pass those screens. Extending minute coverage alone cannot repair this lack of
independent execution evidence. Final validation requires a candidate frozen
before later unseen outcomes; failed or insufficient evidence must remain open.

## Verification and resource profile

Use meaningful synthetic accounting, timing, basis, stale-mark, breach and
gap-overshoot fixtures; validate paired resampling invariance and incomplete
panel rejection. Independently review additions, run the full existing suite,
profile actual serialized/streaming evidence and peak process memory, reconcile
fills/cash/reservations, and retain hashes of exact sources and results.
Choose worker count from measured memory before expanding execution. Research
and engineering success does not imply paper/live readiness.
