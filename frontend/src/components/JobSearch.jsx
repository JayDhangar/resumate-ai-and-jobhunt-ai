import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import AlertsPanel from './AlertsPanel.jsx'
import ApplicationsPanel from './ApplicationsPanel.jsx'
import JobFitModal from './JobFitModal.jsx'
import { Spinner } from './Loader.jsx'

const ROLE_CHIPS = [
  'AI Engineer', 'Software Developer', 'ML Engineer', 'Data Scientist',
  'Frontend Developer', 'Backend Developer', 'Full Stack Developer', 'DevOps Engineer',
]

const VERDICT_META = {
  trusted: { label: 'Trusted', cls: 'trust-high' },
  likely_genuine: { label: 'Likely genuine', cls: 'trust-good' },
  unverified: { label: 'Unverified', cls: 'trust-mid' },
  suspicious: { label: 'Suspicious', cls: 'trust-low' },
}

const PLATFORM_COLORS = {
  linkedin: '#0a66c2', indeed: '#2557a7', naukri: '#4a7fdc', monster: '#6e46ae',
  glassdoor: '#0caa41', ziprecruiter: '#1d915c', wellfound: '#333333',
  remotive: '#12a5a1', remoteok: '#d64545', arbeitnow: '#4a5568',
  themuse: '#8459c8', adzuna: '#1d8649', jooble: '#d97a1e', jsearch: '#3f6fb5',
}

function platformOf(job) {
  const raw = (job.via || job.source || '').toLowerCase()
  const key = Object.keys(PLATFORM_COLORS).find((p) => raw.includes(p))
  return { label: (job.via || job.source || 'board').replace(/^\w/, (c) => c.toUpperCase()), color: PLATFORM_COLORS[key] || '#5d6a88' }
}

const EXP_OPTIONS = [
  { v: '', label: 'Any experience' },
  { v: '0-1', label: '0–1 yrs (Fresher)' },
  { v: '1-3', label: '1–3 yrs' },
  { v: '3-5', label: '3–5 yrs' },
  { v: '5+', label: '5+ yrs' },
]

