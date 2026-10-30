# Nomisma — first discovery study

Investigate conditions associated with sustained intraday breakouts, including
failed breakouts and ordinary sessions. This is discovery data; results make no
trading-readiness claim until finalists pass the untouched holdout.

## Unit of analysis

- Primary unit: every qualifying opportunity in every stock, labeled under each
  resistance arm, entry policy and order type, with stock and session recorded.
- The one-account simulation is a secondary layer derived from that dataset.
- Uncertainty uses a session-level bootstrap; same-session opportunities are
  correlated.

## Periods

| Period | Dates | Use |
| --- | --- | --- |
| Discovery | October 1, 2025–September 30, 2026 | Signal and feature research |
| Holdout | April 1–September 30, 2025 | Sealed; opened once for finalists |
| Forward | October 2026 onward | Point-in-time collection |

All periods are fixed now, before any data is acquired.

## Universe

- Point-in-time U.S.-listed common stocks priced $0.10–$10 at decision time.
- Include symbols since delisted, reverse-split, or moved to OTC. Failed
  breakouts concentrate in those names; excluding them biases results upward.
- Live trading may restrict itself to currently listed stocks; the study may not.

## Data sources

| Source | Plan | Supplies |
| --- | --- | --- |
| Massive (formerly Polygon) | Basic, free | Grouped daily bars, point-in-time tickers, minute bars with extended hours. Sole source for signals and labels. |
| Alpaca | Free SIP history | Quotes and trades for still-listed opportunity windows; `feed=sip`, end at least 15 minutes in the past. Returns nothing for delisted symbols. |

Both sources are top of book only, without depth.

## Resistance arms

The candidate minute is excluded from resistance construction.

| Arm | Resistance | Earliest signal |
| --- | --- | --- |
| b3 | Highest high of three completed five-minute bars | 9:45 |
| b6 | Highest high of six completed five-minute bars | 10:00 |
| c | Premarket high (comparison) | 9:31 |
| d | Highest high of the prior 30 clock minutes, premarket included before 10:00 | 9:31 |

- Arm d: if more than about 10 premarket minutes in the window have no bar, the
  result is "insufficient premarket"; bars are never synthesized.
- Prior-session after-hours and prior-day levels remain contextual features.

## Time windows

- Primary: signals from the arm's earliest start through 11:00 New York time.
- Secondary: signals from 11:00 to 13:00, reported separately and never pooled.
- Admission cutoff: the earlier of 13:00 and close − 30 minutes. The exchange
  calendar is authoritative.

## Entry comparison

- Immediate: the first qualifying completed one-minute close above resistance.
- Delayed: one additional completed one-minute close above that same
  resistance. Skip the opportunity if confirmation fails or the original stop
  is touched while waiting.
- Model information availability and execution delay.

## Execution

**Still-listed opportunities** are replayed with Alpaca SIP quotes and trades:

- Orders: market, and limits at ask + 0%, 0.5%, 1% and 2%.
- Submission: after the confirming minute closes, plus 1–2 s modeled latency.
- Market fill: at the ask up to the displayed ask size, then subsequent prints.
- Limit fill: only if prints occur at or below the limit within a fixed window.
- Unfilled limits are missed opportunities, recorded with their counterfactual
  outcome.

**Delisted opportunities** use a cost sweep only, reported as a separate group:

- Entry: the next minute's open plus 0.5%, 1%, 2% or 3% one-way cost; exits
  are treated symmetrically.
- Compare spread proxies, such as minute range, against listed opportunities.

A promising arm must keep a positive mean net percent return at 2% one-way
cost.

## Initial stop

For this comparison only, use the trigger-anchored 1.5 × one-minute ATR14 stop
as an unoptimized control. Calculate it once from information available at the
initial signal and hold it fixed across entry policies.

## Opportunity boundaries

