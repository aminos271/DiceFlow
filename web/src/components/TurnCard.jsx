export default function TurnCard({ turn }) {
  const { turn_id, player_input, check, narration } = turn
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
        <span className="turn-id">回合 {turn_id}</span>
      </div>
      <div className="player-action">
        <span className="action-label">玩家</span>
        <span className="action-text">{player_input}</span>
      </div>
      {check && (
        <div className="judgment">
          <span className="action-label">判定</span>
          <span className={`dice-roll ${isSuccess ? 'success' : 'fail'}`}>
            🎲 d20={check.roll} / DC {check.dc} {resultLabel(result)}
          </span>
        </div>
      )}
      {narration && (
        <div className="narration-section">
          <span className="action-label">结果</span>
          <span className="narration">{narration}</span>
        </div>
      )}
    </div>
  )
}
