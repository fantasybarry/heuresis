# Nomisma implementation contract

Local Python 3.9+ standard-library app. No runtime packages required. UI is vanilla HTML/CSS/JS served from `nomisma/static/`. All paths below are relative to `nomisma/` in the Heuresis repository. This file documents the internal API, not investment methodology.

## Engine (`nomisma/engine.py`)

Expose `DEFAULT_FILTERS`, `PRESETS` (list of `{id,name,description,filters}`), `validate_filters(dict) -> dict` (raise ValueError with useful field error), and `screen(dataset, filters) -> dict`.

Filters: min_price=10, max_price=1000, min_avg_volume=500000, min_relative_volume=1.0, min_rsi=45, max_rsi=75, min_score=55, above_sma50=true, above_sma200=false, positive_macd=false, min_return_20d=0, max_atr_pct=10, sectors=[] (empty means all). All numeric fields finite, sensible bounds and min/max consistency, reject unknown keys. Engine computes RSI14 (Wilder), SMA20/50/200, EMA12/26 and MACD9 signal, ATR14, 20-day return, prior-20-day average volume, relative volume, distance to prior-20-day high and 20-day excess return vs SPY. Require 201 valid unique ordered daily bars. Score 0..100, transparent weighted components; never label score probability. No forward-looking data. Exclude stale symbols compared with latest benchmark or dataset bar date and flag stale overall data (>5 calendar days).

Dataset: `{source:'demo'|'alpaca'|'csv',label,feed,as_of:'YYYY-MM-DD',warnings:[],assets:[{symbol,name,sector,exchange,bars:[{date,open,high,low,close,volume}]}],benchmark:{symbol:'SPY',bars:[...]}}`. Benchmark may be null. Only completed daily sessions from provider; demo must be clearly synthetic with fixed historical date.

Screen returns `{as_of,source,label,feed,warnings,universe_count,eligible_count,matched_count,rejected:{reason:count},results:[{symbol,name,sector,exchange,price,change_pct,score,setup,as_of,metrics:{rsi,relative_volume,avg_volume,sma20,sma50,sma200,macd,macd_signal,macd_histogram,atr,atr_pct,return_20d,relative_strength,breakout_distance},signals:[{name,points,max_points,description}],risks:[str],chart:[{date,close,volume}]}],market:{symbol:'SPY',price,change_pct,return_20d,above_sma50,chart:[{date,close}]}|null,filters}`. Sorted descending score, tie symbol. Engine validation and financial edge-case tests in `tests/test_engine.py`.

## Data (`nomisma/providers.py`)

Expose `provider_status() -> {alpaca_configured:bool,feed:str}`, `demo_dataset() -> dataset`, `parse_csv(text) -> dataset` (validate, max 20MB, headers symbol,date,open,high,low,close,volume; optional name,sector,exchange; SPY benchmark), `fetch_alpaca(universe='curated', symbols=None, progress=None) -> dataset`. `progress(message)` callback optional. `curated` ~50 liquid ticker starter universe, `all` all active tradable NASDAQ/NYSE/AMEX/ARCA equities from assets API, `custom` list of validated tickers. Environment keys `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_FEED` default iex. Credentials stay server-side. GET requests only to fixed Alpaca hosts, timeouts, bounded retries, batching, pagination, split-adjusted daily bars ~450 calendar days history, strict errors without silent demo fallback. Query API calendar for most recent completed session including early closes, 30-minute buffer, no incomplete daily bars. Clearly warn that IEX volume is exchange-specific and all-equities universe may include ETFs. Live network tests optional/mocked tests mandatory. Own provider tests and sample CSV.

## Server API (root implements)

Run with `python3 run.py` (default localhost:8765). Optional `--port`, `--scan`, `--data-dir`. SQLite state under ignored `data/`. Server loads project `.env` if present without overriding existing environment.

GET `/api/bootstrap`: `{settings:{filters,source,universe,symbols,schedule:{enabled,time,timezone}},presets:[{id,name,description,filters}],watchlist:[symbol],latest:scan|null,history:[{id,created_at,source,as_of,matched_count}],job:{running,message,error,scan_id},provider_status:{alpaca_configured,feed,csv_available}}`.

Scan is screen result plus `{id,created_at}`. Initial bootstrap creates and persists demo scan, source explicitly demo. GET `/api/status`: `{job,latest,history}`. An optional `?since=<latest-id>` returns `latest:null` when the latest result is unchanged, reducing polling payloads. GET `/api/scans/<id>`: scan. Custom universes accept at most 1,000 symbols.

