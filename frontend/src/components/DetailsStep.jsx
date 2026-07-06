import { useEffect, useState } from 'react'

const LIST_SECTIONS = [
  {
    key: 'experience', title: '💼 Work History', itemName: 'role',
    fields: [
      { key: 'title', label: 'Job title' }, { key: 'company', label: 'Company' },
      { key: 'location', label: 'Location' },
      { key: 'start_date', label: 'Start (e.g. Jan 2021)' }, { key: 'end_date', label: 'End (or Present)' },
    ],
    textList: { key: 'bullets', label: 'Achievements — one per line' },
    summary: (it) => [it.title, it.company].filter(Boolean).join(' — ') || 'New role',
    blank: { title: '', company: '', location: '', start_date: '', end_date: '', current: false, bullets: [] },
  },
  {
    key: 'education', title: '🎓 Education', itemName: 'entry',
    fields: [
      { key: 'degree', label: 'Degree' }, { key: 'institution', label: 'Institution' },
      { key: 'location', label: 'Location' },
      { key: 'start_date', label: 'Start year' }, { key: 'end_date', label: 'End year' },
      { key: 'gpa', label: 'GPA (optional)' },
    ],
    textList: { key: 'details', label: 'Highlights — one per line (optional)' },
    summary: (it) => [it.degree, it.institution].filter(Boolean).join(' — ') || 'New entry',
    blank: { degree: '', institution: '', location: '', start_date: '', end_date: '', gpa: '', details: [] },
  },
  {
    key: 'projects', title: '🛠 Projects', itemName: 'project',
    fields: [
      { key: 'name', label: 'Project name' }, { key: 'link', label: 'Link (optional)' },
      { key: 'description', label: 'Short description', wide: true },
    ],
    csvList: { key: 'technologies', label: 'Technologies (comma-separated)' },
    textList: { key: 'bullets', label: 'Details — one per line (optional)' },
    summary: (it) => it.name || 'New project',
    blank: { name: '', description: '', technologies: [], link: '', bullets: [] },
  },
  {
    key: 'certifications', title: '📜 Certifications', itemName: 'certification',
    fields: [
      { key: 'name', label: 'Certification' }, { key: 'issuer', label: 'Issuer' },
      { key: 'date', label: 'Date' }, { key: 'link', label: 'Link (optional)' },
    ],
    summary: (it) => it.name || 'New certification',
    blank: { name: '', issuer: '', date: '', link: '' },
  },
  {
    key: 'languages', title: '🌐 Languages', itemName: 'language',
    fields: [
      { key: 'name', label: 'Language' }, { key: 'proficiency', label: 'Proficiency (e.g. Fluent)' },
    ],
    summary: (it) => it.name || 'New language',
    blank: { name: '', proficiency: '' },
  },
  {
    key: 'awards', title: '🏆 Awards', itemName: 'award',
    fields: [
      { key: 'title', label: 'Award' }, { key: 'issuer', label: 'Issuer' },
      { key: 'date', label: 'Date' }, { key: 'description', label: 'Description', wide: true },
    ],
    summary: (it) => it.title || 'New award',
    blank: { title: '', issuer: '', date: '', description: '' },
  },
]

