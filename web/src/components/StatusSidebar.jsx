export function hpColor(hp, maxHp) {
  const ratio = maxHp > 0 ? hp / maxHp : 0
  if (ratio <= 0.3) return 'var(--red)'
  if (ratio <= 0.6) return 'var(--yellow)'
  return 'var(--green)'
}

function _dispositionLabel(d) {
  const labels = { friendly: '友善', neutral: '中立', suspicious: '怀疑', hostile: '敌对' }
  return labels[d] || d
}

export default function StatusSidebar({ status }) {
  if (!status) return null

  const hpRatio = status.max_hp > 0 ? status.hp / status.max_hp : 0

  return (
    <div className="status-sidebar">
      <div className="status-section">
        <h4>状态</h4>
        <div className="hp-bar-outer">
          <div
            className="hp-bar-inner"
            style={{
              width: `${Math.max(0, Math.min(100, hpRatio * 100))}%`,
              background: hpColor(status.hp, status.max_hp),
            }}
          />
        </div>
        <div className="hp-text" style={{ color: hpColor(status.hp, status.max_hp) }}>
          ❤️ {status.hp} / {status.max_hp}
        </div>
      </div>

      <div className="status-section">
        <h4>背包</h4>
        {status.inventory && status.inventory.length > 0 ? (
          <ul className="inv-list">
            {status.inventory.map((item, i) => <li key={i}>{item}</li>)}
          </ul>
        ) : (
          <div className="inv-empty">空空如也</div>
        )}
      </div>

      <div className="status-section">
        <h4>场景</h4>
        <div className="scene-name">📍 {status.scene_name}</div>
        <div className="scene-desc">{status.scene_description}</div>
      </div>

      {status.visible_entities && status.visible_entities.length > 0 && (
        <div className="status-section">
          <h4>可见 ({status.visible_entities.length})</h4>
          {status.visible_entities.map((ent) => (
            <div key={ent.id} className={`entity-item${ent.hostile ? ' hostile' : ''}`}>
              <div className="entity-main">
                {ent.hostile ? '🔴 ' : '▸ '}{ent.name}
                {ent.hp !== undefined && (
                  <span style={{ color: hpColor(ent.hp, ent.max_hp || ent.hp), marginLeft: 6 }}>
                    {ent.hp}/{ent.max_hp || ent.hp}
                  </span>
                )}
                <span className="entity-tags">
                  {ent.locked && ' 🔒'} {ent.opened && ' 🔓'} {ent.destroyed && ' 💔'}
                </span>
              </div>
              {ent.personality && (
                <div className="entity-npc-info">
                  {ent.disposition && (
                    <span className={`npc-disposition npc-${ent.disposition}`}>
                      {_dispositionLabel(ent.disposition)}
                    </span>
                  )}
                  {ent.favorability !== undefined && (
                    <span className="npc-favor" style={{ color: ent.favorability > 0 ? 'var(--green)' : ent.favorability < 0 ? 'var(--red)' : 'var(--text-dim)' }}>
                      {ent.favorability > 0 ? '+' : ''}{ent.favorability}
                    </span>
                  )}
                  {ent.personality.traits && ent.personality.traits.length > 0 && (
                    <span className="npc-traits">{ent.personality.traits.join('、')}</span>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {status.hints && status.hints.length > 0 && (
        <div className="status-section">
          <h4>提示</h4>
          {status.hints.map((hint, i) => (
            <div key={i} className="hint-item">💡 {hint}</div>
          ))}
        </div>
      )}
    </div>
  )
}
