import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useApp } from '../App'
import { useI18n } from '../i18n'
import { rich } from '../lib/format'
import Icon from './Icon'
import { SpeakButton } from './Speak'

// One stop per idea, in the order a new officer or health worker meets them. `target` is a
// data-tour anchor on the page, or a list tried in order (the first visible one wins, e.g. the
// menu button on phones where the sidebar is hidden); null = centred card. `route` opens first.
export const TOUR_STEPS = [
  { id: 'welcome', target: null },
  { id: 'nav', target: ['nav', 'menu'] },
  { id: 'role', target: 'role' },
  { id: 'display', target: 'display' },
  { id: 'kpis', route: '/', target: 'kpis' },
  { id: 'map', route: '/', target: 'map' },
  { id: 'briefing', route: '/', target: 'briefing' },
  { id: 'impact', route: '/', target: 'impact', officers: true },
  { id: 'ask', target: 'ask' },
  { id: 'stock', route: '/stock', target: 'stock-matrix' },
  { id: 'warnings', route: '/stock', target: 'stock-warnings' },
  { id: 'redis', route: '/redistribution', target: 'redis-recs' },
  { id: 'tracker', route: '/redistribution', target: 'redis-tracker' },
  { id: 'outbreaks', route: '/outbreaks', target: 'outbreaks' },
  { id: 'emergency', route: '/emergency', target: 'emergency', officers: true },
  { id: 'voiceWho', route: '/report', target: 'voice-who' },
  { id: 'voiceSpeak', route: '/report', target: 'voice-speak' },
  { id: 'phone', route: '/phone', target: 'phone' },
  { id: 'model', route: '/model', target: 'model-pipeline' },
  { id: 'done', target: 'help' },
]

const DONE_KEY = 'phcpulse.tourDone'
export const tourDone = () => { try { return !!localStorage.getItem(DONE_KEY) } catch { return true } }
const markDone = () => { try { localStorage.setItem(DONE_KEY, '1') } catch { /* private mode */ } }

const PAD = 8          // breathing room around the highlighted element
const GAP = 14         // distance between the highlight and the step card

const targets = (target) => (Array.isArray(target) ? target : [target]).filter(Boolean)
const narrow = () => innerWidth < 640

function visible(el) {
  const r = el.getBoundingClientRect()
  return r.width >= 4 && r.height >= 4 && r.right > 0 && r.left < innerWidth
}

/** First rendered anchor for the step (visible or not yet scrolled into view). */
function findEl(target) {
  for (const t of targets(target)) {
    const el = document.querySelector(`[data-tour="${t}"]`)
    if (el && visible(el)) return el
  }
  return null
}

/** Box around the step's anchor, or null when it is missing or hidden (e.g. the sidebar on a
 *  phone), in which case the step card is centred instead. */
function findBox(target) {
  const el = findEl(target)
  if (!el) return null
  const r = el.getBoundingClientRect()
  return { top: r.top - PAD, left: r.left - PAD, width: r.width + PAD * 2, height: r.height + PAD * 2 }
}

