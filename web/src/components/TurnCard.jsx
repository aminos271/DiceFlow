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
      <div className="player-input">{player_input}</div>
      {check && (
        <div className={`dice-roll ${isSuccess ? 'success' : 'fail'}`}>
          🎲 d20={check.roll} / DC {check.dc} {resultLabel(result)}
        </div>
      )}
      {narration && <div className="narration">{narration}</div>}
    </div>
  )
}
