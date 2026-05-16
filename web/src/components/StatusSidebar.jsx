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

function HintGroups({ status, onPickHint }) {
  const groups = status.hint_groups || {}
  const labels = {
    recommended: '推荐行动',
    explore: '探索',
    risky: '冒险行动',
  }
  const orderedKeys = ['recommended', 'explore', 'risky'].filter(key => groups[key]?.length)

  if (orderedKeys.length === 0) {
    return status.hints && status.hints.length > 0 ? (
      status.hints.map((hint, i) => (
        <button
          key={i}
          type="button"
          className="hint-item hint-button"
          onClick={() => onPickHint?.(`我想${hint}。`)}
        >
          💡 {hint}
        </button>
      ))
    ) : (
      <div className="inv-empty">暂无提示</div>
    )
  }

  return orderedKeys.map(key => (
    <div key={key} className={`hint-group hint-group-${key}`}>
      <div className="hint-group-title">{labels[key]}</div>
      {groups[key].map((hint, i) => (
        <button
          key={`${key}-${i}`}
          type="button"
          className="hint-item rich-hint hint-button"
          onClick={() => onPickHint?.(hint.command || hint.label)}
          title="填入输入框"
        >
          <div className="hint-label">{hint.label}</div>
          {hint.detail && <div className="hint-detail">{hint.detail}</div>}
        </button>
      ))}
    </div>
  ))
}

