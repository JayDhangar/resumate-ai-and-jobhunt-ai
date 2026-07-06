import { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import { Spinner } from './Loader.jsx'

const RAINBOW = 'conic-gradient(#e8505b, #f9a828, #2f9e57, #1d6fc4, #7c4dbd, #e8505b)'
const COLORS = [
  { key: 'blue', hex: '#1d6fc4' }, { key: 'navy', hex: '#122c4f' },
  { key: 'teal', hex: '#2a9d8f' }, { key: 'green', hex: '#2f9e57' },
  { key: 'purple', hex: '#7c4dbd' }, { key: 'red', hex: '#d13f47' },
  { key: 'gold', hex: '#a67c00' }, { key: 'black', hex: '#222222' },
]

const RESUME_HINTS = [
  'Rewrite summary professionally', 'Improve grammar', 'Increase ATS score',
  'Add metrics to bullets', 'Shorten experience', 'Make it sound more senior',
]

export default function CustomizeStep({
  resume, templateId, tweaks, setTweaks, templateInstructions,
  onApplyResumeEdits, onNext, busy,
}) {
  const [aiText, setAiText] = useState('')
  const [frameLoading, setFrameLoading] = useState(true)
  const [previewSrc, setPreviewSrc] = useState('')

  // debounce preview refresh so sliders/typing don't spam the backend
  useEffect(() => {
    setFrameLoading(true)
    const timer = setTimeout(() => {
      setPreviewSrc(api.previewUrl(resume.id, templateId, templateInstructions) + `&_=${Date.now()}`)
    }, 450)
    return () => clearTimeout(timer)
  }, [resume, templateId, templateInstructions])

  const set = (key, value) => setTweaks((t) => ({ ...t, [key]: t[key] === value ? '' : value }))

  const applyAi = async () => {
    const result = await onApplyResumeEdits(aiText)
    if (result) setAiText('')
  }

  return (
    <div className="customize-grid">
      <div className="customize-controls">
        <section className="glass panel-pad">
          <h3 className="panel-title">🎨 Template style</h3>
          <p className="muted small">Each control replaces the previous choice — no stacking.</p>

          <label className="field-label">Accent color</label>
          <ColorRow
            value={tweaks.color}
            onPick={(color) => setTweaks((t) => ({ ...t, color }))}
          />

          <label className="field-label">Font</label>
          <Segmented value={tweaks.font} onPick={(v) => set('font', v)}
            options={[{ v: 'sans', label: 'Sans' }, { v: 'serif', label: 'Serif' }]} />

          <label className="field-label">Columns</label>
          <Segmented value={tweaks.columns} onPick={(v) => set('columns', v)}
            options={[{ v: '1', label: '▍ One' }, { v: '2', label: '▍▍ Two' }]} />

          <label className="field-label">Spacing</label>
          <Segmented value={tweaks.spacing} onPick={(v) => set('spacing', v)}
            options={[{ v: 'compact', label: 'Compact' }, { v: 'relaxed', label: 'Relaxed' }]} />

          <label className="field-label">Header</label>
          <Segmented value={tweaks.header} onPick={(v) => set('header', v)}
            options={[{ v: 'centered', label: 'Centered' }, { v: 'banner', label: 'Banner' }, { v: 'split', label: 'Split' }]} />

          <label className="field-label">Pages</label>
          <Segmented value={tweaks.pages} onPick={(v) => set('pages', v)}
            options={[{ v: 'one', label: '📄 1-page (compact)' }, { v: 'two', label: '📑 2-page (spacious)' }]} />

          <label className="field-label">Photo</label>
          <Segmented value={tweaks.photo} onPick={(v) => set('photo', v)}
            options={[{ v: 'show', label: '🙂 Show photo' }, { v: 'hide', label: 'Hide photo' }]} />
          <p className="muted small">Upload your photo in “Your Details” → Personal — templates render it when shown.</p>

          <label className="field-label">Extras</label>
          <div className="extras-row">
            <button
              className={`seg-toggle ${tweaks.experience === 'timeline' ? 'seg-active' : ''}`}
              onClick={() => set('experience', 'timeline')}
            >⋮ Timeline experience</button>
            <button
              className={`seg-toggle ${tweaks.monogram === 'on' ? 'seg-active' : ''}`}
              onClick={() => set('monogram', 'on')}
            >Ⓜ Monogram badge</button>
          </div>

          <label className="field-label">Anything else (free text)</label>
          <input
            className="input" placeholder='e.g. "hide the section divider lines"'
            value={tweaks.extra}
            onChange={(e) => setTweaks((t) => ({ ...t, extra: e.target.value }))}
          />
          {(tweaks.color || tweaks.font || tweaks.columns || tweaks.spacing || tweaks.header || tweaks.extra) && (
            <button className="btn btn-ghost btn-small" onClick={() =>
              setTweaks({ color: '', font: '', columns: '', spacing: '', header: '', extra: '' })}>
              ↺ Reset styling
            </button>
          )}
        </section>

        <section className="glass panel-pad">
          <h3 className="panel-title">🤖 AI content edits</h3>
          <textarea
            className="input textarea" rows={3}
            placeholder={'e.g. “Rewrite my summary”, “Remove internship”,\n“Replace Python with Golang”'}
            value={aiText}
            onChange={(e) => setAiText(e.target.value)}
          />
          <div className="chips">
            {RESUME_HINTS.map((h) => (
              <button key={h} className={`chip ${aiText === h ? 'chip-active' : ''}`}
                onClick={() => setAiText(aiText === h ? '' : h)}>{h}</button>
            ))}
          </div>
          <button className="btn btn-primary btn-block" onClick={applyAi} disabled={busy || !aiText.trim()}>
            ✦ Apply AI edits
          </button>
        </section>

        <button className="btn btn-primary btn-block btn-lg" onClick={onNext}>
          Looks good — Preview & Export →
        </button>
      </div>

      <div className="glass live-pane">
        <div className="live-pane-head">
          <h3 className="panel-title">Live preview</h3>
          {frameLoading && <span className="mini-spinner" />}
        </div>
        <div className="frame-wrap paper">
          {frameLoading && <Spinner label="Rendering…" />}
          {previewSrc && (
            <iframe
              title="live preview"
              src={previewSrc}
              className={`preview-frame ${frameLoading ? '' : 'visible'}`}
              onLoad={() => setFrameLoading(false)}
            />
          )}
        </div>
      </div>
    </div>
  )
}

function ColorRow({ value, onPick }) {
  const pickerRef = useRef(null)
  const isCustom = value.startsWith('#')
  return (
    <div className="color-row">
      <button
        className={`color-dot dot-reset ${value === '' ? 'dot-active' : ''}`}
        title="Original template colors"
        onClick={() => onPick('')}
      >↺</button>
      {COLORS.map((c) => (
        <button
          key={c.key}
          className={`color-dot ${value === c.key ? 'dot-active' : ''}`}
          style={{ background: c.hex }}
          title={c.key}
          onClick={() => onPick(c.key)}
        />
      ))}
      <button
        className={`color-dot dot-custom ${isCustom ? 'dot-active' : ''}`}
        style={{ background: isCustom ? value : RAINBOW }}
        title="Custom color — opens the full color picker"
        onClick={() => pickerRef.current?.click()}
      >{isCustom ? '' : '+'}</button>
      <input
        ref={pickerRef}
        type="color"
        className="color-input-hidden"
        value={isCustom ? value : '#4f6df5'}
        onChange={(e) => onPick(e.target.value)}
      />
      {isCustom && <span className="muted small custom-hex">{value}</span>}
    </div>
  )
}

function Segmented({ options, value, onPick }) {
  return (
    <div className="segmented">
      {options.map((option) => (
        <button
          key={option.v}
          className={`seg ${value === option.v ? 'seg-active' : ''}`}
          onClick={() => onPick(option.v)}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}
