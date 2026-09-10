# Nomisma

Nomisma is Heuresis's first project: a local research workspace focused on **intraday penny-stock momentum**. Monitor up to 20 US exchange-listed symbols, inspect prices and volume, and receive explainable Buy / Strong buy setup alerts. The daily screener, watchlist, presets, scan history, and CSV workflow remain available separately.

## Start

For **Windows 11 Pro (Intel/AMD 64-bit)**, use the Windows installer or portable ZIP. The build includes Python and .NET, stores research data in your Windows profile, and can be built and published by GitHub Actions. See [Windows downloads, installation, and GitHub setup](desktop/WINDOWS.md).

For the native macOS app, open **Nomisma** from `~/Applications`. It has its own window, app icon, menus, file dialogs, printing, and optional macOS notifications. Python and the local backend are included. The installed build reuses this workspace's research data and credentials. See [desktop setup and build instructions](desktop/README.md).

On macOS, double-click **Launch Nomisma.command**. It starts this workspace's local server, waits for its health check, and opens the browser. Running the launcher again reuses the same server. A different application or workspace on the requested port is reported rather than replaced. The server continues after the launcher closes; market monitoring still requires **Start monitor**.

The same launcher is available from the terminal:

```sh
python3 launch.py
python3 launch.py --port 8766 --data-dir /your/chosen/path
```

Use `--no-browser` to start the server without opening a tab. Startup errors are recorded in the chosen data directory's `nomisma.log`. The commands below keep the server attached to the terminal, where Ctrl+C stops it.

From the Nomisma project directory:

```sh
python3 run.py
```

Open **http://127.0.0.1:8765**. Python 3.9+ is required; there are no runtime dependencies, build steps, or external frontend assets. Use `--port 8766` if the default port is occupied. The web server binds only to your computer's loopback interface.

The app opens on **Live monitor**. Monitoring starts only when you click **Start**; opening the page or restarting the app does not automatically open a market stream.

To try it without credentials, leave the source on **Synthetic demo**, then click **Start**. The `DEMO`, `MOMO`, and `GAP` symbols use invented prices, volume, and float on May 14, 2025. One simulated minute advances every three seconds, demonstrating Watch, Buy, and Strong buy setups. This is a historical simulation, never current market data. Synthetic alerts stay in the saved inbox; they do not trigger desktop notifications or sounds. Stop the monitor before changing its symbols, source, or alert settings.

## Connect real-time market data

Create `.env` using [.env.example](.env.example) as a template, and fill in credentials from your own Alpaca account:

```dotenv
ALPACA_API_KEY=your_key_here
ALPACA_SECRET_KEY=your_secret_here
ALPACA_FEED=iex
ALPACA_PAPER=true
# Optional: dated float-share data from Financial Modeling Prep
FMP_API_KEY=
```

Restart Nomisma, open the monitor's **Configure** dialog, select **Alpaca**, replace the synthetic tickers with the real symbols you want to follow, save, then click **Start**. You can also populate the list from your watchlist or the top 20 results of a daily scan. Live monitoring supports at most 20 symbols at once; it is not a whole-market streaming scanner. OTC coverage is not provided by the live IEX/SIP monitor.

Environment variables take precedence over `.env`. Use `ALPACA_PAPER=false` for credentials belonging to a live account; this chooses the account host for calendar and metadata requests. Credentials remain on the server and `.env` is ignored by Git. Nomisma reads market data and subscribes to the price stream; it contains no trading or order-execution endpoints.

The monitor loads the exchange calendar, prior daily bars, current quotes, and completed regular-session minute history, then authenticates and subscribes to Alpaca's real-time WebSocket stream. It receives trades, quotes, minute bars, revised bars, and daily aggregate updates. **Live** appears only after authentication and subscription acknowledgments. A failure remains visible and triggers reconnection with refreshed history; it never silently switches to synthetic or delayed data. Minute history is also reconciled while connected to repair gaps around connection boundaries. The browser receives local server-sent events (SSE), with updates throttled to roughly one per second; if that browser connection fails, it can poll every two seconds. The upstream price source remains the Alpaca stream.

