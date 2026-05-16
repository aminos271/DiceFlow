export default function ScriptSelect({ worlds, sessions, onSelectWorld, onContinue, onOpenCreateWorld }) {
  const sorted = [...(sessions || [])]
    .sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''))

  return (
    <div className="script-select">
      {sorted.length > 0 && (
        <div className="continue-section">
          <h2>继续游玩</h2>
          <div className="continue-grid">
            {sorted.map((s) => (
              <div
                key={s.session_id}
                className={`continue-card${s.ending ? ' ended' : ''}`}
                onClick={() => {
                  if (!s.ending) onContinue(s.session_id, s.display_name || s.world_id || '')
                }}
              >
                <div className="continue-card-header">
                  <span className="continue-name">{s.display_name || s.world_id || 'unknown'}</span>
                  {s.ending && <span className="continue-ending">{_endingLabel(s.ending)}</span>}
                </div>
                <div className="continue-meta">
                  <span>{s.world_id || ''}</span>
                  <span>回合 {s.turn_count}</span>
                  <span>{_formatDate(s.updated_at)}</span>
                </div>
                <div className="continue-actions">
                  {s.ending ? (
                    <button
                      className="btn-continue"
                      onClick={(e) => {
                        e.stopPropagation()
                        if (s.world_id) {
                          onSelectWorld(s.world_id, s.display_name || s.world_id)
                        }
                      }}
                    >
                      重新开始
                    </button>
                  ) : (
                    <button
                      className="btn-continue"
                      onClick={(e) => { e.stopPropagation(); onContinue(s.session_id, s.display_name || s.world_id || '') }}
                    >
                      继续游玩
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <h1>DiceFlow</h1>
      <div className="world-toolbar">
        <button className="btn-new-game" onClick={onOpenCreateWorld}>＋ 新建世界</button>
      </div>

      {worlds.length > 0 && (
        <>
          <p className="subtitle">选择一个世界开始冒险</p>
          <div className="script-grid">
            {worlds.map((w) => (
              <div key={w.id} className="script-card" onClick={() => onSelectWorld(w.id, w.title)}>
                <h3>{w.title}</h3>
                <p>{w.description}</p>
                <span className="world-badge">世界</span>
              </div>
            ))}
          </div>
        </>
      )}

      {!worlds.length && (
        <p className="subtitle">没有找到可用的世界。请检查配置。</p>
      )}
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

function _endingLabel(e) {
  if (!e) return ''
  if (e === 'victory') return '胜利'
  if (e === 'death') return '死亡'
  if (e === 'timeout') return '超时'
  return e
}
