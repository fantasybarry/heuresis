# Nomisma live-trading handoff — October 29, 2026

## Start here

On 10/29 the user began **trading Nomisma's Buy / Strong buy alerts with real money** and logging each trade. During the session three live bugs were found and fixed; the most serious one had been **suppressing almost every alert** before 11:26 ET. Everything is running with the fixes; all **572 tests pass**.

- Workspace: `/Users/barry/heuresis`; project: `/Users/barry/heuresis/nomisma` (Python 3.9 stdlib + static JS)
- Follow `AGENTS.md` (SDL-MCP / Graphify). Run `graphify update .` from the repo root after code changes — done after every change below.
- Nothing is committed. The working tree has many earlier uncommitted changes too. **Do not commit, push or build Windows without the user's go-ahead.**
- Memory: `~/.claude/projects/-Users-barry-heuresis/memory/nomisma-alert-replay-findings.md`

## Current state (as of 11:30 ET, 10/29)

| Item | State |
|---|---|
| Nomisma server | `cd nomisma && nohup python3 -B run.py --port 8765 --data-dir /Users/barry/heuresis/nomisma/data >> data/server.log 2>&1 &` — restarted 11:26 with all fixes |
| Data pool | `python3 -u run.py --pool --port 8770` (logs `data/pool.log`), listens on 0.0.0.0 — token is its only protection; keep 8770 off the internet |
| Monitor | Live (Alpaca SIP), radar BURU INLF ADT CETX NCPL NCLH PURR |
| Mac app | `~/Applications/Nomisma.app` uses the running server, so server/JS fixes apply after a page reload (⌘R). Rebuild only for `desktop/` changes: quit app, `python3 tools/build_desktop.py --install` |
| Windows build | Not done; needs the GitHub workflow and the user's go-ahead |

**Settings**
- Search (radar): Alpaca, all listings, $0.10–$50, ≥ +10% day change, **≥ 10M regular-session shares** (premarket excluded), top 50 ranked by total day volume. Weekdays 09:15 ET, then every 30 min until 16:00. Each successful search replaces the radar.
- Alert rule: same price range, ≥ 10M regular-session volume, Buy 65 / Strong buy 85, 2 confirmation bars, 300 s cooldown.
- A stock re-alerts only after dropping to Watch and waiting out the cooldown; an upgrade to Strong buy alerts immediately.

**API tips:** POSTs need `Content-Type: application/json` and `Origin: http://127.0.0.1:8765`. Pass the body explicitly (`-d '{}'`); a zsh `${2:-{}}` default produced invalid JSON. Useful endpoints: `/api/monitor`, `/api/monitor/start|stop|config`, `/api/monitor/alerts?limit=100&offset=0` (limit >100 returns an error), `/api/discovery`, `/api/discovery/latest`. The alert tracker is in `data/nomisma.sqlite3`, table `state`, key `monitor_alert_tracker`.

## Completed today