- Liquidity floor: the signal minute's dollar volume (volume × close) must be at
  least $20,000, about 8× a full-cash position. Opportunities below the floor
  are kept, flagged, and reported separately. Added after the October 2025
  pilot showed a median signal-minute dollar volume of $4,518.
- One active 15-minute opportunity per stock per arm.
- Repeated above-resistance closes are not new observations.
- After expiry, require a fresh crossing: the preceding close at/below the same
  contemporaneous resistance and the candidate close above it.

## Continuation outcome

Measured over 15 minutes from the first close above resistance, the same clock
for both entry policies:

- No original-stop touch, and an ending price above the initial breakout close.
- At most two consecutive one-minute closes at/below resistance.
- The first recovery close must exceed the initial breakout close; later
  recovery cannot repair a weak first recovery.

## Halts

- Record LULD and other halts as features.
- A stop crossed during a halt fills at the first print after reopening.
- Clocks run through halts.
- Report results with and without halted sessions.

## Candle features (frozen)

Diagnostic features, not rejection rules. Any feature added later is labeled
post hoc.

| Scope | Feature |
| --- | --- |
| Breakout, pullback and recovery candles, each | Upper wick ÷ range |
| | Lower wick ÷ range |
| | Body ÷ range |
| | Close location: (close − low) ÷ (high − low) |
| | Range ÷ ATR14 |
| | Volume ÷ mean of prior 20 minutes |
| Move | Advance: highest high after breakout − resistance, in ATR |
| | Pullback depth: from that high to the lowest low before the recovery close, in ATR |
| | Pullback duration, in minutes |

If no close falls at/below resistance, pullback and recovery fields are null,
not zero.

## Risk and account simulation

Sizing:

- Starting account: $2,440. Sizing uses settled cash.
- Risk per trade: 4.1% of session-open equity, recalculated each session in
  both directions ($100 at $2,440).
- Shares = floor(min(settled cash ÷ entry price including costs, risk ÷
  per-share risk including costs)).
- Reject only when even one share exceeds the risk limit; report how often the
  limit binds.
- Fees and execution costs count toward affordability and net returns.

Selection:

- Take the earliest eligible signal across stocks; alphabetical ties are a
  control.
- At most one filled entry episode per session; no planned overnight holding.
- At the cutoff, cancel pending entries and continue managing existing
  positions.

## Evaluation

Use a fixed protective stop and a 15-minute holding reference measured from
first fill.

| Level | Metrics |
| --- | --- |
| Opportunity (primary) | Mean net percent return per opportunity, with R alongside; win rate; participation; missed fills and their counterfactual return; delay; session-bootstrap uncertainty |
| Account (secondary) | Arithmetic mean net session return including valid no-trade sessions; maximum drawdown; longest losing streak |

## Finalists and holdout

- Choose at most two finalists: highest mean net percent return in the
  primary window, with a session-bootstrap lower 90% bound above zero.
- Percent return is primary because R depends on stop width; with stops near
  1% of price, R amplifies a few trades (October 2025: about +0.9 R gross
  against about 0% gross return). R remains the sizing unit.
- If none qualifies, the result is "no edge found" and the holdout stays
  sealed.
- Further tests may iterate on discovery data.
- The holdout is opened once, only after a committed `FINALISTS` file names
  the finalists.

## Acquisition sequence and gates

1. Download Massive grouped daily bars for April 2025–September 2026 to build
   the point-in-time universe.
2. Confirm that Massive minute bars exist for 5–10 symbols delisted during the
   discovery period.
3. Download minute bars for one pilot discovery month.
4. Go/no-go:

   | Check | Threshold | If failed |
   | --- | --- | --- |
   | Projected primary-window opportunities per arm per year | ≥ 600 | Stop or widen the universe |
   | Delisted share of opportunities | ≤ 20% | Reconsider one month of Massive Advanced for delisted quotes |
   | Projected disk use, from measured bars per stock-day and quote records per window | ≤ 60 GB | Stop and resize |

