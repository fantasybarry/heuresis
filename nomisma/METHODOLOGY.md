# Monitoring and screening methodology

Nomisma focuses on intraday penny-stock momentum while retaining its separate daily screener. Both 0–100 scores compare observed technical conditions. Neither is a return forecast, success probability, or backtested strategy. The point allocations are application design choices.

## Intraday session and price timing

Live monitoring follows at most 20 requested symbols on Alpaca's IEX or entitled real-time SIP feed. It loads REST history and snapshots, then subscribes to trades, quotes, minute bars, revised minute bars, and daily aggregates over a real WebSocket. The browser receives local SSE updates at approximately one-second intervals, with two-second polling as a fallback; browser refresh intervals do not change the upstream feed.

The exchange calendar provides the current or most recent trading session, regular open/close, and exactly the prior 30 trading dates. It honors holidays and shortened sessions. Minute timestamps identify the **start** of a bar. A bar becomes usable only after its start plus one minute is no later than the evaluation clock or session close. Bars outside regular hours, from another session, or from the future are excluded. Repeated timestamps replace observations rather than adding their volumes, and ordering is normalized. Prices and volume are not synthesized to fill missing real-market bars.

The displayed price is the latest valid trade with its own timestamp. If unavailable, the last completed minute close can be displayed, but that fallback does not satisfy the fresh-trade alert gate. The technical score always uses completed minute closes: an individual trade can change the displayed price and day change without changing the score. Quotes have an independent timestamp and require positive bid and ask prices with ask at least bid. Spread is `100 × (ask − bid) / ((ask + bid) / 2)`.

Outside regular hours, prices or quotes may continue to display; alerts remain disabled. “Connected” does not imply that every symbol has fresh trades or complete bars. Live-source failures remain errors/reconnection states and never become demo observations. The synthetic demo has a separate historical clock: May 14, 2025, advancing one minute every three wall-clock seconds.

## Intraday volume, gap, and float

| Metric | Exact calculation and coverage |
| --- | --- |
| Feed-day volume (`day_volume`) | Raw provider `dailyBar.v`, accepted only for a valid nonfuture bar timestamp belonging to the displayed session date in America/New_York. It may include available extended-hours activity. |
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

The regular open is normally 09:30 Eastern; the exchange calendar is authoritative. The provider's daily-bar open is never used for the gap because daily aggregation may include extended hours. If raw `prevDailyBar.c` differs from the split-adjusted previous close by more than 20%, Nomisma warns of a possible corporate action. The gap and day-change reference remains split adjusted; this warning is not a verified split announcement.

IEX covers one exchange, so its volumes, historical baselines, and prices do not represent consolidated US-market activity. SIP requires real-time account entitlement. Neither feed adds OTC coverage to this monitor. Mixing feed coverage when interpreting thresholds can make comparisons misleading.

Float is accepted only as a positive whole count of actual publicly available float shares, at most 10 trillion, with a valid source date no later than the evaluation date. Sources are **FMP**, **Manual**, and **Synthetic**; synthetic float is never used for real rows, or vice versa. The optional FMP `/stable/shares-float` integration uses only `floatShares`, never outstanding shares, percentages, or inferred shares. Manual entries override provider data and are explicitly not provider verified. Provider values may be cached for 24 hours, but this does not refresh their source dates. An old source date remains visible. Missing or invalid float produces unavailable float and turnover; it is not itself an alert-blocking filter.

## Missing history and alert eligibility

Nomisma conservatively requires uninterrupted minute coverage from the exact regular open through the latest completed minute before reporting regular-session volume or session VWAP. A missing minute may mean no trades or incomplete delivery. Until coverage is complete, session volume, VWAP, session RVOL, and float turnover are unavailable and alerts are blocked. The chart still shows available bars, and provider feed-day volume may display with its separate receipt timestamp. Periodic history reconciliation can repair missing delivery; it does not invent zero-volume bars.

These requirements apply to both Buy and Strong buy setups:

- The monitor is running and connected to its identified real-time feed, or is explicitly simulating synthetic data, and setup alerts are enabled.
- The evaluation clock is within the regular exchange session: open inclusive, close exclusive.
- A valid trade and a valid two-sided quote are each no more than 30 seconds old; future timestamps never pass.
- The latest completed minute's end is no more than 120 seconds old.
- All required prior-30-session daily bars exist and their average volume is positive; the adjusted close matches the immediately preceding calendar session.
- Minute history has complete regular-session coverage and at least 21 contiguous recent completed minutes with a positive preceding-20-minute volume mean.
- Session volume, latest displayed price, completed minute close, minute RVOL, and spread meet configured limits.
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
| Minute RVOL meets the configured minimum, default 1.5× | 15 |
| Completed minute close exceeds every high of the preceding five completed minutes | 10 |
| Completed minute close is above the split-adjusted previous-session close | 10 |
| **Maximum** | **100** |

Each condition earns its full allocation or zero. Comparisons use unrounded values. The detail report exposes earned points, maximum points, and descriptions. A strong trade price does not substitute for the completed close in breakout, VWAP, RSI, or positive-session scoring.

Default eligibility limits are $0.50–$5, at least 100,000 completed regular-session shares, minute RVOL at least 1.5×, and spread at most 2%. With every gate satisfied, scores of at least 65 yield **Buy setup**, and at least 85 yield **Strong buy setup**. Thresholds and liquidity limits are editable; Buy must remain below Strong buy. These defaults are not optimized estimates of profitability. Formula definitions are in [monitor_metrics.py](nomisma/monitor_metrics.py).

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

Strong trend, momentum, and volume can reverse. Indicators overlap and are not independent confirmations. Current listing universes omit delisted stocks, and adjusted data may be revised, so future strategy testing must explicitly address survivorship bias and point-in-time data. A credible probability model would also require a defined holding period/target, out-of-sample testing, transaction costs, and ongoing calibration. Daily histories alone do not account for earnings, news, liquidity at execution, or personal suitability.
