import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useApp } from '../App'
import Icon from '../components/Icon'
import { Card, EngineTag, StatusPill, useAsync } from '../components/ui'
import { api } from '../lib/api'
import { daysText, fmt } from '../lib/format'
import { blobToWav, speak } from '../lib/wav'

const SAMPLES = {
  en: 'Paracetamol 150 strips left, ORS 60 sachets, zinc 20 strips. 3 beds occupied, 9 staff present, 72 patients in OPD today, 18 with fever.',
  hi: 'पैरासिटामोल की 150 स्ट्रिप बची हैं, ओआरएस 60 पैकेट, 3 बिस्तर भरे हैं, 9 स्टाफ आए हैं, आज ओपीडी में 72 मरीज़ आए।',
  ta: 'பாராசிட்டமால் 150 அட்டைகள் உள்ளன, ஓ.ஆர்.எஸ் 60 பாக்கெட்டுகள், 3 படுக்கைகள் நிரம்பியுள்ளன, 9 ஊழியர்கள் வந்துள்ளனர், இன்று 72 புறநோயாளிகள்.',
  kn: 'ಪ್ಯಾರಾಸಿಟಮಾಲ್ 150 ಸ್ಟ್ರಿಪ್ ಉಳಿದಿದೆ, ಒಆರ್‌ಎಸ್ 60 ಪ್ಯಾಕೆಟ್, 3 ಹಾಸಿಗೆಗಳು ಭರ್ತಿ, 9 ಸಿಬ್ಬಂದಿ ಹಾಜರಿದ್ದಾರೆ, ಇಂದು 72 ಹೊರರೋಗಿಗಳು.',
  or: 'ପାରାସିଟାମଲ 150 ଷ୍ଟ୍ରିପ ଅଛି, ଓଆରଏସ 60 ପ୍ୟାକେଟ, 3ଟି ଶଯ୍ୟା ଭର୍ତ୍ତି, 9 ଜଣ କର୍ମଚାରୀ ଉପସ୍ଥିତ, ଆଜି 72 ଜଣ ରୋଗୀ ଆସିଥିଲେ।',
}
const PROMPT = {
  en: 'Tell me today\'s stock, beds, staff and patients.',
  hi: 'आज का स्टॉक, बिस्तर, स्टाफ और मरीज़ों की संख्या बताइए।',
  ta: 'இன்றைய மருந்து இருப்பு, படுக்கைகள், ஊழியர்கள், நோயாளிகள் எண்ணிக்கையை சொல்லுங்கள்.',
  kn: 'ಇಂದಿನ ಔಷಧ ದಾಸ್ತಾನು, ಹಾಸಿಗೆಗಳು, ಸಿಬ್ಬಂದಿ ಮತ್ತು ರೋಗಿಗಳ ಸಂಖ್ಯೆಯನ್ನು ಹೇಳಿ.',
  or: 'ଆଜିର ଔଷଧ ଷ୍ଟକ, ଶଯ୍ୟା, କର୍ମଚାରୀ ଓ ରୋଗୀ ସଂଖ୍ୟା କୁହନ୍ତୁ।',
}
const FIELDS = [
  ['opd_count', 'OPD patients'], ['fever_cases', 'Fever cases'], ['diarrhoea_cases', 'Diarrhoea cases'],
  ['respiratory_cases', 'Respiratory cases'], ['beds_occupied', 'Beds occupied'], ['staff_present', 'Staff present'],
]
const MAX_SECONDS = 60
const FLAG_STYLE = { borderColor: 'var(--red, #c62828)', background: '#fff4f4' }