export default function JobSearch({ notify }) {
  const [query, setQuery] = useState('')
  const [selectedRoles, setSelectedRoles] = useState(['AI Engineer'])
  const [expFilter, setExpFilter] = useState('')
  const [location, setLocation] = useState('')
  const [remoteOnly, setRemoteOnly] = useState(false)
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(false)
  const [sources, setSources] = useState(null)
  const [expanded, setExpanded] = useState(null)
  const [matchedResume, setMatchedResume] = useState(null) // {id,title,name} when in match mode
  const [resumes, setResumes] = useState(null)
  const [selectedResumeId, setSelectedResumeId] = useState('')
  const [fitJob, setFitJob] = useState(null) // job whose Fit & Apply modal is open
  const [view, setView] = useState('search') // search | apps

  const loadResumes = useCallback(() => {
    api.listResumes().then((list) => {
      setResumes(list)
      setSelectedResumeId((current) => current || (list[0]?.id ?? ''))
    }).catch(() => setResumes([]))
  }, [])

  useEffect(() => {
    fetch('/api/jobs/sources').then((r) => r.json()).then(setSources).catch(() => {})
    loadResumes()
  }, [loadResumes])

  const buildQuery = useCallback((roles = selectedRoles, typed = query) => {
    const parts = [...roles]
    const custom = typed.trim()
    if (custom && !parts.some((r) => r.toLowerCase() === custom.toLowerCase())) parts.push(custom)
    return parts.join('|')
  }, [selectedRoles, query])

  const search = useCallback(async (qOverride = null, expOverride = null) => {
    const q = qOverride ?? buildQuery()
    if (!q.trim()) { notify('Pick at least one role chip or type a role', 'error'); return }
    setLoading(true)
    setExpanded(null)
    setMatchedResume(null)
    try {
      const params = new URLSearchParams({
        q, location, remote_only: remoteOnly, exp: expOverride ?? expFilter,
      })
      const resp = await fetch(`/api/jobs/search?${params}`)
      if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
      setResults(await resp.json())
    } catch (err) {
      notify(`Job search failed: ${err.message}`, 'error')
    } finally {
      setLoading(false)
    }
  }, [buildQuery, location, remoteOnly, expFilter, notify])

  const toggleRole = (role) => {
    const next = selectedRoles.includes(role)
      ? selectedRoles.filter((r) => r !== role)
      : [...selectedRoles, role]
    setSelectedRoles(next)
    if (next.length || query.trim()) search(buildQuery(next))
  }

  const matchResume = useCallback(async (resumeId) => {
    setLoading(true)
    setExpanded(null)
    try {
      const resp = await fetch('/api/jobs/match', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resume_id: resumeId, query: '', location, remote_only: remoteOnly }),
      })
      if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
      const body = await resp.json()
      setResults(body)
      setMatchedResume(body.matched_resume)
      setQuery(body.query)
      notify(`Found ${body.total} jobs matched to "${body.matched_resume.title}"`, 'success')
    } catch (err) {
      notify(`Matching failed: ${err.message}`, 'error')
    } finally {
      setLoading(false)
    }
  }, [location, remoteOnly, notify])

  useEffect(() => { search() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const keyedSources = sources ? Object.entries(sources).filter(([, v]) => v.needs_key) : []
  const missingKeys = keyedSources.filter(([, v]) => !v.enabled)

  const saveJob = async (job) => {
    try {
      const resp = await fetch('/api/jobs/applications', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          job: { title: job.title, company: job.company, location: job.location, description: '', url: job.url },
          source: job.via || job.source, resume_id: selectedResumeId,
        }),
      })
      const body = await resp.json()
      if (!resp.ok) throw new Error(body.detail || resp.statusText)
      notify(body.saved ? '🔖 Saved to My Applications' : 'Already in your tracker', 'success')
    } catch (err) {
      notify(err.message, 'error')
    }
  }

  return (
    <div className="jobs-page">
      <div className="jobs-view-tabs tabs">
        <button className={`tab ${view === 'search' ? 'tab-active' : ''}`} onClick={() => setView('search')}>
          🔍 Search Jobs
        </button>
        <button className={`tab ${view === 'alerts' ? 'tab-active' : ''}`} onClick={() => setView('alerts')}>
          🔔 Alerts
        </button>
        <button className={`tab ${view === 'apps' ? 'tab-active' : ''}`} onClick={() => setView('apps')}>
          📋 My Applications
        </button>
      </div>

      {view === 'apps' && <ApplicationsPanel notify={notify} />}
      {view === 'alerts' && (
        <AlertsPanel
          currentQuery={buildQuery()} currentLocation={location} remoteOnly={remoteOnly}
          resumes={resumes} selectedResumeId={selectedResumeId} notify={notify}
        />
      )}
      {view === 'search' && (
      <>
      <section className="glass panel-pad jobs-controls">
        <div className="jobs-search-row">
          <input
            className="input jobs-query" placeholder="Extra role/keywords (optional — combines with the chips below)"
            value={query} onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && search()}
          />
          <input
            className="input jobs-loc" placeholder="Location (optional)"
            value={location} onChange={(e) => setLocation(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && search()}
          />
          <select
            className="input select"
            value={expFilter}
            onChange={(e) => { setExpFilter(e.target.value); search(null, e.target.value) }}
            title="Filter by required years of experience"
          >
            {EXP_OPTIONS.map((o) => <option key={o.v} value={o.v}>{o.label}</option>)}
          </select>
          <label className="remote-toggle">
            <input type="checkbox" checked={remoteOnly} onChange={(e) => setRemoteOnly(e.target.checked)} />
            Remote only
          </label>
          <button className="btn btn-primary" onClick={() => search()} disabled={loading}>
            {loading ? 'Searching…' : '🔍 Search'}
          </button>
        </div>
        <div className="chips">
          {ROLE_CHIPS.map((role) => (
            <button key={role} className={`chip ${selectedRoles.includes(role) ? 'chip-active' : ''}`}
              title="Click to select/deselect — combine as many roles as you like"
              onClick={() => toggleRole(role)}>
              {selectedRoles.includes(role) ? '✓ ' : ''}{role}
            </button>
          ))}
        </div>
        {missingKeys.length > 0 && (
          <p className="muted small sources-note">
            Active boards: {results?.sources_available?.join(', ') || 'loading…'}.
            Unlock more ({missingKeys.map(([k]) => k).join(', ')}) with free API keys in <code>backend/.env</code> —
            JSearch adds LinkedIn / Indeed / Naukri listings.
          </p>
        )}
      </section>

      <MatchPanel
        onMatch={matchResume} loading={loading} notify={notify} matchedResume={matchedResume}
        resumes={resumes} selectedId={selectedResumeId} setSelectedId={setSelectedResumeId}
        onResumeAdded={loadResumes}
      />

      <div className="jobs-results">
        {loading && <div className="glass panel-pad jobs-loading"><Spinner label={matchedResume ? 'Matching jobs to your resume…' : 'Searching job boards in parallel…'} /></div>}
        {!loading && results && results.jobs.length === 0 && (
          <div className="glass panel-pad empty-state">
            <p><strong>No jobs matched your filters.</strong></p>
            <p className="muted small">
              Try a broader title or clear the location. Note: the free keyless boards mostly
              list remote/EU/US roles — for on-site listings in a specific country (e.g. India via
              LinkedIn / Indeed / Naukri), add a free <code>RAPIDAPI_KEY</code> or Adzuna key in{' '}
              <code>backend/.env</code>.
            </p>
          </div>
        )}
        {!loading && results && results.jobs.length > 0 && (
          <>
            <p className="muted small results-meta">
              {matchedResume
                ? <>🎯 {results.total} jobs ranked by similarity to <strong>{matchedResume.title}</strong> ({matchedResume.name})</>
                : <>{results.total} jobs from {results.sources_used.join(', ')} — ranked by relevance &amp; genuineness</>}
            </p>
            {results.jobs.map((job) => (
              <JobCard
                key={job.id} job={job}
                expanded={expanded === job.id}
                onToggle={() => setExpanded(expanded === job.id ? null : job.id)}
                canFit={!!selectedResumeId}
                onFitApply={() => setFitJob(job)}
                onSave={() => saveJob(job)}
              />
            ))}
          </>
        )}
      </div>
      </>
      )}
      {fitJob && selectedResumeId && (
        <JobFitModal
          job={fitJob}
          resumeId={selectedResumeId}
          resumeLabel={resumes?.find((r) => r.id === selectedResumeId)?.title || 'your resume'}
          notify={notify}
          onClose={() => setFitJob(null)}
        />
      )}
    </div>
  )
}

