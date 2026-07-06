import { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import { Spinner } from './Loader.jsx'

const ACCEPT = '.pdf,.docx,.png,.jpg,.jpeg'

export default function StartStep({ onResumeLoaded, notify }) {
  const [dragOver, setDragOver] = useState(false)
  const [progress, setProgress] = useState(null)
  const [extracting, setExtracting] = useState(false)
  const [title, setTitle] = useState('')
  const [existing, setExisting] = useState(null)
  const inputRef = useRef(null)

  useEffect(() => {
    api.listResumes().then(setExisting).catch(() => setExisting([]))
  }, [])

  const handleFiles = async (files) => {
    const file = files?.[0]
    if (!file) return
    const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
    if (!ACCEPT.split(',').includes(ext)) {
      notify(`Unsupported file type ${ext}. Use PDF, DOCX, PNG or JPG.`, 'error')
      return
    }
    setProgress(0)
    try {
      const record = await api.uploadResume(file, (pct) => {
        setProgress(pct)
        if (pct >= 100) setExtracting(true)
      })
      notify(`Extracted resume for ${record.data.name || record.title} ✓`, 'success')
      onResumeLoaded(record)
    } catch (err) {
      notify(`Upload failed: ${err.message}`, 'error')
    } finally {
      setProgress(null)
      setExtracting(false)
    }
  }

  const createBlank = async () => {
    try {
      const record = await api.createResume(title.trim() || 'My Resume')
      notify('Blank resume created — fill in your details', 'success')
      onResumeLoaded(record)
    } catch (err) {
      notify(err.message, 'error')
    }
  }

  return (
    <>
    <div className="hero">
      <img src="/logo.png" alt="ResuMate mascot at his desk" className="hero-logo" />
      <h2 className="hero-title">Meet your resume mate.</h2>
      <p className="hero-sub muted">
        Upload your old resume or start fresh — AI reads it, polishes it, and exports a
        beautiful, ATS-ready resume in any format.
      </p>
    </div>
    <div className="start-grid">
      <section className="glass panel-pad start-card">
        <h2 className="panel-title">📤 Upload your resume</h2>
        <p className="muted">We'll read it with AI and extract everything automatically.</p>
        <div
          className={`dropzone ${dragOver ? 'dropzone-active' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => { e.preventDefault(); setDragOver(false); handleFiles(e.dataTransfer.files) }}
          onClick={() => progress === null && inputRef.current?.click()}
          role="button"
          tabIndex={0}
        >
          <input ref={inputRef} type="file" accept={ACCEPT} hidden onChange={(e) => handleFiles(e.target.files)} />
          {progress === null ? (
            <>
              <div className="dropzone-icon">⇪</div>
              <p><strong>Drag &amp; drop</strong> or click to browse</p>
              <p className="muted small">PDF · DOCX · PNG · JPG · JPEG</p>
            </>
          ) : extracting ? (
            <Spinner label="AI is reading your resume…" />
          ) : (
            <div className="progress-wrap">
              <div className="progress-track"><div className="progress-fill" style={{ width: `${progress}%` }} /></div>
              <p className="muted">Uploading {progress}%</p>
            </div>
          )}
        </div>
      </section>

      <section className="glass panel-pad start-card">
        <h2 className="panel-title">✨ Start from scratch</h2>
        <p className="muted">Build a brand-new resume step by step with AI help.</p>
        <input
          className="input"
          placeholder="Resume name (e.g. “Software Engineer 2026”)"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && createBlank()}
        />
        <button className="btn btn-primary btn-block" onClick={createBlank}>+ Create resume</button>

        {existing === null ? (
          <Spinner label="Loading your resumes…" />
        ) : existing.length > 0 && (
          <div className="existing-list">
            <h3 className="panel-subtitle">Or continue where you left off</h3>
            {existing.slice(0, 5).map((r) => (
              <button key={r.id} className="existing-item" onClick={() => onResumeLoaded(r)}>
                <span>
                  <strong>{r.title}</strong>
                  <span className="muted small"> · {r.data.name || 'unnamed'}</span>
                </span>
                <span className="muted small">{new Date(r.updated_at).toLocaleDateString()}</span>
              </button>
            ))}
          </div>
        )}
      </section>
    </div>
    </>
  )
}
