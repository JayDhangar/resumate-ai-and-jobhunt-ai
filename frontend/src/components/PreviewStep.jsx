import { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import { Spinner } from './Loader.jsx'

const FORMATS = [
  { fmt: 'pdf', label: 'PDF' }, { fmt: 'docx', label: 'DOCX' },
  { fmt: 'html', label: 'HTML' }, { fmt: 'png', label: 'PNG' },
  { fmt: 'md', label: 'Markdown' }, { fmt: 'json', label: 'JSON' },
]

export default function PreviewStep({
  resume, templateId, templateInstructions,
  onDownload, onSaveVersion, onHistory, busy,
}) {
  const frameRef = useRef(null)
  const [loading, setLoading] = useState(true)
  const [editable, setEditable] = useState(false)
  const [src, setSrc] = useState('')

  useEffect(() => {
    setLoading(true)
    setSrc(api.previewUrl(resume.id, templateId, templateInstructions) + `&_=${Date.now()}`)
  }, [resume, templateId, templateInstructions])

  useEffect(() => {
    const frame = frameRef.current
    if (!frame) return
    try { frame.contentDocument.designMode = editable ? 'on' : 'off' } catch { /* same-origin via proxy */ }
  }, [editable, loading])

  const execute = (command) => {
    try { frameRef.current?.contentDocument?.execCommand(command) } catch { /* noop */ }
  }

  return (
    <div className="preview-step">
      <div className="glass panel-pad preview-toolbar">
        <div className="toolbar-group">
          <button className={`btn ${editable ? 'btn-primary' : 'btn-outline'}`} onClick={() => setEditable(!editable)}>
            ✎ {editable ? 'Editing on' : 'Edit text'}
          </button>
          <button className="btn btn-ghost" onClick={() => execute('undo')} disabled={!editable}>↺ Undo</button>
          <button className="btn btn-ghost" onClick={() => execute('redo')} disabled={!editable}>↻ Redo</button>
        </div>
        <div className="toolbar-group">
          {FORMATS.map(({ fmt, label }) => (
            <button key={fmt} className="btn btn-outline" disabled={busy} onClick={() => onDownload(fmt)}>
              ⬇ {label}
            </button>
          ))}
        </div>
        <div className="toolbar-group">
          <button className="btn btn-outline" disabled={busy} onClick={onSaveVersion}>💾 Save version</button>
          <button className="btn btn-ghost" onClick={onHistory}>🕘 History</button>
        </div>
      </div>
      {editable && (
        <p className="muted small note-line">
          In-place edits are visual only — persistent content changes belong in “Your Details” or AI edits.
        </p>
      )}
      <div className="glass preview-stage">
        <div className="frame-wrap paper tall">
          {loading && <Spinner label="Rendering your resume…" />}
          {src && (
            <iframe
              ref={frameRef}
              title="resume preview"
              src={src}
              className={`preview-frame ${loading ? '' : 'visible'}`}
              onLoad={() => setLoading(false)}
            />
          )}
        </div>
      </div>
    </div>
  )
}
