# All-in cash allocation and exit comparison — September 20, 2026

## Authorized change and scope

The user requests all-in simulation entries for qualifying long setups and an
investigation of exits for consistent profit. The user explicitly removed the
previous $100 account-drawdown requirement. This version removes that threshold,
its permanent latch and account-risk sizing limits. Drawdown remains measured.

Initial settled cash is $1,000. Keep the current momentum signal, confirmation,
first-feasible chronological selection, alphabetical simultaneous ties and one
entry episode per trading date. A qualifying signal is a descriptive technical
setup, not a calibrated prediction of appreciation. No actual orders are submitted.

Implement this as an additive offline adapter. Preserve existing source files,
task documents and frozen historical results. The new requirements supersede
the old drawdown constraint only in this new simulation.

## Entry allocation and actual execution

Let S be settled cash, R pending reservations, U signed unsettled proceeds and
P unpaid negative receivables. Retain the existing cash and true-calendar T+1
accounting, including the explicit 09:30 Eastern posting assumption:

```text
economic_cash = S + sum(U)
available_settled_cash = max(0, S - R - P)
Q_target = floor(available_settled_cash / (entry_cap + entry_fee_per_share))
```

Fixed fees remain zero. Cash determines the requested quantity. Remove all
account-risk, notional, minute-volume and planning bid/ask-size quantity caps.
Do not invent quote sizes or inflate risk budgets to manipulate the old planner.
Obtain its validated ATR/price geometry with no account context, then explicitly
calculate the initial conservative reward/risk gate and new cash-only sizing.
Retain positive geometry, freshness, order expiry, the existing one-cent research
rounding assumption and structural feasibility:

```text
entry_trigger <= ask <= entry_cap - entry_displacement
```

With trigger E0, stop K0, reward multiple r, entry/exit fees a/b and equal exit
displacement g, retain the existing gate exactly:

```text
RR_bound = (r * (E0 - K0) - g - a - b)
           / (E0 - max(0, K0 - g) + a + b)
require positive numerator and RR_bound >= configured min_net_rr (1.5)
```

Reject an empty interval before reservation. Entry remains the existing
ask-triggered capped IOC simulation, with explicit modeled activation latency.
The requested quantity is not a guarantee of the filled quantity:

```text
Q_fill = min(Q_target, remaining capacity of the admissible future ask quote)
entry_cash_debit = Q_fill * (ask + entry_displacement + entry_fee_per_share)
```

Retain the 25% actual quote-capacity fraction, its consumption accounting and
partial IOC behavior. This fraction governs execution, not planning size. The
first positive fill consumes the date's entry allowance; the unfilled remainder
is canceled with its reservation released. Do not top up later or spend unsettled
sale proceeds. A carried position blocks another entry while open. Report
requested/filled/canceled quantity, cash deployed and residual cash explicitly.

Any legacy risk/notional fields retained for input-schema compatibility must
be labeled ignored. Effective metadata must show account drawdown limit null,
financial-risk sizing disabled and planning-liquidity sizing disabled.

## Equity observation with no account drawdown control

Observe economic cash plus fresh conditional net bid marks, keeping explicit
unknown intervals and share-basis checks. Report the running equity peak and
observed drawdown, including observations above $100. There is no threshold,
floor, headroom, allowance, breach trigger or drawdown-based entry cancellation.

Simply setting the inherited guard flag false is insufficient: the old observer
still latches its threshold and the cash adapter checks that state. Override the
sample, context, submission-blocking and report paths. Preserve funding checks
and explicit unknown valuations. Individual trade stop/target exits remain.
Quoted equity is conditional and not a guarantee of immediate sale proceeds.

## Three fixed exit policies

Freeze ATR A0 at the entry decision. Let e be actual entry price, K0 the original
1.5-ATR stop, T the original 2R target rounded from actual entry and K0, a/b entry
and exit fees per share, g exit displacement, and delta the research price grid.
For a fresh valid bid B received after entry:

```text
G = max(0, B - g) - b - (e + a)       # net marked gain per share
H = highest valid observed bid with event timestamp >= first fill timestamp
BE = round_up(e + a + b + g, delta)  # cost-aware breakeven trigger level
```

