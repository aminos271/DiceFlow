export default function ScriptSelect({ scripts, sessions, onSelect, onContinue }) {
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
                  if (!s.ending) onContinue(s.session_id, s.display_name || s.script_id)
                }}
              >
                <div className="continue-card-header">
                  <span className="continue-name">{s.display_name || s.script_id}</span>
                  {s.ending && <span className="continue-ending">{_endingLabel(s.ending)}</span>}
                </div>
                <div className="continue-meta">
                  <span>{s.script_id}</span>
                  <span>回合 {s.turn_count}</span>
                  <span>{_formatDate(s.updated_at)}</span>
                </div>
                <div className="continue-actions">
                  {s.ending ? (
                    <button
                      className="btn-continue"
                      onClick={(e) => { e.stopPropagation(); onSelect(s.script_id, s.script_id) }}
                    >
                      重新开始
                    </button>
                  ) : (
                    <button
                      className="btn-continue"
                      onClick={(e) => { e.stopPropagation(); onContinue(s.session_id, s.display_name || s.script_id) }}
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
      <p className="subtitle">选择一个剧本开始游戏</p>
      <div className="script-grid">
        {scripts.map((s) => (
          <div key={s.id} className="script-card" onClick={() => onSelect(s.id, s.title)}>
            <h3>{s.title}</h3>
            <p>{s.intro}</p>
          </div>
        ))}
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

function _endingLabel(e) {
  if (!e) return ''
  if (e === 'victory') return '胜利'
  if (e === 'death') return '死亡'
  if (e === 'timeout') return '超时'
  return e
}
