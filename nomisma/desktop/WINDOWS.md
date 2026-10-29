# Nomisma for Windows 11 Pro

The Windows edition is a native desktop window for **Windows 11 Pro on Intel or AMD 64-bit PCs**. It includes Python and .NET. You do not need Terminal, Python, Visual Studio, or a .NET installation to use it. This build does not target Windows on ARM.

## Download and install

Use `Nomisma-1.2.4-win-x64-setup.exe`. Run it on your Windows PC and follow the installer. It installs for your Windows account, adds Start menu shortcuts, and offers an optional desktop shortcut. Administrator access is not required for Nomisma itself.

The alternative `Nomisma-1.2.4-win-x64-portable.zip` can be extracted to a folder and started with `Nomisma.exe`. Keep all extracted files together. Both editions use your Windows profile for data; portable means no installer, not that research data travels inside the app folder.

Microsoft Edge WebView2 Runtime is required. It is normally included with Windows 11. If missing, Nomisma displays **Get Microsoft WebView2**, which opens Microsoft's download page. [Microsoft's WebView2 distribution guidance](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution)

These builds are unsigned. Windows may display an unknown-publisher or SmartScreen warning; a GitHub download and matching checksum do not constitute publisher signing. Organizational policies may require a signed build. Code signing can be added to the release process when a signing certificate is available.

## Publish clean source to GitHub

The provided `Nomisma-source.zip` contains source code, tests, build scripts, and the GitHub workflow. It excludes `.git` history, `.env`, research databases, backups, application binaries, and build caches. The existing local Git history contains an older database; deleting the current file from tracking does not remove historical copies.

1. Extract **Nomisma-source.zip into a new folder**.
2. Create a new empty GitHub repository and push the extracted contents from that new folder. Keep `.github/` and `nomisma/` at the repository root; uploading the ZIP itself as a file will not activate its workflow.
3. Open **Actions → Nomisma Windows**. The first source push starts a build. You can also choose **Run workflow**, using version `1.2.4`.
4. After it succeeds, open the run and download the **Nomisma-Windows-x64** artifact. Extract that download to find the installer, portable ZIP, and checksums.

For example, from the **new extracted folder**, replace the URL with your new repository's URL:

```sh
git init -b main
git add .
git commit -m "Add Nomisma desktop apps and Windows installer"
git remote add origin https://github.com/YOUR-ACCOUNT/YOUR-REPOSITORY.git
git push -u origin main
```

For permanent download links on the repository's **Releases** page, create and push a version tag:

```sh
git tag nomisma-v1.2.4
git push origin nomisma-v1.2.4
```

The workflow extracts the installer version from the tag. Use a new tag, such as `nomisma-v1.2.5`, for the next release. It publishes only after the Windows build and verification succeed. Ordinary pushes, pull requests, and manual runs produce downloadable Actions artifacts without publishing a release.

GitHub's Windows runner checks the Python test suite, package checksums, installation, the native WebView2 window and bridge, shutdown, reopening, reinstallation, and data preservation during uninstall. No market-data credentials are required. The local Mac build can compile Windows executables and validate their package structure, but it cannot run the Windows desktop or installer; the workflow supplies that verification after you push.

## Your data and market credentials

| Item | Windows location |
| --- | --- |
| Installed application | `%LOCALAPPDATA%\Programs\Nomisma` |
| Research database and backups | `%LOCALAPPDATA%\Nomisma\data` |
| Credentials | `%LOCALAPPDATA%\Nomisma\.env` |
| WebView2 profile and desktop preferences | `%LOCALAPPDATA%\Nomisma` |

The installer starts with an empty workspace configuration and never includes your Mac's paths, credentials, or research data. The first launch provides synthetic demonstration data until you configure a real source.

To configure Alpaca, use **File → Open configuration folder** and create `.env` there using the project's `.env.example` as a template. Enter your keys locally on the Windows PC. Use **File → Restart local service** after editing it, then configure and start the monitor. Restarting the service stops the current stream and requires a new **Start monitor**. This command is available only for the service the app owns.

To carry research from the Mac, use **Settings → Download workspace backup**, transfer that SQLite file privately, and restore it in Windows Settings after stopping monitoring. Backups contain research and settings, not API keys; configure credentials separately. Do not put backups or `.env` into GitHub.

Closing or exiting the Windows app stops its own local server, live monitor, and scheduled scans. Keep it open for monitoring. If it connected to an independently running Nomisma server, that server remains running when the window closes. The app's status bar identifies which behavior applies.

Desktop alerts and sound are off until enabled. Windows notification settings and Do not disturb can affect delivery. Closing the app stops its notifications. This is a research application and does not submit trades.

## Updates and uninstalling

Exit Nomisma before installing an update. Installers use the same per-user location and preserve research data, credentials, and preferences outside that folder. The installer asks you to close a running app before proceeding.

Remove Nomisma from Windows **Installed apps** or its Start menu uninstall shortcut. Uninstalling preserves the `%LOCALAPPDATA%\Nomisma` data folder for later use.