export default function DetailsStep({ resume, scores, onSave, onNext, notify }) {
  const [data, setData] = useState(resume.data)
  const [dirty, setDirty] = useState(false)
  const [showJson, setShowJson] = useState(false)
  const [jsonText, setJsonText] = useState('')
  const [open, setOpen] = useState('personal')

  useEffect(() => {
    setData(resume.data)
    setDirty(false)
  }, [resume.id])

  const patch = (partial) => {
    setData((d) => ({ ...d, ...partial }))
    setDirty(true)
  }

  const save = async () => {
    const saved = await onSave(data)
    if (saved) setDirty(false)
    return saved
  }

  const saveAndNext = async () => {
    if (dirty) {
      const saved = await save()
      if (!saved) return
    }
    onNext()
  }

  const toggle = (key) => setOpen(open === key ? '' : key)

  return (
    <div className="details-grid">
      <div className="details-main">
        <Section title="👤 Personal Details" open={open === 'personal'} onToggle={() => toggle('personal')}>
          <div className="form-grid">
            <Field label="Full name" value={data.name} onChange={(v) => patch({ name: v })} />
            <Field label="Headline (e.g. Senior Software Engineer)" value={data.headline} onChange={(v) => patch({ headline: v })} />
            <Field label="Email" value={data.email} onChange={(v) => patch({ email: v })} />
            <Field label="Phone" value={data.phone} onChange={(v) => patch({ phone: v })} />
            <Field label="Location" value={data.location} onChange={(v) => patch({ location: v })} />
            <Field label="LinkedIn" value={data.links?.linkedin || ''} onChange={(v) => patch({ links: { ...data.links, linkedin: v } })} />
            <Field label="GitHub" value={data.links?.github || ''} onChange={(v) => patch({ links: { ...data.links, github: v } })} />
            <Field label="Website" value={data.links?.website || ''} onChange={(v) => patch({ links: { ...data.links, website: v } })} />
          </div>
          <label className="field-label">Professional summary</label>
          <textarea
            className="input textarea" rows={3}
            placeholder="2–3 sentences that sell you. The AI can rewrite this later."
            value={data.summary}
            onChange={(e) => patch({ summary: e.target.value })}
          />
        </Section>

        <Section title="⚡ Skills" open={open === 'skills'} onToggle={() => toggle('skills')}>
          {(data.skills || []).map((group, i) => (
            <div key={i} className="skill-row">
              <input
                className="input skill-cat-input" placeholder="Category (e.g. Languages)"
                value={group.category}
                onChange={(e) => {
                  const skills = [...data.skills]
                  skills[i] = { ...skills[i], category: e.target.value }
                  patch({ skills })
                }}
              />
              <input
                className="input" placeholder="Skills, comma-separated (e.g. Python, React, SQL)"
                value={(group.skills || []).join(', ')}
                onChange={(e) => {
                  const skills = [...data.skills]
                  skills[i] = { ...skills[i], skills: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) }
                  patch({ skills })
                }}
              />
              <button className="btn btn-ghost btn-small" title="Remove group"
                onClick={() => patch({ skills: data.skills.filter((_, j) => j !== i) })}>✕</button>
            </div>
          ))}
          <button className="btn btn-outline btn-small"
            onClick={() => patch({ skills: [...(data.skills || []), { category: '', skills: [] }] })}>
            + Add skill group
          </button>
        </Section>

        {LIST_SECTIONS.map((cfg) => (
          <ListSection
            key={cfg.key} cfg={cfg}
            items={data[cfg.key] || []}
            open={open === cfg.key}
            onToggle={() => toggle(cfg.key)}
            onChange={(items) => patch({ [cfg.key]: items })}
          />
        ))}

        <Section title="⚙ Advanced (raw JSON)" open={showJson} onToggle={() => {
          setShowJson(!showJson)
          if (!showJson) setJsonText(JSON.stringify(data, null, 2))
        }}>
          <textarea className="input textarea code" rows={14} spellCheck={false}
            value={jsonText} onChange={(e) => setJsonText(e.target.value)} />
          <button className="btn btn-outline btn-small" onClick={() => {
            try {
              setData(JSON.parse(jsonText)); setDirty(true); notify('JSON applied to the form', 'success')
            } catch (err) { notify(`Invalid JSON: ${err.message}`, 'error') }
          }}>Apply JSON</button>
        </Section>
      </div>

      <aside className="details-side">
        {scores && (
          <div className="glass panel-pad">
            <h3 className="panel-title">📊 Resume Health</h3>
            <ScoreMeter label="Overall" value={scores.resume_score} />
            <ScoreMeter label="ATS" value={scores.ats_score} />
            <ScoreMeter label="Grammar" value={scores.grammar_score} />
            {scores.recommendations?.length > 0 && (
              <ul className="recs-list">
                {scores.recommendations.slice(0, 4).map((rec, i) => <li key={i}>{rec}</li>)}
              </ul>
            )}
          </div>
        )}
        <div className="glass panel-pad sticky-actions">
          <button className="btn btn-outline btn-block" onClick={save} disabled={!dirty}>
            {dirty ? '💾 Save changes' : '✓ Saved'}
          </button>
          <button className="btn btn-primary btn-block" onClick={saveAndNext}>
            Choose a template →
          </button>
        </div>
      </aside>
    </div>
  )
}

