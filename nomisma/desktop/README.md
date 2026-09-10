# Nomisma for macOS

For the Windows 11 Pro installer and GitHub release workflow, see [Nomisma for Windows](WINDOWS.md).

Open **Nomisma.app** in `~/Applications`. The app includes Python and Nomisma's backend, starts the local service when needed, and opens the live monitor in a native macOS window. Terminal and developer tools are not needed to run the finished app.

The workspace build uses this project's existing `data/nomisma.sqlite3` and `.env`. It reuses a healthy server for that database, including an already-running monitor. If another application occupies the default port, it chooses another available loopback port. Opening the app never starts a market monitor automatically.

## Native controls

- **Nomisma → Settings** (`⌘,`) opens source and screener settings.
- **View** switches between the live monitor, daily screener, watchlist, and history. `⌘R` reloads the workspace.
- **Nomisma → Show Research Data in Finder** opens the active data directory. **Open Configuration Folder** opens the folder containing `.env`.
- CSV and backup exports use a native Save dialog; imports use a native file picker.
- **Print report**, or `⌘P` with a report open, uses the macOS print dialog.
- **Desktop alerts** asks for macOS notification permission when clicked. Notifications and sound remain off until enabled, and synthetic alerts remain in the inbox.

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
