const BASE = '/api'

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new Error(detail.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

export function listScripts() {
  return request('/scripts')
}

export function createSession(scriptId, useLLM = true) {
  return request('/sessions', {
    method: 'POST',
    body: JSON.stringify({ script_id: scriptId, use_llm: useLLM }),
  })
}

export function listSessions() {
  return request('/sessions')
}

export function getSession(sessionId) {
  return request(`/sessions/${sessionId}`)
}

export function runTurn(sessionId, input) {
  return request(`/sessions/${sessionId}/turns`, {
    method: 'POST',
    body: JSON.stringify({ input }),
  })
}

export function runMeta(sessionId, command) {
  return request(`/sessions/${sessionId}/meta`, {
    method: 'POST',
    body: JSON.stringify({ command }),
  })
}

export function updateSession(sessionId, displayName) {
  return request(`/sessions/${sessionId}`, {
    method: 'PATCH',
    body: JSON.stringify({ display_name: displayName }),
  })
}

export function updateEntity(sessionId, entityId, patch) {
  return request(`/sessions/${sessionId}/entities/${entityId}`, {
    method: 'PATCH',
    body: JSON.stringify({ patch }),
  })
}

export function deleteSession(sessionId) {
  return request(`/sessions/${sessionId}/delete`, {
    method: 'POST',
  })
}

// ── Lorebook ──────────────────────────────────────────────────────

export function getLorebook(sessionId) {
  return request(`/sessions/${sessionId}/lorebook`)
}

export function createLoreEntry(sessionId, entry) {
  return request(`/sessions/${sessionId}/lorebook`, {
    method: 'POST',
    body: JSON.stringify(entry),
  })
}

export function updateLoreEntry(sessionId, entryId, patch) {
  return request(`/sessions/${sessionId}/lorebook/${entryId}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  })
}

export function deleteLoreEntry(sessionId, entryId) {
  return request(`/sessions/${sessionId}/lorebook/${entryId}`, {
    method: 'DELETE',
  })
}