function Section({ title, open, onToggle, children }) {
  return (
    <section className={`glass form-section ${open ? 'open' : ''}`}>
      <button className="section-head" onClick={onToggle}>
        <span>{title}</span>
        <span className="chev">{open ? '▾' : '▸'}</span>
      </button>
      {open && <div className="section-body">{children}</div>}
    </section>
  )
}

function Field({ label, value, onChange }) {
  return (
    <div className="field">
      <label className="field-label">{label}</label>
      <input className="input" value={value || ''} onChange={(e) => onChange(e.target.value)} />
    </div>
  )
}

function ListSection({ cfg, items, open, onToggle, onChange }) {
  const update = (i, partial) => {
    const next = [...items]
    next[i] = { ...next[i], ...partial }
    onChange(next)
  }
  return (
    <Section title={`${cfg.title} (${items.length})`} open={open} onToggle={onToggle}>
      {items.map((item, i) => (
        <details key={i} className="list-item" open={items.length <= 2}>
          <summary>
            <span>{cfg.summary(item)}</span>
            <span className="item-actions">
              {i > 0 && <button className="mini-btn" title="Move up" onClick={(e) => {
                e.preventDefault()
                const next = [...items]; [next[i - 1], next[i]] = [next[i], next[i - 1]]; onChange(next)
              }}>↑</button>}
              <button className="mini-btn danger" title="Remove" onClick={(e) => {
                e.preventDefault(); onChange(items.filter((_, j) => j !== i))
              }}>✕</button>
            </span>
          </summary>
          <div className="form-grid">
            {cfg.fields.map((f) => (
              <div className={`field ${f.wide ? 'wide' : ''}`} key={f.key}>
                <label className="field-label">{f.label}</label>
                <input className="input" value={item[f.key] || ''} onChange={(e) => update(i, { [f.key]: e.target.value })} />
              </div>
            ))}
          </div>
          {cfg.csvList && (
            <>
              <label className="field-label">{cfg.csvList.label}</label>
              <input className="input"
                value={(item[cfg.csvList.key] || []).join(', ')}
                onChange={(e) => update(i, { [cfg.csvList.key]: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })}
              />
            </>
          )}
          {cfg.textList && (
            <>
              <label className="field-label">{cfg.textList.label}</label>
              <textarea className="input textarea" rows={3}
                value={(item[cfg.textList.key] || []).join('\n')}
                onChange={(e) => update(i, { [cfg.textList.key]: e.target.value.split('\n') })}
                onBlur={(e) => update(i, { [cfg.textList.key]: e.target.value.split('\n').map((s) => s.trim()).filter(Boolean) })}
              />
            </>
          )}
        </details>
      ))}
      <button className="btn btn-outline btn-small" onClick={() => onChange([...items, { ...cfg.blank }])}>
        + Add {cfg.itemName}
      </button>
    </Section>
  )
}

function ScoreMeter({ label, value }) {
  const hue = Math.round((value / 100) * 120)
  return (
    <div className="meter">
      <span className="meter-label">{label}</span>
      <div className="meter-track">
        <div className="meter-fill" style={{ width: `${value}%`, background: `hsl(${hue} 65% 45%)` }} />
      </div>
      <span className="meter-value">{value}</span>
    </div>
  )
}
