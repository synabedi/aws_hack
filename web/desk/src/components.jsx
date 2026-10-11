import React, { useEffect, useState } from 'react'
import { CLASS_LABEL, RESPONSE_MIN, BUFFER_MIN, fmtMin } from './model.js'

export function useNow(ms = 1000) {
  const [n, setN] = useState(Date.now() / 1000)
  useEffect(() => {
    const id = setInterval(() => setN(Date.now() / 1000), ms)
    return () => clearInterval(id)
  }, [ms])
  return n
}

export const Tag = ({ kind, children }) => <span className={`tag tag-${kind}`}>{children}</span>

const P = {
  desk: 'M4 4h7v9H4zM13 4h7v5h-7zM13 11h7v9h-7zM4 15h7v5H4z',
  pumps: 'M4 18h16M7 18v-6h4v6M11 14h4a3 3 0 0 0 3-3V6M15 6h6M9 12V8M7 8h4',
  drains: 'M4 6h16M7 6v3a5 5 0 0 0 10 0V6M12 14v3M12 20v.5',
  lab: 'M4 7h10M18 7h2M4 17h2M10 17h10M14 4.5v5M6 14.5v5',
  evidence: 'M11 4a7 7 0 1 0 0 14a7 7 0 0 0 0-14zM20 20l-4-4M8.5 11l2 2l3.5-4',
  approvals: 'M12 3l7 3v5c0 4.5-3 8-7 10c-4-2-7-5.500-7-10V6zM9 12l2 2l4-4.500',
}
export const Icon = ({ name }) => (
  <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d={P[name]} />
  </svg>
)

export function ForecastChart({ history, forecast, thresholds, scenario, selected, onSelect }) {
  const W = 820, H = 300, m = { l: 34, r: 16, t: 26, b: 28 }
  const t0 = forecast.ts
  const obs = history.map((r) => ({ ...r, tm: (r.ts - t0) / 60 }))
  const xmin = -20, xmax = 60
  const top = Math.max(40, ...forecast.p90, ...obs.map((o) => o.max_depth_cm + 2 * o.sigma_cm), ...(scenario?.depth || [0]))
  const ymax = Math.ceil((top + 4) / 10) * 10
  const x = (v) => m.l + ((v - xmin) / (xmax - xmin)) * (W - m.l - m.r)
  const y = (v) => H - m.b - (Math.min(v, ymax) / ymax) * (H - m.t - m.b)
  const line = (ts, ys) => ts.map((t, i) => `${i ? 'L' : 'M'}${x(t).toFixed(1)},${y(ys[i]).toFixed(1)}`).join('')
  const back = (ts, ys) => ts.map((_, i) => { const k = ts.length - 1 - i; return `L${x(ts[k]).toFixed(1)},${y(ys[k]).toFixed(1)}` }).join('')
  const band = line(forecast.t, forecast.p90) + back(forecast.t, forecast.p10) + 'Z'
  const area = line(forecast.t, forecast.depth) + `L${x(60)},${y(0)}L${x(0)},${y(0)}Z`
  const thr = [...new Set(Object.values(thresholds))].filter((c) => c <= ymax)
  const last = obs[obs.length - 1]
  const focus = selected ? { ...selected, tm: (selected.ts - t0) / 60 } : last
  const fx = Math.min(Math.max(x(focus.tm), m.l + 34), W - m.r - 34)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Measured depth and 60 minute forecast">
      <defs>
        <linearGradient id="ca" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="var(--blue)" stopOpacity="0.2" /><stop offset="1" stopColor="var(--blue)" stopOpacity="0" /></linearGradient>
      </defs>
      {Array.from({ length: ymax / 10 + 1 }, (_, i) => i * 10).map((v) => (
        <g key={v}><line x1={m.l} x2={W - m.r} y1={y(v)} y2={y(v)} className="c-grid" />
          <text x={m.l - 8} y={y(v) + 4} textAnchor="end" className="c-tick">{v}</text></g>
      ))}
      {[-20, -10, 0, 10, 20, 30, 40, 50, 60].map((v) => (
        <text key={v} x={x(v)} y={H - 8} textAnchor={v === 60 ? 'end' : v === -20 ? 'start' : 'middle'} className={v === 0 ? 'c-tick c-tick-now' : 'c-tick'}>{v === 0 ? 'Now' : `${v > 0 ? '+' : ''}${v} min`}</text>
      ))}
      {thr.map((c) => (
        <g key={c}><line x1={m.l} x2={W - m.r} y1={y(c)} y2={y(c)} className="c-thr" />
          <text x={W - m.r} y={y(c) - 5} textAnchor="end" className="c-thr-t">{c} cm</text></g>
      ))}
      <path d={area} fill="url(#ca)" />
      <path d={band} className="c-band" />
      <path d={line(forecast.t, forecast.depth)} className="c-median" />
      {scenario && <path d={line(scenario.t, scenario.depth)} className="c-scn" />}
      <line x1={x(0)} x2={x(0)} y1={m.t} y2={H - m.b} className="c-now" />
      {obs.map((o) => {
        const ok = o.status === 'confident'
        return (
          <g key={o.ts} onClick={() => onSelect(o)} className="c-pt" tabIndex="0"
            onKeyDown={(e) => e.key === 'Enter' && onSelect(o)} aria-label={`Reading ${o.max_depth_cm} cm, ${o.status}`}>
            <line x1={x(o.tm)} x2={x(o.tm)} y1={y(o.max_depth_cm + 2 * o.sigma_cm)} y2={y(Math.max(o.max_depth_cm - 2 * o.sigma_cm, 0))} className={ok ? 'c-err' : 'c-err c-err-low'} />
            <circle cx={x(o.tm)} cy={y(o.max_depth_cm)} r="2.6" className={ok ? 'c-dot' : 'c-dot c-dot-low'} />
            <circle cx={x(o.tm)} cy={y(o.max_depth_cm)} r="9" fill="transparent" />
          </g>
        )
      })}
      <g pointerEvents="none">
        <circle cx={x(focus.tm)} cy={y(focus.max_depth_cm)} r="6" className="c-focus" />
        <rect x={fx - 34} y={Math.max(y(focus.max_depth_cm) - 36, 0)} width="68" height="24" rx="12" className="c-tip" />
        <text x={fx} y={Math.max(y(focus.max_depth_cm) - 36, 0) + 16} textAnchor="middle" className="c-tip-t">{focus.max_depth_cm.toFixed(1)} cm</text>
      </g>
    </svg>
  )
}

