# Task09_17 — investigation of the negative cash-account results

Investigation date: September 18, 2026, America/Chicago. This is an additive
diagnostic report on the completed pilot, using its frozen development data.

The immediate cause of the single-entry loss was a breakout entry that rose
briefly, failed to reach its target, and reversed into its stop. More concerning
for further research are entry after a substantial prior rise, the unvalidated
target distance, and an interaction between price rounding and entry rules that
eliminated many other opportunities. Correct settlement accounting and larger
capital allowances do not themselves establish a profitable signal.

## 1. What actually lost money

All times in this table are **U.S. Eastern daylight time on September 14**.
The machine-readable evidence preserves exact UTC nanoseconds.

| Event | Time | Evidence |
|---|---|---|
| Confirmed alert and order creation | 09:59:01 | FTFT, score 85, trigger $4.95, cap $5.00 |
| Entry | 10:00:37.683 | 50 shares at $4.951; $0.05 entry fee; $247.60 used |
| First highest bid during the holding period | 10:02:13.647 | $5.23 |
| First stop-trigger quote | 10:12:44.272 | Bid reached the $4.59 stop threshold |
| Lowest bid during the holding period | 10:12:44.309 | $4.53 |
| Exit | 10:12:46.281 | 50 shares at $4.579; $0.05 exit fee |

The frozen target was **$5.68**. None of the **15,355 valid quote snapshots**
from entry up to, but excluding, the exit event reached it. Including the
exit quote adds one snapshot and does not change the extrema. The trade closed after
**12 minutes 8.598 seconds**, before its 15-minute holding deadline.
Consequently, the holding-limit timer did not directly cause this loss.

The highest bid was about 5.64% above the entry fill, whereas the target
required about **14.72%**. At the peak bid, marking all 50 shares at modeled
net liquidation value gives **+$13.80** versus the entry cash cost. This was
an unrealized, conditional quote mark, not an available guaranteed profit.
The first peak quote's displayed bid supported only 25 shares under the
model's 25% capacity rule. A later quote at the same price supported 50;
neither observation constitutes an executed alternative exit strategy.
The modeled low mark was −$21.20, explaining the $35 peak-to-trough observed
drawdown despite the smaller final loss of **$18.70**.

This supports testing insufficient continuation and exit geometry. It does
not justify selecting the observed peak as a new profit-taking threshold.

## 2. The alert identified momentum after a substantial rise

The last completed minute at the decision closed at **$4.9393**, versus
**$3.79 five minutes earlier: +30.32%**. That completed close was about
**20.50% above session VWAP** of $4.09884. These are known-at-decision
features, so they can be studied without looking ahead.

The score of 85 was constructed as follows:

| Condition | Awarded points |
|---|---:|
| Above session VWAP | 20 |
| EMA9 above EMA20 | 20 |
| Rising EMA9 | 10 |
| RSI between 50 and 75 | 0 |
| Minute relative volume at least 1.5 | 15 |
| Completed close above preceding five-minute highs | 10 |
| Positive change from previous-session close | 10 |
| **Total** | **85** |

RSI was **76.31**, outside the preferred band, but that condition only removed
15 points. It was not an eligibility veto. Minute relative volume was 2.7525.
The remaining points still met the “Strong buy” threshold.

Thus, “Strong buy” is a weighted checklist of contemporaneous conditions,
not a calibrated likelihood of a future spike, and certainly not an 85%
success probability. Several conditions describe the same recent rise.
Neither extension above VWAP nor RSI above 75 currently prohibits this entry.
The evidence suggests examining whether the strategy often buys after too
much of the move has already occurred; this single trade cannot establish
that relationship statistically.

Two bars were required for confirmation. The first qualifying bar scored
100 at 09:58:01; the confirming bar scored 85 one minute later. The order
then waited **96.683 seconds** before filling. Pending entry uses frozen
levels and does not recheck the full score at execution. However, the latest
completed-bar decision before this fill remained eligible with score 90,
RSI 69.98 and no blockers. A disqualified or invalidated signal is therefore
**not demonstrated** as the cause of this loss.

