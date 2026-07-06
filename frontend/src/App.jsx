import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api.js'
import Header from './components/Header.jsx'
import Stepper from './components/Stepper.jsx'
import StartStep from './components/StartStep.jsx'
import DetailsStep from './components/DetailsStep.jsx'
import TemplateStep from './components/TemplateStep.jsx'
import CustomizeStep from './components/CustomizeStep.jsx'
import PreviewStep from './components/PreviewStep.jsx'
import HistoryDrawer from './components/HistoryDrawer.jsx'
import JobSearch from './components/JobSearch.jsx'
import Toast from './components/Toast.jsx'

export const STEPS = [
  { key: 'start', label: 'Start', icon: '⇪' },
  { key: 'details', label: 'Your Details', icon: '✎' },
  { key: 'template', label: 'Template', icon: '▦' },
  { key: 'customize', label: 'Customize', icon: '✦' },
  { key: 'preview', label: 'Preview & Export', icon: '👁' },
]

const EMPTY_TWEAKS = { color: '', font: '', columns: '', spacing: '', header: '', experience: '', monogram: '', pages: '', photo: '', extra: '' }

export function buildTemplateInstructions(tweaks) {
  const lines = []
  if (tweaks.color) lines.push(`make colors ${tweaks.color}`)
  if (tweaks.font === 'serif') lines.push('make it serif')
  if (tweaks.font === 'sans') lines.push('make it sans')
  if (tweaks.columns === '2') lines.push('use two columns')
  if (tweaks.columns === '1') lines.push('use one column')
  if (tweaks.spacing === 'compact') lines.push('make compact')
  if (tweaks.spacing === 'relaxed') lines.push('increase spacing')
  if (tweaks.header === 'centered') lines.push('centered header')
  if (tweaks.header === 'banner') lines.push('banner header')
  if (tweaks.header === 'split') lines.push('split header')
  if (tweaks.experience === 'timeline') lines.push('timeline experience')
  if (tweaks.monogram === 'on') lines.push('add a monogram badge')
  if (tweaks.pages === 'one') lines.push('one page layout')
  if (tweaks.pages === 'two') lines.push('two page layout')
  if (tweaks.photo === 'show') lines.push('show my photo')
  if (tweaks.photo === 'hide') lines.push('hide the photo')
  if (tweaks.extra.trim()) lines.push(tweaks.extra.trim())
  return lines.join('\n')
}

