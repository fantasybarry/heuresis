# Historical replay pilot

`historical-replay-v1` is an offline engineering experiment. It is a separately
versioned approximation of Nomisma's live signals, not a reconstruction of the
original alert stream. No parameter fitting or trading-readiness claim is made.

## Frozen development experiment

- Cohort: FTFT, SES, TE, on September 11, 14, 15, and 16, 2026.
- Include every declared symbol/session, including non-alerts and missing data.
- The symbols and dates came from the previous audit. They were selected after
  historical alerts were observed and are unsuitable as an independent test set.
- Default signal thresholds come from `monitor_metrics.DEFAULT_MONITOR_CONFIG`.
- Planner baseline: minute ATR14, five-bar breakout, stop multiplier 1.5, reward
  multiple 2, chase allowance 0.25 ATR, 15-minute hold, two-minute entry validity,
  five-minute pre-close buffer, minimum conservative net reward/risk 1.5.
- No thresholds will be loosened to obtain trades. Zero trades is a valid result.

The account, execution and fee settings below are **engineering fixtures**, not
the user's account, risk preferences, broker terms, or measured execution costs:

| Setting | Fixture value |
| --- | ---: |
| Initial cash/equity | $10,000 |
| Maximum modeled risk per trade | $25 |
| Daily loss allowance | $100 |
| Simultaneous modeled risk allowance | $75 |
| Maximum position notional | $1,000 |
| Gross exposure allowance | $3,000 |
| Entry and exit fee | $0.001/share each |
| Fixed fees | $0 |
| Entry, stop and target adverse displacement | $0.001/share each |
| Assumed market-data observation delay | 1 second |
| Assumed order routing delay | 1 second |
| Assumed fill-report delay | 0 seconds |

## Archived inputs and historical clock

Archive original provider responses, request parameters, acquisition times,
pagination completion, and SHA-256 hashes. Credentials must never enter the
archive. Preserve native nanosecond event timestamps and stable response order.
Original historical receipt timestamps are unknown; acquisition times must not
be substituted for them.
Exchange trade identifiers can be reused within a session. Deduplicate only
identical complete trade records and retain distinct timestamp/price/size
observations that reuse an identifier.

Inputs include the exchange calendar, at least 30 preceding daily sessions,
extended-hours minute bars, and regular-session quotes and trades. Raw minute
prices and quote/trade prices supply the execution price basis. To express
split-adjusted daily history in the session's share units, fix the raw/split
factor from the first matched regular-session minute and corroborate its OHLC
and inverse volume ratios. Later comparisons are integrity checks, not updates
to that factor. Inconsistent or missing normalization evidence blocks that
asset. This remains a retrospective corporate-action normalization proxy.

Evaluate completed regular-session minutes at minute end plus one second.
Only quotes/trades with modeled observation times at or before the decision
can enter its snapshot. Final downloaded bars are assumed available at their
end plus one second; this does not recover original versions or eliminate the
possibility of provider revisions. Maintain the existing 21-minute contiguous
history, 30-prior-session history, confirmation, reset, upgrade and cooldown
requirements. Missing minutes are not filled with invented bars.

Total-day volume is reconstructed from completed minutes starting at 04:00 New
York time. This is a declared proxy for the live provider daily aggregate,
which may include trades excluded from minute bars. Historical float and a
point-in-time all-market universe are unavailable; neither today's float nor
today's listings is substituted. The experiment is limited to its fixed cohort.

Use regular two-sided SIP quotes with known share units, valid positive prices,
nonnegative integer sizes, and an uncrossed spread. Preserve excluded quote
states on the timeline where their timestamp is valid so an invalid update
cannot leave an older quote falsely usable. Unknown conditions are ineligible.
Historical halt coverage is unknown and must remain disclosed; quote presence
does not prove a real order would have executed.

## Simulated orders and shared portfolio

Use the existing planner's formulas and conservative sizing gate through a
separate, explicitly modeled historical adapter. Preserve the live planner's
original-evidence contract. Monetary bookkeeping uses Decimal arithmetic.

Reserve the full planned quantity's cash and modeled risk when an entry is
accepted. Activate it one second after decision and use a strictly later quote
before expiry. Require ask at least the trigger and ask plus assumed entry
displacement no greater than the cap. Fill at most 25% of the available ask
display, then cancel the unfilled remainder immediately after the first positive
fill. This is an IOC-style execution approximation, not an assertion of exchange
queue priority. There is no averaging into a position.

