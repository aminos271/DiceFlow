import { useState, useEffect, useCallback } from 'react'
import { listWorlds, createSession, listSessions, createWorld } from './api.js'
import ScriptSelect from './pages/ScriptSelect.jsx'
import GamePage from './pages/GamePage.jsx'
import SessionHistory from './components/SessionHistory.jsx'
import WorldCreateModal from './components/WorldCreateModal.jsx'

export default function App() {
  const [view, setView] = useState('select')
  const [worlds, setWorlds] = useState([])
  const [sessionId, setSessionId] = useState(null)
  const [sessionTitle, setSessionTitle] = useState('')
  const [sessions, setSessions] = useState([])
  const [showHistory, setShowHistory] = useState(false)
  const [showCreateWorld, setShowCreateWorld] = useState(false)

  useEffect(() => {
    listWorlds().then(setWorlds).catch(console.error)
    refreshSessions()
  }, [])

  const refreshSessions = useCallback(() => {
    listSessions().then(setSessions).catch(console.error)
  }, [])

  const handleSelectWorld = async (worldId, title) => {
    try {
      const data = await createSession({ world_id: worldId })
      setSessionId(data.session_id)
      setSessionTitle(title)
      setView('game')
      refreshSessions()
    } catch (err) {
      alert(`创建失败: ${err.message}`)
    }
  }

  const handleBackToSelect = () => {
    setView('select')
    setSessionId(null)
    setSessionTitle('')
    refreshSessions()
  }

  const handleViewSession = (sid, title) => {
    setSessionId(sid)
    setSessionTitle(title)
    setView('game')
    setShowHistory(false)
  }

  const handleCreateWorld = async (payload, startAfterCreate = false) => {
    const res = await createWorld(payload)
    const world = res.world
    await listWorlds().then(setWorlds)
    setShowCreateWorld(false)
    if (startAfterCreate && world?.id) {
      await handleSelectWorld(world.id, world.title || world.id)
    }
  }

  if (view === 'game' && sessionId) {
    return (
      <>
        <GamePage
          sessionId={sessionId}
          scriptTitle={sessionTitle}
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
            onNewGame={(worldId, title) => { setShowHistory(false); handleSelectWorld(worldId, title) }}
            onRefresh={refreshSessions}
            onDeleteActive={handleBackToSelect}
          />
        )}
      </>
    )
  }

  return (
    <>
      <ScriptSelect
        worlds={worlds}
        sessions={sessions}
        onSelectWorld={handleSelectWorld}
        onContinue={handleViewSession}
        onOpenCreateWorld={() => setShowCreateWorld(true)}
      />
      <WorldCreateModal
        open={showCreateWorld}
        onClose={() => setShowCreateWorld(false)}
        onCreate={handleCreateWorld}
      />
    </>
  )
}
