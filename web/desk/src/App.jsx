import React, { useEffect, useMemo, useState } from 'react'
import * as api from './api.js'
import { interventionClock } from './model.js'
import { ForecastChart, ClockDetail, clockView, Verdicts, Evidence, FramePanel, Pumps, Drains, Tag, Icon, useNow } from './components.jsx'
import FloodLab from './FloodLab.jsx'
import Approvals from './Approvals.jsx'
import MapView from './MapView.jsx'

const VIEWS = [['desk', 'Site desk'], ['lab', 'FloodLab'], ['evidence', 'Evidence'], ['approvals', 'Approvals'], ['pumps', 'Pump plan'], ['drains', 'Drain health']]
const TITLE = { approvals: 'Closures waiting for you', pumps: 'Pump plan', drains: 'Drain health' }
const clockTime = (ts) => new Date(ts * 1000).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
const short = (n) => n.replace(' underpass', '').replace(' (real site)', '')

export default function App() {
  const [data, setData] = useState(null)
  const [hist, setHist] = useState({})
  const [sel, setSel] = useState(null)
  const [view, setView] = useState('desk')
  const [pick, setPick] = useState(null)
  const [scenario, setScenario] = useState(null)
  const [rain, setRain] = useState(null)
  const [officer, setOfficer] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  useNow()
  const now = api.dataNow()

  async function load() {
    try { setData(await api.loadAll()); setError(null) } catch (e) { setError(e.message) }
  }
  useEffect(() => { load(); const id = setInterval(() => { if (!api.source.mock) { load(); setHist({}) } }, 30000); return () => clearInterval(id) }, [])

  const ranked = useMemo(() => (data?.sites || []).map((s) => ({ ...s, clock: interventionClock(s) })).sort((a, b) => {
    const key = (x) => (x.clock.none ? 1e9 : x.latest_reading.status !== 'confident' ? -1e6 : x.clock.margin ?? 1e6) - (x.latest_reading?.max_depth_cm || 0) / 1000
    return key(a) - key(b)
  }), [data])

  useEffect(() => { if (!sel && ranked.length) setSel(ranked[0].site.site_id) }, [ranked, sel])
  useEffect(() => {
    setPick(null); setScenario(null); setRain(null)
    if (!sel) return
    if (!hist[sel]) api.history(sel).then((h) => setHist((x) => ({ ...x, [sel]: h })))
    api.lab(sel).then((l) => setRain(l ? l.rain_mm_h[0] : null))
  }, [sel])
  useEffect(() => { if (view !== 'lab') setScenario(null) }, [view])

  if (!data) return <div className="shell"><p className="loading">{error ? `Could not load data: ${error}` : 'Loading sites'}</p></div>

  const view1 = (s) => clockView(s.clock, s.latest_forecast?.ts, now)
  const tone = (s) => {
    if (!s.latest_reading) return 'none'
    if (s.latest_reading.status !== 'confident') return 'review'
    const st = view1(s).state
    return st === 'late' ? 'stop' : st === 'warn' ? 'warn' : s.clock.basis == null ? 'pass' : 'water'
  }
  const cur = ranked.find((s) => s.site.site_id === sel) || ranked[0]
  const r = cur.latest_reading
  const fc = cur.latest_forecast
  const readings = hist[cur.site.site_id] || []
  const reading = (pick && readings.find((h) => h.ts === pick.ts)) || r
  const cv = view1(cur)
  const pending = data.actions.filter((a) => a.status === 'proposed')
  const openSite = (id) => { setSel(id); setView('desk') }
  const siteName = (id) => short(ranked.find((s) => s.site.site_id === id)?.site.name || id)

  async function decide(action, verb) {
    setBusy(true)
    try { await api.decide(action, verb, officer.trim()); await load() } catch (e) { setError(e.message) }
    setBusy(false)
  }

  const chart = fc ? (
    <section className="card">
      <div className="card-head">
        <h2>Depth and forecast</h2>
        <p className="legend"><i className="k k-dot" />Measured, ±2 sigma<i className="k k-low" />Low confidence<i className="k k-med" />Forecast<i className="k k-band" />p10 to p90{view === 'lab' && <><i className="k k-scn" />Scenario</>}</p>
      </div>
      <ForecastChart history={readings.length ? readings : [r]} forecast={fc} thresholds={cur.site.thresholds} scenario={scenario}
        selected={view === 'evidence' ? reading : null} onSelect={(o) => { setPick(o); setView('evidence') }} />
      {fc.confidence !== 'confident' && <p className="fine">Low-confidence forecast{fc.note ? `: ${fc.note}` : ''}.</p>}
    </section>
  ) : (
    <section className="card"><h2>Depth and forecast</h2><p className="empty">No forecast yet. It needs at least three confident depth readings from this site.</p></section>
  )
  const perSite = !TITLE[view]

  return (
    <div className="shell">
      <nav className="rail" aria-label="Views">
        <div className="logo" aria-hidden="true"><svg viewBox="0 0 24 24" width="24" height="24"><path d="M12 3c3.500 4.500 6 7.500 6 11a6 6 0 0 1-12 0c0-3.500 2.500-6.500 6-11z" fill="currentColor" /></svg></div>
        {VIEWS.map(([id, label]) => (
          <button key={id} className={view === id ? 'rail-btn is-on' : 'rail-btn'} onClick={() => setView(id)} aria-label={label} title={label} aria-current={view === id}>
            <Icon name={id} />{id === 'approvals' && pending.length > 0 && <b>{pending.length}</b>}
          </button>
        ))}
      </nav>

      <div className="stage">
        <header className="bar">
          <div>
            <p className="brand">JalMaapi <span lang="hi">जलमापी</span></p>
            <h1>{TITLE[view] || cur.site.name}</h1>
            {perSite && (
              <p className="sub">
                {cur.site.simulated ? <Tag kind="sim">Simulated site</Tag> : <Tag kind="real">Real site</Tag>}
                {cur.site.name_hi && <span lang="hi">{cur.site.name_hi}</span>}
                <span>{r ? `Last reading ${clockTime(r.ts)}` : 'No reading yet'}</span>
                {fc && <span>Rain{rain != null ? ` ${rain.toFixed(0)} mm/h` : ''}, source {fc.rain_source.replace('scenario:', 'scenario ')}</span>}
              </p>
            )}
          </div>
          <div className="bar-right">
            {api.source.mock && <span className="demo">Demo snapshot, generated not measured</span>}
            {error && <span className="demo demo-err">{error}</span>}
            <label className="officer" htmlFor="officer"><span>Officer ID</span><input id="officer" value={officer} onChange={(e) => setOfficer(e.target.value)} placeholder="PWD-NO-014" /></label>
          </div>
        </header>

        <div className="cols">
          <main className="main">
            {view === 'desk' && <>
              <div className="tiles">
                <div className="tile tile-depth">
                  <p className="tile-label">Depth at the deepest point</p>
                  <p className="tile-num">{r ? r.max_depth_cm.toFixed(1) : 'None'}{r && <small>cm</small>}</p>
                  <p className="tile-sub">{r ? `± ${(2 * r.sigma_cm).toFixed(1)} cm${r.status !== 'confident' ? ', low confidence' : ''}` : 'Waiting for the first processed frame'}</p>
                </div>
                <div className={`tile tile-clock is-${cv.state}`}>
                  <p className="tile-label">Time left to decide</p>
                  <p className="tile-num">{cv.big}</p>
                  <p className="tile-sub">{cv.sub}</p>
                </div>
                <div className="tile tile-queue">
                  <p className="tile-label">Closures waiting for approval</p>
                  <p className="tile-num">{pending.length}</p>
                  <p className="tile-sub">{pending.length ? pending.map((a) => siteName(a.site_id)).join(', ') : 'Nothing needs a decision right now'}</p>
                  {pending.length > 0 && <button className="btn btn-go" onClick={() => setView('approvals')}>Review closures</button>}
                </div>
              </div>
              {chart}
              <div className="trio">
                <section className="card"><h2>Camera view</h2><FramePanel state={cur} /></section>
                <section className="card"><h2>How the clock is worked out</h2><ClockDetail clock={cur.clock} /></section>
                <section className="card"><h2>Who can still pass</h2><Verdicts verdicts={cur.verdicts} reading={r} /></section>
              </div>
            </>}

            {view === 'lab' && <>
              {chart}
              <section className="card">
                <div className="card-head"><h2>FloodLab</h2><p className="fine">Change the conditions and see what the site model says.</p></div>
                <FloodLab state={cur} onScenario={setScenario} />
              </section>
            </>}

            {view === 'evidence' && <>
              {chart}
              <section className="card">
                <div className="card-head"><h2>Evidence for {pick ? 'the selected reading' : 'the latest reading'}</h2><p className="fine">Select any point on the chart to inspect it.</p></div>
                {reading ? <Evidence reading={reading} /> : <p className="empty">This site has no reading yet.</p>}
              </section>
            </>}

            {view === 'approvals' && <Approvals actions={data.actions} sites={ranked} officer={officer.trim()} onDecide={decide} onOpen={openSite} busy={busy} />}
            {view === 'pumps' && <Pumps allocation={data.allocation} sites={ranked} onOpen={openSite} />}
            {view === 'drains' && <Drains sites={ranked} onOpen={openSite} />}
          </main>

          <aside className="side">
            <MapView sites={ranked.map((s) => ({ ...s.site, depth: s.latest_reading?.max_depth_cm }))} selected={cur.site.site_id} onSelect={setSel} tone={(x) => tone(ranked.find((s) => s.site.site_id === x.site_id))} />
            <section className="card">
              <h2>Sites, most urgent first</h2>
              <ol className="sites">
                {ranked.map((s) => {
                  const v = view1(s)
                  return (
                    <li key={s.site.site_id}>
                      <button className={s.site.site_id === cur.site.site_id ? 'site is-sel' : 'site'} onClick={() => setSel(s.site.site_id)}>
                        <span className={`dot dot-${tone(s)}`} />
                        <span className="site-name">{short(s.site.name)}<small>{s.site.simulated ? 'Simulated' : 'Real site'}</small></span>
                        <span className="site-depth">{s.latest_reading ? `${s.latest_reading.max_depth_cm.toFixed(0)} cm` : 'No reading'}
                          <small>{!s.latest_reading ? 'Awaiting data' : s.latest_reading.status !== 'confident' ? 'Review' : v.state === 'late' ? 'Close now' : v.state === 'ok' && s.clock.basis == null ? 'No rush' : `${v.big} left`}</small></span>
                      </button>
                    </li>
                  )
                })}
              </ol>
            </section>
            <p className="fine foot">
              <a href={api.source.feedUrl} target="_blank" rel="noreferrer">Open data feed</a>
              {api.source.meta?.aws?.services?.length ? <> Running on AWS {api.source.meta.aws.region}: {api.source.meta.aws.services.join(', ')}.</> : null}
            </p>
          </aside>
        </div>
      </div>
    </div>
  )
}
