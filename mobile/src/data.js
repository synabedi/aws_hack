// Data layer. Same contract as web/API.md (contracts/schemas.py shapes).
// With an API address it talks to the FastAPI service; without one, or if the API cannot be
// reached, it uses the demo snapshot bundled in assets/mock and the app says so.
import sites from '../assets/mock/sites.json'
import actions from '../assets/mock/actions.json'
import allocation from '../assets/mock/allocation.json'
import meta from '../assets/mock/meta.json'
import perSite from '../assets/mock/per_site.json'

export const source = { mock: true, base: '', offset: Date.now() / 1000 - meta.generated_ts, error: null }
// In demo mode the snapshot's clock runs from the moment it was generated.
export const dataNow = () => Date.now() / 1000 - source.offset

let mockActions = actions

async function get(path, opts) {
  const ctl = new AbortController()
  const timer = setTimeout(() => ctl.abort(), 8000)
  try {
    const r = await fetch(source.base + path, { headers: { Accept: 'application/json', 'Content-Type': 'application/json' }, signal: ctl.signal, ...opts })
    if (!r.ok) throw new Error(`${path} returned ${r.status}`)
    return await r.json()
  } finally { clearTimeout(timer) }
}

export async function loadAll(base) {
  source.base = (base || '').trim().replace(/\/$/, '')
  if (source.base) {
    try {
      const [s, a] = await Promise.all([get('/sites'), get('/actions')])
      const al = await get('/allocations/latest').catch(() => null)
      source.mock = false; source.offset = 0; source.error = null
      return { sites: s, actions: a, allocation: al }
    } catch (e) {
      source.error = `Could not reach ${source.base}. Showing the demo snapshot.`
    }
  } else source.error = null
  source.mock = true; source.offset = source.offset || Date.now() / 1000 - meta.generated_ts
  if (!source.offset) source.offset = Date.now() / 1000 - meta.generated_ts
  return { sites, actions: mockActions, allocation }
}

export const history = (id) =>
  source.mock ? Promise.resolve(perSite.history[id]?.readings || []) : get(`/sites/${id}/history`).then((h) => h.readings || h || []).catch(() => [])

// FloodLab inputs. Optional on the API: GET /sites/{id}/lab.
export const lab = (id) => (source.mock ? Promise.resolve(perSite.lab[id] || null) : get(`/sites/${id}/lab`).catch(() => null))

export const simulate = (id, pumps) =>
  source.mock
    ? Promise.resolve(perSite.simulate[id]?.[String(pumps)] || null)
    : get(`/sites/${id}/simulate`, { method: 'POST', body: JSON.stringify({ pumps, minutes: 60 }) }).catch(() => null)

export async function decide(action, verb, officer) {
  if (!source.mock) return get(`/actions/${action.action_id}/${verb}`, { method: 'POST', body: JSON.stringify({ officer_id: officer }) })
  const ts = dataNow()
  const done = { ...action, status: verb === 'approve' ? 'published' : 'rejected', approved_by: officer, decided_at: ts, published_at: verb === 'approve' ? ts : null }
  mockActions = mockActions.map((a) => (a.action_id === action.action_id ? done : a))
  return done
}
