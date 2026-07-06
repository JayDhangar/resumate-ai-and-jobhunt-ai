import { useCallback, useEffect, useState } from 'react'
import { Spinner } from './Loader.jsx'

const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const PRESETS = [
  { label: 'Daily', days: [0, 1, 2, 3, 4, 5, 6] },
  { label: 'Weekdays', days: [0, 1, 2, 3, 4] },
  { label: 'Weekends', days: [5, 6] },
]

export default function AlertsPanel({ currentQuery, currentLocation, remoteOnly, resumes, selectedResumeId, notify }) {
  const [alerts, setAlerts] = useState(null)
  const [quota, setQuota] = useState(null)
  const [creating, setCreating] = useState(false)
  const [runningId, setRunningId] = useState('')
  const [digestOf, setDigestOf] = useState('')

  const load = useCallback(() => {
    fetch('/api/jobs/alerts').then((r) => r.json()).then(setAlerts).catch(() => setAlerts([]))
    fetch('/api/jobs/quota').then((r) => r.json()).then(setQuota).catch(() => {})
  }, [])

  useEffect(() => { load() }, [load])

  const createAlert = async () => {
    if (!currentQuery.trim()) { notify('Type a search query first (in the Search tab)', 'error'); return }
    setCreating(true)
    try {
      const resp = await fetch('/api/jobs/alerts', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: currentQuery, location: currentLocation, remote_only: remoteOnly,
          resume_id: selectedResumeId, days: [0, 1, 2, 3, 4, 5, 6],
        }),
      })
      if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
      notify(`🔔 Alert created for “${currentQuery}” — runs daily, digests only NEW jobs`, 'success')
      load()
    } catch (err) {
      notify(err.message, 'error')
    } finally {
      setCreating(false)
    }
  }

  const update = async (alert, patch) => {
    const payload = {
      name: alert.name, query: alert.query, location: alert.location,
      remote_only: alert.remote_only, resume_id: alert.resume_id,
      days: alert.days, enabled: alert.enabled, email_digest: alert.email_digest,
      ...patch,
    }
    try {
      const resp = await fetch(`/api/jobs/alerts/${alert.id}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
      load()
    } catch (err) {
      notify(err.message, 'error')
    }
  }

  const runNow = async (alert) => {
    setRunningId(alert.id)
    try {
      const resp = await fetch(`/api/jobs/alerts/${alert.id}/run`, { method: 'POST' })
      const body = await resp.json()
      if (!resp.ok) throw new Error(body.detail || resp.statusText)
      notify(body.ran ? `✓ ${body.detail}` : `ℹ ${body.detail}`, 'success')
      setDigestOf(alert.id)
      load()
    } catch (err) {
      notify(err.message, 'error')
    } finally {
      setRunningId('')
    }
  }

  const remove = async (id) => {
    await fetch(`/api/jobs/alerts/${id}`, { method: 'DELETE' })
    notify('Alert deleted', 'success')
    load()
  }

  if (alerts === null) return <div className="glass panel-pad jobs-loading"><Spinner label="Loading alerts…" /></div>

  return (
    <div className="apps-panel">
      <section className="glass panel-pad">
        <div className="match-row">
          <span className="match-title">🔔 Job Alerts</span>
          <button className="btn btn-primary" onClick={createAlert} disabled={creating}>
            + Alert for “{currentQuery || '…'}”{currentLocation ? ` in ${currentLocation}` : ''}
          </button>
        </div>
        <p className="muted small">
          Each alert runs <strong>at most once per day</strong> on its scheduled days, remembers every job
          it has already shown you, and reports <strong>only new postings</strong>. Identical searches share a
          day-level cache, so alerts + manual searches never double-spend your free API quota.
          {quota?.jsearch && (
            <> · JSearch budget this month: <strong>{quota.jsearch.used}/{quota.jsearch.budget}</strong> used.</>
          )}
        </p>
      </section>

      {alerts.length === 0 && (
        <div className="glass panel-pad empty-state">
          <p><strong>No alerts yet.</strong></p>
          <p className="muted small">Search for a role first, then create an alert for it — new matches will be collected daily.</p>
        </div>
      )}

      {alerts.map((alert) => (
        <article key={alert.id} className="glass app-card alert-card">
          <div className="app-main">
            <h3 className="job-title">
              {alert.name || alert.query}
              {!alert.enabled && <span className="muted small"> (paused)</span>}
            </h3>
            <p className="muted small">
              “{alert.query}”{alert.location && <> · {alert.location}</>}{alert.remote_only && ' · remote only'}
              {alert.resume_id && ' · match-scored against your resume'}
              {alert.last_run && <> · last run {new Date(alert.last_run).toLocaleString()}</>}
            </p>
            <div className="day-row">
              {DAY_LABELS.map((label, i) => (
                <button
                  key={label}
                  className={`day-chip ${alert.days.includes(i) ? 'day-on' : ''}`}
                  onClick={() => update(alert, {
                    days: alert.days.includes(i)
                      ? alert.days.filter((d) => d !== i)
                      : [...alert.days, i].sort(),
                  })}
                >{label}</button>
              ))}
              <span className="preset-links">
                {PRESETS.map((p) => (
                  <button key={p.label} className="chip" onClick={() => update(alert, { days: p.days })}>{p.label}</button>
                ))}
              </span>
            </div>
            {digestOf === alert.id && alert.last_new_jobs?.length > 0 && (
              <div className="digest-list">
                {alert.last_new_jobs.slice(0, 8).map((job, i) => (
                  <a key={i} className="digest-item" href={job.url} target="_blank" rel="noopener noreferrer">
                    {job.match_score != null && <strong>{job.match_score}% </strong>}
                    {job.title} @ {job.company} <span className="muted small">({job.location || 'n/a'})</span>
                  </a>
                ))}
              </div>
            )}
          </div>
          <div className="app-side">
            <button className="btn btn-primary" onClick={() => runNow(alert)} disabled={runningId === alert.id}>
              {runningId === alert.id ? 'Running…' : '▶ Run now'}
            </button>
            {alert.last_new_jobs?.length > 0 && (
              <button className="btn btn-outline" onClick={() => setDigestOf(digestOf === alert.id ? '' : alert.id)}>
                {digestOf === alert.id ? 'Hide' : `View ${alert.last_new_jobs.length} new`}
              </button>
            )}
            <label className="remote-toggle">
              <input type="checkbox" checked={alert.enabled} onChange={(e) => update(alert, { enabled: e.target.checked })} />
              Enabled
            </label>
            <label className="remote-toggle" title="Requires SMTP configured in backend/.env">
              <input type="checkbox" checked={alert.email_digest} onChange={(e) => update(alert, { email_digest: e.target.checked })} />
              Email digest
            </label>
            <button className="btn btn-ghost" onClick={() => remove(alert.id)}>🗑 Delete</button>
          </div>
        </article>
      ))}
    </div>
  )
}