| ID | Stop policy |
|---|---|
| fixed_15m | Keep K = K0. |
| breakeven_1atr | Permanently arm when G >= A0; then K = max(K, BE). |
| trail_1atr | Same activation; then K = max(K, BE, round_down(H - A0, delta)). |

Every policy retains T and the 15-minute deadline from first fill. The original
reward/risk gate describes initial geometry; protective exits need not achieve
that nominal reward. ATR and target never refresh from future information, and
stops never decrease. The one-ATR settings are exploratory comparisons registered
before these new runs on already-exposed data; they are not fitted estimates or
untouched validation.

## Causal event ordering

All three policies evaluate price exits at modeled quote receipt. Use only valid,
fresh, share-basis-compatible RTH quotes with event time at or after first fill:

1. Leave an already-latched exit unchanged.
2. At or after the holding deadline, request the holding-limit exit.
3. Otherwise test the existing stop, then the fixed target.
4. If neither triggers, update H, activation and the protective stop.
5. Test the updated stop against the same observed bid. If rounding places it
   at or above that bid, request an exit now, without a retrospective fill.

Each exit request adds routing delay exactly once. Fills require a strictly
later raw quote after both trigger and activation, with remaining bid capacity.
Raw quote processing handles entries and active exit fills, but must not also
schedule the inherited delayed price-trigger path. Unknown/stale observations
cannot arm, ratchet or trigger price exits; the holding timer can still request
an exit. No future capacity means unresolved exposure, not an invented close.

An exit reason persists through partial fills. Ratchets cannot cancel an exit,
reset its deadline or reopen the daily entry allowance. Stop-scenario risk can
remain a labeled diagnostic; it does not constrain allocation.

## Required checks and bounded execution

Meaningful fixtures must cover:

- $1,000 available, cap $10.02, fee .001 => 99 requested. A 200-share ask with
  25% capacity fills 50 and cancels 49, with one daily entry consumed.
- e=10.001, A0=.10, a=b=g=.001, delta=.01 => BE=10.01. Bid10.12 arms protection
  and trail becomes10.02; later high10.20 raises trail to10.10; lower bids cannot
  lower it. A delayed/gapped fill can still lose after activation.
- No prefill quote influence; receipt/routing delays applied once; deadline
  equality; same-observation crossing after rounding; partial-exit continuation;
  no $100 threshold action; later funded entry after a drawdown above $100.
- Cash, reservations, fees, settlement and equity conservation; limit-respecting
  capacity-constrained fills; deterministic repeats; preservation of prior files.

Execute exactly three policies under nominal, doubled-cost and doubled-timing
fixtures, plus one exact nominal fixed_15m repeat: **10 runs, nine comparisons**.
Change each stress separately. Double every nonzero per-share fee/displacement
for the cost fixture and all four existing timing delays for the timing fixture.
No extra parameter search or best-case-only rerun is registered.

The local archive contains nine full quote/trade development dates, September
3–16, for FTFT/SES/TE, all already exposed. Earlier minute-only data and a short
prospective fragment are not additional execution sessions. Do not manufacture
an independent holdout or treat stress variants as independent trading samples.

Report per-date and active-date results, trade concentration, cash utilization,
fees, activation/ratchet traces, final stops, exit reasons, observed drawdown,
unknown intervals, partial fills and unresolved exposure. Do not annualize or
infer stable profitability from one active symbol-date. Selected/accepted policy
and confidence intervals remain null when evidence is insufficient.

## Review and attribution

`researcher` supplied the equations, three policies and ordering contract.
`developer` owns the new adapter/CLI/tests. `infra_engineer` verifies local data
feasibility and performs registered execution/auditing; activation of the separate
`data_engineer` was blocked by the agent-thread limit. Obtain independent code
review before runs and an exact-evidence risk assessment afterward. The removed
$100 criterion must not be reintroduced as an acceptance condition.

Stop triggers and trailing levels do not guarantee execution prices. The SEC's
[stop-order bulletin](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-15)
describes these execution limitations. Model-specific assumptions here remain
explicit fixtures rather than verified broker behavior.
