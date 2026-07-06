import { useEffect } from 'react'

export default function Toast({ toast, onDone }) {
  useEffect(() => {
    const timer = setTimeout(onDone, 4200)
    return () => clearTimeout(timer)
  }, [toast.id, onDone])
  return (
    <div className={`toast toast-${toast.kind}`} role="status">
      {toast.message}
    </div>
  )
}
