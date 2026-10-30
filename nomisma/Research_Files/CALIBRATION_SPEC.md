# Historical replay calibration: development experiment v1

This additive workflow preserves the historical-replay-v1 engine, pilot configuration,
original four-session results, and the existing text of `temporary/task09_17.md`.
It is offline research. It does not change the application's trading parameters.

## Frozen experiment

The registration in `artifacts/calibration-20260917/registration.json` is written
before acquisition of the five additional sessions and before examining sweep results.
The cohort remains FTFT, SES and TE, chosen retrospectively for the original pilot.
All nine sessions are development data: September 3, 4, 8, 9, 10, 11, 14, 15 and 16,
2026. The newly acquired earlier dates do not create an untouched final holdout.
Download at most 200 historical requests per new date, 1,000 in total; archive every
response using the unchanged pilot importer. Retain missing/ineligible observations.

Generate exactly 27 configurations by changing only:

- `stop_atr_multiple`: 1, 1.5, 2
- `reward_multiple`: 2, 2.5, 3
- `hold_minutes`: 5, 15, 30

All other monitor, account, policy, timing and cost assumptions remain the frozen
engineering fixture. In particular, initial cash is $10,000, risk per trade $25,
daily loss allowance $100 and simultaneous portfolio risk $75. These are not the
user's stated financial constraints. Record all candidates, including no-trade and
invalid candidates, with configuration, data, source and result hashes.

## Replay and scoring

Verify parent archive integrity and publish individually hashed session files.
Load only requested development sessions. A versioned adapter carries one unchanged
engine instance across dates: cash, positions, timers, reservations, and split-basis
state persist. Do not concatenate independently reset daily accounts. Pin the original
engine version and verify semantic parity against the archived four-session baseline.

For each session, match the opening and closing ledger snapshots. Only when both
boundaries have no positions and opening cash is positive:

    net_session_pnl = closing_cash - opening_cash
    session_return = net_session_pnl / opening_cash

Include zero-trade dates. Any nonflat or missing boundary produces an unavailable
return with a reason; it is never silently omitted. A candidate's scored mean is
unavailable unless every requested date has a valid return. Rank diagnostic candidates
by arithmetic mean net session return, then stable policy ID for exact ties. Disclose
trade counts, traded dates and symbols, fees, unresolved holdings and total P&L.

Report `session_close_drawdown` only when all boundaries are flat, using initial cash
and session closing cash. `intraday_mark_to_market_drawdown` is unavailable: session
snapshots do not establish the full portfolio's maximum drawdown.

Chronological development folds are fixed in advance:

1. Train September 3–10 (five sessions); validate September 11 and 14.
2. Train September 3–14 (seven sessions); validate September 15 and 16.

For each fold, identify the training leader without validation outcomes, then report
that candidate's validation metrics. Also show every fixed candidate's fold and
neighboring-grid results. Slice the continuously replayed account; do not call a
concatenation of these accounts the P&L of a policy-switching strategy.

## Selection and sensitivity

`diagnostic_best_observed` is a post-hoc exploratory result. A no-trade policy can
lead this ranking and supplies no positive execution evidence. This experiment must
output `candidate_for_holdout = null`, `selected_config = null`, and
`calibration_status = development_only_insufficient_evidence`.

Selection is blocked by the retrospective universe, short/concentrated sample,
absence of a later untouched holdout, missing actual acceptance limits, unavailable
full drawdown and unassessed uncertainty. No unsupported confidence interval or
automatic economic approval is produced.

After the sweep, replay the fixed baseline and diagnostic leader under two separate
sensitivity fixtures: (a) double every fee/displacement cost, keeping timing fixed;
(b) double every timing delay, keeping costs fixed. These are not additional
optimization dimensions or estimates of real broker fills. If the same candidate
is both baseline and leader, avoid duplicate runs and retain both labels. Record
changes in trades and unresolved exposure as well as returns.

A future economic selection experiment needs a defensible point-in-time universe,
substantially broader chronological development evidence, user-specified loss,
drawdown, coverage, stability and precision requirements, and later sealed holdout
dates. Its selection score should use a simultaneous lower confidence bound across
all 27 policies, with paired session-block resampling that preserves dependence and
accounts for the search. Freeze one candidate before opening its holdout; evaluate
that candidate once and reject inadequate evidence instead of retuning on the holdout.
That inferential/holdout selection stage is not claimed implemented or passed here.

## Verification

Tests must cover the 27-config family, exact preservation of other parameters,
chronology, session cash arithmetic, nonflat boundaries, cross-session state,
engine-version pinning, archive tamper detection and holdout access exclusion.
For cash 10000 → 9900 → 9999, returns are -1% and +1%, mean 0%, total return -0.01%,
and session-close drawdown 1%. Cash spent on a still-open position is not a session
loss. Run the full existing suite, independent review, original-baseline parity,
actual sweep and sensitivity runs, artifact reconciliation and risk assessment.
Append actual results and remaining gaps to the preserved report.