Source: [score construction](../nomisma/monitor_metrics.py),
[confirmation and execution](../nomisma/replay.py),
decision `decision-007105` and adjacent decisions in the
[nominal C result](../artifacts/cash-account-20260918/execution-C_single_max/result.json).

## 3. Stop and target parameters describe payoff geometry, not probability

At the decision, ATR was **$0.23465**, about 4.74% of the eventual entry price.
The registered 1.5 ATR stop became **$4.59** after rounding. The target was
twice the entry-to-stop distance, rounded upward, becoming **$5.68** after
the actual fill. This meant approximately **7.29% downside to the stop** and
**14.72% upside to the target**, within a maximum 15-minute holding window.

The formula does not estimate the probability of either level being reached
or how long that would take. A nominal 2:1 reward/risk ratio is not evidence
of positive expected profit. Here, some continuation occurred, but it was
insufficient for the specified target and the fixed stop did not protect the
intermediate gain. Whether a different target, trailing exit or earlier
entry improves overall results remains untested. A tighter stop could also
increase stop-outs; none is selected from this example.

Source: [planner](../nomisma/trade_plan.py) and the frozen trade's levels.

## 4. Price rounding and execution assumptions removed most alternatives

The nominal single-entry run's **71 confirmed alerts** had these mutually
exclusive recorded dispositions:

| Disposition | Count | Meaning |
|---|---:|---|
| Structurally impossible entry interval | 27 | Rounded cap equaled trigger, leaving no room for positive entry displacement |
| Reward/risk rejected | 11 | SES plans failed the minimum conservative net reward/risk bound |
| Quote unavailable to planner | 6 | Quote failed the planner's five-second timestamp requirement |
| Insufficient session time | 2 | Not enough time for holding limit and closing buffer |
| Submitted waiting orders | 4 | Three expired unfilled; one filled |
| Daily entry allowance already used | 21 | Policy blocked further entries after the first fill |
| **Total** | **71** | |

All 27 structural rejections had ATR below **$0.04**, with 20 in TE, five in
FTFT and two in SES. With a one-cent grid and a chase allowance of 0.25 ATR,
rounding down leaves no extra cent when ATR is below $0.04. For example:

```text
trigger = $4.49
rounded cap = $4.49
entry displacement = $0.001
required ask >= $4.49, but ask <= $4.489
```

This is a **parameter compatibility problem** in the research assumptions.
The engine correctly rejects the impossible order. It concentrates admitted
orders in larger absolute-ATR setups and reduces the range of opportunities
the pilot can evaluate. It does not establish that any rejected setup would
have made money. The one-cent increment itself remains an unverified research
assumption and should be validated for the instrument and execution model
before changing rounding or displacement rules.

All 11 reward/risk rejections were SES setups with a one-cent stop distance
and conservative net reward/risk **1.30769**, below the configured minimum
1.5. The 27 structural count is not an exhaustive count of every alert that
would fail that check: earlier rejections and the daily lock prevent some
downstream evaluations.

Data also limited coverage. **4,294 of 10,530 symbol-minute decisions** had
the incomplete regular-session history blocker, which withholds session
VWAP and volume. These overlap other blockers; they must not be added as
independent excluded observations. There were only 388 eligible decisions,
and eligibility plus confirmation/cooldown ultimately produced 71 alerts.

See the full day/symbol funnel and expired-order quote windows in
[diagnostics.json](../artifacts/cash-loss-diagnosis-20260918/diagnostics.json).
All three submitted orders that expired had valid asks below their triggers
throughout their active windows. Their asks did not jump over the permitted
entry interval. This explains their nonfills under the frozen breakout rule.

## 5. Single-entry selection made this day's result worse

The rule selects the **first feasible confirmed alert chronologically**,
with alphabetical ties. It does not estimate which available stock has the
best expected return. After the FTFT fill it blocked 21 later alerts.

The registered multiple-entry cash variant A made the identical first trade,
then two additional trades using remaining settled funds:

| Trade | Net result |
|---|---:|
| First FTFT entry, shared with B/C | −$18.700 |
| Second FTFT entry | +$13.250 |
| Third FTFT entry | −$5.576 |
| **A total** | **−$11.026** |

