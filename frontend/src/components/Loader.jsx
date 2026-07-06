export function Spinner({ label = '' }) {
  return (
    <div className="loader-center">
      <div className="spinner" />
      {label && <p className="muted">{label}</p>}
    </div>
  )
}

export function SkeletonCards({ count = 8 }) {
  return (
    <>
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="tcard skeleton">
          <div className="tcard-preview shimmer" />
          <div className="tcard-body">
            <div className="shimmer line w60" />
            <div className="shimmer line w40" />
          </div>
        </div>
      ))}
    </>
  )
}
