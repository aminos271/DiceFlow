export default function TurnCard({ turn }) {
  const { turn_id, player_input, check, narration, mechanical_results, resolution_card } = turn
  const isDynamic = check?.dynamic
  const result = check?.result

  const resultLabel = (r) => {
    const labels = {
      critical_success: '✨ 大成功',
      success: '✅ 成功',
      fail: '❌ 失败',
      critical_fail: '💥 大失败',
      impossible: '🚫 不可能',
    }
    return labels[r] || (isDynamic ? '🌐 动态' : '❓')
  }
  const isSuccess = result === 'success' || result === 'critical_success'

  return (
    <div className="turn-card">
      <div className="turn-header">
        <span className="turn-id">回合 {turn_id}｜{player_input}</span>
      </div>
      {check && (
        <div className="judgment">
          <span className="action-label">🎲 判定</span>
          <span className={`dice-roll ${isSuccess ? 'success' : 'fail'}`}>
            🎲 d20={check.roll} / DC {check.dc} {resultLabel(result)}
          </span>
        </div>
      )}
      {mechanical_results && mechanical_results.length > 0 && (
        <div className="mechanical-section">
          <span className="action-label">⚙️ 机械结果</span>
          <ul className="mechanical-list">
            {mechanical_results.map((item, i) => <li key={i}>{item}</li>)}
          </ul>
        </div>
      )}
      {narration && (
        <div className="narration-section">
          <span className="action-label">📖 叙事</span>
          <span className="narration">{narration}</span>
        </div>
      )}
      {resolution_card && (
        <div className="resolution-card">
          <div className="resolution-title">{resolution_card.title || '⚔️ 战斗结束'}</div>
          <div className="resolution-outcome">{resolution_card.outcome}</div>
          <div className="resolution-threat">
            威胁等级：{resolution_card.threat_before} → {resolution_card.threat_after}
          </div>
          {resolution_card.scene_changes?.length > 0 && (
            <>
              <div className="resolution-subtitle">场景变化</div>
              <ul>
                {resolution_card.scene_changes.map((item, i) => <li key={i}>{item}</li>)}
              </ul>
            </>
          )}
          {resolution_card.available_actions?.length > 0 && (
            <div className="resolution-actions">
              你现在可以：{resolution_card.available_actions.join(' / ')}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
