"use strict";

// Nomisma is a local research client. Prices, scores, and indicator values always
// come from the server; a failed provider request never substitutes demo results.
const $ = (selector, parent = document) => parent.querySelector(selector);
const $$ = (selector, parent = document) => Array.from(parent.querySelectorAll(selector));
const escapeHTML = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
const copy = (value) => JSON.parse(JSON.stringify(value));
const numeric = (value) => typeof value === "number" && Number.isFinite(value);
const number = (value, decimals = 0) => numeric(value) ? value.toLocaleString("en-US", {minimumFractionDigits:decimals, maximumFractionDigits:decimals}) : "—";
const money = (value) => numeric(value) ? `$${number(value, 2)}` : "—";
const percent = (value, decimals = 2) => numeric(value) ? `${value > 0 ? "+" : ""}${number(value, decimals)}%` : "—";
const multiple = (value) => numeric(value) ? `${number(value, 2)}×` : "—";
const changeClass = (value) => numeric(value) ? value < 0 ? "negative" : value > 0 ? "positive" : "neutral" : "neutral";
const compact = (value) => numeric(value) ? Intl.NumberFormat("en-US", {notation:"compact", maximumFractionDigits:1}).format(value) : "—";
const dateLabel = (value, options = {month:"short", day:"numeric", year:"numeric"}) => {
  if (!value) return "Not available";
  const date = new Date(/^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T12:00:00Z` : value);
  return Number.isNaN(date.getTime()) ? "Not available" : date.toLocaleDateString("en-US", {...options, timeZone:"UTC"});
};
const timestampLabel = (value) => {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Not available" : date.toLocaleString("en-US", {month:"short", day:"numeric", year:"numeric", hour:"numeric", minute:"2-digit"});
};

const icons = {
  grid:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  star:'<path d="m12 3 2.78 5.63L21 9.54l-4.5 4.38 1.06 6.2L12 17.2l-5.56 2.92 1.06-6.2L3 9.54l6.22-.91L12 3Z"/>',
  history:'<path d="M3 11a9 9 0 1 1 2.5 7.3M3 4v7h7m2-4v5l3 2"/>',
  book:'<path d="M12 5c-3-2-6-2-9-1v15c3-1 6-1 9 1 3-2 6-2 9-1V4c-3-1-6-1-9 1Zm0 0v15"/>',
  settings:'<path d="m9 3-1 3-3 1 1 3-2 2 2 2-1 3 3 1 1 3h4l1-3 3-1-1-3 2-2-2-2 1-3-3-1-1-3H9Z"/><circle cx="11" cy="12" r="3"/>',
  "chevron-down":'<path d="m6 9 6 6 6-6"/>',
  "chevron-right":'<path d="m9 5 7 7-7 7"/>',
  "chevron-left":'<path d="m15 5-7 7 7 7"/>',
  "arrow-up-right":'<path d="M6 18 18 6M6 6h12v12"/>',
  "arrow-right":'<path d="M4 12h16m-6-6 6 6-6 6"/>',
  "arrow-up":'<path d="M12 20V4m-6 6 6-6 6 6"/>',
  flask:'<path d="M9 3h6m-5 0v7L5 19a1.5 1.5 0 0 0 1.3 2h11.4a1.5 1.5 0 0 0 1.3-2l-5-9V3M8 14h8"/>',
  calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 11h18m-13 5h2m4 0h2"/>',
  scan:'<path d="M8 3H3v5m13-5h5v5M3 16v5h5m8 0h5v-5M7 15l4-5 3 2 4-5"/>',
  sliders:'<path d="M4 7h4m4 0h8M4 17h8m4 0h4"/><circle cx="10" cy="7" r="2"/><circle cx="14" cy="17" r="2"/>',
  search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4.5 4.5"/>',
  download:'<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
  upload:'<path d="M12 16V4m-5 5 5-5 5 5M4 16v5h16v-5"/>',
  compass:'<circle cx="12" cy="12" r="9"/><path d="m16 8-2.5 5.5L8 16l2.5-5.5L16 8Z"/>',
  plus:'<path d="M12 4v16M4 12h16"/>',
  close:'<path d="m6 6 12 12M6 18 18 6"/>',
  check:'<path d="m5 12 4 4L19 6"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.5"/>',
  trend:'<path d="m3 17 6-6 4 4 8-10m-6 0h6v6"/>',
  bars:'<path d="M5 20v-6m5 6V8m5 12V4m5 16V10"/>',
  target:'<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  shield:'<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z"/><path d="m8 12 3 3 5-6"/>',
  warning:'<path d="M10.3 4a2 2 0 0 1 3.4 0l8 14a2 2 0 0 1-1.7 3H4a2 2 0 0 1-1.7-3l8-14Z"/><path d="M12 9v4m0 3v1"/>',
  refresh:'<path d="M20 7a9 9 0 0 0-15-2L3 7m0-5v5h5m-4 10a9 9 0 0 0 15 2l2-2m0 5v-5h-5"/>'
};
function icon(name, className = "") {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"${className ? ` class="${className}"` : ""}>${icons[name] || icons.info}</svg>`;
}
function hydrateIcons(parent = document) {
  $$('[data-icon]', parent).forEach((element) => { element.innerHTML = icon(element.dataset.icon); });
}

const state = {
  settings:null, presets:[], defaults:null, watchlist:[], latest:null, history:[],
  provider:{}, job:{running:false}, view:"live", query:"", sort:"score", page:0,
  pageSize:20, pollTimer:null, polling:false, lastJobError:null, scans:new Map(),
  detail:null, detailScan:null, detailRange:60, historyScan:null, historyPage:0,
  textSubmit:null, importBusy:false, scanSubmitting:false, lastFocus:new WeakMap(),
  historyOffset:0, historyTotal:0, historyBusy:false, workspaceBusy:false
};

async function api(path, body) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 45000);
  try {
    const response = await fetch(path, {
      method:body === undefined ? "GET" : "POST",
      headers:body === undefined ? {"Accept":"application/json"} : {"Accept":"application/json", "Content-Type":"application/json"},
      body:body === undefined ? undefined : JSON.stringify(body),
      signal:controller.signal, cache:"no-store"
    });
    let data;
    try { data = await response.json(); }
    catch (_) { throw new Error(`The server returned an unreadable response (${response.status}).`); }
    if (!response.ok) throw new Error(data.error || `Request failed (${response.status}).`);
    return data;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("The request took too long. Check that Nomisma is still running, then try again.");
    if (error instanceof TypeError) throw new Error("Cannot reach Nomisma. Check that the local server is running, then try again.");
    throw error;
  } finally { clearTimeout(timer); }
}

function toast(message, error = false) {
  const element = document.createElement("div");
  element.className = `toast${error ? " error" : ""}`;
  element.innerHTML = `${icon(error ? "warning" : "check")}<span>${escapeHTML(message)}</span>`;
  $("#toast-region").replaceChildren(element);
  setTimeout(() => element.remove(), error ? 8000 : 4500);
}
function showError(selector, message) {
  const element = $(selector);
  element.textContent = message || "";
  element.classList.toggle("hidden", !message);
}
function openDialog(dialog, focusSelector) {
  state.lastFocus.set(dialog, document.activeElement);
  if (!dialog.open) dialog.showModal();
  if (focusSelector) requestAnimationFrame(() => $(focusSelector, dialog)?.focus());
}
function closeDialog(dialog) { if (dialog?.open) dialog.close(); }

