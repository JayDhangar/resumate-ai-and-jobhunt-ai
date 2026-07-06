export default function HistoryDrawer({ resume, onRestore, onClose }) {
  const versions = [...(resume.versions || [])].reverse()
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>Version History</h3>
          <button className="btn btn-ghost" onClick={onClose}>✕</button>
        </div>
        {versions.length === 0 && <p className="muted">No versions saved yet.</p>}
        <ul className="version-list">
          {versions.map((v) => (
            <li key={v.version} className="version-item">
              <div>
                <strong>Version {v.version}</strong>
                <p className="muted small">{v.label || 'No label'}</p>
                <p className="muted small">{new Date(v.created_at).toLocaleString()}</p>
              </div>
              <button className="btn btn-outline btn-small" onClick={() => onRestore(v.version)}>
                Restore
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
