/* Intraday monitoring is deliberately independent of the completed daily screener. */
(() => {
  "use strict";
  const q = (selector, parent = document) => parent.querySelector(selector);
  const numberFormats = new Map();
  const compactFormat = new Intl.NumberFormat("en-US", {notation:"compact", maximumFractionDigits:2});
  const timeFormats = [false, true].map((full) => new Intl.DateTimeFormat("en-US", {timeZone:"America/New_York", ...(full ? {month:"short", day:"numeric", year:"numeric"} : {}), hour:"numeric", minute:"2-digit", second:"2-digit"}));
  const n = (value, digits = 0) => {
    if (!numeric(value)) return "—";
    if (!numberFormats.has(digits)) numberFormats.set(digits, new Intl.NumberFormat("en-US", {maximumFractionDigits:digits, minimumFractionDigits:digits}));
    return numberFormats.get(digits).format(value);
  };
  const short = (value) => numeric(value) ? compactFormat.format(value) : "—";
  const dollars = (value) => numeric(value) ? `$${n(value, value < 1 ? 4 : 2)}` : "—";
  const pct = (value) => numeric(value) ? `${value > 0 ? "+" : ""}${n(value, 2)}%` : "—";
  const ratio = (value) => numeric(value) ? `${n(value, 2)}×` : "—";
  const direction = (value) => numeric(value) && value < 0 ? "negative" : numeric(value) && value > 0 ? "positive" : "neutral";
  const clock = (value, full = false) => {
    if (!value) return "Unavailable";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Unavailable";
    return timeFormats[full ? 1 : 0].format(date) + " ET";
  };
  const date = (value) => value ? escapeHTML(String(value).slice(0, 10)) : "Unavailable";
  const symbolList = (value) => [...new Set(String(value).toUpperCase().split(/[\s,;]+/).filter(Boolean))];
  const sourceLabel = (source, feed) => source === "demo" ? "Synthetic demo" : `Alpaca · ${String(feed || "market data").toUpperCase()}`;
  const setup = (level) => level === "Strong buy" ? "Strong buy setup" : level === "Buy" ? "Buy setup" : "Watch";
  const levelClass = (level) => level === "Strong buy" ? "strong" : level === "Buy" ? "buy" : "watch";
  const unavailable = "Unavailable: the provider has not supplied a usable value or enough history.";
  const view = {
    snapshot:null, selected:null, sort:"signal_score", query:"", events:null, pollTimer:null,
    retryTimer:null, fetching:false, receivedAt:0, transport:"connecting", action:false,
    baseline:false, alertSource:null, seen:new Set(), freshSince:Date.now(), alertsKey:"", detailKey:"",
    notifications:false, notificationMessage:"", sound:false, audio:null, extraColumns:false,
    journal:{offset:0, limit:20, total:0, alerts:[], busy:false}, savedAlert:null,
    discovery:null, candidateSort:"liquidity_volatility_score", candidates:new Set(), discoveryBusy:false, diagnosticsBusy:false,
    discoverySettings:null, discoveryStatus:null, discoveryResultId:null, discoveryPolling:false,
    discoveryTimer:null, manualDiscovery:false, scheduleBusy:false, discoveryLoading:false,
    selectedDetail:null, detailFetching:false, detailReceivedAt:0, tableKey:"", refreshing:false,
    alertsRefreshing:false, alertRefreshMessage:"", focus:null, focusDetail:null, focusFetching:false, focusTf:"1Min", focusCandles:null, pulse:null, pulseError:"", candleTf:"5Min", candles:null, candleFetching:false, candleZoom:120, candleOffset:0, candleScale:1, candleDrag:null, candleFull:false
  };
  const candleFrames = [["1Min", "1m", 60e3], ["5Min", "5m", 300e3], ["15Min", "15m", 900e3], ["1Hour", "1h", 3600e3], ["1Day", "1D", 0]];
  const nyClock = new Intl.DateTimeFormat("en-US", {timeZone:"America/New_York", hour:"2-digit", minute:"2-digit", hourCycle:"h23"});
  const nySeconds = new Intl.DateTimeFormat("en-US", {timeZone:"America/New_York", hour:"2-digit", minute:"2-digit", second:"2-digit", hourCycle:"h23"});
  const sessionFill = {pre:"#d6e4f5", post:"#f6dfbf"}, sessionName = {pre:"Pre-market", post:"After-hours"};
  // Intraday bars are labeled by their start time in New York: before 9:30 is pre-market, 16:00 on is after-hours.
  const barSession = (t) => { const [h, m] = nyClock.format(new Date(t)).split(":").map(Number); return h * 60 + m < 570 ? "pre" : h >= 16 ? "post" : ""; };
  const candleTime = new Intl.DateTimeFormat("en-US", {timeZone:"America/New_York", month:"short", day:"numeric", hour:"numeric", minute:"2-digit"});
  const nyDay = (value) => new Date(value).toLocaleDateString("en-CA", {timeZone:"America/New_York"});
  const screeningSortOptions = [
    ["liquidity_volatility_score", "Liquidity & volatility rank"], ["day_volume", "Total day volume"],
    ["avg_volume_3m", "Average volume (3M)"], ["avg_daily_volume", "Average daily volume (20D)"],
    ["day_relative_volume", "Day relative volume"], ["spread_pct", "Bid–ask spread (%)"],
    ["beta", "Beta vs SPY"], ["atr", "Average true range ($)"], ["atr_pct", "Average true range (%)"]
  ];
  const sortOptions = (extra = []) => [...screeningSortOptions, ...extra].map(([key, label]) => `<option value="${key}">${label}</option>`).join("");
  function compareRows(key) {
    return (a, b) => {
      if (key === "symbol") return a.symbol.localeCompare(b.symbol);
      const left = numeric(a[key]), right = numeric(b[key]);
      if (left !== right) return left ? -1 : 1;
      return (left ? b[key] - a[key] : 0) || a.symbol.localeCompare(b.symbol);
    };
  }
  const symbolLimit = () => view.snapshot?.limits?.max_symbols || 50;
  // Older local services may return every source's saved history in a snapshot.
  const currentAlerts = (snapshot = view.snapshot) => (snapshot?.alerts || []).filter((item) => item.source === snapshot?.config.source);
  const markupCache = new WeakMap();
  function replaceMarkup(selector, markup) {
    const element = q(selector);
    if (markupCache.get(element) === markup) return false;
    markupCache.set(element, markup);
    element.innerHTML = markup;
    return true;
  }

  function mount() {
    q("#live-view").innerHTML = `
      <div id="live-error" class="alert error hidden" role="alert"></div>
      <div id="live-announcement" class="sr-only" role="status" aria-live="polite" aria-atomic="true"></div>
      <section class="live-pulse" aria-labelledby="live-pulse-title"><div class="live-pulse-heading"><h2 id="live-pulse-title">Market pulse</h2><span id="live-pulse-summary"></span><small id="live-pulse-note">Loading index ETFs and market movers…</small></div><div id="live-pulse"></div></section>
      <div class="live-workspace">
        <section class="live-market-panel" aria-labelledby="live-radar-title">
          <div class="live-panel-heading"><div><h2 id="live-radar-title">Momentum radar</h2><p id="live-radar-summary">Your intraday rules, in real time.</p></div><div class="live-radar-actions"><label class="live-search"><span class="sr-only">Search radar symbols</span><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg><input id="live-search" type="search" placeholder="Symbol"></label><label class="live-sort"><span>Sort</span><select id="live-sort">${sortOptions([["signal_score","Setup score"],["minute_relative_volume","1-minute RVOL"],["change_pct","Day change"],["gap_pct","Opening gap"],["session_volume","Regular-session volume"],["symbol","Symbol A–Z"]])}</select></label></div></div>
          <div class="live-rule-chips"><span id="live-filter-summary"></span><button type="button" class="text-button" id="live-edit-rules">Edit rules</button></div>
          <div id="live-table" class="live-table-scroll" tabindex="0" aria-label="Live stock metrics"></div>
          <div class="live-table-footer"><span id="live-ranking-note">Auto-scan replaces the radar every 5 minutes until the 4:00 p.m. close.</span><span>Technicals use completed 1-minute bars · total day volume includes premarket</span></div>
          <div id="live-warnings" class="live-warnings hidden"></div>
          <details class="live-definitions"><summary>Read the numbers</summary><div><p><strong>Total day volume</strong> includes the provider’s available premarket and regular-session trading; it continues through available after-hours trading. It does not reset at the opening bell. Volumes reflect the selected feed’s coverage.</p><p><strong>Average volume (3M)</strong> uses 63 prior trading sessions. <strong>Average daily volume (20D)</strong> uses 20 prior sessions. Both exclude today. <strong>Day RVOL</strong> is total day volume ÷ the 20-session average; it is not adjusted for time of day.</p><p><strong>Bid–ask spread</strong> shows ask minus bid in dollars and as a percentage of their midpoint. A narrower spread earns more liquidity points. Quotes older than 30 seconds are unavailable for screening.</p><p><strong>Beta</strong> estimates sensitivity to SPY using up to 252 paired daily price returns, with at least 60 required. <strong>ATR (14)</strong> uses Wilder’s average true range of completed daily bars. ATR% divides it by the prior close so different stock prices can be compared.</p><p><strong>Regular-session volume</strong> uses completed regular-session minutes. <strong>Session VWAP</strong> runs from the 4 a.m. pre-market open, so completed pre-market minutes count too. <strong>1-minute RVOL</strong> is the latest completed minute’s volume ÷ the preceding 20-minute average and drives the minute-volume alert filter.</p><p><strong>30D avg / total</strong> use 30 prior sessions. <strong>Session RVOL</strong> compares regular-session volume with that full-session average. <strong>Gap</strong> compares the regular-session opening price with the prior adjusted close. <strong>Float</strong> is sourced and dated separately. A dash means unavailable.</p></div></details>
        </section>
        <aside class="live-alert-rail" aria-label="Selected stock and setup alerts">
          <section class="live-focus" id="live-focus" aria-label="Selected stock"></section>
          <section class="live-alert-panel" aria-labelledby="live-alerts-title"><div class="live-alert-head"><div><h2 id="live-alerts-title">Setup alerts</h2><span class="live-new-pill"><span id="live-alert-count">0</span> new</span></div><div class="live-alert-actions"><button class="text-button" id="live-alert-refresh" type="button" disabled aria-label="Refresh setup alerts" aria-busy="false">Refresh</button><button class="text-button" id="live-ack-all" disabled>Mark read</button></div></div><div id="live-alerts" class="live-alert-list" aria-label="Recent saved alerts"></div><p id="live-alert-refresh-status" class="live-alert-note" role="status" aria-live="polite">Saved setups retain their original price and score.</p><p class="live-alert-note">Buy and Strong buy describe technical setups, not orders or a probability of profit. <button class="text-button" id="live-journal" type="button">Open journal</button></p></section>
        </aside>
      </div>`;

    document.body.insertAdjacentHTML("beforeend", `
      <dialog id="live-config-dialog" class="modal live-config-modal" aria-labelledby="live-config-title"><form id="live-config-form">
        <div class="modal-header"><div><div class="eyebrow">YOUR INTRADAY PLAYBOOK</div><h2 id="live-config-title">Configure momentum monitor</h2><p>Watch up to 50 symbols with independent intraday rules.</p></div><button class="icon-button" type="button" data-live-close aria-label="Close monitor configuration">✕</button></div>
        <div class="modal-body"><div id="live-config-running" class="live-form-note hidden">Stop the monitor to edit its source, symbols, or rules.</div><fieldset id="live-config-fields">
          <div class="live-form-section"><h3>Market data & symbols</h3><label>Source<select id="live-source" name="source"><option value="demo">Synthetic demo · simulated penny stocks</option><option value="alpaca">Alpaca · real-time trade and quote stream</option></select></label><div id="live-provider-help" class="live-form-note"></div><label>Stock symbols<textarea id="live-symbols" name="symbols" rows="2" required placeholder="ABCD, EFGH, IJKL" aria-describedby="live-symbol-help"></textarea><span class="field-help" id="live-symbol-help">Up to 50 symbols, separated by commas or spaces. Listed US equities; OTC coverage is not available.</span></label><div class="live-import-buttons"><button type="button" class="button subtle" id="live-use-watchlist">Use watchlist</button><button type="button" class="button subtle" id="live-use-scan">Use latest scan’s top 50</button></div><p id="live-import-note" class="field-help" role="status"></p></div>
          <div class="live-form-section"><h3>Penny-stock liquidity filters</h3><div class="live-form-grid"><label>Minimum price ($)<input name="min_price" type="number" min="0.0001" max="1000000" step="any" required></label><label>Maximum price ($)<input name="max_price" type="number" min="0.0001" max="1000000" step="any" required></label><label>Minimum regular-session volume<input name="min_session_volume" type="number" min="0" step="1" required><span class="field-help">Excludes premarket; counts from 9:30 a.m. ET</span></label></div></div>
          <div class="live-form-section"><h3>Technical setup alerts</h3><div class="live-form-grid"><label>Buy setup score<input name="buy_score" type="number" min="0" max="99" step="any" required></label><label>Strong buy setup score<input name="strong_buy_score" type="number" min="1" max="100" step="any" required></label><label>Confirmation bars<input name="confirmation_bars" type="number" min="1" max="5" step="1" required><span class="field-help">Consecutive completed 1-minute bars</span></label><label>Cooldown (seconds)<input name="cooldown_seconds" type="number" min="30" max="3600" step="1" required><span class="field-help">Strong buy upgrades can alert sooner</span></label></div><label class="live-check"><input name="alerts_enabled" type="checkbox">Enable saved in-app setup alerts</label><p class="live-form-note">Both setup levels require price above session VWAP, EMA trend alignment, sufficient 1-minute relative volume, and valid market data. Scores are explainable technical heuristics.</p></div>
        </fieldset><div id="live-config-error" class="alert error hidden" role="alert"></div></div><div class="modal-footer"><span class="field-help">Saved locally. Start monitoring explicitly.</span><div><button type="button" class="button subtle" data-live-close>Cancel</button><button id="live-save-config" class="button primary" type="submit">Save configuration</button></div></div>
      </form></dialog>
      <dialog id="live-report-dialog" class="modal live-report-modal" aria-labelledby="live-report-title"><div class="live-report-header"><div><div class="eyebrow">INTRADAY STOCK REPORT</div><h2 id="live-report-title">Stock details</h2></div><div><button class="button subtle" id="live-print">Print report</button><button class="icon-button" data-live-close aria-label="Close stock report">✕</button></div></div><div id="live-report-error" class="alert error hidden" role="alert"></div><div id="live-report-data"></div><div class="live-float-edit" id="live-float-edit"><details><summary>Add or update a dated float value</summary><p>Use actual publicly available float shares from a source you have checked. This is saved as a manual value and overrides optional provider float data.</p><form id="live-float-form"><div class="live-form-grid"><label>Float shares<input id="live-float-shares" name="shares" type="number" min="1" max="10000000000000" step="1" required></label><label>Source date<input id="live-float-date" name="as_of" type="date" required></label></div><div class="live-float-actions"><button class="button primary" type="submit">Save manual float</button><button class="button subtle" id="live-clear-float" type="button">Clear manual override</button></div><div id="live-float-error" class="alert error hidden" role="alert"></div><p id="live-float-saved" class="field-help" role="status"></p></form></details></div></dialog>`);
  }

  function mountResearch() {
    const dialog = (id, title, subtitle, body, footer = "") => `<dialog id="${id}" class="modal live-research-modal" aria-labelledby="${id}-title"><div class="modal-header"><div><div class="eyebrow">RESEARCH WORKSPACE</div><h2 id="${id}-title">${title}</h2><p>${subtitle}</p></div><button type="button" class="icon-button" data-live-close aria-label="Close ${title}">✕</button></div><div class="modal-body">${body}</div>${footer ? `<div class="modal-footer">${footer}</div>` : ""}</dialog>`;
    document.body.insertAdjacentHTML("beforeend", [
      dialog("live-diagnostics-dialog", "Market data diagnostics", "Test authentication, feed access, subscriptions, and data readiness.", '<p id="live-diagnostics-progress" class="live-form-note" role="status"></p><div id="live-diagnostics-error" class="alert error hidden" role="alert"></div><div id="live-diagnostics-result"></div>', '<span class="field-help">A test uses your current saved monitor source and symbols.</span><button id="live-retest" class="button primary">Run test again</button>'),
      dialog("live-discovery-dialog", "Find intraday candidates", "Find the highest-volume stocks for your radar.", `<form id="live-discovery-form"><fieldset id="live-discovery-fields"><div class="live-form-grid"><label>Source<select name="source" id="live-discovery-source"><option value="demo">Synthetic demo</option><option value="alpaca">Alpaca</option></select></label><label>Universe<select name="universe" id="live-discovery-universe"><option value="curated">Liquid US stocks · starter list</option><option value="all">All verified US-listed stocks</option><option value="custom">Custom symbols</option></select></label></div><label id="live-discovery-custom" class="hidden">Symbols<textarea name="symbols" rows="2" placeholder="AAPL, NVDA, SOFI"></textarea></label><div class="live-form-grid"><label>Minimum price ($)<input name="min_price" type="number" min="0" step="any" value="0" required></label><label>Maximum price ($)<input name="max_price" type="number" min="0.0001" step="any" value="1000" required></label><label>Minimum regular-session volume<input name="min_day_volume" type="number" min="0" step="1" value="0" required></label><label>Minimum day change (%)<input name="min_change_pct" type="number" min="-100" step="any" value="-100" required></label><label>Maximum candidates<input name="limit" type="number" min="1" max="500" step="1" value="100" required></label></div><p class="field-help">Lenient filters keep symbols available for comparison. The volume minimum counts regular-session trading from 9:30 a.m. ET; premarket is excluded. Results are ranked by total day volume, highest first.</p><button type="submit" class="button primary">Find candidates</button></fieldset></form><section class="live-schedule-card" aria-labelledby="live-schedule-title"><div><h3 id="live-schedule-title">Scheduled candidate search</h3><p>Use the source, universe, and filters above. Repeats every 5 minutes until the 4 p.m. close.</p></div><form id="live-schedule-form"><label class="live-check"><input id="live-schedule-enabled" type="checkbox">Search automatically on weekdays</label><div class="live-schedule-controls"><label>New York time<input id="live-schedule-time" type="time" value="09:15" required></label><button id="live-save-schedule" class="button subtle" type="submit">Save schedule & filters</button></div><p id="live-schedule-status" class="field-help" role="status"></p><p class="field-help">Keep Nomisma open and your computer awake. New York time follows daylight saving time. Each completed search replaces the radar with its top 50 stocks and restarts an active monitor.</p><div id="live-schedule-error" class="alert error hidden" role="alert"></div></form></section><p id="live-discovery-progress" class="live-form-note hidden" role="status"></p><div id="live-discovery-error" class="alert error hidden" role="alert"></div><div id="live-discovery-result"></div>`, '<span id="live-candidate-selection" class="field-help" role="status">Choose up to 50 candidates.</span><button id="live-use-candidates" class="button primary" disabled>Save selected symbols</button>'),
      dialog("live-evidence-dialog", "Saved alert evidence", "Original settings and market data are preserved at the time of the alert.", '<div id="live-evidence-error" class="alert error hidden" role="alert"></div><div id="live-evidence-result"></div>', '<span class="field-help">Outcomes are observed market prices, not simulated fills.</span><button id="live-evidence-refresh" class="button subtle">Refresh outcomes</button>')
    ].join(""));
    q("#journal-view").innerHTML = `<section class="panel live-journal-panel"><div id="live-journal-error" class="alert error hidden" role="alert"></div><dl id="live-journal-stats" class="live-journal-stats"></dl><div id="live-journal-results"></div><div class="table-footer"><span id="live-journal-page" role="status"></span><div class="history-page-actions"><button id="live-journal-prev" class="button subtle">Previous</button><button id="live-journal-next" class="button subtle">Next</button></div></div></section>`;
  }
  async function researchJob(path, body, onProgress) {
    let {job} = await api(path, body);
    for (;;) {
      if (!job) throw new Error("The server did not return a research job.");
      onProgress(job.message || "Reading market data…", job);
      if (!job.running) {
        if (job.error) throw new Error(job.error);
        return job.result;
      }
      await new Promise((resolve) => setTimeout(resolve, 1000));
      ({job} = await api(`/api/research/jobs/${encodeURIComponent(job.id)}`));
    }
  }
  async function diagnose() {
    openDialog(q("#live-diagnostics-dialog"), "#live-retest");
    if (view.diagnosticsBusy) return;
    view.diagnosticsBusy = true;
    q("#live-retest").disabled = true;
    showError("#live-diagnostics-error", "");
    q("#live-diagnostics-result").innerHTML = "";
    try {
      const data = await researchJob("/api/diagnostics", {}, (message) => { q("#live-diagnostics-progress").textContent = message; });
      q("#live-diagnostics-progress").textContent = `${sourceLabel(data.source, data.feed)} · tested ${clock(data.checked_at, true)}`;
      q("#live-diagnostics-result").innerHTML = `<div class="live-diagnostic-checks">${(data.checks || []).map((check) => `<article><span class="live-diagnostic-status ${escapeHTML(check.status)}">${escapeHTML(check.status)}</span><div><h3>${escapeHTML(check.name)}</h3><p>${escapeHTML(check.message)}</p></div></article>`).join("")}</div><h3>Symbol readiness</h3><div class="live-table-scroll"><table class="live-history-table"><thead><tr><th>Symbol</th><th>Trade / quote (ET)</th><th>Last minute</th><th>Daily history</th><th>Issues</th></tr></thead><tbody>${(data.symbols || []).map((row) => `<tr><td><strong>${escapeHTML(row.symbol)}</strong></td><td>${clock(row.trade_at)}<br>${clock(row.quote_at)}</td><td>${clock(row.minute_at)}</td><td>${n(row.history_sessions)} sessions${row.missing_history ? `<br>${row.missing_history === true ? "Incomplete baseline" : escapeHTML(Array.isArray(row.missing_history) ? row.missing_history.join(", ") : row.missing_history) + " missing"}` : ""}</td><td>${escapeHTML((row.issues || []).join(" · ") || "None reported")}</td></tr>`).join("")}</tbody></table></div>${warningList(data.warnings)}`;
    } catch (error) { showError("#live-diagnostics-error", error.message); q("#live-diagnostics-progress").textContent = "Test did not complete."; }
    finally { view.diagnosticsBusy = false; q("#live-retest").disabled = false; }
  }
  function warningList(warnings) {
    return warnings?.length ? `<div class="live-form-note"><ul>${warnings.map((warning) => `<li>${escapeHTML(warning)}</li>`).join("")}</ul></div>` : "";
  }
  function readDiscovery() {
    const fields = q("#live-discovery-form").elements;
    const payload = {source:fields.source.value, universe:fields.universe.value, symbols:symbolList(fields.symbols.value)};
    for (const key of ["min_price", "max_price", "min_day_volume", "min_change_pct", "limit"]) payload[key] = Number(fields[key].value);
    if (payload.min_price > payload.max_price) throw new Error("Minimum price cannot exceed maximum price.");
    if (payload.universe === "custom" && !payload.symbols.length) throw new Error("Enter at least one symbol for a custom universe.");
    return payload;
  }
  const screeningKeys = ["day_volume", "avg_volume_3m", "avg_daily_volume", "day_relative_volume", "spread_pct", "beta", "atr"];
  function screeningHeaders(keys = screeningKeys) {
    const headers = {day_volume:'<th class="live-num" title="Includes available premarket trading; does not reset at the open">Total day vol.</th>', avg_volume_3m:'<th class="live-num" title="63 prior trading sessions, excluding today">Avg vol (3M)</th>', avg_daily_volume:'<th class="live-num" title="20 prior trading sessions, excluding today">Avg daily vol (20D)</th>', day_relative_volume:'<th class="live-num" title="Total day volume divided by 20-session average; not time adjusted">Day RVOL</th>', spread_pct:'<th class="live-num">Bid–ask spread</th>', beta:'<th class="live-num" title="Up to 252 daily price returns vs SPY; minimum 60 paired observations">Beta</th>', atr:'<th class="live-num" title="Wilder 14-session average true range, in dollars and percent of prior close">ATR (14)</th>'};
    return keys.map((key) => headers[key]).join("");
  }
  function screeningCells(row, keys = screeningKeys) {
    const cell = (key, label, content, title) => `<td class="live-num" data-metric="${key}" data-label="${label}" title="${escapeHTML(numeric(row[key]) ? title : unavailable)}">${content}</td>`;
    const volumeNote = row.day_volume_fresh === false && numeric(row.day_volume) ? "Stale volume" : row.volume_partial || row.day_volume_partial ? "Partial volume" : "";
    const volumeTitle = `Includes available premarket volume: ${n(row.day_volume)} shares.${row.day_volume_fresh === false ? " Stale volume earns no volume or day RVOL ranking points." : ""}${row.volume_basis === "completed_extended_minutes" ? ` Completed minutes through ${clock(row.volume_at)}; partial total may undercount.` : ""}`;
    const cells = {
      day_volume: () => cell("day_volume", "Total day volume", `${short(row.day_volume)}${volumeNote ? `<small>${volumeNote}</small>` : ""}`, volumeTitle),
      avg_volume_3m: () => cell("avg_volume_3m", "Avg vol (3M)", short(row.avg_volume_3m), `63 prior sessions: ${n(row.avg_volume_3m)} shares/day`),
      avg_daily_volume: () => cell("avg_daily_volume", "Avg daily vol (20D)", short(row.avg_daily_volume), `20 prior sessions: ${n(row.avg_daily_volume)} shares/day`),
      day_relative_volume: () => cell("day_relative_volume", "Day RVOL", ratio(row.day_relative_volume), `Total day volume / 20-session average: ${ratio(row.day_relative_volume)}; not time adjusted`),
      spread_pct: () => cell("spread_pct", "Bid–ask spread", `${dollars(row.spread)}<small>${numeric(row.spread_pct) ? n(row.spread_pct, 2) + "%" : "—"}</small>`, `Ask minus bid; ${n(row.spread_pct, 4)}% of midpoint; quote ${clock(row.quote_at)}`),
      beta: () => cell("beta", "Beta vs SPY", n(row.beta, 2), `Daily price-return beta vs SPY, ${n(row.beta_observations)} paired returns`),
      atr: () => cell("atr", "ATR (14)", `${dollars(row.atr)}<small data-metric="atr_pct">${numeric(row.atr_pct) ? n(row.atr_pct, 2) + "%" : "—"}</small>`, `Wilder ATR14; ${n(row.atr_pct, 2)}% of prior close`)
    };
    return keys.map((key) => cells[key]()).join("");
  }
  function renderCandidateTable() {
    const rows = [...(view.discovery?.rows || [])].sort(compareRows(view.candidateSort));
    const wrapper = q("#live-candidate-table-wrapper");
    if (!wrapper) return;
    wrapper.innerHTML = `<table class="live-history-table live-candidate-table"><thead><tr><th>Select / symbol</th><th class="live-num">Price / day</th>${screeningHeaders()}<th>Data freshness</th></tr></thead><tbody>${rows.map((row) => `<tr><td><label class="live-candidate-choice"><input type="checkbox" data-live-candidate="${escapeHTML(row.symbol)}" aria-label="Select ${escapeHTML(row.symbol)}" ${view.candidates.has(row.symbol) ? "checked" : ""}><span><strong>${escapeHTML(row.symbol)}</strong><small>${escapeHTML(row.name || "")}</small></span></label></td><td class="live-num">${dollars(row.price)}<small class="${direction(row.change_pct)}">${pct(row.change_pct)}</small></td>${screeningCells(row)}<td>${escapeHTML(row.freshness || "Unavailable")}<small>${clock(row.trade_at)}</small>${row.volume_basis ? `<small>${escapeHTML(row.volume_basis.replaceAll("_", " "))}</small>` : ""}</td></tr>`).join("")}</tbody></table>`;
    candidateSelection();
  }
  function rankingDetails(ranking) {
    // Weights come from the search result, so the explanation always matches the ranking that produced it.
    const labels = {...Object.fromEntries(screeningSortOptions), spread_pct:"Bid–ask spread (%) · narrower earns more", beta:"Beta vs SPY · positive earns more"};
    const weights = Object.entries(ranking?.weights || {});
    return `<details class="live-ranking-details"><summary>How the liquidity &amp; volatility rank works</summary><p>Each stock earns points for where each metric falls within this group${numeric(ranking?.pool_limit) ? ` of up to ${n(ranking.pool_limit)} stocks` : ""}. Missing metrics earn zero; the stock stays visible. ${ranking?.benchmark ? `Beta is measured against ${escapeHTML(ranking.benchmark)}. ` : ""}The rank favors activity and volatility. It does not predict direction or returns.</p>${weights.length ? `<ul>${weights.map(([key, weight]) => `<li><span>${escapeHTML(labels[key] || key)}</span><strong>${n(weight)} pts</strong></li>`).join("")}</ul>` : ""}</details>`;
  }
  function renderDiscovery(data) {
    q("#live-discovery-progress").classList.remove("hidden");
    const coverage = data.coverage || {};
    q("#live-discovery-progress").textContent = `${sourceLabel(data.source, data.feed)} · ${data.universe_label || data.universe} · refreshed ${clock(data.as_of, true)} · market clock ${clock(data.market_as_of, true)} · session ${data.session_date || "unavailable"} · ${data.market_phase || ""}`;
    q("#live-discovery-result").innerHTML = `<p class="live-coverage">${n(coverage.requested)} requested · ${n(coverage.received)} received · ${n(coverage.current_session)} current-session · ${n(coverage.matched)} matched · ${n(coverage.returned)} returned<br>${n(coverage.missing)} missing · ${n(coverage.stale)} stale · ${n(coverage.invalid)} invalid</p>${warningList(data.warnings)}${data.rows?.length && !data.rows.some((row) => numeric(row.liquidity_volatility_score)) ? '<p class="live-form-note">These saved candidates predate the liquidity and volatility metrics. Click Find candidates to calculate a fresh ranking.</p>' : ""}${data.rows?.length ? rankingDetails(data.ranking) : ""}${data.rows?.length ? `<div class="live-candidate-toolbar"><label class="live-sort">Sort by<select id="live-candidate-sort">${sortOptions([["change_pct","Day change"],["symbol","Symbol A–Z"]])}</select></label><span>Highest to lowest · unavailable values last</span></div><div id="live-candidate-table-wrapper" class="live-table-scroll" tabindex="0" aria-label="Candidate liquidity and volatility metrics"></div>` : '<div class="live-alert-empty"><h3>No candidates match these filters</h3><p>Adjust the price, volume or day-change limits, or choose another universe.</p></div>'}`;
    if (q("#live-candidate-sort")) q("#live-candidate-sort").value = view.candidateSort;
    renderCandidateTable();
  }
  function renderSchedule() {
    const saved = view.discoverySettings, status = view.discoveryStatus || saved?.status;
    if (!saved) return;
    const schedule = saved.schedule;
    const summary = schedule.enabled ? `Weekdays at ${schedule.time} New York time` : "Candidate schedule is off";
    const last = status?.last_run;
    const lastText = last?.error ? `Last search failed: ${last.error}` : last ? `Last search ${clock(last.completed_at || last.started_at, true)}` : "No scheduled search yet.";
    const nextText = status?.running ? "Finding candidates now…" : status?.next_due ? `Next search ${clock(status.next_due, true)}` : "Enable the schedule to search automatically.";
    q("#live-schedule-summary").textContent = status?.running ? "Candidate search running…" : summary;
    q("#live-schedule-status").textContent = `${nextText} ${lastText}`;
    if (last?.error && !status.running && !view.manualDiscovery) {
      showError("#live-discovery-error", `The latest search failed: ${last.error} Any candidates below are from the previous successful search; check their timestamp.`);
      if (view.discovery) renderDiscovery(view.discovery);
    }
    q("#live-save-schedule").disabled = view.scheduleBusy || view.discoveryLoading;
    q("#live-save-schedule").textContent = view.scheduleBusy ? "Saving…" : "Save schedule & filters";
  }
  function applyDiscoveryJob(job) {
    if (!job) return;
    if (job.running) {
      q("#live-discovery-progress").classList.remove("hidden");
      q("#live-discovery-progress").textContent = job.message || "Finding candidates…";
    } else if (job.result && job.id !== view.discoveryResultId) {
      showError("#live-discovery-error", "");
      view.discoveryResultId = job.id;
      view.discovery = job.result;
      view.candidates.clear();
      renderDiscovery(job.result);
    }
    candidateSelection();
  }
  async function loadDiscoverySettings(applyForm = false) {
    const saved = await api("/api/discovery/settings");
    view.discoverySettings = saved;
    view.discoveryStatus = saved.status;
    if (applyForm) {
      const fields = q("#live-discovery-form").elements;
      for (const [key, value] of Object.entries(saved.config || {})) {
        if (fields[key]) fields[key].value = Array.isArray(value) ? value.join(", ") : value;
      }
      q("#live-discovery-custom").classList.toggle("hidden", fields.universe.value !== "custom");
      q("#live-schedule-enabled").checked = saved.schedule.enabled;
      q("#live-schedule-time").value = saved.schedule.time;
    }
    applyDiscoveryJob(saved.latest);
    applyDiscoveryJob(saved.job);
    renderSchedule();
    return saved;
  }
  async function showDiscovery() {
    openDialog(q("#live-discovery-dialog"), "#live-discovery-source");
    if (view.discoveryLoading || view.manualDiscovery) return;
    view.discoveryLoading = true;
    candidateSelection();
    showError("#live-schedule-error", "");
    try { await loadDiscoverySettings(true); }
    catch (error) { showError("#live-schedule-error", `Cannot load saved search settings: ${error.message}`); }
    finally { view.discoveryLoading = false; candidateSelection(); renderSchedule(); }
  }
  async function saveSchedule(event) {
    event.preventDefault();
    if (view.scheduleBusy) return;
    view.scheduleBusy = true;
    showError("#live-schedule-error", "");
    renderSchedule();
    try {
      view.discoverySettings = await api("/api/discovery/settings", {config:readDiscovery(), schedule:{enabled:q("#live-schedule-enabled").checked, time:q("#live-schedule-time").value, timezone:"America/New_York"}});
      view.discoveryStatus = view.discoverySettings.status;
      q("#live-announcement").textContent = "Candidate schedule and filters saved.";
    } catch (error) { showError("#live-schedule-error", error.message); }
    finally { view.scheduleBusy = false; renderSchedule(); }
  }
  async function pollDiscovery() {
    clearTimeout(view.discoveryTimer);
    if (view.discoveryPolling) return;
    view.discoveryPolling = true;
    try {
      if (!document.hidden && !view.manualDiscovery) {
        if (!view.discoverySettings) await loadDiscoverySettings(false);
        else {
          const data = await api("/api/discovery/latest");
          view.discoveryStatus = data.status;
          applyDiscoveryJob(data.job);
          renderSchedule();
        }
      }
    } catch (error) {
      q("#live-schedule-summary").textContent = "Candidate schedule status unavailable";
    } finally {
      view.discoveryPolling = false;
      view.discoveryTimer = setTimeout(pollDiscovery, view.discoveryStatus?.running ? 2000 : 30000);
    }
  }
  async function discover(event) {
    event.preventDefault();
    if (view.discoveryBusy || view.discoveryLoading || view.discoveryStatus?.running) return;
    showError("#live-discovery-error", "");
    let payload;
    try { payload = readDiscovery(); }
    catch (error) { showError("#live-discovery-error", error.message); return; }
    view.discoveryBusy = view.manualDiscovery = true;
    view.discovery = null;
    view.candidates.clear();
    q("#live-discovery-result").innerHTML = "";
    q("#live-discovery-progress").classList.remove("hidden");
    candidateSelection();
    try {
      view.discovery = await researchJob("/api/discovery", payload, (message, job) => {
        q("#live-discovery-progress").textContent = message;
        view.discoveryResultId = job.id;
      });
      renderDiscovery(view.discovery);
    } catch (error) { showError("#live-discovery-error", error.message); q("#live-discovery-progress").textContent = "Discovery did not complete."; }
    finally {
      view.discoveryBusy = view.manualDiscovery = false;
      view.discoveryStatus = null;
      candidateSelection();
      await pollDiscovery();
    }
  }
  async function scanRadar() {
    if (view.discoveryBusy || view.discoveryLoading || view.discoveryStatus?.running) return;
    const note = q("#live-ranking-note"), noteText = note.textContent;
    view.discoveryBusy = true;
    showError("#live-error", "");
    render();
    try {
      const {config} = view.discoverySettings || await loadDiscoverySettings(false);
      const result = await researchJob("/api/discovery", config, (message) => { note.textContent = message; });
      // The server has already saved the matches as the radar's symbols and restarted an active monitor.
      if (!result?.rows?.length) throw new Error("No stocks meet your candidate search filters right now. Adjust them in Find candidates.");
      if (view.snapshot?.status.running) await fetchSnapshot(); else await setRunning(true);
      q("#live-announcement").textContent = `${Math.min(result.rows.length, symbolLimit())} qualified stocks loaded into the radar.`;
    } catch (error) { showError("#live-error", error.message); }
    finally {
      view.discoveryBusy = false;
      view.discoveryStatus = null;
      note.textContent = noteText;
      render();
      pollDiscovery();
    }
  }
  function candidateSelection() {
    const running = !!view.snapshot?.status.running;
    const busy = view.discoveryBusy || view.discoveryLoading || !!view.discoveryStatus?.running;
    q("#live-discovery-fields").disabled = busy;
    q("#live-candidate-selection").textContent = `${view.candidates.size} of ${symbolLimit()} selected. ${running ? "Stop the monitor before saving a new selection." : "Saving replaces monitor symbols and source. Start monitoring explicitly."}`;
    q("#live-use-candidates").disabled = !view.candidates.size || running || busy || !view.snapshot;
    document.querySelectorAll("[data-live-candidate]").forEach((field) => { field.disabled = view.candidates.size >= symbolLimit() && !field.checked; });
  }
  async function useCandidates() {
    if (!view.discovery || !view.candidates.size || view.snapshot?.status.running) return;
    q("#live-use-candidates").disabled = true;
    try {
      await api("/api/monitor/config", {...view.snapshot.config, source:view.discovery.source, symbols:[...view.candidates]});
      await fetchSnapshot();
      await fetchSelectedDetail(true);
      q("#live-discovery-dialog").close();
      q("#live-announcement").textContent = "Candidate selection saved. Start the monitor to follow these symbols.";
    } catch (error) { showError("#live-discovery-error", error.message); }
    finally { candidateSelection(); }
  }
  async function loadJournal(offset = 0) {
    if (view.journal.busy) return;
    view.journal.busy = true;
    q("#live-journal-prev").disabled = true;
    q("#live-journal-next").disabled = true;
    q("#live-journal-page").textContent = "Loading saved alerts…";
    showError("#live-journal-error", "");
    try {
      const data = await api(`/api/monitor/alerts?limit=${view.journal.limit}&offset=${Math.max(0, offset)}`);
      Object.assign(view.journal, data);
      // Summaries cover this page's finished 30-minute windows only.
      const finished = data.alerts.map((alert) => alert.outcomes?.[30]).filter((outcome) => outcome?.status === "observed");
      const changes = finished.map((outcome) => outcome.close_change_pct).filter(numeric).sort((a, b) => a - b);
      const dips = finished.map((outcome) => outcome.adverse_excursion_pct).filter(numeric);
      const middle = changes.length / 2, median = changes.length ? (changes.length % 2 ? changes[Math.floor(middle)] : (changes[middle - 1] + changes[middle]) / 2) : null;
      q("#live-journal-stats").innerHTML = data.alerts.length ? [
        ["Alerts on this page", n(data.alerts.length), `${n(data.total)} saved in all`],
        ["Median 30-minute change", pct(median), `${n(changes.length)} with a finished 30-minute window`],
        ["Up after 30 minutes", changes.length ? `${n(changes.filter((value) => value > 0).length)} of ${n(changes.length)}` : "—", "Close above the signal-minute close"],
        ["Average worst dip", pct(dips.length ? dips.reduce((sum, value) => sum + value, 0) / dips.length : null), "Lowest low within 30 minutes"]
      ].map(([label, value, note]) => `<div><dt>${label}</dt><dd>${value}</dd><small>${escapeHTML(note)}</small></div>`).join("") : "";
      q("#live-journal-results").innerHTML = !data.alerts.length ? '<div class="live-alert-empty"><h3>No saved alerts yet</h3><p>Confirmed setups will preserve their original settings, data, and chart here.</p></div>' : `<div class="live-table-scroll"><table class="live-history-table"><thead><tr><th>Alert / source</th><th>Signal minute (ET)</th><th class="live-num">Score</th><th class="live-num">Signal price</th><th class="live-num">5 min</th><th class="live-num">15 min</th><th class="live-num">30 min</th><th class="live-num">Worst dip (30 min)</th></tr></thead><tbody>${data.alerts.map((alert) => { const dip = alert.outcomes?.[30]; return `<tr><td><button class="text-button" data-live-alert="${escapeHTML(alert.id)}">${escapeHTML(alert.symbol)} · ${setup(alert.level)}</button><small>${escapeHTML(sourceLabel(alert.source, alert.feed))}</small></td><td>${clock(alert.market_time || alert.created_at, true)}</td><td class="live-num">${n(alert.score)}/100</td><td class="live-num">${dollars(alert.price)}</td>${[5,15,30].map((minute) => { const outcome = alert.outcomes?.[minute]; return `<td class="live-num ${direction(outcome?.close_change_pct)}">${outcome?.status === "observed" ? pct(outcome.close_change_pct) : escapeHTML(outcome?.status || "Unavailable")}</td>`; }).join("")}<td class="live-num ${direction(dip?.adverse_excursion_pct)}">${dip?.status === "observed" ? pct(dip.adverse_excursion_pct) : "—"}</td></tr>`; }).join("")}</tbody></table></div><p class="field-help">Observed price changes, not fills, trades or profits. Click an alert for its frozen setup, settings and chart. Outcomes compare completed minute bars with the original signal-bar close.</p>`;
    } catch (error) { showError("#live-journal-error", error.message); }
    finally {
      const page = view.journal;
      page.busy = false;
      q("#live-journal-page").textContent = page.total ? `${page.offset + 1}–${Math.min(page.offset + page.limit, page.total)} of ${n(page.total)} saved alerts` : "0 saved alerts";
      q("#live-journal-prev").disabled = page.offset === 0;
      q("#live-journal-next").disabled = page.offset + page.limit >= page.total;
    }
  }
  async function showEvidence(id) {
    view.savedAlert = id;
    q("#live-evidence-result").innerHTML = '<p class="live-form-note" role="status">Loading saved evidence…</p>';
    q("#live-evidence-refresh").disabled = true;
    showError("#live-evidence-error", "");
    openDialog(q("#live-evidence-dialog"));
    try {
      const alert = await api(`/api/monitor/alerts/${encodeURIComponent(id)}`);
      if (view.savedAlert !== id) return;
      const row = alert.snapshot, config = alert.config;
      q("#live-evidence-dialog-title").textContent = `${alert.symbol} · ${setup(alert.level)}`;
      q("#live-evidence-result").innerHTML = `<button class="button subtle planner-entry-link" type="button" data-plan-alert="${escapeHTML(alert.id)}">Open trade plan</button><p class="live-form-note">${escapeHTML(sourceLabel(alert.source, alert.feed))} · ${clock(alert.market_time || alert.created_at, true)}<br>Alert price ${dollars(alert.price)} · score ${n(alert.score)}/100${alert.source === "demo" ? " · All values are synthetic." : ""}</p>${row && config ? `<h3>Original alert evidence</h3><dl class="live-evidence-metrics">${reportMetric("Reference close", dollars(alert.reference_price), "Original completed signal minute")}${reportMetric("Minute RVOL", ratio(row.minute_relative_volume))}${reportMetric("Bid–ask spread", numeric(row.spread_pct) ? `${n(row.spread_pct,2)}%` : "—")}${reportMetric("Session volume", n(row.session_volume))}${reportMetric("VWAP", dollars(row.vwap))}${reportMetric("EMA 9 / 20", `${dollars(row.ema9)} / ${dollars(row.ema20)}`)}</dl>${lineChart(row.chart, [{...alert, signal_bar_at:row.signal_bar_at}])}<h3>Data quality at the alert</h3><p class="field-help">Price ${clock(row.price_at, true)} · quote ${clock(row.quote_at)} · completed minute ${clock(row.signal_bar_at)}. ${row.stale ? "Stale or incomplete data." : "Freshness checks passed."}</p>${warningList(row.warnings)}${gateChecks(row)}<h3>Original rules</h3><p class="field-help">Price ${dollars(config.min_price)}–${dollars(config.max_price)} · minimum ${row.volume_filter_basis === "total_day" ? "total day" : "regular-session"} volume ${n(config.min_session_volume)}${numeric(config.min_relative_volume) ? ` · minute RVOL ≥ ${ratio(config.min_relative_volume)}` : ""}${numeric(config.max_spread_pct) ? ` · spread ≤ ${n(config.max_spread_pct,2)}%` : ""}<br>Buy / Strong buy scores ${n(config.buy_score)} / ${n(config.strong_buy_score)} · ${n(config.confirmation_bars)} confirmation bars · ${n(config.cooldown_seconds)}s cooldown</p><h3>Score evidence</h3><div class="live-score-breakdown">${(row.signals || []).map((signal) => `<div><span><strong>${escapeHTML(signal.name)}</strong><small>${escapeHTML(signal.description)}</small></span><span>${n(signal.points)} / ${n(signal.max_points)}</span></div>`).join("")}</div><details class="live-saved-json"><summary>Original settings and complete data snapshot</summary><p class="field-help">Preserved when this alert was created.</p><pre>${escapeHTML(JSON.stringify({config, snapshot:row, session:alert.session}, null, 2))}</pre></details>` : '<p class="live-form-note">This older alert has no saved configuration or market-data snapshot. Its original chart cannot be reconstructed from the current monitor.</p>'}<h3 class="live-outcomes-title">Observed outcomes</h3><p class="field-help">${escapeHTML(alert.observation_basis || "Price changes from the signal-bar close; adverse excursion is the lowest subsequent minute low relative to that close. These are observations, not executions.")}</p><div class="live-outcomes">${[5,15,30].map((minute) => { const outcome = alert.outcomes?.[minute] || {status:"unavailable",reason:"No saved observation data."}; return `<article><h4>After ${minute} minutes</h4><span class="live-outcome-status">${escapeHTML(outcome.status)}</span>${outcome.status === "observed" ? `<strong class="${direction(outcome.close_change_pct)}">${pct(outcome.close_change_pct)}</strong><p>Adverse excursion <span class="${direction(outcome.adverse_excursion_pct)}">${pct(outcome.adverse_excursion_pct)}</span></p><small>Close ${dollars(outcome.end_close)} · ${clock(outcome.observed_at)}</small>` : `<p>${escapeHTML(outcome.reason || "Waiting for complete future minute bars.")}</p><small>Target ${clock(outcome.target_at)}</small>`}</article>`; }).join("")}</div>`;
    } catch (error) { if (view.savedAlert === id) { showError("#live-evidence-error", error.message); q("#live-evidence-result").innerHTML = ""; } }
    finally { if (view.savedAlert === id) q("#live-evidence-refresh").disabled = false; }
  }
  function accept(snapshot) {
    if (!snapshot || !snapshot.config || !snapshot.status) return;
    const alerts = currentAlerts(snapshot);
    if (view.baseline && view.alertSource === snapshot.config.source) {
      for (const item of alerts) {
        const age = Date.now() - Date.parse(item.created_at);
        const fresh = !view.seen.has(item.id) && !item.acknowledged && Date.parse(item.created_at) >= view.freshSince && age >= -5000 && age <= 15000 && snapshot.status.running;
        if (fresh) {
          q("#live-announcement").textContent = `${item.source === "demo" ? "Synthetic demo: " : ""}${item.symbol}, ${setup(item.level)}, ${dollars(item.price)}.`;
          if (item.source === "alpaca") notify(item);
        }
      }
    }
    for (const item of alerts) view.seen.add(item.id);
    if (view.seen.size > 1000) view.seen = new Set(alerts.map((item) => item.id));
    if (view.alertSource !== snapshot.config.source) view.alertRefreshMessage = "";
    view.baseline = true;
    view.alertSource = snapshot.config.source;
    view.snapshot = {...snapshot, alerts};
    view.receivedAt = Date.now();
    render();
  }
  function render() {
    const {config, status, rows = []} = view.snapshot;
    const alerts = currentAlerts();
    const running = !!status.running;
    const stateNames = {stopped:"Monitor stopped", loading:"Preparing session data", connecting:"Connecting to market data", live:"Market stream connected", reconnecting:"Reconnecting to market data", error:"Connection needs attention", demo:"Synthetic simulation running"};
    q("#live-connection").textContent = stateNames[status.connection] || "Monitor status";
    q("#live-status-message").textContent = status.error || status.message || (running ? "Watching your selected symbols." : "Configure your symbols, then start a session.");
    q("#live-state-dot").className = `live-state-dot ${status.connection === "live" ? "connected" : status.connection === "demo" ? "synthetic" : ["error", "reconnecting"].includes(status.connection) ? "caution" : ""}`;
    q("#live-start").classList.toggle("hidden", running);
    q("#live-stop").classList.toggle("hidden", !running);
    q("#live-start").disabled = view.action;
    q("#live-stop").disabled = view.action;
    q("#live-config").disabled = view.action;
    q("#live-discover").disabled = view.action;
    q("#live-scan").disabled = view.action || view.discoveryBusy || !!view.discoveryStatus?.running;
    q("#live-scan span").textContent = view.discoveryBusy || view.discoveryStatus?.running ? "Scanning…" : "Scan now";
    const refreshing = status.refresh?.state === "loading" || view.refreshing;
    const refreshAvailable = !!status.refresh;
    q("#live-refresh").disabled = !refreshAvailable || view.action || refreshing || view.alertsRefreshing || !running || !["live", "demo"].includes(status.connection);
    q("#live-refresh").textContent = refreshing ? "Refreshing…" : "Refresh data";
    q("#live-refresh-status").textContent = !refreshAvailable
      ? "Restart Nomisma’s local service to use the updated data controls."
      : status.refresh?.error
      ? status.refresh.error
      : refreshing ? "Reloading quotes, history, volume baselines, and setup alerts…"
      : status.refresh?.completed_at ? `Data refreshed ${clock(status.refresh.completed_at)}. Live prices continue to update automatically.`
      : running ? "Live prices update automatically. Refresh data reloads quotes, history, and volume baselines."
      : "Start the monitor to load market data and enable Refresh data.";
    q("#live-export").disabled = !rows.length;
    q("#live-config-fields").disabled = running;
    q("#live-save-config").disabled = running || view.action;
    q("#live-config-running").classList.toggle("hidden", !running);
    const demo = (status.source || config.source) === "demo";
    const feed = status.feed || view.snapshot.provider_status?.feed;
    // A streaming monitor shows its source and data time; otherwise its status message explains what to do next.
    const streaming = ["live", "demo"].includes(status.connection) && !status.error && !!status.updated_at;
    q("#live-status-message").classList.toggle("hidden", streaming);
    q("#live-update-time").classList.toggle("hidden", !streaming);
    q("#live-update-time").title = demo ? "Simulated penny stocks on a historical clock. Prices, float, volume, and alerts are fictional." : feed === "iex" ? "IEX covers one exchange: volume and relative volume do not represent the consolidated market." : "Prices and quotes stream from your configured real-time market feed.";
    const warnings = [...new Set(status.warnings || [])];
    q("#live-warnings").classList.toggle("hidden", !warnings.length);
    replaceMarkup("#live-warnings", warnings.length ? `<details><summary>${warnings.length} market data ${warnings.length === 1 ? "note" : "notes"}</summary><ul>${warnings.map((warning) => `<li>${escapeHTML(warning)}</li>`).join("")}</ul></details>` : "");
    const setups = rows.filter((row) => row.signal === "Buy" || row.signal === "Strong buy");
    const strong = rows.filter((row) => row.signal === "Strong buy").length;
    const lastScan = view.discoveryStatus?.last_run?.completed_at;
    q("#live-radar-summary").textContent = `${n(rows.length)} ${rows.length === 1 ? "symbol" : "symbols"} · ${n(setups.length)} ${setups.length === 1 ? "setup" : "setups"} · ${n(strong)} strong buy${lastScan ? ` · last scan ${nyClock.format(new Date(lastScan))} ET` : ""}${demo ? " · synthetic demo" : ""}`;
    replaceMarkup("#live-filter-summary", [`$${n(config.min_price, 2)}–$${n(config.max_price, 2)}`, `Session vol ≥ ${short(config.min_session_volume)}`, `Buy ≥ ${n(config.buy_score)} · Strong ≥ ${n(config.strong_buy_score)}`, `${n(config.confirmation_bars)} confirmation ${config.confirmation_bars === 1 ? "bar" : "bars"}`, ...(config.alerts_enabled ? [] : ["Alerts off"])].map((text) => `<span class="live-chip">${escapeHTML(text)}</span>`).join(""));
    q("#live-alert-count").textContent = alerts.filter((item) => !item.acknowledged).length;
    q("#live-ack-all").disabled = !alerts.some((item) => !item.acknowledged);
    const alertsRefreshing = view.alertsRefreshing || view.refreshing;
    q("#live-alert-refresh").disabled = view.action || alertsRefreshing;
    q("#live-alert-refresh").setAttribute("aria-busy", String(alertsRefreshing));
    q("#live-alert-refresh").textContent = alertsRefreshing ? "Refreshing…" : "Refresh";
    q("#live-alert-refresh-status").textContent = alertsRefreshing
      ? "Refreshing saved setup alerts…"
      : view.alertRefreshMessage || "Saved setups retain their original price and score.";
    renderTable(); renderFocus(); renderAlerts(); renderNotificationNote(); renderFreshness(); renderPulse();
    if (q("#live-discovery-dialog").open) candidateSelection();
    if (q("#live-report-dialog").open) fetchSelectedDetail();
  }
  function metricCell(value, formatted, title, className = "") {
    return `<td class="live-num ${className}" title="${escapeHTML(numeric(value) ? `${title}: ${n(value, 4).replace(/\.?0+$/, "")}` : unavailable)}">${formatted}</td>`;
  }
  function eligibilityText(row) {
    let blocker = row.eligibility?.primary_blocker || row.blockers?.[0];
    const checkName = /minute relative volume/i.test(blocker || "") ? "Minute RVOL" : /total day volume is below/i.test(blocker || "") ? "Total day volume" : /regular-session volume is below/i.test(blocker || "") ? "Session volume" : /bid\/ask spread/i.test(blocker || "") ? "Spread maximum" : null;
    const check = row.eligibility?.checks?.find((item) => item.name === checkName);
    if (check) blocker = `${check.name}: ${numeric(check.actual) ? n(check.actual, check.unit === "shares" ? 0 : 2) + unitLabel(check.unit) : "unavailable"}; ${check.name === "Spread maximum" ? "maximum" : "requires"} ${n(check.required, check.unit === "shares" ? 0 : 2)}${unitLabel(check.unit)}`;
    const confirmation = row.confirmation || {};
    const required = confirmation.required || view.snapshot?.config.confirmation_bars || 1;
    const bars = confirmation.bars || 0;
    const progress = `${n(Math.min(bars, required))} of ${n(required)} confirmation bars`;
    const cooldown = confirmation.cooldown_remaining_seconds > 0 ? ` · ${n(Math.ceil(confirmation.cooldown_remaining_seconds))}s cooldown` : "";
    const dots = `<span class="live-dots" aria-hidden="true">${Array.from({length:required}, (_, i) => `<i class="${i < bars ? "on" : ""}"></i>`).join("")}</span>`;
    return `<strong class="${blocker ? "live-blocked-label" : "positive"}">${escapeHTML(blocker || (confirmation.confirmed ? "Confirmed setup" : row.alert_eligible ? "Conditions pass" : "Not eligible"))}</strong><small>${dots}${escapeHTML(progress + cooldown)}</small>`;
  }
  const badge = (level) => `<span class="live-badge ${levelClass(level)}">${level === "Strong buy" || level === "Buy" ? level : "No setup"}</span>`;
  const pct1 = (value) => numeric(value) ? `${value > 0 ? "+" : value < 0 ? "−" : ""}${n(Math.abs(value), 1)}%` : "—";
  const ratio1 = (value) => numeric(value) ? `${n(value, 1)}×` : "—";
  const scoreBar = (score) => `<span class="live-score-bar" aria-hidden="true"><span class="${score >= 80 ? "high" : score >= 60 ? "" : "low"}" style="width:${numeric(score) ? Math.max(0, Math.min(100, score)) : 0}%"></span></span>`;
  function stockRow(row, config) {
    const symbol = escapeHTML(row.symbol);
    const volumeClass = numeric(row.minute_relative_volume) && row.minute_relative_volume >= 1.5 ? "live-volume-active" : "";
    const minuteCell = metricCell(row.minute_relative_volume, ratio(row.minute_relative_volume), "1-minute RVOL", volumeClass);
    const selected = row.symbol === view.focus ? " live-selected" : "";
    if (!view.extraColumns) return `<tr class="${row.stale ? "live-stale" : ""}${selected}">
      <td><button class="live-stock-button" data-live-symbol="${symbol}" aria-label="Select ${symbol}"><span class="live-symbol">${symbol}${row.stale ? '<span class="live-row-dot stale" title="Stale or unavailable market data"></span>' : ""}</span>${badge(row.signal)}</button></td>
      <td class="live-num" data-label="Price / day"><strong>${dollars(row.price)}</strong><small class="${direction(row.change_pct)}">${pct1(row.change_pct)}</small></td>
      ${screeningCells(row, ["day_volume"])}<td class="live-num" data-metric="day_relative_volume" data-label="Day RVOL" title="Total day volume / 20-session average; not time adjusted">${ratio1(row.day_relative_volume)}</td>${metricCell(row.minute_relative_volume, ratio1(row.minute_relative_volume), "1-minute RVOL", volumeClass)}<td class="live-num" data-metric="spread_pct" data-label="Bid–ask spread" title="Ask minus bid as a percentage of the midpoint; quote ${escapeHTML(clock(row.quote_at))}">${numeric(row.spread_pct) ? `${n(row.spread_pct, 2)}%` : "—"}</td>
      <td data-label="Setup score"><span class="live-score-cell">${scoreBar(row.signal_score)}${n(row.signal_score)}</span></td>
      <td class="live-eligibility">${eligibilityText(row)}</td>
    </tr>`;
    return `<tr class="${row.stale ? "live-stale" : ""}${selected}">
      <td><button class="live-stock-button" data-live-symbol="${symbol}" aria-label="Open ${symbol} intraday report"><span class="live-symbol">${symbol}<span class="live-row-dot ${row.stale ? "stale" : ""}" title="${row.stale ? "Stale or unavailable market data" : "Price and quote freshness checked"}"></span></span><span class="live-setup ${levelClass(row.signal)}">${setup(row.signal)}</span></button><button type="button" class="live-candle-open" data-live-candles="${symbol}" title="Full-screen candles" aria-label="Open ${symbol} full-screen candlestick chart">${icon("trend")}</button></td>
      <td class="live-num" data-label="Price / day"><strong>${dollars(row.price)}</strong><small class="${direction(row.change_pct)}">${pct(row.change_pct)}</small></td>
      ${screeningCells(row)}
      <td class="live-eligibility">${eligibilityText(row)}</td>
      ${view.extraColumns ? `<td class="live-num" data-label="Setup score"><span class="live-score">${n(row.signal_score)}<small>/100</small></span></td>${minuteCell}${metricCell(row.float_shares, short(row.float_shares), "Float shares")}${metricCell(row.gap_pct, pct(row.gap_pct), "Opening gap percentage", direction(row.gap_pct))}${metricCell(row.session_volume, short(row.session_volume), "Completed regular-session minute volume")}${metricCell(row.avg_volume_30d, short(row.avg_volume_30d), "30-session average volume")}${metricCell(row.volume_30d_total, short(row.volume_30d_total), "30-session total volume")}${metricCell(row.relative_volume, ratio(row.relative_volume), "Session RVOL")}` : ""}
    </tr>`;
  }
  function renderTable() {
    const {rows = [], config, status} = view.snapshot;
    const filtered = rows.filter((row) => !view.query || `${row.symbol} ${row.name}`.toLowerCase().includes(view.query));
    filtered.sort(compareRows(view.sort));
    if (!rows.length) {
      replaceMarkup("#live-table", `<div class="live-empty"><span aria-hidden="true">⌁</span><h3>${status.running ? "Building your session view" : "Your next session starts here"}</h3><p>${status.running ? "Loading current quotes, minute bars, and prior history for liquidity and volatility. Connection status above shows progress." : `Ready to monitor ${escapeHTML(config.symbols.join(", "))}. Start the monitor to follow prices and evaluate minute-by-minute setups.`}</p></div>`);
      return;
    }
    if (!filtered.length) { replaceMarkup("#live-table", '<div class="live-empty"><h3>No matching symbols</h3><p>Try another symbol or company name.</p></div>'); return; }
    const focused = document.activeElement?.dataset.liveSymbol;
    const changed = replaceMarkup("#live-table", `<table class="live-stocks ${view.extraColumns ? "expanded" : ""}"><thead><tr>${view.extraColumns ? `<th>Stock / setup</th><th class="live-num">Price / day</th>${screeningHeaders()}` : '<th>Stock</th><th class="live-num">Price / day</th><th class="live-num">Day vol</th><th class="live-num">Day RVOL</th><th class="live-num" title="Latest completed minute\'s volume divided by the preceding 20-minute average">1-min RVOL</th><th class="live-num">Spread</th><th>Setup score</th>'}<th>Alert eligibility</th>${view.extraColumns ? '<th class="live-num">Setup score</th><th class="live-num">1-min RVOL</th><th class="live-num">Float</th><th class="live-num">Gap</th><th class="live-num">Regular vol.</th><th class="live-num">30D avg vol.</th><th class="live-num">30D total vol.</th><th class="live-num">Session RVOL</th>' : ""}</tr></thead><tbody>${filtered.map((row) => stockRow(row, config)).join("")}</tbody></table>`);
    if (changed && focused) [...q("#live-table").querySelectorAll("[data-live-symbol]")].find((button) => button.dataset.liveSymbol === focused)?.focus({preventScroll:true});
  }
  function renderFreshness() {
    if (!view.snapshot) return;
    const elapsed = Math.floor((Date.now() - view.receivedAt) / 1000);
    const status = view.snapshot.status;
    const interrupted = elapsed > 35;
    const browserState = interrupted ? "Browser updates interrupted" : view.transport === "polling" ? "Browser polling every 2s" : "Browser streaming";
    q("#live-update-time").textContent = `${sourceLabel(status.source || view.snapshot.config.source, status.feed || view.snapshot.provider_status?.feed).replace("Alpaca · ", "Alpaca ")} · data ${status.updated_at ? nySeconds.format(new Date(status.updated_at)) + " ET" : "—"}${interrupted ? ` · ${browserState} (${elapsed}s)` : ""}`;
    q("#live-update-time").classList.toggle("negative", interrupted);
    renderNextScan();
  }
  const scanDay = new Intl.DateTimeFormat("en-US", {timeZone:"America/New_York", weekday:"short", hour:"numeric", minute:"2-digit"});
  function renderNextScan() {
    // The countdown fills over the 5-minute repeat; a later first search of the day shows its New York time.
    const status = view.discoveryStatus, due = Date.parse(status?.next_due || ""), left = Math.max(0, Math.round((due - Date.now()) / 1000));
    const scanning = status?.running || view.discoveryBusy;
    q("#live-next-scan").textContent = scanning ? "scanning…" : Number.isNaN(due) ? "off" : left > 300 ? `${scanDay.format(due)} ET` : `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;
    q("#live-next-scan-fill").style.width = `${scanning ? 100 : Number.isNaN(due) || left > 300 ? 0 : (1 - left / 300) * 100}%`;
  }
  function focusBars(row) {
    // Alpaca rows chart real candles at any timeframe; the demo groups its completed 1-minute bars.
    const [tf, , ms] = candleFrames.find(([key]) => key === view.focusTf);
    if (row.source === "alpaca") {
      const data = view.focusCandles?.key === `${row.symbol}|${tf}` ? view.focusCandles : null;
      return data && {bars:withLivePrice(data.bars, row, ms).slice(-60), error:data.error};
    }
    const minutes = view.focusDetail?.symbol === row.symbol ? view.focusDetail.chart : null;
    if (!minutes) return null;
    if (!ms) return {bars:[], error:"Daily candles need Alpaca market data."};
    const groups = new Map();
    for (const bar of minutes) {
      const start = Math.floor(Date.parse(bar.t) / ms) * ms, group = groups.get(start);
      if (!group) groups.set(start, {...bar, t:new Date(start).toISOString()});
      else Object.assign(group, {high:Math.max(group.high, bar.high), low:Math.min(group.low, bar.low), close:bar.close, volume:(group.volume || 0) + (bar.volume || 0)});
    }
    return {bars:[...groups.values()].slice(-60), error:""};
  }
  function focusChart(bars) {
    if (!bars.length) return '<p class="live-chart-empty">No candles for this timeframe yet.</p>';
    const width = 400, height = 252, right = 58, top = 6, priceBottom = 186, volumeTop = 200, volumeBottom = 248;
    const low = Math.min(...bars.map((bar) => bar.low)), high = Math.max(...bars.map((bar) => bar.high)), pad = Math.max((high - low) * .08, high * .002, .005);
    const min = low - pad, max = high + pad, step = (width - right) / bars.length, body = Math.max(1, step * .62);
    const x = (i) => step * (i + .5), y = (price) => top + (max - price) / (max - min) * (priceBottom - top);
    const maxVolume = Math.max(1, ...bars.map((bar) => bar.volume || 0)), last = bars[bars.length - 1], lastY = y(last.close);
    const lastColor = last.close >= (bars[bars.length - 2]?.close ?? last.open) ? "#2f6b43" : "#a3412a", tick = niceStep(max - min, 3);
    let grid = "";
    for (let value = Math.ceil(min / tick) * tick; value <= max; value += tick) grid += `<line x1="0" x2="${width - right}" y1="${y(value)}" y2="${y(value)}" stroke="#edf0ea"/>${Math.abs(y(value) - lastY) < 14 ? "" : `<text x="${width - right + 8}" y="${y(value) + 4}" fill="#56625a" font-size="11">${priceText(value)}</text>`}`;
    const candles = bars.map((bar, i) => {
      const up = bar.close >= bar.open, color = up ? "#2f6b43" : "#a3412a", volume = (bar.volume || 0) / maxVolume * (volumeBottom - volumeTop);
      return `<line x1="${x(i)}" x2="${x(i)}" y1="${y(bar.high)}" y2="${y(bar.low)}" stroke="${color}"/><rect x="${x(i) - body / 2}" y="${y(Math.max(bar.open, bar.close))}" width="${body}" height="${Math.max(1, Math.abs(y(bar.open) - y(bar.close)))}" fill="${color}"/><rect x="${x(i) - body / 2}" y="${volumeBottom - volume}" width="${body}" height="${volume}" fill="${up ? "#a9cdb2" : "#e3b9ac"}"><title>${escapeHTML(candleTime.format(new Date(bar.t)))} ET · ${n(bar.volume)} shares</title></rect>`;
    }).join("");
    return `<svg viewBox="0 0 ${width} ${height}" class="live-focus-candles" role="img" aria-label="${bars.length} candles, last close ${dollars(last.close)}">${grid}${candles}<rect x="${width - right + 2}" y="${lastY - 10}" width="${right - 2}" height="20" rx="4" fill="${lastColor}"/><text x="${width - right / 2 + 1}" y="${lastY + 4}" text-anchor="middle" fill="#fff" font-size="11" font-weight="600">${priceText(last.close)}</text></svg>`;
  }
  function renderFocus() {
    const rows = view.snapshot?.rows || [];
    if (!rows.some((row) => row.symbol === view.focus)) { view.focus = [...rows].sort(compareRows(view.sort))[0]?.symbol || null; view.focusDetail = null; loadFocus(); }
    const row = rows.find((item) => item.symbol === view.focus);
    if (!row) { replaceMarkup("#live-focus", '<div class="live-focus-empty"><h3>Select a stock</h3><p>Radar stocks appear here with their candles and why each one is or is not alerting.</p></div>'); return; }
    const config = view.snapshot.config, reasons = row.reasons || [], confirmation = row.confirmation || {};
    const required = confirmation.required || config.confirmation_bars || 1, session = row.eligibility?.checks?.find((check) => check.name === "Session volume");
    const checks = [
      ["Price in range", `${dollars(row.price)} · ${dollars(config.min_price)}–${dollars(config.max_price)}`, numeric(row.price) && row.price >= config.min_price && row.price <= config.max_price],
      ["Regular-session volume", `${short(session?.actual)} · ≥ ${short(config.min_session_volume)}`, !!session?.passed],
      ["Above session VWAP", reasons.includes("Above session VWAP") ? "Yes" : "No", reasons.includes("Above session VWAP")],
      ["EMA 9 above EMA 20", reasons.includes("EMA trend") ? "Yes" : "No", reasons.includes("EMA trend")],
      ["Setup score", `${n(row.signal_score)} · Buy ≥ ${n(config.buy_score)}`, numeric(row.signal_score) && row.signal_score >= config.buy_score],
      ["Fresh market data", row.stale ? "Stale or incomplete" : "Checked", !row.stale],
      ["Confirmation", `${n(Math.min(confirmation.bars || 0, required))} of ${n(required)} bars`, !!confirmation.confirmed]
    ];
    const data = focusBars(row), symbol = escapeHTML(row.symbol);
    const chart = !data ? '<p class="live-chart-empty">Loading candles…</p>' : data.error && !data.bars.length ? `<p class="live-chart-empty">${escapeHTML(data.error)}</p>` : focusChart(data.bars);
    replaceMarkup("#live-focus", `<div class="live-focus-head"><div><div class="live-focus-symbol"><h2 class="live-mono">${symbol}</h2>${badge(row.signal)}</div><p class="live-mono"><strong>${dollars(row.price)}</strong> <span class="${direction(row.change_pct)}">${pct1(row.change_pct)}</span></p></div><button type="button" class="button subtle" data-live-candles="${symbol}" aria-label="Open ${symbol} full-screen candlestick chart"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/></svg>Full chart</button></div>
      <div class="live-tf" role="group" aria-label="Chart timeframe">${candleFrames.map(([tf, label]) => `<button type="button" data-live-focus-tf="${tf}" aria-pressed="${tf === view.focusTf}">${label}</button>`).join("")}</div>
      <div class="live-focus-chart">${chart}</div>
      <dl class="live-focus-metrics">${[["Day volume", short(row.day_volume)], ["Day RVOL", ratio1(row.day_relative_volume)], ["1-min RVOL", ratio1(row.minute_relative_volume)], ["Spread", numeric(row.spread_pct) ? `${n(row.spread_pct, 2)}%` : "—"], ["ATR % (14D)", numeric(row.atr_pct) ? `${n(row.atr_pct, 1)}%` : "—"], ["Setup score", `${n(row.signal_score)} / 100`]].map(([label, value]) => `<div><dt>${label}</dt><dd class="live-mono">${value}</dd></div>`).join("")}</dl>
      <h3>Why it is or is not alerting</h3><ul class="live-focus-checks">${checks.map(([label, value, passed]) => `<li><span>${label}</span><span><span class="live-mono">${escapeHTML(value)}</span><b class="${passed ? "pass" : "fail"}">${passed ? "Pass" : "Fail"}</b></span></li>`).join("")}</ul>
      <button type="button" class="text-button live-focus-report" data-live-report="${symbol}">Open full report</button>`);
  }
  function selectFocus(symbol) {
    // A narrow window has no room beside the radar, so the full report opens instead.
    if (innerWidth <= 1100) { showStock(symbol); return; }
    view.focus = symbol;
    view.focusDetail = null;
    renderTable(); renderFocus(); loadFocus();
  }
  async function loadFocus() {
    const symbol = view.focus, tf = view.focusTf;
    if (!symbol || view.focusFetching || document.hidden || q("#live-view").classList.contains("hidden")) return;
    const row = view.snapshot?.rows?.find((item) => item.symbol === symbol);
    view.focusFetching = true;
    try {
      if (row?.source === "alpaca") {
        const key = `${symbol}|${tf}`;
        if (view.focusCandles?.key !== key || Date.now() - view.focusCandles.at > 15000) {
          try { view.focusCandles = {key, bars:(await api(`/api/monitor/candles/${encodeURIComponent(symbol)}?timeframe=${encodeURIComponent(tf)}`)).candles, at:Date.now(), error:""}; }
          catch (error) { view.focusCandles = {key, bars:[], at:Date.now(), error:`Candles unavailable: ${error.message}`}; }
        }
      } else {
        const data = await api(`/api/monitor/symbol/${encodeURIComponent(symbol)}`);
        if (symbol === view.focus) view.focusDetail = data.row;
      }
    } catch (_) { /* The panel keeps its last chart; the full report shows fetch errors. */ }
    finally { view.focusFetching = false; }
    if (symbol !== view.focus || tf !== view.focusTf) loadFocus(); else renderFocus();
  }
  async function loadPulse() {
    if (document.hidden || q("#live-view").classList.contains("hidden")) return;
    try { view.pulse = await api("/api/market/pulse"); view.pulseError = ""; }
    catch (error) { view.pulseError = error.message; }
    renderPulse();
  }
  const nyWeekday = new Intl.DateTimeFormat("en-US", {timeZone:"America/New_York", weekday:"short"});
  function livePulse(item) {
    // The monitor's stream carries pulse trades; during regular hours they replace the 30-second snapshot price.
    const trade = view.snapshot?.pulse_trades?.[item.symbol];
    if (!trade) return item;
    const time = new Date(trade.t), [hour, minute] = nyClock.format(time).split(":").map(Number), day = nyDay(time);
    if (["Sat", "Sun"].includes(nyWeekday.format(time)) || hour * 60 + minute < 570 || hour >= 16 || (item.session_date && day < item.session_date)) return item;
    // A new session's trade compares with the last close the snapshot showed; otherwise with that session's prior close.
    const reference = !item.live && item.session_date && day > item.session_date ? item.price : item.previous_close;
    return {...item, price:trade.price, change_pct:reference ? (trade.price / reference - 1) * 100 : null, live:true, streamed:true};
  }
  function renderPulse() {
    const quotes = (view.pulse?.quotes || []).map(livePulse), indexes = quotes.filter((item) => item.kind === "index"), movers = quotes.filter((item) => item.kind === "mover");
    const up = (list) => list.filter((item) => item.change_pct > 0).length;
    q("#live-pulse-summary").textContent = quotes.length ? `${up(indexes)} of ${indexes.length} indexes up · ${up(movers)} of ${movers.length} movers up · small caps (IWM) ${pct(indexes.find((item) => item.symbol === "IWM")?.change_pct)}` : "";
    q("#live-pulse-note").textContent = view.pulseError ? (quotes.length ? `Update failed; showing ${clock(view.pulse.as_of)}` : "") : view.pulse?.quotes?.length ? `Index ETFs track each index · ${sourceLabel("alpaca", view.pulse.feed)} · ${quotes.some((item) => item.streamed) ? "streaming live" : quotes.some((item) => item.live) ? `live ${clock(view.pulse.as_of)}` : `closing prices ${date(quotes.find((item) => item.session_date)?.session_date)}`}` : view.pulse ? "" : "Loading index ETFs and market movers…";
    if (!quotes.length) { replaceMarkup("#live-pulse", view.pulseError || view.pulse?.message ? `<p class="live-pulse-error">${escapeHTML(view.pulse?.message || `Market pulse is unavailable: ${view.pulseError}`)}</p>` : ""); return; }
    const spark = (values, change) => {
      if (values.length < 2) return "";
      const low = Math.min(...values), high = Math.max(...values), points = values.map((value, i) => `${(i * 96 / (values.length - 1)).toFixed(1)},${(30 - (value - low) / (high - low || 1) * 28).toFixed(1)}`).join(" ");
      return `<svg viewBox="0 0 96 32" aria-hidden="true"><polyline points="${points}" fill="none" class="${direction(change)}" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" vector-effect="non-scaling-stroke"/></svg>`;
    };
    const label = (item) => `Open ${item.name ? `${item.name} (${item.symbol})` : item.symbol} full-screen chart, ${pct(item.change_pct)}`;
    replaceMarkup("#live-pulse", `<div class="live-pulse-indexes">${indexes.map((item) => `<button type="button" class="live-pulse-card" data-live-candles="${escapeHTML(item.symbol)}" aria-label="${escapeHTML(label(item))}"><span><span class="live-pulse-name">${escapeHTML(item.name)} <small>${escapeHTML(item.symbol)}</small></span><strong>${dollars(item.price)}</strong><span class="${direction(item.change_pct)}">${pct(item.change_pct)}</span></span>${spark(item.spark || [], item.change_pct)}</button>`).join("")}</div><div class="live-pulse-movers"><h3>Market movers</h3>${movers.map((item) => `<button type="button" class="live-pulse-chip" data-live-candles="${escapeHTML(item.symbol)}" aria-label="${escapeHTML(label(item))}"><strong>${escapeHTML(item.symbol)}</strong><span class="${direction(item.change_pct)}">${pct(item.change_pct)}</span></button>`).join("")}</div>`);
  }
  function renderAlerts() {
    const alerts = currentAlerts();
    const demo = view.snapshot.config.source === "demo";
    const key = JSON.stringify([view.snapshot.config.source, alerts]);
    if (key === view.alertsKey) return;
    view.alertsKey = key;
    const today = nyDay(Date.now()), day = new Intl.DateTimeFormat("en-US", {timeZone:"America/New_York", month:"short", day:"numeric"});
    const when = (value) => { const time = new Date(value); return Number.isNaN(time.getTime()) ? "—" : nyDay(time) === today ? nyClock.format(time) : day.format(time); };
    q("#live-alerts").innerHTML = !alerts.length
      ? `<div class="live-alert-empty"><h3>${demo ? "No demo alerts yet" : "No market alerts yet"}</h3><p>${demo ? "Synthetic setups appear here while the demo monitor runs." : "Alpaca setups appear here after fresh regular-session data passes your filters and confirmation rules."} Saved alerts from all sources remain in the journal.</p></div>`
      : alerts.map((item) => `<button type="button" class="live-alert-row ${item.acknowledged ? "read" : "unread"}" data-live-alert="${escapeHTML(item.id)}" aria-label="Open saved ${escapeHTML(item.symbol)} ${escapeHTML(setup(item.level))} alert from ${escapeHTML(clock(item.market_time || item.created_at, true))}${item.acknowledged ? "" : ", unread"}"><i aria-hidden="true"></i><span class="live-mono">${when(item.market_time || item.created_at)}</span><strong class="live-mono">${escapeHTML(item.symbol)}</strong><span>${badge(item.level)}</span><span class="live-mono">${dollars(item.price)} · ${n(item.score)}</span></button>`).join("");
  }
  function lineChart(series, markers = []) {
    const points = (series || []).filter((bar) => numeric(bar.close));
    if (!points.length) return '<p class="live-chart-empty">Completed minute history is unavailable.</p>';
    const width = 760, height = 292, left = 12, right = 70, priceBottom = 200, volumeTop = 226, volumeBottom = 280;
    const values = points.flatMap((bar) => [bar.close, bar.vwap, bar.ema9, bar.ema20]).filter(numeric);
    const low = Math.min(...values), high = Math.max(...values), pad = Math.max((high - low) * .15, high * .002, .005);
    const min = low - pad, max = high + pad;
    const x = (i) => left + i / Math.max(1, points.length - 1) * (width - left - right);
    const y = (price) => 10 + (max - price) / (max - min) * (priceBottom - 10);
    const maxVolume = Math.max(1, ...points.map((bar) => bar.volume || 0));
    const pathFor = (key) => { let pen = false; return points.map((bar, i) => { if (!numeric(bar[key])) { pen = false; return ""; } const part = `${pen ? "L" : "M"}${x(i).toFixed(2)},${y(bar[key]).toFixed(2)}`; pen = true; return part; }).join(" "); };
    const grid = [0, 1, 2, 3].map((i) => { const value = min + (max - min) * i / 3; return `<line x1="${left}" x2="${width - right}" y1="${y(value)}" y2="${y(value)}" stroke="#dce5d9" stroke-dasharray="3 5"/><text x="${width - right + 10}" y="${y(value) + 4}" fill="#637360" font-size="11">${n(value, value < 1 ? 4 : 2)}</text>`; }).join("");
    const markerShapes = markers.map((alert) => {
      const when = Date.parse(alert.signal_bar_at || alert.market_time || alert.t);
      const index = points.findIndex((bar) => Math.abs(Date.parse(bar.t) - when) < 60000);
      if (index < 0) return "";
      return `<path d="M${x(index)},${y(points[index].close) - 3} l-5,-9 h10 Z" fill="#8c6831" stroke="#fff"><title>${escapeHTML(setup(alert.level))} · ${escapeHTML(clock(alert.market_time || alert.t))} · ${dollars(alert.price)}</title></path>`;
    }).join("");
    const lines = [["close", "#39704b"], ["vwap", "#aa7c35"], ["ema9", "#5578ab"], ["ema20", "#9d69a2"]];
    return `<div class="live-chart-legend">${lines.map(([key, color]) => `<span><i style="background:${color}"></i>${({close:"Price",vwap:"VWAP",ema9:"EMA 9",ema20:"EMA 20"})[key]}</span>`).join("")}<span>▼ Saved alert</span></div><svg viewBox="0 0 ${width} ${height}" class="live-price-chart" role="img" aria-label="${points.length} completed minute prices, VWAP, EMA 9, EMA 20, volume and saved alert markers. Exact values available in the table below.">${grid}${lines.map(([key,color]) => `<path d="${pathFor(key)}" fill="none" stroke="${color}" stroke-width="${key === "close" ? 2 : 1.5}" vector-effect="non-scaling-stroke"/>`).join("")}${markerShapes}<text x="${left}" y="220" fill="#637360" font-size="10">MINUTE VOLUME</text>${points.map((bar,i) => { const h = (bar.volume || 0) / maxVolume * (volumeBottom - volumeTop); return `<rect x="${x(i) - 1}" y="${volumeBottom - h}" width="${Math.max(1, (width - left - right) / points.length - 1)}" height="${h}" fill="${i && bar.close < points[i-1].close ? "#c5a391" : "#9ab68c"}"><title>${escapeHTML(clock(bar.t))}: ${dollars(bar.close)} · VWAP ${dollars(bar.vwap)} · EMA9 ${dollars(bar.ema9)} · EMA20 ${dollars(bar.ema20)} · volume ${n(bar.volume)}</title></rect>`; }).join("")}<text x="${width-right+10}" y="${volumeTop+8}" fill="#637360" font-size="11">${short(maxVolume)}</text></svg><div class="live-chart-times"><span>${clock(points[0].t)}</span><span>${clock(points[points.length-1].t)}</span></div><details class="live-chart-data"><summary>Inspect exact minute values</summary><div class="live-table-scroll"><table class="live-history-table"><thead><tr><th>Minute (ET)</th><th>Close</th><th>VWAP</th><th>EMA 9</th><th>EMA 20</th><th>Volume</th></tr></thead><tbody>${points.map((bar) => `<tr><td>${clock(bar.t)}</td><td>${dollars(bar.close)}</td><td>${dollars(bar.vwap)}</td><td>${dollars(bar.ema9)}</td><td>${dollars(bar.ema20)}</td><td>${n(bar.volume)}</td></tr>`).join("")}</tbody></table></div></details>`;
  }
  function withLivePrice(bars, row, ms) {
    // The latest trade moves the newest candle between 15-second history refreshes.
    const last = bars[bars.length - 1], time = Date.parse(row.price_at);
    if (!last || !numeric(row.price) || Number.isNaN(time) || time < Date.parse(last.t)) return bars;
    if (ms ? time < Date.parse(last.t) + ms : nyDay(time) === nyDay(last.t)) {
      return [...bars.slice(0, -1), {...last, close:row.price, high:Math.max(last.high, row.price), low:Math.min(last.low, row.price)}];
    }
    return [...bars, {t:new Date(ms ? Math.floor(time / ms) * ms : time).toISOString(), open:row.price, high:row.price, low:row.price, close:row.price, volume:0, forming:true}];
  }
  const axisFormats = [{month:"short", day:"numeric"}, {month:"short", day:"numeric", year:"numeric"}, {hour:"numeric", minute:"2-digit"}, {weekday:"short", month:"short", day:"numeric", year:"numeric"}]
    .map((options) => new Intl.DateTimeFormat("en-US", {timeZone:"America/New_York", ...options}));
  const priceText = (value) => n(value, value < 1 ? 4 : 2);
  function niceStep(span, count) {
    // Round gridline spacing (1, 2 or 5 × a power of ten) so price levels read at a glance.
    const raw = span / count, power = 10 ** Math.floor(Math.log10(raw)), unit = raw / power;
    return power * (unit < 1.5 ? 1 : unit < 3 ? 2 : unit < 7 ? 5 : 10);
  }
  const candleRoom = 8;  // empty candle slots kept right of the newest candle
  function candleChart(points, ms, ahead, width = 760, height = 320, first = 0) {
    view.candleGeo = null;
    if (!points.length) return '<p class="live-chart-empty">Alpaca returned no candles for this timeframe.</p>';
    const left = 12, right = 70, top = 10, priceBottom = height - 104, volumeTop = height - 84, volumeBottom = height - 26;
    const vwaps = points.map((bar) => bar.vwap).filter(numeric);
    const low = Math.min(...points.map((bar) => bar.low), ...vwaps), high = Math.max(...points.map((bar) => bar.high), ...vwaps), pad = Math.max((high - low) * .06, high * .001, .005);
    // Dragging the price axis scales the auto-fitted range around its middle (above 1 squashes candles, below 1 stretches them).
    const mid = (high + low) / 2, half = ((high - low) / 2 + pad) * view.candleScale;
    const min = mid - half, max = mid + half, step = (width - left - right) / (points.length + ahead + candleRoom), body = Math.max(1, step * .7);
    const x = (i) => left + step * (i + .5);
    const y = (price) => top + (max - price) / (max - min) * (priceBottom - top);
    const maxVolume = Math.max(1, ...points.map((bar) => bar.volume || 0));
    const label = (t) => escapeHTML((ms ? candleTime : axisFormats[3]).format(new Date(t)));
    const last = points[points.length - 1], lastY = Math.max(top, Math.min(priceBottom, y(last.close))), lastColor = last.close >= (points[points.length - 2]?.close ?? last.open) ? "#39704b" : "#b4553f";
    const tick = niceStep(max - min, Math.max(3, Math.round((priceBottom - top) / 60)));
    let grid = "";
    for (let value = Math.ceil(min / tick) * tick; value <= max; value += tick) {
      grid += `<line x1="${left}" x2="${width - right}" y1="${y(value)}" y2="${y(value)}" stroke="#e3eadf"/>${Math.abs(y(value) - lastY) < 14 ? "" : `<text x="${width - right + 10}" y="${y(value) + 4}" fill="#637360" font-size="11">${priceText(value)}</text>`}`;
    }
    // Time labels sit on fixed bars of the whole series, so they stay put while the chart pans.
    const every = Math.max(1, Math.ceil(110 / step));
    let axis = "", previous = "";
    points.forEach((bar, i) => {
      if ((first + i) % every || x(i) < left + 30 || x(i) > width - right - 30) return;
      const time = new Date(bar.t), day = nyDay(bar.t), newDay = day !== previous;
      const text = ms ? axisFormats[newDay ? 0 : 2].format(time) : axisFormats[day.slice(0, 4) !== previous.slice(0, 4) ? 1 : 0].format(time);
      axis += `<line x1="${x(i)}" x2="${x(i)}" y1="${top}" y2="${volumeBottom}" stroke="#eef2ea"/><text x="${x(i)}" y="${height - 8}" text-anchor="middle" fill="#637360" font-size="11"${ms && newDay ? ' font-weight="600"' : ""}>${escapeHTML(text)}</text>`;
      previous = day;
    });
    const candles = points.map((bar, i) => {
      const up = bar.close >= bar.open, color = up ? "#39704b" : "#b4553f", h = (bar.volume || 0) / maxVolume * (volumeBottom - volumeTop);
      return [`<line x1="${x(i)}" x2="${x(i)}" y1="${y(bar.high)}" y2="${y(bar.low)}" stroke="${color}" vector-effect="non-scaling-stroke"/><rect x="${x(i) - body / 2}" y="${y(Math.max(bar.open, bar.close))}" width="${body}" height="${Math.max(1, Math.abs(y(bar.open) - y(bar.close)))}" fill="${color}"/>`, `<rect x="${x(i) - body / 2}" y="${volumeBottom - h}" width="${body}" height="${h}" fill="${up ? "#9ab68c" : "#c5a391"}"/>`];
    });
    const vwapPath = points.map((bar, i) => numeric(bar.vwap) ? `${numeric(points[i - 1]?.vwap) ? "L" : "M"}${x(i)} ${y(bar.vwap)}` : "").join("");
    const vwapLine = vwapPath ? `<path d="${vwapPath}" fill="none" stroke="#aa7c35" stroke-width="1.5" vector-effect="non-scaling-stroke"/>` : "";
    const sessions = points.map((bar) => ms ? barSession(bar.t) : "");
    let bands = "";
    for (let i = 0, j; i < sessions.length; i = j) {
      for (j = i + 1; j < sessions.length && sessions[j] === sessions[i]; j++);
      if (sessions[i]) bands += `<rect x="${left + step * i}" y="${top}" width="${step * (j - i)}" height="${volumeBottom - top}" fill="${sessionFill[sessions[i]]}" opacity=".45"/>`;
    }
    view.candleGeo = {points, sessions, label, width, height, left, right, top, step, priceBottom, volumeTop, volumeBottom, min, max, maxVolume};
    return `<svg viewBox="0 0 ${width} ${height}" class="live-price-chart" tabindex="0" role="img" aria-label="${points.length} candles from ${label(points[0].t)} to ${label(last.t)}. Last close ${dollars(last.close)}.">${bands}${grid}${axis}<line x1="${left}" x2="${width - right}" y1="${volumeTop - 6}" y2="${volumeTop - 6}" stroke="#dce5d9"/><clipPath id="live-price-clip"><rect x="${left}" y="${top}" width="${width - left - right}" height="${priceBottom - top}"/></clipPath>${candles.map(([, volume]) => volume).join("")}<g clip-path="url(#live-price-clip)">${candles.map(([price]) => price).join("")}${vwapLine}</g><line x1="${left}" x2="${width - right}" y1="${lastY}" y2="${lastY}" stroke="${lastColor}" stroke-dasharray="2 3" opacity=".7"/><rect x="${width - right + 4}" y="${lastY - 9}" width="${right - 6}" height="18" rx="3" fill="${lastColor}"/><text x="${width - right + 9}" y="${lastY + 4}" fill="#fff" font-size="11">${priceText(last.close)}</text>${vwapPath ? `<text x="${left + 4}" y="${top + 12}" fill="#aa7c35" font-size="10" font-weight="600">VWAP</text>` : ""}<text x="${left + 4}" y="${volumeTop + 6}" fill="#8a987c" font-size="10">Volume</text><rect class="live-price-axis" x="${width - right}" y="${top}" width="${right}" height="${priceBottom - top}" fill="transparent"><title>Drag up or down to scale prices; double-click to fit</title></rect><text x="${width - right + 10}" y="${volumeTop + 8}" fill="#637360" font-size="11">${short(maxVolume)}</text><g class="live-candle-hover" pointer-events="none">${candleHover().svg}</g></svg>`;
  }
  function candleHover() {
    // Crosshair for the candle under the pointer; the readout shows the newest candle when not hovering.
    const g = view.candleGeo, h = view.candleHover;
    if (!g) return {svg:"", text:""};
    const i = h ? Math.max(0, Math.min(g.points.length - 1, Math.floor((h.x - g.left) / g.step))) : g.points.length - 1;
    const bar = g.points[i], base = g.points[i - 1]?.close ?? bar.open, change = base ? (bar.close - base) / base * 100 : null;
    const text = `<span class="live-readout-time">${g.label(bar.t)}${g.sessions[i] ? ` · ${sessionName[g.sessions[i]]}` : ""}${bar.forming ? " · forming" : ""}</span><strong class="live-readout-price">${dollars(bar.close)}</strong><span class="live-readout-change ${direction(change)}">${pct(change)}</span><span>Open <b>${dollars(bar.open)}</b></span><span>High <b>${dollars(bar.high)}</b></span><span>Low <b>${dollars(bar.low)}</b></span><span>Volume <b>${short(bar.volume)}</b></span>${numeric(bar.vwap) ? `<span>VWAP <b>${dollars(bar.vwap)}</b></span>` : ""}`;
    if (!h) return {svg:"", text};
    const x = g.left + g.step * (i + .5), tag = (y, value, fill) => `<line x1="${g.left}" x2="${g.width - g.right}" y1="${y}" y2="${y}" stroke="#637360" stroke-dasharray="3 3" opacity=".6"/><rect x="${g.width - g.right + 4}" y="${y - 9}" width="${g.right - 6}" height="18" rx="3" fill="${fill}"/><text x="${g.width - g.right + 9}" y="${y + 4}" fill="#fff" font-size="11">${value}</text>`;
    const price = g.max - (h.y - g.top) / (g.priceBottom - g.top) * (g.max - g.min);
    let level = h.y >= g.top && h.y <= g.priceBottom ? tag(h.y, priceText(price), "#4d5d49") : "";
    if (h.y >= g.volumeTop - 6 && h.y <= g.volumeBottom) {
      // Over the volume pane, the hovered bar carries its exact share count just above it.
      const text = `${n(bar.volume)} shares`, w = text.length * 6.6 + 16, at = Math.max(g.left + w / 2, Math.min(g.width - g.right - w / 2, x));
      const y = Math.max(g.top, g.volumeBottom - (bar.volume || 0) / g.maxVolume * (g.volumeBottom - g.volumeTop) - 26);
      level = `<rect x="${at - w / 2}" y="${y}" width="${w}" height="20" rx="4" fill="#20332d"/><text x="${at}" y="${y + 14}" text-anchor="middle" fill="#fff" font-size="11.5" font-weight="600">${text}</text>`;
    }
    const when = g.label(bar.t), half = when.length * 3.6 + 10, at = Math.max(g.left + half, Math.min(g.width - g.right - half, x));
    return {svg:`<rect x="${x - g.step / 2}" y="${g.top}" width="${g.step}" height="${g.volumeBottom - g.top}" fill="#39704b" opacity=".07"/><line x1="${x}" x2="${x}" y1="${g.top}" y2="${g.volumeBottom}" stroke="#637360" stroke-dasharray="3 3" opacity=".6"/>${level}<rect x="${at - half}" y="${g.height - 21}" width="${half * 2}" height="18" rx="3" fill="#4d5d49"/><text x="${at}" y="${g.height - 8}" text-anchor="middle" fill="#fff" font-size="11">${when}</text>`, text};
  }
  function drawCandleHover() {
    const {svg, text} = candleHover(), layer = q("#live-candle-chart .live-candle-hover"), readout = q("#live-candle-readout");
    if (layer) layer.innerHTML = svg;
    if (readout) readout.innerHTML = text;
  }
  function sessionVwap(bars) {
    // Extended-hours VWAP from Alpaca's per-bar VWAP, reset each New York day at the 4 a.m. pre-market open.
    // A day is drawn only when its first bar is loaded: the previous loaded bar is from an earlier day, or it starts at 4:00.
    let day = "", value = 0, volume = 0, whole = false;
    return bars.map((bar, i) => {
      if (nyDay(bar.t) !== day) {
        day = nyDay(bar.t); value = volume = 0;
        whole = i > 0 || nyClock.format(new Date(bar.t)) <= "04:00";
      }
      value += (bar.vw ?? (bar.high + bar.low + bar.close) / 3) * (bar.volume || 0);
      volume += bar.volume || 0;
      return whole && volume ? {...bar, vwap:value / volume} : bar;
    });
  }
  function candleBody(row) {
    const ms = candleFrames.find(([tf]) => tf === view.candleTf)[2];
    const data = view.candles?.key === `${row.symbol}|${view.candleTf}` ? view.candles : null;
    if (!data) return '<p class="live-chart-empty">Loading candles…</p>';
    const bars = withLivePrice(data.bars, row, ms), all = ms ? sessionVwap(bars) : bars;
    const count = Math.min(Math.round(view.candleZoom), all.length);
    // A negative offset drags the newest candle left, leaving empty slots for upcoming candles (at least a tenth stay visible).
    view.candleOffset = Math.max(-Math.floor(count * .9), Math.min(view.candleOffset, all.length - count));
    const stop = all.length - Math.round(view.candleOffset), ahead = Math.max(0, stop - all.length);
    const note = data.loadingOlder ? "Loading older candles…" : data.exhausted && stop - count === 0 ? "Start of available history." : "";
    const chart = all.length || !data.error ? candleChart(all.slice(stop - count, stop), ms, ahead, ...(view.candleFull ? [Math.max(400, Math.round((innerWidth - 48) / 1.4)), Math.max(240, Math.round((innerHeight - 170) / 1.4))] : [760, 320]), stop - count) : "";
    return `${data.error ? `<p class="live-chart-empty">Candles unavailable: ${escapeHTML(data.error)}</p>` : ""}<div id="live-candle-readout" class="live-candle-readout" aria-hidden="true">${candleHover().text}</div>${chart}<div class="live-candle-nav"><span>${ms ? `<span class="live-session-key"><i style="background:${sessionFill.pre}"></i>Pre-market<i></i>Regular<i style="background:${sessionFill.post}"></i>After-hours</span>` : ""}${note}</span><span class="live-tf-group">${Math.round(view.candleOffset) ? '<button type="button" class="button subtle" data-live-candle-latest>Jump to latest ›</button>' : ""}<button type="button" class="button subtle" data-live-candle-zoom="1.25" aria-label="Zoom out" title="Zoom out (−)">−</button><button type="button" class="button subtle" data-live-candle-zoom="0.8" aria-label="Zoom in" title="Zoom in (+)">+</button></span></div>`;
  }
  function candleSection(row) {
    if (row.source !== "alpaca") return "";
    const buttons = candleFrames.map(([tf, text]) => `<button type="button" class="button subtle" data-live-tf="${tf}" aria-pressed="${tf === view.candleTf}">${text}</button>`).join("");
    const exit = row.chartOnly ? "✕ Close" : view.candleFull ? "Exit full screen" : "Full screen";
    return `<section class="live-report-section${view.candleFull ? " live-candle-full" : ""}"><div class="live-report-section-title"><h3>${view.candleFull ? `${escapeHTML(row.symbol)} <span>Candles · Alpaca, extended hours included</span>` : "Candles"}</h3><div class="live-tf-group"><div class="live-tf-group live-tf-segment" role="group" aria-label="Candle timeframe">${buttons}</div><button type="button" class="button subtle" data-live-candle-full>${exit}</button></div></div><div id="live-candle-chart" class="live-candle-chart">${candleBody(row)}</div><p class="field-help live-candle-help"><span>Drag or ←/→ to scroll; drag left past the newest candle for room ahead</span><span>${view.candleFull ? "Scroll" : "⌘/Ctrl + scroll"}, pinch or +/− to zoom</span><span>Drag the price axis to stretch or squash</span><span>Double-click to reset</span>${view.candleFull ? "<span>Esc to close</span>" : ""}<span>Updates every 15 seconds</span></p></section>`;
  }
  function renderCandles() {
    const box = q("#live-candle-chart");
    if (!box || view.selectedDetail?.symbol !== view.selected) return;
    const focused = document.activeElement?.closest?.("#live-candle-chart");
    box.innerHTML = candleBody(view.selectedDetail);
    if (focused) box.querySelector("svg")?.focus({preventScroll:true});
    loadOlderCandles();
  }
  function moveCandles(offset, zoom = view.candleZoom) {
    view.candleZoom = Math.max(20, Math.min(800, zoom));
    view.candleOffset = offset;
    // Gestures fire faster than the chart can redraw, so redraw at most once per frame.
    view.candleFrame ||= requestAnimationFrame(() => { view.candleFrame = 0; renderCandles(); });
  }
  function zoomCandles(factor, at = .5) {
    // `at` is the pointer's position across the plot (0 left, 1 right); the candle under it stays put.
    const bars = view.candles?.bars.length || 0, zoom = Math.max(20, Math.min(800, view.candleZoom * factor));
    moveCandles(view.candleOffset - (Math.min(zoom, bars) - Math.min(view.candleZoom, bars)) * (1 - at), zoom);
  }
  async function loadCandles(force = false) {
    const row = view.selectedDetail;
    if (!row || row.symbol !== view.selected || row.source !== "alpaca" || !q("#live-report-dialog").open || view.candleFetching) return;
    const key = `${row.symbol}|${view.candleTf}`;
    if (!force && view.candles?.key === key && Date.now() - view.candles.at < 15000) return;
    view.candleFetching = true;
    try {
      const data = await api(`/api/monitor/candles/${encodeURIComponent(row.symbol)}?timeframe=${encodeURIComponent(view.candleTf)}`);
      if (view.candles?.key === key) {
        // Keep older pages already scrolled into; newer bars replace same-time ones.
        const merged = new Map(view.candles.bars.map((bar) => [bar.t, bar]));
        data.candles.forEach((bar) => merged.set(bar.t, bar));
        Object.assign(view.candles, {bars:[...merged.values()].sort((a, b) => a.t < b.t ? -1 : 1), at:Date.now(), error:""});
      } else {
        view.candles = {key, bars:data.candles, at:Date.now(), error:"", exhausted:false, loadingOlder:false};
      }
    } catch (error) {
      if (view.candles?.key === key) Object.assign(view.candles, {at:Date.now(), error:error.message});
      else view.candles = {key, bars:[], at:Date.now(), error:error.message, exhausted:false, loadingOlder:false};
    } finally {
      view.candleFetching = false;
    }
    if (key !== `${view.selected}|${view.candleTf}`) return loadCandles(true);
    renderCandles();
  }
  async function loadOlderCandles() {
    const data = view.candles, [symbol, timeframe] = (data?.key || "").split("|");
    if (!data || data.exhausted || data.loadingOlder || !data.bars.length || data.key !== `${view.selected}|${view.candleTf}`) return;
    if (data.bars.length - view.candleOffset - view.candleZoom > 40) return;
    data.loadingOlder = true;
    try {
      const result = await api(`/api/monitor/candles/${encodeURIComponent(symbol)}?timeframe=${encodeURIComponent(timeframe)}&before=${encodeURIComponent(data.bars[0].t)}`);
      const older = result.candles.filter((bar) => bar.t < data.bars[0].t);
      data.bars = [...older, ...data.bars];
      data.exhausted = !older.length;
    } catch (error) {
      data.exhausted = true;
      data.error = `Older candles unavailable: ${error.message}`;
    } finally {
      data.loadingOlder = false;
    }
    if (view.candles === data) renderCandles();
  }
  function volumeChart(history) {
    const bars = (history || []).filter((bar) => numeric(bar.volume));
    if (!bars.length) return '<p class="live-chart-empty">Prior session volume history is unavailable.</p>';
    const max = Math.max(1, ...bars.map((bar) => bar.volume));
    return `<div class="live-volume-chart" role="img" aria-label="Daily volume across ${bars.length} prior trading sessions">${bars.map((bar) => `<div class="live-volume-bar" style="--bar-height:${Math.max(1, bar.volume / max * 100)}%" title="${date(bar.date)}: ${n(bar.volume)} shares"><span></span></div>`).join("")}</div><div class="live-chart-times"><span>${date(bars[0].date)}</span><span>${date(bars[bars.length - 1].date)}</span></div>`;
  }
  function reportMetric(label, value, note = "", cls = "") {
    return `<div class="live-report-metric"><dt>${escapeHTML(label)}</dt><dd class="${cls}">${value}</dd>${note ? `<small>${escapeHTML(note)}</small>` : ""}</div>`;
  }
  function unitLabel(unit) { return ["shares", "points"].includes(unit) ? ` ${unit}` : unit || ""; }
  function gateChecks(row) {
    return row.eligibility?.checks?.length ? `<div class="live-gate-checks">${row.eligibility.checks.map((check) => `<div><strong>${escapeHTML(check.name)}</strong><span class="${check.passed ? "positive" : "live-blocked-label"}">${numeric(check.actual) ? n(check.actual, ["shares", "points"].includes(check.unit) ? 0 : 2) : "Unavailable"}${numeric(check.actual) ? escapeHTML(unitLabel(check.unit)) : ""} · ${check.passed ? "Pass" : "Blocked"}</span><small>${check.name === "Spread maximum" ? "Maximum" : "Minimum"} ${n(check.required, ["shares", "points"].includes(check.unit) ? 0 : 2)}${escapeHTML(unitLabel(check.unit))}</small></div>`).join("")}</div>` : "";
  }
  function tradingStatusMetrics(row) {
    const status = row.trading_status, bands = row.price_bands;
    return reportMetric("Trading status", status?.available ? (status.halted ? "Halted / paused" : "Trading") : "Unavailable", status?.available ? `${status.reason || status.code} · ${clock(status.at)}` : "No current-session status event received", status?.halted ? "negative" : "") + reportMetric("Price bands", bands?.available ? `${dollars(bands.lower)}–${dollars(bands.upper)}` : "Unavailable", bands?.available ? `Event ${clock(bands.at)}` : "Requires a supported feed and dated price-band event");
  }
  function screeningReport(row) {
    return `<section class="live-report-section live-screening-report"><div class="live-report-section-title"><h3>Liquidity & volatility</h3><span>Rank ${n(row.rank)} by total day volume</span></div><p class="field-help">History through ${date(row.history_as_of)}; today excluded.</p><dl class="live-report-metrics">${reportMetric("Average volume (3-month)", n(row.avg_volume_3m), "63 prior trading sessions")}${reportMetric("Relative volume (day)", ratio(row.day_relative_volume), "Total day volume ÷ 20-session average; not time adjusted")}${reportMetric("Bid–ask spread", dollars(row.spread), `${numeric(row.spread_pct) ? n(row.spread_pct, 2) + "% of midpoint" : "Unavailable"} · quote ${clock(row.quote_at)}`)}${reportMetric("Average daily volume", n(row.avg_daily_volume), "20 prior trading sessions")}${reportMetric("Beta vs SPY", n(row.beta, 2), `${n(row.beta_observations)} paired daily price returns; up to 252, minimum 60`)}${reportMetric("Average true range (14)", dollars(row.atr), `${numeric(row.atr_pct) ? n(row.atr_pct, 2) + "% of prior close" : "Unavailable"} · Wilder smoothing`)}</dl></section>`;
  }
  function renderReport(force = false) {
    if (view.selectedDetail?.chartOnly) {
      q("#live-report-dialog").classList.add("candle-full");
      if (force || view.detailKey !== "chart") { view.detailKey = "chart"; q("#live-report-data").innerHTML = candleSection(view.selectedDetail); }
      return;
    }
    const listed = view.snapshot.rows?.some((item) => item.symbol === view.selected);
    const row = listed && view.selectedDetail?.symbol === view.selected ? view.selectedDetail : null;
    q("#live-report-dialog").classList.toggle("candle-full", view.candleFull);
    q("#live-print").disabled = !row;
    if (!row) {
      q("#live-report-data").innerHTML = listed ? '<div class="live-empty" role="status"><h3>Loading stock report…</h3><p>Retrieving this symbol’s chart and volume history.</p></div>' : '<div class="live-empty"><h3>Outside the current monitor</h3><p>This symbol’s alert is saved, but current metrics require adding it to the monitor configuration.</p></div>';
      q("#live-float-edit").classList.add("hidden");
      return;
    }
    const key = JSON.stringify(row);
    if (!force && (key === view.detailKey || view.candleDrag)) return;
    view.detailKey = key;
    const history = row.volume_history || [];
    const historyOpen = q("#live-history-details")?.open;
    const chartOpen = q("#live-report-data .live-chart-data")?.open;
    const candleFocused = document.activeElement?.closest?.("#live-candle-chart");
    const reasons = row.reasons || [], blockers = row.blockers || [], warnings = row.warnings || [];
    q("#live-report-title").textContent = `${row.symbol} · ${row.name || "Intraday report"}`;
    q("#live-float-edit").classList.toggle("hidden", row.source === "demo");
    q("#live-report-data").innerHTML = `
      <div class="live-report-source ${row.source === "demo" ? "synthetic" : ""}"><strong>${escapeHTML(sourceLabel(row.source, row.feed))}</strong><span>Session ${date(row.session_date)} · Price ${clock(row.price_at, true)}</span>${row.source === "demo" ? '<p>All values are fictional simulation data.</p>' : ""}</div>
      <div class="live-report-price"><div><strong>${dollars(row.price)}</strong><span class="${direction(row.change_pct)}">${pct(row.change_pct)} today</span></div><div><span class="live-setup ${levelClass(row.signal)}">${setup(row.signal)}</span><span>${n(row.signal_score)} / 100</span></div></div>
      <div class="live-feed-volume"><strong>Total day volume: ${n(row.day_volume)} shares</strong><span>Includes available premarket and regular trading · updated ${clock(row.day_volume_at)}${(row.day_volume_basis || row.volume_basis) ? " · " + escapeHTML((row.day_volume_basis || row.volume_basis).replaceAll("_", " ")) : ""}</span></div>${screeningReport(row)}
      <dl class="live-report-metrics">${reportMetric("Regular-session volume", n(row.session_volume), "Completed regular-session minute bars; premarket excluded from this technical measure")}${reportMetric("Float shares", n(row.float_shares), numeric(row.float_shares) ? `${row.float_source || "Source unavailable"} · as of ${row.float_as_of || "date unavailable"}` : "No usable dated float source")}${reportMetric("30-session average volume", n(row.avg_volume_30d), "30 prior trading sessions; excludes today")}${reportMetric("30-session total volume", n(row.volume_30d_total), "30 prior trading sessions; excludes today")}${reportMetric("Session relative volume", ratio(row.relative_volume), "Versus full-session 30D average; not time adjusted")}${reportMetric("1-minute relative volume", ratio(row.minute_relative_volume), "Latest completed minute / preceding 20 minutes")}${reportMetric("Opening gap", pct(row.gap_pct), "Regular open versus prior adjusted close", direction(row.gap_pct))}${reportMetric("Float turnover", ratio(row.float_turnover), "Session volume / dated float shares")}${reportMetric("Bid–ask spread", numeric(row.spread_pct) ? `${n(row.spread_pct, 2)}%` : "—", `Quote ${clock(row.quote_at)}`)}${reportMetric("Session VWAP", dollars(row.vwap), "Volume-weighted minute bars since the 4 a.m. pre-market open")}${reportMetric("EMA 9 / EMA 20", `${dollars(row.ema9)} / ${dollars(row.ema20)}`, "Completed minute closes")}${reportMetric("RSI", n(row.rsi, 1), "Minute momentum oscillator")}${tradingStatusMetrics(row)}</dl>
      ${candleSection(row)}
      <section class="live-report-section"><div class="live-report-section-title"><h3>Intraday price</h3><span>Completed 1-minute closes</span></div>${lineChart(row.chart, (view.snapshot.alerts || []).filter((alert) => alert.symbol === row.symbol && alert.source === row.source && alert.session_date === row.session_date))}</section>
      <section class="live-report-section"><div class="live-report-section-title"><h3>Participation over 30 sessions</h3><span>Prior sessions · today excluded</span></div>${volumeChart(history)}<details id="live-history-details" ${historyOpen ? "open" : ""}><summary>Show exact daily volumes (${history.length} sessions)</summary><table class="live-history-table"><thead><tr><th>Trading session</th><th class="live-num">Volume (shares)</th></tr></thead><tbody>${history.map((bar) => `<tr><td>${date(bar.date)}</td><td class="live-num">${n(bar.volume)}</td></tr>`).join("")}</tbody></table></details></section>
      <section class="live-report-section live-score-section"><div class="live-report-section-title"><h3>Inside the technical setup</h3><span>${n(row.signal_score)} / 100 · heuristic score</span></div><div class="live-form-note">${eligibilityText(row)}</div>${gateChecks(row)}${row.signals?.length ? `<div class="live-score-breakdown">${row.signals.map((signal) => `<div><span><strong>${escapeHTML(signal.name)}</strong><small>${escapeHTML(signal.description)}</small></span><span>${n(signal.points)} / ${n(signal.max_points)}</span></div>`).join("")}</div>` : ""}${reasons.length ? `<h4>Supporting conditions</h4><ul>${reasons.map((reason) => `<li>${escapeHTML(reason)}</li>`).join("")}</ul>` : ""}${blockers.length ? `<div class="live-blockers"><h4>Why this is not alert eligible</h4><ul>${blockers.map((reason) => `<li>${escapeHTML(reason)}</li>`).join("")}</ul></div>` : `<p class="live-eligible-note">${row.alert_eligible ? "Data and technical gates pass. Saved alerts still require consecutive confirmation bars and obey the repeat cooldown." : "This stock is not eligible for a technical setup alert."}</p>`}${warnings.length ? `<div class="live-blockers"><h4>Data notes</h4><ul>${warnings.map((warning) => `<li>${escapeHTML(warning)}</li>`).join("")}</ul></div>` : ""}</section>
      <div class="live-report-foot"><p>Price: ${clock(row.price_at, true)} · quote: ${clock(row.quote_at)} · volume through: ${clock(row.volume_at)} · signal bar: ${clock(row.signal_bar_at)}.</p><p>${row.stale ? "Market data is stale or incomplete. " : ""}${row.market_open ? "Regular session." : "Outside the current regular session."} A dash means unavailable. Technical setup scores are not calibrated return forecasts. Check news, spread, filings, and trading halts before making a decision.</p></div>`;
    if (chartOpen && q("#live-report-data .live-chart-data")) q("#live-report-data .live-chart-data").open = true;
    if (candleFocused) q("#live-candle-chart svg")?.focus({preventScroll:true});
  }
  function showChart(symbol) {
    // Full-screen candles for a symbol outside the monitor, such as a daily screener result.
    view.selected = symbol;
    // A monitored symbol's newest candle follows its live trades while they are fresh.
    const live = view.snapshot?.rows?.find((item) => item.symbol === symbol && !item.stale);
    view.selectedDetail = {price:live?.price, price_at:live?.price_at, symbol, source:"alpaca", chartOnly:true};
    view.candleFull = true;
    view.candleOffset = 0;
    view.candleScale = 1;
    view.candleHover = null;
    q("#live-report-title").textContent = `${symbol} · Candles`;
    renderReport(true);
    openDialog(q("#live-report-dialog"), "[data-live-candle-full]");
    loadCandles(true);
  }
  function showStock(symbol) {
    view.selected = symbol;
    view.selectedDetail = null;
    view.detailReceivedAt = 0;
    view.detailKey = "";
    showError("#live-report-error", "");
    q("#live-report-title").textContent = `${symbol} · Intraday report`;
    q("#live-float-form").reset();
    showError("#live-float-error", "");
    q("#live-float-saved").textContent = "";
    const row = view.snapshot?.rows?.find((item) => item.symbol === symbol);
    q("#live-float-date").max = new Date().toLocaleDateString("en-CA", {timeZone:"America/New_York"});
    if (row?.float_source === "Manual") { q("#live-float-shares").value = row.float_shares || ""; q("#live-float-date").value = row.float_as_of || ""; }
    renderReport(true);
    openDialog(q("#live-report-dialog"), "#live-print");
    fetchSelectedDetail(true);
  }
  async function fetchSelectedDetail(force = false) {
    if (!view.selected || !q("#live-report-dialog").open || document.hidden || document.body.classList.contains("printing-live-report")) return;
    if (view.detailFetching || (!force && Date.now() - view.detailReceivedAt < 2000)) return;
    if (view.selectedDetail?.chartOnly) {
      const live = view.snapshot?.rows?.find((item) => item.symbol === view.selected && !item.stale);
      if (live && live.price_at !== view.selectedDetail.price_at) { Object.assign(view.selectedDetail, {price:live.price, price_at:live.price_at}); renderCandles(); }
      loadCandles();
      return;
    }
    const selected = view.selected;
    const summary = view.snapshot?.rows?.find((row) => row.symbol === selected);
    if (!summary) { view.selectedDetail = null; renderReport(); return; }
    if (!view.snapshot.status.refresh && Array.isArray(summary.chart)) {
      view.selectedDetail = summary;
      view.detailReceivedAt = Date.now();
      renderReport();
      loadCandles();
      return;
    }
    view.detailFetching = true;
    try {
      const data = await api(`/api/monitor/symbol/${encodeURIComponent(selected)}`);
      if (selected !== view.selected) return;
      view.selectedDetail = data.row;
      view.detailReceivedAt = Date.now();
      showError("#live-report-error", "");
      renderReport();
      loadCandles();
    } catch (error) {
      if (selected === view.selected) {
        view.detailReceivedAt = Date.now();
        showError("#live-report-error", `Cannot refresh this report: ${error.message}`);
        if (!view.selectedDetail) q("#live-report-data").innerHTML = '<div class="live-empty"><p>Report data could not load. Retrying while this report is open.</p></div>';
      }
    } finally {
      view.detailFetching = false;
      if (selected !== view.selected) fetchSelectedDetail(true);
    }
  }
  function recordAlertRefresh(previousIds, source) {
    const added = currentAlerts().filter((alert) => !previousIds.has(alert.id)).length;
    const result = source !== view.snapshot.config.source ? "Saved alerts reloaded."
      : added ? `${n(added)} new ${added === 1 ? "setup" : "setups"}.` : "No new setups.";
    view.alertRefreshMessage = `Checked ${clock(new Date().toISOString())} · ${result}`;
  }
  async function refreshAlerts() {
    if (view.alertsRefreshing || view.refreshing || view.action) return;
    const previousIds = new Set(currentAlerts().map((alert) => alert.id));
    const source = view.snapshot?.config.source;
    view.alertsRefreshing = true;
    showError("#live-error", "");
    render();
    try {
      accept(await api("/api/monitor?compact=1"));
      recordAlertRefresh(previousIds, source);
    } catch (error) {
      showError("#live-error", `Cannot refresh setup alerts: ${error.message}`);
      view.alertRefreshMessage = "Alert refresh failed. Try again.";
    } finally { view.alertsRefreshing = false; render(); }
  }
  async function refreshData() {
    if (view.refreshing || view.alertsRefreshing || view.snapshot?.status.refresh?.state === "loading") return;
    const previousIds = new Set(currentAlerts().map((alert) => alert.id));
    const source = view.snapshot?.config.source;
    view.refreshing = true;
    showError("#live-error", "");
    render();
    try {
      let snapshot = await api("/api/monitor/refresh", {});
      const startedAt = snapshot.status.refresh.started_at;
      const deadline = Date.now() + 300000;
      accept(snapshot);
      // Explicitly read completion and the saved inbox even if the background
      // stream is interrupted. The POST may return before new alerts are saved.
      do {
        if (Date.now() >= deadline) throw new Error("Data refresh is still running. Updates will continue automatically; use Setup alerts Refresh to check saved alerts.");
        if (snapshot.status.refresh.state === "loading") await new Promise((resolve) => setTimeout(resolve, 1000));
        snapshot = await api("/api/monitor?compact=1");
        accept(snapshot);
        if (snapshot.status.refresh?.started_at !== startedAt) throw new Error("The monitor session changed during refresh. Try again once connected.");
      } while (snapshot.status.refresh.state === "loading");
      if (snapshot.status.refresh.state !== "completed") throw new Error(snapshot.status.refresh.error || "Data refresh was cancelled. Try again once connected.");
      recordAlertRefresh(previousIds, source);
      await pollDiscovery();
      await fetchSelectedDetail(true);
    } catch (error) {
      showError("#live-error", error.message);
      view.alertRefreshMessage = "Data refresh did not finish. Use Refresh here to check saved setup alerts.";
    }
    finally { view.refreshing = false; render(); }
  }
  function providerHelp() {
    const demo = q("#live-source").value === "demo";
    const provider = view.snapshot?.provider_status || {};
    const configurationLocation = window.nomismaDesktop?.configFile ? `<code>${escapeHTML(window.nomismaDesktop.configFile)}</code> (${window.nomismaDesktop.platform === "windows" ? "File" : "Nomisma"} menu → Open Configuration Folder)` : ".env in the Nomisma folder";
    q("#live-provider-help").innerHTML = demo
      ? "The demo runs fictional penny stocks on an advancing historical clock. No market connection is used."
      : `${provider.alpaca_configured ? `<strong>Alpaca credentials are configured.</strong> Feed: ${escapeHTML(String(provider.feed || "iex").toUpperCase())}.` : `<strong>Alpaca credentials are not configured.</strong> Add ALPACA_API_KEY and ALPACA_SECRET_KEY to ${configurationLocation}, then restart the local server.`} ${provider.feed === "sip" ? "Real-time SIP access requires the appropriate data entitlement." : "IEX volume covers one exchange. Use an entitled SIP feed for consolidated volume."} Float data is ${provider.float_configured ? "available through your optional FMP configuration when the provider supplies it" : "optional: configure FMP_API_KEY or enter a dated float value in a stock report"}. Nomisma supports up to 50 symbols; Alpaca Basic permits 30 live subscriptions. Larger lists require the appropriate data plan. <strong>Use real ticker symbols below; replace any synthetic demo symbols.</strong>`;
  }
  function showConfig() {
    if (!view.snapshot) return;
    const form = q("#live-config-form");
    for (const [key, value] of Object.entries(view.snapshot.config)) {
      const field = form.elements.namedItem(key);
      if (!field) continue;
      if (field.type === "checkbox") field.checked = value;
      else field.value = Array.isArray(value) ? value.join(", ") : value;
    }
    showError("#live-config-error", "");
    q("#live-import-note").textContent = "";
    providerHelp();
    openDialog(q("#live-config-dialog"), view.snapshot.status.running ? "[data-live-close]" : "#live-source");
  }
  function readConfig() {
    const form = q("#live-config-form");
    const result = {};
    for (const key of Object.keys(view.snapshot.config)) {
      const field = form.elements.namedItem(key);
      if (!field) continue;
      result[key] = key === "symbols" ? symbolList(field.value) : key === "source" ? field.value : field.type === "checkbox" ? field.checked : Number(field.value);
    }
    if (!result.symbols.length || result.symbols.length > symbolLimit()) throw new Error(`Enter between 1 and ${symbolLimit()} unique symbols.`);
    if (result.min_price > result.max_price) throw new Error("Minimum price must not exceed maximum price.");
    if (result.buy_score >= result.strong_buy_score) throw new Error("Strong buy score must be higher than Buy score.");
    return result;
  }
  async function importSymbols(kind) {
    try {
      const bootstrap = await api("/api/bootstrap");
      const all = kind === "watchlist" ? bootstrap.watchlist || [] : (bootstrap.latest?.results || []).map((row) => row.symbol);
      if (!all.length) throw new Error(kind === "watchlist" ? "Your watchlist is empty. Star symbols in the daily screener first." : "The latest daily scan has no matching symbols. Run the daily screener first.");
      q("#live-symbols").value = all.slice(0, symbolLimit()).join(", ");
      q("#live-import-note").textContent = `Loaded ${Math.min(symbolLimit(), all.length)} symbols${all.length > symbolLimit() ? ` from ${all.length}; only the first ${symbolLimit()} fit` : ""}. Review the source and price range before saving.`;
      showError("#live-config-error", "");
    } catch (error) { showError("#live-config-error", error.message); }
  }
  async function setRunning(running) {
    view.action = true;
    showError("#live-error", "");
    render();
    try {
      const snapshot = await api(`/api/monitor/${running ? "start" : "stop"}`, {});
      accept(snapshot);
    } catch (error) { showError("#live-error", error.message); }
    finally { view.action = false; render(); }
  }
  async function acknowledge(body) {
    const source = view.snapshot.config.source;
    try {
      const result = await api("/api/monitor/alerts/ack", {...body, source});
      if (view.snapshot.config.source !== source) return;
      view.snapshot.alerts = currentAlerts({...view.snapshot, alerts:result.alerts || []});
      render();
    } catch (error) { showError("#live-error", error.message); }
  }
  async function exportRows() {
    try {
      const response = await fetch("/api/monitor/export.csv", {cache:"no-store"});
      if (!response.ok) throw new Error("Could not export the current monitor. Try again.");
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url; link.download = `nomisma-intraday-${view.snapshot.status.session?.date || "monitor"}.csv`;
      document.body.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) { showError("#live-error", error.message); }
  }
  async function saveFloat(clear = false) {
    const form = q("#live-float-form");
    const buttons = [...form.querySelectorAll("button")];
    buttons.forEach((button) => { button.disabled = true; });
    showError("#live-float-error", "");
    try {
      const body = {symbol:view.selected, shares:clear ? null : Number(q("#live-float-shares").value)};
      if (!clear) body.as_of = q("#live-float-date").value;
      await api("/api/monitor/float", body);
      q("#live-float-saved").textContent = clear ? "Manual override cleared. The next data update will use available provider float." : "Dated manual float saved. It will appear in current or subsequent market data updates.";
      if (clear) form.reset();
      await fetchSnapshot();
      await fetchSelectedDetail(true);
    } catch (error) { showError("#live-float-error", error.message); }
    finally { buttons.forEach((button) => { button.disabled = false; }); }
  }
  function notify(item) {
    // Never replay persisted alerts, alert on a demo, or request permissions implicitly.
    if (item.source !== "alpaca" || view.snapshot?.config.source !== "alpaca") return;
    if (view.notifications && "Notification" in window && Notification.permission === "granted") {
      try {
        const notification = new Notification(`${item.symbol} · ${setup(item.level)}`, {body:`${dollars(item.price)} · ${n(item.score)}/100 · ${(item.reasons || []).slice(0, 2).join(" · ")}`, tag:`nomisma-${item.id}`});
        notification.onclick = () => { window.focus(); location.hash = "live"; showStock(item.symbol); notification.close(); };
      } catch (_) { /* Permission and browser restrictions do not interrupt monitoring. */ }
    }
    if (view.sound && view.audio?.state === "running") {
      const oscillator = view.audio.createOscillator(), gain = view.audio.createGain();
      oscillator.connect(gain); gain.connect(view.audio.destination);
      oscillator.frequency.setValueAtTime(item.level === "Strong buy" ? 880 : 660, view.audio.currentTime);
      gain.gain.setValueAtTime(.045, view.audio.currentTime);
      gain.gain.exponentialRampToValueAtTime(.001, view.audio.currentTime + .3);
      oscillator.start(); oscillator.stop(view.audio.currentTime + .3);
    }
  }
  function renderNotificationNote() {
    const note = view.snapshot?.config.source === "demo"
      ? "Demo alerts are synthetic and stay in this demo inbox. Desktop alerts and sound apply only to new Alpaca setups."
      : view.notifications || view.sound
      ? "Only new Alpaca setups can trigger enabled desktop alerts or sound. Saved history is not replayed."
      : `Opt in for this ${window.nomismaDesktop ? "desktop window" : "browser tab"}. Only new Alpaca setups can trigger desktop alerts or sound.`;
    q("#live-notification-note").textContent = [view.notificationMessage, note].filter(Boolean).join(" ");
  }
  async function toggleNotifications() {
    view.notificationMessage = "";
    if (view.notifications) view.notifications = false;
    else if (!("Notification" in window)) view.notificationMessage = "Desktop notifications are unavailable in this browser. Your saved inbox remains active.";
    else {
      try {
        const permission = Notification.permission === "granted" ? "granted" : await Notification.requestPermission();
        view.notifications = permission === "granted";
        const permissionHelp = window.nomismaDesktop?.platform === "windows" ? "Windows notification settings control delivery" : window.nomismaDesktop ? "macOS System Settings → Notifications → Nomisma controls permission" : "Browser site settings control permission";
        view.notificationMessage = view.notifications ? "" : `Notifications were not enabled. ${permissionHelp}; your inbox remains active.`;
      } catch (_) { view.notificationMessage = "Desktop permission could not be enabled. Use the saved inbox."; }
    }
    q("#live-notifications").setAttribute("aria-pressed", String(view.notifications));
    q("#live-notifications span").textContent = view.notifications ? "On" : "Off";
    renderNotificationNote();
  }
  async function toggleSound() {
    view.notificationMessage = "";
    if (view.sound) view.sound = false;
    else {
      try {
        const Audio = window.AudioContext || window.webkitAudioContext;
        if (!Audio) throw new Error("Sound is not supported in this browser.");
        if (!view.audio) view.audio = new Audio();
        await view.audio.resume();
        view.sound = view.audio.state === "running";
      } catch (error) { view.notificationMessage = error.message; }
    }
    q("#live-sound").setAttribute("aria-pressed", String(view.sound));
    q("#live-sound span").textContent = view.sound ? "On" : "Off";
    renderNotificationNote();
  }
  async function fetchSnapshot() {
    if (view.fetching) return;
    view.fetching = true;
    try {
      accept(await api("/api/monitor?compact=1"));
      if (q("#live-error").textContent.startsWith("Cannot update the monitor:")) showError("#live-error", "");
    }
    catch (error) { showError("#live-error", `Cannot update the monitor: ${error.message}`); view.baseline = false; }
    finally { view.fetching = false; }
  }
  function poll() {
    clearTimeout(view.pollTimer);
    view.pollTimer = setTimeout(async () => { await fetchSnapshot(); if (view.transport === "polling") poll(); }, 2000);
  }
  function stream() {
    if (!("EventSource" in window)) { view.transport = "polling"; poll(); return; }
    clearTimeout(view.retryTimer);
    view.events?.close();
    const events = new EventSource("/api/monitor/events?compact=1");
    view.events = events;
    events.addEventListener("monitor", (event) => {
      try { view.transport = "streaming"; clearTimeout(view.pollTimer); accept(JSON.parse(event.data)); }
      catch (_) { /* A malformed event never replaces the last valid snapshot. */ }
    });
    events.onerror = () => {
      events.close(); view.transport = "polling"; view.baseline = false; view.freshSince = Date.now();
      poll();
      view.retryTimer = setTimeout(stream, 30000);
      renderFreshness();
    };
  }
  function bind() {
    q("#live-refresh").addEventListener("click", refreshData);
    q("#live-alert-refresh").addEventListener("click", refreshAlerts);
    q("#live-schedule-open").addEventListener("click", showDiscovery);
    q("#live-schedule-form").addEventListener("submit", saveSchedule);
    q("#live-diagnostics").addEventListener("click", diagnose);
    q("#live-retest").addEventListener("click", diagnose);
    q("#live-discover").addEventListener("click", showDiscovery);
    q("#live-discovery-form").addEventListener("submit", discover);
    q("#live-discovery-universe").addEventListener("change", (event) => q("#live-discovery-custom").classList.toggle("hidden", event.target.value !== "custom"));
    q("#live-use-candidates").addEventListener("click", useCandidates);
    q("#live-extra-columns").addEventListener("change", (event) => { view.extraColumns = event.target.checked; if (view.snapshot) renderTable(); });
    q("#live-journal").addEventListener("click", () => { location.hash = "journal"; });
    q("#live-edit-rules").addEventListener("click", showConfig);
    window.nomismaJournal = () => loadJournal(view.journal.offset);
    q("#live-journal-prev").addEventListener("click", () => loadJournal(view.journal.offset - view.journal.limit));
    q("#live-journal-next").addEventListener("click", () => loadJournal(view.journal.offset + view.journal.limit));
    q("#live-evidence-refresh").addEventListener("click", () => { if (view.savedAlert) showEvidence(view.savedAlert); });
    document.addEventListener("change", (event) => {
      if (event.target.id === "live-candidate-sort") {
        view.candidateSort = event.target.value;
        renderCandidateTable();
        return;
      }
      if (!event.target.matches("[data-live-candidate]")) return;
      const field = event.target;
      if (field.checked && view.candidates.size < symbolLimit()) view.candidates.add(field.dataset.liveCandidate);
      else { view.candidates.delete(field.dataset.liveCandidate); field.checked = false; }
      candidateSelection();
    });
    q("#live-config").addEventListener("click", showConfig);
    q("#live-source").addEventListener("change", providerHelp);
    q("#live-start").addEventListener("click", () => setRunning(true));
    q("#live-stop").addEventListener("click", () => setRunning(false));
    q("#live-export").addEventListener("click", exportRows);
    q("#live-scan").addEventListener("click", scanRadar);
    q("#live-search").addEventListener("input", (event) => { view.query = event.target.value.trim().toLowerCase(); if (view.snapshot) renderTable(); });
    q("#live-sort").addEventListener("change", (event) => { view.sort = event.target.value; if (view.snapshot) renderTable(); });
    q("#live-ack-all").addEventListener("click", () => acknowledge({all:true}));
    q("#live-notifications").addEventListener("click", toggleNotifications);
    q("#live-sound").addEventListener("click", toggleSound);
    q("#live-use-watchlist").addEventListener("click", () => importSymbols("watchlist"));
    q("#live-use-scan").addEventListener("click", () => importSymbols("scan"));
    q("#live-config-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      q("#live-save-config").disabled = true;
      try {
        const config = readConfig();
        const response = await api("/api/monitor/config", config);
        view.snapshot.config = response.config;
        q("#live-config-dialog").close();
        await fetchSnapshot();
      } catch (error) { showError("#live-config-error", error.message); }
      finally { q("#live-save-config").disabled = !!view.snapshot?.status.running; }
    });
    q("#live-float-form").addEventListener("submit", (event) => { event.preventDefault(); saveFloat(); });
    q("#live-clear-float").addEventListener("click", () => saveFloat(true));
    q("#live-print").addEventListener("click", async () => {
      const history = q("#live-history-details");
      const wasOpen = history?.open;
      if (history) history.open = true;
      document.body.classList.add("printing-live-report");
      try {
        if (window.nomismaDesktop) await window.nomismaDesktop.print();
        else window.print();
      } finally {
        document.body.classList.remove("printing-live-report");
        // Live updates can replace the report while the native print panel is open.
        const currentHistory = q("#live-history-details");
        if (currentHistory) currentHistory.open = wasOpen;
      }
    });
    window.addEventListener("afterprint", () => document.body.classList.remove("printing-live-report"));
    for (const dialog of document.querySelectorAll("#live-config-dialog, #live-report-dialog, .live-research-modal")) {
      dialog.addEventListener("close", () => { state.lastFocus.get(dialog)?.focus({preventScroll:true}); });
      dialog.addEventListener("click", (event) => {
        if (event.target !== dialog) return;
        const bounds = dialog.getBoundingClientRect();
        if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
      });
    }
    document.addEventListener("click", (event) => {
      const close = event.target.closest("[data-live-close]");
      if (close) close.closest("dialog").close();
      const candles = event.target.closest("[data-live-candles]");
      if (candles) window.nomismaCandles(candles.dataset.liveCandles);
      const stock = event.target.closest("[data-live-symbol]");
      if (stock && view.snapshot) selectFocus(stock.dataset.liveSymbol);
      const focusFrame = event.target.closest("[data-live-focus-tf]");
      if (focusFrame) { view.focusTf = focusFrame.dataset.liveFocusTf; renderFocus(); loadFocus(); }
      const report = event.target.closest("[data-live-report]");
      if (report && view.snapshot) showStock(report.dataset.liveReport);
      const menu = event.target.closest(".live-menu-list button")?.closest("details");
      if (menu) menu.open = false;
      const alert = event.target.closest("[data-live-alert]");
      if (alert) showEvidence(alert.dataset.liveAlert);
      const ack = event.target.closest("[data-live-ack]");
      if (ack) acknowledge({id:ack.dataset.liveAck});
      const frame = event.target.closest("[data-live-tf]");
      if (frame) { view.candleTf = frame.dataset.liveTf; view.candleOffset = 0; view.candleScale = 1; renderReport(true); loadCandles(true); }
      if (event.target.closest("[data-live-candle-latest]")) moveCandles(0);
      if (event.target.closest("[data-live-candle-full]") && view.selectedDetail?.chartOnly) q("#live-report-dialog").close();
      else if (event.target.closest("[data-live-candle-full]")) {
        view.candleFull = !view.candleFull;
        screenFull(view.candleFull);
        renderReport(true);
      }
      const zoom = event.target.closest("[data-live-candle-zoom]");
      if (zoom) zoomCandles(Number(zoom.dataset.liveCandleZoom), 1);
    });
    document.addEventListener("dblclick", (event) => {
      if (!event.target.closest("#live-candle-chart svg")) return;
      view.candleScale = 1;
      if (event.target.closest(".live-price-axis")) moveCandles(view.candleOffset); else moveCandles(0, 120);
    });
    // Without the Fullscreen API (desktop web views), Esc leaves the chart overlay instead of closing the report.
    q("#live-report-dialog").addEventListener("cancel", (event) => { if (view.candleFull && !view.selectedDetail?.chartOnly) { event.preventDefault(); view.candleFull = false; screenFull(false); renderReport(true); } });
    // The report dialog fills the window around the chart; the desktop window or browser then fills the screen.
    const screenFull = (on) => window.nomismaDesktop?.fullScreen ? window.nomismaDesktop.fullScreen(on).catch(() => {})
      : on ? q("#live-report-dialog").requestFullscreen?.().catch(() => {}) : document.fullscreenElement && document.exitFullscreen();
    // Only an exit from this dialog's own full screen counts; a late event from a closed chart must not close a new one.
    let fullscreen = false;
    const leaveFull = () => {
      if (document.fullscreenElement) { fullscreen = document.fullscreenElement === q("#live-report-dialog"); return; }
      if (!fullscreen || !view.candleFull) return;
      fullscreen = false;
      if (view.selectedDetail?.chartOnly) q("#live-report-dialog").close();
      else { view.candleFull = false; renderReport(true); }
    };
    document.addEventListener("fullscreenchange", leaveFull);
    q("#live-report-dialog").addEventListener("close", () => {
      // The close event arrives a task later; if a chart has reopened the dialog since, it is not closed any more.
      if (q("#live-report-dialog").open) return;
      fullscreen = false;
      if (view.candleFull) { view.candleFull = false; screenFull(false); }
      if (view.selectedDetail?.chartOnly) { view.selected = view.selectedDetail = null; view.detailKey = ""; q("#live-report-dialog").classList.remove("candle-full"); }
    });
    window.nomismaCandles = (symbol) => { showChart(symbol); screenFull(true); };
    window.addEventListener("resize", () => { if (view.candleFull) renderCandles(); });
    // Candle chart markup is replaced on every update, so its gestures are delegated from the document.
    const candlePlot = (clientX) => {
      // Pixels per candle and the pointer's position across the plot area (12 units left, 70 right of the viewBox).
      const svg = q("#live-candle-chart svg"), w = svg?.viewBox.baseVal.width || 760, rect = svg?.getBoundingClientRect() || {left:0, width:w};
      const count = (Math.min(Math.round(view.candleZoom), view.candles?.bars.length || 1) || 1) + candleRoom;
      return {step:rect.width * ((w - 82) / w) / count, at:Math.max(0, Math.min(1, ((clientX - rect.left) * w / rect.width - 12) / (w - 82)))};
    };
    document.addEventListener("pointerdown", (event) => {
      const svg = event.target.closest("#live-candle-chart svg");
      if (event.button !== 0 || !svg) return;
      view.candleDrag = event.target.closest(".live-price-axis") ? {y:event.clientY, scale:view.candleScale} : {x:event.clientX, offset:view.candleOffset, step:candlePlot(event.clientX).step};
      svg.focus({preventScroll:true});
      event.preventDefault();
    });
    document.addEventListener("pointermove", (event) => {
      const svg = event.target.closest?.("#live-candle-chart svg");
      if (svg) {
        const r = svg.getBoundingClientRect(), box = svg.viewBox.baseVal;
        view.candleHover = {x:(event.clientX - r.left) * box.width / r.width, y:(event.clientY - r.top) * box.height / r.height};
        drawCandleHover();
      } else if (view.candleHover && !view.candleDrag) { view.candleHover = null; drawCandleHover(); }
      if (view.candleDrag?.scale) {
        // Dragging the price axis down widens the price range (shorter candles); up narrows it (taller candles).
        view.candleScale = Math.max(.1, Math.min(10, view.candleDrag.scale * Math.exp((event.clientY - view.candleDrag.y) * .006)));
        moveCandles(view.candleOffset);
      } else if (view.candleDrag) moveCandles(view.candleDrag.offset + (event.clientX - view.candleDrag.x) / view.candleDrag.step);
    });
    document.addEventListener("pointerup", () => { view.candleDrag = null; });
    // The chart is replaced under the pointer on updates, so leaving it is detected by moves elsewhere or leaving the window.
    document.addEventListener("pointerout", (event) => { if (!event.relatedTarget && view.candleHover && !view.candleDrag) { view.candleHover = null; drawCandleHover(); } });
    document.addEventListener("wheel", (event) => {
      if (!event.target.closest("#live-candle-chart svg")) return;
      const unit = event.deltaMode ? 16 : 1, dx = (event.shiftKey ? event.deltaY : event.deltaX) * unit, dy = event.shiftKey ? 0 : event.deltaY * unit;
      const zooming = event.ctrlKey || event.metaKey || view.candleFull;  // pinch arrives as ctrl+wheel
      if (Math.abs(dx) > Math.abs(dy)) { event.preventDefault(); moveCandles(view.candleOffset - dx / candlePlot(event.clientX).step); return; }
      if (!zooming) return;  // plain scrolling keeps scrolling the report
      event.preventDefault();
      zoomCandles(Math.exp(Math.max(-100, Math.min(100, dy)) * (event.ctrlKey ? .01 : .002)), candlePlot(event.clientX).at);
    }, {passive:false});
    document.addEventListener("keydown", (event) => {
      if (!view.candleFull && !event.target.closest?.("#live-candle-chart svg")) return;
      const pan = Math.max(1, Math.round(view.candleZoom / 10)), zoom = {"+":.8, "=":.8, "-":1.25}[event.key];
      const moves = {ArrowLeft:[view.candleOffset + pan], ArrowRight:[view.candleOffset - pan], End:[0], Home:[Infinity]};
      if (!zoom && !moves[event.key]) return;
      event.preventDefault();
      if (zoom) zoomCandles(zoom, 1); else moveCandles(...moves[event.key]);
    });
    document.addEventListener("visibilitychange", () => {
      // Resuming an inactive tab establishes a new inbox baseline, avoiding catch-up notifications.
      if (!document.hidden) { view.baseline = false; view.freshSince = Date.now(); fetchSnapshot(); }
    });
    window.addEventListener("pagehide", () => { view.events?.close(); clearTimeout(view.pollTimer); clearTimeout(view.retryTimer); clearTimeout(view.discoveryTimer); });
    window.addEventListener("pageshow", (event) => { if (event.persisted) { view.baseline = false; view.freshSince = Date.now(); fetchSnapshot().then(stream); pollDiscovery(); } });
    setInterval(renderFreshness, 1000);
    setInterval(() => fetchSelectedDetail(), 2000);
    setInterval(loadFocus, 5000);
    setInterval(loadPulse, 30000);
    // SSE comment heartbeats are invisible to EventSource. Verify quiet streams
    // periodically without treating an unchanged stopped session as disconnected.
    setInterval(() => { if (Date.now() - view.receivedAt > 15000 && !document.hidden) fetchSnapshot(); }, 10000);
  }
  mount(); mountResearch(); bind();
  q("#live-sort").value = view.sort;
  fetchSnapshot().then(stream);
  pollDiscovery();
  loadPulse();
})();