const filterFields = ["min_price", "max_price", "min_avg_volume", "min_relative_volume", "min_rsi", "max_rsi", "min_score", "min_return_20d", "max_atr_pct"];
const booleanFields = ["above_sma50", "above_sma200", "positive_macd"];
function filtersEqual(a, b) {
  if (!a || !b) return false;
  return [...filterFields, ...booleanFields].every((key) => a[key] === b[key]) && [...(a.sectors || [])].map((s) => s.toLowerCase()).sort().join("|") === [...(b.sectors || [])].map((s) => s.toLowerCase()).sort().join("|");
}
function presetFor(filters) { return state.presets.find((preset) => filtersEqual(preset.filters, filters)); }
function filterDescriptions(filters) {
  if (!filters) return [];
  const descriptions = [
    `Score ≥ ${number(filters.min_score)}`,
    `Rel. volume ≥ ${number(filters.min_relative_volume, 1)}×`,
    `RSI ${number(filters.min_rsi)}–${number(filters.max_rsi)}`
  ];
  if (filters.above_sma50) descriptions.push("Above 50-day SMA");
  if (filters.above_sma200) descriptions.push("Above 200-day SMA");
  if (filters.positive_macd) descriptions.push("MACD above signal");
  descriptions.push(`Price ${money(filters.min_price)}–${money(filters.max_price)}`);
  descriptions.push(`Avg. volume ≥ ${compact(filters.min_avg_volume)}`);
  descriptions.push(`20D return ≥ ${number(filters.min_return_20d, 1)}%`);
  descriptions.push(`ATR ≤ ${number(filters.max_atr_pct, 1)}%`);
  if (filters.sectors?.length) descriptions.push(`Sectors: ${filters.sectors.join(", ")}`);
  return descriptions;
}
function sourceName(source) { return ({demo:"Synthetic demo", alpaca:"Alpaca daily", csv:"Imported CSV"})[source] || source || "No data"; }
function sourceTag(source) { return `<span class="source-tag ${escapeHTML(source)}">${escapeHTML(sourceName(source))}</span>`; }
function average(results, field) {
  const values = results.map((item) => field === "score" ? item.score : item.metrics?.[field]).filter(numeric);
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
}

