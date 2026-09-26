import { useState } from 'react'
import { useApp } from '../App'
import Icon from '../components/Icon'
import { useSpeak } from '../components/Speak'
import { Card, useAsync } from '../components/ui'
import { useI18n } from '../i18n'
import { api } from '../lib/api'
import { rich } from '../lib/format'

const KEYS = [['1', ''], ['2', 'abc'], ['3', 'def'], ['4', 'ghi'], ['5', 'jkl'], ['6', 'mno'], ['7', 'pqrs'], ['8', 'tuv'], ['9', 'wxyz'], ['*', ''], ['0', '+'], ['#', '']]

export default function Phone() {
  const { refresh, notify, meta } = useApp()
  const { t } = useI18n()
  const say = useSpeak()
  const workers = useAsync(() => api.get('/api/workers'), [])
  const [phone, setPhone] = useState('+919000000022')
  const [session, setSession] = useState(null)       // {id, path: [], screen}
  const [entry, setEntry] = useState('')
  const [busy, setBusy] = useState(false)
  const [sms, setSms] = useState('PCM 120 ORS 40 BED 4 STF 9 OPD 85')
  const [thread, setThread] = useState([])
  const [ivr, setIvr] = useState({ lang: 'hi', pcm: 90, ors: 35, beds: 5, staff: 8, opd: 64 })
  const [ivrOut, setIvrOut] = useState(null)

  const worker = workers.data?.find((w) => w.phone === phone)

  const ussd = async (path, id) => {
    setBusy(true)
    try {
      const body = new URLSearchParams({ sessionId: id, phoneNumber: phone, serviceCode: '*123#', text: path.join('*') })
      const res = await fetch('/api/ussd', { method: 'POST', body })
      const txt = await res.text()
      setSession({ id, path, screen: txt.slice(4), ended: txt.startsWith('END') })
      if (txt.startsWith('END') && txt.includes('Submitted')) { refresh(); notify(t('phone.ussdSaved')) }
    } catch (e) { notify(e.message) } finally { setBusy(false) }
  }
  const press = (k) => {
    if (!session || session.ended) { setEntry((e) => (e + k).slice(0, 12)); return }
    setEntry((e) => (e + k).slice(0, 8))
  }
  const call = () => {
    if (!session || session.ended) {
      if (entry === '*123#' || entry === '') { setEntry(''); ussd([], `s${Date.now()}`) }
      else setEntry('')
      return
    }
    if (!entry) return
    const path = [...session.path, entry]
    setEntry('')
    ussd(path, session.id)
  }
  const end = () => { setSession(null); setEntry('') }

  const sendSms = async () => {
    setThread((th) => [...th, { me: true, text: sms }])
    try {
      const r = await api.post('/api/sms', { phone, text: sms })
      setThread((th) => [...th, { me: false, text: r.reply }])
      if (r.saved) refresh()
    } catch (e) { notify(e.message) }
  }

  const callIvr = async () => {
    const body = {
      detectIntentResponseId: 'demo', languageCode: `${ivr.lang}-IN`,
      fulfillmentInfo: { tag: 'submit-report' },
      sessionInfo: { parameters: { caller_phone: phone, pcm: ivr.pcm, ors: ivr.ors, beds: ivr.beds, staff: ivr.staff, opd: ivr.opd } },
    }
    try {
      const r = await api.post('/api/dialogflow/webhook', body)
      const text = r.fulfillment_response.messages[0].text.text[0]
      setIvrOut({ body, text })
      refresh()
      say(text, ivr.lang)
    } catch (e) { notify(e.message) }
  }

  return (
    <>
      <div className="page-h">
        <div>
          <div className="eyebrow">{t('phone.eyebrow')}</div>
          <h1>{t('phone.title')}</h1>
          <p>{t('phone.intro')}</p>
        </div>
        <div className="right">
          <select className="select" value={phone} onChange={(e) => { setPhone(e.target.value); end(); setThread([]) }} aria-label={t('phone.worker')}>
            {(workers.data || []).map((w) => <option key={w.phone} value={w.phone}>{w.phone} · {w.phc_code} {w.name}</option>)}
          </select>
        </div>
      </div>

      <div className="grid g-3" data-tour="phone">
        <Card title="USSD *123#" icon="phone" hint={t('phone.ussdHint')}>
          <div className="phone">
            <div className="scr" lang="en">
              <div className="hdr"><span>▂▄▆ Airtel</span><span>{worker?.phc_code}</span><span>▮▮▮</span></div>
              {session ? session.screen : entry ? '' : t('phone.dial')}
              {busy && '\n…'}
            </div>
            <div className="typed">{entry || (session && !session.ended ? '_' : '')}</div>
            <div className="keys">
              <button className="call" onClick={call} aria-label={t('phone.send')}>✆</button>
              <button onClick={() => setEntry((e) => e.slice(0, -1))} aria-label={t('phone.delete')}>⌫</button>
              <button className="end" onClick={end} aria-label={t('phone.end')}>✕</button>
              {KEYS.map(([k, s]) => <button key={k} onClick={() => press(k)}>{k}<small>{s}</small></button>)}
            </div>
          </div>
          <div className="muted small" style={{ marginTop: 10 }}>{rich(t('phone.ussdTry'))}</div>
          <div className="row" style={{ marginTop: 8 }}>
            <button className="btn sm" onClick={() => setEntry('*123#')}>{t('phone.typeCode')}</button>
          </div>
        </Card>

        <Card title={t('phone.smsTitle')} icon="msg" hint={t('phone.smsHint')}>
          <div className="stack">
            <div style={{ background: '#f7f1f1', borderRadius: 12, padding: 10, minHeight: 220, display: 'flex', flexDirection: 'column', gap: 8 }}>
              {!thread.length && <div className="muted small">{rich(t('phone.smsGrammar'))}</div>}
              {thread.map((m, i) => <div key={i} className={m.me ? 'msg-u' : 'msg-a'} style={{ fontSize: 'calc(13px * var(--fs, 1))' }}>{m.text}</div>)}
            </div>
            <div className="row">
              <input className="input" style={{ flex: 1 }} value={sms} onChange={(e) => setSms(e.target.value)} aria-label={t('phone.smsText')} />
              <button className="btn primary" onClick={sendSms} aria-label={t('phone.send')}><Icon name="send" size={15} /></button>
            </div>
          </div>
        </Card>

        <Card title={t('phone.ivrTitle')} icon="speaker" hint="webhook: /api/dialogflow/webhook">
          <div className="stack">
            <div className="muted small">{t('phone.ivrIntro')}</div>
            <div className="lang-tabs">
              {['hi', 'ta', 'kn', 'or', 'en'].map((l) => <button key={l} className={ivr.lang === l ? 'on' : ''} onClick={() => setIvr({ ...ivr, lang: l })}>{meta.languages[l].native}</button>)}
              <select className="select" value={ivr.lang} onChange={(e) => setIvr({ ...ivr, lang: e.target.value })} aria-label="IVR language">
                {Object.entries(meta.languages).map(([c, l]) => <option key={c} value={c} lang={c}>{l.native} · {l.name}</option>)}
              </select>
            </div>
            <div className="parsed-grid">
              {[['pcm', 'phone.fPcm'], ['ors', 'phone.fOrs'], ['beds', 'field.beds_occupied'], ['staff', 'field.staff_present'], ['opd', 'field.opd_count']].map(([k, l]) => (
                <label key={k} className="f"><div className="l">{t(l)}</div>
                  <input type="number" value={ivr[k]} onChange={(e) => setIvr({ ...ivr, [k]: Number(e.target.value) })} /></label>
              ))}
            </div>
            <button className="btn primary" onClick={callIvr}><Icon name="phone" size={15} />{t('phone.simulate')}</button>
            {ivrOut && (
              <>
                <div className="say" lang={ivr.lang}>{ivrOut.text}</div>
                <details className="small"><summary>{t('phone.webhookRequest')}</summary><pre style={{ whiteSpace: 'pre-wrap', fontSize: 'calc(11px * var(--fs, 1))' }}>{JSON.stringify(ivrOut.body, null, 2)}</pre></details>
              </>
            )}
          </div>
        </Card>
      </div>
    </>
  )
}
