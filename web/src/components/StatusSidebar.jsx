import { useState } from 'react'

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

function AccordionSection({ title, count, expanded, onToggle, children }) {
  return (
    <div className="status-section">
      <h4 className="section-header" onClick={onToggle}>
        <span className="section-arrow">{expanded ? '▼' : '▶'}</span>
        <span>{title}</span>
        {count !== undefined && <span className="section-count">({count})</span>}
      </h4>
      {expanded && children}
    </div>
  )
}

function DetailRow({ label, value }) {
  return (
    <div className="detail-row">
      <span className="detail-label">{label}</span>
      <span className="detail-value">{value}</span>
    </div>
  )
}

function EntityDetailPanel({ entity, onClose }) {
  if (!entity) return null
  return (
    <div className="entity-detail-panel">
      <div className="detail-header">
        <h3>{entity.name}</h3>
        <button className="btn-close-detail" onClick={onClose}>✕</button>
      </div>
      <DetailRow label="ID" value={entity.id} />
      <DetailRow label="类型" value={entity.type || '-'} />
      <DetailRow label="标签" value={entity.tags?.length ? entity.tags.join('、') : '-'} />
      <DetailRow label="可见" value={entity.is_visible ? '是' : '否'} />
      <DetailRow label="在背包" value={entity.is_in_inventory ? '是' : '否'} />
      <DetailRow label="可用" value={entity.available ? '是' : '否'} />
      {entity.hostile && <DetailRow label="敌对" value="是" />}
      {entity.locked && <DetailRow label="锁定" value="是" />}
      {entity.opened && <DetailRow label="已打开" value="是" />}
      {entity.destroyed && <DetailRow label="已摧毁" value="是" />}
      {entity.looted && <DetailRow label="已搜刮" value="是" />}
      <DetailRow label="存活" value={entity.alive ? '是' : '否'} />
      {entity.hp !== undefined && (
        <DetailRow label="生命值" value={`${entity.hp}/${entity.max_hp || entity.hp}`} />
      )}
      {entity.disposition !== undefined && (
        <DetailRow label="态度" value={_dispositionLabel(entity.disposition)} />
      )}
      {entity.favorability !== undefined && (
        <DetailRow label="好感度" value={String(entity.favorability)} />
      )}
      {entity.personality && (
        <>
          <DetailRow label="性格特质" value={entity.personality.traits?.length ? entity.personality.traits.join('、') : '-'} />
          <DetailRow label="举止" value={entity.personality.manner || '-'} />
          <DetailRow label="动机" value={entity.personality.motivation || '-'} />
        </>
      )}
      {entity.last_seen_turn_id !== undefined && (
        <DetailRow label="最后出现在回合" value={String(entity.last_seen_turn_id)} />
      )}
    </div>
  )
}

export default function StatusSidebar({ status, selectedEntity, onSelectEntity }) {
  const [expanded, setExpanded] = useState({
    status: true,
    backpack: true,
    scene: true,
    entities: true,
    hints: false,
  })

  if (!status) return null

  const toggleSection = (section) => {
    setExpanded(prev => ({ ...prev, [section]: !prev[section] }))
  }

  const hpRatio = status.max_hp > 0 ? status.hp / status.max_hp : 0
  const knownEntities = status.known_entities || []

  return (
    <div className="status-sidebar">
      <AccordionSection
        title="状态"
        expanded={expanded.status}
        onToggle={() => toggleSection('status')}
      >
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
      </AccordionSection>

      <AccordionSection
        title="背包"
        count={status.inventory?.length ?? 0}
        expanded={expanded.backpack}
        onToggle={() => toggleSection('backpack')}
      >
        {status.inventory && status.inventory.length > 0 ? (
          <ul className="inv-list">
            {status.inventory.map((item, i) => (
              <li
                key={i}
                className={`inv-item${selectedEntity?.name === item ? ' selected' : ''}`}
                onClick={() => onSelectEntity(item)}
              >
                {item}
              </li>
            ))}
          </ul>
        ) : (
          <div className="inv-empty">空空如也</div>
        )}
      </AccordionSection>

      <AccordionSection
        title="场景"
        expanded={expanded.scene}
        onToggle={() => toggleSection('scene')}
      >
        <div className="scene-name">📍 {status.scene_name}</div>
        <div className="scene-desc">{status.scene_description}</div>
      </AccordionSection>

      <AccordionSection
        title="实体记录"
        count={knownEntities.length}
        expanded={expanded.entities}
        onToggle={() => toggleSection('entities')}
      >
        {knownEntities.length > 0 ? (
          knownEntities.map((ent) => (
            <div
              key={ent.id}
              className={`entity-item${ent.hostile ? ' hostile' : ''}${selectedEntity?.id === ent.id ? ' selected' : ''}`}
              onClick={() => onSelectEntity(ent.id)}
            >
              <div className="entity-main">
                {!ent.is_visible && <span className="entity-hidden-mark" title="当前不可见">⊙ </span>}
                {ent.is_visible && (ent.hostile ? '🔴 ' : '▸ ')}
                {ent.name}
                {ent.hp !== undefined && (
                  <span style={{ color: hpColor(ent.hp, ent.max_hp || ent.hp), marginLeft: 6 }}>
                    {ent.hp}/{ent.max_hp || ent.hp}
                  </span>
                )}
                <span className="entity-tags">
                  {ent.locked && ' 🔒'} {ent.opened && ' 🔓'} {ent.destroyed && ' 💔'} {ent.is_in_inventory && ' 🎒'}
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
          ))
        ) : (
          <div className="inv-empty">暂无记录</div>
        )}
      </AccordionSection>

      <AccordionSection
        title="提示"
        count={status.hints?.length ?? 0}
        expanded={expanded.hints}
        onToggle={() => toggleSection('hints')}
      >
        {status.hints && status.hints.length > 0 ? (
          status.hints.map((hint, i) => (
            <div key={i} className="hint-item">💡 {hint}</div>
          ))
        ) : (
          <div className="inv-empty">暂无提示</div>
        )}
      </AccordionSection>

      {selectedEntity && (
        <EntityDetailPanel
          entity={selectedEntity}
          onClose={() => onSelectEntity(selectedEntity.id)}
        />
      )}
    </div>
  )
}
