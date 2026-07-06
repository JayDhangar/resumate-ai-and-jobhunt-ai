import { useCallback, useEffect, useState } from 'react'
import { Spinner } from './Loader.jsx'

const STATUSES = ['saved', 'applied', 'interviewing', 'offer', 'rejected']
const STATUS_META = {
  saved: { label: '🔖 Saved', cls: 'st-saved' },
  applied: { label: '📤 Applied', cls: 'st-applied' },
  interviewing: { label: '🎤 Interviewing', cls: 'st-interview' },
  offer: { label: '🎉 Offer', cls: 'st-offer' },
  rejected: { label: '✗ Rejected', cls: 'st-rejected' },
}

export default function ApplicationsPanel({ notify }) {
  const [apps, setApps] = useState(null)
  const [filter, setFilter] = useState('')

  const load = useCallback(() => {
    fetch('/api/jobs/applications')
      .then((r) => r.json())
      .then(setApps)
      .catch(() => setApps([]))
  }, [])

  useEffect(() => { load() }, [load])

  const update = async (id, patch) => {
    try {
      const resp = await fetch(`/api/jobs/applications/${id}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      })
      if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
      load()
    } catch (err) {
      notify(err.message, 'error')
    }
  }

  const remove = async (id) => {
    await fetch(`/api/jobs/applications/${id}`, { method: 'DELETE' })
    notify('Removed from tracker', 'success')
    load()
  }

  if (apps === null) return <div className="glass panel-pad jobs-loading"><Spinner label="Loading your applications…" /></div>

  const visible = filter ? apps.filter((a) => a.status === filter) : apps
  const counts = STATUSES.reduce((acc, s) => ({ ...acc, [s]: apps.filter((a) => a.status === s).length }), {})

  return (
    <div className="apps-panel">
      <div className="glass panel-pad apps-summary">
        <button className={`chip ${filter === '' ? 'chip-active' : ''}`} onClick={() => setFilter('')}>
          All ({apps.length})
        </button>
        {STATUSES.map((s) => (
          <button key={s} className={`chip ${filter === s ? 'chip-active' : ''}`} onClick={() => setFilter(filter === s ? '' : s)}>
            {STATUS_META[s].label} ({counts[s]})
          </button>
        ))}
      </div>

      {visible.length === 0 && (
        <div className="glass panel-pad empty-state">
          <p><strong>Nothing tracked yet.</strong></p>
          <p className="muted small">
            Use the 🔖 button on any job to save it, or send an application email — sent
            applications are logged here automatically.
          </p>
        </div>
      )}

      {visible.map((app) => (
        <article key={app.id} className="glass app-card">
          <div className="app-main">
            <h3 className="job-title">{app.job_title}</h3>
            <p className="job-sub">
              <strong>{app.company || '—'}</strong>
              {app.location && <> · {app.location}</>}
            </p>
            <p className="muted small">
              {app.applied_at && <>applied {new Date(app.applied_at).toLocaleDateString()} · </>}
              {app.email_to && <>to {app.email_to} · </>}
              {app.resume_title && <>with “{app.resume_title}” · </>}
              added {new Date(app.created_at).toLocaleDateString()}
            </p>
            <input
              className="input notes-input" placeholder="Notes (interview dates, contacts…)"
              defaultValue={app.notes}
              onBlur={(e) => e.target.value !== app.notes && update(app.id, { notes: e.target.value })}
            />
          </div>
          <div className="app-side">
            <select
              className={`input select status-select ${STATUS_META[app.status]?.cls || ''}`}
              value={app.status}
              onChange={(e) => update(app.id, { status: e.target.value })}
            >
              {STATUSES.map((s) => <option key={s} value={s}>{STATUS_META[s].label}</option>)}
            </select>
            {app.url && (
              <a className="btn btn-outline" href={app.url} target="_blank" rel="noopener noreferrer">View posting ↗</a>
            )}
            <button className="btn btn-ghost" onClick={() => remove(app.id)}>🗑 Remove</button>
          </div>
        </article>
      ))}
    </div>
  )
}
