import { useState } from 'react'

export default function InputBar({ onSend, onMeta, disabled, pendingStatus, gameOver }) {
  const [text, setText] = useState('')

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!text.trim() || disabled) return
    onSend(text.trim())
    setText('')
  }

  if (gameOver) {
    return (
      <div className="game-over-input">
        <span>游戏结束</span>
      </div>
    )
  }

  return (
    <div className="input-area">
      {pendingStatus && (
        <div className="pending-status">
          <span className="pending-spinner" />
          {pendingStatus}
        </div>
      )}
      <form className="input-bar" onSubmit={handleSubmit}>
        <input
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={disabled ? pendingStatus || '处理中...' : '输入行动...'}
          disabled={disabled}
          autoFocus
        />
        <button type="submit" className="btn-send" disabled={disabled || !text.trim()}>
          发送
        </button>
        <div className="meta-buttons">
          <button type="button" onClick={() => onMeta('look')} title="查看周围" disabled={disabled}>看</button>
          <button type="button" onClick={() => onMeta('inv')} title="查看背包" disabled={disabled}>背包</button>
          <button type="button" onClick={() => onMeta('status')} title="查看状态" disabled={disabled}>状态</button>
          <button type="button" onClick={() => onMeta('hint')} title="查看提示" disabled={disabled}>提示</button>
        </div>
      </form>
    </div>
  )
}
