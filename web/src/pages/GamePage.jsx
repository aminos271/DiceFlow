import { useState, useEffect, useCallback } from 'react'
import { getSession, runTurn, runMeta } from '../api.js'
import TurnHistory from '../components/TurnHistory.jsx'
import StatusSidebar from '../components/StatusSidebar.jsx'
import InputBar from '../components/InputBar.jsx'

export default function GamePage({ sessionId, scriptTitle, onBack, onOpenHistory, onSessionEnded }) {
  const [turns, setTurns] = useState([])
  const [status, setStatus] = useState(null)
  const [isGameOver, setIsGameOver] = useState(false)
  const [ending, setEnding] = useState(null)
  const [sending, setSending] = useState(false)

  useEffect(() => {
    getSession(sessionId)
      .then((data) => {
        setTurns(data.turn_history || [])
        setStatus(data.status || null)
        setIsGameOver(data.is_game_over || false)
        setEnding(data.ending || null)
      })
      .catch(console.error)
  }, [sessionId])

  const handleSend = useCallback(async (input) => {
    setSending(true)
    try {
      const data = await runTurn(sessionId, input)
      setTurns((prev) => [...prev, data.turn])
      setStatus(data.status || null)
      if (data.is_game_over) {
        setIsGameOver(true)
        setEnding(data.ending || null)
        onSessionEnded()
      }
    } catch (err) {
      alert(`行动失败: ${err.message}`)
    } finally {
      setSending(false)
    }
  }, [sessionId, onSessionEnded])

  const handleMeta = useCallback(async (command) => {
    try {
      const data = await runMeta(sessionId, command)
      if (data.result) {
        setTurns((prev) => [
          ...prev,
          {
            turn_id: `meta-${Date.now()}`,
            player_input: `/${command}`,
            check: null,
            narration: data.result,
          },
        ])
      }
      if (data.status) {
        setStatus(data.status)
        setIsGameOver(data.status.is_game_over || false)
        setEnding(data.status.ending || null)
      }
    } catch (err) {
      alert(`查看失败: ${err.message}`)
    }
  }, [sessionId])

  const endingLabel = (e) => {
    if (!e) return ''
    if (e === 'victory') return '胜利！'
    if (e === 'death') return '死亡...'
    if (e === 'timeout') return '20 轮耗尽'
    return e
  }

  return (
    <div className="game-page">
      <div className="top-bar">
        <span className="logo">🎲 DiceFlow</span>
        <span className="script-name">{scriptTitle}</span>
        <span className="spacer" />
        <button onClick={onOpenHistory}>📋 历史</button>
        <button onClick={onBack}>← 返回</button>
      </div>

      <div className="game-content">
        <TurnHistory turns={turns} />
        <StatusSidebar status={status} />
      </div>

      {isGameOver ? (
        <div className="game-over-overlay">
          <span className="ending">结局: {endingLabel(ending)}</span>
          <button onClick={onBack}>← 返回选剧本</button>
        </div>
      ) : (
        <InputBar
          onSend={handleSend}
          onMeta={handleMeta}
          disabled={sending}
          gameOver={isGameOver}
        />
      )}
    </div>
  )
}