POST `/api/scan`: `{filters,source:'demo'|'alpaca'|'csv',universe:'curated'|'all'|'custom',symbols:[...]}` returns `{job}` immediately (202); UI polls `/api/status`. Only one scan runs at once; 409 otherwise. Backend validates before launching. Failed live scan never falls back to demo.

POST `/api/settings`: settings object above, returns `{settings}`. Preserve unspecified top-level fields. Schedule timezone is America/New_York only for now. Time validated HH:MM. Schedule runs once per local weekday once due, with startup catch-up, persists last success date; failed schedules retry with backoff. Requires process running. Schedule source and filters follow saved settings.

POST `/api/watchlist`: `{symbol,enabled:bool}` returns `{watchlist:[...]}`.

POST `/api/presets`: `{name,filters}` returns `{presets:[...]}`; custom preset id persisted. Built-in presets read-only.

POST `/api/import`: `{csv:string}` validates and stores CSV dataset; returns `{asset_count,as_of}`. Follow with scan source csv; settings source may be saved separately.

GET `/api/export.csv?scan=<id>` returns current matching results, CSV escaped and formula-safe.

Errors JSON `{error:string}`. Unknown endpoints 404. UI should show error, loading and empty states. No data/keys via static handler. Mutations accept application/json except the binary restore route, and reject foreign Origin; server bound to loopback.

## Research and workspace extensions

- GET `/api/health`: `{app:'nomisma',status:'ok',version:'2',data_directory}`. The launcher verifies both app identity and data directory before reusing a server.
- POST `/api/diagnostics`: `{}`. Tests the saved monitor configuration. POST `/api/discovery`: `{source,universe,symbols,min_price,max_price,min_day_volume,min_change_pct,limit}`. Both return HTTP 202 `{job:{id,kind,running,message,error,result}}`.
- GET `/api/research/jobs/<id>` returns the same job envelope. One research action runs at a time. At most 32 recent jobs are retained in memory. Restart clears them. A monitor start is refused while a diagnostic is running to avoid competing stream connections.
- Discovery result contains source/feed, request/completion/market timestamps, session date and market phase, universe label, requested/received/current-session/matched/returned/missing/stale/invalid counts, candidate rows, filters, and warnings. Rows carry symbol/name, latest price, day change, feed-day volume, timestamps, trade age, and freshness. Real discovery requires current-session trade/daily dates and the exact previous-session close date. Regular-session trades older than five minutes are excluded. Outside regular hours any retained stale row remains labeled stale.
- GET `/api/history?limit=20&offset=0`: `{history,total,limit,offset}`. GET `/api/monitor/alerts?limit=20&offset=0`: `{alerts,total,limit,offset}`. HTTP pagination accepts limits 1–100 and offsets 0–10000000.
- GET `/api/monitor/alerts/<id>` returns original alert evidence and observed outcomes, with legacy evidence explicitly unavailable. List and monitor SSE results omit the large original config/snapshot/session fields.
- GET `/api/workspace/backup` downloads a consistent SQLite snapshot. POST `/api/workspace/restore` accepts a raw `application/octet-stream` or `application/vnd.sqlite3` body, maximum 128 MB. The monitor, daily scan, and research jobs must be stopped/finished. The app validates the upload and preserves an automatic local safety backup before restoring validated table rows. Returns `{restored:true,backup_path}`. Restored monitor remains stopped; reload UI to reflect restored settings.

## UI (frontend agent owns static files)

Sophisticated high quality light warm-neutral financial research workspace. Dark slim sidebar, green accents, distinctive typography using available system fonts, generous whitespace, precise numeric alignment. Branding: Heuresis platform / Nomisma project. Responsive sidebar, dashboard KPI cards, market context chart, filter panel, ranked stock table with sparkline, selected-stock detail chart and score breakdown. Top nav Dashboard / Watchlist / Scan history / Methodology can be client views. All visible controls work. Source demo banner persistent when demo; data timestamps; no fabricated live metrics. Details of signal weighting read from API signals. Filter editor all filters; presets, save preset, daily schedule, CSV import/export, source selector and universe/custom tickers. Network credentials configured only via .env; connection UI explains concise instructions without asking users to enter secrets into frontend. Keyboard accessible dialogs, labels, focus, native buttons. Use inline SVG for charts/icons, no dependencies or external assets. Document and coordinate any API contract changes.
