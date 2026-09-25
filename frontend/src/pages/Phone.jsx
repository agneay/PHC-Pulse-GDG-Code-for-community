import { useState } from 'react'
import { useApp } from '../App'
import Icon from '../components/Icon'
import { Card, useAsync } from '../components/ui'
import { api } from '../lib/api'
import { speak } from '../lib/wav'

const KEYS = [['1', ''], ['2', 'abc'], ['3', 'def'], ['4', 'ghi'], ['5', 'jkl'], ['6', 'mno'], ['7', 'pqrs'], ['8', 'tuv'], ['9', 'wxyz'], ['*', ''], ['0', '+'], ['#', '']]

export default function Phone() {
  const { refresh, notify, meta } = useApp()
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
      if (txt.startsWith('END') && txt.includes('Submitted')) { refresh(); notify('USSD report saved, forecasts updated') }
    } finally { setBusy(false) }
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
    setThread((t) => [...t, { me: true, text: sms }])
    const r = await api.post('/api/sms', { phone, text: sms })
    setThread((t) => [...t, { me: false, text: r.reply }])
    if (r.saved) refresh()
  }

  const callIvr = async () => {
    const body = {
      detectIntentResponseId: 'demo', languageCode: `${ivr.lang}-IN`,
      fulfillmentInfo: { tag: 'submit-report' },
      sessionInfo: { parameters: { caller_phone: phone, pcm: ivr.pcm, ors: ivr.ors, beds: ivr.beds, staff: ivr.staff, opd: ivr.opd } },
    }
    const r = await api.post('/api/dialogflow/webhook', body)
    const text = r.fulfillment_response.messages[0].text.text[0]
    setIvrOut({ body, text })
    speak(text, meta.languages[ivr.lang].bcp47)
    refresh()
  }

  return (
    <>
      <div className="page-h">
        <div>
          <div className="eyebrow">Works on a ₹1,000 feature phone</div>
          <h1>USSD · SMS · IVR channels</h1>
          <p>Many PHCs have poor data connectivity and many health workers carry basic phones. The same daily report can come in through a USSD menu, an SMS shortcode, or an IVR voice call (Dialogflow CX), all written to the same warehouse.</p>
        </div>
        <div className="right">
          <select className="select" value={phone} onChange={(e) => { setPhone(e.target.value); end(); setThread([]) }} aria-label="Registered worker">
            {(workers.data || []).map((w) => <option key={w.phone} value={w.phone}>{w.phone} · {w.phc_code} {w.name}</option>)}
          </select>
        </div>
      </div>

      <div className="grid g-3">
        <Card title="USSD *123#" icon="phone" hint="stateless menu, gateway-ready">
          <div className="phone">
            <div className="scr">
              <div className="hdr"><span>▂▄▆ Airtel</span><span>{worker?.phc_code}</span><span>▮▮▮</span></div>
              {session ? session.screen : entry ? '' : 'Dial *123# and press the green key'}
              {busy && '\n…'}
            </div>
            <div className="typed">{entry || (session && !session.ended ? '_' : '')}</div>
            <div className="keys">
              <button className="call" onClick={call} aria-label="Send">✆</button>
              <button onClick={() => setEntry((e) => e.slice(0, -1))} aria-label="Delete">⌫</button>
              <button className="end" onClick={end} aria-label="End">✕</button>
              {KEYS.map(([k, s]) => <button key={k} onClick={() => press(k)}>{k}<small>{s}</small></button>)}
            </div>
          </div>
          <div className="muted small" style={{ marginTop: 10 }}>Try: dial <code>*123#</code> ✆ → <code>1</code> (drug stock) → <code>1</code> (PCM) → <code>140</code> → <code>0</code> → <code>2</code> (beds) → <code>4</code> → <code>5</code> → <code>1</code> submit.</div>
          <div className="row" style={{ marginTop: 8 }}>
            <button className="btn sm" onClick={() => setEntry('*123#')}>Type *123#</button>
          </div>
        </Card>

        <Card title="SMS shortcode" icon="msg" hint="send to 5676xxx">
          <div className="stack">
            <div style={{ background: '#f7f1f1', borderRadius: 12, padding: 10, minHeight: 220, display: 'flex', flexDirection: 'column', gap: 8 }}>
              {!thread.length && <div className="muted small">Grammar: <code>PCM 120 ORS 40 BED 4 STF 9 OPD 85</code>. Plain free text also works (“paracetamol 120, beds 4”).</div>}
              {thread.map((m, i) => <div key={i} className={m.me ? 'msg-u' : 'msg-a'} style={{ fontSize: 13 }}>{m.text}</div>)}
            </div>
            <div className="row">
              <input className="input" style={{ flex: 1 }} value={sms} onChange={(e) => setSms(e.target.value)} aria-label="SMS text" />
              <button className="btn primary" onClick={sendSms}><Icon name="send" size={15} /></button>
            </div>
          </div>
        </Card>

        <Card title="IVR call (Dialogflow CX)" icon="speaker" hint="webhook: /api/dialogflow/webhook">
          <div className="stack">
            <div className="muted small">The Dialogflow CX agent asks the questions by voice and collects slot values, then calls this webhook. The reply is spoken back in the caller's language.</div>
            <div className="lang-tabs">
              {['hi', 'ta', 'kn', 'or', 'en'].map((l) => <button key={l} className={ivr.lang === l ? 'on' : ''} onClick={() => setIvr({ ...ivr, lang: l })}>{meta.languages[l].native}</button>)}
            </div>
            <div className="parsed-grid">
              {[['pcm', 'Paracetamol strips'], ['ors', 'ORS sachets'], ['beds', 'Beds occupied'], ['staff', 'Staff present'], ['opd', 'OPD']].map(([k, l]) => (
                <label key={k} className="f"><div className="l">{l}</div>
                  <input type="number" value={ivr[k]} onChange={(e) => setIvr({ ...ivr, [k]: Number(e.target.value) })} /></label>
              ))}
            </div>
            <button className="btn primary" onClick={callIvr}><Icon name="phone" size={15} />Simulate call end → webhook</button>
            {ivrOut && (
              <>
                <div className="say">{ivrOut.text}</div>
                <details className="small"><summary>Webhook request</summary><pre style={{ whiteSpace: 'pre-wrap', fontSize: 11 }}>{JSON.stringify(ivrOut.body, null, 2)}</pre></details>
              </>
            )}
          </div>
        </Card>
      </div>
    </>
  )
}