Alpaca's `iex` feed covers one exchange. Its volume is not consolidated US-market volume, and sparse IEX minute history can leave session totals or alerts unavailable. `sip` provides consolidated coverage when your account has the necessary **real-time data entitlement**; Nomisma does not substitute delayed SIP. Choose liquidity thresholds with the selected feed's coverage in mind. [Alpaca data feeds](https://docs.alpaca.markets/us/docs/historical-stock-data-1), [real-time stock data](https://docs.alpaca.markets/us/docs/real-time-stock-pricing-data)

Automated provider tests use simulated responses; they have not verified your actual Alpaca credentials or subscription entitlement. “Configured” means credentials are present. Confirm account connectivity by starting an Alpaca monitor and checking both **Live** status and each stock's price/quote timestamps.

## Intraday workflow and reports

The default radar keeps the symbol, price/change, setup score, minute RVOL, spread, and eligibility together. Optional volume columns expose the detailed history metrics. Eligibility explains the main blocking condition; confirmation progress counts completed eligible minute bars independently of the technical score. A score above the Buy threshold does not override missing data, a wide spread, or any other guard.

The stock report overlays session VWAP and EMA9/EMA20 on completed minute prices, with minute volume and saved-alert markers. Gaps and unavailable indicators stay unavailable. The chart uses the same completed-bar calculations as the score.

**Test connection** runs a read-only diagnostic and reports its results separately from monitor control. It checks the configured source, provider access, timestamps, and history coverage. An already-running market stream supplies subscription evidence; a stopped monitor can be tested with a temporary bounded connection. A diagnostic does not save alerts or start an ongoing monitor.

**Find candidates** searches a selected universe using current-session snapshots, price, day change, and feed-day volume. Review the source, feed coverage, market phase, refresh time, and each result's freshness before selecting up to 20 symbols. Applying a selection requires a stopped monitor and saves its configuration; it does not start monitoring. Discovery is a snapshot search, not a continuous whole-market stream. Synthetic discovery results remain explicitly synthetic. Real-source failures are never replaced with demo data.

When the provider accepts optional trading-status and limit-price-band subscriptions, current-session events appear in the report. Confirmed halted or paused states suppress setup alerts. Missing status coverage means **unavailable**, not an assurance that trading is unrestricted.

The monitor's editable defaults are a $0.50–$5 price range, at least 100,000 shares of completed regular-session volume, latest-minute relative volume of at least 1.5×, and a bid/ask spread no wider than 2%. Buy begins at 65/100 and Strong buy at 85/100, with two consecutive completed minute bars required before saving an alert and a 300-second repeat cooldown. These are research defaults, not a backtested strategy.

Open a stock to see its minute chart, score breakdown, freshness, reasons an alert is blocked, and the volume chart/table for the prior 30 trading sessions. **Print report** prints that stock's report, including its history and data provenance; the monitor's CSV export includes current metrics and timestamps.

| Display | Meaning |
| --- | --- |
| Feed-day volume | The provider's daily aggregate, including available extended-hours activity. Its timestamp records when Nomisma received the aggregate, not the daily bar's start or the time of its latest constituent trade. |
| Session volume | Sum of completed regular-session minute volumes through the displayed minute-end timestamp. Trade sizes are not accumulated separately. |
| 30-session total / average | Volume from exactly the previous 30 exchange-calendar trading sessions, excluding today. The average is the total divided by 30. |
| Session relative volume | Completed regular-session volume divided by the prior 30-session full-day average. This is **not adjusted for time of day**. |
| 1-minute relative volume | Latest completed minute volume divided by the average volume of the preceding 20 completed regular-session minutes. This is the RVOL used by the monitor filter and score. |
| Opening gap | First regular-session minute's open versus the split-adjusted previous-session close. This differs from the latest price's day change. |
| Float / turnover | Dated publicly available float shares and completed session volume divided by that float. Source and source date remain visible. |

The volume, baseline, and gap definitions are intentionally distinct. Provider daily aggregation can contain available extended-hours activity, whereas session volume and VWAP use regular-session minute bars. Feed coverage applies to every volume field. Missing data appears as unavailable, never as zero or a passing filter. See [the methodology](METHODOLOGY.md) for exact calculations and score weights.

The monitor conservatively withholds regular-session volume, VWAP, daily relative volume, and float turnover if the exact opening minute or any minute before the latest completed bar is missing or malformed. A missing minute may mean no trades or missing data, especially on IEX; the app does not guess which. Feed-day volume can remain visible separately. Full prior-30-session history and 21 contiguous recent minutes are also required for alerts. Extended-hours prices may display, but setup alerts run only during the regular exchange session.

## Float data

Float is optional. Set `FMP_API_KEY` to enable Financial Modeling Prep's `/stable/shares-float` endpoint if your account permits it. Only a positive actual `floatShares` value with a usable source date is accepted; outstanding shares, float percentages, and market-cap estimates are not substitutes. Provider float values are cached for up to 24 hours within the running app, while retaining the provider's original date. Missing float does not prevent prices or otherwise valid setup alerts.

You can enter **Float shares** and **Source date** in a real stock's report. A saved manual entry overrides provider float and is labeled **Manual**, not provider verified. Future dates and invalid counts are rejected. Clearing the override makes float unavailable until provider data is loaded again by the periodic background refresh or a monitor restart. Synthetic demo float is always invented and does not use real manual overrides.

## Alerts and keeping the monitor running

Prices can update with each trade, but the technical score uses the latest **completed minute close**. A Buy or Strong buy label is an eligible technical setup; saving an alert additionally requires your consecutive-bar confirmation count. Both setup levels require price above session VWAP, EMA9 above EMA20, sufficient minute RVOL and session volume, an acceptable spread and price, complete baselines, a trade and quote no older than 30 seconds, and completed-minute data no older than 120 seconds. Missing/stale data, a closed regular session, disabled alerts, or a disconnected monitor suppresses alerts.

Only a new completed minute bar advances alert confirmation. Quotes, trades, duplicates, historical reloading, and late corrections do not independently generate notifications. A confirmed Strong buy upgrade may alert during the Buy cooldown. Repeating a level requires a reset to Watch and expiration of the cooldown. Alert history and deduplication state persist locally, and **Mark read** acknowledges inbox alerts.

Desktop notifications and sound are **off by default** and require an explicit click in the app or browser tab. Native apps use the operating system's notification delivery; the browser version depends on localhost notification support and site settings. Previously saved alerts are not replayed as notifications. Keep the local server and computer running for monitoring, and keep the native app running or browser tab open for desktop alerts and sound; computer sleep or web-view suspension can delay delivery. The macOS app leaves its local server running when closed or quit. The Windows app stops the local service it started when you exit; an independently started service continues running. Use **Stop monitor** to end streaming while keeping a workspace open. Restarting the server requires a new **Start**. No background system service is installed.

These Buy / Strong buy labels are explainable heuristics, not purchase instructions or calibrated predictions. Nomisma does not guarantee halt detection or analyze live news, filings, dilution, or execution costs. It never submits orders.

## Daily screener workflow

The separate **Daily screener** retains its end-of-day filters and schedule. Its initial demo contains 48 synthetic histories dated December 31, 2025. Familiar company names and tickers identify examples; their prices and rankings are invented. Daily demo scans remain synthetic regardless of when you run them.

1. Choose a data source and universe. The starter universe contains 48 maintained ticker symbols; Alpaca's broader universe loads active tradable listings from supported US exchanges. A custom universe accepts up to 1,000 symbols.
2. Choose a preset or edit price, prior average volume, relative volume, RSI, moving-average trend, MACD histogram, 20-session price return, ATR percentage, sector, and minimum-score filters.
3. Run a scan. Review each result's chart, contributing signal points, and risk observations. The filter settings used for each historical result are stored with that result.
4. Save symbols to your watchlist, save custom filter presets, and export matching results as CSV.
5. Optionally enable the daily schedule after saving the source and filters you want to use.

The default preset searches prices of $10–$1,000, prior 20-session average volume of at least 500,000 shares, relative volume of at least 1×, RSI of 45–75, price above its 50-session average, a nonnegative 20-session return, ATR at most 10% of price, and a score of at least 55. These are editable starting assumptions for daily swing-trade research, not a validated trading strategy.

## Daily market data

The daily screener uses the same Alpaca environment credentials. Select its source and universe in **Settings**, then run a scan; these settings are separate from the live monitor's list and filters.

The provider fetches approximately 450 calendar days of split-adjusted daily bars, follows every pagination token, and uses the exchange calendar to select a session that closed at least 30 minutes ago. It honors early closes. A scan during market hours therefore uses the preceding completed session. Bar returns are price returns, not dividend-inclusive total returns. Live-source failures are surfaced as errors; they never become demo results. [Historical bars](https://docs.alpaca.markets/us/reference/stockbars), [market calendar](https://docs.alpaca.markets/us/reference/legacycalendar)

The broader universe covers active tradable NASDAQ, NYSE, AMEX, and ARCA listings returned by Alpaca and can include ETFs and other exchange-traded products. It is not a claim to cover every stock worldwide. Sector metadata is maintained for the starter universe; other symbols have an **Unknown** sector and will not match named-sector filters. A broad scan can take several minutes depending on your feed and rate limit. [Assets endpoint](https://docs.alpaca.markets/us/reference/get-v2-assets-1)

## Import your own daily data

Use the dashboard's CSV import with UTF-8 data and these columns:

```csv
symbol,date,open,high,low,close,volume,name,sector,exchange
AAPL,2025-12-30,100,103,99,102,1000000,Apple,Technology,NASDAQ
AAPL,2025-12-31,102,104,101,103,1200000,Apple,Technology,NASDAQ
```

Only the first seven columns are required. Supply **at least 201 valid daily bars per stock**, plus SPY over the same dates for benchmark-relative strength. The two lines above show the format only; they do not supply sufficient history. Use consistently split-adjusted data from one feed. Duplicate symbol/date pairs, malformed OHLC ranges, nonfinite numbers, weekends, and today/future dates are rejected. Imported files cannot establish whether today's session is complete, so only prior dates are accepted. Maximum size: 20 MB.

[examples/sample.csv](examples/sample.csv) contains 205 sessions for two example stocks and SPY so you can exercise the complete import workflow. Its values are **synthetic**, and the company-name fields explicitly say so; a CSV source label by itself does not prove data is real.

CSV exchange coverage, holiday validity, and corporate-action adjustments cannot be independently verified by the app. Those limitations remain visible on imported scans. An imported CSV is a static snapshot; scheduled scans do not refresh it automatically.

## Daily operation

The built-in schedule uses **America/New_York**, including daylight-saving changes. It checks every 30 seconds, runs once per weekday after your selected time, and persists its last successful date. A restart after that time catches up for the current weekday; it does not replay missed historical days. Failed scheduled scans retry after 15 minutes. If a manual scan is in progress, the scheduler waits for it to finish.

**The application and computer must remain running.** No background system service is installed. Set the schedule after the usual close and the provider's 30-minute buffer (17:00 Eastern is the default). Holidays can produce a new scan of the last completed session, identified by its original data date. Demo and CSV sources retain their original data until replaced.

For your own task scheduler, run one scan and exit using saved settings:

```sh
python3 run.py --scan
```

Use `--scan --source alpaca` for a one-off source override. The process exits nonzero on failure and prints the saved scan ID, source, data date, and counts on success. Avoid running separate scheduled processes against the same data directory simultaneously; the built-in scan lock applies to one app process.

## Daily score

Scores combine trend (35 points), momentum (25), positive-day volume participation (20), relative strength versus SPY (15), and proximity to the prior 20-session high (5). Each stock shows its actual points and the conditions behind them. Missing or misaligned SPY data earns no relative-strength points and is explicitly flagged. See [the methodology](METHODOLOGY.md).

The daily and intraday scores are separate hand-designed rankings. Neither is the probability that a stock will rise. Nomisma does not yet include historical strategy validation, calibrated forecasts, earnings/news analysis, a general fundamentals screen, transaction costs, position sizing, or order execution. Use the output as a research shortlist.

## Storage and testing

Settings, presets, watchlists, imported data, scans, monitor configuration, manual float overrides, and setup alerts are stored in `data/nomisma.sqlite3`. Runtime data and backups are excluded from Git. Use `--data-dir /your/chosen/path` to keep a separate workspace. Scan history and the alert journal have pagination so older records remain accessible. Alert acknowledgment state is saved too.

In **Settings**, download a consistent SQLite backup while the app is running. To restore, stop monitoring and wait for any scan, diagnostic, or discovery job to finish, choose the backup file, and click **Restore**. The app validates the file before changing data and saves the current workspace under `data/backups/before-restore-….sqlite3`. Only validated rows are copied into the app's own database schema. Restore replaces local research data and settings; the restored monitor remains stopped. Credentials are held separately in `.env` and are never included in these database backups. Uploaded backups are limited to 128 MB. Stop the app first if copying the database manually instead.

### Alert evidence and observed outcomes

New alerts preserve their configuration, data quality, indicator values, session metadata, and minute chart as they appeared at the setup. Open a saved alert to inspect that evidence even if its symbol is no longer monitored. Alerts created before this feature remain available, with missing original evidence explicitly identified.

The journal measures **observed price changes**, not fills, trades, profits, or a backtest. Its reference is the completed signal minute's close. For each 5-, 15-, and 30-minute window after that minute ends, close change is `(last window close / reference close − 1) × 100`; adverse movement is `min(0, (lowest window low / reference close − 1) × 100)`. A window must consist entirely of completed contiguous minutes from the same symbol, source, feed, and session. Incomplete windows show pending or unavailable, never invented returns. Windows beyond the session close are unavailable. Current-session bar corrections can revise observations without altering the original alert evidence.

Keep the relevant symbol monitored to collect its future window. Loading matching session history can repair gaps. Previously observed results remain saved when the monitor changes sessions or symbols. Fees, slippage, spread, position sizing, and execution feasibility are not modeled.

From the project directory:

```sh
python3 -B -m unittest discover -s tests -v
```

The suite exercises independently checked indicators, intraday volume and calendar boundaries, freshness and missing-data guards, alert confirmation/deduplication, WebSocket framing/authentication, provider pagination, daily filters, CSV validation, persistence, scheduling, and HTTP input/origin protections. Provider tests use mocked responses, so they do not require credentials or verify your account's actual entitlement. The server is designed for local personal use; deploying it publicly would require a production server and authentication.

For a browser workflow check with an installed Chrome/Chromium, run `python3 -B tools/browser_check.py` from this project directory. It uses an isolated temporary database and browser profile, exercises real dashboard controls, and saves desktop/mobile screenshots under the root `artifacts/nomisma/` directory. Use `--chrome /path/to/chrome` on systems where the browser is not discovered automatically.