export default function App() {
  const [theme, setTheme] = useState(() => localStorage.getItem('rb-theme') || 'dark')
  const [mode, setMode] = useState(() => localStorage.getItem('rb-mode') || 'builder')
  const [step, setStep] = useState(0)
  const [resume, setResume] = useState(null)
  const [templates, setTemplates] = useState(null) // null = loading
  const [selectedTemplateId, setSelectedTemplateId] = useState('')
  const [tweaks, setTweaks] = useState(EMPTY_TWEAKS)
  const [scores, setScores] = useState(null)
  const [busy, setBusy] = useState('')
  const [toast, setToast] = useState(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [health, setHealth] = useState(null)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('rb-theme', theme)
  }, [theme])

  useEffect(() => {
    localStorage.setItem('rb-mode', mode)
    document.documentElement.dataset.product = mode === 'jobs' ? 'jobs' : 'resume'
  }, [mode])

  // tweaks are stored per resume, so one resume's layout choices (like a
  // 1-page PDF) never leak into another's exports
  const tweaksLoadedFor = useRef(null)
  useEffect(() => {
    if (!resume?.id) return
    try {
      const saved = localStorage.getItem(`rb-tweaks:${resume.id}`)
        ?? localStorage.getItem('rb-tweaks')  // legacy global key
      setTweaks({ ...EMPTY_TWEAKS, ...JSON.parse(saved || '{}') })
    } catch { setTweaks(EMPTY_TWEAKS) }
    tweaksLoadedFor.current = resume.id
  }, [resume?.id])

  useEffect(() => {
    if (resume?.id && tweaksLoadedFor.current === resume.id) {
      localStorage.setItem(`rb-tweaks:${resume.id}`, JSON.stringify(tweaks))
    }
  }, [tweaks, resume?.id])

  const notify = useCallback((message, kind = 'info') => {
    setToast({ message, kind, id: Date.now() })
  }, [])

  const templateInstructions = useMemo(() => buildTemplateInstructions(tweaks), [tweaks])

  const loadTemplates = useCallback(async () => {
    try {
      setTemplates(await api.listTemplates())
    } catch (err) {
      setTemplates([])
      notify(`Could not load templates: ${err.message}`, 'error')
    }
  }, [notify])

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth({ status: 'offline' }))
    loadTemplates()
  }, [loadTemplates])

  const refreshScores = useCallback(async (resumeId) => {
    try { setScores(await api.scores(resumeId)) } catch { setScores(null) }
  }, [])

  const handleResumeLoaded = useCallback((record, advance = true) => {
    setResume(record)
    if (record.selected_template_id) setSelectedTemplateId(record.selected_template_id)
    refreshScores(record.id)
    if (advance) setStep(1)
  }, [refreshScores])

  const saveResumeData = useCallback(async (data, saveVersion = false, note = '') => {
    if (!resume) return null
    try {
      const updated = await api.updateResume(resume.id, data, saveVersion, note)
      setResume(updated)
      refreshScores(updated.id)
      if (saveVersion) notify('Version saved', 'success')
      return updated
    } catch (err) {
      notify(`Save failed: ${err.message}`, 'error')
      return null
    }
  }, [resume, notify, refreshScores])

  const selectTemplate = useCallback(async (templateId, advance = false) => {
    setSelectedTemplateId(templateId)
    if (resume) {
      try {
        const updated = await api.selectTemplate(resume.id, templateId)
        setResume(updated)
        notify('Template selected ✓', 'success')
      } catch (err) {
        notify(err.message, 'error')
        return
      }
    }
    if (advance) setStep(3)
  }, [resume, notify])

  const applyResumeEdits = useCallback(async (instructions) => {
    if (!resume || !instructions.trim()) return null
    setBusy('AI is editing your resume…')
    try {
      const result = await api.editResume(resume.id, instructions)
      setResume(result.resume)
      if (result.scores) setScores(result.scores)
      notify(`Edits applied: ${(result.applied || []).join(' · ') || 'done'}`, 'success')
      return result
    } catch (err) {
      notify(`Edit failed: ${err.message}`, 'error')
      return null
    } finally {
      setBusy('')
    }
  }, [resume, notify])

  const generate = useCallback(async (formats) => {
    if (!resume) return null
    setBusy(`Generating ${formats.join(', ').toUpperCase()}…`)
    try {
      const result = await api.generate(resume.id, {
        template_id: selectedTemplateId,
        template_instructions: templateInstructions,
        formats,
      })
      const updated = await api.getResume(resume.id)
      setResume(updated)
      return result
    } catch (err) {
      notify(`Generation failed: ${err.message}`, 'error')
      return null
    } finally {
      setBusy('')
    }
  }, [resume, selectedTemplateId, templateInstructions, notify])

  const download = useCallback(async (fmt) => {
    const result = await generate([fmt])
    if (result?.files?.[fmt]) {
      window.open(api.downloadUrl(resume.id, fmt), '_blank')
      notify(`${fmt.toUpperCase()} ready`, 'success')
    } else if (result) {
      notify(`Could not produce ${fmt.toUpperCase()}: ${result.errors?.[fmt] || 'unknown error'}`, 'error')
    }
  }, [generate, resume, notify])

  const restoreVersion = useCallback(async (version) => {
    if (!resume) return
    try {
      const restored = await api.restoreVersion(resume.id, version)
      setResume(restored)
      refreshScores(restored.id)
      notify(`Restored version ${version}`, 'success')
    } catch (err) {
      notify(err.message, 'error')
    }
  }, [resume, notify, refreshScores])

  const maxStep = resume ? (selectedTemplateId ? 4 : 2) : 0

  return (
    <div className="app">
      <div className="bg-glow" aria-hidden="true" />
      <Header
        theme={theme}
        onToggleTheme={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
        health={health}
        mode={mode}
        onModeChange={setMode}
      />
      {mode === 'jobs' ? (
        <main className="stage">
          <JobSearch notify={notify} />
        </main>
      ) : (
      <>
      <Stepper steps={STEPS} current={step} maxReachable={maxStep} onGo={setStep} />
      <main className="stage">
        {step === 0 && (
          <StartStep onResumeLoaded={handleResumeLoaded} notify={notify} />
        )}
        {step === 1 && resume && (
          <DetailsStep
            resume={resume}
            scores={scores}
            onSave={saveResumeData}
            onNext={() => setStep(2)}
            notify={notify}
          />
        )}
        {step === 2 && (
          <TemplateStep
            templates={templates}
            selectedId={selectedTemplateId}
            onSelect={selectTemplate}
            onReload={loadTemplates}
            onNext={() => setStep(3)}
            notify={notify}
          />
        )}
        {step === 3 && resume && (
          <CustomizeStep
            resume={resume}
            templateId={selectedTemplateId}
            tweaks={tweaks}
            setTweaks={setTweaks}
            templateInstructions={templateInstructions}
            onApplyResumeEdits={applyResumeEdits}
            onNext={() => setStep(4)}
            busy={!!busy}
          />
        )}
        {step === 4 && resume && (
          <PreviewStep
            resume={resume}
            templateId={selectedTemplateId}
            templateInstructions={templateInstructions}
            onDownload={download}
            onSaveVersion={() => saveResumeData(resume.data, true, 'Manual save')}
            onHistory={() => setHistoryOpen(true)}
            busy={!!busy}
            notify={notify}
          />
        )}
        {step > 0 && !resume && (
          <div className="glass panel-pad center-note">
            <p>Start by uploading a resume or creating one from scratch.</p>
            <button className="btn btn-primary" onClick={() => setStep(0)}>← Go to Start</button>
          </div>
        )}
      </main>
      </>
      )}
      {historyOpen && resume && (
        <HistoryDrawer resume={resume} onRestore={restoreVersion} onClose={() => setHistoryOpen(false)} />
      )}
      {toast && <Toast toast={toast} onDone={() => setToast(null)} />}
      {busy && (
        <div className="busy-overlay">
          <div className="spinner" />
          <p>{busy}</p>
        </div>
      )}
    </div>
  )
}