export const mmss = (min) => {
  const s = Math.max(Math.round(min * 60), 0)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

/* Intervention Clock in words: time left to decide, not time until the water arrives. */
export function clockView(clock, forecastTs, now) {
  if (clock.none) return { state: 'none', big: 'No reading', sub: 'The clock starts with the first confident depth reading.' }
  if (clock.crossed) return { state: 'late', big: 'Close now', sub: `Depth is at or above the ${clock.thr} cm closure rule.` }
  if (clock.basis == null) return { state: 'ok', big: 'No rush', sub: `The ${clock.thr} cm closure rule is not reached in the next 60 minutes, even on the high edge of the forecast.` }
  const left = clock.margin - Math.max((now - forecastTs) / 60, 0)
  if (left <= 0) return { state: 'late', big: 'Close now', sub: `A closure started now would be in place about ${Math.max(Math.round(-left), 1)} min after water may reach ${clock.thr} cm.` }
  return { state: left <= 5 ? 'warn' : 'ok', big: mmss(left), sub: `After this, a closure cannot be in place before water may reach ${clock.thr} cm.` }
}

export function ClockDetail({ clock }) {
  if (clock.none) return <p className="fine">Nothing to count down to yet.</p>
  const span = Math.max(clock.late ?? clock.median ?? clock.basis ?? 0, clock.basis ?? 0, clock.need) * 1.06
  const w = (v) => `${(Math.max(v, 0) / span) * 100}%`
  const show = clock.basis != null && !clock.crossed
  return (
    <>
      {show && <>
        <div className="tl" aria-hidden="true">
          <div className="tl-bar">
            {clock.margin > 0 && <span className="tl-wait" style={{ width: w(clock.margin) }} />}
            <span className="tl-resp" style={{ width: w(RESPONSE_MIN) }} />
            <span className="tl-buf" style={{ width: w(BUFFER_MIN) }} />
          </div>
          <div className="tl-mark" style={{ left: w(clock.basis) }} />
        </div>
        <p className="tl-key">{clock.margin > 0 && <span><i className="sw sw-wait" />Can still wait</span>}<span><i className="sw sw-resp" />Set up barriers</span><span><i className="sw sw-buf" />Buffer</span><span><i className="sw sw-mark" />Water may reach {clock.thr} cm</span></p>
      </>}
      <dl className="rows">
        <div><dt>Earliest crossing</dt><dd>{clock.crossed ? 'already above' : fmtMin(clock.early)}<small>10th percentile</small></dd></div>
        <div><dt>Most likely</dt><dd>{clock.crossed ? 'already above' : fmtMin(clock.median)}<small>median</small></dd></div>
        <div><dt>Latest crossing</dt><dd>{clock.crossed ? 'already above' : fmtMin(clock.late)}<small>90th percentile</small></dd></div>
        <div><dt>Barriers and diversion</dt><dd>{RESPONSE_MIN} min<small>assumed</small></dd></div>
        <div><dt>Safety buffer</dt><dd>{BUFFER_MIN} min<small>assumed</small></dd></div>
      </dl>
    </>
  )
}

export function Verdicts({ verdicts, reading }) {
  return (
    <ul className="verdicts">
      {verdicts.map((c) => {
        const t = c.t_impassable_min
        let kind = 'pass', text = 'Can pass'
        if (c.passable == null) { kind = 'review'; text = reading ? 'Manual review' : 'No reading' }
        else if (!c.passable) { kind = 'stop'; text = 'No entry' }
        else if (reading && reading.max_depth_cm + 2 * reading.sigma_cm >= c.threshold_cm) { kind = 'warn'; text = 'Borderline' }
        return (
          <li key={c.vehicle_class}>
            <span className="v-name">{CLASS_LABEL[c.vehicle_class] || c.vehicle_class}<small>{c.threshold_cm} cm limit{c.assumed ? ', assumed' : ''}</small></span>
            <span className="v-when">{c.passable == null ? 'No automatic verdict' : !c.passable ? 'Above limit' : t == null ? 'Not reached in 60 min' : `Blocked in ${fmtMin(t)}`}</span>
            <span className={`pill pill-${kind}`}>{text}</span>
          </li>
        )
      })}
    </ul>
  )
}

const real = (u) => u && !String(u).startsWith('synthetic://')

/* The camera view: the frame the number came from. */
export function FramePanel({ state }) {
  const r = state.latest_reading
  const img = r && (real(r.depthmap_uri) ? r.depthmap_uri : real(r.frame_uri) ? r.frame_uri : null)
  if (img) return <figure className="frame"><img src={img} alt="Latest camera frame with the depth map" /><figcaption>{r.max_depth_cm.toFixed(0)} ± {(2 * r.sigma_cm).toFixed(0)} cm</figcaption></figure>
  return (
    <div className="frame frame-empty">
      {state.site.simulated
        ? <p><b>No camera at a simulated site.</b> Depth is replayed from the site model, so there is no frame to show.</p>
        : <p><b>No frame yet.</b> The camera frame, water mask and depth map appear here once the staged flood footage is processed.</p>}
    </div>
  )
}

/* Evidence Passport: what a reading rests on. Missing fields are shown as missing. */
export function Evidence({ reading }) {
  const none = <em className="none">Not recorded</em>
  const t = new Date(reading.ts * 1000).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  const vr = reading.vlm_range_cm
  const inRange = vr && reading.max_depth_cm >= vr[0] - 15 && reading.max_depth_cm <= vr[1] + 15
  const ok = reading.status === 'confident'
  return (
    <div className="evidence">
      <div className="frames">
        {[['Camera frame', reading.frame_uri], ['Water mask and waterline', reading.mask_uri], ['Depth map', reading.depthmap_uri]].map(([l, u]) => (
          <figure key={l}>{real(u) ? <img src={u} alt={l} /> : <div className="noimg">{reading.simulated ? 'Simulated, no image' : 'No image yet'}</div>}<figcaption>{l}</figcaption></figure>
        ))}
      </div>
      <dl className="rows">
        <div><dt>Reading time</dt><dd>{t}<small>{reading.source}</small></dd></div>
        <div><dt>Depth</dt><dd>{reading.max_depth_cm.toFixed(1)} cm<small>sigma {reading.sigma_cm.toFixed(1)} cm</small></dd></div>
        <div><dt>Water level</dt><dd>{reading.level_m.toFixed(3)} m<small>above the basin floor</small></dd></div>
        <div><dt>Status</dt><dd><span className={`pill pill-${ok ? 'pass' : 'review'}`}>{ok ? 'Confident' : reading.status === 'failed' ? 'Failed' : 'Low confidence'}</span></dd></div>
        <div><dt>Valid waterline points</dt><dd>{reading.n_waterline_points ?? none}</dd></div>
        <div><dt>Vision cue range</dt><dd>{vr ? <>{vr[0]} to {vr[1]} cm<small>{inRange ? 'agrees' : 'disagrees by over 15 cm'}</small></> : none}</dd></div>
        <div><dt>Checks that fired</dt><dd className={reading.checks_failed?.length ? 'why' : ''}>{reading.checks_failed?.length ? reading.checks_failed.join(', ') : 'None'}</dd></div>
        <div><dt>Pumps running</dt><dd>{reading.pumps_on ?? 0}</dd></div>
      </dl>
    </div>
  )
}

/* Pump plan: forecast-based allocation next to the simple baseline. */
export function Pumps({ allocation, sites, onOpen }) {
  if (!allocation) return <p className="card empty">No pump allocation round has run yet.</p>
  const a = allocation
  const rows = [...sites].sort((x, y) => (a.awards[y.site.site_id] || 0) - (a.awards[x.site.site_id] || 0))
  const gain = a.benefit_minutes - a.baseline_benefit_minutes
  const dots = (n) => (n ? <span className="pumpdots" aria-label={`${n} pumps`}>{Array.from({ length: n }, (_, i) => <i key={i} />)}</span> : <span className="none">None</span>)
  return (
    <>
      <div className="tiles">
        <div className="tile tile-clock is-ok"><p className="tile-label">Planned on the forecast</p><p className="tile-num">{a.benefit_minutes.toFixed(0)}<small>site-min avoided</small></p><p className="tile-sub">Minutes above the closure rule avoided across all sites in the next hour.</p></div>
        <div className="tile"><p className="tile-label">Baseline: pumps to the deepest sites now</p><p className="tile-num">{a.baseline_benefit_minutes.toFixed(0)}<small>site-min avoided</small></p><p className="tile-sub">Same {a.inventory.pumps} pumps, sent by current depth only.</p></div>
        <div className="tile"><p className="tile-label">Difference</p><p className="tile-num">{gain >= 0 ? '+' : ''}{gain.toFixed(0)}<small>site-min</small></p><p className="tile-sub">{gain > 0 ? 'The forecast plan does better in this round.' : gain < 0 ? 'The baseline does better in this round.' : 'No difference in this round.'} A measured result of this simulation, not a general claim.</p></div>
      </div>
      <section className="card">
        <h2>Where each pump goes</h2>
        <div className="scroll">
          <table className="grid">
            <thead><tr><th>Site</th><th>Depth now</th><th>Traffic weight</th><th>Forecast plan</th><th>Baseline</th><th>Minutes avoided by pump 1, 2, 3</th></tr></thead>
            <tbody>
              {rows.map((s) => {
                const id = s.site.site_id
                const bids = a.bids.filter((b) => b.site_id === id).sort((x, y) => x.pumps - y.pumps)
                return (
                  <tr key={id}>
                    <td><button className="link sm" onClick={() => onOpen(id)}>{s.site.name}</button>{s.site.simulated && <Tag kind="sim">Simulated</Tag>}</td>
                    <td>{s.latest_reading ? `${s.latest_reading.max_depth_cm.toFixed(0)} cm` : 'No reading'}</td>
                    <td>{s.site.traffic_weight.toFixed(1)}</td>
                    <td>{dots(a.awards[id] || 0)}</td>
                    <td>{dots(a.baseline_awards[id] || 0)}</td>
                    <td>{bids.length ? bids.map((b) => b.minutes_avoided.toFixed(0)).join(', ') : 'No bids'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <p className="fine">{a.justification}</p>
        <p className="fine">The allocation is computed in code. The agent only explains it, and moving a pump still needs an officer's approval.</p>
      </section>
    </>
  )
}

/* Drain health: how fast each site drains compared with its own best. */
export function Drains({ sites, onOpen }) {
  return (
    <section className="card">
      <h2>How fast each site drains, against its own best</h2>
      <ul className="drains">
        {sites.map((s) => {
          const d = s.drain_health
          return (
            <li key={s.site.site_id}>
              <span className="v-name"><button className="link sm" onClick={() => onOpen(s.site.site_id)}>{s.site.name}</button>{s.site.simulated && <Tag kind="sim">Simulated</Tag>}</span>
              {d ? <>
                <span className={d.flagged ? 'meter meter-flag' : 'meter'} role="img" aria-label={`${d.score_pct.toFixed(0)} percent`}><i style={{ width: `${Math.min(d.score_pct, 100)}%` }} /></span>
                <span className="drain-num">{d.score_pct.toFixed(0)}%</span>
                <span className="fine">k {d.k.toFixed(4)}, interval {d.k_ci[0].toFixed(4)} to {d.k_ci[1].toFixed(4)}</span>
                <span className={`pill pill-${d.flagged ? 'stop' : 'pass'}`}>{d.flagged ? 'Flagged' : 'Normal'}</span>
              </> : <span className="fine wide">No recession fitted yet. Needs one drain-down after the water stops rising.</span>}
            </li>
          )
        })}
      </ul>
      <p className="fine">k is the drain coefficient fitted to the falling water curve. A low score says the site drains slowly. It does not say why: a silted inlet and a backed-up downstream drain look the same from one camera.</p>
    </section>
  )
}
