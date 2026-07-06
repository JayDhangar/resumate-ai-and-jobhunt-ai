import { useMemo, useRef, useState } from 'react'
import { api } from '../api.js'
import { SkeletonCards, Spinner } from './Loader.jsx'

const STYLES = ['', 'modern', 'ats', 'minimal', 'creative', 'corporate', 'executive', 'professional', 'custom']

export default function TemplateStep({ templates, selectedId, onSelect, onReload, onNext, notify }) {
  const [tab, setTab] = useState('web')
  const [query, setQuery] = useState('')
  const [style, setStyle] = useState('')
  const [sort, setSort] = useState('popularity')
  const [uploading, setUploading] = useState(false)
  const [previewTpl, setPreviewTpl] = useState(null)
  const fileRef = useRef(null)

  const loading = templates === null
  const visible = useMemo(() => {
    if (!templates) return []
    let list = templates.filter((t) => {
      if (tab === 'mine') return t.source === 'uploaded'
      if (tab === 'saved') return t.saved
      return t.source !== 'uploaded'
    })
    if (style) list = list.filter((t) => t.style === style)
    if (query) {
      const q = query.toLowerCase()
      list = list.filter((t) =>
        t.name.toLowerCase().includes(q) ||
        (t.description || '').toLowerCase().includes(q) ||
        (t.tags || []).some((tag) => tag.includes(q)))
    }
    const sorters = {
      popularity: (a, b) => b.popularity - a.popularity,
      ats: (a, b) => b.ats_score - a.ats_score,
      name: (a, b) => a.name.localeCompare(b.name),
    }
    return [...list].sort(sorters[sort] || sorters.popularity)
  }, [templates, tab, query, style, sort])

  const toggleSave = async (t) => {
    try {
      const result = await api.toggleSaveTemplate(t.id)
      await onReload()
      notify(result.saved
        ? `⭐ "${t.name}" saved — it will survive template refreshes`
        : `"${t.name}" unsaved — it may be replaced on the next refresh`, 'success')
    } catch (err) {
      notify(err.message, 'error')
    }
  }

  const handleAddTemplate = async (files) => {
    const file = files?.[0]
    if (!file) return
    setUploading(true)
    try {
      await api.uploadTemplate(file, '')
      await onReload()
      setTab('mine')
      notify(`Template "${file.name}" analysed and added to My Templates ✓`, 'success')
    } catch (err) {
      notify(`Template upload failed: ${err.message}`, 'error')
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  return (
    <div className="template-step">
      <div className="glass panel-pad gallery-bar">
        <div className="tabs">
          <button className={`tab ${tab === 'web' ? 'tab-active' : ''}`} onClick={() => setTab('web')}>Web Templates</button>
          <button className={`tab ${tab === 'saved' ? 'tab-active' : ''}`} onClick={() => setTab('saved')}>⭐ Saved</button>
          <button className={`tab ${tab === 'mine' ? 'tab-active' : ''}`} onClick={() => setTab('mine')}>My Templates</button>
        </div>
        <input className="input search-input" placeholder="🔍 Search templates…" value={query} onChange={(e) => setQuery(e.target.value)} />
        <select className="input select" value={style} onChange={(e) => setStyle(e.target.value)}>
          {STYLES.map((s) => <option key={s} value={s}>{s ? s[0].toUpperCase() + s.slice(1) : 'All styles'}</option>)}
        </select>
        <select className="input select" value={sort} onChange={(e) => setSort(e.target.value)}>
          <option value="popularity">Popular</option>
          <option value="ats">ATS score</option>
          <option value="name">Name</option>
        </select>
        <button className="btn btn-primary" onClick={() => fileRef.current?.click()} disabled={uploading}>
          {uploading ? 'Analysing…' : '+ Add Template'}
        </button>
        <input ref={fileRef} type="file" hidden accept=".pdf,.docx,.png,.jpg,.jpeg" onChange={(e) => handleAddTemplate(e.target.files)} />
      </div>

      <div className="tcards">
        {loading && <SkeletonCards count={10} />}
        {!loading && visible.length === 0 && (
          <p className="muted empty">
            {tab === 'mine'
              ? 'No uploaded templates yet — click “+ Add Template” to upload a PDF, DOCX or image.'
              : 'No templates match your filters.'}
          </p>
        )}
        {!loading && visible.map((t) => (
          <div key={t.id} className={`tcard glass ${selectedId === t.id ? 'tcard-selected' : ''}`}>
            {selectedId === t.id && <span className="selected-badge">✓ Selected</span>}
            {t.source !== 'uploaded' && (
              <button
                className={`save-star ${t.saved ? 'saved' : ''}`}
                title={t.saved ? 'Saved — persists across refreshes. Click to unsave.' : 'Save to keep this template permanently'}
                onClick={() => toggleSave(t)}
              >{t.saved ? '★' : '☆'}</button>
            )}
            <div className="tcard-preview">
              <PreviewImg template={t} />
              <div className="tcard-overlay">
                <button className="btn btn-glass" onClick={() => setPreviewTpl(t)}>👁 Preview</button>
                <button className="btn btn-primary" onClick={() => onSelect(t.id, true)}>Use template →</button>
              </div>
            </div>
            <div className="tcard-body">
              <div className="tcard-title-row">
                <h3>{t.name}</h3>
                <span className="ats-chip" title="ATS-friendliness score">ATS {t.ats_score}</span>
              </div>
              <div className="tcard-meta">
                <span className="swatches">
                  {[t.colors?.primary, t.colors?.accent].map((c, i) => c ? <span key={i} className="swatch" style={{ background: c }} /> : null)}
                </span>
                <span className="muted small">{t.style} · {t.layout?.columns === 2 ? '2 col' : '1 col'}</span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {selectedId && (
        <div className="glass panel-pad next-bar">
          <span className="muted">Template selected — ready to customize it with your details.</span>
          <button className="btn btn-primary" onClick={onNext}>Customize →</button>
        </div>
      )}

      {previewTpl && (
        <SamplePreviewModal
          template={previewTpl}
          selected={selectedId === previewTpl.id}
          onUse={() => { onSelect(previewTpl.id, true); setPreviewTpl(null) }}
          onClose={() => setPreviewTpl(null)}
        />
      )}
    </div>
  )
}

function PreviewImg({ template }) {
  const [failed, setFailed] = useState(false)
  if (failed) {
    return (
      <div
        className="preview-fallback"
        style={{ background: `linear-gradient(150deg, ${template.colors?.primary || '#444'}, ${template.colors?.accent || '#777'})` }}
      >
        <span>{(template.name || '?').slice(0, 1).toUpperCase()}</span>
        <small>preview unavailable — is the backend running?</small>
      </div>
    )
  }
  return (
    <img
      src={api.templatePreviewUrl(template.id)}
      alt={template.name}
      loading="lazy"
      onError={() => setFailed(true)}
    />
  )
}

function SamplePreviewModal({ template, selected, onUse, onClose }) {
  const [loaded, setLoaded] = useState(false)
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal sample-modal glass-strong" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div>
            <h3>{template.name}</h3>
            <p className="muted small">{template.description || `${template.style} template`}</p>
          </div>
          <div className="modal-actions">
            <button className="btn btn-primary" onClick={onUse}>
              {selected ? '✓ Selected — continue' : '✓ Use this template'}
            </button>
            <button className="btn btn-ghost" onClick={onClose}>✕</button>
          </div>
        </div>
        <div className="frame-wrap">
          {!loaded && <Spinner label="Rendering sample…" />}
          <iframe
            title={`${template.name} sample`}
            src={api.templateSampleUrl(template.id)}
            className={`sample-frame ${loaded ? 'visible' : ''}`}
            onLoad={() => setLoaded(true)}
          />
        </div>
      </div>
    </div>
  )
}
