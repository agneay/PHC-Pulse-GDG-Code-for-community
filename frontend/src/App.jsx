import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { NavLink, Route, Routes, useLocation } from 'react-router-dom'
import Icon from './components/Icon'
import { EngineTag, Loading } from './components/ui'
import { api, ensureToken, qs, setToken } from './lib/api'
import Command from './pages/Command'
import ModelPage from './pages/Model'
import Outbreaks from './pages/Outbreaks'
import PhcDetail from './pages/PhcDetail'
import Phone from './pages/Phone'
import Redistribution from './pages/Redistribution'
import Stock from './pages/Stock'
import VoiceReport from './pages/VoiceReport'

const Ctx = createContext(null)
export const useApp = () => useContext(Ctx)

export default function App() {
  const [meta, setMeta] = useState(null)
  const [filter, setFilter] = useState({ state: '', district: '' })
  const [version, setVersion] = useState(0)          // bump to refresh all pages after writes
  const [toast, setToast] = useState(null)
  const [askOpen, setAskOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const loc = useLocation()

  const loadMeta = useCallback(async () => {
    try {
      await ensureToken()
      setMeta(await api.get('/api/meta'))
    } catch {
      // A token signed with an old secret gets a 401 and is cleared by the API layer: sign in again.
      await ensureToken()
      setMeta(await api.get('/api/meta'))
    }
  }, [])
  useEffect(() => { loadMeta() }, [loadMeta])
  useEffect(() => { setMenuOpen(false) }, [loc.pathname])

  const notify = useCallback((msg) => {
    setToast(msg)
    setTimeout(() => setToast(null), 3200)
  }, [])

  const switchPersona = async (id) => {
    const r = await api.post('/api/auth/login', { persona_id: id })
    setToken(r.token)
    setFilter({ state: '', district: '' })
    await loadMeta()
    setVersion((v) => v + 1)
    notify(`Signed in as ${r.user.name}`)
  }

  const scopeQs = useMemo(() => qs(filter), [filter])
  const value = useMemo(() => ({
    meta, filter, setFilter, scopeQs, version, refresh: () => setVersion((v) => v + 1), notify,
  }), [meta, filter, scopeQs, version, notify])

  if (!meta) return <Loading label="Connecting to PHC Pulse…" />
  const user = meta.user
  const userScope = user.scope || {}
  const states = meta.states.filter((s) => !userScope.state || s.code === userScope.state)
  const districts = meta.districts.filter((d) =>
    (!userScope.district || d.code === userScope.district) &&
    (!(filter.state || userScope.state) || d.state === (filter.state || userScope.state)))

  return (
    <Ctx.Provider value={value}>
      <div className="shell">
        <aside className={`side ${menuOpen ? 'open' : ''}`}>
          <div className="brand">
            <div className="brand-mark"><Icon name="pulse" size={20} stroke={2.6} /></div>
            <div><b>PHC Pulse</b><small>A heartbeat for every health centre</small></div>
          </div>
          <div className="nav-sec">Officers</div>
          <NavLink className="nav" to="/" end><Icon name="grid" />Command centre</NavLink>
          <NavLink className="nav" to="/stock"><Icon name="pill" />Stock early warning</NavLink>
          <NavLink className="nav" to="/redistribution"><Icon name="truck" />Redistribution</NavLink>
          <NavLink className="nav" to="/outbreaks"><Icon name="bug" />Outbreak signals</NavLink>
          <div className="nav-sec">Health workers</div>
          <NavLink className="nav" to="/report"><Icon name="mic" />Voice report</NavLink>
          <NavLink className="nav" to="/phone"><Icon name="phone" />USSD · SMS · IVR</NavLink>
          <div className="nav-sec">Platform</div>
          <NavLink className="nav" to="/model"><Icon name="chip" />Models & HMIS</NavLink>
          <div className="side-foot">
            Pilot: 120 PHCs · 8 districts · 4 states<br />
            Data as of {meta.today}<br />
            Synthetic data modelled on HMIS
          </div>
        </aside>
        {menuOpen && <div className="drawer-bg" style={{ zIndex: 940 }} onClick={() => setMenuOpen(false)} />}
        <div className="main">
          <header className="topbar">
            <button className="menu-btn" onClick={() => setMenuOpen(true)} aria-label="Open menu"><Icon name="menu" /></button>
            <div>
              <div className="title">{user.name}</div>
              <div className="sub">{user.role === 'national' ? 'National view' : user.role === 'state' ? 'State view' : user.role === 'district' ? 'District view' : 'Facility view'} · row-level access by jurisdiction</div>
            </div>
            <div className="spacer" />
            {user.role !== 'phc' && !userScope.district && (
              <div className="row">
                {!userScope.state && (
                  <select className="select" value={filter.state} aria-label="State"
                    onChange={(e) => setFilter({ state: e.target.value, district: '' })}>
                    <option value="">All states</option>
                    {states.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
                  </select>
                )}
                <select className="select" value={filter.district} aria-label="District"
                  onChange={(e) => setFilter((f) => ({ ...f, district: e.target.value }))}>
                  <option value="">All districts</option>
                  {districts.map((d) => <option key={d.code} value={d.code}>{d.name}</option>)}
                </select>
              </div>
            )}
            <select className="select" value={meta.personas.find((p) => p.name === user.name)?.id || 'national'}
              onChange={(e) => switchPersona(e.target.value)} aria-label="Switch role" title="Demo: switch role">
              {meta.personas.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
            <EngineTag engine={meta.gemini.enabled ? meta.gemini.model : 'rules'} />
            <button className="btn primary sm" onClick={() => setAskOpen(true)}><Icon name="spark" size={15} />Ask Pulse</button>
          </header>
          <main className="content">
            <Routes>
              <Route path="/" element={<Command />} />
              <Route path="/stock" element={<Stock />} />
              <Route path="/redistribution" element={<Redistribution />} />
              <Route path="/outbreaks" element={<Outbreaks />} />
              <Route path="/report" element={<VoiceReport />} />
              <Route path="/phone" element={<Phone />} />
              <Route path="/model" element={<ModelPage />} />
              <Route path="/phc/:id" element={<PhcDetail />} />
            </Routes>
          </main>
        </div>
      </div>
      {askOpen && <AskDrawer onClose={() => setAskOpen(false)} />}
      {toast && <div className="toast">{toast}</div>}
    </Ctx.Provider>
  )
}

const SUGGESTIONS = [
  'Which PHCs will run out of ORS before their next supply?',
  'Summarise the outbreak signals and what stock they put at risk.',
  'Which transfers should I approve first today and why?',
  'मेरे ज़िले में सबसे कमज़ोर PHC कौन से हैं?',
]

function AskDrawer({ onClose }) {
  const { scopeQs, meta } = useApp()
  const [q, setQ] = useState('')
  const [msgs, setMsgs] = useState([])
  const [busy, setBusy] = useState(false)
  const send = async (text) => {
    const question = (text ?? q).trim()
    if (!question) return
    setQ('')
    setMsgs((m) => [...m, { role: 'u', text: question }])
    setBusy(true)
    try {
      const r = await api.post(`/api/ask${scopeQs}`, { question })
      setMsgs((m) => [...m, { role: 'a', text: r.answer, engine: r.engine }])
    } catch (e) {
      setMsgs((m) => [...m, { role: 'a', text: e.message }])
    } finally { setBusy(false) }
  }
  return (
    <>
      <div className="drawer-bg" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-label="Ask PHC Pulse">
        <div className="dh">
          <Icon name="spark" /><b>Ask PHC Pulse</b>
          <span className="pill ai">{meta.gemini.enabled ? meta.gemini.model : 'Gemini off'}</span>
          <button className="btn ghost sm" style={{ marginLeft: 'auto' }} onClick={onClose} aria-label="Close"><Icon name="x" /></button>
        </div>
        <div className="db">
          {!msgs.length && (
            <div className="stack">
              <div className="muted small">Gemini answers from the live snapshot of your jurisdiction: stock forecasts, outbreak clusters and the redistribution plan. You can ask in any Indian language.</div>
              {SUGGESTIONS.map((s) => <button key={s} className="btn" style={{ whiteSpace: 'normal', textAlign: 'left' }} onClick={() => send(s)}>{s}</button>)}
            </div>
          )}
          {msgs.map((m, i) => <div key={i} className={m.role === 'u' ? 'msg-u' : 'msg-a'}>{m.text}{m.engine && <div style={{ marginTop: 6 }}><EngineTag engine={m.engine} /></div>}</div>)}
          {busy && <div className="msg-a"><span className="spinner" /></div>}
        </div>
        <form className="df" onSubmit={(e) => { e.preventDefault(); send() }}>
          <input className="input" style={{ flex: 1 }} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask about stock, outbreaks, transfers…" />
          <button className="btn primary" disabled={busy}><Icon name="send" size={15} /></button>
        </form>
      </aside>
    </>
  )
}