Start the holding clock at first fill. Derive the target from that actual
simulated fill using the planner's price rounding. Bid triggers stop and target;
the first observable exit reason is latched. A quote-triggered reason cannot
latch before its modeled observation time. It activates two seconds
after its quote event (observation plus routing). A holding-deadline exit
activates one second after the deadline. Execute against later bid quotes and
retain any residual position when capacity is insufficient.

For a continuous unchanged side-price run, usable shares are
`max(0, floor(0.25 * current_displayed_size) - previously_consumed)`.
Unchanged refreshes do not replenish consumed capacity. Reset the counter on a
side-price change or new session. Collapse same-nanosecond quote updates into
one deterministic opportunity using archived response order; that ordering is
not asserted to recover exchange sequencing.

Cash, gross exposure and modeled risk are shared across symbols and sessions.
Pending or open exposure prevents a second entry in the same symbol. Canceling
unfilled shares releases their reservations; filled shares retain proportional
cap-based scenario risk until exit. Daily allowance subtracts realized loss
debits and outstanding risk. Profits do not erase loss debits. Actual simulated
losses may exceed scenario reservations after gaps or delayed execution.

Never invent a closing fill from an OHLC bar or a session boundary. Report
unresolved holdings, remaining reservations and mark freshness explicitly.
Realized P&L alone is not portfolio performance when positions remain unresolved.
If a carried position's share-basis factor changes or becomes unavailable,
freeze it as unresolved instead of inventing a split adjustment or evaluating
its old quantity against the new share basis.

## Required evidence

- Identical frozen inputs produce identical complete outputs.
- Every declared symbol/session/minute has an accounted-for decision or skip.
- No input timestamp exceeds the declared simulated information cutoff.
- Cash, fees, quantities, reservations and realized P&L reconcile.
- Competing orders cannot independently reuse the same available balance.
- Tests exercise partial fills, expiration, invalid quotes, gaps, no exit,
  overlapping opportunities, nanosecond ties and delayed exits.
- Real-data output includes an inspectable decision, order, fill and account
  ledger, with archive and source hashes and explicit exclusions.

Researcher numerical checks: for trigger $1.50, cap $1.52, stop $1.40, 5,000-share
median minute volume and 200/200 displayed shares, the fixture allows 50 shares,
reserving $6.15 risk and $76.05 cash. An 80-share ask at $1.50 fills 20 at $1.501,
debits $30.04, retains $2.46 risk and yields a $1.71 target; 30 shares cancel.
A 40-share bid permits 10 shares of exit, an unchanged refresh permits zero,
and growth to 80 shares permits 10 more.

## Later research

After engineering validation, establish a broader reproducible universe,
prespecify acceptance criteria and user risk constraints, and obtain sufficient
history for chronological selection and untouched final validation. The later
candidate family is stop multipliers `{1, 1.5, 2}`, reward multiples
`{2, 2.5, 3}`, and holding limits `{5, 15, 30}` minutes. These 27 policies are
unfitted candidates; even the larger reward multiples may fail cost-aware gates.
Prospective event/version recording is separate follow-up work, needed to test
the historical availability and execution assumptions against actual arrivals.

## Running the pilot

Run from the `nomisma` project directory. Only `download` reads the configured
Alpaca credentials. `run` verifies and consumes the local archive offline.

```sh
python3 -B tools/replay_pilot.py config --output artifacts/my-replay/config.json
python3 -B tools/replay_pilot.py download --output artifacts/my-replay/dataset --symbols FTFT,SES,TE --dates 2026-09-11,2026-09-14,2026-09-15,2026-09-16 --max-requests 1000
python3 -B tools/replay_pilot.py run --dataset artifacts/my-replay/dataset/dataset.json --config artifacts/my-replay/config.json --output artifacts/my-replay/baseline --verify-repeat
```

The configuration command preserves an existing file instead of overwriting
it. Downloads require a new or empty destination. If a bounded download stops,
use `download --resume-from <previous-archive> --output <new-archive>` with the
same symbols and dates. Reused pages must match the request sequence and their
original hashes; acquisition times are retained. Outputs include the complete
result, individual ledgers, a configuration copy, source/input hashes, and the
repeat-equality check. A source or dataset change during execution fails the run.

Provider references: [bars](https://docs.alpaca.markets/us/reference/stockbars),
[quotes](https://docs.alpaca.markets/us/reference/stockquotes-1),
[trades](https://docs.alpaca.markets/us/reference/stocktrades-1),
[late updates](https://docs.alpaca.markets/us/docs/real-time-stock-pricing-data),
[quote conditions](https://docs.alpaca.markets/us/reference/stockmetaconditions-1),
[SIP size convention](https://docs.alpaca.markets/us/changelog/marketdata-bid-and-ask-size-display-change).
