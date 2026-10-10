/* JalMaapi dashboard. Plain JS, no build. Talks to the API in web/API.md; falls back to web/mock/. */
(() => {
  "use strict";
  const qs = new URLSearchParams(location.search);
  const API = (qs.get("api") || window.JALMAAPI_API || "").replace(/\/$/, "");
  const FORCE_MOCK = qs.get("mock") === "1";
  const CLASS_LABEL = { closure: "Closure rule (any vehicle)", pedestrian: "Pedestrian", two_wheeler: "Two-wheeler", small_car: "Small car", large_car: "Large car", bus_truck: "Bus / truck" };
  const state = { mock: false, sites: [], actions: [], allocation: null, feed: [], meta: null, current: null, histories: {}, simCache: {}, map: null, markers: [], charts: {} };
  const $ = (s, el = document) => el.querySelector(s);
  const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html !== undefined) e.innerHTML = html; return e; };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (v, d = 1) => (v === null || v === undefined || Number.isNaN(v)) ? "–" : Number(v).toFixed(d);
  const timeAgo = (ts) => { if (!ts) return "no reading"; const s = Math.max(0, Date.now() / 1000 - ts); return s < 90 ? `${Math.round(s)} s ago` : `${Math.round(s / 60)} min ago`; };
  const toast = (msg) => { const t = $("#toast"); t.textContent = msg; t.classList.add("show"); clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("show"), 2800); };
  const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

  // ---------- data access ----------
  async function apiGet(path) {
    const r = await fetch(API + path, { headers: { Accept: "application/json" } });
    if (!r.ok) throw new Error(`${path}: ${r.status}`);
    return r.json();
  }
  async function mockGet(name) { const r = await fetch(`mock/${name}.json`); if (!r.ok) throw new Error(`mock ${name}`); return r.json(); }
  async function loadAll() {
    if (!FORCE_MOCK) {
      try {
        const [sites, actions, allocation, feed] = await Promise.all([apiGet("/sites"), apiGet("/actions"), apiGet("/allocations/latest").catch(() => null), apiGet("/feed").catch(() => [])]);
        state.meta = await apiGet("/meta").catch(() => null);
        Object.assign(state, { mock: false, sites, actions, allocation, feed });
        return;
      } catch (e) { console.warn("API unavailable, using mock data:", e.message); }
    }
    const [sites, actions, allocation, feed, meta] = await Promise.all([mockGet("sites"), mockGet("actions"), mockGet("allocation"), mockGet("feed"), mockGet("meta")]);
    Object.assign(state, { mock: true, sites, actions, allocation, feed, meta });
  }
  async function loadHistory(id) {
    if (state.histories[id]) return state.histories[id];
    const h = state.mock ? await mockGet(`history_${id}`).catch(() => ({ readings: [] })) : await apiGet(`/sites/${id}/history`).catch(() => ({ readings: [] }));
    state.histories[id] = h; return h;
  }
  async function simulate(id, pumps) {
    const key = `${id}:${pumps}`;
    if (state.simCache[key]) return state.simCache[key];
    let fc = null;
    if (state.mock) { const all = await mockGet(`simulate_${id}`).catch(() => null); fc = all ? all[String(pumps)] : null; }
    else { fc = await fetch(`${API}/sites/${id}/simulate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ pumps, minutes: 60 }) }).then((r) => r.ok ? r.json() : null).catch(() => null); }
    state.simCache[key] = fc; return fc;
  }
  async function decide(action, verb) {
    const officer = $("#officer-id").value.trim();
    if (!officer) { toast("Enter your officer id first; every decision is logged against it."); $("#officer-id").focus(); return; }
    let updated;
    if (state.mock) {
      updated = { ...action, status: verb === "approve" ? "published" : "rejected", approved_by: officer, decided_at: Date.now() / 1000, published_at: verb === "approve" ? Date.now() / 1000 : null };
    } else {
      const r = await fetch(`${API}/actions/${action.action_id}/${verb}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ officer_id: officer }) });
      if (!r.ok) { toast(`Decision failed: ${r.status}`); return; }
      updated = await r.json();
    }
    state.actions = state.actions.map((a) => a.action_id === action.action_id ? updated : a);
    state.sites.forEach((s) => { s.pending_actions = (s.pending_actions || []).filter((a) => a.action_id !== action.action_id); });
    toast(verb === "approve" ? `Approved and published by ${officer}${state.mock ? " (mock: not sent)" : ""}` : `Rejected by ${officer}`);
    renderAll();
  }

  // ---------- helpers ----------
  const depthClass = (s) => { const r = s.latest_reading; if (!r) return "none"; if (r.status !== "confident") return "warn"; const d = r.max_depth_cm; return d >= s.site.thresholds.closure ? "bad" : d >= 5 ? "warn" : "ok"; };
  const tClose = (s) => s.latest_forecast ? s.latest_forecast.t_impassable_min.closure : null;
  function urgency(s) { const r = s.latest_reading; if (!r) return 1e9; if (r.status !== "confident") return 5e8 - r.max_depth_cm; const t = tClose(s); return (t === null || t === undefined ? 1e6 : t) * 1000 - r.max_depth_cm; }
  function countdownChip(s) {
    const r = s.latest_reading; if (!r) return `<span class="chip chip-none">no reading</span>`;
    if (r.status !== "confident") return `<span class="chip chip-warn">low confidence: manual review</span>`;
    const t = tClose(s);
    if (r.max_depth_cm >= s.site.thresholds.closure) return `<span class="chip chip-bad">above 15 cm now</span>`;
    if (t === null || t === undefined) return `<span class="chip chip-ok">not within 60 min</span>`;
    return `<span class="chip ${t < 20 ? "chip-bad" : "chip-warn"}">15 cm in ${Math.round(t)} min</span>`;
  }
  const simTag = (site) => site.simulated ? `<span class="tag tag-sim" title="Synthetic depth curve from the same site model">SIM</span>` : `<span class="tag tag-real">REAL</span>`;
  function siteById(id) { return state.sites.find((s) => s.site.site_id === id); }

  // ---------- views ----------
  function renderTop() {
    $("#source-badge").hidden = !state.mock;
    $("#source-badge").title = state.mock ? (state.meta?.note || "mock") : "";
    const latest = Math.max(0, ...state.sites.map((s) => s.latest_reading?.ts || 0));
    $("#updated").textContent = latest ? `latest reading ${timeAgo(latest)}` : "";
    const n = state.actions.filter((a) => a.status === "proposed").length;
    $("#approval-count").hidden = n === 0; $("#approval-count").textContent = n;
  }
  function renderCity() {
    const list = $("#site-list"); list.innerHTML = "";
    const sorted = [...state.sites].sort((a, b) => urgency(a) - urgency(b));
    for (const s of sorted) {
      const r = s.latest_reading;
      const li = el("li", "site-row");
      li.setAttribute("role", "button"); li.tabIndex = 0;
      li.innerHTML = `<div><div class="name">${esc(s.site.name)} ${simTag(s.site)}</div><div class="small muted">${esc(s.site.name_hi || "")} · ${r ? timeAgo(r.ts) : "awaiting staged-flood data"}</div><div style="margin-top:4px">${countdownChip(s)}</div></div>
        <div class="depth">${r ? `${fmt(r.max_depth_cm, 0)}<span class="small muted"> ±${fmt(r.sigma_cm, 0)} cm</span>` : "<span class='small muted'>–</span>"}</div>`;
      const open = () => showSite(s.site.site_id);
      li.addEventListener("click", open); li.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } });
      list.appendChild(li);
    }
    renderMap();
  }
  function renderMap() {
    if (!window.L) return;
    if (!state.map) {
      state.map = L.map("map", { zoomControl: true, scrollWheelZoom: false }).setView([28.62, 77.18], 11);
      state.tiles = L.tileLayer(tileUrl(), { attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>', maxZoom: 18 }).addTo(state.map);
    }
    state.markers.forEach((m) => m.remove()); state.markers = [];
    for (const s of state.sites) {
      const c = depthClass(s); const r = s.latest_reading;
      const m = L.circleMarker([s.site.lat, s.site.lon], { radius: r ? Math.max(8, Math.min(22, 6 + r.max_depth_cm / 3)) : 8, color: cssVar(`--${c}`), fillColor: cssVar(`--${c}`), fillOpacity: .75, weight: 2 }).addTo(state.map);
      m.bindTooltip(`<strong>${esc(s.site.name)}</strong>${s.site.simulated ? " (simulated)" : ""}<br>${r ? `${fmt(r.max_depth_cm, 0)} ± ${fmt(r.sigma_cm, 0)} cm · ${esc(r.status)}` : "no reading yet"}`, { direction: "top" });
      m.on("click", () => showSite(s.site.site_id));
      state.markers.push(m);
    }
  }
  const tileUrl = () => document.documentElement.dataset.theme === "light" ? "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png" : "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";

  async function showSite(id) { state.current = id; switchView("site"); await renderSite(); }
  async function renderSite() {
    const sel = $("#site-select");
    if (sel.options.length !== state.sites.length) { sel.innerHTML = state.sites.map((s) => `<option value="${esc(s.site.site_id)}">${esc(s.site.name)}${s.site.simulated ? " (sim)" : ""}</option>`).join(""); }
    if (!state.current) state.current = [...state.sites].sort((a, b) => urgency(a) - urgency(b))[0]?.site.site_id;
    sel.value = state.current;
    const s = siteById(state.current); if (!s) return;
    const r = s.latest_reading, fc = s.latest_forecast;
    $("#site-title").innerHTML = `<h1>${esc(s.site.name)} ${simTag(s.site)} ${r && r.status !== "confident" ? '<span class="tag tag-low">LOW CONFIDENCE</span>' : ""}</h1><span class="muted small">${esc(s.site.name_hi || "")} · ${s.site.lat.toFixed(4)}, ${s.site.lon.toFixed(4)} · rain: ${esc(s.site.rain_source)}${s.site.params ? ` · fitted R ${fmt(s.site.params.R, 0)} m², k ${fmt(s.site.params.k, 3)}` : ""}</span>`;
    const fb = $("#frame-box"); fb.innerHTML = "";
    if (r && (r.depthmap_uri || r.frame_uri) && !String(r.frame_uri).startsWith("synthetic://")) {
      const img = el("img"); img.alt = "Latest frame with depth heat map"; img.src = r.depthmap_uri || r.frame_uri; fb.appendChild(img);
      fb.appendChild(el("div", "overlay", `${fmt(r.max_depth_cm, 0)} ± ${fmt(r.sigma_cm, 0)} cm`));
    } else if (r) {
      fb.innerHTML = `<div><strong>Simulated site</strong><br><span class="small">No camera. Depth curve replayed from the site model.</span></div>`;
    } else {
      fb.innerHTML = `<div><strong>No reading yet</strong><br><span class="small">Reference still, water mask and depth heat map appear here once the staged flood is processed (validation/protocol.md).</span></div>`;
    }
    $("#reading-line").innerHTML = r ? `Max depth <strong>${fmt(r.max_depth_cm, 1)} cm</strong> <span class="sigma">σ ${fmt(r.sigma_cm, 1)} cm · level ${fmt(r.level_m, 3)} m · ${esc(r.status)}${r.checks_failed?.length ? ` · checks: ${esc(r.checks_failed.join(", "))}` : ""}${r.n_waterline_points ? ` · ${r.n_waterline_points} waterline px` : ""}</span>` : `<span class="muted">—</span>`;
    // verdicts
    const v = $("#verdicts"); v.innerHTML = "";
    for (const c of s.verdicts) {
      const stateCls = c.passable === null ? "unknown" : c.passable ? "pass" : "nopass";
      const txt = c.passable === null ? "unknown" : c.passable ? "can pass" : "NO ENTRY";
      const t = c.t_impassable_min;
      v.appendChild(el("div", `verdict ${stateCls}`, `<div class="cls">${esc(CLASS_LABEL[c.vehicle_class] || c.vehicle_class)} ${c.assumed ? '<span class="tag tag-assumed">assumed</span>' : ""}</div><div class="state">${txt}</div><div class="meta">threshold ${fmt(c.threshold_cm, 0)} cm${c.passable === false ? "" : t === null || t === undefined ? " · not within 60 min" : t <= 0 ? " · now" : ` · in ${Math.round(t)} min`}</div>`));
    }
    // charts
    const pumps = Number($("#pumps-select").value || 0);
    const fcShow = pumps > 0 ? (await simulate(s.site.site_id, pumps)) || fc : fc;
    drawForecast(s, fcShow, pumps);
    const h = await loadHistory(s.site.site_id); drawHistory(s, h.readings || []);
    // drain
    const d = s.drain_health; const dc = $("#drain-card");
    dc.innerHTML = d ? `<div class="health-bar ${d.flagged ? "flag" : ""}"><i style="width:${Math.min(100, d.score_pct)}%"></i></div><dl class="kv"><dt>Health</dt><dd>${fmt(d.score_pct, 0)}% ${d.flagged ? '<span class="chip chip-bad">flagged</span>' : ""}</dd><dt>k</dt><dd>${fmt(d.k, 4)} [${fmt(d.k_ci[0], 4)}, ${fmt(d.k_ci[1], 4)}]</dd><dt>Note</dt><dd style="font-family:var(--font)">${esc(d.note || "")}</dd></dl>${d.simulated ? '<span class="tag tag-sim">SIM</span>' : ""}` : `<div class="empty">No recession fitted yet. Needs passes B and C of the staged flood.</div>`;
    // actions
    const sa = $("#site-actions"); sa.innerHTML = "";
    const pend = state.actions.filter((a) => a.site_id === s.site.site_id && a.status === "proposed");
    if (!pend.length) sa.innerHTML = `<div class="empty">Nothing proposed. ${r && r.status !== "confident" ? "Low-confidence reading: the officer reviews manually; no automatic verdict." : ""}</div>`;
    pend.forEach((a) => sa.appendChild(actionCard(a)));
  }
  function thresholdLines(s, n) {
    const th = s.site.thresholds; const mk = (v, label) => ({ label, data: Array(n).fill(v), borderColor: cssVar("--muted"), borderDash: [4, 4], borderWidth: 1, pointRadius: 0, fill: false });
    return [mk(th.closure, "closure 15 cm"), mk(th.small_car, "small car 30"), mk(th.bus_truck, "bus/truck 50 (assumed)")];
  }
  function drawForecast(s, fc, pumps) {
    const ctx = $("#forecast-chart"); state.charts.f?.destroy();
    if (!fc) { $("#forecast-line").textContent = "No forecast: needs at least 3 confident readings."; state.charts.f = null; ctx.getContext("2d").clearRect(0, 0, ctx.width, ctx.height); return; }
    const labels = fc.t.map((m) => `${Math.round(m)} min`);
    state.charts.f = new Chart(ctx, { type: "line", data: { labels, datasets: [
      { label: "p90", data: fc.p90, borderColor: "transparent", backgroundColor: "rgba(56,189,248,.18)", pointRadius: 0, fill: "+1" },
      { label: "p10", data: fc.p10, borderColor: "transparent", pointRadius: 0, fill: false },
      { label: `median max depth${pumps ? ` with ${pumps} pump${pumps > 1 ? "s" : ""}` : ""}`, data: fc.depth, borderColor: cssVar("--accent"), borderWidth: 2.5, pointRadius: 0, tension: .2 },
      ...thresholdLines(s, fc.t.length) ] },
      options: { responsive: true, maintainAspectRatio: false, animation: false, interaction: { mode: "index", intersect: false },
        plugins: { legend: { labels: { color: cssVar("--muted"), filter: (i) => !["p10", "p90"].includes(i.text) } }, tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${fmt(c.parsed.y, 1)} cm` } } },
        scales: { x: { ticks: { color: cssVar("--muted"), maxTicksLimit: 7 }, grid: { color: cssVar("--border") } }, y: { title: { display: true, text: "max depth, cm", color: cssVar("--muted") }, ticks: { color: cssVar("--muted") }, grid: { color: cssVar("--border") }, beginAtZero: true } } } });
    const t = fc.t_impassable_min; const p10 = fc.t_impassable_p10 || {}, p90 = fc.t_impassable_p90 || {};
    const part = (c) => t[c] === null || t[c] === undefined ? `${CLASS_LABEL[c]}: not within 60 min` : `${CLASS_LABEL[c]}: ${t[c] <= 0 ? "now" : `${Math.round(t[c])} min`}${p10[c] !== undefined && p10[c] !== null && p90[c] !== null && p90[c] !== undefined ? ` (${Math.round(p10[c])}–${Math.round(p90[c])})` : ""}`;
    $("#forecast-line").textContent = `${fc.confidence === "low_confidence" ? "LOW CONFIDENCE forecast" + (fc.note ? ` (${fc.note})` : "") + ". " : ""}${["closure", "small_car", "bus_truck"].map(part).join(" · ")}. Params R ${fmt(fc.params.R, 0)}, k ${fmt(fc.params.k, 3)}. Rain: ${fc.rain_source}.${fc.simulated ? " Simulated." : ""}`;
  }
  function drawHistory(s, readings) {
    const ctx = $("#history-chart"); state.charts.h?.destroy();
    if (!readings.length) { state.charts.h = null; ctx.getContext("2d").clearRect(0, 0, ctx.width, ctx.height); return; }
    const t0 = readings[0].ts;
    state.charts.h = new Chart(ctx, { type: "line", data: { labels: readings.map((r) => `${Math.round((r.ts - t0) / 60)} min`), datasets: [
      { label: "measured max depth", data: readings.map((r) => r.max_depth_cm), borderColor: cssVar("--accent"), pointRadius: readings.map((r) => r.status === "confident" ? 2 : 5), pointBackgroundColor: readings.map((r) => r.status === "confident" ? cssVar("--accent") : cssVar("--warn")), borderWidth: 2, tension: .15 },
      ...thresholdLines(s, readings.length).slice(0, 1) ] },
      options: { responsive: true, maintainAspectRatio: false, animation: false, plugins: { legend: { labels: { color: cssVar("--muted") } }, tooltip: { callbacks: { label: (c) => `${fmt(c.parsed.y, 1)} ± ${fmt(readings[c.dataIndex].sigma_cm, 1)} cm (${readings[c.dataIndex].status})` } } },
        scales: { x: { ticks: { color: cssVar("--muted"), maxTicksLimit: 8 }, grid: { color: cssVar("--border") } }, y: { ticks: { color: cssVar("--muted") }, grid: { color: cssVar("--border") }, beginAtZero: true, title: { display: true, text: "cm", color: cssVar("--muted") } } } } });
  }
  function actionCard(a, decided = false) {
    const s = siteById(a.site_id); const site = s?.site;
    const card = el("div", "action");
    card.innerHTML = `<div class="head"><div><span class="type">${esc(a.type)}</span> · ${esc(site?.name || a.site_id)} ${site ? simTag(site) : ""} ${a.reading_status !== "confident" ? '<span class="tag tag-low">LOW CONFIDENCE</span>' : ""}</div><span class="small muted">proposed by ${esc(a.proposed_by)} · ${timeAgo(a.created_ts)}${decided ? ` · ${esc(a.status)} by ${esc(a.approved_by || "")}` : ""}</span></div>
      <div class="small">${esc(a.justification)}</div>
      ${a.payload?.advisory_en ? `<div class="advisory"><div class="hi">${esc(a.payload.advisory_hi || "")}</div><div class="small">${esc(a.payload.advisory_en)}</div></div>` : ""}`;
    if (!decided) {
      const row = el("div", "actions-row");
      const ok = el("button", "btn btn-approve", "Approve and publish"); const no = el("button", "btn btn-reject", "Reject");
      if (a.reading_status !== "confident") { ok.disabled = true; ok.title = "Policy: no action on a low-confidence reading. Review the frame manually."; }
      ok.addEventListener("click", () => decide(a, "approve")); no.addEventListener("click", () => decide(a, "reject"));
      row.append(ok, no); card.appendChild(row);
    }
    return card;
  }
  function renderApprovals() {
    const q = $("#approval-list"), d = $("#decided-list"); q.innerHTML = ""; d.innerHTML = "";
    const pend = state.actions.filter((a) => a.status === "proposed").sort((a, b) => urgency(siteById(a.site_id) || {}) - urgency(siteById(b.site_id) || {}));
    if (!pend.length) q.innerHTML = `<div class="empty">Queue empty.</div>`;
    pend.forEach((a) => q.appendChild(actionCard(a)));
    const done = state.actions.filter((a) => a.status !== "proposed");
    if (!done.length) d.innerHTML = `<div class="empty">No decisions yet.</div>`;
    done.forEach((a) => d.appendChild(actionCard(a, true)));
  }
  function renderPumps() {
    const al = state.allocation; const tb = $("#alloc-table tbody"); tb.innerHTML = "";
    if (!al) { $("#alloc-just").textContent = "No allocation round yet."; return; }
    $("#alloc-just").textContent = al.justification; $("#kpi-plan").textContent = fmt(al.benefit_minutes, 0); $("#kpi-base").textContent = fmt(al.baseline_benefit_minutes, 0);
    for (const s of [...state.sites].sort((a, b) => (al.awards[b.site.site_id] || 0) - (al.awards[a.site.site_id] || 0))) {
      const id = s.site.site_id; const bids = al.bids.filter((b) => b.site_id === id).sort((a, b) => a.pumps - b.pumps);
      const tr = el("tr"); tr.innerHTML = `<td>${esc(s.site.name)} ${simTag(s.site)}</td><td class="num">${s.latest_reading ? fmt(s.latest_reading.max_depth_cm, 0) + " cm" : "–"}</td><td class="num">${fmt(s.site.traffic_weight, 1)}</td><td class="num"><strong>${al.awards[id] ?? 0}</strong></td><td class="num">${al.baseline_awards[id] ?? 0}</td><td class="num small">${bids.length ? bids.map((b) => `+${b.pumps}: ${fmt(b.minutes_avoided, 0)} min`).join(" · ") : "–"}</td>`;
      tb.appendChild(tr);
    }
  }
  function renderDrains() {
    const tb = $("#drain-table tbody"); tb.innerHTML = "";
    for (const s of state.sites) {
      const d = s.drain_health; const tr = el("tr");
      tr.innerHTML = d ? `<td>${esc(s.site.name)} ${simTag(s.site)}</td><td class="num">${fmt(d.k, 4)}</td><td class="num">[${fmt(d.k_ci[0], 4)}, ${fmt(d.k_ci[1], 4)}]</td><td class="num">${fmt(d.score_pct, 0)}%</td><td>${d.flagged ? '<span class="chip chip-bad">flagged</span>' : '<span class="chip chip-ok">ok</span>'}</td><td class="small">${esc(d.note || "")}</td>`
        : `<td>${esc(s.site.name)} ${simTag(s.site)}</td><td colspan="5" class="muted small">no recession fitted yet</td>`;
      tb.appendChild(tr);
    }
  }
  function renderFeed() { $("#feed-url").textContent = `${API || location.origin}/feed`; $("#feed-json").textContent = JSON.stringify(state.feed, null, 1); }
  function renderAll() { renderTop(); renderCity(); renderApprovals(); renderPumps(); renderDrains(); renderFeed(); if ($("#view-site").classList.contains("active")) renderSite(); }

  // ---------- navigation and theme ----------
  function switchView(name) {
    document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${name}`));
    document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
    if (name === "city" && state.map) setTimeout(() => state.map.invalidateSize(), 50);
    if (name === "site") renderSite();
    history.replaceState(null, "", `#${name}`);
  }
  document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => switchView(b.dataset.view)));
  $("#site-select").addEventListener("change", (e) => { state.current = e.target.value; renderSite(); });
  $("#pumps-select").addEventListener("change", () => renderSite());
  $("#theme-toggle").addEventListener("click", () => {
    const root = document.documentElement; root.dataset.theme = root.dataset.theme === "light" ? "dark" : "light";
    try { localStorage.setItem("jalmaapi-theme", root.dataset.theme); } catch (_) { /* private mode */ }
    if (state.tiles) state.tiles.setUrl(tileUrl());
    renderAll();
  });
  try { const t = localStorage.getItem("jalmaapi-theme"); if (t) document.documentElement.dataset.theme = t; const o = localStorage.getItem("jalmaapi-officer"); if (o) $("#officer-id").value = o; } catch (_) { /* ignore */ }
  $("#officer-id").addEventListener("change", (e) => { try { localStorage.setItem("jalmaapi-officer", e.target.value.trim()); } catch (_) { /* ignore */ } });

  // ---------- boot ----------
  (async () => {
    try { await loadAll(); } catch (e) { $("#app").innerHTML = `<div class="card"><h2>Could not load data</h2><p class="muted">${esc(e.message)}. Serve this folder over HTTP (python3 -m http.server) or pass ?api=.</p></div>`; return; }
    renderAll();
    const v = location.hash.replace("#", ""); if (["city", "site", "approvals", "pumps", "drains", "feed"].includes(v)) switchView(v);
    if (!state.mock) setInterval(async () => { try { await loadAll(); state.histories = {}; state.simCache = {}; renderAll(); } catch (_) { /* keep last good state */ } }, 30000);
  })();
})();
