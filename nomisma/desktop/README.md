# Nomisma for macOS

For the Windows 11 Pro installer and GitHub release workflow, see [Nomisma for Windows](WINDOWS.md).

Open **Nomisma.app** in `~/Applications`. The app includes Python and Nomisma's backend, starts the local service when needed, and opens the live monitor in a native macOS window. Terminal and developer tools are not needed to run the finished app.

The workspace build uses this project's existing `data/nomisma.sqlite3` and `.env`. It reuses a healthy server for that database, including an already-running monitor. If another application occupies the default port, it chooses another available loopback port. Opening the app never starts a market monitor automatically.

Version **1.2.4** includes up to **50 radar symbols**, faster market-data loading, a **Refresh data** button for an active monitor, and saved candidate searches with an optional weekday schedule. The candidate schedule defaults to **9:15 a.m. New York time** and starts off. Enable it in **Find candidates** after saving the source and filters you want to use. Keep the local service and computer running; a later opening catches up for the current weekday. Results persist across restarts, and searches leave monitor symbols and monitoring state unchanged. Alpaca's Basic plan limits streaming to 30 symbols; larger lists need an eligible market-data plan. See [the intraday workflow](../README.md#intraday-workflow-and-reports).

Candidate results and the radar now show total day volume including available premarket activity, 3-month and 20-session average volume, day RVOL, dollar/percentage spread, beta versus SPY, and daily ATR. Sort individual values high to low or use the explained liquidity/volatility ranking; missing values remain visible. The separate technical setup score continues to control alerts. During regular trading, new candidate searches run when you click **Find candidates**; there is no repeating intraday scan or automatic addition of symbols.

Version 1.2.1 also fixes candidate-table scrolling on narrow screens: the symbol column moves with the table so every metric can be read in full. Wider windows retain the pinned symbol column.

Version **1.2.2** keeps the main **Setup alerts** panel aligned with the monitor's configured source. Alpaca shows only Alpaca alerts, and **Mark all read** affects that source only. Earlier synthetic alerts remain available in the **Research journal** and in the main panel when the synthetic lab is selected.

Version **1.2.3** fixes freshness checks for candidate volume reconstructed from completed extended-hours minutes. Both the response receipt and latest included minute must be within two minutes, including after historical metrics finish loading. Stale fallback totals cannot pass a positive minimum-volume filter or earn volume ranking points. With a zero minimum, the candidate remains visible and its unavailable volume inputs earn no points. Saved filters, schedules, and research remain intact.

The same release refreshes stale, missing, or invalid candidate quotes after history loads, so a long search can recover current spreads. It keeps the chosen feed and the 30-second provider-timestamp limit; unsuccessful refreshes remain unavailable. The radar and candidate table visibly label **Stale volume** or **Partial volume**.

## Native controls

- **Nomisma → Settings** (`⌘,`) opens source and screener settings.
- **View** switches between the live monitor, daily screener, watchlist, and history. `⌘R` reloads the workspace.
- **Refresh data** in the live monitor reloads market data while its connection continues. It is separate from reloading the window or restarting the local service.
- **Nomisma → Show Research Data in Finder** opens the active data directory. **Open Configuration Folder** opens the folder containing `.env`.
- CSV and backup exports use a native Save dialog; imports use a native file picker.
- **Print report**, or `⌘P` with a report open, uses the macOS print dialog.
- **Desktop alerts** asks for macOS notification permission when clicked. Notifications and sound remain off until enabled. Synthetic alerts remain in the research journal and in the inbox when the synthetic source is selected.

Closing the window keeps the app running; click its Dock icon to reopen it. `⌘Q` quits the native app. The local server keeps running in either case, preserving active monitoring and schedules. Use **Stop monitor** to end streaming. Quit the native app to stop its notifications and sound. Restarting the computer stops the local server; no login item or system service is installed.

Credentials are read when the local server starts. Reloading the window or reopening the app reuses that server and does not reload `.env`. To apply changed credentials, stop monitoring, quit the app, and stop its local Python server in Activity Monitor before reopening Nomisma. The process command contains `run.py` and this workspace's `--data-dir`; leave unrelated Python processes alone.

## Build or update

From the project directory:

```sh
python3 tools/build_desktop.py --install
```

The builder creates `dist/Nomisma.app` and installs it in `~/Applications/Nomisma.app`. Quit the native app before replacing an installed build. The build machine needs Apple's command-line developer tools and a standalone Python runtime. The default runtime comes from Codex's local runtime cache; use `--python-runtime /path/to/python` to select another relocatable distribution containing `bin/python3` and its standard library. No third-party Python packages are required.

The backend and frontend source are copied into the bundle at build time. Rebuild after changing them. An already-running local server continues to serve its own source until restarted. The builder verifies runtime relocation, native-library links, required standard-library imports, and the finished app's code signature. Builds match the current Mac's architecture and require macOS 13 or newer.

App bundles contain application code, the Python runtime, and paths to the workspace. They do **not** contain credentials, research databases, imports, or backups. Rebuilding replaces only the app bundle and preserves external workspace files.

For a build that starts with its own data directory instead of linking this checkout:

```sh
python3 tools/build_desktop.py --portable --output dist/Nomisma-Portable.app
```

Portable builds store data in `~/Library/Application Support/Nomisma/data` and read credentials from `~/Library/Application Support/Nomisma/.env`. If a linked workspace is unavailable on another Mac, the normal build also falls back to that location. To share an app without including workspace paths, use `--portable`. These local builds use an ad-hoc code signature; public distribution requires Developer ID signing and Apple notarization.

## Troubleshooting

The startup screen displays an error and **Try Again** if the local service cannot start. Check that the data folder is writable and consult its `nomisma.log`. Another application using port 8765 is left untouched. The host searches ports 8765–8795 and remembers its selected port for the next launch.

The server binds only to your Mac's loopback interface. External links open in your normal browser. Native notification, printing, and file-dialog capabilities are restricted to the active local workspace.

Version **1.2.4** restricts real candidate searches, daily Alpaca/CSV screening, and live radar selections to verified company common/ordinary stocks and depositary shares. ETFs, funds, derivatives, preferred shares and unverified instruments are excluded using Nasdaq Trader symbol directories. Internet access is required to refresh this hourly classification cache. SPY is retained only as the market benchmark.
