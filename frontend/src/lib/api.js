const TOKEN_KEY = 'phcpulse.token'
const PERSONA_KEY = 'phcpulse.persona'

const load = (k) => { try { return localStorage.getItem(k) } catch { return null } }
const save = (k, v) => { try { v ? localStorage.setItem(k, v) : localStorage.removeItem(k) } catch { /* private mode */ } }
const token = () => load(TOKEN_KEY)

export function setToken(t) { save(TOKEN_KEY, t) }

/** Sign in as a demo persona; remembered so an expired session can be renewed transparently. */
export async function signIn(personaId) {
  const res = await fetch('/api/auth/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ persona_id: personaId }),
  })
  if (!res.ok) throw new Error(`Sign-in failed (${res.status})`)
  const r = await res.json()
  setToken(r.token)
  save(PERSONA_KEY, personaId)
  return r
}

// Write endpoints require a signed token. Start the demo as the national persona.
export async function ensureToken() {
  if (!token()) await signIn(load(PERSONA_KEY) || 'national')
}

async function authFetch(path, init = {}, retried = false) {
  const t = token()
  const res = await fetch(path, { ...init, headers: { ...(init.headers || {}), ...(t ? { Authorization: `Bearer ${t}` } : {}) } })
  if (res.status === 401 && !retried) {
    // Tokens expire after a shift: renew as the same persona and repeat the request once.
    setToken(null)
    await signIn(load(PERSONA_KEY) || 'national')
    return authFetch(path, init, true)
  }
  return res
}

async function request(method, path, body, { form = false } = {}) {
  const headers = {}
  let payload
  if (form) payload = body
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  const res = await authFetch(path, { method, headers, body: payload })
  const ct = res.headers.get('content-type') || ''
  const data = ct.includes('json') ? await res.json() : await res.text()
  if (!res.ok) {
    const detail = data && data.detail
    const msg = detail?.message || detail || (typeof data === 'string' ? data : res.statusText)
    const err = new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
    err.status = res.status
    err.detail = detail
    throw err
  }
  return data
}

export const api = {
  get: (p) => request('GET', p),
  post: (p, b) => request('POST', p, b ?? {}),
  form: (p, fd) => request('POST', p, fd, { form: true }),
}

// Read-aloud audio (Gemini TTS) for devices without a voice in the language.
export async function ttsAudio(text, language) {
  const res = await authFetch('/api/tts', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text, language }),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail || `Read-aloud failed (${res.status})`)
  }
  return res.blob()
}

// File downloads go through fetch (not a plain link) so the Authorization header, and thus the
// caller's jurisdiction, applies to the export too.
export async function download(path, filename) {
  const res = await authFetch(path)
  if (!res.ok) throw new Error(`Download failed (${res.status})`)
  const url = URL.createObjectURL(await res.blob())
  const a = document.createElement('a')
  a.href = url; a.download = filename
  document.body.appendChild(a); a.click(); a.remove()
  URL.revokeObjectURL(url)
}

export function qs(obj) {
  const s = new URLSearchParams()
  Object.entries(obj).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') s.set(k, v) })
  const str = s.toString()
  return str ? `?${str}` : ''
}
