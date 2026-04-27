import { useState } from 'react'
import { updateSession, deleteSession as apiDeleteSession } from '../api.js'

export default function SessionHistory({ sessions, activeSessionId, onClose, onSelect, onNewGame, onRefresh, onDeleteActive }) {
  const [editingId, setEditingId] = useState(null)
  const [editName, setEditName] = useState('')

  if (!sessions) return null

  const handleStartRename = (s) => {
    setEditingId(s.session_id)
    setEditName(s.display_name || s.script_id)
  }

  const handleSaveRename = async (sid) => {
    const name = editName.trim()
    if (!name || name.length > 40) return
    try {
      await updateSession(sid, name)
      setEditingId(null)
      setEditName('')
      onRefresh?.()
    } catch (err) {
      alert(`改名失败: ${err.message}`)
    }
  }

  const handleCancelRename = () => {
    setEditingId(null)
    setEditName('')
  }

  const handleDelete = async (sid) => {
    if (!confirm('确定要删除这个会话吗？此操作不可撤销。')) return
    try {
      await apiDeleteSession(sid)
      if (sid === activeSessionId) {
        onDeleteActive?.()
      }
      onRefresh?.()
    } catch (err) {
      alert(`删除失败: ${err.message}`)
    }
  }

  return (
    <div className="history-overlay" onClick={onClose}>
      <div className="history-panel" onClick={(e) => e.stopPropagation()}>
        <div className="history-header">
          <h3>📋 历史会话</h3>
          <button className="btn-close" onClick={onClose}>✕</button>
        </div>
        {sessions.length === 0 ? (
          <div className="history-empty">暂无历史会话</div>
        ) : (
          sessions.map((s) => {
            const isActive = s.session_id === activeSessionId
            const isEditing = editingId === s.session_id
            const display = s.display_name || s.script_id

            return (
              <div
                key={s.session_id}
                className={`history-item${isActive ? ' active' : ''}`}
              >
                {isEditing ? (
                  <div className="rename-row">
                    <input
                      className="rename-input"
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      onKeyDown={(e) => { if (e.key === 'Enter') handleSaveRename(s.session_id); if (e.key === 'Escape') handleCancelRename() }}
                      maxLength={40}
                      autoFocus
                    />
                    <button className="btn-sm btn-save" onClick={() => handleSaveRename(s.session_id)}>保存</button>
                    <button className="btn-sm btn-cancel" onClick={handleCancelRename}>取消</button>
                  </div>
                ) : (
                  <div className="hi-title" onClick={() => onSelect(s.session_id, s.script_id)}>
                    {display}
                  </div>
                )}
                <div className="hi-meta" onClick={() => !isEditing && onSelect(s.session_id, s.script_id)}>
                  <span>{s.script_id}</span>
                  <span>回合 {s.turn_count}</span>
                  <span>{_formatDate(s.created_at)}</span>
                </div>
                {s.ending && <div className="hi-ending">结局: {s.ending}</div>}
                <div className="hi-actions">
                  {!isEditing && (
                    <>
                      <button className="btn-sm" onClick={() => handleStartRename(s)} title="改名">✎</button>
                      <button className="btn-sm btn-danger" onClick={() => handleDelete(s.session_id)} title="删除">✕</button>
                    </>
                  )}
                  <button
                    className="btn-new-game"
                    onClick={(e) => { e.stopPropagation(); onNewGame(s.script_id) }}
                  >
                    新游戏
                  </button>
                </div>
              </div>
            )
          })
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
