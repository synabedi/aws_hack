import React, { useEffect, useMemo, useState } from 'react'
import { View, Text, Pressable, ScrollView, StyleSheet, RefreshControl } from 'react-native'
import { StatusBar } from 'expo-status-bar'
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context'
import { C } from './src/theme'
import { interventionClock } from './src/model'
import * as api from './src/data'
import { useNow } from './src/ui'
import { Sites, Site, Approvals, Pumps } from './src/screens'

const TABS = [['sites', 'Sites'], ['site', 'Site desk'], ['approvals', 'Approvals'], ['pumps', 'Pumps']]

export default function App() {
  const [data, setData] = useState(null)
  const [tab, setTab] = useState('sites')
  const [sel, setSel] = useState(null)
  const [officer, setOfficer] = useState('')
  const [apiBase, setApiBase] = useState(process.env.EXPO_PUBLIC_API_BASE || '')
  const [busy, setBusy] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  useNow()
  const now = api.dataNow()

  const load = async (base = apiBase) => setData(await api.loadAll(base))
  useEffect(() => { load(); const id = setInterval(() => { if (!api.source.mock) load() }, 30000); return () => clearInterval(id) }, [])

  const ranked = useMemo(() => (data?.sites || []).map((x) => ({ ...x, clock: interventionClock(x) })).sort((a, b) => {
    const key = (x) => (x.clock.none ? 1e9 : x.latest_reading.status !== 'confident' ? -1e6 : x.clock.margin ?? 1e6) - (x.latest_reading?.max_depth_cm || 0) / 1000
    return key(a) - key(b)
  }), [data])

  if (!data) return <SafeAreaProvider><View style={[s.root, s.center]}><Text style={s.sub}>Loading sites</Text></View></SafeAreaProvider>

  const cur = ranked.find((x) => x.site.site_id === sel) || ranked[0]
  const pending = data.actions.filter((a) => a.status === 'proposed').length
  const open = (id) => { setSel(id); setTab('site') }
  const connect = async (base) => { setApiBase(base); await load(base) }
  const decide = async (action, verb) => { setBusy(true); try { await api.decide(action, verb, officer.trim()); await load() } finally { setBusy(false) } }
  const refresh = async () => { setRefreshing(true); await load(); setRefreshing(false) }

  return (
    <SafeAreaProvider>
      <SafeAreaView style={s.root} edges={['top', 'left', 'right']}>
        <StatusBar style="light" />
        <View style={s.top}>
          <Text style={s.brand}>JalMaapi <Text style={s.brandHi}>जलमापी</Text></Text>
          {api.source.mock ? <View style={s.demo}><Text style={s.demoT}>Demo snapshot</Text></View> : <View style={[s.demo, { backgroundColor: C.greenT }]}><Text style={[s.demoT, { color: '#17734f' }]}>Live</Text></View>}
        </View>
        <ScrollView style={s.scroll} contentContainerStyle={s.body} keyboardShouldPersistTaps="handled"
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}>
          {tab === 'sites' && <Sites ranked={ranked} now={now} onOpen={open} apiBase={apiBase} onConnect={connect} />}
          {tab === 'site' && <Site cur={cur} now={now} />}
          {tab === 'approvals' && <Approvals actions={data.actions} ranked={ranked} officer={officer} setOfficer={setOfficer} onDecide={decide} busy={busy} />}
          {tab === 'pumps' && <Pumps allocation={data.allocation} ranked={ranked} onOpen={open} />}
        </ScrollView>
        <SafeAreaView edges={['bottom']} style={s.tabs}>
          {TABS.map(([id, label]) => (
            <Pressable key={id} onPress={() => setTab(id)} style={s.tab} accessibilityRole="tab" accessibilityState={{ selected: tab === id }}>
              <View style={[s.tabPill, tab === id && s.tabOn]}>
                <Text style={[s.tabT, tab === id && { color: C.ink }]}>{label}</Text>
                {id === 'approvals' && pending > 0 ? <View style={s.badge}><Text style={s.badgeT}>{pending}</Text></View> : null}
              </View>
            </Pressable>
          ))}
        </SafeAreaView>
      </SafeAreaView>
    </SafeAreaProvider>
  )
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.ink },
  center: { alignItems: 'center', justifyContent: 'center' },
  sub: { color: '#aab2cc', fontSize: 15 },
  top: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 18, paddingVertical: 12 },
  brand: { color: '#fff', fontSize: 20, fontWeight: '700' },
  brandHi: { color: '#9fdfee', fontSize: 16, fontWeight: '400' },
  demo: { backgroundColor: C.amberT, borderRadius: 99, paddingHorizontal: 12, paddingVertical: 5 },
  demoT: { color: '#7a5200', fontSize: 12, fontWeight: '600' },
  scroll: { flex: 1, backgroundColor: C.bg, borderTopLeftRadius: 26, borderTopRightRadius: 26 },
  body: { padding: 16, gap: 14, paddingBottom: 28 },
  tabs: { flexDirection: 'row', backgroundColor: C.ink, paddingHorizontal: 8, paddingTop: 8, paddingBottom: 8 },
  tab: { flex: 1, alignItems: 'center', minHeight: 44, justifyContent: 'center' },
  tabPill: { flexDirection: 'row', alignItems: 'center', gap: 5, borderRadius: 14, paddingHorizontal: 10, paddingVertical: 9 },
  tabOn: { backgroundColor: '#fff' },
  tabT: { color: '#aab2cc', fontSize: 13, fontWeight: '600' },
  badge: { minWidth: 18, height: 18, borderRadius: 9, backgroundColor: C.red, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 4 },
  badgeT: { color: '#fff', fontSize: 11, fontWeight: '700' },
})
