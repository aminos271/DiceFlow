import { useEffect, useRef } from 'react'

export default function InputBar({ onSend, onOpenPanel, value, onChange, focusToken, disabled, pendingStatus, gameOver }) {
  const inputRef = useRef(null)

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!value.trim() || disabled) return
    onSend(value.trim())
  }

  useEffect(() => {
    if (focusToken > 0 && inputRef.current && !disabled && !gameOver) {
      inputRef.current.focus()
      inputRef.current.select()
    }
  }, [focusToken, disabled, gameOver])

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
          ref={inputRef}
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={disabled ? pendingStatus || '处理中...' : '输入行动...'}
          disabled={disabled}
          autoFocus
        />
        <button type="submit" className="btn-send" disabled={disabled || !value.trim()}>
          发送
        </button>
        <div className="meta-buttons">
          <button type="button" onClick={() => onOpenPanel('skills')} title="技能栏" disabled={disabled}>技能栏</button>
          <button type="button" onClick={() => onOpenPanel('status')} title="查看状态" disabled={disabled}>状态</button>
          <button type="button" onClick={() => onOpenPanel('backpack')} title="查看背包" disabled={disabled}>背包</button>
          <button type="button" onClick={() => onOpenPanel('lorebook')} title="查看资料库" disabled={disabled}>资料库</button>
        </div>
      </form>
    </div>
  )
}
