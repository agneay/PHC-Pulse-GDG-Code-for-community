import { useState } from 'react'
import { useApp } from '../App'
import { useI18n } from '../i18n'
import { api } from '../lib/api'
import Icon from './Icon'
import { SpeakButton } from './Speak'
import { Card, EngineTag } from './ui'

export default function Briefing() {
  const { scopeQs, meta } = useApp()
  const { t, lang: uiLang } = useI18n()
  const [lang, setLang] = useState(meta.languages[uiLang] ? uiLang : 'en')   // follows the site language
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
    <Card className="ai-card" icon="spark" title={t('brief.title')}
      right={<>
        <select className="select" value={lang} aria-label={t('brief.language')}
          onChange={(e) => { setLang(e.target.value); if (data) load(e.target.value) }}>
          {Object.entries(meta.languages).map(([c, l]) => <option key={c} value={c} lang={c}>{l.native} · {l.name}</option>)}
        </select>
        <button className="btn primary sm" onClick={() => load()} disabled={busy}>
          {busy ? <span className="spinner" /> : <Icon name="spark" size={14} />}{data ? t('brief.regenerate') : t('brief.generate')}
        </button>
      </>}>
      {err && <div className="err">{err}</div>}
      {!data && !busy && <div className="muted small">{t('brief.intro')}</div>}
      {busy && !data && <div className="row muted small"><span className="spinner" /> {t('brief.writing')}</div>}
      {data && (
        <div className="stack" lang={lang}>
          <div className="row" style={{ alignItems: 'flex-start' }}>
            <h4 style={{ flex: 1 }}>{data.headline}</h4>
            <SpeakButton text={`${data.headline}. ${data.summary}`} language={lang} />
          </div>
          <div className="small" style={{ color: 'var(--ink-2)', lineHeight: 1.55 }}>{data.summary}</div>
          <div>
            <div className="eyebrow">{t('brief.doToday')}</div>
            <ul>{data.actions.map((a, i) => <li key={i}>{a}</li>)}</ul>
          </div>
          {data.risks?.length > 0 && (
            <div>
              <div className="eyebrow" style={{ color: 'var(--orange)' }}>{t('brief.watch')}</div>
              <ul>{data.risks.map((a, i) => <li key={i}>{a}</li>)}</ul>
            </div>
          )}
          <div><EngineTag engine={data.engine} /></div>
        </div>
      )}
    </Card>
  )
}
