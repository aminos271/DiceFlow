import { useState, useEffect, useCallback } from 'react'
import { getLorebook, createLoreEntry, updateLoreEntry, deleteLoreEntry } from '../api.js'

const TYPE_LABELS = { world: '世界观', location: '地点', character: '角色', event: '事件' }
const TABS = ['world', 'location', 'character', 'event']
const EMPTY_FORM = {
  title: '', aliases: '', summary: '', content: '', tags: '',
  pinned: false, discovered: false, linked_entity_id: '', linked_turn_ids: '',
}

export default function LorebookPanel({ sessionId }) {
  const [entries, setEntries] = useState({ world_entries: [], character_entries: [], event_entries: [] })
  const [activeTab, setActiveTab] = useState('world')
  const [selectedId, setSelectedId] = useState(null)
  const [mode, setMode] = useState('view') // 'view' | 'create' | 'edit'
  const [form, setForm] = useState({ ...EMPTY_FORM })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const fetchEntries = useCallback(async () => {
    try {
      const data = await getLorebook(sessionId)
      setEntries(data.entries || { world_entries: [], character_entries: [], event_entries: [] })
    } catch (err) {
      setError(`加载失败: ${err.message}`)
    }
  }, [sessionId])

  useEffect(() => {
    fetchEntries()
  }, [fetchEntries])

  const currentList = entries[`${activeTab}_entries`] || []

  // ── Selection ───────────────────────────────────────────────────

  const selected = selectedId ? currentList.find(e => e.id === selectedId) || null : null

  const handleSelect = (id) => {
    setSelectedId(id)
    setMode('view')
    setError('')
  }

  const handleBackToList = () => {
    setSelectedId(null)
    setMode('view')
    setError('')
  }

  // ── Create ──────────────────────────────────────────────────────

  const handleNew = () => {
    setSelectedId(null)
    setMode('create')
    setForm({
      ...EMPTY_FORM,
      type: activeTab,
    })
    setError('')
  }

  // ── Edit ────────────────────────────────────────────────────────

  const handleStartEdit = () => {
    if (!selected) return
    setMode('edit')
    setForm({
      title: selected.title || '',
      aliases: (selected.aliases || []).join('、'),
      summary: selected.summary || '',
      content: selected.content || '',
      tags: (selected.tags || []).join('、'),
      pinned: selected.pinned || false,
      discovered: selected.discovered || false,
      linked_entity_id: selected.linked_entity_id || '',
      linked_turn_ids: (selected.linked_turn_ids || []).join('、'),
    })
    setError('')
  }

  const handleFormChange = (field) => (e) => {
    const val = e.target.type === 'checkbox' ? e.target.checked : e.target.value
    setForm(prev => ({ ...prev, [field]: val }))
  }

  const buildBody = () => {
    return {
      type: activeTab,
      title: form.title.trim(),
      aliases: form.aliases ? form.aliases.split(/[,，、]/).map(s => s.trim()).filter(Boolean) : [],
      summary: form.summary,
      content: form.content,
      tags: form.tags ? form.tags.split(/[,，、]/).map(s => s.trim()).filter(Boolean) : [],
      pinned: form.pinned,
      discovered: form.discovered,
      linked_entity_id: form.linked_entity_id.trim() || null,
      linked_turn_ids: form.linked_turn_ids
        ? form.linked_turn_ids.split(/[,，、]/).map(s => Number(s.trim())).filter(n => !isNaN(n))
        : [],
    }
  }

  const handleSave = async () => {
    if (!form.title.trim()) {
      setError('标题不能为空')
      return
    }
    setSaving(true)
    setError('')
    try {
      if (mode === 'create') {
        await createLoreEntry(sessionId, buildBody())
      } else {
        await updateLoreEntry(sessionId, selectedId, buildBody())
      }
      await fetchEntries()
      setMode('view')
      if (mode === 'edit') {
        // Keep selected entry after edit
      } else {
        setSelectedId(null)
      }
    } catch (err) {
      setError(`保存失败: ${err.message}`)
    } finally {
      setSaving(false)
    }
  }

  const handleCancel = () => {
    if (mode === 'create') {
      setMode('view')
      setSelectedId(null)
    } else {
      setMode('view')
    }
    setError('')
  }

  // ── Delete ──────────────────────────────────────────────────────

  const handleDelete = async () => {
    if (!selectedId) return
    if (!window.confirm(`确定要删除"${selected?.title || selectedId}"吗？`)) return
    setSaving(true)
    setError('')
    try {
      await deleteLoreEntry(sessionId, selectedId)
      await fetchEntries()
      setSelectedId(null)
      setMode('view')
    } catch (err) {
      setError(`删除失败: ${err.message}`)
    } finally {
      setSaving(false)
    }
  }

  // ── Toggle helpers ──────────────────────────────────────────────

  const handleTogglePinned = async () => {
    if (!selected) return
    try {
      await updateLoreEntry(sessionId, selectedId, { pinned: !selected.pinned })
      await fetchEntries()
    } catch (err) {
      setError(`操作失败: ${err.message}`)
    }
  }

  const handleToggleDiscovered = async () => {
    if (!selected) return
    try {
      await updateLoreEntry(sessionId, selectedId, { discovered: !selected.discovered })
      await fetchEntries()
    } catch (err) {
      setError(`操作失败: ${err.message}`)
    }
  }

  // ── Tab bar ─────────────────────────────────────────────────────

  const tabBar = (
    <div className="lore-tabs">
      {TABS.map(t => (
        <button
          key={t}
          className={`lore-tab${activeTab === t ? ' active' : ''}`}
          onClick={() => { setActiveTab(t); setSelectedId(null); setMode('view'); setError('') }}
        >
          {TYPE_LABELS[t]} ({entries[`${t}_entries`]?.length || 0})
        </button>
      ))}
    </div>
  )

  // ── Entry list ──────────────────────────────────────────────────

  const entryList = (
    <div className="lore-list">
      {currentList.length === 0 ? (
        <div className="lore-empty">暂无{TYPE_LABELS[activeTab]}条目</div>
      ) : (
        currentList.map(e => (
          <div
            key={e.id}
            className={`lore-item${selectedId === e.id ? ' active' : ''}${e.pinned ? ' pinned' : ''}`}
            onClick={() => handleSelect(e.id)}
          >
            <div className="lore-item-title">
              {e.pinned && <span className="lore-pin" title="已置顶">📌</span>}
              {e.discovered && <span className="lore-discovered" title="已发现">👁</span>}
              <span>{e.title}</span>
            </div>
            {e.tags && e.tags.length > 0 && (
              <div className="lore-item-tags">{e.tags.join('、')}</div>
            )}
            {e.summary && (
              <div className="lore-item-summary">{e.summary}</div>
            )}
          </div>
        ))
      )}
    </div>
  )

  // ── Detail view ─────────────────────────────────────────────────

  const detailView = selected && (
    <div className="lore-detail">
      <div className="lore-detail-header">
        <h3>
          {selected.pinned && '📌 '}
          {selected.title}
        </h3>
        <div className="lore-detail-actions">
          <button className="btn-sm" onClick={handleTogglePinned} title={selected.pinned ? '取消置顶' : '置顶'}>
            {selected.pinned ? '📌取消' : '📌置顶'}
          </button>
          <button className="btn-sm" onClick={handleToggleDiscovered} title={selected.discovered ? '标记未发现' : '标记已发现'}>
            {selected.discovered ? '👁已发现' : '未发现'}
          </button>
          <button className="btn-sm" onClick={handleStartEdit}>编辑</button>
          <button className="btn-sm btn-danger" onClick={handleDelete} disabled={saving}>删除</button>
        </div>
      </div>
      <div className="lore-detail-body">
        <LoreDetailRow label="类型" value={TYPE_LABELS[selected.type] || selected.type} />
        <LoreDetailRow label="别名" value={selected.aliases?.length ? selected.aliases.join('、') : '-'} />
        <LoreDetailRow label="标签" value={selected.tags?.length ? selected.tags.join('、') : '-'} />
        <LoreDetailRow label="来源" value={selected.source === 'derived' ? '自动生成' : '手动创建'} />
        {selected.linked_entity_id && (
          <LoreDetailRow label="关联实体" value={selected.linked_entity_id} />
        )}
        {selected.linked_turn_ids && selected.linked_turn_ids.length > 0 && (
          <LoreDetailRow label="关联回合" value={selected.linked_turn_ids.join('、')} />
        )}
        <LoreDetailRow label="摘要" value={selected.summary || '-'} />
        <LoreDetailRow label="创建时间" value={selected.created_at ? new Date(selected.created_at).toLocaleString() : '-'} />
        <LoreDetailRow label="更新时间" value={selected.updated_at ? new Date(selected.updated_at).toLocaleString() : '-'} />
        {selected.content && (
          <div className="lore-content">{selected.content}</div>
        )}
      </div>
    </div>
  )

  // ── Create/Edit form ────────────────────────────────────────────

  const createEditForm = (
    <div className="lore-detail">
      <h3>{mode === 'create' ? `新建${TYPE_LABELS[activeTab]}条目` : `编辑: ${selected?.title || ''}`}</h3>
      {error && <div className="lore-error">{error}</div>}
      <div className="edit-form">
        <div className="edit-field">
          <label>标题 *</label>
          <input type="text" value={form.title} onChange={handleFormChange('title')} maxLength={80} />
        </div>
        <div className="edit-field">
          <label>别名（逗号分隔）</label>
          <input type="text" value={form.aliases} onChange={handleFormChange('aliases')} />
        </div>
        <div className="edit-field">
          <label>标签（逗号分隔）</label>
          <input type="text" value={form.tags} onChange={handleFormChange('tags')} />
        </div>
        <div className="edit-field">
          <label>摘要</label>
          <textarea value={form.summary} onChange={handleFormChange('summary')} rows={3} />
        </div>
        <div className="edit-field">
          <label>详细内容</label>
          <textarea value={form.content} onChange={handleFormChange('content')} rows={6} />
        </div>
        <div className="edit-field">
          <label>关联实体 ID（可选）</label>
          <input type="text" value={form.linked_entity_id} onChange={handleFormChange('linked_entity_id')} />
        </div>
        <div className="edit-field">
          <label>关联回合 ID（逗号分隔）</label>
          <input type="text" value={form.linked_turn_ids} onChange={handleFormChange('linked_turn_ids')} />
        </div>
        <div className="edit-checks">
          <label className="edit-check">
            <input type="checkbox" checked={form.pinned} onChange={handleFormChange('pinned')} />
            置顶
          </label>
          <label className="edit-check">
            <input type="checkbox" checked={form.discovered} onChange={handleFormChange('discovered')} />
            已发现
          </label>
        </div>
        <div className="edit-actions">
          <button className="btn-sm btn-cancel" onClick={handleCancel} disabled={saving}>取消</button>
          <button className="btn-sm btn-save" onClick={handleSave} disabled={saving}>
            {saving ? '保存中...' : '保存'}
          </button>
        </div>
      </div>
    </div>
  )

  // ── Determine what to show in the right panel ────────────────────

  let rightPanel
  if (mode === 'create' || mode === 'edit') {
    rightPanel = createEditForm
  } else if (mode === 'view' && selected) {
    rightPanel = detailView
  } else {
    rightPanel = (
      <div className="lore-detail">
        <div className="lore-empty">选择一个条目查看详情</div>
      </div>
    )
  }

  return (
    <div className="lorebook-panel">
      {tabBar}
      <div className="lorebook-body">
        <div className="lorebook-sidebar">
          <div className="lore-list-header">
            <span>{TYPE_LABELS[activeTab]}列表</span>
            <button className="btn-sm" onClick={handleNew} title="新建">+ 新建</button>
          </div>
          {entryList}
        </div>
        <div className="lorebook-main">
          {rightPanel}
        </div>
      </div>
    </div>
  )
}

function LoreDetailRow({ label, value }) {
  return (
    <div className="detail-row">
      <span className="detail-label">{label}</span>
      <span className="detail-value">{value}</span>
    </div>
  )
}
