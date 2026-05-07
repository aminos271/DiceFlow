import { useState, useEffect, useCallback, useRef } from 'react'
import { getSession, runTurn, updateEntity } from '../api.js'
import TurnHistory from '../components/TurnHistory.jsx'
import StatusSidebar from '../components/StatusSidebar.jsx'
import InputBar from '../components/InputBar.jsx'
import PopupOverlay from '../components/PopupOverlay.jsx'
import LorebookPanel from '../components/LorebookPanel.jsx'

const PROGRESS_STEPS = [
  { delay: 0, text: '解析行动中...' },
  { delay: 300, text: '判定中...' },
  { delay: 800, text: '生成叙事中...' },
]

export default function GamePage({ sessionId, scriptTitle, onBack, onOpenHistory, onSessionEnded }) {
  const [turns, setTurns] = useState([])
  const [status, setStatus] = useState(null)
  const [isGameOver, setIsGameOver] = useState(false)
  const [ending, setEnding] = useState(null)
  const [sending, setSending] = useState(false)
  const [pendingStatus, setPendingStatus] = useState('')
  const [selectedEntity, setSelectedEntity] = useState(null)
  const [panel, setPanel] = useState(null) // { type: 'skills'|'status'|'backpack' }
  const [inputDraft, setInputDraft] = useState('')
  const [inputFocusToken, setInputFocusToken] = useState(0)
  const timersRef = useRef([])

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

  useEffect(() => {
    // Cleanup timers on unmount
    return () => timersRef.current.forEach(clearTimeout)
  }, [])

  // Clear selected entity when it no longer exists in known_entities
  useEffect(() => {
    if (selectedEntity && status?.known_entities) {
      const stillExists = status.known_entities.some(e => e.id === selectedEntity.id)
      if (!stillExists) setSelectedEntity(null)
    }
  }, [status?.known_entities, selectedEntity])

  const clearTimers = () => {
    timersRef.current.forEach(clearTimeout)
    timersRef.current = []
  }

  const handleSend = useCallback(async (input) => {
    setSending(true)
    clearTimers()
    // Start progress simulation
    PROGRESS_STEPS.forEach(({ delay, text }) => {
      const id = setTimeout(() => setPendingStatus(text), delay)
      timersRef.current.push(id)
    })
    try {
      const data = await runTurn(sessionId, input)
      clearTimers()
      setPendingStatus('')
      setInputDraft('')
      setTurns((prev) => [...prev, data.turn])
      setStatus(data.status || null)
      if (data.is_game_over) {
        setIsGameOver(true)
        setEnding(data.ending || null)
        onSessionEnded()
      }
    } catch (err) {
      clearTimers()
      setPendingStatus('')
      alert(`行动失败: ${err.message}`)
    } finally {
      setSending(false)
    }
  }, [sessionId, onSessionEnded])

  const handleOpenPanel = useCallback((panelType) => {
    setPanel({ type: panelType })
  }, [])

  const handleClosePanel = useCallback(() => {
    setPanel(null)
  }, [])

  const handleEntityEdit = useCallback(async (sid, entityId, patch) => {
    await updateEntity(sid, entityId, patch)
    // Refresh status to get updated known_entities
    const data = await getSession(sessionId)
    setStatus(data.status || null)
    setSelectedEntity(null)
  }, [sessionId])

  const handleSelectEntity = useCallback((entityIdOrName) => {
    if (!status?.known_entities) return
    let found = status.known_entities.find(e => e.id === entityIdOrName)
    if (!found) {
      found = status.known_entities.find(e => e.name === entityIdOrName)
    }
    if (found) {
      setSelectedEntity(prev => prev?.id === found.id ? null : found)
    }
  }, [status?.known_entities])

  const handlePickHint = useCallback((command) => {
    if (!command || sending || isGameOver) return
    setInputDraft(command)
    setInputFocusToken(token => token + 1)
  }, [sending, isGameOver])

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
        <button onClick={() => handleOpenPanel('lorebook')}>📚 资料库</button>
        <button onClick={onOpenHistory}>📋 历史</button>
        <button onClick={onBack}>← 返回</button>
      </div>

      <div className="game-content">
        <TurnHistory turns={turns} />
        <StatusSidebar
          status={status}
          selectedEntity={selectedEntity}
          onSelectEntity={handleSelectEntity}
          sessionId={sessionId}
          onEditEntity={handleEntityEdit}
          onPickHint={handlePickHint}
        />
      </div>

      {isGameOver ? (
        <div className="game-over-overlay">
          <span className="ending">结局: {endingLabel(ending)}</span>
          <button onClick={onBack}>← 返回选剧本</button>
        </div>
      ) : (
        <InputBar
          onSend={handleSend}
          onOpenPanel={handleOpenPanel}
          value={inputDraft}
          onChange={setInputDraft}
          focusToken={inputFocusToken}
          disabled={sending}
          pendingStatus={pendingStatus}
          gameOver={isGameOver}
        />
      )}

      <PopupOverlay
        type={panel?.type}
        status={status}
        sessionId={sessionId}
        onClose={handleClosePanel}
        onEditEntity={handleEntityEdit}
      />
    </div>
  )
}
