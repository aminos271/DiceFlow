import { useState } from 'react'

export default function InputBar({ onSend, onMeta, disabled, gameOver }) {
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
    <form className="input-bar" onSubmit={handleSubmit}>
      <input
        type="text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="输入行动..."
        disabled={disabled}
        autoFocus
      />
      <button type="submit" className="btn-send" disabled={disabled || !text.trim()}>
        发送
      </button>
      <div className="meta-buttons">
        <button type="button" onClick={() => onMeta('look')} title="查看周围">看</button>
        <button type="button" onClick={() => onMeta('inv')} title="查看背包">背包</button>
        <button type="button" onClick={() => onMeta('status')} title="查看状态">状态</button>
        <button type="button" onClick={() => onMeta('hint')} title="查看提示">提示</button>
      </div>
    </form>
  )
}