// Each chart uses the actual returned series. The SVG has an accessible label;
// the large detail chart also exposes exact dates and closes on hover or focus.
let chartId = 0;
function chartSVG(raw, {width = 300, height = 100, fill = true, grid = false, mini = false, label = "Historical closing prices"} = {}) {
  const bars = (raw || []).filter((bar) => numeric(bar.close));
  if (!bars.length) return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="No chart data"></svg>`;
  const closes = bars.map((bar) => bar.close);
  const padding = grid ? {top:12, bottom:13, left:0, right:47} : {top:5, bottom:5, left:1, right:1};
  const rawMin = Math.min(...closes), rawMax = Math.max(...closes);
  const margin = Math.max((rawMax - rawMin) * .1, Math.abs(rawMax) * .001, .01);
  const min = rawMin - margin, max = rawMax + margin;
  const innerWidth = width - padding.left - padding.right, innerHeight = height - padding.top - padding.bottom;
  const x = (i) => padding.left + i / Math.max(bars.length - 1, 1) * innerWidth;
  const y = (value) => padding.top + (max - value) / (max - min) * innerHeight;
  const points = closes.map((value, i) => `${x(i).toFixed(2)},${y(value).toFixed(2)}`);
  const line = `M${points.join(" L")}`;
  const area = `${line} L${x(bars.length - 1)},${height - padding.bottom} L${x(0)},${height - padding.bottom} Z`;
  const up = closes[closes.length - 1] >= closes[0];
  const color = up ? "#93ac73" : "#be8d7b";
  const id = `chart-fill-${++chartId}`;
  let gridLines = "";
  if (grid) for (let i = 0; i < 4; i++) {
    const value = min + (max - min) * i / 3, position = y(value);
    gridLines += `<line x1="0" y1="${position}" x2="${innerWidth}" y2="${position}" stroke="#eaf0e3" stroke-dasharray="3 4"/><text x="${innerWidth + 9}" y="${position + 3}" font-size="9" fill="#a8b598" font-family="system-ui,sans-serif">${number(value, value < 10 ? 2 : 0)}</text>`;
  }
  return `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="${escapeHTML(label)}"><defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="${color}" stop-opacity="${mini ? ".09" : ".20"}"/><stop offset="100%" stop-color="${color}" stop-opacity=".01"/></linearGradient></defs>${gridLines}${fill ? `<path d="${area}" fill="url(#${id})"/>` : ""}<path d="${line}" fill="none" stroke="${color}" stroke-width="${mini ? 1.5 : 1.7}" vector-effect="non-scaling-stroke" stroke-linecap="round" stroke-linejoin="round"/>${mini ? "" : `<circle cx="${x(bars.length - 1)}" cy="${y(closes[closes.length - 1])}" r="2.3" fill="${color}"/>`}</svg>`;
}
function sparkline(stock) {
  return `<div class="sparkline">${chartSVG(stock.chart?.slice(-60), {width:90, height:31, mini:true, label:`${stock.symbol}, latest 60 daily closes`})}</div>`;
}
function avatar(symbol) {
  const palettes = [["#eff2e7", "#889955"], ["#edf0f7", "#7d8faa"], ["#f6eee9", "#b19578"], ["#eef2f2", "#849c9a"], ["#f1edf5", "#a192ad"], ["#edf4e9", "#82a172"]];
  let sum = 0;
  for (const char of String(symbol)) sum += char.charCodeAt(0);
  const [background, color] = palettes[sum % palettes.length];
  return `<span class="company-avatar" style="--avatar-bg:${background};--avatar-color:${color}" aria-hidden="true">${escapeHTML(String(symbol).slice(0, 2))}</span>`;
}
function stockTable(scan, results, {page = 0, history = false} = {}) {
  if (!results.length) return emptyState("search", "No stocks match this view", state.query && !history ? "Try a different symbol, company name, or sector." : "Try a broader preset or adjust your filters to discover more setups.", history ? "" : '<button class="button subtle" data-action="filters">Adjust filters</button>');
  const start = page * state.pageSize;
  const rows = results.slice(start, start + state.pageSize).map((stock) => {
    const saved = state.watchlist.includes(stock.symbol);
    return `<tr><td><button class="star-button${saved ? " saved" : ""}" data-watch="${escapeHTML(stock.symbol)}" aria-label="${saved ? "Remove" : "Add"} ${escapeHTML(stock.symbol)} ${saved ? "from" : "to"} watchlist" aria-pressed="${saved}">${icon("star")}</button></td><td><button class="company-button" data-stock="${escapeHTML(stock.symbol)}" data-scan="${escapeHTML(scan.id)}">${avatar(stock.symbol)}<span class="company-copy"><span class="company-symbol">${escapeHTML(stock.symbol)}</span><span class="company-name" title="${escapeHTML(stock.name)}">${escapeHTML(stock.name || stock.sector || "US equity")}</span></span></button></td><td class="num"><div class="price-main">${money(stock.price)}</div><div class="price-change ${changeClass(stock.change_pct)}">${percent(stock.change_pct)}</div></td><td class="trend-column">${sparkline(stock)}</td><td class="num"><div class="score-cell"><span class="score-number">${number(stock.score, 0)}</span><span class="score-track" aria-hidden="true"><span style="width:${Math.max(0, Math.min(100, stock.score || 0))}%"></span></span></div></td><td class="num volume-value">${multiple(stock.metrics?.relative_volume)}</td><td class="num rsi-value">${number(stock.metrics?.rsi, 1)}</td><td><span class="setup-badge">${escapeHTML(stock.setup)}</span></td><td class="row-actions"><button class="detail-arrow" data-candles="${escapeHTML(stock.symbol)}" title="Full-screen candles" aria-label="Open ${escapeHTML(stock.symbol)} full-screen candlestick chart">${icon("trend")}</button><button class="detail-arrow" data-stock="${escapeHTML(stock.symbol)}" data-scan="${escapeHTML(scan.id)}" aria-label="Open ${escapeHTML(stock.symbol)} details">${icon("chevron-right")}</button></td></tr>`;
  }).join("");
  return `<table class="stock-table"><thead><tr><th><span class="sr-only">Watchlist</span></th><th>Company</th><th class="num">Price / day</th><th class="trend-column">60D trend</th><th class="num">Score <span title="Technical ranking, not a probability">/100</span></th><th class="num" title="Latest volume divided by prior 20-session average">Rel. vol.</th><th class="num" title="14-session relative strength index">RSI</th><th>Setup</th><th><span class="sr-only">Details</span></th></tr></thead><tbody>${rows}</tbody></table>`;
}
function emptyState(iconName, title, description, action = "") {
  return `<div class="empty-state">${icon(iconName)}<h3>${escapeHTML(title)}</h3><p>${escapeHTML(description)}</p>${action}</div>`;
}
function pageControls(total, page, context = "dashboard") {
  if (total <= state.pageSize) return "";
  const pages = Math.ceil(total / state.pageSize);
  return `<span class="pagination"><button class="icon-button" data-page="${page - 1}" data-page-context="${context}" ${page === 0 ? "disabled" : ""} aria-label="Previous results page">${icon("chevron-left")}</button><span>${page + 1} / ${pages}</span><button class="icon-button" data-page="${page + 1}" data-page-context="${context}" ${page + 1 >= pages ? "disabled" : ""} aria-label="Next results page">${icon("chevron-right")}</button></span>`;
}

function renderStats() {
  const scan = state.latest;
  const results = scan?.results || [];
  const count = scan?.matched_count || 0;
  const rate = scan?.universe_count ? count / scan.universe_count * 100 : null;
  const stats = [
    {name:"Stocks on your radar", value:number(count), unit:"", foot:`<span class="tag">${number(rate, 1)}% of universe</span><span>met your filters</span>`, icon:"scan", featured:true},
    {name:"Average signal score", value:number(average(results, "score"), 0), unit:"/ 100", foot:`${icon("target")}<span>Across matching stocks</span>`, icon:"target"},
    {name:"Average relative volume", value:number(average(results, "relative_volume"), 2), unit:"×", foot:`${icon("bars")}<span>vs. prior 20-session average</span>`, icon:"bars"},
    {name:"Universe screened", value:number(scan?.universe_count), unit:"stocks", foot:`<span class="live-dot"></span><span>${number(scan?.eligible_count)} with sufficient usable data</span>`, icon:"grid"}
  ];
  $("#stats-grid").innerHTML = stats.map((stat) => `<article class="stat-card${stat.featured ? " featured" : ""}"><div class="stat-top"><span>${stat.name}</span><span class="stat-icon">${icon(stat.icon)}</span></div><div class="stat-value">${stat.value}<span class="stat-unit">${stat.unit}</span></div><div class="stat-foot">${stat.foot}</div></article>`).join("");
}
function renderFilterChips() {
  const descriptions = filterDescriptions(state.latest?.filters || state.settings?.filters);
  $("#filter-count").textContent = descriptions.length;
  $("#active-filters").innerHTML = descriptions.slice(0, 4).map((item) => `<span class="filter-chip">${icon("check")}${escapeHTML(item)}</span>`).join("") + (descriptions.length > 4 ? `<button class="filter-chip more" data-action="filters" title="View and edit all filters">+${descriptions.length - 4} more</button>` : "");
  if (state.latest && !filtersEqual(state.latest.filters, state.settings.filters)) $("#active-filters").insertAdjacentHTML("beforeend", '<span class="filter-chip pending-chip">New filters saved · run to apply</span>');
}
function filteredResults() {
  const query = state.query.toLowerCase().trim();
  const results = (state.latest?.results || []).filter((stock) => !query || `${stock.symbol} ${stock.name} ${stock.sector}`.toLowerCase().includes(query));
  return results.sort((a, b) => {
    if (state.sort === "symbol") return a.symbol.localeCompare(b.symbol);
    const get = (stock) => state.sort === "relative_volume" ? stock.metrics?.relative_volume : stock[state.sort];
    return (get(b) ?? -Infinity) - (get(a) ?? -Infinity) || a.symbol.localeCompare(b.symbol);
  });
}
function renderResults() {
  const results = filteredResults();
  state.page = Math.min(state.page, Math.max(0, Math.ceil(results.length / state.pageSize) - 1));
  $("#match-count").textContent = number(state.latest?.matched_count || 0);
  $("#results-table").innerHTML = stockTable(state.latest, results, {page:state.page});
  const start = state.page * state.pageSize;
  const summary = results.length ? `Showing ${start + 1}–${Math.min(start + state.pageSize, results.length)} of ${number(results.length)} ${state.query ? "search results" : "matching stocks"}` : "0 matching stocks";
  $("#results-summary").innerHTML = `${summary}${pageControls(results.length, state.page)}`;
  $("#export-results").disabled = !state.latest;
}
function renderMarket() {
  const market = state.latest?.market;
  if (!market) {
    $("#market-panel").innerHTML = `<div class="market-top"><h2>Market pulse</h2><span class="market-label">BENCHMARK</span></div>${emptyState("trend", "Context unavailable", "Include enough SPY history to compare results with the broader market.")}`;
    return;
  }
  const bars = (market.chart || []).slice(-60);
  $("#market-panel").innerHTML = `<div class="market-top"><h2>Market pulse</h2><span class="market-label">LAST 60 SESSIONS</span></div><div class="market-name"><strong>${escapeHTML(market.symbol)}</strong><span>·</span><span>S&P 500 ETF</span></div><div class="market-price-row"><span class="market-price">${money(market.price)}</span><span class="market-change ${changeClass(market.change_pct)}">${percent(market.change_pct)} <span class="neutral">1D</span></span></div><div class="market-chart">${chartSVG(bars, {width:300, height:95, label:"SPY, last 60 daily closes"})}</div><div class="chart-dates"><span>${dateLabel(bars[0]?.date, {month:"short", day:"numeric"})}</span><span>${dateLabel(bars[bars.length - 1]?.date, {month:"short", day:"numeric"})}</span></div><div class="market-context"><span>Market trend</span><span class="context-badge${market.above_sma50 ? "" : " cautious"}">${icon(market.above_sma50 ? "trend" : "info")}${market.above_sma50 ? "Above" : "Below"} 50-day SMA</span></div>`;
}
function renderStrategy() {
  const filters = state.settings.filters;
  const preset = presetFor(filters);
  const schedule = state.settings.schedule;
  const source = state.settings.source;
  const universe = state.settings.universe === "custom" ? `${state.settings.symbols.length} custom symbols` : source === "csv" ? "Imported symbols" : source === "demo" ? "Synthetic stock universe" : ({curated:"Liquid US starter list", all:"All verified US-listed stocks"})[state.settings.universe];
  $("#strategy-panel").innerHTML = `<div class="strategy-top"><h2>Your strategy</h2><button class="icon-button" data-action="filters" aria-label="Edit your strategy">${icon("sliders")}</button></div><div class="strategy-name"><span class="strategy-emblem">${icon("compass")}</span><div><strong>${escapeHTML(preset?.name || "Custom strategy")}</strong><small>${escapeHTML(universe)}</small></div></div><div class="strategy-items"><div class="strategy-item"><span>Signal threshold</span><span>${number(filters.min_score)} / 100</span></div><div class="strategy-item"><span>Volume baseline</span><span>≥ ${number(filters.min_relative_volume, 1)}×</span></div><div class="strategy-item"><span>Momentum range</span><span>RSI ${number(filters.min_rsi)}–${number(filters.max_rsi)}</span></div><div class="strategy-item"><span>Data source</span><span>${escapeHTML(sourceName(source))}</span></div></div><div class="strategy-bottom"><span>${icon("clock")}${schedule.enabled ? `${escapeHTML(schedule.time)} ET · weekdays` : "Daily schedule is off"}</span><button class="text-button" data-action="settings">${schedule.enabled ? "Manage" : "Set schedule"} ${icon("arrow-right")}</button></div>`;
}
function renderWarnings() {
  const warnings = state.latest?.warnings || [];
  const element = $("#scan-warnings");
  element.classList.toggle("hidden", !warnings.length || state.view === "live");
  element.innerHTML = warnings.length ? `<details><summary>${icon("info")}<span>${escapeHTML(warnings[0])}${warnings.length > 1 ? ` <span class="warning-count">+${warnings.length - 1} data notes</span>` : ""}</span></summary><ul>${warnings.map((warning) => `<li>${escapeHTML(warning)}</li>`).join("")}</ul></details>` : "";
}
async function loadHistory(offset = 0) {
  if (state.historyBusy) return;
  state.historyBusy = true;
  showError("#history-error", "");
  renderHistory();
  try {
    const result = await api(`/api/history?limit=${state.pageSize}&offset=${Math.max(0, offset)}`);
    state.history = result.history || [];
    state.historyTotal = result.total;
    state.historyOffset = result.offset;
  } catch (error) { showError("#history-error", error.message); }
  finally { state.historyBusy = false; renderHistory(); }
}
function renderHistory() {
  $("#history-count").textContent = `${number(state.historyTotal)} ${state.historyTotal === 1 ? "scan" : "scans"}`;
  $("#history-page-label").textContent = state.historyBusy ? "Loading history…" : state.historyTotal ? `${state.historyOffset+1}–${Math.min(state.historyOffset+state.history.length, state.historyTotal)} of ${number(state.historyTotal)} scans` : "No saved scans";
  $("#history-previous").disabled = state.historyBusy || state.historyOffset === 0;
  $("#history-next").disabled = state.historyBusy || state.historyOffset + state.pageSize >= state.historyTotal;
  if (!state.history.length) {
    $("#history-results").innerHTML = emptyState("history", "Your research starts here", "Completed scans appear here with their original data date, filters, and ranked results.");
    return;
  }
  $("#history-results").innerHTML = `<table class="history-table"><thead><tr><th>Completed</th><th>Data source</th><th>Data as of</th><th>Matches</th><th><span class="sr-only">Actions</span></th></tr></thead><tbody>${state.history.map((scan) => `<tr><td>${timestampLabel(scan.created_at)}</td><td>${sourceTag(scan.source)}</td><td>${dateLabel(scan.as_of)}</td><td>${number(scan.matched_count)}</td><td><button class="text-button" data-history="${escapeHTML(scan.id)}">View scan ${icon("arrow-up-right")}</button><button class="icon-button" data-export="${escapeHTML(scan.id)}" aria-label="Export scan from ${escapeHTML(dateLabel(scan.as_of))}">${icon("download")}</button></td></tr>`).join("")}</tbody></table>`;
}
function renderHeader() {
  const scan = state.latest;
  $("#as-of-label").textContent = scan ? `Data as of ${dateLabel(scan.as_of)}` : "No completed scan";
  $("#demo-banner").classList.toggle("hidden", scan?.source !== "demo" || state.view === "live");
  $("#connection-label").textContent = scan ? sourceName(scan.source) : "Local workspace";
  $("#connection-button").classList.toggle("live", scan?.source === "alpaca" && state.view !== "live");
  $("#connection-button").classList.toggle("imported", scan?.source === "csv");
  $("#run-scan").disabled = Boolean(state.job.running || state.scanSubmitting);
  $("#scan-button-label").textContent = state.job.running || state.scanSubmitting ? "Screening…" : "Run screener";
  if (state.view === "live") $("#connection-label").textContent = "Workspace settings";
}
function renderAll() {
  renderHeader(); renderStats(); renderFilterChips(); renderResults(); renderMarket(); renderStrategy(); renderWarnings(); renderHistory();
}
function changeView(view, updateHash = true) {
  const metadata = {
    live:["INTRADAY · PENNY-STOCK MOMENTUM", "Catch the move. Know the setup", "Follow price, participation, and momentum as the session unfolds."],
    dashboard:["YOUR DAILY RESEARCH WORKSPACE", "Your market, in focus", "Find strength in the noise. Discover stocks that meet your strategy."],
    history:["YOUR RESEARCH, OVER TIME", "Every scan tells a story", "Revisit your screens and the market conditions behind them."]
  };
  if (!metadata[view]) view = "live";
  state.view = view;
  if (view === "history") loadHistory(state.historyOffset);
  $$(".view-panel").forEach((panel) => panel.classList.toggle("hidden", panel.id !== `${view}-view`));
  $$("[data-view]").forEach((button) => {
    const active = button.dataset.view === view;
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page"); else button.removeAttribute("aria-current");
  });
  $("#page-eyebrow").textContent = metadata[view][0];
  $("#page-title").innerHTML = `${metadata[view][1]}<span>.</span>`;
  $("#page-description").textContent = metadata[view][2];
  $(".heading-actions").classList.toggle("hidden", view === "live");
  $("#job-status").classList.toggle("hidden", view === "live" || !state.job.running);
  renderHeader();
  renderWarnings();
  document.body.classList.toggle("live-active", view === "live");
  document.title = `Nomisma — ${view === "history" ? "Scan history" : view.charAt(0).toUpperCase() + view.slice(1)}`;
  if (updateHash && window.location.hash !== `#${view}`) history.replaceState(null, "", `#${view}`);
}

