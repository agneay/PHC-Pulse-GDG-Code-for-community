const TOKEN_KEY = 'phcpulse.token'

function token() {
  try { return localStorage.getItem(TOKEN_KEY) } catch { return null }
}

export function setToken(t) {
  try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY) } catch { /* private mode */ }
}

async function request(method, path, body, { form = false } = {}) {
  const headers = {}
  const t = token()
  if (t) headers.Authorization = `Bearer ${t}`
  let payload
  if (form) payload = body
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  const res = await fetch(path, { method, headers, body: payload })
  if (res.status === 401) { setToken(null) }
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
  const t = token()
  const res = await fetch('/api/tts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(t ? { Authorization: `Bearer ${t}` } : {}) },
    body: JSON.stringify({ text, language }),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail || `Read-aloud failed (${res.status})`)
  }
  return res.blob()
}

// Write endpoints require a signed token. Start the demo as the national persona.
export async function ensureToken() {
  if (token()) return
  const r = await api.post('/api/auth/login', { persona_id: 'national' })
  setToken(r.token)
}

// File downloads go through fetch (not a plain link) so the Authorization header, and thus the
// caller's jurisdiction, applies to the export too.
export async function download(path, filename) {
  const t = token()
  const res = await fetch(path, { headers: t ? { Authorization: `Bearer ${t}` } : {} })
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
