/* Built-in research planner. Calculations and validation remain on the server. */
(() => {
  "use strict";
  const $ = (s, parent = document) => parent.querySelector(s);
  const money = n => numeric(n) ? new Intl.NumberFormat("en-US", {style:"currency",currency:"USD",maximumFractionDigits:n < 1 ? 4 : 2}).format(n) : "Unavailable";
  const price = n => numeric(n) ? (n>0 && n<1e-20 ? `$${n}` : new Intl.NumberFormat("en-US", {style:"currency",currency:"USD",minimumFractionDigits:2,maximumFractionDigits:20}).format(n)) : "Unavailable";
  const num = n => numeric(n) ? new Intl.NumberFormat("en-US", {maximumFractionDigits:4}).format(n) : "Unavailable";
  const time = value => value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString("en-US", {timeZone:"America/New_York",timeZoneName:"short"}) : "Unavailable";
  let selected = null, active = null, opening = 0, busy = false, settingsBusy = false, renderedExpired = false;
  const policies = [
    ["stop_atr_multiple","Stop distance × minute ATR",1], ["reward_multiple","Gross reward multiple",1],
    ["chase_atr_multiple","Entry allowance × minute ATR",1], ["min_net_rr","Minimum net reward / risk",1],
    ["tick_size","Research price increment ($)",1], ["entry_valid_seconds","Entry validity (seconds)",1],
    ["close_buffer_seconds","Buffer before session close (seconds)",1],
    ["participation_rate","Recent minute-volume cap (%)",100], ["quote_capacity_fraction","Displayed quote-size cap (%)",100]
  ];
  const accounts = [
    ["equity","Account equity ($)"], ["cash","Available cash ($)"], ["risk_budget","Risk budget for one plan ($)"],
    ["day_risk_remaining","Remaining daily risk budget ($)"], ["portfolio_risk_remaining","Remaining portfolio risk budget ($)"],
    ["max_position_notional","Maximum position value ($)"], ["gross_notional_remaining","Remaining gross exposure allowance ($)"]
  ];
  const costs = [
    ["entry_fixed","Total fixed entry fee ($)"], ["entry_per_share","Entry fee per share ($)"],
    ["exit_fixed","Total fixed exit fee ($)"], ["exit_per_share","Exit fee per share ($)"],
    ["entry_slippage","Entry slippage per share ($)"], ["stop_slippage","Adverse stop execution per share ($)"],
    ["target_slippage","Target-exit slippage per share ($)"]
  ];
  const fields = (items, prefix) => items.map(([key,label]) => `<label>${label}<input id="${prefix}-${key}" name="${key}" type="number" min="0" step="any" inputmode="decimal"></label>`).join("");
  document.body.insertAdjacentHTML("beforeend", `
    <dialog id="planner-dialog" class="modal planner-modal" aria-labelledby="planner-title">
      <div class="modal-header"><div><div class="eyebrow">BUILT-IN RESEARCH MODEL</div><h2 id="planner-title">Trade plan</h2><p>Conditional price levels, risk and holding rules.</p></div><button class="icon-button" type="button" data-planner-close aria-label="Close trade plan">✕</button></div>
      <div class="modal-body"><div id="planner-error" class="alert error hidden" role="alert"></div><div id="planner-result" aria-live="polite"></div></div>
      <div class="modal-footer"><button class="text-button" type="button" data-planner-settings>Model & sizing settings</button><div><button class="button subtle" type="button" id="planner-original">Original analysis</button><button class="button primary" type="button" id="planner-current">Analyze current data</button></div></div>
    </dialog>
    <dialog id="planner-settings-dialog" class="modal planner-modal" aria-labelledby="planner-settings-title"><form id="planner-settings-form">
      <div class="modal-header"><div><div class="eyebrow">RESEARCH ASSUMPTIONS</div><h2 id="planner-settings-title">Model & sizing settings</h2><p>Saved locally. Changes apply to future analyses.</p></div><button class="icon-button" type="button" data-planner-close aria-label="Close model settings">✕</button></div>
      <div class="modal-body"><div id="planner-settings-error" class="alert error hidden" role="alert"></div>
        <div class="planner-caution">This model has not been fitted or validated for profitability. Prices and quantities describe research scenarios. It does not place orders or track your broker account.</div>
        <section class="planner-section"><h3>Entry and exit policy</h3><p>Uses completed one-minute ATR(14) and the latest five-minute high. The price increment is a rounding assumption; check the instrument’s actual price rules.</p><div class="form-grid two">${fields(policies,"planner-policy")}<label>Maximum holding time<select id="planner-policy-hold_minutes"><option value="5">5 minutes</option><option value="15">15 minutes</option><option value="30">30 minutes</option></select></label></div></section>
        <section class="planner-section"><h3>Account and risk context</h3><p>Enter available budgets after accounting for existing positions and losses. Context is usable for five minutes after confirmation. Each plan is independent; multiple plans do not reserve cash against one another.</p><p id="planner-context-time" class="field-help"></p><div class="form-grid two">${fields(accounts,"planner-account")}</div><label>Complete current positions<textarea id="planner-positions" rows="2" placeholder="AAPL:25, MSFT:10 — leave empty if you hold no stocks"></textarea><span class="field-help">Use SYMBOL:SHARES separated by commas. The model will not add to an existing position.</span></label><label class="check-option"><input id="planner-confirm-context" type="checkbox"><span>I confirm these balances, remaining risk budgets and the complete positions list are current.</span></label><button id="planner-clear-context" type="button" class="text-button">Remove saved account context</button></section>
        <section class="planner-section"><h3>Cost and adverse-execution assumptions</h3><p>Supply every field to enable sizing, including an explicit zero where justified. Fixed and per-share fees must cover the entire entry and exit, including partial fills. These are scenario assumptions, not measured execution guarantees.</p><div class="form-grid two">${fields(costs,"planner-cost")}</div></section>
      </div><div class="modal-footer"><span class="field-help">No account credentials are needed.</span><button id="planner-save-settings" class="button primary" type="submit">Save assumptions</button></div>
    </form></dialog>`);

  function toggleBusy(value) {
    busy=value;
    for(const id of ["#planner-current","#planner-original"]) $(id).disabled=value || !selected;
  }
  function metric(label,value,note="") { return `<div><dt>${escapeHTML(label)}</dt><dd>${escapeHTML(value)}</dd>${note ? `<small>${escapeHTML(note)}</small>` : ""}</div>`; }
  function render(payload) {
    active=payload;
    $("#planner-title").textContent=`${payload.symbol || "Stock"} · Trade plan`;
    const plan=payload.plan;
    if(!plan) { $("#planner-result").innerHTML=`<p class="planner-caution">${escapeHTML(payload.message || "No original model analysis is available.")}</p><p>Use current analysis while the matching stock and source are actively monitored. This creates a separate assessment.</p>`; return; }
    const r=plan.result, l=r.levels || {}, s=r.sizing || {}, historical=plan.kind==="original_alert";
    const labels={unavailable:"Analysis unavailable",expired:"Entry window unavailable",levels_only:"Price levels only",no_trade:"No trade under these assumptions",wait:"Waiting for entry conditions",conditional:"Conditional research scenario"};
    const expired=payload.source!=="demo" && r.expires_at && Date.now()>=Date.parse(r.expires_at);
    renderedExpired=!!expired;
    $("#planner-result").innerHTML=`<div class="planner-labels"><span class="planner-badge">Research · unvalidated</span><span>${payload.source==="demo" ? "Synthetic demo" : `${escapeHTML(payload.source)} · ${escapeHTML(payload.feed)}`}</span></div>
      <p class="planner-history">${historical ? "Original analysis, frozen with the alert." : "Current reanalysis, separate from the original alert."} As of ${escapeHTML(time(r.as_of))}.</p>
      <h3 class="planner-status">${escapeHTML(labels[r.status] || r.status)}</h3>
      <p class="planner-caution">${expired ? "This entry window has expired. These saved values are historical. " : ""}A Buy alert and these model outputs are not a prediction of profit. No orders are placed.</p>
      <dl class="planner-metrics">${metric("Conditional entry",numeric(l.entry_trigger) ? `${price(l.entry_trigger)} – ${price(l.entry_max)}` : "Unavailable","Ask-based trigger; entry must remain within the band.")}${metric("Protective stop trigger",price(l.stop),"Gaps and halts can cause losses beyond this scenario.")}${metric("Target after entry",numeric(l.target_at_trigger) ? `${price(l.target_at_trigger)} – ${price(l.target_at_max)}` : "Unavailable","Depends on the actual entry price; fill and fees are not guaranteed.")}${metric("Planned holding limit",numeric(l.hold_minutes) ? `${l.hold_minutes} minutes` : "Unavailable","From first fill; earlier stop or target, with an exit before session close intended.")}${metric("Hypothetical position size",s.quantity===null || s.quantity===undefined ? "Unavailable" : `${num(s.quantity)} shares`,historical ? "At the original analysis time, using its saved account context." : "Uses your manually confirmed account context.")}${metric("Entry value at cap",money(s.notional_max))}${metric("Modeled stop-loss budget",money(s.risk_reserved),"A stressed loss scenario, not maximum possible loss.")}${metric("Conservative net reward / risk",numeric(s.robust_net_rr) ? `${num(s.robust_net_rr)} : 1` : "Unavailable","Includes the lower entry price and possible one-share partial fill.")}</dl>
      <p class="field-help">Entry window ends ${escapeHTML(time(r.expires_at))}. Stop and target use bid prices. A halt or incomplete exit leaves the remaining position exposed after the deadline.</p>
      ${(r.reasons || []).length ? `<section class="planner-section"><h4>Assessment</h4><ul>${r.reasons.map(x=>`<li>${escapeHTML(x)}</li>`).join("")}</ul></section>` : ""}
      ${(r.warnings || []).length ? `<details class="planner-details" open><summary>Assumptions and limitations</summary><ul>${r.warnings.map(x=>`<li>${escapeHTML(x)}</li>`).join("")}</ul></details>` : ""}
      <details class="planner-details"><summary>Calculation evidence and saved inputs</summary><p>Minute ATR ${escapeHTML(price(l.atr))}; cash required ${escapeHTML(money(s.cash_required))}. Version ${escapeHTML(r.model_id)}.</p><pre>${escapeHTML(JSON.stringify(plan,null,2))}</pre></details>
      ${payload.message ? `<p class="field-help">${escapeHTML(payload.message)}</p>` : ""}`;
  }
  async function showAlert(id) {
    const token=++opening; selected=id; active=null; showError("#planner-error",""); openDialog($("#planner-dialog"));
    $("#planner-result").innerHTML="<p>Loading saved analysis…</p>"; toggleBusy(true);
    try { const result=await api(`/api/planner/alerts/${encodeURIComponent(id)}`); if(token===opening)render(result); }
    catch(e) { if(token===opening) showError("#planner-error",e.message); }
    finally { if(token===opening) toggleBusy(false); }
  }
  async function showSettings() {
    if(settingsBusy)return;
    settingsBusy=true; showError("#planner-settings-error",""); openDialog($("#planner-settings-dialog")); $("#planner-save-settings").disabled=true;
    try {
      const {settings}=await api("/api/planner/settings");
      for(const [key,,scale] of policies) $(`#planner-policy-${key}`).value=settings.policy[key]*scale;
      $("#planner-policy-hold_minutes").value=settings.policy.hold_minutes;
      for(const [key] of accounts) $(`#planner-account-${key}`).value=settings.context?.[key] ?? "";
      $("#planner-positions").value=Object.entries(settings.context?.positions || {}).map(([symbol,shares])=>`${symbol}:${shares}`).join(", ");
      $("#planner-confirm-context").checked=false;
      $("#planner-context-time").textContent=settings.context?.as_of ? `Last confirmed ${time(settings.context.as_of)}. Confirmation expires after five minutes.` : "No account context saved. Price levels can still be analyzed.";
      for(const [key] of costs) $(`#planner-cost-${key}`).value=settings.costs?.[key] ?? "";
    } catch(e) { showError("#planner-settings-error",e.message); }
    finally { settingsBusy=false; $("#planner-save-settings").disabled=false; }
  }
  function readNumber(id) { const value=$(id).value; if(value.trim()==="" || !Number.isFinite(Number(value)))throw new Error("Complete each required numeric assumption with a numeric number."); return Number(value); }
  function readPositions() {
    const raw=$("#planner-positions").value.trim(), result={};
    if(!raw)return result;
    for(const item of raw.split(/[,\n]+/)) {
      const match=item.trim().match(/^([A-Za-z][A-Za-z0-9.\-]{0,9})\s*:\s*(\d+)$/);
      if(!match)throw new Error("Write positions as SYMBOL:SHARES, separated by commas.");
      const symbol=match[1].toUpperCase(); if(Object.hasOwnProperty.call(result,symbol))throw new Error("List each position only once.");
      result[symbol]=Number(match[2]);
    }
    return result;
  }
  $("#planner-settings-form").addEventListener("submit",async event=>{
    event.preventDefault(); if(settingsBusy)return; settingsBusy=true; $("#planner-save-settings").disabled=true; showError("#planner-settings-error","");
    try {
      const update={policy:{}};
      for(const [key,,scale] of policies)update.policy[key]=readNumber(`#planner-policy-${key}`)/scale;
      update.policy.hold_minutes=Number($("#planner-policy-hold_minutes").value);
      update.costs=costs.every(([key])=>$(`#planner-cost-${key}`).value.trim()==="") ? null : Object.fromEntries(costs.map(([key])=>[key,readNumber(`#planner-cost-${key}`)]));
      if($("#planner-confirm-context").checked) {
        update.context={...Object.fromEntries(accounts.map(([key])=>[key,readNumber(`#planner-account-${key}`)])),positions:readPositions()};
        update.confirm_context=true;
      }
      await api("/api/planner/settings",update); $("#planner-settings-dialog").close();
    }catch(e){showError("#planner-settings-error",e.message);}
    finally{settingsBusy=false;$("#planner-save-settings").disabled=false;}
  });
  $("#planner-clear-context").addEventListener("click",async()=>{
    if(settingsBusy)return; settingsBusy=true;
    try{await api("/api/planner/settings",{context:null});for(const [key] of accounts)$(`#planner-account-${key}`).value="";$("#planner-positions").value="";$("#planner-confirm-context").checked=false;$("#planner-context-time").textContent="Account context removed. Numeric sizing is unavailable until confirmed.";}
    catch(e){showError("#planner-settings-error",e.message);}finally{settingsBusy=false;}
  });
  $("#planner-current").addEventListener("click",async()=>{
    if(busy || !selected)return; const id=selected,token=++opening; toggleBusy(true);showError("#planner-error","");
    try{const result=await api("/api/planner/analyze",{alert_id:id});if(token===opening)render(result);}
    catch(e){if(token===opening)showError("#planner-error",e.message);}finally{if(token===opening)toggleBusy(false);}
  });
  $("#planner-original").addEventListener("click",()=>{if(!busy && selected)showAlert(selected);});
  document.addEventListener("click",event=>{
    const close=event.target.closest("[data-planner-close]");if(close)close.closest("dialog").close();
    const settings=event.target.closest("[data-planner-settings]");if(settings)showSettings();
    const alert=event.target.closest("[data-plan-alert]");if(alert)showAlert(alert.dataset.planAlert);
  });
  for(const id of ["#planner-dialog","#planner-settings-dialog"]){const dialog=$(id);dialog.addEventListener("close",()=>state.lastFocus.get(dialog)?.focus({preventScroll:true}));}
  function updateExpiry(){
    if(!active?.plan || !$("#planner-dialog").open)return;
    const nowExpired=active.source!=="demo" && active.plan.result.expires_at && Date.now()>=Date.parse(active.plan.result.expires_at);
    if(!!nowExpired!==renderedExpired)render(active);
  }
  setInterval(updateExpiry,1000);
  document.addEventListener("visibilitychange",()=>{if(!document.hidden)updateExpiry();});
})();