### Candidate freshness fixes in 1.2.3

Candidate discovery checks both the receipt time and the latest completed minute behind an extended-hours volume fallback. Both must be no more than two minutes old, and freshness is checked again after historical metrics load. A stale fallback cannot pass a positive minimum-volume filter or earn day-volume or day-RVOL ranking points. With a zero minimum, the candidate remains visible with those inputs unavailable. The provider's current daily aggregate keeps its existing five-minute receipt limit for discovery. Saved filters, schedules, and research are preserved.

After history loads, discovery refreshes stale, missing, or invalid quotes for its selected ranking pool using the same feed. Valid provider timestamps must still be within 30 seconds; failed or unusable responses leave spreads unavailable and earn no spread points. This quote refresh does not change trade or volume timestamps. Radar and candidate volume cells now visibly identify stale or partial totals.

### Alert source fix in 1.2.2

The main **Setup alerts** panel now shows only the monitor's configured source. Saved synthetic alerts no longer appear beside an Alpaca monitor. The panel's unread count and **Mark all read** action use that same source. All earlier records remain available in the **Research journal**; this update does not delete alerts or change another source's acknowledgment state.

### Mobile table fix in 1.2.1

On narrow windows, the candidate symbol column scrolls with the table so it no longer covers the liquidity and volatility metrics. Desktop windows retain the pinned symbol column. Existing selections, research data, and settings are preserved.

### Intraday improvements in 1.2.0

- Candidate results and the radar display total day volume including available premarket activity, average volume over 63 and 20 prior sessions, day RVOL, dollar/percentage spread, beta versus SPY, and daily ATR in dollars and percent. Sort each metric high to low, or use the explained liquidity/volatility ranking. Missing metrics remain visible and earn no points. The technical setup score and its alert guards remain separate.
- **Find candidates** can run automatically each weekday at **9:15 a.m. New York time**, or another saved time. The schedule starts off; enable it after saving your search source, universe, and filters. Keep the Windows app open for scheduled searches. A later opening catches up for the current weekday, and the last successful results remain available after restarting. Searches do not replace monitor symbols or start monitoring.
- **Refresh data** updates quotes, minute history, daily volume baselines, and optional float data while the active monitor continues streaming. Progress and errors stay visible, and newer streamed values and saved alert state are preserved. This button does not reload `.env`; use **File → Restart local service** for changed credentials.
- The radar supports **50 symbols**, including imports from scan results and candidate selections. Your provider plan must allow the selected count. Alpaca Basic permits 30 streamed symbols; larger lists need an eligible plan. [Alpaca market-data plans](https://docs.alpaca.markets/us/docs/about-market-data-api)
- Independent history requests load concurrently, radar updates omit full chart histories, and each stock report loads its detailed history when opened.

The candidate schedule is independent of the daily screener's after-close schedule. Weekday market holidays can return no current-session candidates with a market-closed note. See [the intraday workflow](../README.md#intraday-workflow-and-reports) for schedule retries, data sources, and refresh behavior.

During regular trading, click **Find candidates** for another search. No repeating intraday scan or automatic addition of symbols is enabled. The existing volume threshold now uses total day volume while preserving its saved numeric value; completed regular-session history is still required for technical alerts.

### Startup fix in 1.0.1

Version 1.0.0 could pause at **Starting Nomisma’s local service…** for 30–60 seconds. Its launcher checked 31 local ports in sequence, making up to two connection attempts per unused port; Windows could wait for each refused connection to time out. Version 1.0.1 checks free ports with a local socket bind, probes only occupied ports concurrently, and bypasses proxy discovery for local health checks.

Startup timings are recorded in `%LOCALAPPDATA%\Nomisma\data\startup.log` (or your configured data folder). Each line records the version, timestamp, success flag, total elapsed milliseconds, and cumulative `backend_ready_ms`, `webview_ready_ms`, and `page_ready_ms` milestones. A missing milestone means that stage was not reached. The log contains no credentials or market data and keeps at most 256 KiB plus one previous file. These timings help identify any delay remaining after the update.

## Build locally

Build prerequisites are Python 3.9+, the .NET 10 SDK, and NSIS 3. The builder works on Windows, macOS, and Linux, and downloads pinned, checksum-verified Windows Python and timezone packages. NuGet restores the pinned WebView2 package.

From the `nomisma` project directory:

```sh
python tools/build_windows.py --version 1.2.4
```

If the build tools are not on PATH, add `--dotnet /path/to/dotnet` and `--makensis /path/to/makensis`. Outputs are placed in `dist/windows/`. The application is self-contained with respect to Python and .NET; WebView2 Runtime is shared with Windows.

To create a new clean source snapshot from this repository:

```sh
python tools/export_source.py
```

To verify a downloaded installer against its release checksum on Windows:

```powershell
Get-FileHash .\Nomisma-1.2.4-win-x64-setup.exe -Algorithm SHA256
```

Compare the result with the matching entry in `SHA256SUMS.txt` from the same release.
