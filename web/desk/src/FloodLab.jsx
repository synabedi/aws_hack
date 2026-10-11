import React, { useEffect, useMemo, useState } from 'react'
import { lab as loadLab, simulate, source } from './api.js'
import { crossing, runLab, peak, fmtMin, RESPONSE_MIN, BUFFER_MIN } from './model.js'

const START = { rainX: 1, kX: 1, pumps: 0, pumpDelayMin: 0 }
const left = (t) => (t == null ? 'Not needed' : t === 0 ? 'Already above' : t - RESPONSE_MIN - BUFFER_MIN < 0 ? `Too late by ${Math.round(RESPONSE_MIN + BUFFER_MIN - t)} min` : `${Math.round(t - RESPONSE_MIN - BUFFER_MIN)} min`)

export default function FloodLab({ state, onScenario }) {
  const id = state.site.site_id
  const fc = state.latest_forecast
  const thr = state.site.thresholds.closure
  const [inputs, setInputs] = useState(undefined) // undefined = loading, null = not available
  const [o, setO] = useState(START)
  const [remote, setRemote] = useState(null)
  const changed = JSON.stringify(o) !== JSON.stringify(START)

  useEffect(() => { let live = true; setInputs(undefined); setO(START); setRemote(null); loadLab(id).then((l) => live && setInputs(l)); return () => { live = false } }, [id])
  // With the lab inputs the site equation runs here; without them only the pump count can be asked of the API.
  const base = useMemo(() => (inputs ? runLab(inputs) : fc), [inputs, fc])
  const scn = useMemo(() => (inputs && changed ? runLab(inputs, o) : null), [inputs, o, changed])
  useEffect(() => {
    if (inputs || !o.pumps) { setRemote(null); return }
    let live = true
    simulate(id, o.pumps).then((r) => live && setRemote(r))
    return () => { live = false }
  }, [inputs, o.pumps, id])
  const shown = scn || remote
  useEffect(() => { onScenario(shown) }, [shown])

  if (!fc) return <p className="fine">FloodLab needs a forecast, and this site has no reading yet.</p>
  if (inputs === undefined) return <p className="fine">Loading the site model.</p>
  const slider = (key, label, min, max, step, fmt) => (
    <label className="sl" htmlFor={`sl-${key}`}>
      <span>{label}<b>{fmt(o[key])}</b></span>
      <input id={`sl-${key}`} type="range" min={min} max={max} step={step} value={o[key]} onChange={(e) => setO({ ...o, [key]: +e.target.value })} />
    </label>
  )
  const bT = crossing(base.t, base.depth, thr)
  const sT = shown ? crossing(shown.t, shown.depth, thr) : null
  const row = (label, a, b) => <tr><th scope="row">{label}</th><td>{a}</td><td className={shown ? '' : 'dim'}>{shown ? b : 'Move a control'}</td></tr>
  return (
    <div className="lab">
      <div className="lab-controls">
        {inputs && slider('rainX', `Rainfall, now ${inputs.rain_mm_h[0].toFixed(0)} mm/h`, 0, 2.5, 0.1, (v) => `${(inputs.rain_mm_h[0] * v).toFixed(0)} mm/h`)}
        {inputs && slider('kX', 'Drain performance', 0.1, 1.5, 0.05, (v) => `${Math.round(v * 100)}% of fitted`)}
        {slider('pumps', 'Pumps sent', 0, 3, 1, (v) => v)}
        {inputs && slider('pumpDelayMin', 'Pumps arrive after', 0, 30, 1, (v) => `${v} min`)}
        <button className="btn-quiet" onClick={() => setO(START)} disabled={!changed}>Reset to the fitted model</button>
      </div>
      <table className="lab-table">
        <thead><tr><th></th><th scope="col">Fitted model</th><th scope="col">This scenario</th></tr></thead>
        <tbody>
          {row(`Reaches ${thr} cm in`, bT === 0 ? 'Already there' : fmtMin(bT), sT === 0 ? 'Already there' : fmtMin(sT))}
          {row('Peak depth, next 60 min', `${peak(base.depth).toFixed(0)} cm`, shown && `${peak(shown.depth).toFixed(0)} cm`)}
          {row('Depth after 60 min', `${base.depth[base.depth.length - 1].toFixed(0)} cm`, shown && `${shown.depth[shown.depth.length - 1].toFixed(0)} cm`)}
          {row('Time left to decide', left(bT), left(sT))}
        </tbody>
      </table>
      <p className="fine">
        {inputs
          ? 'Both columns run the fitted site equation with single parameter values, so they can differ from the forecast median by a fraction of a centimetre. The dotted line on the chart is this scenario.'
          : 'This site only supports the pump count, answered by the API. Rain and drain controls appear when the API serves the site model inputs.'}
        {state.site.simulated && ' Simulated site.'}{source.mock && ' Demo snapshot.'}
      </p>
    </div>
  )
}
