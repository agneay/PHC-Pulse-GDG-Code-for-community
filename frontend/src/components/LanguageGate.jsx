import { useEffect, useState } from 'react'
import { translate, UI_LANGS, useI18n } from '../i18n'
import { detectRegion } from '../i18n/detect'
import Icon from './Icon'

/** First visit: find the user's state from their location and offer English or its languages. */
export default function LanguageGate() {
  const { chosen, setLang } = useI18n()
  const [region, setRegion] = useState(undefined)      // undefined = detecting, null = unknown
  const [more, setMore] = useState(false)

  useEffect(() => {
    if (chosen) return
    let alive = true
    detectRegion().then((r) => alive && setRegion(r))
    return () => { alive = false }
  }, [chosen])

  if (chosen) return null
  const regional = [region?.lang, ...(region?.also || [])].filter((c) => c && c !== 'en' && UI_LANGS[c])
  const offered = regional[0] || null
  // Headline in the regional language too, so a worker who doesn't read English knows what to tap.
  const say = (key, vars) => (offered ? `${translate(offered, key, vars)} · ${translate('en', key, vars)}` : translate('en', key, vars))
  const choice = (c, primary) => (
    <button key={c} className={`btn lg ${primary ? 'primary' : ''}`} onClick={() => setLang(c)} autoFocus={primary} lang={c}
      dir={UI_LANGS[c].rtl ? 'rtl' : undefined}>
      {UI_LANGS[c].native}<small>{UI_LANGS[c].english}{UI_LANGS[c].draft ? ' · draft' : ''}</small>
    </button>
  )

  return (
    <div className="gate-bg" role="dialog" aria-modal="true" aria-labelledby="gate-title">
      <div className="gate">
        <div className="gate-icon"><Icon name="globe" size={26} /></div>
        <h2 id="gate-title">{say('gate.title')}</h2>
        <p className="muted small">
          {region === undefined && <><span className="spinner" /> {translate('en', 'gate.detecting')}</>}
          {region?.source === 'location' && say('gate.detected', { state: region.stateName })}
          {region?.source === 'browser' && translate('en', 'gate.detectedBrowser')}
        </p>
        <div className="gate-choices">
          {regional.map((c, i) => choice(c, i === 0))}
          <button className={`btn lg ${offered ? '' : 'primary'}`} onClick={() => setLang('en')} lang="en">
            English
          </button>
        </div>
        {regional.some((c) => UI_LANGS[c].draft) && (
          <p className="muted small">{regional.filter((c) => UI_LANGS[c].draft).map((c) => translate(c, 'gate.draft')).join(' · ')} ({translate('en', 'gate.draft')})</p>
        )}
        {!more ? (
          <button className="linkish small" onClick={() => setMore(true)}>{say('gate.other')}</button>
        ) : (
          <div className="gate-more">
            {Object.entries(UI_LANGS).filter(([c]) => c !== 'en' && !regional.includes(c)).map(([c, l]) => (
              <button key={c} className="btn" onClick={() => setLang(c)} lang={c}>{l.native} <span className="muted small">{l.english}</span></button>
            ))}
          </div>
        )}
        <p className="muted small" style={{ marginTop: 14 }}>{say('gate.note')}</p>
      </div>
    </div>
  )
}
