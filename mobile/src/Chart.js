import React from 'react'
import Svg, { Path, Line, Circle, Rect, Text as T, Defs, LinearGradient, Stop, G } from 'react-native-svg'
import { C } from './theme'

// Measured depth (dots with ±2 sigma) and the 60 minute forecast with its p10 to p90 band.
export default function Chart({ width, history, forecast, thresholds, scenario }) {
  const W = width, H = 230, m = { l: 30, r: 12, t: 24, b: 26 }
  const t0 = forecast.ts
  const obs = history.map((r) => ({ ...r, tm: (r.ts - t0) / 60 })).filter((o) => o.tm >= -20)
  const xmin = -20, xmax = 60
  const top = Math.max(40, ...forecast.p90, ...obs.map((o) => o.max_depth_cm + 2 * o.sigma_cm), ...(scenario?.depth || [0]))
  const ymax = Math.ceil((top + 4) / 10) * 10
  const x = (v) => m.l + ((v - xmin) / (xmax - xmin)) * (W - m.l - m.r)
  const y = (v) => H - m.b - (Math.min(v, ymax) / ymax) * (H - m.t - m.b)
  const line = (ts, ys) => ts.map((t, i) => `${i ? 'L' : 'M'}${x(t).toFixed(1)},${y(ys[i]).toFixed(1)}`).join('')
  const back = (ts, ys) => ts.map((_, i) => { const k = ts.length - 1 - i; return `L${x(ts[k]).toFixed(1)},${y(ys[k]).toFixed(1)}` }).join('')
  const thr = [...new Set(Object.values(thresholds))].filter((c) => c <= ymax)
  const last = obs[obs.length - 1]
  const yt = []
  for (let v = 0; v <= ymax; v += ymax > 60 ? 20 : 10) yt.push(v)
  const tipX = last ? Math.min(Math.max(x(last.tm), m.l + 32), W - m.r - 32) : 0
  return (
    <Svg width={W} height={H} accessibilityLabel="Measured depth and 60 minute forecast">
      <Defs><LinearGradient id="a" x1="0" y1="0" x2="0" y2="1"><Stop offset="0" stopColor={C.blue} stopOpacity="0.2" /><Stop offset="1" stopColor={C.blue} stopOpacity="0" /></LinearGradient></Defs>
      {yt.map((v) => (
        <G key={v}><Line x1={m.l} x2={W - m.r} y1={y(v)} y2={y(v)} stroke={C.line} />
          <T x={m.l - 6} y={y(v) + 4} fontSize="10" fill={C.mute} textAnchor="end">{v}</T></G>
      ))}
      {[-20, 0, 20, 40, 60].map((v) => (
        <T key={v} x={x(v)} y={H - 8} fontSize="10" fill={v === 0 ? C.ink : C.mute} fontWeight={v === 0 ? '700' : '400'}
          textAnchor={v === 60 ? 'end' : v === -20 ? 'start' : 'middle'}>{v === 0 ? 'Now' : `${v > 0 ? '+' : ''}${v} min`}</T>
      ))}
      {thr.map((c) => (
        <G key={c}><Line x1={m.l} x2={W - m.r} y1={y(c)} y2={y(c)} stroke={C.red} strokeDasharray="2 5" opacity="0.7" />
          <T x={W - m.r} y={y(c) - 4} fontSize="10" fill={C.red} textAnchor="end">{c} cm</T></G>
      ))}
      <Path d={line(forecast.t, forecast.depth) + `L${x(60)},${y(0)}L${x(0)},${y(0)}Z`} fill="url(#a)" />
      <Path d={line(forecast.t, forecast.p90) + back(forecast.t, forecast.p10) + 'Z'} fill={C.blue} opacity="0.13" />
      <Path d={line(forecast.t, forecast.depth)} stroke={C.blue} strokeWidth="2.5" fill="none" />
      {scenario ? <Path d={line(scenario.t, scenario.depth)} stroke={C.ink} strokeWidth="2" strokeDasharray="2 6" strokeLinecap="round" fill="none" /> : null}
      <Line x1={x(0)} x2={x(0)} y1={m.t} y2={H - m.b} stroke={C.mute} strokeDasharray="3 4" />
      {obs.map((o) => {
        const ok = o.status === 'confident'
        return (
          <G key={o.ts}>
            <Line x1={x(o.tm)} x2={x(o.tm)} y1={y(o.max_depth_cm + 2 * o.sigma_cm)} y2={y(Math.max(o.max_depth_cm - 2 * o.sigma_cm, 0))} stroke={ok ? C.ink : C.violet} opacity={ok ? 0.2 : 0.5} />
            <Circle cx={x(o.tm)} cy={y(o.max_depth_cm)} r="2.4" fill={ok ? C.ink : '#fff'} stroke={ok ? 'none' : C.violet} strokeWidth="1.5" />
          </G>
        )
      })}
      {last ? (
        <G>
          <Circle cx={x(last.tm)} cy={y(last.max_depth_cm)} r="5.5" fill={C.ink} stroke="#fff" strokeWidth="2.5" />
          <Rect x={tipX - 32} y={Math.max(y(last.max_depth_cm) - 34, 0)} width="64" height="22" rx="11" fill={C.ink} />
          <T x={tipX} y={Math.max(y(last.max_depth_cm) - 34, 0) + 15} fontSize="11" fontWeight="600" fill="#fff" textAnchor="middle">{last.max_depth_cm.toFixed(1)} cm</T>
        </G>
      ) : null}
    </Svg>
  )
}
