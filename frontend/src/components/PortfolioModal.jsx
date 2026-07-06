import { useEffect, useState } from 'react'
import { Spinner } from './Loader.jsx'

const ACCENTS = ['', '#33ff66', '#7c5fe8', '#e8505b', '#6d87ff', '#ffe600', '#2a9d8f', '#ff7b2f']

export default function PortfolioModal({ resume, notify, onClose }) {
  const [designs, setDesigns] = useState(null)
  const [selected, setSelected] = useState('bento')
  const [accent, setAccent] = useState('')
  const [frameLoading, setFrameLoading] = useState(true)
  const [src, setSrc] = useState('')
  const [downloading, setDownloading] = useState(false)

  useEffect(() => {
    fetch('/api/portfolio/designs').then((r) => r.json()).then(setDesigns).catch(() => setDesigns([]))
  }, [])

  useEffect(() => {
    setFrameLoading(true)
    const params = new URLSearchParams({ design: selected, accent })
    const timer = setTimeout(() => {
      setSrc(`/api/resumes/${resume.id}/portfolio/preview?${params}&_=${Date.now()}`)
    }, 250)
    return () => clearTimeout(timer)
  }, [resume.id, selected, accent])

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const download = async () => {
    setDownloading(true)
    try {
      const params = new URLSearchParams({ design: selected, accent })
      const resp = await fetch(`/api/resumes/${resume.id}/portfolio/download?${params}`)
      if (!resp.ok) throw new Error((await resp.json()).detail || resp.statusText)
      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `portfolio-${selected}.html`
      a.click()
      URL.revokeObjectURL(url)
      notify(`🌐 Portfolio downloaded — also saved in backend/generated/portfolios/. Double-click the file to run it anytime.`, 'success')
    } catch (err) {
      notify(err.message, 'error')
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal portfolio-modal glass-strong" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div>
            <h3>🌐 Build your portfolio website</h3>
            <p className="muted small">One self-contained file — works offline, host it whenever you're ready.</p>
          </div>
          <button className="btn btn-ghost" onClick={onClose}>✕</button>
        </div>
        <div className="portfolio-body">
          <aside className="design-list">
            {designs === null && <Spinner label="Loading designs…" />}
            {designs?.map((d) => (
              <button
                key={d.id}
                className={`design-card ${selected === d.id ? 'design-active' : ''}`}
                onClick={() => setSelected(d.id)}
              >
                <span className="design-emoji">{d.emoji}</span>
                <span>
                  <b>{d.name}</b>
                  <small>{d.tagline}</small>
                </span>
              </button>
            ))}
            <label className="field-label">Accent color</label>
            <div className="color-row">
              {ACCENTS.map((c) => (
                <button
                  key={c || 'default'}
                  className={`color-dot ${accent === c ? 'dot-active' : ''}`}
                  style={{ background: c || 'conic-gradient(#e8505b,#f9a828,#2f9e57,#1d6fc4,#7c4dbd,#e8505b)' }}
                  title={c || "design's signature color"}
                  onClick={() => setAccent(c)}
                />
              ))}
              <input
                type="color"
                className="color-input-native"
                value={accent || '#7c5fe8'}
                onChange={(e) => setAccent(e.target.value)}
                title="Custom color"
              />
            </div>
            <button className="btn btn-primary btn-block" onClick={download} disabled={downloading}>
              {downloading ? 'Building…' : '⬇ Download portfolio.html'}
            </button>
            <p className="muted small">
              Tip: interactions are live in this preview — scroll it, click projects,
              try the terminal's <code>help</code> command.
            </p>
          </aside>
          <div className="frame-wrap portfolio-frame-wrap">
            {frameLoading && <Spinner label="Rendering your portfolio…" />}
            {src && (
              <iframe
                title="portfolio preview"
                src={src}
                className={`preview-frame ${frameLoading ? '' : 'visible'}`}
                onLoad={() => setFrameLoading(false)}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
