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

---

# Discovery study handoff — October 29, 2026

This section covers the offline discovery study (`nomisma/DISCOVERY_STUDY_SPEC.md`), separate from the live trading above. It brings `handoff/10_22_HANDOFF.md` up to date; that file's **Pitfalls** list still applies in full.

## Start here

- **Status:** data acquisition is complete, and the holdout is downloaded and **sealed**. Both studies concluded **"no edge found"**, so there are no finalists and the holdout stays closed.
- **Running:** nothing. No `discovery_acquire.py` process is running.
- **Next decision belongs to the user.** Should research continue at all? If yes, with which pre-registered third hypothesis? Ask with `/grill-me`: numbered questions, each with a recommended answer, then wait for answers.
- **Relevance to live trading:** the user is now trading live alerts, which use a different rule set from the study's. The study's finding still applies: the gross drift of a breakout entry on sub-$10 stocks, about +1%, roughly equals a round trip's cost. Mention it if asked, without lecturing.

## Locations

| What | Where |
|---|---|
| Spec | `nomisma/DISCOVERY_STUDY_SPEC.md` in the main checkout. This is the most current copy (see the next row). |
| Worktree copy | `/Users/barry/orca/workspaces/heuresis/Research_1`, branch `fantasybarry/Research_1`, at `93854b0`. Its spec **lacks the holdout-seal lines** added on 10/22 (main spec lines 218–222). Copy the main spec there before the next commit on that branch. |
| Code | `nomisma/nomisma/discovery_data.py`, `discovery_signals.py`, `discovery_replay.py`, `tools/discovery_acquire.py` |
| Tests | `nomisma/tests/test_discovery_data.py`: 8 tests, passing on 10/29 |
| Data (gitignored) | `nomisma/data/discovery/`, 3.4 GB in total. `discovery/` holds results and raw data, `holdout/` holds sealed raw data, `reference/delisted` holds the delisted-ticker list. |
| Logs | `data/discovery/step1.log`, `step3-2025-10.log`, `step5.log`, `spreads-2025-10.log` |
| Pre-registration | `nomisma/HYPOTHESES`, with the second-study result in `data/discovery/discovery/hypotheses-2025-10_2026-09.json` |
| Credentials | `nomisma/.env` holds `MASSIVE_API_KEY`, the free Basic plan key added 10/16. `run.py` whitelists it. Load it with `load_environment`. **Never print it.** |

## Completed

1. **Spec design (10/15–16).** The user and I worked through 20 `/grill-me` questions and rewrote the spec to match:
   - Every opportunity is the unit of analysis.
   - The universe includes delisted stocks.
   - Four resistance arms: b3, b6, c and d.
   - Data: Massive Basic for bars, Alpaca free SIP for quotes.
   - Risk is 4.1% of session-open equity.
   - At most 2 finalists, chosen by a fixed rule.
   - A pilot go/no-go gate, and a sealed holdout.
2. **Step 1, universe (10/16).**
   - Unadjusted grouped daily bars plus monthly point-in-time ticker lists.
   - Result: 251 sessions, 2,971 distinct tickers, 2,075 per day at the median (2,018–2,192), and 522,097 stock-days (`discovery/universe_summary.json`).
   - Verified beforehand: as-of-date lists include stocks delisted later, and one page of the delisted list reaches back to January 2025.
3. **Steps 2–6** were done in other sessions; results are in the files listed.
   - **Delisted check:** 599 common stocks delisted during discovery, and all sampled ones have minute bars (`delisted_check.json`).
   - **October 2025 pilot:** 191 bars per stock-day. The delisted share is 13–14%. Every arm projects far more than 600 opportunities a year (`pilot-2025-10-summary.json`).
   - **Disk projection:** 51 GB, mostly quotes (`pilot-2025-10-disk.json`).
   - **Replays, conditions, spreads and the second study:** see the spec's "Condition search", "Loss follow-up" and "Second study" sections, and `tally.txt`.
4. **Holdout download and seal (10/22).**
   - The download had died mid-August 2025 when a session ended. I resumed it and finished August and September.
   - Every month is complete. Tickers per month: April 2,507, May 2,406, June 2,341, July 2,295, August 2,309, September 2,206.
   - `manifest holdout` lists 14,231 files, with manifest SHA-256 `a770dd255cb035d347ac07f2e1ebce2df3f8fed10a03237edad48d29aa34a34b`. It's recorded in the spec.

## Stuck or open

1. **There's no direction for a third study.** It's the user's call.
2. **Forward collection (October 2026 onward) is in the spec but not built.** No code collects it. Any future candidate needs it for confirmation.
3. **Step 7, the full order-type replay with Alpaca quotes, never ran.** No arm survived step 6, so this is by design. Only spread samples exist (`spreads-*.json`, `alpaca-spreads/`).
4. **Four `replay-v2-*-summary.json` files are still missing,** for October 2025–January 2026; 8 of 12 exist. Scoring doesn't need them.
5. **The Massive API key was pasted into the 10/16 chat.** Suggest the user regenerate it on massive.com and update `.env`.

## Next steps

1. Start a `/grill-me` round on whether to continue, and if so, which entry hypothesis. The 10/22 conclusion was that any edge must come from the entry, since no exit created one.
2. If continuing:
   1. pre-register the hypothesis in `HYPOTHESES`, with its cohort, exit, costs and pass rules;
   2. commit it in `Research_1`;
   3. score it **once** on `replay-v2-*.csv.gz`.
3. Only if something passes: build forward collection, then write a committed `FINALISTS` file before the holdout is read.
4. Before the next commit in `Research_1`, sync the spec from main and commit the untracked `10_22_HANDOFF.md` there if the user wants it.

## Pitfalls specific to this session

- **Checking the seal overwrites the file list.** `discovery_acquire.py manifest holdout` **rewrites** `holdout/MANIFEST.json`. To check the seal, copy that file aside first, rerun, and compare the printed hash with the one in the spec. A mismatch means a holdout file changed.
- **Prices stay unadjusted** everywhere (`adjusted=false`). Adjusted history rescales bars from before a reverse split, which breaks the $0.10–$10 filter.
- **Massive Basic is slow and its history window slides.**
  - The limit is 5 calls a minute. One month of minute bars takes about 8 hours.
  - "Could not reach Massive after retries" happens now and then. Rerun the same command; it resumes, because a ticker counts as done only once its page-0 file exists.
  - The free plan keeps a rolling 2-year history. The holdout rolls off around April 2027 and discovery around October 2027. Everything is already on disk, so **don't delete `data/discovery/`**.
- **How the universe is built.** A ticker counts as common stock if its month's list or the next month's includes it, which catches mid-month listings. Grouped daily bars exclude OTC.
- **Alpaca's free plan has gaps.** It returns no data for delisted symbols, and SIP requests must end at least 15 minutes in the past.
- **Two sessions share the main checkout.** It also holds uncommitted live-trading work (see the live-trading section above), so don't commit or stash there. This discovery section was **appended** on 10/29; the live-trading section above belongs to another session and is untouched. Its pre-edit version is in commit `f252d5c`.
