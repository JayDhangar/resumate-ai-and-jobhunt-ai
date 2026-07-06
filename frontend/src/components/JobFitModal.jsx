import { useCallback, useEffect, useState } from 'react'
import { Spinner } from './Loader.jsx'

const TONES = [
  { key: 'professional', label: 'Professional' },
  { key: 'concise', label: 'Concise' },
  { key: 'enthusiastic', label: 'Enthusiastic' },
  { key: 'formal', label: 'Formal' },
]

const jobPayload = (job) => ({
  title: job.title, company: job.company, location: job.location,
  description: job.description, url: job.url,
})

export default function JobFitModal({ job, resumeId, resumeLabel, notify, onClose }) {
  const [tab, setTab] = useState('fit')

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal fit-modal glass-strong" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div>
            <h3>{job.title}</h3>
            <p className="muted small">{job.company} · matched against <strong>{resumeLabel}</strong></p>
          </div>
          <div className="modal-actions">
            <div className="tabs">
              <button className={`tab ${tab === 'fit' ? 'tab-active' : ''}`} onClick={() => setTab('fit')}>📊 Resume Fit</button>
              <button className={`tab ${tab === 'email' ? 'tab-active' : ''}`} onClick={() => setTab('email')}>✉️ Apply Email</button>
              <button className={`tab ${tab === 'cover' ? 'tab-active' : ''}`} onClick={() => setTab('cover')}>📄 Cover Letter</button>
            </div>
            <button className="btn btn-ghost" onClick={onClose}>✕</button>
          </div>
        </div>
        <div className="fit-body">
          {tab === 'fit' && <FitTab job={job} resumeId={resumeId} notify={notify} />}
          {tab === 'email' && <EmailTab job={job} resumeId={resumeId} notify={notify} />}
          {tab === 'cover' && <CoverLetterTab job={job} resumeId={resumeId} notify={notify} />}
        </div>
      </div>
    </div>
  )
}

function FitTab({ job, resumeId, notify }) {
  const [fit, setFit] = useState(null)
  const [loading, setLoading] = useState(true)
  const [tailoring, setTailoring] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetch('/api/jobs/analyze-fit', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resume_id: resumeId, job: jobPayload(job) }),
    })
      .then(async (r) => { if (!r.ok) throw new Error((await r.json()).detail || r.statusText); return r.json() })
      .then((data) => { if (!cancelled) setFit(data) })
      .catch((err) => notify(`Fit analysis failed: ${err.message}`, 'error'))
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [job, resumeId, notify, refreshKey])

  const tailor = async () => {
    setTailoring(true)
    try {
      const resp = await fetch('/api/jobs/tailor', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resume_id: resumeId, job: jobPayload(job) }),
      })
      const body = await resp.json()
      if (!resp.ok) throw new Error(body.detail || resp.statusText)
      notify(`✨ Resume tailored for this job — saved as version ${body.version}. Re-scoring…`, 'success')
      setRefreshKey((k) => k + 1)  // re-run the fit analysis with the tailored resume
    } catch (err) {
      notify(`Tailoring failed: ${err.message}`, 'error')
    } finally {
      setTailoring(false)
    }
  }

  if (loading) return <div className="fit-loading"><Spinner label="AI is comparing your resume with this job…" /></div>
  if (!fit) return <p className="muted empty">Analysis unavailable.</p>

  const hue = Math.round((fit.fit_score / 100) * 120)
  const suggestions = fit.suggestions || {}
  return (
    <div className="fit-content">
      <div className="fit-score-row">
        <div className="fit-dial" style={{ borderColor: `hsl(${hue} 65% 45%)` }}>
          <span className="fit-num" style={{ color: `hsl(${hue} 65% 50%)` }}>{fit.fit_score}</span>
          <span className="fit-lbl">fit score</span>
        </div>
        <div className="fit-skills">
          {fit.matched_skills?.length > 0 && (
            <div>
              <span className="field-label">✓ You already have</span>
              <div className="chips">{fit.matched_skills.map((s) => <span key={s} className="skill-hit">{s}</span>)}</div>
            </div>
          )}
          {fit.missing_skills?.length > 0 && (
            <div>
              <span className="field-label">✗ The role also wants</span>
              <div className="chips">{fit.missing_skills.map((s) => <span key={s} className="skill-miss">{s}</span>)}</div>
            </div>
          )}
        </div>
      </div>
      <div className="fit-suggestions">
        <h4>How to align your resume with this role</h4>
        {suggestions.summary && <p><strong>Summary:</strong> {suggestions.summary}</p>}
        {suggestions.skills?.length > 0 && (
          <p><strong>Skills to add/emphasise:</strong> {suggestions.skills.join(', ')}</p>
        )}
        {suggestions.experience?.length > 0 && (
          <><strong>Experience:</strong><ul>{suggestions.experience.map((s, i) => <li key={i}>{s}</li>)}</ul></>
        )}
        {suggestions.projects?.length > 0 && (
          <><strong>Projects:</strong><ul>{suggestions.projects.map((s, i) => <li key={i}>{s}</li>)}</ul></>
        )}
        {fit.source === 'heuristic' && (
          <p className="muted small">Heuristic analysis (no AI provider reachable) — AI gives deeper suggestions.</p>
        )}
      </div>
      <button className="btn btn-primary btn-block btn-lg tailor-btn" onClick={tailor} disabled={tailoring}>
        {tailoring ? '✨ Tailoring your resume…' : '✨ Tailor my resume for this job (saves a new version)'}
      </button>
      <p className="muted small">
        AI rewrites your summary and bullets to target this posting — without inventing anything.
        Your previous resume stays safe in version history.
      </p>
    </div>
  )
}

