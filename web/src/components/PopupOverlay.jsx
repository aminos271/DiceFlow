import { useState, useEffect } from 'react'
import { hpColor } from './StatusSidebar.jsx'

function _dispositionLabel(d) {
  const labels = { friendly: '友善', neutral: '中立', suspicious: '怀疑', hostile: '敌对' }
  return labels[d] || d
}

function DetailRow({ label, value }) {
  return (
    <div className="detail-row">
      <span className="detail-label">{label}</span>
      <span className="detail-value">{value}</span>
    </div>
  )
}

function EntityDetailView({ entity, sessionId, onEditEntity, onClose }) {
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
    <div>
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

export default function PopupOverlay({ type, status, sessionId, onClose, onEditEntity }) {
  const [detailEntityId, setDetailEntityId] = useState(null)

  // Clear detail view when panel type changes or modal closes
  useEffect(() => {
    setDetailEntityId(null)
  }, [type])

  // Derive current entity from latest status so edits are reflected immediately
  const detailEntity = detailEntityId
    ? (status?.known_entities || []).find(e => e.id === detailEntityId) || null
    : null

  if (!type || !status) return null

  const handleBackdrop = (e) => {
    if (e.target === e.currentTarget) onClose()
  }

  const handleItemClick = (itemName) => {
    const ent = status.known_entities?.find(e => e.name === itemName && e.is_in_inventory)
    if (ent) {
      setDetailEntityId(ent.id)
    }
  }

  const handleKnownEntityClick = (entityId) => {
    const ent = status.known_entities?.find(e => e.id === entityId)
    if (ent) {
      setDetailEntityId(ent.id)
    }
  }

  const handleBackFromDetail = () => {
    setDetailEntityId(null)
  }

  // Entity detail sub-panel
  if (detailEntity) {
    return (
      <div className="popup-overlay" onClick={handleBackdrop}>
        <div className="popup-card popup-entity-detail">
          <div className="popup-header">
            <span className="popup-title">{detailEntity.name}</span>
            <button className="btn-close-detail" onClick={onClose}>✕</button>
          </div>
          <div className="popup-body">
            <button className="btn-sm" onClick={handleBackFromDetail} style={{ marginBottom: 8 }}>← 返回</button>
            <EntityDetailView
              entity={detailEntity}
              sessionId={sessionId}
              onEditEntity={onEditEntity}
              onClose={onClose}
            />
          </div>
        </div>
      </div>
    )
  }

  const renderContent = () => {
    if (type === 'skills') {
      return (
        <div className="popup-body">
          {status.hints && status.hints.length > 0 ? (
            status.hints.map((hint, i) => (
              <div key={i} className="hint-item">💡 {hint}</div>
            ))
          ) : (
            <div className="inv-empty">暂无可用行动</div>
          )}
        </div>
      )
    }

    if (type === 'status') {
      const hpRatio = status.max_hp > 0 ? status.hp / status.max_hp : 0
      return (
        <div className="popup-body">
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
          <DetailRow label="回合" value={String(status.turn_id)} />
          <DetailRow label="场景" value={status.scene_name} />
          <DetailRow label="敌对数量" value={String(status.hostile_count)} />
          <DetailRow label="背包物品" value={String(status.inventory?.length ?? 0)} />
          {status.is_game_over && (
            <div className="popup-ending">游戏已结束</div>
          )}
        </div>
      )
    }

    if (type === 'backpack') {
      return (
        <div className="popup-body">
          {status.inventory && status.inventory.length > 0 ? (
            <ul className="inv-list">
              {status.inventory.map((item, i) => (
                <li
                  key={i}
                  className="inv-item"
                  onClick={() => handleItemClick(item)}
                >
                  {item}
                </li>
              ))}
            </ul>
          ) : (
            <div className="inv-empty">背包空空如也</div>
          )}
          {status.known_entities && status.known_entities.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <div className="section-header" style={{ marginBottom: 8 }}>
                <span>已知实体</span>
                <span className="section-count">({status.known_entities.length})</span>
              </div>
              {status.known_entities.map((ent) => (
                <div
                  key={ent.id}
                  className={`entity-item${ent.hostile ? ' hostile' : ''}`}
                  onClick={() => handleKnownEntityClick(ent.id)}
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
                </div>
              ))}
            </div>
          )}
        </div>
      )
    }

    return null
  }

  const titles = {
    skills: '技能栏',
    status: '状态',
    backpack: '背包',
  }

  return (
    <div className="popup-overlay" onClick={handleBackdrop}>
      <div className="popup-card">
        <div className="popup-header">
          <span className="popup-title">{titles[type] || ''}</span>
          <button className="btn-close-detail" onClick={onClose}>✕</button>
        </div>
        {renderContent()}
      </div>
    </div>
  )
}
