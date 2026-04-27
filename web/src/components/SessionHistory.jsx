export default function SessionHistory({ sessions, activeSessionId, onClose, onSelect, onNewGame }) {
  if (!sessions) return null

  return (
    <div className="history-overlay" onClick={onClose}>
      <div className="history-panel" onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 style={{ margin: 0 }}>📋 历史会话</h3>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              color: 'var(--text-dim)',
              fontSize: 18,
              padding: '4px 8px',
            }}
          >
            ✕
          </button>
        </div>
        {sessions.length === 0 ? (
          <div style={{ color: 'var(--text-dim)', fontSize: 13 }}>暂无历史会话</div>
        ) : (
          sessions.map((s) => (
            <div
              key={s.session_id}
              className={`history-item${s.session_id === activeSessionId ? ' active' : ''}`}
              onClick={() => onSelect(s.session_id, s.script_id)}
            >
              <div className="hi-title">{s.script_id}</div>
              <div className="hi-meta">
                <span>回合 {s.turn_count}</span>
                <span>{_formatDate(s.created_at)}</span>
              </div>
              {s.ending && <div className="hi-ending">结局: {s.ending}</div>}
              <button
                className="btn-new-game"
                onClick={(e) => { e.stopPropagation(); onNewGame(s.script_id) }}
              >
                新游戏
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

function _formatDate(iso) {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch {
    return iso.slice(0, 16)
  }
}
