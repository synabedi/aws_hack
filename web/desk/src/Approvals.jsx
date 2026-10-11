import React from 'react'
import { Tag } from './components.jsx'

const time = (ts) => new Date(ts * 1000).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
const TYPE = { closure: 'closure', reopen: 'reopening', pump_move: 'pump move', advisory: 'advisory' }

function Advisory({ a }) {
  if (!a.payload?.advisory_en && !a.payload?.advisory_hi) return null
  return (
    <div className="adv">
      {a.payload.advisory_hi && <p lang="hi" className="hi">{a.payload.advisory_hi}</p>}
      {a.payload.advisory_en && <p lang="en">{a.payload.advisory_en}</p>}
    </div>
  )
}

export default function Approvals({ actions, sites, officer, onDecide, onOpen, busy }) {
  const site = (id) => sites.find((s) => s.site.site_id === id)?.site
  const head = (a) => {
    const s = site(a.site_id)
    return <><button className="link" onClick={() => onOpen(a.site_id)}>{s?.name || a.site_id}</button>{(a.simulated || s?.simulated) && <Tag kind="sim">Simulated</Tag>}</>
  }
  const open = actions.filter((a) => a.status === 'proposed')
  const done = actions.filter((a) => a.status !== 'proposed').sort((a, b) => (b.decided_at || b.published_at || 0) - (a.decided_at || a.published_at || 0))
  return (
    <div className="appr">
      {!open.length && <p className="card empty">Nothing is waiting for a decision. A closure is proposed when a site is at the closure rule or within 20 minutes of it.</p>}
      {open.map((a) => {
        const low = a.reading_status !== 'confident'
        return (
          <article key={a.action_id} className="card ap">
            <header>{head(a)}<span className="pill pill-warn">Proposed {TYPE[a.type] || a.type}</span>{low && <span className="pill pill-review">Low-confidence reading</span>}</header>
            <p>{a.justification}</p>
            <p className="fine">Draft advisory, published only if you approve:</p>
            <Advisory a={a} />
            <div className="ap-btns">
              <button className="btn btn-go" disabled={!officer || busy || low} onClick={() => onDecide(a, 'approve')}>Approve and publish</button>
              <button className="btn" disabled={!officer || busy} onClick={() => onDecide(a, 'reject')}>Reject</button>
              {low ? <span className="fine">Policy blocks approval on a low-confidence reading. Check the frame yourself.</span>
                : !officer && <span className="fine">Enter your officer ID at the top to decide. Every decision is logged against it.</span>}
            </div>
          </article>
        )
      })}
      {!!done.length && <h3>Decision log</h3>}
      {done.map((a) => (
        <article key={a.action_id} className="card ap">
          <header>{head(a)}
            <span className={`pill pill-${a.status === 'rejected' ? 'review' : 'pass'}`}>
              {a.status === 'rejected' ? 'Rejected' : a.approved_by ? `${TYPE[a.type] || a.type} approved and published` : 'Advisory published automatically'}
            </span>
          </header>
          <p className="fine">
            {a.approved_by ? `${a.status === 'rejected' ? 'Rejected' : 'Approved'} by ${a.approved_by} at ${time(a.decided_at)}` : `${a.justification} Published at ${time(a.published_at)}.`}
          </p>
          {a.status !== 'rejected' && <Advisory a={a} />}
        </article>
      ))}
    </div>
  )
}
