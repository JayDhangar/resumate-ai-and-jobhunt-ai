export default function Header({ theme, onToggleTheme, health, mode, onModeChange }) {
  const llmBadge = health?.llm_available
    ? `AI: ${health.llm_provider}`
    : health?.status === 'ok' ? 'AI: offline mode' : 'backend offline'
  const isJobs = mode === 'jobs'
  return (
    <header className="header">
      <div className="brand">
        <span className="brand-logo-wrap">
          <img src="/logo.png" alt="mascot" className="brand-logo" />
        </span>
        <div className="brand-text">
          {isJobs ? (
            <h1>Job<span className="accent">Hunt</span> <span className="ai-tag">AI</span></h1>
          ) : (
            <h1>Resu<span className="accent">Mate</span> <span className="ai-tag">AI</span></h1>
          )}
          <span className="tagline">
            {isJobs
              ? 'hunt smarter — real jobs · scam-checked · direct apply links'
              : 'your resume mate — build · polish · get hired'}
          </span>
        </div>
      </div>
      <div className="mode-toggle" role="tablist" aria-label="Product">
        <button
          className={`mode-pill ${!isJobs ? 'mode-active' : ''}`}
          onClick={() => onModeChange('builder')}
          role="tab" aria-selected={!isJobs}
        >
          📄 ResuMate
        </button>
        <button
          className={`mode-pill ${isJobs ? 'mode-active' : ''}`}
          onClick={() => onModeChange('jobs')}
          role="tab" aria-selected={isJobs}
        >
          💼 JobHunt
        </button>
      </div>
      <div className="header-right">
        <span className={`badge ${health?.llm_available ? 'badge-ok' : 'badge-warn'}`}>{llmBadge}</span>
        <button className="btn btn-ghost" onClick={onToggleTheme} title="Toggle theme">
          {theme === 'dark' ? '☀ Light' : '☾ Dark'}
        </button>
      </div>
    </header>
  )
}
