# Handoff: Nomisma discovery study, 2026-10-22

## Where things stand

The research has found no edge. Two studies are finished, and both say the same thing: a breakout entry on gapping sub-$10 stocks drifts about +1% gross, which is about what a round trip costs. No candidate goes on to forward confirmation, and the holdout stays sealed.

**Next step:** a new `/grill-me` round with the user. Start with the bigger question: is this setup worth more studies at all? The setup is long-only, sub-$10 stocks, a $2,440 cash account under the pattern-day-trader limit, and 15-minute momentum trades. Only after that, pick a third hypothesis, if there is one.

## Locations

| What | Where |
|---|---|
| Worktree (my work) | `/Users/barry/orca/workspaces/heuresis/Research_1`, branch `fantasybarry/Research_1` |
| Main checkout | `/Users/barry/heuresis`, `main`. **Has a lot of the user's uncommitted work. Don't touch anything except the discovery files.** |
| Spec | `nomisma/DISCOVERY_STUDY_SPEC.md`. The worktree and main copies are identical. |
| Pre-registration | `nomisma/HYPOTHESES` (commit `27e56d9`, 2026-10-21T19:36). Also copied to main. |
| Code | `nomisma/nomisma/discovery_replay.py`, `discovery_data.py`, `discovery_signals.py`, `tools/discovery_acquire.py` |
| Tests | `nomisma/tests/test_discovery_replay.py`, `test_discovery_data.py`. 15 tests, passing in both checkouts. |
| Data (gitignored) | `/Users/barry/heuresis/nomisma/data/discovery/discovery/` |
| Second-study result | `data/discovery/discovery/hypotheses-2025-10_2026-09.json` |
| Credentials | `/Users/barry/heuresis/nomisma/.env`. Load them with `from run import load_environment; load_environment(Path('.env'))`, run from `/Users/barry/heuresis/nomisma`. **Never print them.** |

Commits on the branch: `5ed6716` baseline copy → `dedf6e8` replay fixes and stop variants → `3eaffda` hold test, candidate closed → `27e56d9` HYPOTHESES → `911712f` H1/H2 scoring → `bdea131` spec/data sync and first-study conclusions → `93854b0` second-study result. The working tree is clean. Nothing has been pushed or turned into a PR.

## Completed

### First study: the 39 losers on the arm c, gap ≥40% candidate
The candidate: arm c (resistance = premarket high), primary window, liquid, immediate entry, gap ≥40%, premarket ≥$1M, a 1.5×ATR stop and a 15-minute hold.

- **Replay fixes** in `discovery_replay.py`:
  - `HALT_GAP` = 5 missing minutes → status `suspected_halt`.
  - `LIMIT` = 2% above the deciding close → status `above_limit`.
  - When the deadline minute has no bar, the time exit fills at the next print.
  - Missing minutes extend a streak of closes at/below resistance.
- **Stop variants** (S0–S3, from 1.5 ATR to no stop) at 0.5% per side: mean net +0.01% to +0.24%, every lower 90% bound about −1.1% to −1.2%. None passes.
- **Pullback-wick exit:** worse on every variant. It cut ILLR, a +47% winner.
- **Hold-time tests:** every longer hold is worse, and 5 and 10 minutes fail too. Returns peak 10–30 minutes after entry, then fade.
- **Outcome:** candidate closed, "no edge found." The user accepted the conclusions:
  1. The move fades after 10–30 minutes.
  2. No exit creates an edge, so any edge must come from the entry.
  3. The fade can't be traded: it's a cash account with no shorting.

### Second study: pre-registered H1 and H2, scored once on 2026-10-22
Cohort: arm c, gap ≥20%, premarket ≥$1M, primary window, liquid. 737 opportunities, October 2025–September 2026, read from `replay-v2-*.csv.gz`.

| | Fills | Mean net (deciding cost) | Lower 90% | Without best | Months + |
|---|---:|---:|---:|---:|---:|
| H1 pullback-and-reclaim (0.5% per side) | 127 | −1.00% | −1.74% | −1.21% | 3/12 |
| H2 close ≥$2, ≥$100k signal-minute volume (measured spread) | 379 | −0.42% | −1.18% | −0.56% | 6/12 |

Both fail every check, and they **must not be revised on this data**.
- **H1:** gross return is about 0%. The 127 trades split 63 target exits, 57 stop exits and 7 time exits.
- **H2:** the measured spread costs about half the assumed 1% round trip, but the gross drift is only about +0.1%.

## Stuck or open

1. **The holdout download is running again**, but not because I restarted it. Another session (shell PID 4130, python PID 6275) restarted it at 13:45 on 2026-10-22. It finished 2025-08 and is now on 2025-09, at about 740 of 2,206 tickers as of this writing.
   - Log: `/Users/barry/heuresis/nomisma/data/discovery/step5.log`.
   - **It isn't mine. Don't kill or restart it without asking.** If it dies, the restart command is `python3 -u tools/discovery_acquire.py minutes --month 2025-09`, run from `nomisma/`. It skips files that already exist.
   - The question I asked earlier, whether to restart it, is now moot.
2. **October 2025–January 2026 have no `replay-v2-*-summary.json`.** They were lost when the session restarted mid-run. Scoring doesn't need them; regenerate them only if someone asks.
3. **No direction yet for a third study.** It's the user's call.

## Pitfalls

- **The holdout (April–September 2025) is sealed.** `data.readable` refuses it unless a `FINALISTS` file exists. Don't create one, and don't analyse holdout bars, even though they are being downloaded.
- **Don't read these July–September 2026 results produced by another session:** `tally.txt`, `conditions-2026-07/08/09.json`, and the ~10 lines that session added around line 241 of the spec. Treat July–September as already seen.
- **Never overwrite outputs.** New runs get new names (`replay-v3-*` etc.).
- **Pre-register before scoring.** Write the hypothesis and its exit, fixed in advance, into `HYPOTHESES`, commit it, then score it once. `hypotheses()` refuses to run without the file.
- **Pass rules (user-agreed):**
  - session-bootstrap lower 90% bound >0
  - at least 8 of 12 months positive
  - positive without the best trade
  - positive on both sides of price <$2/≥$2 and of 9:30–10:00 / 10:00–11:00
  - every quarter positive, with no quarter over half the total
  - judged on the whole cohort, including the top winners
  - main cost 0.5% per side; also report 1% and 2%
- **Don't use body/range or gap size as filters.** They are weak contrasts, and the user ruled them out.
- **Credentials:** spread scoring fails with "Set ALPACA_API_KEY…" unless `load_environment` runs first.
- **Sync changes to main by copying individual files.** Never commit in the main checkout and never stash there; the stash is shared across worktrees.
- **Commit trailer:** end commit messages with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Working style:** the user drives decisions through `/grill-me`: numbered questions, each with a recommended answer, then wait for the answers. Ponytail mode (minimal code) is on.
