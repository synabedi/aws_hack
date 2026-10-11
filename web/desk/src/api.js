// Data layer. Same contract as web/API.md (contracts/schemas.py shapes).
// Order: ?api=<url> or VITE_API_BASE, else same origin (served by FastAPI). If the API
// is unreachable, or with ?mock=1, the demo snapshot in public/mock is used and labelled.
const qs = new URLSearchParams(location.search)
const BASE = (qs.get('api') || import.meta.env.VITE_API_BASE || '').replace(/\/$/, '')
const FORCE_MOCK = qs.get('mock') === '1'
const MOCK = `${import.meta.env.BASE_URL}mock/`

export const source = { mock: false, offset: 0, meta: null, feedUrl: `${BASE}/feed` }
// In demo mode the snapshot's clock runs from the moment it was generated.
export const dataNow = () => Date.now() / 1000 - source.offset

async function get(path, opts) {
  const r = await fetch(BASE + path, { headers: { Accept: 'application/json', 'Content-Type': 'application/json' }, ...opts })
  if (!r.ok) throw new Error(`${path} returned ${r.status}`)
  return r.json()
}
async function mget(name) {
  const r = await fetch(`${MOCK}${name}.json`)
  if (!r.ok) throw new Error(`demo file ${name} missing`)
  return r.json()
}

let mockActions = null
export async function loadAll() {
  if (!FORCE_MOCK && !source.mock) {
    try {
      const [sites, actions] = await Promise.all([get('/sites'), get('/actions')])
      const [allocation, meta] = await Promise.all([get('/allocations/latest').catch(() => null), get('/meta').catch(() => null)])
      source.meta = meta
      return { sites, actions, allocation }
    } catch (e) {
      console.warn('API unavailable, using the demo snapshot:', e.message)
    }
  }
  const [sites, actions, allocation, meta] = await Promise.all([mget('sites'), mget('actions'), mget('allocation'), mget('meta')])
  if (!source.mock) { source.mock = true; source.meta = meta; source.offset = Date.now() / 1000 - meta.generated_ts; source.feedUrl = `${MOCK}feed.json` }
  mockActions = mockActions || actions
  return { sites, actions: mockActions, allocation }
}

export const history = (id) =>
  (source.mock ? mget(`history_${id}`) : get(`/sites/${id}/history`)).then((h) => h.readings || h || []).catch(() => [])

// FloodLab inputs (basin table, rain ahead, fitted parameters). Optional on the API: GET /sites/{id}/lab.
export const lab = (id) => (source.mock ? mget(`lab_${id}`) : get(`/sites/${id}/lab`)).catch(() => null)

export const simulate = (id, pumps) =>
  source.mock
    ? mget(`simulate_${id}`).then((all) => all[String(pumps)]).catch(() => null)
    : get(`/sites/${id}/simulate`, { method: 'POST', body: JSON.stringify({ pumps, minutes: 60 }) }).catch(() => null)

export async function decide(action, verb, officer) {
  if (!source.mock) return get(`/actions/${action.action_id}/${verb}`, { method: 'POST', body: JSON.stringify({ officer_id: officer }) })
  const ts = dataNow()
  const done = { ...action, status: verb === 'approve' ? 'published' : 'rejected', approved_by: officer, decided_at: ts, published_at: verb === 'approve' ? ts : null }
  mockActions = mockActions.map((a) => (a.action_id === action.action_id ? done : a))
  return done
}
