export default function Stepper({ steps, current, maxReachable, onGo }) {
  return (
    <nav className="stepper" aria-label="Builder steps">
      {steps.map((step, i) => {
        const state = i === current ? 'active' : i < current ? 'done' : ''
        const reachable = i <= maxReachable
        return (
          <button
            key={step.key}
            className={`step ${state} ${reachable ? '' : 'locked'}`}
            onClick={() => reachable && onGo(i)}
            disabled={!reachable}
            title={reachable ? step.label : 'Complete previous steps first'}
          >
            <span className="step-num">{i < current ? '✓' : i + 1}</span>
            <span className="step-label">{step.label}</span>
          </button>
        )
      })}
    </nav>
  )
}