function schedulePoll(delay = 15000) {
  clearTimeout(state.pollTimer);
  state.pollTimer = setTimeout(pollStatus, delay);
}
function applyJob(job, notify = true) {
  const wasRunning = state.job.running;
  state.job = job || {running:false};
  $("#job-status").classList.toggle("hidden", !state.job.running || state.view === "live");
  $("#job-message").textContent = state.job.message || "Screening your stock universe…";
  if (state.job.error && state.job.error !== state.lastJobError) {
    state.lastJobError = state.job.error;
    showError("#global-error", `The scan did not finish: ${state.job.error} The last completed results are still shown.`);
  } else if (state.job.running) {
    state.lastJobError = null;
    showError("#global-error", "");
  }
  if (notify && wasRunning && !state.job.running && !state.job.error) toast("Your screen is ready. Results have been updated.");
  renderHeader();
}
async function pollStatus() {
  if (state.polling || !state.settings) return;
  state.polling = true;
  try {
    const result = await api(`/api/status${state.latest?.id ? `?since=${encodeURIComponent(state.latest.id)}` : ""}`);
    const changed = Boolean(result.latest && result.latest.id !== state.latest?.id);
    if (result.latest) state.latest = result.latest;
    if (changed) await loadHistory(state.historyOffset);
    if (state.pollFailed) showError("#global-error", "");
    state.pollFailed = false;
    applyJob(result.job);
    if (changed) {
      state.page = 0;
      if (!result.job?.error) showError("#global-error", "");
      renderAll();
    }
  } catch (error) {
    state.pollFailed = true;
    if (state.job.running) showError("#global-error", `Checking scan progress failed: ${error.message} Retrying automatically.`);
  } finally {
    state.polling = false;
    schedulePoll(state.job.running ? 1400 : 15000);
  }
}
async function runScan() {
  if (state.job.running || state.scanSubmitting) return;
  state.scanSubmitting = true;
  renderHeader();
  showError("#global-error", "");
  try {
    const {filters, source, universe, symbols} = state.settings;
    const result = await api("/api/scan", {filters, source, universe, symbols});
    applyJob(result.job, false);
    schedulePoll(400);
  } catch (error) {
    showError("#global-error", error.message);
    toast("The screen could not start. Check the message above.", true);
  } finally { state.scanSubmitting = false; renderHeader(); }
}

