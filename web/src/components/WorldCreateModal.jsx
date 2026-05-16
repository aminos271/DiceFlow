import { useMemo, useState } from 'react'

const INITIAL_FORM = {
  id: '',
  title: '',
  description: '',
  intro: '',
  scene_name: '起点',
  scene_description: '',
  premise: '',
  tone: '',
  player_inventory_text: '',
  initial_npc_name: '',
  initial_npc_summary: '',
  bootstrap_yaml: '',
}

export default function WorldCreateModal({ open, onClose, onCreate }) {
  const [form, setForm] = useState(INITIAL_FORM)
  const [submitting, setSubmitting] = useState(false)

  const placeholderBootstrap = useMemo(() => `title: 你的世界标题
intro: 开场白
player:
  hp: 10
  max_hp: 10
  inventory: []
  location: 起点
scene:
  name: 起点
  description: 这里是你的起始场景
flags:
  game_over: false
  ending: ''
world:
  premise: 世界前提
  tone: 世界氛围
  allowed_scene_types: [tavern, street, chamber]
  allowed_entity_types: [npc, pickup, container, clue]
  forbidden: []
  max_runtime_dc: 14
  max_new_entities_per_transition: 3
entities: {}
scene_actions: {}
ending_conditions:
  - when:
      turn_id_gte: 20
    ending: timeout
  - when:
      player_hp_lte: 0
    ending: death`, [])

  if (!open) return null

  const handleChange = (field) => (e) => {
    setForm((prev) => ({ ...prev, [field]: e.target.value }))
  }

  const resetAndClose = () => {
    if (submitting) return
    setForm(INITIAL_FORM)
    onClose?.()
  }

  const submit = async (startAfterCreate) => {
    if (!form.title.trim()) {
      alert('世界标题不能为空')
      return
    }
    setSubmitting(true)
    try {
      const payload = {
        id: form.id.trim() || undefined,
        title: form.title.trim(),
        description: form.description.trim(),
        intro: form.intro.trim(),
        scene_name: form.scene_name.trim(),
        scene_description: form.scene_description.trim(),
        premise: form.premise.trim(),
        tone: form.tone.trim(),
        player_inventory: form.player_inventory_text
          .split(/[,，、\n]/)
          .map((s) => s.trim())
          .filter(Boolean),
        initial_npc_name: form.initial_npc_name.trim() || undefined,
        initial_npc_summary: form.initial_npc_summary.trim(),
        bootstrap_yaml: form.bootstrap_yaml,
      }
      await onCreate?.(payload, startAfterCreate)
      setForm(INITIAL_FORM)
    } catch (err) {
      alert(`创建世界失败: ${err.message}`)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="world-modal-overlay" onClick={resetAndClose}>
      <div className="world-modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="world-modal-header">
          <h3>新建世界</h3>
          <button className="btn-close" onClick={resetAndClose}>✕</button>
        </div>
        <div className="world-modal-body">
          <div className="world-form-grid">
            <label className="world-field">
              <span>世界标题</span>
              <input value={form.title} onChange={handleChange('title')} placeholder="例如：沉港夜雨" />
            </label>
            <label className="world-field">
              <span>世界 ID</span>
              <input value={form.id} onChange={handleChange('id')} placeholder="留空自动生成" />
            </label>
          </div>

          <label className="world-field">
            <span>世界简介</span>
            <textarea value={form.description} onChange={handleChange('description')} rows={3} />
          </label>

          <label className="world-field">
            <span>开场白</span>
            <textarea value={form.intro} onChange={handleChange('intro')} rows={3} />
          </label>

          <div className="world-form-grid">
            <label className="world-field">
              <span>起始场景名</span>
              <input value={form.scene_name} onChange={handleChange('scene_name')} />
            </label>
            <label className="world-field">
              <span>世界氛围</span>
              <input value={form.tone} onChange={handleChange('tone')} placeholder="例如：阴冷、悬疑、低魔" />
            </label>
          </div>

          <label className="world-field">
            <span>起始场景描述</span>
            <textarea value={form.scene_description} onChange={handleChange('scene_description')} rows={3} />
          </label>

          <label className="world-field">
            <span>世界前提 / 主题</span>
            <textarea value={form.premise} onChange={handleChange('premise')} rows={3} />
          </label>

          <div className="world-form-grid">
            <label className="world-field">
              <span>初始背包</span>
              <input value={form.player_inventory_text} onChange={handleChange('player_inventory_text')} placeholder="短剑, 火把" />
            </label>
            <label className="world-field">
              <span>初始 NPC 名称</span>
              <input value={form.initial_npc_name} onChange={handleChange('initial_npc_name')} placeholder="留空则不创建" />
            </label>
          </div>

          <label className="world-field">
            <span>初始 NPC 简述</span>
            <textarea value={form.initial_npc_summary} onChange={handleChange('initial_npc_summary')} rows={2} />
          </label>

          <label className="world-field">
            <span>高级配置：bootstrap.yaml（可选）</span>
            <textarea
              className="world-bootstrap-textarea"
              value={form.bootstrap_yaml}
              onChange={handleChange('bootstrap_yaml')}
              rows={18}
              placeholder={placeholderBootstrap}
            />
          </label>
        </div>
        <div className="world-modal-actions">
          <button className="btn-sm btn-cancel" onClick={resetAndClose} disabled={submitting}>取消</button>
          <button className="btn-sm" onClick={() => submit(false)} disabled={submitting}>
            {submitting ? '创建中...' : '仅创建'}
          </button>
          <button className="btn-new-game" onClick={() => submit(true)} disabled={submitting}>
            {submitting ? '创建中...' : '创建并进入'}
          </button>
        </div>
      </div>
    </div>
  )
}