function CoverLetterTab({ job, resumeId, notify }) {
  const [tone, setTone] = useState('professional')
  const [letter, setLetter] = useState(null)
  const [loading, setLoading] = useState(false)
  const [downloading, setDownloading] = useState(false)

  const generate = useCallback(async (selectedTone = tone, regenerate = false) => {
    setLoading(true)
    try {
      const resp = await fetch('/api/jobs/cover-letter', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          resume_id: resumeId, job: jobPayload(job), tone: selectedTone,
          previous_body: regenerate ? (letter?.body || '') : '',
        }),
      })
      if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
      setLetter(await resp.json())
    } catch (err) {
      notify(`Cover letter failed: ${err.message}`, 'error')
    } finally {
      setLoading(false)
    }
  }, [tone, resumeId, job, letter, notify])

  useEffect(() => { generate() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const downloadPdf = async () => {
    setDownloading(true)
    try {
      const resp = await fetch('/api/jobs/cover-letter/pdf', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resume_id: resumeId, title: letter.title, body: letter.body }),
      })
      if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'Cover_Letter.pdf'
      a.click()
      URL.revokeObjectURL(url)
      notify('📄 Cover letter PDF downloaded', 'success')
    } catch (err) {
      notify(err.message, 'error')
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="email-tab">
      <div className="email-toolbar">
        <div className="segmented tone-seg">
          {TONES.map((t) => (
            <button key={t.key} className={`seg ${tone === t.key ? 'seg-active' : ''}`}
              onClick={() => { setTone(t.key); generate(t.key, false) }}>{t.label}</button>
          ))}
        </div>
        <button className="btn btn-outline" onClick={() => generate(tone, true)} disabled={loading}>
          🔄 Regenerate
        </button>
      </div>
      {loading && <div className="fit-loading"><Spinner label="Writing your cover letter…" /></div>}
      {!loading && letter && (
        <>
          <label className="field-label">Title</label>
          <input className="input" value={letter.title}
            onChange={(e) => setLetter({ ...letter, title: e.target.value })} />
          <label className="field-label">Letter (editable)</label>
          <textarea className="input textarea email-body" rows={15} value={letter.body}
            onChange={(e) => setLetter({ ...letter, body: e.target.value })} />
          <div className="email-actions">
            <button className="btn btn-primary" onClick={downloadPdf} disabled={downloading}>
              {downloading ? 'Rendering PDF…' : '⬇ Download PDF'}
            </button>
            <button className="btn btn-outline" onClick={async () => {
              await navigator.clipboard.writeText(letter.body)
              notify('Cover letter copied', 'success')
            }}>⧉ Copy</button>
          </div>
        </>
      )}
    </div>
  )
}

