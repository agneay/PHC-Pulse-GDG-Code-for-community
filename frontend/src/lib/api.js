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
    const msg = (data && data.detail) || (typeof data === 'string' ? data : res.statusText)
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  return data
}

export const api = {
  get: (p) => request('GET', p),
  post: (p, b) => request('POST', p, b ?? {}),
  form: (p, fd) => request('POST', p, fd, { form: true }),
}

export function qs(obj) {
  const s = new URLSearchParams()
  Object.entries(obj).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') s.set(k, v) })
  const str = s.toString()
  return str ? `?${str}` : ''
}
