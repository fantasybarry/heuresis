# Monitoring and screening methodology

Nomisma focuses on intraday penny-stock momentum while retaining its separate daily screener. Its liquidity/volatility ranking, intraday technical setup score, and daily screener score each use a 0–100 scale for a different comparison. They are not return forecasts, success probabilities, or backtested strategies. The point allocations are application design choices.

## Intraday session and price timing

Live monitoring follows at most 50 requested symbols on Alpaca's IEX or entitled real-time SIP feed, subject to the account's subscription limit. It loads REST history and snapshots, then subscribes to trades, quotes, minute bars, revised minute bars, and daily aggregates over a real WebSocket. The browser receives local SSE updates at approximately one-second intervals, with two-second polling as a fallback; browser refresh intervals do not change the upstream feed.

The exchange calendar provides the current or most recent trading session, regular open/close, and exactly the prior 30 trading dates used by the technical alert baseline. Longer daily history supports the separate liquidity/volatility metrics. The calendar honors holidays and shortened sessions. Minute timestamps identify the **start** of a bar. A bar becomes usable only after its start plus one minute is no later than the evaluation clock or session close. Bars outside regular hours, from another session, or from the future are excluded from regular-session technical calculations. Repeated timestamps replace observations rather than adding their volumes, and ordering is normalized. Prices and volume are not synthesized to fill missing real-market bars.

The displayed price is the latest valid trade with its own timestamp. If unavailable, the last completed minute close can be displayed, but that fallback does not satisfy the fresh-trade alert gate. The technical score always uses completed minute closes: an individual trade can change the displayed price and day change without changing the score. Quotes have an independent timestamp and require positive bid and ask prices with ask at least bid. Spread is `100 × (ask − bid) / ((ask + bid) / 2)`.

Outside regular hours, prices or quotes may continue to display; alerts remain disabled. “Connected” does not imply that every symbol has fresh trades or complete bars. Live-source failures remain errors/reconnection states and never become demo observations. The synthetic demo has a separate historical clock: May 14, 2025, advancing one minute every three wall-clock seconds.

## Intraday volume, gap, and float

| Metric | Exact calculation and coverage |
| --- | --- |
| Total day volume (`day_volume`) | Provider `dailyBar.v` for the displayed New York session date, including eligible premarket and extended-hours trades. When that aggregate is unavailable, completed minute volume from 04:00 New York onward may be shown with an explicit fallback basis; it is never added to an existing daily aggregate. |
| Feed-day receipt time (`day_volume_at`) | Server receipt time of a daily-stream update, or the snapshot response receipt time. It is not the bar's start, a trade timestamp, or proof that every constituent trade is current. |
| Regular-session volume (`session_volume`) | Sum of all valid completed regular-session minute volumes from the exact opening minute through the latest completed minute. `volume_at` is that latest minute's end. Raw trade sizes are never summed into this measure. |
| Prior 30-session total (`volume_30d_total`) | Sum of daily volumes on exactly the previous 30 exchange-calendar trading dates, excluding the displayed session. Daily data is split adjusted and retains the provider's daily coverage, which can differ from regular-hours-only volume. |
| Prior 30-session mean (`avg_volume_30d`) | The prior 30-session total divided by 30. A missing recent daily session cannot be replaced by an older observation. |
| Session RVOL (`relative_volume`) | `session_volume / avg_volume_30d`. The denominator represents complete daily sessions; this is **not time-of-day adjusted**. |
| Minute RVOL (`minute_relative_volume`) | Latest completed minute volume divided by the arithmetic mean of the preceding 20 completed regular-session minute volumes. All 21 minutes must be contiguous; the baseline must be positive. |
| Session VWAP | `sum(minute.vwap × minute.volume) / sum(minute.volume)` across completed regular-session minutes. Actual provider minute VWAP is required for each positive-volume minute; typical OHLC price is never substituted. |
| Opening gap (`gap_pct`) | `100 × (exact regular-opening minute.open / split-adjusted previous-session.close − 1)`. The calendar's immediately preceding session must match the reference bar. |
| Day change (`change_pct`) | `100 × (latest displayed price / the same split-adjusted previous-session.close − 1)`. This changes intraday while the opening gap stays fixed. |
| Float turnover (`float_turnover`) | `session_volume / float_shares`, expressed as a ratio. Source and source date remain visible beside the float count. |

