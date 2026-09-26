import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { NavLink, Route, Routes, useLocation } from 'react-router-dom'
import Icon from './components/Icon'
import LanguageGate from './components/LanguageGate'
import Tour, { TourOffer } from './components/Tour'
import { EngineTag, Loading } from './components/ui'
import { FONT_STEPS, UI_LANGS, useI18n } from './i18n'
import { api, ensureToken, qs, signIn } from './lib/api'
import { personaName } from './lib/labels'
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
  const { t } = useI18n()
  const [meta, setMeta] = useState(null)
  const [filter, setFilter] = useState({ state: '', district: '' })
  const [version, setVersion] = useState(0)          // bump to refresh all pages after writes
  const [toast, setToast] = useState(null)
  const [askOpen, setAskOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [touring, setTouring] = useState(false)
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
    setTimeout(() => setToast(null), 4000)
  }, [])

  const switchPersona = async (id) => {
    const r = await signIn(id)
    setFilter({ state: '', district: '' })
    await loadMeta()
    setVersion((v) => v + 1)
    notify(t('toast.signedIn', { name: personaName(r.user, t, meta) }))
  }

  const scopeQs = useMemo(() => qs(filter), [filter])
  const value = useMemo(() => ({
    meta, filter, setFilter, scopeQs, version, refresh: () => setVersion((v) => v + 1), notify,
  }), [meta, filter, scopeQs, version, notify])

  if (!meta) return <><Loading label={t('common.connecting')} /><LanguageGate /></>
  const user = meta.user
  const userScope = user.scope || {}
  const states = meta.states.filter((s) => !userScope.state || s.code === userScope.state)
  const districts = meta.districts.filter((d) =>
    (!userScope.district || d.code === userScope.district) &&
    (!(filter.state || userScope.state) || d.state === (filter.state || userScope.state)))

  return (
    <Ctx.Provider value={value}>
      <div className="shell">
        <aside className={`side ${menuOpen ? 'open' : ''}`} data-tour="nav">
          <div className="brand">
            <div className="brand-mark"><Icon name="pulse" size={20} stroke={2.6} /></div>
            <div><b>PHC Pulse</b><small>{t('brand.tagline')}</small></div>
          </div>
          <div className="nav-sec">{t('nav.officers')}</div>
          <NavLink className="nav" to="/" end><Icon name="grid" />{t('nav.command')}</NavLink>
          <NavLink className="nav" to="/stock"><Icon name="pill" />{t('nav.stock')}</NavLink>
          <NavLink className="nav" to="/redistribution"><Icon name="truck" />{t('nav.redistribution')}</NavLink>
          <NavLink className="nav" to="/outbreaks"><Icon name="bug" />{t('nav.outbreaks')}</NavLink>
          <div className="nav-sec">{t('nav.workers')}</div>
          <NavLink className="nav" to="/report"><Icon name="mic" />{t('nav.report')}</NavLink>
          <NavLink className="nav" to="/phone"><Icon name="phone" />{t('nav.phone')}</NavLink>
          <div className="nav-sec">{t('nav.platform')}</div>
          <NavLink className="nav" to="/model"><Icon name="chip" />{t('nav.model')}</NavLink>
          <div className="side-foot">
            {t('side.pilot')}<br />
            {t('side.asof', { date: meta.today })}<br />
            {t('side.synthetic')}
          </div>
        </aside>
        {menuOpen && <div className="drawer-bg" style={{ zIndex: 940 }} onClick={() => setMenuOpen(false)} />}
        <div className="main">
          <header className="topbar">
            <button className="menu-btn" onClick={() => setMenuOpen(true)} aria-label={t('topbar.menu')} data-tour="menu"><Icon name="menu" /></button>
            <div>
              <div className="title">{personaName(user, t, meta)}</div>
              <div className="sub">{t(`view.${user.role}`)} · {t('topbar.rls')}</div>
            </div>
            <div className="spacer" />
            {user.role !== 'phc' && !userScope.district && (
              <div className="row">
                {!userScope.state && (
                  <select className="select" value={filter.state} aria-label={t('filter.state')}
                    onChange={(e) => setFilter({ state: e.target.value, district: '' })}>
                    <option value="">{t('filter.allStates')}</option>
                    {states.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
                  </select>
                )}
                <select className="select" value={filter.district} aria-label={t('filter.district')}
                  onChange={(e) => setFilter((f) => ({ ...f, district: e.target.value }))}>
                  <option value="">{t('filter.allDistricts')}</option>
                  {districts.map((d) => <option key={d.code} value={d.code}>{d.name}</option>)}
                </select>
              </div>
            )}
            <select className="select" value={meta.personas.find((p) => p.name === user.name)?.id || 'national'}
              onChange={(e) => switchPersona(e.target.value)} aria-label={t('topbar.role')} title={t('topbar.roleTitle')} data-tour="role">
              {meta.personas.map((p) => <option key={p.id} value={p.id}>{personaName(p, t, meta)}</option>)}
            </select>
            <DisplaySettings />
            <EngineTag engine={meta.gemini.enabled ? meta.gemini.model : 'rules'} />
            <HelpMenu onTour={() => { setMenuOpen(false); setTouring(true) }} />
            <button className="btn primary sm" onClick={() => setAskOpen(true)} data-tour="ask"><Icon name="spark" size={15} />{t('topbar.ask')}</button>
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
      {toast && <div className="toast" role="status">{toast}</div>}
      <LanguageGate />
      {touring ? <Tour onClose={() => setTouring(false)} /> : <TourOffer onStart={() => setTouring(true)} />}
    </Ctx.Provider>
  )
}