export default function Tour({ onClose }) {
  const { t, lang, rtl } = useI18n()
  const { meta } = useApp()
  const steps = TOUR_STEPS.filter((s) => !s.officers || meta.user.role !== 'phc')
  const navigate = useNavigate()
  const loc = useLocation()
  const [i, setI] = useState(0)
  const [box, setBox] = useState(null)
  const [ready, setReady] = useState(false)
  const card = useRef(null)
  const next = useRef(null)
  const [cardH, setCardH] = useState(220)
  const step = steps[i]
  const last = i === steps.length - 1

  const close = useCallback(() => { markDone(); onClose() }, [onClose])
  const go = useCallback((d) => setI((n) => Math.max(0, Math.min(steps.length - 1, n + d))), [])

  // Open the step's page, wait for its anchor to render (pages load data first), then scroll it
  // into view. Falls back to a centred card after ~4 s so the tour never gets stuck.
  useEffect(() => {
    if (step.route && loc.pathname !== step.route) { navigate(step.route); return }
    setReady(false)
    setBox(null)
    let tries = 0, timer
    const look = () => {
      const el = findEl(step.target)
      if (el || !step.target || tries++ > 40) {
        // Leave room for the top bar while it is sticky, and on phones bring the top of big
        // elements up since the step card docks at the bottom.
        const bar = document.querySelector('.topbar')
        const barH = bar && getComputedStyle(bar).position === 'sticky' ? bar.offsetHeight : 0
        if (el) el.style.scrollMarginTop = `${barH + 12}px`
        // Instant jump (smooth scrolling is unreliable in some webviews); the highlight animates.
        el?.scrollIntoView({ block: narrow() && el.offsetHeight > innerHeight / 3 ? 'start' : 'center' })
        timer = setTimeout(() => { setBox(findBox(step.target)); setReady(true) }, el ? 60 : 0)
        return
      }
      timer = setTimeout(look, 100)
    }
    look()
    return () => clearTimeout(timer)
  }, [step, loc.pathname, navigate])

  // Keep the highlight glued to its element while the page scrolls or resizes.
  useEffect(() => {
    if (!ready) return
    let raf = 0
    const update = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(() => setBox(findBox(step.target))) }
    addEventListener('resize', update)
    addEventListener('scroll', update, true)
    return () => { cancelAnimationFrame(raf); removeEventListener('resize', update); removeEventListener('scroll', update, true) }
  }, [ready, step])

  useEffect(() => {
    const onKey = (e) => {   // Enter/Space are left to the focused button
      if (e.key === 'Escape') { close(); return }
      if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return
      e.preventDefault()
      const forward = (e.key === 'ArrowRight') !== rtl      // arrows follow the reading direction
      if (forward && last) close()
      else go(forward ? 1 : -1)
    }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [close, go, last, rtl])

  useLayoutEffect(() => {
    if (ready && card.current) { setCardH(card.current.offsetHeight); next.current?.focus({ preventScroll: true }) }
  }, [ready, i, lang])

  // Card below the highlight when it fits, else above, else beside, else centred. On phones it
  // docks to the bottom edge (or the top when the highlight sits low on the screen).
  const W = Math.min(380, innerWidth - 24)
  let pos = { top: Math.max(12, (innerHeight - cardH) / 2), left: (innerWidth - W) / 2 }
  if (box && narrow()) {
    const low = box.top > innerHeight / 2
    pos = { top: low ? 12 : innerHeight - cardH - 12, left: (innerWidth - W) / 2 }
  } else if (box) {
    const left = Math.max(16, Math.min(innerWidth - W - 16, box.left + box.width / 2 - W / 2))
    if (box.top + box.height + GAP + cardH < innerHeight - 8) pos = { top: box.top + box.height + GAP, left }
    else if (box.top - GAP - cardH > 8) pos = { top: box.top - GAP - cardH, left }
    else if (box.left + box.width + GAP + W < innerWidth - 8) pos = { top: Math.max(16, Math.min(innerHeight - cardH - 16, box.top)), left: box.left + box.width + GAP }
    else if (box.left - GAP - W > 8) pos = { top: Math.max(16, Math.min(innerHeight - cardH - 16, box.top)), left: box.left - GAP - W }
  }

  const title = t(`tour.${step.id}.t`)
  const body = t(`tour.${step.id}.b`)
  return (
    <div className="tour" aria-live="polite">
      {/* Clicks outside the card are swallowed so a beginner can't wander off mid-step. */}
      <div className="tour-block" onClick={(e) => e.stopPropagation()} />
      {box ? <div className="tour-hole" style={{ top: box.top, left: box.left, width: box.width, height: box.height }} />
        : <div className="tour-dim" />}
      <div ref={card} className="tour-card" role="dialog" aria-modal="true" aria-label={t('tour.label')} tabIndex={-1}
        style={{ top: pos.top, left: pos.left, width: W, visibility: ready ? 'visible' : 'hidden' }}>
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <span className="eyebrow">{t('tour.step', { n: i + 1, total: steps.length })}</span>
          <div className="row" style={{ gap: 2 }}>
            <SpeakButton text={`${title}. ${body.replaceAll('**', '')}`} language={lang} />
            <button className="btn ghost sm" onClick={close} aria-label={t('tour.skip')} title={t('tour.skip')}><Icon name="x" size={15} /></button>
          </div>
        </div>
        <h3>{title}</h3>
        <p>{rich(body)}</p>
        <div className="tour-dots" aria-hidden="true">
          {steps.map((s, k) => <span key={s.id} className={k === i ? 'on' : k < i ? 'seen' : ''} />)}
        </div>
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <button className="linkish small" onClick={close}>{t('tour.skip')}</button>
          <div className="row" style={{ gap: 6 }}>
            {i > 0 && <button className="btn sm" onClick={() => go(-1)}>{t('tour.back')}</button>}
            <button ref={next} className="btn primary sm" onClick={() => (last ? close() : go(1))}>
              {last ? t('tour.finish') : t('tour.next')}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

/** One-time invitation for first-time visitors, shown after they pick a language. */
export function TourOffer({ onStart }) {
  const { t, chosen } = useI18n()
  const [hidden, setHidden] = useState(tourDone)
  if (!chosen || hidden) return null
  const dismiss = () => { markDone(); setHidden(true) }
  return (
    <div className="tour-offer" role="status">
      <Icon name="flag" size={18} />
      <span>{t('tour.offer')}</span>
      <div className="row" style={{ gap: 6 }}>
        <button className="btn primary sm" onClick={() => { setHidden(true); onStart() }}>{t('tour.start')}</button>
        <button className="btn ghost sm" onClick={dismiss}>{t('tour.later')}</button>
      </div>
    </div>
  )
}