5. Download full discovery and holdout minute bars promptly; Massive Basic
   keeps a rolling two-year history.
6. Replay every opportunity on minute bars with the cost sweep. An arm
   survives only if mean net percent return stays positive at 2% one-way cost.
   October 2025 result: no arm survives; unconditional gross return is about
   0% against a median spread of 0.93%.
7. Download Alpaca quotes and trades only for surviving arms' opportunities
   above the liquidity floor, including failures, then run the order-type
   replay and analyze.

Evidence handling:

- Preserve raw responses as gzipped JSON, never edited; derive Parquet from it.
- Preserve unknown outcomes.
- Store holdout data in a separate directory, with a SHA-256 manifest recorded
  here. Sealed 2026-10-22: `data/discovery/holdout/MANIFEST.json`, 14,231 raw
  files (grouped daily, ticker snapshots, minute bars April–September 2025),
  manifest SHA-256
  `a770dd255cb035d347ac07f2e1ebce2df3f8fed10a03237edad48d29aa34a34b`.
- Study code refuses holdout dates unless `FINALISTS` exists.

## Condition search (post hoc)

Added after the October 2025 replay showed no unconditional edge.

- Search only decision-time features: breakout-candle features, time of day,
  price, dollar volume, stop width, and breakout margin above resistance.
  Advance, pullback and recovery features occur after the signal and are
  diagnostics only.
- Every rule found this way is labeled post hoc.
- A candidate rule needs gross return above about 1% per trade, which beats
  the median spread, in October 2025.
- It must then hold on the other 11 discovery months, and finally on the
  holdout.
- October 2025 result: "no edge found" for this design.
  - No single decision-time feature quintile exceeds +0.32% gross.
  - The strongest condition, gap ≥ 20% with premarket ≥ $1M, nets −0.20% to
    −0.73% per trade using measured Alpaca SIP spreads at entry and exit
    (median entry spread 0.41–0.50%). Every arm's session-bootstrap lower 90%
    bound is below zero.
- Full discovery year verdict (October 2025–September 2026): **no edge
  found**. No finalists; the holdout stays sealed.
  - Unconditional breakouts are about 0% gross in every arm (−0.06% to
    −0.01% pooled) and positive in at most 3 of 12 months.
  - No single-feature cell reaches 1% gross in any month.
  - The post-hoc candidate (arm c, gap ≥ 40%, premarket ≥ $1M) averages
    +0.53% gross and −0.00% net per trade over 300 trades with measured SIP
    spreads (median 0.48%). Its session-bootstrap lower 90% bound is −0.96%,
    and 41 of 341 trades had no quotes.
  - On the $2,440 account the candidate ends at $2,610 (+$170) after 159
    trades, with a −$1,692 worst drawdown.

## Later stages

Investigate stop placement, upward-only stop adjustments after favorable
movement, and alternative exit durations.

- Upward-only stops were tried early, on October 2025–January 2026, using the
  post-hoc candidate: arm c, gap ≥ 40%, premarket ≥ $1M.
  - The rules tested were breakeven at +1R, and trailing 1.5 ATR or 3 ATR
    below the highest high.
  - Each reduced losses but cut winners more. Net results: −$261, −$119 and
    −$299, against +$104 for the fixed stop.
  - Not adopted; the fixed stop stays.

## Loss follow-up (post hoc)

Added October 20, 2026, after the forensic review of the 39 losing account
trades of October 2025–March 2026
(`artifacts/loss-investigation-20261019/`). Candidate: arm c, primary window,
liquid, immediate entry, gap ≥ 40%, premarket ≥ $1M.

Replay corrections, applied to every later replay:

- Five or more minutes without a bar between the deciding close and the entry
  bar is a suspected halt, and an entry open more than 2% above the deciding
  close is an unfilled limit. Neither is a fill; both keep their counterfactual
  path.
