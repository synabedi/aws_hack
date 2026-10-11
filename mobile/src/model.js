// Decision maths for the dashboard. Everything shown is derived from the API's
// Reading / Forecast / SiteState (contracts/schemas.py) or computed here from them.

export const CLASS_LABEL = {
  closure: 'Closure rule', pedestrian: 'Pedestrian', two_wheeler: 'Two-wheeler',
  small_car: 'Small car', large_car: 'Large car', bus_truck: 'Bus and truck',
}
export const RESPONSE_MIN = 8 // assumed time to set up barriers and a diversion
export const BUFFER_MIN = 3 // assumed safety buffer

// First time the curve reaches thr (linear interpolation). 0 if already above, null if never.
export function crossing(t, y, thr) {
  if (!t || !y || !y.length) return null
  if (y[0] >= thr) return 0
  for (let i = 1; i < y.length; i++) {
    if (y[i] >= thr) return t[i - 1] + ((thr - y[i - 1]) / (y[i] - y[i - 1] || 1)) * (t[i] - t[i - 1])
  }
  return null
}

// Intervention Clock: how long the officer can still wait before a closure can no longer be
// in place ahead of the 15 cm rule. Conservative basis = earliest plausible crossing
// (10th percentile of crossing time, i.e. the high edge of the depth band).
export function interventionClock(state) {
  const fc = state.latest_forecast
  const r = state.latest_reading
  if (!fc || !r) return { none: true }
  const thr = state.site.thresholds.closure
  const pick = (dict, curve) => (dict && dict.closure !== undefined ? dict.closure : crossing(fc.t, curve, thr))
  const median = pick(fc.t_impassable_min, fc.depth)
  const early = pick(fc.t_impassable_p10, fc.p90) ?? median
  const late = pick(fc.t_impassable_p90, fc.p10)
  const need = RESPONSE_MIN + BUFFER_MIN
  const crossed = r.max_depth_cm >= thr
  return { early, median, late, need, thr, crossed, basis: crossed ? 0 : early, margin: crossed ? -need : early == null ? null : early - need }
}

// ---- FloodLab: the same site equation as predict/site_model.py, run in the browser ----
// A(h) dh/dt = R i(t) / 3.6e6 - k head / sqrt(head + eps) - pumps * rate * ramp
const HEAD_EPS = 1e-4
const PUMP_RAMP = 0.01
const MIN_AREA = 0.05

function areaAt(basin, h) {
  const hs = basin.h_m, as = basin.area_m2
  if (h <= hs[0]) return Math.max(as[0], MIN_AREA)
  const n = hs.length - 1
  if (h >= hs[n]) return as[n]
  const i = Math.min(Math.floor((h - hs[0]) / (hs[1] - hs[0])), n - 1)
  return Math.max(as[i] + ((h - hs[i]) / (hs[i + 1] - hs[i])) * (as[i + 1] - as[i]), MIN_AREA)
}

export function runLab(lab, { rainX = 1, kX = 1, pumps = 0, pumpDelayMin = 0, minutes = 60 } = {}) {
  const { R, k, h0 = 0 } = lab.params
  const rain = (s) => lab.rain_mm_h[Math.min(Math.floor(s / 60), lab.rain_mm_h.length - 1)] * rainX
  const f = (h, s) => {
    const head = Math.max(h - h0, 0)
    const ramp = Math.min(Math.max((h - Math.max(h0, 0)) / PUMP_RAMP, 0), 1)
    const pump = s >= pumpDelayMin * 60 ? pumps * lab.pump_rate_m3_s * ramp : 0
    const net = (R * rain(s)) / 3.6e6 - (k * kX * head) / Math.sqrt(head + HEAD_EPS) - pump
    if (h <= 0 && net < 0) return 0
    return net / areaAt(lab.basin, Math.max(h, 0))
  }
  const dt = 1
  let h = lab.h_now_m
  const t = [0], depth = [h * 100]
  for (let s = 0; s < minutes * 60; s += dt) {
    const k1 = f(h, s), k2 = f(h + (dt / 2) * k1, s + dt / 2), k3 = f(h + (dt / 2) * k2, s + dt / 2), k4 = f(h + dt * k3, s + dt)
    h = Math.max(h + (dt / 6) * (k1 + 2 * k2 + 2 * k3 + k4), 0)
    if ((s + dt) % 60 === 0) { t.push((s + dt) / 60); depth.push(h * 100) }
  }
  return { t, depth }
}

export const peak = (y) => y.reduce((a, b) => Math.max(a, b), 0)
export const fmtMin = (m) => (m == null ? 'not within 60 min' : m < 1 ? 'under 1 min' : `${Math.round(m)} min`)