function EmailTab({ job, resumeId, notify }) {
  const [tone, setTone] = useState('professional')
  const [draft, setDraft] = useState(null)
  const [loading, setLoading] = useState(false)
  const [to, setTo] = useState('')
  const [sending, setSending] = useState(false)
  const [smtp, setSmtp] = useState(null)
  const [showTips, setShowTips] = useState(false)
  const [attachResume, setAttachResume] = useState(true)

  useEffect(() => {
    fetch('/api/jobs/email-status').then((r) => r.json()).then(setSmtp).catch(() => setSmtp({ configured: false }))
  }, [])

  const generate = useCallback(async (selectedTone = tone, regenerate = false) => {
    setLoading(true)
    try {
      const resp = await fetch('/api/jobs/draft-email', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          resume_id: resumeId, job: jobPayload(job), tone: selectedTone,
          previous_subject: regenerate ? (draft?.subject || '') : '',
        }),
      })
      if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
      setDraft(await resp.json())
    } catch (err) {
      notify(`Email drafting failed: ${err.message}`, 'error')
    } finally {
      setLoading(false)
    }
  }, [tone, resumeId, job, draft, notify])

  useEffect(() => { generate() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const send = async () => {
    setSending(true)
    try {
      const resp = await fetch('/api/jobs/send-email', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          to, subject: draft.subject, body: draft.body,
          resume_id: resumeId, attach_resume: attachResume,
          job: jobPayload(job),
        }),
      })
      const body = await resp.json()
      if (!resp.ok) throw new Error(body.detail || resp.statusText)
      notify(
        `✉️ Sent to ${to}${body.attachment ? ` with ${body.attachment}` : ''} ✓ — logged in My Applications`,
        'success',
      )
    } catch (err) {
      notify(err.message, 'error')
    } finally {
      setSending(false)
    }
  }

  const copyAll = async () => {
    await navigator.clipboard.writeText(`Subject: ${draft.subject}\n\n${draft.body}`)
    notify('Email copied to clipboard', 'success')
  }

  const mailto = draft
    ? `mailto:${encodeURIComponent(to)}?subject=${encodeURIComponent(draft.subject)}&body=${encodeURIComponent(draft.body)}`
    : '#'

  return (
    <div className="email-tab">
      <div className="email-toolbar">
        <div className="segmented tone-seg">
          {TONES.map((t) => (
            <button key={t.key} className={`seg ${tone === t.key ? 'seg-active' : ''}`}
              onClick={() => { setTone(t.key); generate(t.key, false) }}>{t.label}</button>
          ))}
        </div>
        <button className="btn btn-outline" onClick={() => generate(tone, true)} disabled={loading}>
          🔄 Regenerate
        </button>
      </div>

      {loading && <div className="fit-loading"><Spinner label="Drafting your application email…" /></div>}

      {!loading && draft && (
        <>
          <label className="field-label">To (HR / recruiter email)</label>
          <input className="input" placeholder="hr@company.com" value={to} onChange={(e) => setTo(e.target.value)} />
          <label className="field-label">Subject</label>
          <input className="input" value={draft.subject}
            onChange={(e) => setDraft({ ...draft, subject: e.target.value })} />
          <label className="field-label">Body (editable)</label>
          <textarea className="input textarea email-body" rows={11} value={draft.body}
            onChange={(e) => setDraft({ ...draft, body: e.target.value })} />

          <label className="remote-toggle attach-toggle">
            <input type="checkbox" checked={attachResume} onChange={(e) => setAttachResume(e.target.checked)} />
            📎 Attach my resume as PDF (recommended)
          </label>
          <div className="email-actions">
            <button className="btn btn-primary" onClick={send}
              disabled={sending || !smtp?.configured || !to.includes('@')}
              title={smtp?.configured ? `Sends from ${smtp.sender}` : 'Configure SMTP_* in backend/.env to enable direct sending'}>
              {sending ? 'Sending…' : smtp?.configured ? `📤 Send from ${smtp.sender}` : '📤 Send (SMTP not set up)'}
            </button>
            <a className="btn btn-outline" href={mailto}>Open in mail app</a>
            <button className="btn btn-outline" onClick={copyAll}>⧉ Copy</button>
            <button className="btn btn-ghost" onClick={() => setShowTips(!showTips)}>
              💡 {showTips ? 'Hide tips' : 'How to email HR'}
            </button>
          </div>
          {!smtp?.configured && (
            <p className="muted small">
              To send directly from the app, add <code>SMTP_HOST / SMTP_USER / SMTP_PASSWORD</code> in{' '}
              <code>backend/.env</code> (Gmail: smtp.gmail.com + an App Password) and restart the backend.
            </p>
          )}
          {showTips && (
            <ul className="trust-reasons email-tips">
              {(draft.tips || []).map((tip, i) => <li key={i}>💡 {tip}</li>)}
            </ul>
          )}
        </>
      )}
    </div>
  )
}