function EntityDetailPanel({ entity, sessionId, onEditEntity, onClose }) {
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({})

  if (!entity) return null

  const startEdit = () => {
    const init = {}
    if (entity.name) init.name = entity.name
    if (entity.tags) init.tags = entity.tags.join('、')
    if (entity.hp !== undefined) { init.hp = String(entity.hp); init.max_hp = String(entity.max_hp || entity.hp) }
    if (entity.hostile !== undefined) init.hostile = entity.hostile
    if (entity.available !== undefined) init.available = entity.available
    if (entity.is_visible !== undefined) init.visible = entity.is_visible
    if (entity.locked !== undefined) init.locked = entity.locked
    if (entity.opened !== undefined) init.opened = entity.opened
    if (entity.destroyed !== undefined) init.destroyed = entity.destroyed
    if (entity.alive !== undefined) init.alive = entity.alive
    if (entity.disposition) init.disposition = entity.disposition
    if (entity.favorability !== undefined) init.favorability = String(entity.favorability)
    setForm(init)
    setEditing(true)
  }

  const handleChange = (field) => (e) => {
    const val = e.target.type === 'checkbox' ? e.target.checked : e.target.value
    setForm(prev => ({ ...prev, [field]: val }))
  }

  const handleSave = async () => {
    const patch = {}
    if (form.name !== undefined && form.name !== entity.name) patch.name = form.name
    if (form.tags !== undefined) {
      const tags = form.tags.split(/[,，、]/).map(s => s.trim()).filter(Boolean)
      patch.tags = tags
    }
    if (form.hp !== undefined) {
      patch.hp = Number(form.hp)
      patch.max_hp = Number(form.max_hp)
    }
    for (const f of ['hostile', 'available', 'visible', 'locked', 'opened', 'destroyed', 'alive']) {
      if (form[f] !== undefined) patch[f] = form[f]
    }
    if (entity.disposition !== undefined && form.disposition) {
      patch.disposition = form.disposition
    }
    if (entity.favorability !== undefined && form.favorability !== undefined) {
      patch.favorability = Number(form.favorability)
    }
    if (Object.keys(patch).length === 0) {
      setEditing(false)
      return
    }
    setSaving(true)
    try {
      await onEditEntity(sessionId, entity.id, patch)
      setEditing(false)
    } catch (err) {
      alert(`编辑失败: ${err.message}`)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="entity-detail-panel">
      <div className="detail-header">
        <h3>{entity.name}</h3>
        <div className="detail-header-actions">
          {entity.can_edit && !editing && (
            <button className="btn-sm" onClick={startEdit}>编辑</button>
          )}
          <button className="btn-close-detail" onClick={onClose}>✕</button>
        </div>
      </div>
      {editing ? (
        <div className="edit-form">
          <div className="edit-field">
            <label>名称</label>
            <input type="text" value={form.name || ''} onChange={handleChange('name')} />
          </div>
          <div className="edit-field">
            <label>标签（逗号分隔）</label>
            <input type="text" value={form.tags || ''} onChange={handleChange('tags')} />
          </div>
          {form.hp !== undefined && (
            <div className="edit-field">
              <label>HP / Max HP</label>
              <div className="edit-hp-row">
                <input type="number" value={form.hp} onChange={handleChange('hp')} min="0" />
                <span>/</span>
                <input type="number" value={form.max_hp} onChange={handleChange('max_hp')} min="1" />
              </div>
            </div>
          )}
          <div className="edit-checks">
            {['hostile', 'available', 'visible'].map(f => (
              form[f] !== undefined && (
                <label key={f} className="edit-check">
                  <input type="checkbox" checked={form[f]} onChange={handleChange(f)} />
                  {f === 'hostile' ? '敌对' : f === 'available' ? '可用' : '可见'}
                </label>
              )
            ))}
            {['locked', 'opened', 'destroyed', 'alive'].map(f => (
              form[f] !== undefined && (
                <label key={f} className="edit-check">
                  <input type="checkbox" checked={form[f]} onChange={handleChange(f)} />
                  {f === 'locked' ? '锁定' : f === 'opened' ? '已打开' : f === 'destroyed' ? '已摧毁' : '存活'}
                </label>
              )
            ))}
          </div>
          {form.disposition !== undefined && (
            <div className="edit-field">
              <label>态度</label>
              <select value={form.disposition} onChange={handleChange('disposition')}>
                <option value="friendly">友善</option>
                <option value="neutral">中立</option>
                <option value="suspicious">怀疑</option>
                <option value="hostile">敌对</option>
              </select>
            </div>
          )}
          {form.favorability !== undefined && (
            <div className="edit-field">
              <label>好感度</label>
              <input type="number" value={form.favorability} onChange={handleChange('favorability')} />
            </div>
          )}
          <div className="edit-actions">
            <button className="btn-sm btn-cancel" onClick={() => setEditing(false)} disabled={saving}>取消</button>
            <button className="btn-sm btn-save" onClick={handleSave} disabled={saving}>
              {saving ? '保存中...' : '保存'}
            </button>
          </div>
        </div>
      ) : (
        <>
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
          {entity.turns_since_interaction !== undefined && entity.turns_since_interaction !== null && (
            <DetailRow label="距上次互动" value={`${entity.turns_since_interaction} 回合${entity.can_edit ? ' (可编辑)' : ''}`} />
          )}
        </>
      )}
    </div>
  )
}

export default function StatusSidebar({ status, selectedEntity, onSelectEntity, sessionId, onEditEntity, onPickHint }) {
  const [expanded, setExpanded] = useState({
    status: true,
    backpack: true,
    scene: true,
    exits: true,
    threads: true,
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
        title="可前往地点"
        count={status.exits?.length ?? 0}
        expanded={expanded.exits}
        onToggle={() => toggleSection('exits')}
      >
        {status.exits?.length ? (
          status.exits.map((exit) => (
            <div key={exit.location_id} className="exit-item">
              <span className="exit-direction">{exit.direction}</span>
              <span className="exit-name">📍 {exit.location_name}</span>
            </div>
          ))
        ) : (
          <div className="inv-empty">暂无已知出口</div>
        )}
      </AccordionSection>

      <AccordionSection
        title="当前线索/目标"
        count={status.threads?.filter(t => t.status === 'active').length ?? 0}
        expanded={expanded.threads}
        onToggle={() => toggleSection('threads')}
      >
        {status.threads?.length ? (
          status.threads.map((thread) => (
            <div key={thread.id} className={`thread-item ${thread.status}`}>
              <div className="thread-title">
                {thread.status === 'completed' ? '✓ ' : thread.status === 'failed' ? '✗ ' : '◆ '}
                {thread.title}
              </div>
              <div className="thread-progress-outer">
                <div
                  className={`thread-progress-inner ${thread.status}`}
                  style={{ width: `${Math.max(0, Math.min(100, thread.progress))}%` }}
                />
              </div>
              <div className="thread-meta">
                <span>{thread.progress}%</span>
                <span>{thread.status === 'active' ? '进行中' : thread.status === 'completed' ? '已完成' : '已失败'}</span>
              </div>
              {thread.next_hint && thread.status === 'active' && (
                <div className="thread-hint">💡 {thread.next_hint}</div>
              )}
            </div>
          ))
        ) : (
          <div className="inv-empty">暂无线索</div>
        )}
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
        <HintGroups status={status} onPickHint={onPickHint} />
      </AccordionSection>

      {selectedEntity && (
        <EntityDetailPanel
          entity={selectedEntity}
          sessionId={sessionId}
          onEditEntity={onEditEntity}
          onClose={() => onSelectEntity(selectedEntity.id)}
        />
      )}
    </div>
  )
}