function setFilterForm(filters) {
  const form = $("#filters-form");
  filterFields.forEach((key) => { form.elements[key].value = filters[key]; });
  booleanFields.forEach((key) => { form.elements[key].checked = filters[key]; });
  form.elements.sectors.value = (filters.sectors || []).join(", ");
  $("#preset-select").value = presetFor(filters)?.id || "";
  renderSectorSuggestions();
}
function getFilterForm() {
  const form = $("#filters-form"), filters = {};
  filterFields.forEach((key) => {
    if (!form.elements[key].value.trim()) throw new Error("Fill in all numeric filter values.");
    filters[key] = Number(form.elements[key].value);
    if (!Number.isFinite(filters[key])) throw new Error("Filter values must be finite numbers.");
  });
  booleanFields.forEach((key) => { filters[key] = form.elements[key].checked; });
  filters.sectors = [...new Set(form.elements.sectors.value.split(",").map((sector) => sector.trim()).filter(Boolean))];
  if (filters.min_price > filters.max_price) throw new Error("Minimum price cannot exceed maximum price.");
  if (filters.min_rsi > filters.max_rsi) throw new Error("Minimum RSI cannot exceed maximum RSI.");
  return filters;
}
function updatePresetOptions() {
  $("#preset-select").innerHTML = '<option value="">Custom strategy</option>' + state.presets.map((preset) => `<option value="${escapeHTML(preset.id)}" title="${escapeHTML(preset.description)}">${escapeHTML(preset.name)}</option>`).join("");
}
function renderSectorSuggestions() {
  const sectors = [...new Set((state.latest?.results || []).map((stock) => stock.sector).filter(Boolean))].sort().slice(0, 12);
  const selected = $("#filter-sectors").value.split(",").map((value) => value.trim().toLowerCase());
  $("#sector-suggestions").innerHTML = sectors.map((sector) => `<button type="button" data-sector="${escapeHTML(sector)}" class="${selected.includes(sector.toLowerCase()) ? "selected" : ""}" aria-pressed="${selected.includes(sector.toLowerCase())}">${escapeHTML(sector)}</button>`).join("");
}
function openFilters() {
  updatePresetOptions();
  setFilterForm(state.settings.filters);
  showError("#filters-error", "");
  openDialog($("#filters-dialog"), "#preset-select");
}
async function saveFilters(event) {
  event.preventDefault();
  const button = $('#filters-form button[type="submit"]');
  button.disabled = true;
  showError("#filters-error", "");
  try {
    const filters = getFilterForm();
    const result = await api("/api/settings", {filters});
    state.settings = result.settings;
    closeDialog($("#filters-dialog"));
    renderFilterChips(); renderStrategy();
    toast("Filters saved. Run the screener to apply them.");
  } catch (error) { showError("#filters-error", error.message); }
  finally { button.disabled = false; }
}
function openTextDialog({title, description, label, placeholder = "", submit = "Save", onSubmit, maxLength = 80}) {
  $("#text-dialog-title").textContent = title;
  $("#text-dialog-description").textContent = description;
  $("#text-field-label").firstChild.textContent = label;
  $("#text-input").value = "";
  $("#text-input").placeholder = placeholder;
  $("#text-input").maxLength = maxLength;
  $("#text-submit").textContent = submit;
  showError("#text-error", "");
  state.textSubmit = onSubmit;
  openDialog($("#text-dialog"), "#text-input");
}
function savePreset() {
  let filters;
  try {
    if (!$("#filters-form").reportValidity()) return;
    filters = getFilterForm();
  } catch (error) { showError("#filters-error", error.message); return; }
  openTextDialog({title:"Save your strategy", description:"Keep this filter combination as a reusable preset.", label:"Preset name", placeholder:"e.g. Liquid momentum", onSubmit:async (name) => {
    const result = await api("/api/presets", {name, filters});
    state.presets = result.presets;
    updatePresetOptions();
    $("#preset-select").value = presetFor(filters)?.id || "";
    toast("Preset saved. Save filters to use it for future scans.");
  }});
}