function MatchPanel({ onMatch, loading, notify, matchedResume, resumes, selectedId, setSelectedId, onResumeAdded }) {
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef(null)

  const handleUpload = async (files) => {
    const file = files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const record = await api.uploadResume(file)
      notify(`Resume "${record.data.name || record.title}" extracted ✓`, 'success')
      setSelectedId(record.id)
      onResumeAdded()
      onMatch(record.id)
    } catch (err) {
      notify(`Upload failed: ${err.message}`, 'error')
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  return (
    <section className={`glass panel-pad match-panel ${matchedResume ? 'match-active' : ''}`}>
      <div className="match-row">
        <span className="match-title">🎯 Match jobs to my resume</span>
        {resumes === null ? (
          <span className="muted small">loading resumes…</span>
        ) : (
          <>
            {resumes.length > 0 && (
              <select className="input select match-select" value={selectedId} onChange={(e) => setSelectedId(e.target.value)}>
                {resumes.map((r) => {
                  const name = r.data.name || ''
                  const showName = name && name.toLowerCase() !== r.title.toLowerCase()
                  return (
                    <option key={r.id} value={r.id}>{r.title}{showName ? ` — ${name}` : ''}</option>
                  )
                })}
              </select>
            )}
            {resumes.length > 0 && (
              <button className="btn btn-primary" disabled={loading || !selectedId} onClick={() => onMatch(selectedId)}>
                Find matching jobs
              </button>
            )}
            <button className="btn btn-outline" disabled={uploading} onClick={() => fileRef.current?.click()}>
              {uploading ? 'Extracting…' : '⇪ Upload resume'}
            </button>
            <input ref={fileRef} type="file" hidden accept=".pdf,.docx,.png,.jpg,.jpeg" onChange={(e) => handleUpload(e.target.files)} />
          </>
        )}
      </div>
      <p className="muted small">
        Your resume is embedded and compared against every live posting (RAG similarity) —
        results get a match % and the overlapping skills.
      </p>
    </section>
  )
}

function JobCard({ job, expanded, onToggle, canFit, onFitApply, onSave }) {
  const verdict = VERDICT_META[job.trust?.verdict] || VERDICT_META.unverified
  const platform = platformOf(job)
  return (
    <article className={`glass job-card ${expanded ? 'job-open' : ''}`}>
      <div className="job-head" onClick={onToggle} role="button" tabIndex={0}>
        <div className="job-main">
          <div className="job-title-row">
            <span className="platform-badge" style={{ background: platform.color }}>{platform.label}</span>
            <h3 className="job-title">{job.title}</h3>
          </div>
          <p className="job-sub">
            <strong>{job.company || 'Unknown company'}</strong>
            {job.location && <> · {job.location}</>}
            {job.remote && <span className="remote-pill">Remote</span>}
            {job.salary && <> · <span className="salary">{job.salary}</span></>}
          </p>
          <p className="muted small job-meta">
            {job.posted_at && <>posted {job.posted_at} · </>}
            {job.tags?.length > 0 && <>{job.tags.slice(0, 4).join(' · ')}</>}
          </p>
          {job.matching_skills?.length > 0 && (
            <div className="match-skills">
              {job.matching_skills.map((skill) => <span key={skill} className="skill-hit">{skill}</span>)}
            </div>
          )}
        </div>
        <div className="job-side">
          {job.match_score != null && (
            <div className="match-badge" title="Similarity to your resume">
              <span className="match-pct">{job.match_score}%</span>
              <span className="match-lbl">match</span>
            </div>
          )}
          <div className={`trust-badge ${verdict.cls}`} title="Genuineness score">
            <span className="trust-score">{job.trust?.score ?? '–'}</span>
            <span className="trust-label">{verdict.label}</span>
          </div>
          <div className="job-side-actions">
            <button className="btn btn-outline" title="Save to My Applications"
              onClick={(e) => { e.stopPropagation(); onSave() }}>🔖</button>
            <a
              className="btn btn-primary apply-btn" href={job.url} target="_blank" rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
            >
              Apply ↗
            </a>
          </div>
        </div>
      </div>
      {expanded && (
        <div className="job-body">
          {canFit && (
            <button className="btn btn-primary btn-block fit-cta" onClick={onFitApply}>
              📊 Resume Fit &amp; Apply Email — score my resume against this job
            </button>
          )}
          {job.trust?.reasons?.length > 0 && (
            <ul className="trust-reasons">
              {job.trust.reasons.map((reason, i) => <li key={i}>{reason}</li>)}
            </ul>
          )}
          <p className="job-desc">{job.description || 'No description provided — check the posting via the apply link.'}</p>
          <p className="muted small">Apply link: <a href={job.url} target="_blank" rel="noopener noreferrer">{job.url}</a></p>
        </div>
      )}
    </article>
  )
}
