import { useState } from 'react'
import { useApp } from '../App'
import { api } from '../lib/api'
import { speak } from '../lib/wav'
import Icon from './Icon'
import { Card, EngineTag } from './ui'

const LANGS = ['en', 'hi', 'ta', 'kn', 'or']

export default function Briefing() {
  const { scopeQs, meta } = useApp()
  const [lang, setLang] = useState('en')
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const load = async (l = lang) => {
    setBusy(true); setErr(null)
    try {
      const sep = scopeQs ? '&' : '?'
      setData(await api.get(`/api/briefing${scopeQs}${sep}language=${l}`))
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <Card className="ai-card" icon="spark" title="Today's AI briefing"
      right={<>
        <select className="select" value={lang} aria-label="Briefing language"
          onChange={(e) => { setLang(e.target.value); if (data) load(e.target.value) }}>
          {LANGS.map((l) => <option key={l} value={l}>{meta.languages[l].native}</option>)}
        </select>
        <button className="btn primary sm" onClick={() => load()} disabled={busy}>
          {busy ? <span className="spinner" /> : <Icon name="spark" size={14} />}{data ? 'Regenerate' : 'Generate'}
        </button>
      </>}>
      {err && <div className="err">{err}</div>}
      {!data && !busy && (
        <div className="muted small">Gemini reads the live forecasts, outbreak clusters and the optimiser's plan for your jurisdiction and writes a prioritised action list in your language.</div>
      )}
      {busy && !data && <div className="row muted small"><span className="spinner" /> Writing the briefing…</div>}
      {data && (
        <div className="stack">
          <div className="row" style={{ alignItems: 'flex-start' }}>
            <h4 style={{ flex: 1 }}>{data.headline}</h4>
            <button className="btn ghost sm" title="Read aloud"
              onClick={() => speak(`${data.headline}. ${data.summary}`, meta.languages[lang].bcp47)}>
              <Icon name="speaker" size={15} />
            </button>
          </div>
          <div className="small" style={{ color: 'var(--ink-2)', lineHeight: 1.55 }}>{data.summary}</div>
          <div>
            <div className="eyebrow">Do today</div>
            <ul>{data.actions.map((a, i) => <li key={i}>{a}</li>)}</ul>
          </div>
          {data.risks?.length > 0 && (
            <div>
              <div className="eyebrow" style={{ color: 'var(--orange)' }}>Watch</div>
              <ul>{data.risks.map((a, i) => <li key={i}>{a}</li>)}</ul>
            </div>
          )}
          <div><EngineTag engine={data.engine} /></div>
        </div>
      )}
    </Card>
  )
}
