# Cash-account allocation pilot, 18 September 2026

## Purpose and scope

The user clarified that the $1,000 account is a cash account and proposed
concentrating its buying power in one eligible long position. This additive,
offline study tests that proposal with the existing fixed $100 drawdown
threshold below the running observed account-equity peak. It does not reset
the loss allowance each day, imply a guaranteed loss ceiling, authorize
orders, or alter the previous experiments. All reused dates are development
data whose outcomes have already been examined.

## Cash and settlement

Let S be settled cash, U the sum of dated unsettled net sale proceeds, and R
pending entry cash reservations, all in dollars. U is signed if exit fees
exceed gross proceeds; let P be the absolute sum of negative unsettled amounts.
Economic cash C = S + U; available entry cash = max(0, S - R - P).
Initially S = C = 1000 and U = R = P = 0.

- Accept only entries fully covered by unreserved settled cash.
- Reserve q * (entry price cap + entry fee per share) before routing.
- On an entry fill, subtract its actual purchase price plus entry fees from
  S and C. Release the entire pending reservation when the inherited IOC
  entry finishes; unfilled quantity is cancelled, never fictitiously filled.
- On each partial or complete exit, add net proceeds to U and C, and retain
  the fill identity and its settlement availability timestamp.
- When a receivable becomes available, transfer its amount from U to S.
  C, realized P&L and equity do not change during this transfer.
- Cancelling an unfilled order releases R, without changing S, U or C.
- Require C = S + U and R >= 0 at every event. Every new reservation must
  be covered by S - P. A negative net exit creates an explicit payable;
  reserve its funding immediately. If an exit creates a funding deficit,
  cancel pending entries and block new purchases. At settlement an unpaid
  fee liability may make S negative; preserve that deficit and the resulting
  loss rather than clipping it or refusing to record the exit.

Equity remains C plus the inherited conditional net liquidation value of
holdings. Reservations are not expenses; unsettled proceeds remain assets.
Never remove unsettled proceeds from equity or create a drawdown on settlement.
Keep the existing delayed quote observations, stale/invalid mark handling,
unknown intervals, permanent threshold latch and capacity-limited exits.

Use a separately validated, bounded T+1 settlement calendar. Fail closed for
missing trade dates or unavailable following settlement dates. Release funds
at 09:30 America/New_York on the settlement date as a conservative RTH-only
research assumption, not a statement about an actual broker's posting time.
Weekends and settlement holidays must not count as settlement business days.
Do not substitute the next available replay date for the true settlement date.
Pending receivables beyond the replay horizon remain unsettled in final output.

This entry restriction is conservative: cash-account brokers may permit some
purchases with unsettled proceeds if the purchased securities are held until
the funding sale settles. This intraday pilot does not rely on that behavior.

## Feasibility and causal selection

Before reserving cash require a nonempty admissible ask interval:

    entry_trigger <= ask <= entry_cap - entry_slippage

Reject a plan when entry_trigger > entry_cap - entry_slippage. Preserve its
decision and explicit rejection reason; create no cash/risk reservation or
executable order. Do not widen price caps, reduce costs or manufacture fills.
A structurally feasible order may still expire without an admissible quote.

For the single-entry variants, use the first qualifying feasible setup in
chronological decision order; break simultaneous ties alphabetically by symbol.
Allow at most one pending entry across symbols. A pending order reserves the
choice until it fills, expires or is cancelled. The first positive fill commits
the trading date to that symbol and entry episode. A partial IOC fill also
consumes the day's choice. No second entry or top-up is allowed that date,
including when some settled cash remains. Unfilled cancellation/expiration
permits a later qualifying setup; no fill means a valid no-trade day.
Any carried position blocks new entries in the single-entry variants.

These are explicit strategy assumptions, not legal requirements of a cash
account. The day's eventual winning stock or largest spike is never consulted.

## Sizing and registered comparisons

The inherited planner sizes whole shares using the minimum of cash, stop-risk,
notional and observed liquidity caps. With zero fixed fees, entry cap M, stop K,
entry/exit per-share fees fe/fx and stop displacement ds:

    risk_per_share = M - max(0, K - ds) + fe + fx
    cash_quantity = floor(max(0, S - R - P) / (M + fe))
    risk_quantity = floor(available_risk / risk_per_share)

The liquidity cap remains the minimum of 1% of the trailing 20 completed
minute-volume median and 25% of the observed bid and ask sizes. Actual fills
also retain the historical quote-capacity restrictions.

Let E be complete observed liquidation equity, H its running peak, and
A = max(0, 100 - (H - E) - position_guard_risk - pending_risk).
Position guard risk remains the greater of original remaining entry risk and
current net liquidation value minus net stop-scenario liquidation value.
Unknown equity or a latched threshold breach blocks new risk.

Register three comparisons before new historical execution:

| ID | Entries | Risk and allocation policy |
|---|---|---|
| A_cash_legacy | Existing multiple-entry policy | Settlement and feasibility repaired; retain $25 per-trade, $75 portfolio, $100 daily loss-debit and prior notional caps, all additionally bounded by A. |
| B_single_legacy | One entry episode per day | Same limits as A; isolates the daily selection restriction. |
| C_single_max | One entry episode per day | Use A for each planner risk limit; use available settled cash for notional limits. The old $25/$75 and fixed notional fixtures do not silently prevent maximum affordable allocation. |

C still sizes down when stop risk or liquidity binds, leaves a fee/whole-share
residual when cash binds, and never tightens a stop just to spend more cash.
It may deploy settled profits after settlement. Spending all cash is an upper
allocation target, not a requirement to disregard the $100 risk constraint.

Hold the existing signal and exit parameters fixed: stop 1.5 ATR, reward 2,
holding limit 15 minutes, with the same confirmation/eligibility rules.
Run A, B and C nominally, then double costs and timing delays separately for
B and C. Repeat C to verify deterministic output. No parameter search or new
winner selection is part of this study. Earlier baseline remains a descriptive
reference only; differences from it combine settlement and feasibility changes.

## Validation and reporting

Test meaningful behavior: conservation of cash/equity; no same-day proceeds
reuse; unspent settled cash reuse; cancel/partial-fill reservations; settlement
across weekends, holidays, skipped replay dates and the final horizon; causal
ties and daily locks; infeasible-order rejection without stale order IDs;
cash/risk/liquidity binding; removal of old fixture limits in C; unknown marks,
permanent breaches and delayed gap overshoot. Reject unsupported calendars,
costs and source identities explicitly.

Obtain independent implementation review before historical runs, then execute
the full existing suite and audit every new result. Reconcile each fill,
receivable, settlement and reservation; check entry policy and equity math.
Record exact source, configuration, calendar and dataset hashes, reproducibility,
unknown valuation periods, rejected opportunities, requested versus filled
quantities, cash deployment and outcome differences. Preserve original files
and artifacts; append findings to temporary/task09_17.md.

Report diagnostics without confidence intervals or accepted parameters. The
existing nine sessions, concentrated activity, historical coverage gaps,
conditional liquidity, unknown original receipts/halts and absence of an
untouched holdout remain limitations. Independent risk assessment applies to
the exact new evidence and cannot turn a stop/exit request into a hard $100
maximum-loss guarantee.

## Primary rule references

- [SEC cash-account bulletin, updated August 7, 2026](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins/updated-9)
- [Fidelity cash-account trading violations, March 24, 2026](https://www.fidelity.com/learning-center/trading-investing/trading/avoiding-cash-trading-violations)
- [SEC stop-order execution limitations](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-15)