Those later trades contributed **+$7.674**, which exactly explains A's
better result relative to B/C on this sample. This is a comparison already
executed under registered rules, not permission to select the later winner
with hindsight. One day does not establish that multiple entries are better.

C still had **$752.40 of unused settled cash** after its first purchase.
The one-entry lock is an additional strategy restriction. Cash accounts can
use available paid-for funds for purchases; the settlement restriction
concerns how subsequent transactions are funded, not a universal limit of
one trade per day. See the SEC's
[cash-account bulletin](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins/updated-9).

## 6. Costs and capital allocation were secondary to this loss

At the actual fill quote events:

```text
50 × (exit bid $4.58 − entry ask $4.95) = −$18.50
Modeled entry/exit price displacement       −$0.10
Entry and exit fees                        −$0.10
Net                                         −$18.70
```

The $0.20 comprises about **1.07% of the net loss**. This is a fixed-event
attribution, not a zero-cost replay: changing costs can change order
eligibility elsewhere. The quoted ask-to-bid component includes market price
movement and crossing the spread; this calculation does not separately
identify those two effects.

The existing doubled-cost comparison used the same fill events and lost
$18.90. The existing doubled-timing comparison used the same entry and
stop-trigger quote but exited **2.0836 seconds later**, at a bid five cents
lower, adding **$2.50** to the loss for a total of **$21.20**. All four modeled
delays were doubled in that registered stress; it is not a separately
randomized estimate of routing latency alone.

The nominal exit fill was $0.011 below the $4.59 stop, or $0.55 worse for
50 shares than an exact stop-price fill, before comparing fees. Stops are
triggers rather than guaranteed execution prices; see the SEC's
[order-type bulletin](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-15).

Removing the old allocation ceilings did not change B's position: C still
had a **50-share planning liquidity cap**, versus cash capacity 199 and risk
capacity 242. Both deployed $247.60 and generated identical nominal fills,
trades and ledger. This establishes why maximum allocation did not improve
the result. It does not establish actual market capacity or justify removing
liquidity limits. Performance with nearly all $1,000 deployed remains unknown.

## 7. What the evidence supports next

The strongest research questions are whether extension at entry predicts
weak subsequent continuation, whether achievable moves fit the target and
holding horizon, and whether entry rounding is excluding otherwise feasible
setups. The immediate priority is to verify instrument price increments and
the entry-price contract, then register a limited comparison of entry
quality and exit behavior on broader data, with an untouched evaluation
period. Keep the current replay as the baseline.

For each candidate, record the contemporaneous score components, percentage
extension above VWAP, recent return, ATR/price, time of day, signal age,
target/stop distance, rejection reason, and quote-based favorable/adverse
excursion. Keep rejected setups separate from executed outcomes. Use
causally available information for any selection rule; do not select the
day's eventual best stock or optimize against this observed peak.

All existing comparisons traded **one symbol on one date**. They reuse the
same observations and are not seven independent profitability tests. They
cannot distinguish a generally weak strategy from an adverse example or
estimate a reliable success rate. No revised parameter set is accepted by
this investigation; the prior development-only risk conclusion still applies.

## Work and verification

- `researcher` independently inspected scoring, confirmation, selection and
  target/stop mathematics, and checked the last prefill signal.
- `infra_engineer` independently inspected archived quote paths, displayed
  capacity, costs, timing stress and unfilled orders.
- The coordinator reconciled the decision funnel, exact P&L decomposition,
  policy comparison and quote extrema, and saved this report plus the
  reproducible [diagnostic script](../artifacts/cash-loss-diagnosis-20260918/diagnose.py)
  and [computed evidence](../artifacts/cash-loss-diagnosis-20260918/diagnostics.json).

The diagnostic script verifies all **104 files in the pilot's final evidence
inventory** before and after analysis, verifies the inspected session hashes
against the catalog, and asserts the P&L arithmetic and key counts. It
performs no parameter search or new strategy replay. The prior **525 passing
tests and 54 audit checks** belong to the completed pilot; they were not
rerun or represented as new evidence of profitability.

The existing task09_17.md, task09_18.md, application sources, parameters and
replay outputs remain as previously recorded. This report and its diagnostic
artifacts are the only additions from this investigation.
