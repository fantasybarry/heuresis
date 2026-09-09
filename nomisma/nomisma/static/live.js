/* Intraday monitoring is deliberately independent of the completed daily screener. */
(() => {
  "use strict";
  const q = (selector, parent = document) => parent.querySelector(selector);
  const html = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}[char]));
  const finite = (value) => typeof value === "number" && Number.isFinite(value);
  const n = (value, digits = 0) => finite(value) ? value.toLocaleString("en-US", {maximumFractionDigits:digits, minimumFractionDigits:digits}) : "—";
  const short = (value) => finite(value) ? Intl.NumberFormat("en-US", {notation:"compact", maximumFractionDigits:2}).format(value) : "—";
  const dollars = (value) => finite(value) ? `$${n(value, value < 1 ? 4 : 2)}` : "—";
  const pct = (value) => finite(value) ? `${value > 0 ? "+" : ""}${n(value, 2)}%` : "—";
  const ratio = (value) => finite(value) ? `${n(value, 2)}×` : "—";
  const direction = (value) => finite(value) && value < 0 ? "negative" : finite(value) && value > 0 ? "positive" : "neutral";
  const clock = (value, full = false) => {
    if (!value) return "Unavailable";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Unavailable";
    return date.toLocaleString("en-US", {timeZone:"America/New_York", ...(full ? {month:"short", day:"numeric", year:"numeric"} : {}), hour:"numeric", minute:"2-digit", second:"2-digit"}) + " ET";
  };
  const date = (value) => value ? html(String(value).slice(0, 10)) : "Unavailable";
  const symbolList = (value) => [...new Set(String(value).toUpperCase().split(/[\s,;]+/).filter(Boolean))];
  const sourceLabel = (source, feed) => source === "demo" ? "Synthetic demo" : `Alpaca · ${String(feed || "market data").toUpperCase()}`;
  const setup = (level) => level === "Strong buy" ? "Strong buy setup" : level === "Buy" ? "Buy setup" : "Watch";
  const levelClass = (level) => level === "Strong buy" ? "strong" : level === "Buy" ? "buy" : "watch";
  const unavailable = "Unavailable: the provider has not supplied a usable value or enough history.";
  const view = {
    snapshot:null, selected:null, sort:"signal_score", query:"", events:null, pollTimer:null,
    retryTimer:null, fetching:false, receivedAt:0, transport:"connecting", action:false,
    baseline:false, seen:new Set(), freshSince:Date.now(), alertsKey:"", detailKey:"",
    notifications:false, sound:false, audio:null, lastFocus:new WeakMap()
  };

  async function request(path, body) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(path, {method:body === undefined ? "GET" : "POST", headers:{Accept:"application/json", ...(body === undefined ? {} : {"Content-Type":"application/json"})}, body:body === undefined ? undefined : JSON.stringify(body), cache:"no-store", signal:controller.signal});
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || `Request failed (${response.status}).`);
      return result;
    } catch (error) {
      if (error.name === "AbortError") throw new Error("The monitor request timed out. Check that Nomisma is running.");
      throw error;
    } finally { clearTimeout(timeout); }
  }
  function errorAt(id, message) {
    const element = q(id);
    element.textContent = message || "";
    element.classList.toggle("hidden", !message);
  }
  function openDialog(dialog, selector) {
    view.lastFocus.set(dialog, document.activeElement);
    if (!dialog.open) dialog.showModal();
    if (selector) requestAnimationFrame(() => q(selector, dialog)?.focus());
  }
  function mount() {
    q("#live-view").innerHTML = `
      <div id="live-error" class="alert error hidden" role="alert"></div>
      <div id="live-announcement" class="sr-only" role="status" aria-live="polite" aria-atomic="true"></div>
      <section class="live-command" aria-label="Monitor controls">
        <div class="live-command-status"><span class="live-state-dot" id="live-state-dot"></span><div><strong id="live-connection">Loading monitor</strong><span id="live-status-message">Reading your saved configuration…</span></div></div>
        <div class="live-command-actions"><button class="button subtle" id="live-config" disabled>Configure monitor</button><button class="button subtle hidden" id="live-stop">Stop monitor</button><button class="button primary" id="live-start" disabled><span aria-hidden="true">▶</span> Start monitor</button></div>
      </section>
      <div id="live-source-banner" class="live-source-banner" role="status"></div>
      <div id="live-warnings" class="live-warnings hidden"></div>
      <div class="live-overview" id="live-overview"></div>
      <div class="live-workspace">
        <section class="panel live-market-panel" aria-labelledby="live-radar-title">
          <div class="live-panel-heading"><div><div class="section-heading"><h2 id="live-radar-title">Momentum radar</h2><span class="count-pill" id="live-symbol-count">0</span></div><p id="live-filter-summary">Your intraday rules, in real time.</p></div><button class="button subtle" id="live-export" disabled>Export CSV</button></div>
          <div class="live-table-toolbar"><label class="live-search"><span class="sr-only">Search monitored stocks</span><input id="live-search" type="search" placeholder="Search your symbols…"></label><label class="live-sort">Sort by<select id="live-sort"><option value="signal_score">Setup score</option><option value="minute_relative_volume">1-minute RVOL</option><option value="gap_pct">Opening gap</option><option value="session_volume">Session volume</option><option value="symbol">Symbol</option></select></label></div>
          <div id="live-table" class="live-table-scroll" tabindex="0" aria-label="Live stock metrics; scroll horizontally for all columns"></div>
          <div class="live-table-footer"><span id="live-update-time">Waiting for your first session</span><span>Scroll for all metrics → · Technicals use completed 1-minute bars</span></div>
          <details class="live-definitions"><summary>Read the numbers</summary><div><p><strong>Feed-day volume</strong> is the provider’s daily aggregation, including available extended-hours trading. <strong>Session volume</strong> totals completed regular-session 1-minute bars and updates when a minute closes.</p><p><strong>30D avg / total</strong> use the 30 prior trading sessions, excluding today.</p><p><strong>Session RVOL</strong> is session volume ÷ the full-session 30D average; it is not adjusted for time of day.</p><p><strong>1-minute RVOL</strong> is the latest completed minute’s volume ÷ the preceding 20-minute average. This drives the volume alert filter.</p><p><strong>Gap</strong> compares the regular-session opening price with the prior split-adjusted close. Day change uses the latest price.</p><p><strong>Float</strong> is sourced and dated separately. A dash means unavailable, never an estimate from shares outstanding.</p></div></details>
        </section>
        <aside class="live-alert-rail" aria-label="Technical setup alerts">
          <section class="panel live-alert-panel"><div class="live-panel-heading"><div><div class="section-heading"><h2>Setup alerts</h2><span id="live-alert-count" class="count-pill">0</span></div><p>Confirmed moves worth a closer look.</p></div><button class="text-button" id="live-ack-all" disabled>Mark read</button></div><div class="live-alert-options"><button class="live-option" id="live-notifications" aria-pressed="false">Desktop alerts <span>Off</span></button><button class="live-option" id="live-sound" aria-pressed="false">Alert sound <span>Off</span></button><p id="live-notification-note">Opt in for this browser tab. Synthetic alerts stay in this inbox.</p></div><div id="live-alerts" class="live-alert-list" aria-label="Saved alert inbox"></div></section>
          <section class="live-rule-note"><span class="live-rule-mark" aria-hidden="true">↗</span><h3>Evidence before action.</h3><p>Buy and Strong buy describe technical setups, not orders or a probability of profit. Open a stock to inspect its score and data quality.</p><div id="live-alert-rules"></div><p class="live-note-small">Regular-session alerts require fresh trades, quotes, and completed minute bars. Feed outages, missing data, and stale prices suppress alerts. Halt detection is not guaranteed.</p></section>
        </aside>
      </div>`;

    document.body.insertAdjacentHTML("beforeend", `
      <dialog id="live-config-dialog" class="modal live-config-modal" aria-labelledby="live-config-title"><form id="live-config-form">
        <div class="modal-header"><div><div class="eyebrow">YOUR INTRADAY PLAYBOOK</div><h2 id="live-config-title">Configure momentum monitor</h2><p>Watch up to 20 symbols with independent intraday rules.</p></div><button class="icon-button" type="button" data-live-close aria-label="Close monitor configuration">✕</button></div>
        <div class="modal-body"><div id="live-config-running" class="live-form-note hidden">Stop the monitor to edit its source, symbols, or rules.</div><fieldset id="live-config-fields">
          <div class="live-form-section"><h3>Market data & symbols</h3><label>Source<select id="live-source" name="source"><option value="demo">Synthetic demo · simulated penny stocks</option><option value="alpaca">Alpaca · real-time trade and quote stream</option></select></label><div id="live-provider-help" class="live-form-note"></div><label>Stock symbols<textarea id="live-symbols" name="symbols" rows="2" required placeholder="ABCD, EFGH, IJKL" aria-describedby="live-symbol-help"></textarea><span class="field-help" id="live-symbol-help">Up to 20 symbols, separated by commas or spaces. Listed US equities; OTC coverage is not available.</span></label><div class="live-import-buttons"><button type="button" class="button subtle" id="live-use-watchlist">Use watchlist</button><button type="button" class="button subtle" id="live-use-scan">Use latest scan’s top 20</button></div><p id="live-import-note" class="field-help" role="status"></p></div>
          <div class="live-form-section"><h3>Penny-stock liquidity filters</h3><div class="live-form-grid"><label>Minimum price ($)<input name="min_price" type="number" min="0.0001" max="1000000" step="any" required></label><label>Maximum price ($)<input name="max_price" type="number" min="0.0001" max="1000000" step="any" required></label><label>Minimum session volume<input name="min_session_volume" type="number" min="0" step="1" required><span class="field-help">Completed regular-session minutes</span></label><label>Minimum 1-minute RVOL (×)<input name="min_relative_volume" type="number" min="0" max="1000" step="any" required><span class="field-help">Latest minute ÷ preceding 20-minute average</span></label><label>Maximum bid–ask spread (%)<input name="max_spread_pct" type="number" min="0.01" max="20" step="any" required><span class="field-help">Missing or stale quotes block alerts</span></label></div></div>
          <div class="live-form-section"><h3>Technical setup alerts</h3><div class="live-form-grid"><label>Buy setup score<input name="buy_score" type="number" min="0" max="99" step="any" required></label><label>Strong buy setup score<input name="strong_buy_score" type="number" min="1" max="100" step="any" required></label><label>Confirmation bars<input name="confirmation_bars" type="number" min="1" max="5" step="1" required><span class="field-help">Consecutive completed 1-minute bars</span></label><label>Cooldown (seconds)<input name="cooldown_seconds" type="number" min="30" max="3600" step="1" required><span class="field-help">Strong buy upgrades can alert sooner</span></label></div><label class="live-check"><input name="alerts_enabled" type="checkbox">Enable saved in-app setup alerts</label><p class="live-form-note">Both setup levels require price above session VWAP, EMA trend alignment, sufficient 1-minute relative volume, and valid market data. Scores are explainable technical heuristics.</p></div>
        </fieldset><div id="live-config-error" class="alert error hidden" role="alert"></div></div><div class="modal-footer"><span class="field-help">Saved locally. Start monitoring explicitly.</span><div><button type="button" class="button subtle" data-live-close>Cancel</button><button id="live-save-config" class="button primary" type="submit">Save configuration</button></div></div>
      </form></dialog>
      <dialog id="live-report-dialog" class="modal live-report-modal" aria-labelledby="live-report-title"><div class="live-report-header"><div><div class="eyebrow">INTRADAY STOCK REPORT</div><h2 id="live-report-title">Stock details</h2></div><div><button class="button subtle" id="live-print">Print report</button><button class="icon-button" data-live-close aria-label="Close stock report">✕</button></div></div><div id="live-report-data"></div><div class="live-float-edit" id="live-float-edit"><details><summary>Add or update a dated float value</summary><p>Use actual publicly available float shares from a source you have checked. This is saved as a manual value and overrides optional provider float data.</p><form id="live-float-form"><div class="live-form-grid"><label>Float shares<input id="live-float-shares" name="shares" type="number" min="1" max="10000000000000" step="1" required></label><label>Source date<input id="live-float-date" name="as_of" type="date" required></label></div><div class="live-float-actions"><button class="button primary" type="submit">Save manual float</button><button class="button subtle" id="live-clear-float" type="button">Clear manual override</button></div><div id="live-float-error" class="alert error hidden" role="alert"></div><p id="live-float-saved" class="field-help" role="status"></p></form></details></div></dialog>`);
  }

  function accept(snapshot) {
    if (!snapshot || !snapshot.config || !snapshot.status) return;
    const alerts = snapshot.alerts || [];
    if (view.baseline) {
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
    view.baseline = true;
    view.snapshot = snapshot;
    view.receivedAt = Date.now();
    render();
  }
  function render() {
    const {config, status, rows = [], alerts = []} = view.snapshot;
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
    q("#live-export").disabled = !rows.length;
    q("#live-config-fields").disabled = running;
    q("#live-save-config").disabled = running || view.action;
    q("#live-config-running").classList.toggle("hidden", !running);
    const demo = (status.source || config.source) === "demo";
    const feed = status.feed || view.snapshot.provider_status?.feed;
    const banner = q("#live-source-banner");
    banner.classList.toggle("synthetic", demo);
    banner.innerHTML = demo
      ? `<span class="live-source-tag">SYNTHETIC DEMO</span><p>Simulated penny stocks on a historical clock. Prices, float, volume, and alerts are fictional. <strong>Switch to Alpaca for market data.</strong></p>`
      : `<span class="live-source-tag">${html(sourceLabel("alpaca", feed))}</span><p>${feed === "iex" ? "IEX covers one exchange: volume and relative volume do not represent the consolidated market." : "Prices and quotes stream from your configured real-time market feed."} Alerts run during the regular trading session.</p>`;
    const warnings = [...new Set(status.warnings || [])];
    q("#live-warnings").classList.toggle("hidden", !warnings.length);
    q("#live-warnings").innerHTML = warnings.length ? `<details><summary>${warnings.length} market data ${warnings.length === 1 ? "note" : "notes"}</summary><ul>${warnings.map((warning) => `<li>${html(warning)}</li>`).join("")}</ul></details>` : "";
    const setups = rows.filter((row) => row.signal === "Buy" || row.signal === "Strong buy");
    const strong = rows.filter((row) => row.signal === "Strong buy").length;
    const minuteValues = rows.map((row) => row.minute_relative_volume).filter(finite);
    const bestVolume = minuteValues.length ? Math.max(...minuteValues) : null;
    q("#live-overview").innerHTML = [
      ["Symbols on your radar", String(rows.length || 0), `${config.symbols.length} configured · up to 20`, ""],
      ["Bullish technical setups", String(setups.length), `${strong} strong buy · confirmation required for alerts`, "highlight"],
      ["Highest 1-minute RVOL", ratio(bestVolume), "Against the preceding 20 completed minutes", ""],
      ["Trading session", status.session?.date || "Not started", demo ? "Historical simulation · explicitly synthetic" : rows.some((row) => row.market_open) ? "Regular session · market clock ET" : "Waiting / outside regular session", "session"]
    ].map(([label, value, caption, className]) => `<article class="live-stat ${className}"><span>${label}</span><strong>${html(value)}</strong><small>${html(caption)}</small></article>`).join("");
    q("#live-symbol-count").textContent = rows.length;
    q("#live-filter-summary").textContent = `${dollars(config.min_price)}–${dollars(config.max_price)} · volume ≥ ${short(config.min_session_volume)} · 1-minute RVOL ≥ ${ratio(config.min_relative_volume)} · spread ≤ ${n(config.max_spread_pct, 2)}%`;
    q("#live-alert-rules").innerHTML = `<div><span>Buy / strong buy</span><strong>${n(config.buy_score)} / ${n(config.strong_buy_score)} pts</strong></div><div><span>Confirmation</span><strong>${n(config.confirmation_bars)} minute bars</strong></div><div><span>Repeat cooldown</span><strong>${n(config.cooldown_seconds)} seconds</strong></div><div><span>Saved alerts</span><strong>${config.alerts_enabled ? "Enabled" : "Disabled"}</strong></div>`;
    q("#live-alert-count").textContent = alerts.filter((item) => !item.acknowledged).length;
    q("#live-ack-all").disabled = !alerts.some((item) => !item.acknowledged);
    renderTable(); renderAlerts(); renderFreshness();
    if (q("#live-report-dialog").open) renderReport();
  }
  function metricCell(value, formatted, title, className = "") {
    return `<td class="live-num ${className}" title="${html(finite(value) ? `${title}: ${n(value, 4).replace(/\.?0+$/, "")}` : unavailable)}">${formatted}</td>`;
  }
  function stockRow(row, config) {
    const symbol = html(row.symbol);
    const floats = finite(row.float_shares) ? `<small>${html(row.float_source || "")}</small>` : '<small>Unavailable</small>';
    const volumeClass = finite(row.minute_relative_volume) && row.minute_relative_volume >= config.min_relative_volume ? "live-volume-active" : "";
    return `<tr class="${row.stale ? "live-stale" : ""}">
      <td><button class="live-stock-button" data-live-symbol="${symbol}" aria-label="Open ${symbol} intraday report"><span class="live-symbol">${symbol}<span class="live-row-dot ${row.stale ? "stale" : ""}" title="${row.stale ? "Stale or unavailable market data" : "Price and quote freshness checked"}"></span></span><span class="live-setup ${levelClass(row.signal)}">${setup(row.signal)}</span></button></td>
      <td class="live-num"><strong>${dollars(row.price)}</strong><small class="${direction(row.change_pct)}">${pct(row.change_pct)}</small></td>
      ${metricCell(row.day_volume, short(row.day_volume), "Provider feed-day volume, including available extended hours")}
      ${metricCell(row.float_shares, `${short(row.float_shares)}${floats}`, "Float shares")}
      ${metricCell(row.minute_relative_volume, ratio(row.minute_relative_volume), "1-minute RVOL", volumeClass)}
      ${metricCell(row.gap_pct, pct(row.gap_pct), "Gap percentage", direction(row.gap_pct))}
      <td class="live-num"><span class="live-score">${n(row.signal_score)}<small>/100</small></span></td>
      ${metricCell(row.session_volume, short(row.session_volume), "Completed regular-session minute volume")}
      ${metricCell(row.avg_volume_30d, short(row.avg_volume_30d), "30-session average volume")}
      ${metricCell(row.volume_30d_total, short(row.volume_30d_total), "30-session total volume")}
      ${metricCell(row.relative_volume, ratio(row.relative_volume), "Session RVOL")}
    </tr>`;
  }
  function renderTable() {
    const {rows = [], config, status} = view.snapshot;
    const filtered = rows.filter((row) => !view.query || `${row.symbol} ${row.name}`.toLowerCase().includes(view.query));
    filtered.sort((a, b) => view.sort === "symbol" ? a.symbol.localeCompare(b.symbol) : (b[view.sort] ?? -Infinity) - (a[view.sort] ?? -Infinity) || a.symbol.localeCompare(b.symbol));
    if (!rows.length) {
      q("#live-table").innerHTML = `<div class="live-empty"><span aria-hidden="true">⌁</span><h3>${status.running ? "Building your session view" : "Your next session starts here"}</h3><p>${status.running ? "Loading current quotes, minute bars, and 30 prior sessions of volume. Connection status above shows progress." : `Ready to monitor ${html(config.symbols.join(", "))}. Start the monitor to follow prices and evaluate minute-by-minute setups.`}</p></div>`;
      return;
    }
    if (!filtered.length) { q("#live-table").innerHTML = '<div class="live-empty"><h3>No matching symbols</h3><p>Try another symbol or company name.</p></div>'; return; }
    const focused = document.activeElement?.dataset.liveSymbol;
    q("#live-table").innerHTML = `<table class="live-stocks"><thead><tr><th>Stock / setup</th><th class="live-num">Price / day</th><th class="live-num" title="Provider daily volume including available extended-hours trading">Feed-day vol.</th><th class="live-num">Float</th><th class="live-num" title="Latest completed minute volume divided by preceding 20-minute average">1-min RVOL</th><th class="live-num" title="Regular-session opening price versus prior adjusted close">Gap</th><th class="live-num">Score</th><th class="live-num" title="Volume from completed regular-session minute bars">Session vol.</th><th class="live-num" title="Average daily volume across 30 prior trading sessions">30D avg vol.</th><th class="live-num" title="Total volume across 30 prior trading sessions">30D total vol.</th><th class="live-num" title="Session volume divided by full-session 30D average; not time-of-day adjusted">Session RVOL</th></tr></thead><tbody>${filtered.map((row) => stockRow(row, config)).join("")}</tbody></table>`;
    if (focused) [...q("#live-table").querySelectorAll("[data-live-symbol]")].find((button) => button.dataset.liveSymbol === focused)?.focus({preventScroll:true});
  }
  function renderFreshness() {
    if (!view.snapshot) return;
    const elapsed = Math.floor((Date.now() - view.receivedAt) / 1000);
    const status = view.snapshot.status;
    const interrupted = elapsed > 35;
    const browserState = interrupted ? "Browser updates interrupted" : view.transport === "polling" ? "Browser polling every 2s" : "Browser streaming";
    q("#live-update-time").textContent = `${status.updated_at ? `Data ${clock(status.updated_at)}` : "No session data yet"} · ${browserState}${interrupted ? ` (${elapsed}s)` : ""}`;
    q("#live-update-time").classList.toggle("negative", interrupted);
  }
  function renderAlerts() {
    const alerts = view.snapshot.alerts || [];
    const key = JSON.stringify(alerts);
    if (key === view.alertsKey) return;
    view.alertsKey = key;
    q("#live-alerts").innerHTML = !alerts.length
      ? '<div class="live-alert-empty"><span aria-hidden="true">◎</span><h3>Waiting for confirmation</h3><p>New Buy and Strong buy setups appear here after your required consecutive minute bars. Alerts are saved locally.</p></div>'
      : alerts.map((item) => `<article class="live-alert-card ${item.acknowledged ? "read" : "unread"}"><div class="live-alert-top"><button class="live-alert-symbol" data-live-symbol="${html(item.symbol)}">${html(item.symbol)}</button><span class="live-setup ${levelClass(item.level)}">${setup(item.level)}</span></div><p class="live-alert-source">${html(sourceLabel(item.source, item.feed))} · ${clock(item.market_time || item.created_at, true)}</p><div class="live-alert-values"><strong>${dollars(item.price)}</strong><span>${n(item.score)} / 100</span></div>${item.reasons?.length ? `<p class="live-alert-reason">${html(item.reasons.slice(0, 2).join(" · "))}</p>` : ""}<div class="live-alert-bottom"><span>${item.acknowledged ? "Read" : "New setup"}</span>${item.acknowledged ? "" : `<button class="text-button" data-live-ack="${html(item.id)}">Mark read</button>`}</div></article>`).join("");
  }
  function lineChart(series) {
    const points = (series || []).filter((bar) => finite(bar.close));
    if (!points.length) return '<p class="live-chart-empty">Completed minute history is unavailable.</p>';
    const width = 760, height = 205, left = 12, right = 62, bottom = 22;
    const prices = points.map((bar) => bar.close);
    const low = Math.min(...prices), high = Math.max(...prices), pad = Math.max((high - low) * .15, high * .002, .005);
    const min = low - pad, max = high + pad;
    const x = (i) => left + i / Math.max(1, points.length - 1) * (width - left - right);
    const y = (price) => 10 + (max - price) / (max - min) * (height - bottom - 10);
    const path = points.map((bar, i) => `${i ? "L" : "M"}${x(i).toFixed(2)},${y(bar.close).toFixed(2)}`).join(" ");
    const grid = [0, 1, 2, 3].map((i) => { const value = min + (max - min) * i / 3; return `<line x1="${left}" x2="${width - right}" y1="${y(value)}" y2="${y(value)}" stroke="#dce5d9" stroke-dasharray="3 5"/><text x="${width - right + 10}" y="${y(value) + 4}" fill="#637360" font-size="11">${n(value, 2)}</text>`; }).join("");
    return `<svg viewBox="0 0 ${width} ${height}" class="live-price-chart" role="img" aria-label="${points.length} completed regular-session minute closes; ${html(dollars(prices[0]))} to ${html(dollars(prices[prices.length - 1]))}"><defs><linearGradient id="live-price-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#75a563" stop-opacity=".23"/><stop offset="100%" stop-color="#75a563" stop-opacity="0"/></linearGradient></defs>${grid}<path d="${path} L${x(points.length - 1)},${height - bottom} L${left},${height - bottom} Z" fill="url(#live-price-fill)"/><path d="${path}" fill="none" stroke="#39704b" stroke-width="2" vector-effect="non-scaling-stroke"/>${points.map((bar, i) => `<circle cx="${x(i)}" cy="${y(bar.close)}" r="4" fill="transparent"><title>${html(clock(bar.t))}: ${html(dollars(bar.close))}; volume ${n(bar.volume)}</title></circle>`).join("")}</svg><div class="live-chart-times"><span>${clock(points[0].t)}</span><span>${clock(points[points.length - 1].t)}</span></div>`;
  }
  function volumeChart(history) {
    const bars = (history || []).filter((bar) => finite(bar.volume));
    if (!bars.length) return '<p class="live-chart-empty">Prior session volume history is unavailable.</p>';
    const max = Math.max(1, ...bars.map((bar) => bar.volume));
    return `<div class="live-volume-chart" role="img" aria-label="Daily volume across ${bars.length} prior trading sessions">${bars.map((bar) => `<div class="live-volume-bar" style="--bar-height:${Math.max(1, bar.volume / max * 100)}%" title="${date(bar.date)}: ${n(bar.volume)} shares"><span></span></div>`).join("")}</div><div class="live-chart-times"><span>${date(bars[0].date)}</span><span>${date(bars[bars.length - 1].date)}</span></div>`;
  }
  function reportMetric(label, value, note = "", cls = "") {
    return `<div class="live-report-metric"><dt>${html(label)}</dt><dd class="${cls}">${value}</dd>${note ? `<small>${html(note)}</small>` : ""}</div>`;
  }
  function renderReport(force = false) {
    const row = view.snapshot.rows?.find((item) => item.symbol === view.selected);
    if (!row) { q("#live-report-data").innerHTML = '<div class="live-empty"><h3>Outside the current monitor</h3><p>This symbol’s alert is saved, but current metrics require adding it to the monitor configuration.</p></div>'; q("#live-float-edit").classList.add("hidden"); return; }
    const key = JSON.stringify(row);
    if (!force && key === view.detailKey) return;
    view.detailKey = key;
    const history = row.volume_history || [];
    const historyOpen = q("#live-history-details")?.open;
    const reasons = row.reasons || [], blockers = row.blockers || [], warnings = row.warnings || [];
    q("#live-report-title").textContent = `${row.symbol} · ${row.name || "Intraday report"}`;
    q("#live-float-edit").classList.toggle("hidden", row.source === "demo");
    q("#live-report-data").innerHTML = `
      <div class="live-report-source ${row.source === "demo" ? "synthetic" : ""}"><strong>${html(sourceLabel(row.source, row.feed))}</strong><span>Session ${date(row.session_date)} · Price ${clock(row.price_at, true)}</span>${row.source === "demo" ? '<p>All values are fictional simulation data.</p>' : ""}</div>
      <div class="live-report-price"><div><strong>${dollars(row.price)}</strong><span class="${direction(row.change_pct)}">${pct(row.change_pct)} today</span></div><div><span class="live-setup ${levelClass(row.signal)}">${setup(row.signal)}</span><span>${n(row.signal_score)} / 100</span></div></div>
      <div class="live-feed-volume"><strong>Feed-day volume: ${n(row.day_volume)} shares</strong><span>Provider daily aggregation, including available extended hours · updated ${clock(row.day_volume_at)}</span></div>
      <dl class="live-report-metrics">${reportMetric("Session volume", n(row.session_volume), "Completed regular-session minute bars")}${reportMetric("Float shares", n(row.float_shares), finite(row.float_shares) ? `${row.float_source || "Source unavailable"} · as of ${row.float_as_of || "date unavailable"}` : "No usable dated float source")}${reportMetric("30-session average volume", n(row.avg_volume_30d), "30 prior trading sessions; excludes today")}${reportMetric("30-session total volume", n(row.volume_30d_total), "30 prior trading sessions; excludes today")}${reportMetric("Session relative volume", ratio(row.relative_volume), "Versus full-session 30D average; not time adjusted")}${reportMetric("1-minute relative volume", ratio(row.minute_relative_volume), "Latest completed minute / preceding 20 minutes")}${reportMetric("Opening gap", pct(row.gap_pct), "Regular open versus prior adjusted close", direction(row.gap_pct))}${reportMetric("Float turnover", ratio(row.float_turnover), "Session volume / dated float shares")}${reportMetric("Bid–ask spread", finite(row.spread_pct) ? `${n(row.spread_pct, 2)}%` : "—", `Quote ${clock(row.quote_at)}`)}${reportMetric("Session VWAP", dollars(row.vwap), "Volume-weighted regular-session minute bars")}${reportMetric("EMA 9 / EMA 20", `${dollars(row.ema9)} / ${dollars(row.ema20)}`, "Completed minute closes")}${reportMetric("RSI", n(row.rsi, 1), "Minute momentum oscillator")}</dl>
      <section class="live-report-section"><div class="live-report-section-title"><h3>Intraday price</h3><span>Completed 1-minute closes</span></div>${lineChart(row.chart)}</section>
      <section class="live-report-section"><div class="live-report-section-title"><h3>Participation over 30 sessions</h3><span>Prior sessions · today excluded</span></div>${volumeChart(history)}<details id="live-history-details" ${historyOpen ? "open" : ""}><summary>Show exact daily volumes (${history.length} sessions)</summary><table class="live-history-table"><thead><tr><th>Trading session</th><th class="live-num">Volume (shares)</th></tr></thead><tbody>${history.map((bar) => `<tr><td>${date(bar.date)}</td><td class="live-num">${n(bar.volume)}</td></tr>`).join("")}</tbody></table></details></section>
      <section class="live-report-section live-score-section"><div class="live-report-section-title"><h3>Inside the technical setup</h3><span>${n(row.signal_score)} / 100 · heuristic score</span></div>${row.signals?.length ? `<div class="live-score-breakdown">${row.signals.map((signal) => `<div><span><strong>${html(signal.name)}</strong><small>${html(signal.description)}</small></span><span>${n(signal.points)} / ${n(signal.max_points)}</span></div>`).join("")}</div>` : ""}${reasons.length ? `<h4>Supporting conditions</h4><ul>${reasons.map((reason) => `<li>${html(reason)}</li>`).join("")}</ul>` : ""}${blockers.length ? `<div class="live-blockers"><h4>Why this is not alert eligible</h4><ul>${blockers.map((reason) => `<li>${html(reason)}</li>`).join("")}</ul></div>` : `<p class="live-eligible-note">${row.alert_eligible ? "Data and technical gates pass. Saved alerts still require consecutive confirmation bars and obey the repeat cooldown." : "This stock is not eligible for a technical setup alert."}</p>`}${warnings.length ? `<div class="live-blockers"><h4>Data notes</h4><ul>${warnings.map((warning) => `<li>${html(warning)}</li>`).join("")}</ul></div>` : ""}</section>
      <div class="live-report-foot"><p>Price: ${clock(row.price_at, true)} · quote: ${clock(row.quote_at)} · volume through: ${clock(row.volume_at)} · signal bar: ${clock(row.signal_bar_at)}.</p><p>${row.stale ? "Market data is stale or incomplete. " : ""}${row.market_open ? "Regular session." : "Outside the current regular session."} A dash means unavailable. Technical setup scores are not calibrated return forecasts. Check news, spread, filings, and trading halts before making a decision.</p></div>`;
  }
  function showStock(symbol) {
    view.selected = symbol;
    view.detailKey = "";
    q("#live-report-title").textContent = `${symbol} · Intraday report`;
    q("#live-float-form").reset();
    errorAt("#live-float-error", "");
    q("#live-float-saved").textContent = "";
    const row = view.snapshot?.rows?.find((item) => item.symbol === symbol);
    q("#live-float-date").max = new Date().toLocaleDateString("en-CA", {timeZone:"America/New_York"});
    if (row?.float_source === "Manual") { q("#live-float-shares").value = row.float_shares || ""; q("#live-float-date").value = row.float_as_of || ""; }
    renderReport(true);
    openDialog(q("#live-report-dialog"), "#live-print");
  }
  function providerHelp() {
    const demo = q("#live-source").value === "demo";
    const provider = view.snapshot?.provider_status || {};
    q("#live-provider-help").innerHTML = demo
      ? "The demo runs fictional penny stocks on an advancing historical clock. No market connection is used."
      : `${provider.alpaca_configured ? `<strong>Alpaca credentials are configured.</strong> Feed: ${html(String(provider.feed || "iex").toUpperCase())}.` : "<strong>Alpaca credentials are not configured.</strong> Add ALPACA_API_KEY and ALPACA_SECRET_KEY to projects/nomisma/.env, then restart Nomisma."} ${provider.feed === "sip" ? "Real-time SIP access requires the appropriate data entitlement." : "IEX volume covers one exchange. Use an entitled SIP feed for consolidated volume."} Float data is ${provider.float_configured ? "available through your optional FMP configuration when the provider supplies it" : "optional: configure FMP_API_KEY or enter a dated float value in a stock report"}. <strong>Use real ticker symbols below; replace any synthetic demo symbols.</strong>`;
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
    errorAt("#live-config-error", "");
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
    if (!result.symbols.length || result.symbols.length > 20) throw new Error("Enter between 1 and 20 unique symbols.");
    if (result.min_price > result.max_price) throw new Error("Minimum price must not exceed maximum price.");
    if (result.buy_score >= result.strong_buy_score) throw new Error("Strong buy score must be higher than Buy score.");
    return result;
  }
  async function importSymbols(kind) {
    try {
      const bootstrap = await request("/api/bootstrap");
      const all = kind === "watchlist" ? bootstrap.watchlist || [] : (bootstrap.latest?.results || []).map((row) => row.symbol);
      if (!all.length) throw new Error(kind === "watchlist" ? "Your watchlist is empty. Add symbols in Watchlist first." : "The latest daily scan has no matching symbols. Run the daily screener first.");
      q("#live-symbols").value = all.slice(0, 20).join(", ");
      q("#live-import-note").textContent = `Loaded ${Math.min(20, all.length)} symbols${all.length > 20 ? ` from ${all.length}; only the first 20 fit` : ""}. Review the source and price range before saving.`;
      errorAt("#live-config-error", "");
    } catch (error) { errorAt("#live-config-error", error.message); }
  }
  async function setRunning(running) {
    view.action = true;
    errorAt("#live-error", "");
    render();
    try {
      const snapshot = await request(`/api/monitor/${running ? "start" : "stop"}`, {});
      accept(snapshot);
    } catch (error) { errorAt("#live-error", error.message); }
    finally { view.action = false; render(); }
  }
  async function acknowledge(body) {
    try {
      const result = await request("/api/monitor/alerts/ack", body);
      view.snapshot.alerts = result.alerts || [];
      render();
    } catch (error) { errorAt("#live-error", error.message); }
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
    } catch (error) { errorAt("#live-error", error.message); }
  }
  async function saveFloat(clear = false) {
    const form = q("#live-float-form");
    const buttons = [...form.querySelectorAll("button")];
    buttons.forEach((button) => { button.disabled = true; });
    errorAt("#live-float-error", "");
    try {
      const body = {symbol:view.selected, shares:clear ? null : Number(q("#live-float-shares").value)};
      if (!clear) body.as_of = q("#live-float-date").value;
      await request("/api/monitor/float", body);
      q("#live-float-saved").textContent = clear ? "Manual override cleared. The next data update will use available provider float." : "Dated manual float saved. It will appear in current or subsequent market data updates.";
      if (clear) form.reset();
      await fetchSnapshot();
    } catch (error) { errorAt("#live-float-error", error.message); }
    finally { buttons.forEach((button) => { button.disabled = false; }); }
  }
  function notify(item) {
    // Never replay persisted alerts, alert on a demo, or request permissions implicitly.
    if (item.source !== "alpaca") return;
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
  async function toggleNotifications() {
    if (view.notifications) view.notifications = false;
    else if (!("Notification" in window)) q("#live-notification-note").textContent = "Desktop notifications are unavailable in this browser. Your saved inbox remains active.";
    else {
      try {
        const permission = Notification.permission === "granted" ? "granted" : await Notification.requestPermission();
        view.notifications = permission === "granted";
        q("#live-notification-note").textContent = view.notifications ? "New real-market alerts may notify in this tab. Synthetic and historical alerts stay in the inbox." : "Notifications were not enabled. Browser site settings control permission; your inbox remains active.";
      } catch (_) { q("#live-notification-note").textContent = "Desktop permission could not be enabled. Use the saved inbox."; }
    }
    q("#live-notifications").setAttribute("aria-pressed", String(view.notifications));
    q("#live-notifications span").textContent = view.notifications ? "On" : "Off";
  }
  async function toggleSound() {
    if (view.sound) view.sound = false;
    else {
      try {
        const Audio = window.AudioContext || window.webkitAudioContext;
        if (!Audio) throw new Error("Sound is not supported in this browser.");
        if (!view.audio) view.audio = new Audio();
        await view.audio.resume();
        view.sound = view.audio.state === "running";
      } catch (error) { q("#live-notification-note").textContent = error.message; }
    }
    q("#live-sound").setAttribute("aria-pressed", String(view.sound));
    q("#live-sound span").textContent = view.sound ? "On" : "Off";
  }
  async function fetchSnapshot() {
    if (view.fetching) return;
    view.fetching = true;
    try {
      accept(await request("/api/monitor"));
      if (q("#live-error").textContent.startsWith("Cannot update the monitor:")) errorAt("#live-error", "");
    }
    catch (error) { errorAt("#live-error", `Cannot update the monitor: ${error.message}`); view.baseline = false; }
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
    const events = new EventSource("/api/monitor/events");
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
    q("#live-config").addEventListener("click", showConfig);
    q("#live-source").addEventListener("change", providerHelp);
    q("#live-start").addEventListener("click", () => setRunning(true));
    q("#live-stop").addEventListener("click", () => setRunning(false));
    q("#live-export").addEventListener("click", exportRows);
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
        const response = await request("/api/monitor/config", config);
        view.snapshot.config = response.config;
        q("#live-config-dialog").close();
        await fetchSnapshot();
      } catch (error) { errorAt("#live-config-error", error.message); }
      finally { q("#live-save-config").disabled = !!view.snapshot?.status.running; }
    });
    q("#live-float-form").addEventListener("submit", (event) => { event.preventDefault(); saveFloat(); });
    q("#live-clear-float").addEventListener("click", () => saveFloat(true));
    q("#live-print").addEventListener("click", () => {
      const history = q("#live-history-details");
      const wasOpen = history?.open;
      if (history) history.open = true;
      document.body.classList.add("printing-live-report");
      try { window.print(); } finally { document.body.classList.remove("printing-live-report"); if (history) history.open = wasOpen; }
    });
    window.addEventListener("afterprint", () => document.body.classList.remove("printing-live-report"));
    for (const dialog of [q("#live-config-dialog"), q("#live-report-dialog")]) {
      dialog.addEventListener("close", () => { view.lastFocus.get(dialog)?.focus({preventScroll:true}); });
      dialog.addEventListener("click", (event) => {
        if (event.target !== dialog) return;
        const bounds = dialog.getBoundingClientRect();
        if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
      });
    }
    document.addEventListener("click", (event) => {
      const close = event.target.closest("[data-live-close]");
      if (close) close.closest("dialog").close();
      const stock = event.target.closest("[data-live-symbol]");
      if (stock && view.snapshot) showStock(stock.dataset.liveSymbol);
      const ack = event.target.closest("[data-live-ack]");
      if (ack) acknowledge({id:ack.dataset.liveAck});
    });
    document.addEventListener("visibilitychange", () => {
      // Resuming an inactive tab establishes a new inbox baseline, avoiding catch-up notifications.
      if (!document.hidden) { view.baseline = false; view.freshSince = Date.now(); fetchSnapshot(); }
    });
    window.addEventListener("pagehide", () => { view.events?.close(); clearTimeout(view.pollTimer); clearTimeout(view.retryTimer); });
    window.addEventListener("pageshow", (event) => { if (event.persisted) { view.baseline = false; view.freshSince = Date.now(); fetchSnapshot().then(stream); } });
    setInterval(renderFreshness, 1000);
    // SSE comment heartbeats are invisible to EventSource. Verify quiet streams
    // periodically without treating an unchanged stopped session as disconnected.
    setInterval(() => { if (Date.now() - view.receivedAt > 15000 && !document.hidden) fetchSnapshot(); }, 10000);
  }
  mount(); bind();
  fetchSnapshot().then(stream);
})();
