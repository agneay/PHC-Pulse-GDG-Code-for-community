import { useEffect, useState } from 'react'
import { useI18n } from '../i18n'
import Icon from './Icon'

export function Card({ title, hint, right, children, className = '', bodyClass = 'card-b', icon }) {
  return (
    <section className={`card ${className}`}>
      {(title || right) && (
        <div className="card-h">
          {icon && <span style={{ color: 'var(--red)', display: 'flex' }}><Icon name={icon} size={17} /></span>}
          {title && <h3>{title}</h3>}
          {hint && <span className="hint">{hint}</span>}
          {right && <div className="right">{right}</div>}
        </div>
      )}
      <div className={bodyClass}>{children}</div>
    </section>
  )
}

export function Kpi({ label, value, sub, tone, icon }) {
  return (
    <div className={`card kpi ${tone || ''}`}>
      <div className="l">{icon && <Icon name={icon} size={14} />}{label}</div>
      <div className="v num">{value}</div>
      {sub && <div className="s">{sub}</div>}
    </div>
  )
}

export function StatusPill({ status }) {
  const { t } = useI18n()
  return <span className={`pill ${status}`}>{t(`status.${status}`)}</span>
}

export function Loading({ label }) {
  const { t } = useI18n()
  return <div className="loading"><div className="row"><span className="spinner" /> {label || t('common.loading')}</div></div>
}

export function ErrorBox({ error }) {
  if (!error) return null
  return <div className="err">{String(error.message || error)}</div>
}

export function EngineTag({ engine }) {
  const { t } = useI18n()
  if (!engine) return null
  const ai = engine.startsWith('gemini')
  return (
    <span className={`pill ${ai ? 'ai' : 'grey'}`} title={ai ? t('engine.geminiTitle') : t('engine.rulesTitle')}>
      {ai && <Icon name="spark" size={12} />}{ai ? engine : t('engine.rules')}
    </span>
  )
}

export function useAsync(fn, deps) {
  const [state, setState] = useState({ data: null, error: null, loading: true })
  const [tick, setTick] = useState(0)
  useEffect(() => {
    let alive = true
    setState((s) => ({ ...s, loading: true, error: null }))
    fn().then((data) => alive && setState({ data, error: null, loading: false }))
      .catch((error) => alive && setState({ data: null, error, loading: false }))
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])
  return { ...state, reload: () => setTick((t) => t + 1) }
}