function updateSourceControls() {
  const source = $("#settings-source").value;
  const configurationLocation = window.nomismaDesktop?.configFile ? `<code>${escapeHTML(window.nomismaDesktop.configFile)}</code> (${window.nomismaDesktop.platform === "windows" ? "File" : "Nomisma"} menu → Open Configuration Folder)` : '<code>.env</code> in the Nomisma folder';
  $("#provider-controls").classList.remove("hidden");
  const universeSelect = $("#settings-universe");
  const allDescription = source === "alpaca" ? "All verified US-listed stocks" : source === "csv" ? "All symbols in your imported CSV" : "All symbols in the synthetic demo";
  universeSelect.options[0].textContent = source === "alpaca" ? "Liquid US stocks · starter universe" : source === "csv" ? "Imported dataset · default universe" : "Synthetic demo · default universe";
  universeSelect.options[1].textContent = allDescription;
  $("#csv-import-box").classList.toggle("hidden", source !== "csv");
  $("#custom-symbols-field").classList.toggle("hidden", $("#settings-universe").value !== "custom");
  const help = {
    demo:'<p><strong>A place to explore.</strong> Demo mode uses synthetic prices with a fixed historical data date. It demonstrates screening and scoring, but does not describe today’s market.</p>',
    alpaca:state.provider.alpaca_configured ? `<p><strong>Alpaca is configured.</strong> Your server uses the ${escapeHTML(String(state.provider.feed || "iex").toUpperCase())} feed and completed daily sessions.</p>${state.provider.feed === "iex" ? '<p>IEX volume is exchange-specific. Volume and liquidity filters can behave differently from consolidated market data.</p>' : ""}<p>The full exchange-listed universe can take several minutes. Failed requests are reported and can be retried.</p>` : `<p><strong>Connect Alpaca on your server.</strong> Add your credentials to ${configurationLocation}, then restart the local server and reload this workspace.</p><pre>ALPACA_API_KEY=your_key\nALPACA_SECRET_KEY=your_secret\nALPACA_FEED=iex\nALPACA_PAPER=true</pre><p>Use <code>ALPACA_PAPER=false</code> for live-account credentials. Credentials stay on your server. IEX data covers one exchange; consolidated SIP data requires the appropriate provider subscription.</p>`,
    csv:`<p><strong>${state.provider.csv_available ? "Your imported data is ready." : "Import daily prices to get started."}</strong> Your scan will use the symbols and completed sessions contained in the file. Uploading a new file replaces the workspace’s imported dataset; previous completed scans remain available.</p>`
  };
  $("#data-source-help").innerHTML = help[source];
}
function openSettings() {
  const settings = state.settings;
  $("#settings-source").value = settings.source;
  $("#settings-universe").value = settings.universe;
  $("#settings-symbols").value = settings.symbols.join(", ");
  $("#schedule-enabled").checked = settings.schedule.enabled;
  $("#schedule-time").value = settings.schedule.time;
  $("#csv-file").value = "";
  $("#import-status").textContent = "";
  showError("#settings-error", "");
  updateSourceControls();
  openDialog($("#settings-dialog"), "#settings-source");
}
function updateRestoreControls() {
  $("#workspace-restore").disabled = state.workspaceBusy || !$("#workspace-restore-file").files.length || !$("#workspace-restore-confirm").checked;
  $("#workspace-backup").disabled = state.workspaceBusy;
  $("#workspace-restore-file").disabled = state.workspaceBusy;
  $("#workspace-restore-confirm").disabled = state.workspaceBusy;
  $('#settings-form button[type="submit"]').disabled = state.workspaceBusy || state.importBusy;
}
async function downloadBackup() {
  if (state.workspaceBusy) return;
  state.workspaceBusy = true;
  updateRestoreControls();
  showError("#workspace-data-error", "");
  $("#workspace-data-status").textContent = "Preparing a consistent backup…";
  try {
    const response = await fetch("/api/workspace/backup", {cache:"no-store"});
    if (!response.ok) throw new Error((await response.json()).error || "The backup could not be downloaded.");
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = `nomisma-backup-${new Date().toISOString().replace(/[:.]/g, "-")}.sqlite3`;
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    $("#workspace-data-status").textContent = "Workspace backup downloaded.";
  } catch (error) { showError("#workspace-data-error", error.message); $("#workspace-data-status").textContent = "Backup did not complete."; }
  finally { state.workspaceBusy = false; updateRestoreControls(); }
}
async function restoreWorkspace() {
  const file = $("#workspace-restore-file").files[0];
  if (state.workspaceBusy || !file || !$("#workspace-restore-confirm").checked) return;
  showError("#workspace-data-error", "");
  if (!file.size || file.size > 128 * 1024 * 1024) { showError("#workspace-data-error", "Choose a nonempty Nomisma backup no larger than 128 MB."); return; }
  if (state.job.running) { showError("#workspace-data-error", "Wait for the daily scan to finish before restoring."); return; }
  state.workspaceBusy = true;
  updateRestoreControls();
  $("#workspace-data-status").textContent = "Validating your backup and preserving the current workspace…";
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 120000);
  try {
    const response = await fetch("/api/workspace/restore", {method:"POST", headers:{"Content-Type":"application/octet-stream",Accept:"application/json"}, body:file, signal:controller.signal});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "The backup could not be restored.");
    $("#workspace-data-status").textContent = `Workspace restored. Safety backup: ${result.backup_path}. Reloading…`;
    // Read the restored state only after the server has replaced its database.
    setTimeout(() => location.reload(), 1800);
  } catch (error) {
    showError("#workspace-data-error", error.name === "AbortError" ? "Restore response timed out. Reload to check the workspace before retrying." : error.message);
    $("#workspace-data-status").textContent = "Restore did not complete successfully.";
    state.workspaceBusy = false;
    updateRestoreControls();
  } finally { clearTimeout(timer); }
}
async function saveSettings(event) {
  event.preventDefault();
  if (state.importBusy || state.workspaceBusy) return;
  const button = $('#settings-form button[type="submit"]');
  button.disabled = true;
  showError("#settings-error", "");
  try {
    const source = $("#settings-source").value;
    const universe = $("#settings-universe").value;
    const symbols = [...new Set($("#settings-symbols").value.toUpperCase().split(/[\s,;]+/).filter(Boolean))];
    if (source === "alpaca" && !state.provider.alpaca_configured) throw new Error("Configure the Alpaca credentials on your server, restart Nomisma, and reload this page before choosing this source.");
    if (source === "csv" && !state.provider.csv_available) throw new Error("Import a CSV file before saving CSV as your data source.");
    if (universe === "custom" && !symbols.length) throw new Error("Enter at least one symbol for your custom universe.");
    const result = await api("/api/settings", {source, universe, symbols, schedule:{enabled:$("#schedule-enabled").checked, time:$("#schedule-time").value, timezone:"America/New_York"}});
    state.settings = result.settings;
    closeDialog($("#settings-dialog"));
    renderStrategy(); renderFilterChips();
    toast("Settings saved. Your next scan will use this configuration.");
  } catch (error) { showError("#settings-error", error.message); }
  finally { button.disabled = false; }
}
async function importCSV(event) {
  const file = event.target.files[0];
  if (!file || state.importBusy) return;
  showError("#settings-error", "");
  if (file.size > 20 * 1024 * 1024) { showError("#settings-error", "This file exceeds the 20 MB upload limit."); event.target.value = ""; return; }
  state.importBusy = true;
  $("#csv-file").disabled = true;
  $('#settings-form button[type="submit"]').disabled = true;
  $("#import-status").textContent = `Reading and validating ${file.name}…`;
  try {
    const csv = await file.text();
    const result = await api("/api/import", {csv});
    state.provider.csv_available = true;
    $("#import-status").textContent = `${number(result.asset_count)} symbols imported · data as of ${dateLabel(result.as_of)}. Save settings, then run the screener.`;
    updateSourceControls();
    toast("CSV data imported and validated.");
  } catch (error) { $("#import-status").textContent = "Import did not complete."; showError("#settings-error", error.message); }
  finally { state.importBusy = false; $("#csv-file").disabled = false; $('#settings-form button[type="submit"]').disabled = false; event.target.value = ""; }
}