- A time exit whose deadline minute has no bar exits at the next print.
- Minutes without a bar extend a streak of closes at/below resistance.

Test design, fixed before running:

- Exploration on October 2025–June 2026; July–September 2026 tests only
  changes committed in a `CANDIDATE_CHANGES` file first (enforced in code).
- Stops S0–S2 at 1.5, 2.5 and 3.5 ATR below resistance + one tick; S3 has no
  stop and is a diagnostic bound. Optional exit at the next open after a bar
  closing at/below resistance with upper wick ≥ 0.5 of its range.
- Pass at 0.5% one-way: mean net percent above S0, session-bootstrap lower 90%
  bound above zero, at least two-thirds of months positive, and positive
  without the single best trade. Body/range and gap are not filters.

Result on 257 opportunities (247 fills; the 10 skipped averaged −8.6%
counterfactual):

| Stop | Mean net @0.5% | Lower 90% | Without best | Months + | Mean net @1% |
| --- | ---: | ---: | ---: | ---: | ---: |
| S0 | +0.01% | −1.19% | −0.21% | 5/9 | −0.98% |
| S1 | +0.16% | −1.16% | −0.07% | 3/9 | −0.84% |
| S2 | +0.22% | −1.17% | −0.00% | 5/9 | −0.78% |
| S3 | +0.24% | −1.12% | +0.02% | 5/9 | −0.76% |

The wick exit lowered every stop's mean by 0.3–0.65 points, cutting a +47%
winner. No variant passes; nothing is committed for July–September, and the
result for this candidate is "no edge found".

Hold durations, tested once with S0 and S3 under the same criteria:

- 5 and 10 minutes fail: means −0.84% to +0.09%, lower bounds −1.10% to
  −1.68%, 2–5 of 9 months positive.
- Longer holds lose at every horizon: S0 falls from +0.01% at 15 minutes to
  −0.83%, −1.58%, −3.28% and −4.69% at 30, 60, 120 minutes and the close.
- Trades in profit at 15 minutes average +11.1% then, +8.4% at 60 minutes and
  +1.5% at the close; the move fades after about 15 minutes.
- Closed: no further exit or stop variants for this candidate.

First-study conclusions:

1. For this entry, returns peak about 10–30 minutes after entry and then fade.
   No fixed hold from 5 minutes to the close produces a net edge; 15 minutes
   stays the reference because it was fixed in advance, not because it is
   proven best.
2. The entry's gross drift, about +1%, roughly equals the round-trip cost. No
   tested exit (time, fixed, trailing or breakeven stop, pullback wick)
   creates a net edge; any edge must come from the entry.
3. The fade is observed but not tradable here: the cash account cannot short.

## Second study

Entry hypotheses H1 (pullback and reclaim) and H2 (cheaper to trade) are
pre-registered in `HYPOTHESES` with their cohort, exits, costs and pass rules.
They are scored once on corrected replays (`replay-v2-YYYY-MM.csv.gz`) of
October 2025–September 2026 and confirmed only on forward data.

Result, scored once on October 22, 2026 (`hypotheses-2025-10_2026-09.json`),
737 cohort opportunities. Both fail every pass check; neither is revised on
this data.

| | Fills | Deciding cost | Mean net | Lower 90% | Without best | Months + | Mean net @0.5% |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| H1 | 127 | 0.5% one-way | −1.00% | −1.74% | −1.21% | 3/12 | −1.00% |
| H2 | 379 | measured spread | −0.42% | −1.18% | −0.56% | 6/12 | −0.90% |

- H1 trades 17% of opportunities (314 failed reclaims, 220 without a
  pullback); 63 targets against 57 stops, gross about 0%.
- H2's measured spreads cost about half the assumed 1% round trip (326 of
  379 fills quoted), but its gross drift is about +0.1%: cheaper names do
  not carry the gap ≥ 40% drift.
- No second-study candidate goes to forward confirmation.
