import { useState, useEffect, useCallback } from 'react'
import { listScripts, listWorlds, createSession, listSessions } from './api.js'
import ScriptSelect from './pages/ScriptSelect.jsx'
import GamePage from './pages/GamePage.jsx'
import SessionHistory from './components/SessionHistory.jsx'

export default function App() {
  const [view, setView] = useState('select')
  const [scripts, setScripts] = useState([])
  const [worlds, setWorlds] = useState([])
  const [sessionId, setSessionId] = useState(null)
  const [scriptTitle, setScriptTitle] = useState('')
  const [sessions, setSessions] = useState([])
  const [showHistory, setShowHistory] = useState(false)

  useEffect(() => {
    listScripts().then(setScripts).catch(console.error)
    listWorlds().then(setWorlds).catch(console.error)
    refreshSessions()
  }, [])

  const refreshSessions = useCallback(() => {
    listSessions().then(setSessions).catch(console.error)
  }, [])

  const handleSelectScript = async (scriptId, title) => {
    try {
      const data = await createSession(scriptId)
      setSessionId(data.session_id)
      setScriptTitle(title)
      setView('game')
      refreshSessions()
    } catch (err) {
      alert(`创建失败: ${err.message}`)
    }
  }

  const handleSelectWorld = async (worldId, title) => {
    try {
      const data = await createSession({ world_id: worldId })
      setSessionId(data.session_id)
      setScriptTitle(title)
      setView('game')
      refreshSessions()
    } catch (err) {
      alert(`创建失败: ${err.message}`)
    }
  }

  const handleBackToSelect = () => {
    setView('select')
    setSessionId(null)
    setScriptTitle('')
    refreshSessions()
  }

  const handleViewSession = (sid, title) => {
    setSessionId(sid)
    setScriptTitle(title)
    setView('game')
    setShowHistory(false)
  }

  const handleRestartScript = (scriptId, title) => {
    setShowHistory(false)
    handleSelectScript(scriptId, title)
  }

  if (view === 'game' && sessionId) {
    return (
      <>
        <GamePage
          sessionId={sessionId}
          scriptTitle={scriptTitle}
          onBack={handleBackToSelect}
          onOpenHistory={() => { refreshSessions(); setShowHistory(true) }}
          onSessionEnded={refreshSessions}
        />
        {showHistory && (
          <SessionHistory
            sessions={sessions}
            activeSessionId={sessionId}
            onClose={() => setShowHistory(false)}
            onSelect={handleViewSession}
            onNewGame={(sid) => { setShowHistory(false); handleSelectScript(sid, scripts.find(s => s.id === sid)?.title || sid) }}
            onRefresh={refreshSessions}
            onDeleteActive={handleBackToSelect}
          />
        )}
      </>
    )
  }

  return (
    <ScriptSelect
      scripts={scripts}
      worlds={worlds}
      sessions={sessions}
      onSelectScript={handleSelectScript}
      onSelectWorld={handleSelectWorld}
      onContinue={handleViewSession}
    />
  )
}