Total day volume continues through the opening bell; the regular-session counter starts at the regular open. The two are different measures. Alpaca's daily-bar rules include extended-hours trade volume, while those trades need not update daily OHLC. Its daily stream emits aggregate updates after the market opens. A daily bar's timestamp identifies its New York calendar day, so freshness uses receipt time separately. [Alpaca bar aggregation rules](https://docs.alpaca.markets/us/docs/market-data-faq), [Alpaca daily-bar stream](https://docs.alpaca.markets/us/docs/real-time-stock-pricing-data)

The fallback sums only completed, available extended-hours minute bars from 04:00 through 20:00 New York. It can omit the current incomplete minute, missing bars, and trades that do not produce a minute bar under the provider's eligibility rules. It is labeled partial and can differ from the later daily aggregate; missing observations are not invented as zero. When a current daily aggregate arrives, it replaces the fallback. Total day volume always retains the selected feed's coverage.

A newly received response does not make old fallback minutes current. Fallback freshness requires both its receipt time and the latest included completed-minute end to be no more than 120 seconds old. Discovery exposes that actual minute end as `volume_at` and the separate receipt as `volume_received_at`; the monitor's `volume_at` still refers to its regular-session technical minute. Discovery checks fallback freshness before filtering and again after historical enrichment. A stale fallback cannot pass a positive minimum-volume filter. With a zero minimum, the candidate and partial total remain visible, but that total is unavailable for ranking, day RVOL is null, and both inputs earn zero points. Discovery's provider daily aggregates keep their existing 300-second receipt limit; the live monitor requires receipt within 120 seconds.

The regular open is normally 09:30 Eastern; the exchange calendar is authoritative. The provider's daily-bar open is never used for the gap because daily aggregation may include extended hours. If raw `prevDailyBar.c` differs from the split-adjusted previous close by more than 20%, Nomisma warns of a possible corporate action. The gap and day-change reference remains split adjusted; this warning is not a verified split announcement.

IEX covers one exchange, so its volumes, historical baselines, and prices do not represent consolidated US-market activity. SIP requires real-time account entitlement. Neither feed adds OTC coverage to this monitor. Mixing feed coverage when interpreting thresholds can make comparisons misleading.

Float is accepted only as a positive whole count of actual publicly available float shares, at most 10 trillion, with a valid source date no later than the evaluation date. Sources are **FMP**, **Manual**, and **Synthetic**; synthetic float is never used for real rows, or vice versa. The optional FMP `/stable/shares-float` integration uses only `floatShares`, never outstanding shares, percentages, or inferred shares. Manual entries override provider data and are explicitly not provider verified. Provider values may be cached for 24 hours, but this does not refresh their source dates. An old source date remains visible. Missing or invalid float produces unavailable float and turnover; it is not itself an alert-blocking filter.

## Liquidity and volatility metrics

These metrics appear in candidate results and the momentum radar. Historical inputs exclude the active session, require usable OHLCV values, and report the actual history date, expected preceding exchange-session date, and available observation count. Conflicting duplicate daily bars are excluded. Average-volume windows require the matching returned SPY session dates, and ATR requires continuity over its available history; insufficient reference history leaves these metrics unavailable. These checks cannot detect a trading date omitted by the provider for both the stock and SPY. Unavailable metrics stay visible as a dash with an explanation.

| Metric | Definition |
| --- | --- |
| Average volume (3M) | Arithmetic mean of volume across 63 prior trading sessions. Three months means this fixed session count, not three calendar months. |
| Average daily volume (20D) | Arithmetic mean of volume across 20 prior trading sessions. |
| Day RVOL | Current total day volume divided by the prior 20-session average daily volume. The denominator must be positive. This compares an accumulating day with completed daily sessions and is **not adjusted for time of day**. It differs from the 30-session regular-session RVOL and 1-minute RVOL used elsewhere. |
| Bid–ask spread | Dollars: `ask − bid`. Percent: `100 × (ask − bid) / ((ask + bid) / 2)`. A usable quote has positive finite bid and ask, ask at least bid, and a nonfuture timestamp no more than 30 seconds old. A valid zero spread remains zero. |
| Beta versus SPY | Slope `cov(stock return, SPY return) / var(SPY return)` using at most 252 aligned daily simple price returns, with at least 60 observations and positive SPY return variance. Stock and benchmark returns must share the same start and end dates. The observation count is shown; a shorter history is not presented as a full year. |
| ATR (14) | For each completed daily bar after the first, true range is `max(high − low, abs(high − previous close), abs(low − previous close))`. Seed with the arithmetic mean of 14 true ranges, then apply Wilder smoothing: `(13 × previous ATR + new true range) / 14`. At least 15 prior daily bars are required. |
| ATR percentage | `100 × daily ATR(14) / the last prior adjusted close`. This permits comparison across different stock prices; the dollar ATR remains visible. |

Candidate discovery refreshes stale, missing, or invalid quotes after historical enrichment, within the existing pool of at most 500 selected symbols and on the same market feed. It requests at most 50 symbols per batch, with two requests in parallel. A new response must still contain a valid same-session provider quote timestamp no more than 30 seconds old, checked again before ranking; receipt time is not quote time. Failures leave the spread unavailable with no spread points. This step changes no trade or volume timestamps and does not broaden the selected pool.

The historical feed uses split-adjusted price and volume. Beta therefore measures price-return sensitivity using that chosen feed, rather than a provider's published total-return or monthly beta. Cash dividends, spin-offs, sampling frequency, the benchmark, and available history can make it differ from other services. A higher positive beta indicates more historical exposure to SPY's moves, not a higher probability of a gain. ATR measures range without predicting direction. [Alpaca adjustment options](https://docs.alpaca.markets/us/reference/stockbars), [Fidelity on beta](https://www.fidelity.com/learning-center/investment-products/etf/smart-beta), [Fidelity on ATR](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/atr)

## Liquidity/volatility ranking

The default candidate and radar sort ranks observed activity and volatility across the rows in that comparison. It does not replace the technical setup score or its alert guards. Each component receives points according to its percentile among available values in that comparison:

| Component | Direction earning more points | Maximum points |
| --- | --- | ---: |
| Total day volume | Higher | 15 |
| Average volume (3M) | Higher | 10 |
| Average daily volume (20D) | Higher | 10 |
| Day RVOL | Higher | 20 |
| Spread percentage | Lower | 15 |
| Positive beta versus SPY | Higher | 10 |
| ATR percentage | Higher | 20 |
| **Total** | | **100** |

Percentiles use zero-based ranks divided by `available_count − 1`; ties receive their average rank. Spread uses the inverse percentile. A sole available observation receives the component's full points; tied equal values with more than one observation receive half. Missing metrics and stale volume or spread inputs earn zero without redistributing their weight or excluding the entire stock. Zero and negative beta remain measured values but earn no beta points. Each row exposes component values, weights, percentiles, earned points, and metric availability. Overall ties use ticker order.

Discovery first applies the selected search filters, then enriches at most the 500 qualifying symbols with the highest total day volume. It ranks that enriched comparison group before applying the requested result limit. Coverage identifies the examined and unexamined pool; this is not a ranking of every listing by every metric. The radar ranks its own configured rows. Scores can change when the comparison group changes even if a stock's raw values do not. Sorting a raw metric displays high-to-low numbers with unavailable values last; a high raw spread is still a wider spread, even though the composite rewards narrower spreads.

High volume, beta, and ATR favor active or volatile stocks by design. The three volume inputs overlap, and a narrow displayed spread does not establish available size or an executable fill. These weights express a research preference, not estimated returns or independent confirmations.

## Missing history and alert eligibility

Regular-session volume and session VWAP are calculated from the regular-session minute bars received, starting with the exact opening minute. A missing later minute has no trades, typically a trading halt, so it does not change either total; it is reported as a data note. If the opening minute is missing or a bar is malformed, session volume, VWAP, session RVOL and float turnover are unavailable and alerts are blocked. Provider feed-day volume may still display with its separate receipt timestamp. Periodic history reconciliation can repair missing delivery; it does not invent zero-volume bars.

These requirements apply to both Buy and Strong buy setups:

- The monitor is running and connected to its identified real-time feed, or is explicitly simulating synthetic data, and setup alerts are enabled.
- The evaluation clock is within the regular exchange session: open inclusive, close exclusive.
- A valid trade and a valid two-sided quote are each no more than 30 seconds old; future timestamps never pass.
- The latest completed minute's end is no more than 120 seconds old.
- The exchange calendar of prior sessions is valid and the adjusted close of the immediately preceding session exists. Recent listings with fewer than 30 prior sessions can alert; their 30-session volume baseline is shown as unavailable.
- Minute history starts at the regular open (later halt gaps are allowed) and has at least 21 contiguous recent completed minutes.
- Regular-session volume (premarket excluded), latest displayed price, and completed minute close meet configured limits. Minute RVOL and spread are shown but do not gate alerts.
- The completed minute close is above session VWAP, and EMA9 is above EMA20.

Missing numbers are null/unavailable, not zero or passing conditions. An ineligible row is Watch and lists its blockers even when some technical conditions earn points. A row can pass data gates but remain Watch because its score is below Buy. Halt and news detection are not guaranteed; fresh data alone does not establish executable liquidity.

## Intraday score and indicators

EMA9 and EMA20 use completed minute closes. Each EMA starts with its initial period's arithmetic mean, then applies `EMA += 2/(period+1) × (close − EMA)`. RSI14 uses Wilder's smoothing of minute-close changes, with the same flat/all-gain/all-loss conventions described in the daily section below. These indicators are session-local: previous-day minute bars are not carried into their seeds.

| Condition | Points when true |
| --- | ---: |
| Completed minute close is above regular-session VWAP | 20 |
| EMA9 is above EMA20 | 20 |
| EMA9 rose from the preceding completed minute | 10 |
| RSI14 is between 50 and 75 inclusive | 15 |
| Minute RVOL is at least 1.5× | 15 |
| Completed minute close exceeds every high of the preceding five completed minutes | 10 |
| Completed minute close is above the split-adjusted previous-session close | 10 |
| **Maximum** | **100** |

Each condition earns its full allocation or zero. Comparisons use unrounded values. The detail report exposes earned points, maximum points, and descriptions. A strong trade price does not substitute for the completed close in breakout, VWAP, RSI, or positive-session scoring.

Default eligibility limits are $0.50–$5 and at least 100,000 regular-session shares. With every gate satisfied, scores of at least 65 yield **Buy setup**, and at least 85 yield **Strong buy setup**. Thresholds and liquidity limits are editable; Buy must remain below Strong buy. These defaults are not optimized estimates of profitability. Formula definitions are in [monitor_metrics.py](nomisma/monitor_metrics.py).

For compatibility, the saved API setting remains named `min_session_volume`; it now applies to total day volume, including available premarket activity. Existing numeric settings are retained, and the UI labels the basis explicitly. Complete regular-session minute history is still required for session VWAP and technical alerts; using total volume for this threshold does not bypass those guards.

## Alert confirmation, repeats, and delivery

The row label describes the current completed-bar setup; the saved inbox additionally requires consecutive confirmation. The default is two consecutive completed minute bars at the applicable level, configurable from one through five. Strong buy bars also count toward Buy confirmation: Buy followed by Strong buy confirms Buy, and another Strong buy confirms the upgrade. A missed minute or ineligible bar breaks the streak. Live confirmation advances on newly completed ordinary minute-bar events, not on every quote/trade, REST reload, late revised bar, or duplicate timestamp.

The default cooldown is 300 seconds of market time, configurable from 30 to 3,600. The tracker persists per source, symbol, and session. A confirmed Strong buy upgrade may alert during the Buy cooldown. Repeating a level requires a reset to Watch and expiry of the cooldown; continuous eligibility does not notify every minute. Stopping prevents later callbacks from that monitor generation from adding alerts. Reconnecting pauses alerts until the stream is live again. See [monitor.py](nomisma/monitor.py).

Inbox alerts and acknowledgment states are stored locally; the UI displays the latest 100 while older records remain in the database. Desktop notifications and sound require explicit browser-tab opt-in and apply only to newly received Alpaca alerts. They do not replay saved/historical alerts and are disabled for synthetic alerts. The server process and computer must remain running for monitoring, and the browser tab must remain open for notification/audio delivery. Browser suspension or permissions can delay or prevent delivery. The application performs no order submission, portfolio management, email, or messaging-service actions.

## Daily screener: indicators and timing

Every stock requires at least 201 ordered, unique daily OHLCV observations. The live provider uses only completed sessions and split-adjusted prices/volume. Invalid histories, absent volume baselines, and symbols whose latest bar predates the scan's latest valid data date are excluded. Overall data older than five calendar days is flagged. A reported data date reflects actual bars, not the scan's execution time.

SMA20/50/200 are arithmetic means of the most recent 20/50/200 closes. EMA12/26 use an initial arithmetic mean, followed by `EMA += 2/(period+1) × (close − EMA)`. MACD is EMA12 minus EMA26; its signal is the 9-period EMA of MACD. The **positive MACD** filter requires a positive histogram (MACD above its signal), which can occur even when both lines remain below zero. [Fidelity EMA](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/ema), [Fidelity MACD](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/macd)

RSI14 seeds average gains/losses from the first 14 close changes and uses Wilder's smoothing thereafter. RSI is 100 when gains exist without losses, 0 when losses exist without gains, and 50 for a completely flat history. ATR14 averages true ranges—each the maximum of high−low, |high−previous close|, and |low−previous close|—using Wilder's smoothing. ATR percentage is `100 × ATR / latest close`. Initial seeds and available history can cause small differences from other charting packages. [Fidelity RSI](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/RSI), [Fidelity ATR](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/atr)

Average volume excludes the latest session and averages the previous 20. Relative volume divides latest volume by that baseline. A 20-session return compares latest close with the close 20 observations earlier. Relative strength subtracts SPY's return over exactly the same 21 session dates; it is a percentage-point difference, not an RSI measure. High proximity compares latest close with the maximum **high** of the previous 20 observations, excluding the latest session.

## Daily screener: score composition

| Component | Maximum | Evidence considered |
| --- | ---: | --- |
| Trend | 35 | Price above SMA50 and SMA200, SMA50 above SMA200, and rising SMA50 |
| Momentum | 25 | RSI range, MACD histogram and zero-line position, positive 20-session return |
| Volume participation | 20 | Relative volume when the latest close rises versus the previous session |
| SPY relative strength | 15 | Positive excess price return over the same 20-session interval |
| Prior-high proximity | 5 | Latest close near or above the previous 20-session high |

The exact points and thresholds for each stock are returned in its `signals` array and displayed in the detail view. Scores are the sum of those awarded points, rounded to two decimals. Ties sort by ticker. Missing benchmark data earns 0/15, which can reduce comparability with benchmark-complete scans. Formula definitions live in [engine.py](nomisma/engine.py); the app's point allocations are original design choices, not weights endorsed by the indicator reference sources.

Filters run on unrounded indicator values, apart from the deliberately rounded score. A stock may fail multiple filters, so rejection counts are nonexclusive and need not sum to the universe count. `eligible_count` means stocks with valid usable histories before user filters; `matched_count` is the final shortlist size. A watchlist stores symbols, not a portfolio or a guarantee that those symbols pass future screens.

## Interpretation limits

The built-in **research trade planner** is a separate deterministic calculation applied after an alert. It uses minute ATR for conditional entry/stop/target levels and explicit account, cost and liquidity assumptions for hypothetical position size. A holding limit is a policy deadline, not a predicted price peak. The default parameters are unvalidated; no historical fitting, trading performance or order execution is implied. Its lower-entry, one-share-partial reward/risk gate and full derivation are in [TRADE_PLANNER.md](TRADE_PLANNER.md). Existing observed-outcome windows remain unchanged and are not used as simulated fills.

Strong trend, momentum, and volume can reverse. Indicators overlap and are not independent confirmations. Current listing universes omit delisted stocks, and adjusted data may be revised, so future strategy testing must explicitly address survivorship bias and point-in-time data. A credible probability model would also require a defined holding period/target, out-of-sample testing, transaction costs, and ongoing calibration. Daily histories alone do not account for earnings, news, liquidity at execution, or personal suitability.


## Preserved alert evidence and observed outcomes

New monitor alerts freeze the complete original row, its completed minute chart, filter configuration, confirmation state, and session metadata. The alert schema version is recorded. Later data changes do not rewrite this evidence; legacy alerts without an original snapshot remain explicitly unavailable.

The reference for journal outcomes is the **completed signal minute's close**, not the latest displayed trade or an assumed fill. If the signal minute starts at 10:17 and ends at 10:18, its 5-minute observation covers exactly 10:18–10:23, using all five completed bars. The 15- and 30-minute windows follow the same convention.

Close change (%) = 100 × (last completed window close / reference close − 1).

Adverse excursion (%) = min(0, 100 × (minimum low across the complete window / reference close − 1)).

Observations require exact symbol, source, feed, and session identity, positive prices, and contiguous completed future minutes. Future-dated bars are excluded. Missing minutes make a due observation unavailable until repaired; a window extending beyond the exchange close is unavailable. Historical observations remain saved after changing the monitor's session or symbols. Corrections can revise observed outcomes while leaving the original alert intact. No execution, spread, commissions, slippage, or portfolio returns are simulated.

Current-session trading-status messages, when subscribed and received, distinguish halted/paused states from full trading resumption. Missing or unknown status is labeled unavailable and never interpreted as proof of uninterrupted trading. Explicit halts suppress alerts. Limit-price bands retain their provider timestamp and availability independently of setup scoring.

### Stocks-only instrument eligibility

Live candidate discovery, daily Alpaca/CSV screening, and manually selected live symbols require a match in Nasdaq Trader’s public Nasdaq-listed and other-listed symbol directories. Only non-test, non-ETF common/ordinary stocks or depositary shares with recognizable descriptions are allowed. Names indicating funds, trusts, notes, bonds, preferred shares, warrants, rights or units are excluded. Ambiguous descriptions are excluded conservatively; some legitimate company securities may therefore be omitted. Directories are cached for one hour; a failed refresh blocks screening rather than admitting unverified instruments. No brokerage credentials are sent to the directory service. SPY remains an internal market benchmark, never a candidate. Synthetic demo fixtures and historical saved results retain their original provenance.