const watchBusy = new Set();
async function toggleWatch(symbol, enabled) {
  if (watchBusy.has(symbol)) return;
  watchBusy.add(symbol);
  const focused = document.activeElement;
  try {
    const result = await api("/api/watchlist", {symbol, enabled:enabled ?? !state.watchlist.includes(symbol)});
    state.watchlist = result.watchlist;
    renderResults();
    if (state.detail) renderStockWatchButton();
    if (state.historyScan && $("#history-dialog").open) renderHistoryDetail();
    if (focused?.dataset.watch === symbol && !focused.isConnected) {
      const context = $("#history-dialog").open ? $("#history-dialog") : $(`#${state.view}-view`);
      const replacement = $$("[data-watch]", context || document).find((element) => element.dataset.watch === symbol);
      replacement?.focus();
    }
    toast(`${symbol} ${state.watchlist.includes(symbol) ? "added to" : "removed from"} your watchlist.`);
  } catch (error) { toast(error.message, true); throw error; }
  finally { watchBusy.delete(symbol); }
}
async function getScan(id) {
  if (String(state.latest?.id) === String(id)) return state.latest;
  if (state.scans.has(String(id))) return state.scans.get(String(id));
  const scan = await api(`/api/scans/${encodeURIComponent(id)}`);
  state.scans.set(String(id), scan);
  return scan;
}
function renderStockWatchButton() {
  const element = $("#detail-watch-button");
  if (!element || !state.detail) return;
  const saved = state.watchlist.includes(state.detail.symbol);
  element.innerHTML = `${icon("star")}<span class="watch-button-text">${saved ? "Watching" : "Watch"}</span>`;
  element.classList.toggle("watching", saved);
  element.setAttribute("aria-pressed", String(saved));
  element.setAttribute("aria-label", `${saved ? "Remove" : "Add"} ${state.detail.symbol} ${saved ? "from" : "to"} watchlist`);
}
async function openStock(symbol, scanId) {
  try {
    const scan = await getScan(scanId);
    const stock = scan.results.find((item) => item.symbol === symbol);
    if (!stock) throw new Error("This stock is not in the selected scan.");
    state.detail = stock; state.detailScan = scan; state.detailRange = 60;
    renderStockDetail();
    openDialog($("#stock-dialog"));
  } catch (error) { toast(error.message, true); }
}
function renderStockDetail() {
  const stock = state.detail, scan = state.detailScan, metrics = stock.metrics || {};
  const metricItems = [
    ["RSI · 14 sessions", number(metrics.rsi, 1)], ["Relative volume", multiple(metrics.relative_volume)],
    ["20-session return", percent(metrics.return_20d)], ["ATR / price", numeric(metrics.atr_pct) ? `${number(metrics.atr_pct, 2)}%` : "—"],
    ["50-day average", money(metrics.sma50)], ["200-day average", money(metrics.sma200)],
    ["Relative strength vs SPY", numeric(metrics.relative_strength) ? `${metrics.relative_strength > 0 ? "+" : ""}${number(metrics.relative_strength, 2)} pp` : "Unavailable"],
    ["Prior 20D high distance", percent(metrics.breakout_distance)]
  ];
  $("#stock-detail").innerHTML = `<div class="stock-header"><div class="stock-header-top"><div class="stock-identity">${avatar(stock.symbol)}<div><h2 id="stock-title">${escapeHTML(stock.symbol)}</h2><p>${escapeHTML(stock.name)} · ${escapeHTML(stock.sector || "Sector unavailable")}</p></div></div><div class="stock-header-actions"><button class="button subtle" data-candles="${escapeHTML(stock.symbol)}" title="Full-screen candlestick chart · 1m to 1D">${icon("trend")}<span class="watch-button-text">Candles</span></button><button class="button subtle" id="detail-watch-button" data-watch="${escapeHTML(stock.symbol)}"></button><button class="icon-button" data-close aria-label="Close stock details">${icon("close")}</button></div></div><div class="stock-price-row"><div><div class="stock-price-large">${money(stock.price)}<small class="${changeClass(stock.change_pct)}">${percent(stock.change_pct)}</small></div><div class="stock-as-of">${escapeHTML(sourceName(scan.source))} · ${escapeHTML(scan.feed || "Daily closes")} · ${dateLabel(stock.as_of)}${scan.source === "demo" ? " · Prices are synthetic" : ""}</div></div><div class="stock-score"><div class="score-circle" style="--score-angle:${Math.min(100, Math.max(0, stock.score)) * 3.6}deg">${number(stock.score)}</div><div><strong>Signal score</strong><small>Ranking, not probability</small></div></div></div></div><section class="stock-chart-section"><div class="chart-heading"><span>Daily closing price · USD</span><div class="chart-range" role="group" aria-label="Chart range"><button data-range="20">20D</button><button data-range="60" class="active">60D</button><button data-range="120">120D</button></div></div><div id="detail-chart" class="detail-chart" tabindex="0" aria-label="Historical closing prices. Use left and right arrow keys to explore values."></div><div id="detail-chart-dates" class="chart-dates"></div></section><div class="stock-metrics">${metricItems.map(([label, value]) => `<div class="stock-metric"><small>${label}</small><strong>${value}</strong></div>`).join("")}</div><div class="detail-bottom"><section><h3>What’s behind the score</h3>${(stock.signals || []).map((signal) => `<div class="signal-row"><div class="signal-label"><span>${escapeHTML(signal.name)}</span><strong>${number(signal.points, 1)} <span class="neutral">/ ${number(signal.max_points)}</span></strong></div><div class="signal-bar" aria-hidden="true"><span style="width:${signal.max_points ? Math.max(0, Math.min(100, signal.points / signal.max_points * 100)) : 0}%"></span></div><p class="signal-description">${escapeHTML(signal.description)}</p></div>`).join("")}</section><section class="risk-box"><h3>${icon("shield")}Keep in perspective</h3>${stock.risks?.length ? `<ul>${stock.risks.map((risk) => `<li>${escapeHTML(risk)}</li>`).join("")}</ul>` : '<p>No specific technical warnings were flagged by this screen. Risk remains in every investment.</p>'}<p class="risk-note">A technical setup is a research lead. Scores are not calibrated odds of gains. Review the company, news, liquidity, and your own risk limits before making a decision.</p></section></div><footer class="detail-footer"><span>${escapeHTML(stock.exchange || "Exchange not provided")} · ${escapeHTML(scan.label || sourceName(scan.source))}</span></footer>`;
  renderStockWatchButton(); renderDetailChart();
}
function renderDetailChart() {
  const bars = (state.detail.chart || []).slice(-state.detailRange);
  const container = $("#detail-chart");
  container.innerHTML = chartSVG(bars, {width:700, height:190, grid:true, label:`${state.detail.symbol}, ${bars.length} daily closes from ${bars[0]?.date || "unavailable"} to ${bars[bars.length - 1]?.date || "unavailable"}`}) + '<div class="chart-tooltip hidden" id="chart-tooltip"></div>';
  $("#detail-chart-dates").innerHTML = `<span>${dateLabel(bars[0]?.date)}</span><span>${bars.length} trading sessions</span><span>${dateLabel(bars[bars.length - 1]?.date)}</span>`;
  $$("[data-range]", $("#stock-dialog")).forEach((button) => {
    button.classList.toggle("active", Number(button.dataset.range) === state.detailRange);
    button.setAttribute("aria-pressed", String(Number(button.dataset.range) === state.detailRange));
  });
  let current = bars.length - 1;
  function showValue(index) {
    if (!bars.length) return;
    current = Math.max(0, Math.min(bars.length - 1, index));
    const bar = bars[current], tooltip = $("#chart-tooltip");
    tooltip.innerHTML = `${dateLabel(bar.date)} <strong>${money(bar.close)}</strong>${numeric(bar.volume) ? `<br>Volume ${compact(bar.volume)}` : ""}`;
    tooltip.classList.remove("hidden");
    container.setAttribute("aria-label", `${state.detail.symbol}, ${dateLabel(bar.date)}, close ${money(bar.close)}. Use arrow keys to explore.`);
  }
  container.onpointermove = (event) => {
    const rect = container.getBoundingClientRect();
    const fraction = (event.clientX - rect.left) / (rect.width * (653 / 700));
    showValue(Math.round(fraction * (bars.length - 1)));
  };
  container.onpointerleave = () => { if (document.activeElement !== container) $("#chart-tooltip").classList.add("hidden"); };
  container.onfocus = () => showValue(current);
  container.onblur = () => $("#chart-tooltip").classList.add("hidden");
  container.onkeydown = (event) => {
    if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
      event.preventDefault();
      showValue(event.key === "Home" ? 0 : event.key === "End" ? bars.length - 1 : current + (event.key === "ArrowLeft" ? -1 : 1));
    }
  };
}
async function openHistory(id) {
  $("#history-detail").innerHTML = `<div class="modal-header"><h2 id="history-title">Opening scan</h2><button class="icon-button" data-close aria-label="Close scan history">${icon("close")}</button></div><div class="initial-loading"><span class="spinner"></span><p>Loading the original results…</p></div>`;
  state.historyScan = null;
  openDialog($("#history-dialog"));
  try {
    const scan = await getScan(id);
    if (!$("#history-dialog").open) return;
    state.historyScan = scan; state.historyPage = 0;
    renderHistoryDetail();
  } catch (error) {
    $("#history-detail").innerHTML = `<div class="modal-header"><h2 id="history-title">Couldn’t open this scan</h2><button class="icon-button" data-close aria-label="Close scan history">${icon("close")}</button></div>${emptyState("warning", "Scan unavailable", error.message)}`;
  }
}
function renderHistoryDetail() {
  const scan = state.historyScan;
  const descriptions = filterDescriptions(scan.filters);
  $("#history-detail").innerHTML = `<div class="modal-header"><div><div class="eyebrow">COMPLETED SCAN</div><h2 id="history-title">${dateLabel(scan.as_of)} market screen</h2><p>Run ${timestampLabel(scan.created_at)} · ${escapeHTML(scan.label || sourceName(scan.source))}</p></div><button class="icon-button" data-close aria-label="Close scan history">${icon("close")}</button></div><div class="history-summary">${sourceTag(scan.source)}<span><strong>${number(scan.matched_count)}</strong>matches</span><span><strong>${number(scan.universe_count)}</strong>screened</span><button class="text-button" data-export="${escapeHTML(scan.id)}">${icon("download")}Export CSV</button></div>${scan.source === "demo" ? '<div class="history-demo-note">Synthetic historical data. These prices and signals do not describe the live market.</div>' : ""}<div class="history-filters">${descriptions.map((description) => `<span class="filter-chip">${escapeHTML(description)}</span>`).join("")}</div><div class="table-scroll">${stockTable(scan, scan.results || [], {page:state.historyPage, history:true})}</div><div class="table-footer"><span>${number(scan.matched_count)} matching stocks · data as of ${dateLabel(scan.as_of)}</span>${pageControls(scan.results.length, state.historyPage, "history")}</div>${scan.warnings?.length ? `<div class="history-warning-notes"><details><summary>${scan.warnings.length} data notes</summary><ul>${scan.warnings.map((warning) => `<li>${escapeHTML(warning)}</li>`).join("")}</ul></details></div>` : ""}`;
}
async function exportScan(id) {
  if (!id) { toast("Run a screen before exporting results.", true); return; }
  try {
    const response = await fetch(`/api/export.csv?scan=${encodeURIComponent(id)}`, {cache:"no-store"});
    if (!response.ok) {
      let message = `Export failed (${response.status}).`;
      try { message = (await response.json()).error || message; } catch (_) { /* Keep HTTP status. */ }
      throw new Error(message);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url; link.download = `nomisma-scan-${String(id).replace(/[^a-z0-9_-]/gi, "")}.csv`;
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    toast("Full scan exported as CSV.");
  } catch (error) { toast(error.message, true); }
}

function bindEvents() {
  hydrateIcons();
  $("#run-scan").addEventListener("click", runScan);
  $("#edit-filters").addEventListener("click", openFilters);
  ["#connection-button", "#sidebar-settings", "#connect-data"].forEach((selector) => $(selector).addEventListener("click", () => { if (state.settings) openSettings(); }));
  $("#filters-form").addEventListener("submit", saveFilters);
  $("#settings-form").addEventListener("submit", saveSettings);
  $("#settings-source").addEventListener("change", updateSourceControls);
  $("#settings-universe").addEventListener("change", updateSourceControls);
  $("#csv-file").addEventListener("change", importCSV);
  $("#history-previous").addEventListener("click", () => loadHistory(state.historyOffset - state.pageSize));
  $("#history-next").addEventListener("click", () => loadHistory(state.historyOffset + state.pageSize));
  $("#workspace-backup").addEventListener("click", downloadBackup);
  $("#workspace-restore-file").addEventListener("change", () => { $("#workspace-restore-confirm").checked = false; updateRestoreControls(); });
  $("#workspace-restore-confirm").addEventListener("change", updateRestoreControls);
  $("#workspace-restore").addEventListener("click", restoreWorkspace);
  $("#save-preset").addEventListener("click", savePreset);
  $("#preset-select").addEventListener("change", (event) => {
    const preset = state.presets.find((item) => item.id === event.target.value);
    if (preset) { setFilterForm(preset.filters); showError("#filters-error", ""); }
  });
  $("#filters-form").addEventListener("input", (event) => {
    if (event.target.id === "preset-select") return;
    $("#preset-select").value = "";
    if (event.target.name === "sectors") renderSectorSuggestions();
  });
  $("#reset-filters").addEventListener("click", () => { setFilterForm(state.defaults); showError("#filters-error", ""); });
  $("#stock-search").addEventListener("input", (event) => { state.query = event.target.value; state.page = 0; renderResults(); });
  $("#stock-sort").addEventListener("change", (event) => { state.sort = event.target.value; state.page = 0; renderResults(); });
  $("#export-results").addEventListener("click", () => exportScan(state.latest?.id));
  $("#text-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const value = $("#text-input").value.trim();
    if (!value) { showError("#text-error", "Enter a value before saving."); return; }
    $("#text-submit").disabled = true;
    showError("#text-error", "");
    try { await state.textSubmit(value); closeDialog($("#text-dialog")); }
    catch (error) { showError("#text-error", error.message); }
    finally { $("#text-submit").disabled = false; }
  });
  $$('dialog').forEach((dialog) => {
    dialog.addEventListener("close", () => {
      const previous = state.lastFocus.get(dialog);
      if (previous?.isConnected) previous.focus();
      else {
        const parentDialog = $$("dialog[open]").at(-1);
        if (parentDialog) $("button, input, select", parentDialog)?.focus();
        else $("#main-content").focus();
      }
    });
    dialog.addEventListener("click", (event) => {
      if (event.target !== dialog) return;
      const rect = dialog.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) closeDialog(dialog);
    });
  });
  document.addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    if (!button || button.disabled) return;
    if (button.hasAttribute("data-close")) { closeDialog(button.closest("dialog")); return; }
    if (!state.settings) return;
    if (button.dataset.view) { changeView(button.dataset.view); return; }
    if (button.dataset.watch) { try { await toggleWatch(button.dataset.watch); } catch (_) { /* Already shown. */ } return; }
    if (button.dataset.candles) { window.nomismaCandles?.(button.dataset.candles); return; }
    if (button.dataset.stock) { await openStock(button.dataset.stock, button.dataset.scan); return; }
    if (button.dataset.history) { await openHistory(button.dataset.history); return; }
    if (button.dataset.export) { await exportScan(button.dataset.export); return; }
    if (button.dataset.sector) {
      const sector = button.dataset.sector;
      const values = $("#filter-sectors").value.split(",").map((s) => s.trim()).filter(Boolean);
      const index = values.findIndex((s) => s.toLowerCase() === sector.toLowerCase());
      if (index >= 0) values.splice(index, 1); else values.push(sector);
      $("#filter-sectors").value = values.join(", ");
      $("#preset-select").value = "";
      renderSectorSuggestions();
      return;
    }
    if (button.dataset.range) { state.detailRange = Number(button.dataset.range); renderDetailChart(); return; }
    if (button.dataset.page !== undefined) {
      if (button.dataset.pageContext === "history") { state.historyPage = Number(button.dataset.page); renderHistoryDetail(); }
      else { state.page = Number(button.dataset.page); renderResults(); }
      return;
    }
    const action = button.dataset.action;
    if (action === "filters") openFilters();
    if (action === "settings") openSettings();
    if (action === "retry-bootstrap") bootstrap();
  });
  window.addEventListener("hashchange", () => { if (state.settings) changeView(location.hash.slice(1), false); });
  document.addEventListener("visibilitychange", () => { if (!document.hidden && state.settings) schedulePoll(100); });
}

async function bootstrap() {
  showError("#global-error", "");
  $("#loading-state").classList.remove("hidden");
  try {
    const data = await api("/api/bootstrap");
    state.settings = data.settings;
    state.presets = data.presets || [];
    state.defaults = copy(state.presets.find((preset) => preset.id === "balanced")?.filters || state.settings.filters);
    state.watchlist = data.watchlist || [];
    state.latest = data.latest;
    state.history = data.history || [];
    state.historyTotal = data.history_total ?? state.history.length;
    state.provider = data.provider_status || {};
    $("#loading-state").classList.add("hidden");
    $("#workspace-content").classList.remove("hidden");
    applyJob(data.job, false);
    renderAll();
    changeView(location.hash.slice(1) || "live", false);
    schedulePoll(state.job.running ? 800 : 15000);
  } catch (error) {
    $("#loading-state").classList.add("hidden");
    $("#global-error").innerHTML = `${escapeHTML(error.message)} <button id="retry-bootstrap">Try again</button>`;
    $("#global-error").classList.remove("hidden");
    $("#retry-bootstrap").addEventListener("click", bootstrap);
  }
}

bindEvents();
bootstrap();