### 1. Stale radar at the open — `nomisma/server.py` `_update_radar`
- **Symptom:** the watchlist still showed yesterday's 16 stocks at 9:33.
- **Cause:** searches before ~9:40 find nothing (10M regular-session shares can't accumulate yet), and an empty search kept the previous radar — including a previous day's. Stale names could also alert without being up 10% today.
- **Fix:** `self.radar_date` / `self.radar_paused` (in memory). An empty search when the radar is from an earlier session **stops the monitor** with the message "Paused: no stock meets today's search yet…"; the next search with rows restarts it. Empty searches later in the same day still keep that day's radar.
- Test: `test_empty_search_on_a_new_day_pauses_the_radar_until_stocks_qualify`.

### 2. Banner stuck after a server restart — `nomisma/static/app.js` `pollStatus`
- "Checking scan progress failed: Cannot reach Nomisma…" never cleared after the server came back, because the lost job returned as not-running with no error. Now `state.pollFailed` clears the banner on the next successful poll.

### 3. Clock lag suppressing alerts — `nomisma/monitor_metrics.py`, `nomisma/monitor.py` (most important)
- This Mac's clock is ~0.1 s **behind** (`sntp time.apple.com` → +0.10 s). Exchange timestamps therefore looked "in the future".
- **(a)** `build_rows` rejected trades and quotes with `t > now`. On busy stocks the newest trade almost always did, so rows flickered to "A valid trade/quote from the past 30 seconds is required" about half the time.
- **(b)** `_on_event` dropped or skipped minute bars that arrived before local `stamp + 1 min`, and `build_rows` treated them as unfinished. Skipped minutes reset the 2-bar confirmation streak, so **streaks stayed at 1 and almost nothing alerted all morning** (only BURU at 10:07 got through).
- **Fix:** `_CLOCK_SKEW = timedelta(seconds=2)` in `monitor_metrics.py`. It is used in `_fresh`, the trade/quote/status/price-band validity checks, and in `monitor.py` for bar acceptance. Bar evaluation runs with `now=max(now, stamp + 1 min)`.
- Tests: `test_trade_and_quote_slightly_ahead_of_local_clock_stay_fresh` (monitor_metrics) and `test_bar_arriving_just_before_lagging_local_clock_ends_its_minute_is_evaluated` (monitor; verified to fail with skew 0). The existing future-trade test now uses +3 s.
- **Verified live:** after the 11:26 restart, all 7 radar stocks show fresh trades and quotes, and every minute is counted. The first post-fix alerts went out at 11:28:00: **PURR Buy $11.545, NCLH Buy $18.435, BURU Buy $0.4095** (all score 75, minute 11:27).

### 4. Trade log — `nomisma/data/trade_log.csv` (git-ignored)
One trade so far:

| Date | Stock | Entry | Exit | Shares | P&L | Return | Account |
|---|---|---|---|---|---|---|---|
| 10/29 | BURU | 10:09 @ 0.2549 | 10:30 @ 0.2959 | 4,000 | +$164.00 | +16.08% | $1,650 → **$1,814** (+9.94%) |

- Columns also record the position size (62% of the account), the trigger alert (Strong buy, minute 10:06, sent 10:07:00 @ 0.2492, score 100, "(assumed)" — **the user has not confirmed it was the trigger**), entry delay (2 min, +2.29% vs. the alert price), radar since 09:37, and the replay comparison.
- Replay rule for the same alert: entry 0.2492 at 10:07, +10% target hit 10:19, giving +10.0%.
- The next trade starts from **$1,814** unless the user gives another balance (for example after fees). P&L is before fees.

### 5. Replay work preserved
The scratchpad is not durable, so scripts, configs, reports and the 20-session cache (101 MB) were copied to `nomisma/data/replay_scripts/` (`multi_replay.py`, `score_exits.py`, `pullback.py`, `replay_today.py`, `build_cache.py`, `multi_report*.json`, `sessions/`).

## Background: replay findings and user decisions (from 10/28–29)
- 20 sessions (10/01–10/28), one position per stock, −5% / +10% / 30 min exit, 0.2% cost: **no variant broke even.** Current alerts −0.64% per trade, ~82 alerts/day, 4/20 profitable days. Best: Strong buy only after 11:00, −0.42% per trade, 6/20 days. 10:00–11:00 ET is the worst hour.
- The user chose to keep Buy and Strong buy alerts live and trade them anyway, log real trades for comparison, and **stop ad-hoc tuning** on these sessions. New edge ideas go through `nomisma/DISCOVERY_STUDY_SPEC.md` (sealed holdout).
- Known gap the user accepted: ~82 alerts/day vs. their stated capacity of 20–30.

## Stuck / open problems
1. **The live alert history before 11:26 on 10/29 is not representative.** The clock bug suppressed alerts, so today's morning shouldn't be compared with the replay as if the live rules had worked. Earlier live sessions were probably affected the same way.
2. **The 9:15 search is useless under the 10M regular-session rule.** It always comes back empty. A first search around 9:35–9:45 was suggested but not decided.
3. **`radar_date` is in memory.** After a server restart, the first empty search pauses an active monitor even if the radar is from today. That is harmless in the morning; mid-day empty searches are rare.
4. **The replay's 10:00–11:00 weakness and the alert volume are unresolved by design**, because the user chose to trade as-is.
5. **Pool log shows repeated `ProviderError`s** for research, scan and minute reconciliation earlier. Not investigated.

## Next steps
1. When the user sends trades, append rows to `nomisma/data/trade_log.csv` (same columns), look up the triggering alert via `/api/monitor/alerts`, and compare with the replay rule (−5% / +10% / 30 min from the alert price) using Alpaca 1-minute bars.
2. Ask the user to confirm whether the BURU 10:07 Strong buy was the trigger, then drop "(assumed)".
3. After the close, summarise the day: alerts (count by hour and level), trades, P&L versus the replay.
4. Optional, only with the user's agreement: move the first scheduled search to ~9:35; persist `radar_date`; rebuild the Mac app (only needed for `desktop/` changes).
5. Update the memory file with the clock-skew finding if it proves durable.

## Pitfalls
- **Never print `.env` values**; show only key names and lengths.
- **Restarting the server kills in-flight scans and searches** and briefly shows "Cannot reach Nomisma" in the app. Tell the user to reload (⌘R) and rerun a lost scan. After a restart, start the monitor again (`POST /api/monitor/start -d '{}'`).
- **Restarting during market hours resets confirmation streaks** for the current minute window; alerts can lag by 1–2 minutes after a restart.
- **The local clock runs behind.** Anything comparing exchange timestamps with `utcnow()` needs the `_CLOCK_SKEW` tolerance. Don't reintroduce strict `<= now` checks.
- **`multi_replay.py` picks "the last 20 sessions before today".** Run on a later day, it selects a different window and downloads new data, so set the dates explicitly to reproduce the 10/01–10/28 results.
- **Replay approximations:** 1-minute closes as fills, bid = ask, no slippage, currently listed stocks only. The user's real entry on BURU was 2.3% worse than the alert price.
- **Foreground `sleep` is blocked** in this harness; use Monitor or a background `until` loop.
- **Position sizing:** the user put 62% of the account into one trade. The replay's base rate is negative, so flag sizing risk without lecturing.