/** Language switcher and text size, always in the top bar. */
function DisplaySettings() {
  const { t, lang, setLang, fontScale, stepFont } = useI18n()
  return (
    <div className="row settings" role="group" aria-label={t('settings.label')} data-tour="display">
      <label className="lang-pick" title={t('settings.language')}>
        <Icon name="globe" size={15} />
        <select className="select" value={lang} onChange={(e) => setLang(e.target.value)} aria-label={t('settings.language')}>
          {Object.entries(UI_LANGS).map(([c, l]) => <option key={c} value={c} lang={c}>{l.native}</option>)}
        </select>
      </label>
      <div className="font-size" role="group" aria-label={t('settings.textSize')}>
        <button className="btn sm" onClick={() => stepFont(-1)} disabled={fontScale === FONT_STEPS[0]}
          aria-label={t('settings.smaller')} title={t('settings.smaller')}>A<span aria-hidden="true">−</span></button>
        <button className="btn sm big" onClick={() => stepFont(1)} disabled={fontScale === FONT_STEPS.at(-1)}
          aria-label={t('settings.larger')} title={t('settings.larger')}>A<span aria-hidden="true">+</span></button>
      </div>
    </div>
  )
}

/** Help button: the guided tour for beginners, plus the API docs for integrators. */
function HelpMenu({ onTour }) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  useEffect(() => {
    if (!open) return
    const away = (e) => { if (!ref.current?.contains(e.target)) setOpen(false) }
    const esc = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('pointerdown', away)
    document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('pointerdown', away); document.removeEventListener('keydown', esc) }
  }, [open])
  return (
    <div className="help" ref={ref} data-tour="help">
      <button className="btn sm" onClick={() => setOpen((o) => !o)} aria-haspopup="menu" aria-expanded={open}>
        <Icon name="help" size={15} />{t('help.title')}
      </button>
      {open && (
        <div className="help-menu" role="menu">
          <button role="menuitem" onClick={() => { setOpen(false); onTour() }} autoFocus>
            <Icon name="flag" size={17} />
            <span><b>{t('help.tour')}</b><small>{t('help.tourSub')}</small></span>
          </button>
          <a role="menuitem" href="/docs" target="_blank" rel="noreferrer" onClick={() => setOpen(false)}>
            <Icon name="chip" size={17} />
            <span><b>{t('help.docs')}</b><small>{t('help.docsSub')}</small></span>
          </a>
        </div>
      )}
    </div>
  )
}

function AskDrawer({ onClose }) {
  const { scopeQs, meta } = useApp()
  const { t, lang } = useI18n()
  const [q, setQ] = useState('')
  const [msgs, setMsgs] = useState([])
  const [busy, setBusy] = useState(false)
  const suggestions = [t('ask.s1'), t('ask.s2'), t('ask.s3'), t('ask.s4')]
  const send = async (text) => {
    const question = (text ?? q).trim()
    if (!question) return
    setQ('')
    setMsgs((m) => [...m, { role: 'u', text: question }])
    setBusy(true)
    try {
      const r = await api.post(`/api/ask${scopeQs}`, { question, language: lang })
      setMsgs((m) => [...m, { role: 'a', text: r.answer, engine: r.engine }])
    } catch (e) {
      setMsgs((m) => [...m, { role: 'a', text: e.message }])
    } finally { setBusy(false) }
  }
  return (
    <>
      <div className="drawer-bg" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-label={t('ask.title')}>
        <div className="dh">
          <Icon name="spark" /><b>{t('ask.title')}</b>
          <span className="pill ai">{meta.gemini.enabled ? meta.gemini.model : t('ask.off')}</span>
          <button className="btn ghost sm" style={{ marginLeft: 'auto' }} onClick={onClose} aria-label={t('common.close')}><Icon name="x" /></button>
        </div>
        <div className="db">
          {!msgs.length && (
            <div className="stack">
              <div className="muted small">{t('ask.intro')}</div>
              {suggestions.map((s) => <button key={s} className="btn" style={{ whiteSpace: 'normal', textAlign: 'left' }} onClick={() => send(s)}>{s}</button>)}
            </div>
          )}
          {msgs.map((m, i) => <div key={i} className={m.role === 'u' ? 'msg-u' : 'msg-a'}>{m.text}{m.engine && <div style={{ marginTop: 6 }}><EngineTag engine={m.engine} /></div>}</div>)}
          {busy && <div className="msg-a"><span className="spinner" /></div>}
        </div>
        <form className="df" onSubmit={(e) => { e.preventDefault(); send() }}>
          <input className="input" style={{ flex: 1 }} value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('ask.placeholder')} aria-label={t('ask.placeholder')} />
          <button className="btn primary" disabled={busy} aria-label={t('ask.send')}><Icon name="send" size={15} /></button>
        </form>
      </aside>
    </>
  )
}