export default function VoiceReport() {
  const { meta, refresh, notify } = useApp()
  const [sp] = useSearchParams()
  const phcs = useAsync(() => api.get('/api/overview'), [])
  const userPhc = meta.user.scope?.phc_id
  const [phcId, setPhcId] = useState(userPhc || Number(sp.get('phc')) || null)   // never guess the facility
  const [lang, setLang] = useState(null)
  const [mode, setMode] = useState('voice')
  const [text, setText] = useState('')
  const [rec, setRec] = useState(false)
  const [secs, setSecs] = useState(0)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [out, setOut] = useState(null)        // {report, engine}
  const [saved, setSaved] = useState(null)
  const [live, setLive] = useState('')
  const mr = useRef(null); const chunks = useRef([]); const timer = useRef(null); const sr = useRef(null)
  const liveRef = useRef('')
  const followUp = useRef(false)

  const phc = phcs.data?.phcs.find((p) => p.id === phcId)
  useEffect(() => {   // requested PHC outside the user's jurisdiction -> make them pick one
    if (phcs.data && phcId && !phc) setPhcId(null)
  }, [phcs.data, phc, phcId])
  const language = lang || phc?.language || 'en'
  const bcp = meta.languages[language]?.bcp47 || 'en-IN'
  const gem = meta.gemini.enabled
  const SR = typeof window !== 'undefined' && (window.SpeechRecognition || window.webkitSpeechRecognition)

  useEffect(() => () => { clearInterval(timer.current); mr.current?.stream?.getTracks().forEach((t) => t.stop()) }, [])

  useEffect(() => { if (rec && secs >= MAX_SECONDS) stop() })   // hard cap: 60 s per report

  const reset = () => { setOut(null); setSaved(null); setErr(null); setLive(''); followUp.current = false }

  const handleResult = (r) => {
    setOut(r)
    const rep = r.report
    const say = [rep.confirmation, rep.follow_up_question].filter(Boolean).join(' ')
    setTimeout(() => speak(say, bcp), 150)
  }

  const start = async (isFollowUp = false) => {
    setErr(null); if (!isFollowUp) { setOut(null); setSaved(null) }
    followUp.current = isFollowUp
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const m = new MediaRecorder(stream)
      chunks.current = []
      m.ondataavailable = (e) => e.data.size && chunks.current.push(e.data)
      m.onstop = () => onStop(stream)
      m.start()
      mr.current = m
      setRec(true); setSecs(0); setLive('')
      liveRef.current = ''
      timer.current = setInterval(() => setSecs((s) => s + 1), 1000)
      if (!gem && SR) {           // no Gemini: browser speech-to-text provides the transcript
        const r = new SR()
        r.lang = bcp; r.continuous = true; r.interimResults = true
        r.onresult = (e) => {
          liveRef.current = Array.from(e.results).map((x) => x[0].transcript).join(' ')
          setLive(liveRef.current)
        }
        r.start(); sr.current = r
      }
    } catch (e) { setErr(`Microphone unavailable: ${e.message}. Use text mode instead.`) }
  }

  const stop = () => {
    clearInterval(timer.current)
    sr.current?.stop()
    if (mr.current && mr.current.state !== 'inactive') mr.current.stop()
    setRec(false)
  }

  const onStop = async (stream) => {
    stream.getTracks().forEach((t) => t.stop())
    const prev = followUp.current ? out?.report : null
    setBusy(true)
    try {
      if (gem) {
        const blob = new Blob(chunks.current, { type: mr.current.mimeType || 'audio/webm' })
        const wav = await blobToWav(blob)
        const fd = new FormData()
        fd.append('audio', wav, 'report.wav'); fd.append('phc_id', phcId); fd.append('language', language)
        if (prev) fd.append('previous', JSON.stringify(prev))
        handleResult(await api.form('/api/reports/voice', fd))
      } else {
        await new Promise((r) => setTimeout(r, 400))
        const transcript = liveRef.current
        if (!transcript.trim()) throw new Error('No speech captured. Gemini is not configured here, so speech-to-text relies on the browser (Chrome). Try again or use text mode.')
        handleResult(await api.post('/api/reports/parse', { phc_id: phcId, language, text: transcript, previous: prev }))
      }
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const parseText = async () => {
    setBusy(true); setErr(null)
    try {
      handleResult(await api.post('/api/reports/parse', { phc_id: phcId, language, text, previous: followUp.current ? out?.report : null }))
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  // Editing a value invalidates the plausibility warnings; the server re-checks on submit.
  const edit = (k, v) => setOut((o) => ({ ...o, warnings: [], report: { ...o.report, [k]: v === '' ? null : Number(v) } }))
  const editStock = (i, v) => setOut((o) => {
    const stock = [...o.report.stock]; stock[i] = { ...stock[i], quantity: v === '' ? null : Number(v) }
    return { ...o, warnings: [], report: { ...o.report, stock } }
  })
  const warnings = out?.warnings || []
  const flagged = new Set(warnings.map((w) => w.field))

  const submit = async () => {
    setBusy(true); setErr(null)
    try {
      // Submitting while warnings are on screen means the worker has re-checked those numbers.
      const r = await api.post('/api/reports/submit', { phc_id: phcId, language, channel: mode === 'voice' ? 'voice' : 'text', engine: out.engine, report: out.report, confirmed: warnings.length > 0 })
      setSaved(r); refresh(); notify(`Report saved for ${r.phc}. Forecasts recomputed.`)
    } catch (e) {
      if (e.status === 409 && e.detail?.warnings) setOut((o) => ({ ...o, warnings: e.detail.warnings }))
      else setErr(e.message)
    } finally { setBusy(false) }
  }

  const drugName = (c) => meta.drugs.find((d) => d.code === c)
  const rep = out?.report

  return (
    <>
      <div className="page-h">
        <div>
          <div className="eyebrow">Voice-first reporting · under 60 seconds</div>
          <h1>Daily voice report</h1>
          <p>The ASHA/ANM speaks naturally in their own language, mixing languages is fine. Gemini transcribes, translates and structures the report, reads the numbers back in the same language, and asks for anything missing.</p>
        </div>
      </div>

      <div className="voice-hero">
        <Card title="1 · Who is reporting" icon="users">
          <div className="stack">
            <div className="row">
              <select className="select" style={{ flex: 1 }} value={phcId ?? ''} disabled={!!userPhc}
                onChange={(e) => { setPhcId(Number(e.target.value)); setLang(null); reset() }} aria-label="PHC">
                {!phcId && <option value="">Select the reporting PHC…</option>}
                {(phcs.data?.phcs || []).map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name} ({p.district_code})</option>)}
              </select>
            </div>
            <div className="lang-tabs">
              {['en', 'hi', 'ta', 'kn', 'or', 'te', 'bn', 'mr'].map((l) => (
                <button key={l} className={language === l ? 'on' : ''} onClick={() => { setLang(l); reset() }}>{meta.languages[l].native}</button>
              ))}
            </div>
            <div className="say">
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <b>{PROMPT[language] || PROMPT.en}</b>
                <button className="btn ghost sm" onClick={() => speak(PROMPT[language] || PROMPT.en, bcp)} title="Play prompt"><Icon name="speaker" size={15} /></button>
              </div>
              <div className="small" style={{ marginTop: 6, opacity: .85 }}>e.g. “{SAMPLES[language] || SAMPLES.en}”</div>
            </div>
            <div className="row small">
              <span className="muted">Engine:</span>
              {gem ? <span className="pill ai"><Icon name="spark" size={12} />{meta.gemini.model}: audio → structured JSON</span>
                : <span className="pill grey">Browser speech-to-text + rules (set GEMINI_API_KEY for Gemini)</span>}
            </div>
          </div>
        </Card>

        <Card title="2 · Speak" icon="mic" right={<div className="lang-tabs">
          <button className={mode === 'voice' ? 'on' : ''} onClick={() => setMode('voice')}>Voice</button>
          <button className={mode === 'text' ? 'on' : ''} onClick={() => setMode('text')}>Type</button></div>}>
          {mode === 'voice' ? (
            <div style={{ textAlign: 'center' }}>
              <button className={`mic ${rec ? 'rec' : ''}`} onClick={() => (rec ? stop() : start(false))} disabled={busy || !phcId}
                aria-label={rec ? 'Stop recording' : 'Start recording'}>
                <Icon name={rec ? 'stop' : 'mic'} size={48} stroke={1.8} />
              </button>
              <div className="num" style={{ fontSize: 20, fontWeight: 700 }}>{rec ? `0:${String(secs).padStart(2, '0')} / 1:00` : busy ? 'Understanding…' : 'Tap to speak'}</div>
              {busy && <div className="row" style={{ justifyContent: 'center', marginTop: 6 }}><span className="spinner" /> {gem ? 'Gemini is transcribing and structuring' : 'Parsing'}</div>}
              {live && <div className="note" style={{ marginTop: 10, textAlign: 'left' }}>{live}</div>}
              {!gem && !SR && <div className="note" style={{ marginTop: 10 }}>This browser has no speech recognition and Gemini isn't configured. Use <b>Type</b> mode.</div>}
            </div>
          ) : (
            <div className="stack">
              <textarea className="textarea" rows={5} value={text} onChange={(e) => setText(e.target.value)} placeholder="Type or paste the worker's report in any language…" />
              <div className="row">
                <button className="btn" onClick={() => setText(SAMPLES[language] || SAMPLES.en)}>Use sample</button>
                <button className="btn primary" onClick={parseText} disabled={busy || !text.trim() || !phcId}>{busy ? <span className="spinner" /> : <Icon name="spark" size={14} />}Understand report</button>
              </div>
            </div>
          )}
          {err && <div className="err" style={{ marginTop: 10 }}>{err}</div>}
        </Card>
      </div>

      {rep && (
        <Card title="3 · Confirm" icon="check" right={<EngineTag engine={out.engine} />}>
          <div className="stack">
            <div className="grid g-2e" style={{ gap: 12 }}>
              <div>
                <div className="eyebrow">Transcript ({rep.detected_language})</div>
                <div className="small" style={{ marginTop: 4, lineHeight: 1.55 }}>“{rep.transcript}”</div>
                {rep.english_translation && rep.detected_language !== 'en' && (
                  <div className="small muted" style={{ marginTop: 4 }}>EN: {rep.english_translation}</div>)}
              </div>
              <div className="say" style={{ fontSize: 14 }}>
                <div className="row" style={{ justifyContent: 'space-between' }}>
                  <b>Read-back</b>
                  <button className="btn ghost sm" onClick={() => speak(rep.confirmation, bcp)} title="Play again"><Icon name="speaker" size={15} /></button>
                </div>
                {rep.confirmation}
              </div>
            </div>
            <div className="parsed-grid">
              {rep.stock.map((s, i) => (
                <label key={s.drug_code + s.kind} className="f" style={flagged.has(s.drug_code) ? FLAG_STYLE : null}>
                  <div className="l">{drugName(s.drug_code)?.name} {{ received: '(received)', discarded: '(expired / damaged, thrown away)' }[s.kind] || '(remaining on shelf)'}</div>
                  <input type="number" value={s.quantity ?? ''} placeholder="not reported" onChange={(e) => editStock(i, e.target.value)} />
                  <div className="l">{drugName(s.drug_code)?.unit}</div>
                </label>
              ))}
              {FIELDS.map(([k, l]) => (
                <label key={k} className="f" style={flagged.has(k) ? FLAG_STYLE : rep[k] == null ? { borderStyle: 'dashed' } : null}>
                  <div className="l">{l}</div>
                  <input type="number" value={rep[k] ?? ''} placeholder="–" onChange={(e) => edit(k, e.target.value)} />
                </label>
              ))}
            </div>
            {warnings.length > 0 && !saved && (
              <div className="err" role="alert">
                <b>Please re-check these numbers before submitting:</b>
                <ul className="small" style={{ margin: '6px 0 0', paddingLeft: 18 }}>{warnings.map((w, i) => <li key={i}>{w.message}</li>)}</ul>
              </div>
            )}
            {rep.notes && <div className="note">Notes: {rep.notes}</div>}
            {rep.follow_up_question && !saved && (
              <div className="note" style={{ borderColor: '#ffc68a', background: 'var(--orange-100)' }}>
                <div className="row"><b style={{ flex: 1 }}>Follow-up: {rep.follow_up_question}</b>
                  {mode === 'voice'
                    ? <button className="btn orange sm" onClick={() => (rec ? stop() : start(true))}>{rec ? 'Stop' : <><Icon name="mic" size={14} />Answer</>}</button>
                    : <span className="muted small">Type the answer above and press “Understand report”, it is merged.</span>}
                </div>
              </div>
            )}
            {!saved ? (
              <div className="row">
                <button className="btn primary" onClick={submit} disabled={busy}><Icon name="check" size={15} />{warnings.length ? 'Numbers re-checked, submit' : 'Confirm & submit'}</button>
                <button className="btn" onClick={reset}>Discard</button>
                {mode === 'text' && <button className="btn ghost" onClick={() => { followUp.current = true; setText('') }}>Add follow-up answer</button>}
                {rep.confidence != null && <span className="muted small">confidence {Math.round(rep.confidence * 100)}%</span>}
              </div>
            ) : (
              <div className="stack">
                <div className="row"><span className="pill ok"><Icon name="check" size={12} />Saved to warehouse · report #{saved.report_id}</span>
                  <Link to={`/phc/${phcId}`} className="btn sm">Open {saved.phc} forecast →</Link>
                  <button className="btn sm" onClick={reset}>New report</button></div>
                <div className="table-wrap">
                  <table className="t">
                    <thead><tr><th>Drug</th><th className="r">Stock</th><th className="r">Cover</th><th>Runs out</th><th>Status</th></tr></thead>
                    <tbody>{saved.items.filter((i) => rep.stock.some((s) => s.drug_code === i.drug_code) || ['critical', 'stocked_out', 'high'].includes(i.status)).map((i) => (
                      <tr key={i.drug_code}><td>{drugName(i.drug_code)?.name}</td><td className="r num">{fmt(i.stock)}</td>
                        <td className="r num">{fmt(i.cover_days)}d</td><td>{daysText(i.days_to_stockout)}</td><td><StatusPill status={i.status} /></td></tr>))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </Card>
      )}
    </>
  )
}
