import React, { useEffect, useState } from 'react'
import { View, Text, Pressable, StyleSheet } from 'react-native'
import { C, PILL } from './theme'
import { fmtMin, RESPONSE_MIN, BUFFER_MIN } from './model'

export function useNow(ms = 1000) {
  const [n, setN] = useState(0)
  useEffect(() => { const id = setInterval(() => setN((x) => x + 1), ms); return () => clearInterval(id) }, [ms])
  return n
}

export const mmss = (min) => { const s = Math.max(Math.round(min * 60), 0); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}` }
export const clockTime = (ts) => { const d = new Date(ts * 1000); return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}` }
export const short = (n) => n.replace(' underpass', '').replace(' (real site)', '')

// Intervention Clock in words: time left to decide, not time until the water arrives.
export function clockView(clock, forecastTs, now) {
  if (clock.none) return { state: 'none', big: 'No reading', sub: 'The clock starts with the first confident depth reading.' }
  if (clock.crossed) return { state: 'late', big: 'Close now', sub: `Depth is at or above the ${clock.thr} cm closure rule.` }
  if (clock.basis == null) return { state: 'ok', big: 'No rush', sub: `The ${clock.thr} cm closure rule is not reached in the next 60 minutes, even on the high edge of the forecast.` }
  const left = clock.margin - Math.max((now - forecastTs) / 60, 0)
  if (left <= 0) return { state: 'late', big: 'Close now', sub: `A closure started now would be in place about ${Math.max(Math.round(-left), 1)} min after water may reach ${clock.thr} cm.` }
  return { state: left <= 5 ? 'warn' : 'ok', big: mmss(left), sub: `After this, a closure cannot be in place before water may reach ${clock.thr} cm.` }
}
export function toneOf(s, now) {
  if (!s.latest_reading) return 'none'
  if (s.latest_reading.status !== 'confident') return 'review'
  const st = clockView(s.clock, s.latest_forecast?.ts, now).state
  return st === 'late' ? 'stop' : st === 'warn' ? 'warn' : s.clock.basis == null ? 'pass' : 'water'
}

export const Card = ({ title, children, style }) => (
  <View style={[st.card, style]}>{title ? <Text style={st.h2}>{title}</Text> : null}{children}</View>
)
export const Pill = ({ kind, children }) => (
  <View style={[st.pill, { backgroundColor: PILL[kind][0] }]}><Text style={[st.pillT, { color: PILL[kind][1] }]}>{children}</Text></View>
)
export const Fine = ({ children, style }) => <Text style={[st.fine, style]}>{children}</Text>
export const Row = ({ label, value, note, last }) => (
  <View style={[st.row, last && { borderBottomWidth: 0 }]}>
    <Text style={st.rowL}>{label}</Text>
    <Text style={st.rowV}>{value}{note ? <Text style={st.rowN}>  {note}</Text> : null}</Text>
  </View>
)
export const Btn = ({ label, onPress, primary, disabled }) => (
  <Pressable onPress={onPress} disabled={disabled} accessibilityRole="button"
    style={({ pressed }) => [st.btn, primary && st.btnGo, disabled && { opacity: 0.4 }, pressed && { opacity: 0.7 }]}>
    <Text style={[st.btnT, primary && { color: '#fff' }]}>{label}</Text>
  </Pressable>
)
export const Stepper = ({ label, display, onMinus, onPlus }) => (
  <View style={st.stepper}>
    <Text style={[st.rowL, { flex: 1 }]}>{label}</Text>
    <Pressable onPress={onMinus} accessibilityLabel={`Lower ${label}`} style={st.stepB}><Text style={st.stepBT}>−</Text></Pressable>
    <Text style={st.stepV}>{display}</Text>
    <Pressable onPress={onPlus} accessibilityLabel={`Raise ${label}`} style={st.stepB}><Text style={st.stepBT}>+</Text></Pressable>
  </View>
)

export function ClockRows({ clock }) {
  if (clock.none) return <Fine>Nothing to count down to yet.</Fine>
  const x = (v) => (clock.crossed ? 'already above' : fmtMin(v))
  return (
    <View>
      <Row label="Earliest crossing" value={x(clock.early)} note="10th percentile" />
      <Row label="Most likely" value={x(clock.median)} note="median" />
      <Row label="Latest crossing" value={x(clock.late)} note="90th percentile" />
      <Row label="Barriers and diversion" value={`${RESPONSE_MIN} min`} note="assumed" />
      <Row label="Safety buffer" value={`${BUFFER_MIN} min`} note="assumed" last />
    </View>
  )
}

export const st = StyleSheet.create({
  card: { backgroundColor: C.card, borderRadius: 22, padding: 18, gap: 10 },
  h2: { fontSize: 16, fontWeight: '600', color: C.ink },
  fine: { fontSize: 13, lineHeight: 18, color: C.mute },
  pill: { borderRadius: 99, paddingHorizontal: 10, paddingVertical: 4, alignSelf: 'flex-start' },
  pillT: { fontSize: 12, fontWeight: '600' },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10, paddingVertical: 9, borderBottomWidth: 1, borderBottomColor: C.line },
  rowL: { fontSize: 14, color: C.mute, flexShrink: 1 },
  rowV: { fontSize: 14, fontWeight: '600', color: C.ink, textAlign: 'right', flexShrink: 1 },
  rowN: { fontSize: 12, fontWeight: '400', color: C.mute },
  btn: { borderRadius: 99, paddingHorizontal: 18, paddingVertical: 11, borderWidth: 1.5, borderColor: C.line, backgroundColor: C.card, minHeight: 44, justifyContent: 'center' },
  btnGo: { backgroundColor: C.ink, borderColor: C.ink },
  btnT: { fontSize: 14, fontWeight: '600', color: C.ink },
  stepper: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 4 },
  stepB: { width: 44, height: 44, borderRadius: 22, backgroundColor: C.bg, alignItems: 'center', justifyContent: 'center' },
  stepBT: { fontSize: 22, color: C.ink, lineHeight: 26 },
  stepV: { minWidth: 86, textAlign: 'center', fontSize: 14, fontWeight: '600', color: C.ink },
})
