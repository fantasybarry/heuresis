# Nomisma for Windows 11 Pro

The Windows edition is a native desktop window for **Windows 11 Pro on Intel or AMD 64-bit PCs**. It includes Python and .NET. You do not need Terminal, Python, Visual Studio, or a .NET installation to use it. This build does not target Windows on ARM.

## Download and install

Use `Nomisma-1.0.1-win-x64-setup.exe`. Run it on your Windows PC and follow the installer. It installs for your Windows account, adds Start menu shortcuts, and offers an optional desktop shortcut. Administrator access is not required for Nomisma itself.

The alternative `Nomisma-1.0.1-win-x64-portable.zip` can be extracted to a folder and started with `Nomisma.exe`. Keep all extracted files together. Both editions use your Windows profile for data; portable means no installer, not that research data travels inside the app folder.

Microsoft Edge WebView2 Runtime is required. It is normally included with Windows 11. If missing, Nomisma displays **Get Microsoft WebView2**, which opens Microsoft's download page. [Microsoft's WebView2 distribution guidance](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution)

These builds are unsigned. Windows may display an unknown-publisher or SmartScreen warning; a GitHub download and matching checksum do not constitute publisher signing. Organizational policies may require a signed build. Code signing can be added to the release process when a signing certificate is available.

## Publish clean source to GitHub

The provided `Nomisma-source.zip` contains source code, tests, build scripts, and the GitHub workflow. It excludes `.git` history, `.env`, research databases, backups, application binaries, and build caches. The existing local Git history contains an older database; deleting the current file from tracking does not remove historical copies.

1. Extract **Nomisma-source.zip into a new folder**.
2. Create a new empty GitHub repository and push the extracted contents from that new folder. Keep `.github/` and `nomisma/` at the repository root; uploading the ZIP itself as a file will not activate its workflow.
3. Open **Actions → Nomisma Windows**. The first source push starts a build. You can also choose **Run workflow**, using version `1.0.1`.
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
git tag nomisma-v1.0.1
git push origin nomisma-v1.0.1
```

The workflow extracts the installer version from the tag. Use a new tag, such as `nomisma-v1.0.2`, for the next release. It publishes only after the Windows build and verification succeed. Ordinary pushes, pull requests, and manual runs produce downloadable Actions artifacts without publishing a release.

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

### Startup fix in 1.0.1

Version 1.0.0 could pause at **Starting Nomisma’s local service…** for 30–60 seconds. Its launcher checked 31 local ports in sequence, making up to two connection attempts per unused port; Windows could wait for each refused connection to time out. Version 1.0.1 checks free ports with a local socket bind, probes only occupied ports concurrently, and bypasses proxy discovery for local health checks.

Startup timings are recorded in `%LOCALAPPDATA%\Nomisma\data\startup.log` (or your configured data folder). Each line records the version, timestamp, success flag, total elapsed milliseconds, and cumulative `backend_ready_ms`, `webview_ready_ms`, and `page_ready_ms` milestones. A missing milestone means that stage was not reached. The log contains no credentials or market data and keeps at most 256 KiB plus one previous file. These timings help identify any delay remaining after the update.

## Build locally

Build prerequisites are Python 3.9+, the .NET 10 SDK, and NSIS 3. The builder works on Windows, macOS, and Linux, and downloads pinned, checksum-verified Windows Python and timezone packages. NuGet restores the pinned WebView2 package.

From the `nomisma` project directory:

```sh
python tools/build_windows.py --version 1.0.1
```

If the build tools are not on PATH, add `--dotnet /path/to/dotnet` and `--makensis /path/to/makensis`. Outputs are placed in `dist/windows/`. The application is self-contained with respect to Python and .NET; WebView2 Runtime is shared with Windows.

To create a new clean source snapshot from this repository:

```sh
python tools/export_source.py
```

To verify a downloaded installer against its release checksum on Windows:

```powershell
Get-FileHash .\Nomisma-1.0.1-win-x64-setup.exe -Algorithm SHA256
```

Compare the result with the matching entry in `SHA256SUMS.txt` from the same release.
