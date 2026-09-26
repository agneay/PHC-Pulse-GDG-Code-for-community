import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useApp } from '../App'
import Icon from '../components/Icon'
import { SpeakButton, useSpeak } from '../components/Speak'
import { Card, EngineTag, StatusPill, useAsync } from '../components/ui'
import { useI18n } from '../i18n'
import { api } from '../lib/api'
import { daysText, drugLabel, fmt, unitLabel } from '../lib/format'
import { blobToWav, stopSpeaking } from '../lib/wav'

// What the worker says / sees in the *reporting* language (the PHC's language by default),
// independent of the language the website itself is shown in.
const SAMPLES = {
  en: 'Paracetamol 150 strips left, ORS 60 sachets, zinc 20 strips. 3 beds occupied, 9 staff present, 72 patients in OPD today, 18 with fever.',
  hi: 'पैरासिटामोल की 150 स्ट्रिप बची हैं, ओआरएस 60 पैकेट, 3 बिस्तर भरे हैं, 9 स्टाफ आए हैं, आज ओपीडी में 72 मरीज़ आए।',
  ta: 'பாராசிட்டமால் 150 அட்டைகள் உள்ளன, ஓ.ஆர்.எஸ் 60 பாக்கெட்டுகள், 3 படுக்கைகள் நிரம்பியுள்ளன, 9 ஊழியர்கள் வந்துள்ளனர், இன்று 72 புறநோயாளிகள்.',
  kn: 'ಪ್ಯಾರಾಸಿಟಮಾಲ್ 150 ಸ್ಟ್ರಿಪ್ ಉಳಿದಿದೆ, ಒಆರ್‌ಎಸ್ 60 ಪ್ಯಾಕೆಟ್, 3 ಹಾಸಿಗೆಗಳು ಭರ್ತಿ, 9 ಸಿಬ್ಬಂದಿ ಹಾಜರಿದ್ದಾರೆ, ಇಂದು 72 ಹೊರರೋಗಿಗಳು.',
  or: 'ପାରାସିଟାମଲ 150 ଷ୍ଟ୍ରିପ ଅଛି, ଓଆରଏସ 60 ପ୍ୟାକେଟ, 3ଟି ଶଯ୍ୟା ଭର୍ତ୍ତି, 9 ଜଣ କର୍ମଚାରୀ ଉପସ୍ଥିତ, ଆଜି 72 ଜଣ ରୋଗୀ ଆସିଥିଲେ।',
  bn: 'প্যারাসিটামল 150 স্ট্রিপ আছে, ওআরএস 60 প্যাকেট, 3টি বেড ভর্তি, 9 জন কর্মী উপস্থিত, আজ ওপিডিতে 72 জন রোগী।',
  te: 'పారాసిటమాల్ 150 స్ట్రిప్పులు ఉన్నాయి, ఓఆర్ఎస్ 60 ప్యాకెట్లు, 3 పడకలు నిండాయి, 9 మంది సిబ్బంది హాజరు, ఈరోజు ఓపీడీలో 72 మంది రోగులు.',
  mr: 'पॅरासिटामॉलच्या 150 स्ट्रिप शिल्लक आहेत, ओआरएस 60 पाकिटे, 3 खाटा भरलेल्या, 9 कर्मचारी हजर, आज ओपीडीमध्ये 72 रुग्ण.',
  gu: 'પેરાસિટામોલની 150 સ્ટ્રીપ બાકી છે, ઓઆરએસ 60 પેકેટ, 3 પથારી ભરેલી, 9 કર્મચારી હાજર, આજે ઓપીડીમાં 72 દર્દીઓ.',
  ml: 'പാരസെറ്റമോൾ 150 സ്ട്രിപ്പ് ബാക്കിയുണ്ട്, ഒആർഎസ് 60 പാക്കറ്റ്, 3 കിടക്കകൾ നിറഞ്ഞു, 9 ജീവനക്കാർ ഹാജർ, ഇന്ന് ഒപിയിൽ 72 രോഗികൾ.',
  pa: 'ਪੈਰਾਸੀਟਾਮੋਲ ਦੀਆਂ 150 ਸਟ੍ਰਿਪਾਂ ਬਚੀਆਂ ਹਨ, ਓਆਰਐਸ 60 ਪੈਕੇਟ, 3 ਬਿਸਤਰੇ ਭਰੇ, 9 ਸਟਾਫ਼ ਹਾਜ਼ਰ, ਅੱਜ ਓਪੀਡੀ ਵਿੱਚ 72 ਮਰੀਜ਼।',
  ur: 'پیراسیٹامول کی 150 سٹرپ باقی ہیں، او آر ایس 60 پیکٹ، 3 بستر بھرے ہیں، 9 عملہ حاضر ہے، آج او پی ڈی میں 72 مریض آئے۔',
}
const PROMPT = {
  en: 'Tell me today\'s stock, beds, staff and patients.',
  hi: 'आज का स्टॉक, बिस्तर, स्टाफ और मरीज़ों की संख्या बताइए।',
  ta: 'இன்றைய மருந்து இருப்பு, படுக்கைகள், ஊழியர்கள், நோயாளிகள் எண்ணிக்கையை சொல்லுங்கள்.',
  kn: 'ಇಂದಿನ ಔಷಧ ದಾಸ್ತಾನು, ಹಾಸಿಗೆಗಳು, ಸಿಬ್ಬಂದಿ ಮತ್ತು ರೋಗಿಗಳ ಸಂಖ್ಯೆಯನ್ನು ಹೇಳಿ.',
  or: 'ଆଜିର ଔଷଧ ଷ୍ଟକ, ଶଯ୍ୟା, କର୍ମଚାରୀ ଓ ରୋଗୀ ସଂଖ୍ୟା କୁହନ୍ତୁ।',
  bn: 'আজকের ওষুধের মজুত, বেড, কর্মী আর রোগীর সংখ্যা বলুন।',
  te: 'ఈరోజు మందుల నిల్వ, పడకలు, సిబ్బంది, రోగుల సంఖ్య చెప్పండి.',
  mr: 'आजचा औषधसाठा, खाटा, कर्मचारी आणि रुग्णसंख्या सांगा.',
  gu: 'આજનો દવાનો સ્ટોક, પથારી, કર્મચારી અને દર્દીઓની સંખ્યા કહો.',
  ml: 'ഇന്നത്തെ മരുന്ന് സ്റ്റോക്ക്, കിടക്കകൾ, ജീവനക്കാർ, രോഗികളുടെ എണ്ണം പറയൂ.',
  pa: 'ਅੱਜ ਦਾ ਦਵਾਈ ਸਟਾਕ, ਬਿਸਤਰੇ, ਸਟਾਫ਼ ਅਤੇ ਮਰੀਜ਼ਾਂ ਦੀ ਗਿਣਤੀ ਦੱਸੋ।',
  ur: 'آج کا دواؤں کا اسٹاک، بستر، عملہ اور مریضوں کی تعداد بتائیں۔',
}
const FIELDS = ['opd_count', 'fever_cases', 'diarrhoea_cases', 'respiratory_cases', 'beds_occupied', 'staff_present']
const MAX_SECONDS = 60
const FLAG_STYLE = { borderColor: 'var(--red, #c62828)', background: '#fff4f4' }
const clock = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

export default function VoiceReport() {
  const { meta, refresh, notify } = useApp()
  const { t, lang: uiLang } = useI18n()
  const say = useSpeak()
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
  const [out, setOut] = useState(null)        // {report, engine, warnings}
  const [saved, setSaved] = useState(null)
  const [live, setLive] = useState('')
  const mr = useRef(null); const chunks = useRef([]); const timer = useRef(null); const sr = useRef(null)
  const recording = useRef(false)             // read by recogniser callbacks (closures don't see state)
  const finals = useRef('')                   // recognised text kept across recogniser restarts
  const srDone = useRef(null)                 // resolves when the recogniser has flushed its last result
  const followUp = useRef(false)

  const phc = phcs.data?.phcs.find((p) => p.id === phcId)
  useEffect(() => {   // requested PHC outside the user's jurisdiction -> make them pick one
    if (phcs.data && phcId && !phc) setPhcId(null)
  }, [phcs.data, phc, phcId])
  const language = lang || phc?.language || 'en'
  const bcp = meta.languages[language]?.bcp47 || 'en-IN'
  const gem = meta.gemini.enabled
  const SR = typeof window !== 'undefined' && (window.SpeechRecognition || window.webkitSpeechRecognition)
  const canRecord = typeof window !== 'undefined' && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== 'undefined'
  const voiceWorks = gem ? canRecord : !!SR

  const stop = () => {
    clearInterval(timer.current)
    recording.current = false
    sr.current?.stop()
    if (mr.current && mr.current.state !== 'inactive') mr.current.stop()
    setRec(false)
  }

  useEffect(() => () => {        // leaving the page: release the microphone
    recording.current = false
    clearInterval(timer.current)
    sr.current?.abort?.()
    mr.current?.stream?.getTracks().forEach((tr) => tr.stop())
    stopSpeaking()
  }, [])
  useEffect(() => { if (rec && secs >= MAX_SECONDS) stop() })   // hard cap: 60 s per report

  const reset = () => { setOut(null); setSaved(null); setErr(null); setLive(''); followUp.current = false }

  const handleResult = (r) => {
    setOut(r)
    const rep = r.report
    say([rep.confirmation, rep.follow_up_question].filter(Boolean).join(' '), language)
  }

  const micError = (e) => {
    if (e?.name === 'NotAllowedError' || e === 'not-allowed' || e === 'service-not-allowed') return t('voice.errMicBlocked')
    if (e?.name === 'NotFoundError' || e === 'audio-capture') return t('voice.errNoMic')
    if (e === 'network') return t('voice.errSpeechNetwork')
    if (e === 'language-not-supported') return t('voice.errSpeechLang', { language: meta.languages[language].name })
    return t('voice.errMicOther', { reason: e?.message || e })
  }

  // Browser speech-to-text (used when Gemini is off). Chrome ends "continuous" recognition after
  // a pause, so it is restarted until the worker presses stop, keeping what was already heard.
  const startRecogniser = () => {
    const r = new SR()
    r.lang = bcp; r.continuous = true; r.interimResults = true
    let doneResolve
    srDone.current = new Promise((res) => { doneResolve = res })
    r.onresult = (e) => {
      let interim = ''
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) finals.current += `${e.results[i][0].transcript} `
        else interim += e.results[i][0].transcript
      }
      setLive((finals.current + interim).trim())
    }
    r.onerror = (e) => {
      if (e.error === 'no-speech' || e.error === 'aborted') return
      setErr(micError(e.error))
      stop()
    }
    r.onend = () => {
      if (recording.current) { try { r.start(); return } catch { /* fall through */ } }
      doneResolve()
    }
    r.start()
    sr.current = r
  }

  const start = async (isFollowUp = false) => {
    setErr(null); if (!isFollowUp) { setOut(null); setSaved(null) }
    followUp.current = isFollowUp
    stopSpeaking()                   // never record our own read-back
    finals.current = ''
    setLive('')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const m = new MediaRecorder(stream)
      chunks.current = []
      m.ondataavailable = (e) => e.data.size && chunks.current.push(e.data)
      m.onstop = () => onStop(stream)
      m.start()
      mr.current = m
      recording.current = true
      setRec(true); setSecs(0)
      timer.current = setInterval(() => setSecs((s) => s + 1), 1000)
      if (!gem) startRecogniser()
    } catch (e) { setErr(micError(e)) }
  }

  const onStop = async (stream) => {
    stream.getTracks().forEach((tr) => tr.stop())
    const prev = followUp.current ? out?.report : null
    setBusy(true)
    try {
      if (gem) {
        if (!chunks.current.length) throw new Error(t('voice.errEmpty'))
        const blob = new Blob(chunks.current, { type: mr.current.mimeType || 'audio/webm' })
        const wav = await blobToWav(blob)
        const fd = new FormData()
        fd.append('audio', wav, 'report.wav'); fd.append('phc_id', phcId); fd.append('language', language)
        if (prev) fd.append('previous', JSON.stringify(prev))
        handleResult(await api.form('/api/reports/voice', fd))
      } else {
        await Promise.race([srDone.current, new Promise((r) => setTimeout(r, 2000))])
        const transcript = finals.current.trim() || live
        if (!transcript.trim()) throw new Error(t('voice.errNoSpeech'))
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
      setSaved(r); refresh(); notify(t('voice.saved', { phc: r.phc }))
    } catch (e) {
      if (e.status === 409 && e.detail?.warnings) setOut((o) => ({ ...o, warnings: e.detail.warnings }))
      else setErr(e.message)
    } finally { setBusy(false) }
  }

  const drug = (c) => meta.drugs.find((d) => d.code === c)
  const warningText = (w) => {
    const d = drug(w.drug_code)
    return w.code ? t(`warn.${w.code}`, { ...w, drug: drugLabel(d, uiLang), unit: d ? unitLabel(t, d.unit) : '' }) : w.message
  }
  const rep = out?.report

  return (
    <>
      <div className="page-h">
        <div>
          <div className="eyebrow">{t('voice.eyebrow')}</div>
          <h1>{t('voice.title')}</h1>
          <p>{t('voice.intro')}</p>
        </div>
      </div>

      <div className="voice-hero">
        <Card title={t('voice.step1')} icon="users">
          <div className="stack">
            <div className="row">
              <select className="select" style={{ flex: 1 }} value={phcId ?? ''} disabled={!!userPhc}
                onChange={(e) => { setPhcId(Number(e.target.value)); setLang(null); reset() }} aria-label={t('voice.phc')}>
                {!phcId && <option value="">{t('voice.selectPhc')}</option>}
                {(phcs.data?.phcs || []).map((p) => <option key={p.id} value={p.id}>{p.code} · {p.name} ({p.district_code})</option>)}
              </select>
            </div>
            <div className="eyebrow">{t('voice.reportLanguage')}</div>
            <div className="lang-tabs">
              {[...new Set([phc?.language, uiLang, 'en'])].filter((l) => l && meta.languages[l]).map((l) => (
                <button key={l} className={language === l ? 'on' : ''} onClick={() => { setLang(l); reset() }} lang={l}>{meta.languages[l].native}</button>
              ))}
              <select className="select" value={language} onChange={(e) => { setLang(e.target.value); reset() }} aria-label={t('voice.reportLanguage')}>
                {Object.entries(meta.languages).map(([c, l]) => <option key={c} value={c} lang={c}>{l.native} · {l.name}</option>)}
              </select>
            </div>
            <div className="say" lang={language}>
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <b>{PROMPT[language] || PROMPT.en}</b>
                <SpeakButton text={PROMPT[language] || PROMPT.en} language={PROMPT[language] ? language : 'en'} title={t('voice.playPrompt')} />
              </div>
              <div className="small" style={{ marginTop: 6, opacity: 0.85 }}>{t('voice.eg')} “{SAMPLES[language] || SAMPLES.en}”</div>
            </div>
            <div className="row small">
              <span className="muted">{t('voice.engine')}</span>
              {gem ? <span className="pill ai"><Icon name="spark" size={12} />{t('voice.engineGemini', { model: meta.gemini.model })}</span>
                : <span className="pill grey">{t('voice.engineBrowser')}</span>}
            </div>
          </div>
        </Card>

        <Card title={t('voice.step2')} icon="mic" right={<div className="lang-tabs">
          <button className={mode === 'voice' ? 'on' : ''} onClick={() => setMode('voice')}>{t('voice.modeVoice')}</button>
          <button className={mode === 'text' ? 'on' : ''} onClick={() => setMode('text')}>{t('voice.modeType')}</button></div>}>
          {mode === 'voice' ? (
            <div style={{ textAlign: 'center' }}>
              <button className={`mic ${rec ? 'rec' : ''}`} onClick={() => (rec ? stop() : start(false))} disabled={busy || !phcId || !voiceWorks}
                aria-label={rec ? t('voice.stop') : t('voice.start')} aria-pressed={rec}>
                <Icon name={rec ? 'stop' : 'mic'} size={48} stroke={1.8} />
              </button>
              <div className="num" style={{ fontSize: 'calc(20px * var(--fs, 1))', fontWeight: 700 }} aria-live="polite">
                {rec ? `${clock(secs)} / ${clock(MAX_SECONDS)}` : busy ? t('voice.understanding') : t('voice.tapToSpeak')}
              </div>
              {!phcId && <div className="note" style={{ marginTop: 10 }}>{t('voice.pickPhcFirst')}</div>}
              {busy && <div className="row" style={{ justifyContent: 'center', marginTop: 6 }}><span className="spinner" /> {gem ? t('voice.busyGemini') : t('voice.busyParsing')}</div>}
              {live && <div className="note" style={{ marginTop: 10, textAlign: 'left' }} lang={language}>{live}</div>}
              {!voiceWorks && <div className="note" style={{ marginTop: 10 }}>{gem ? t('voice.noRecorder') : t('voice.noRecognition')}</div>}
            </div>
          ) : (
            <div className="stack">
              <textarea className="textarea" rows={5} value={text} onChange={(e) => setText(e.target.value)} placeholder={t('voice.typePlaceholder')} aria-label={t('voice.typePlaceholder')} lang={language} />
              <div className="row">
                <button className="btn" onClick={() => setText(SAMPLES[language] || SAMPLES.en)}>{t('voice.useSample')}</button>
                <button className="btn primary" onClick={parseText} disabled={busy || !text.trim() || !phcId}>{busy ? <span className="spinner" /> : <Icon name="spark" size={14} />}{t('voice.understand')}</button>
              </div>
              {!phcId && <div className="note">{t('voice.pickPhcFirst')}</div>}
            </div>
          )}
          {err && <div className="err" style={{ marginTop: 10 }} role="alert">{err}</div>}
        </Card>
      </div>

      {rep && (
        <Card title={t('voice.step3')} icon="check" right={<EngineTag engine={out.engine} />}>
          <div className="stack">
            <div className="grid g-2e" style={{ gap: 12 }}>
              <div>
                <div className="eyebrow">{t('voice.transcript', { language: rep.detected_language })}</div>
                <div className="small" style={{ marginTop: 4, lineHeight: 1.55 }} lang={rep.detected_language}>“{rep.transcript}”</div>
                {rep.english_translation && rep.detected_language !== 'en' && (
                  <div className="small muted" style={{ marginTop: 4 }} lang="en">EN: {rep.english_translation}</div>)}
              </div>
              <div className="say" style={{ fontSize: 'calc(14px * var(--fs, 1))' }} lang={language}>
                <div className="row" style={{ justifyContent: 'space-between' }}>
                  <b>{t('voice.readBack')}</b>
                  <SpeakButton text={rep.confirmation} language={language} title={t('voice.playAgain')} />
                </div>
                {rep.confirmation}
              </div>
            </div>
            <div className="parsed-grid">
              {rep.stock.map((s, i) => (
                <label key={s.drug_code + s.kind} className="f" style={flagged.has(s.drug_code) ? FLAG_STYLE : null}>
                  <div className="l">{drugLabel(drug(s.drug_code), uiLang)} ({t(`kind.${s.kind || 'remaining'}`)})</div>
                  <input type="number" value={s.quantity ?? ''} placeholder={t('voice.notReported')} onChange={(e) => editStock(i, e.target.value)} />
                  <div className="l">{unitLabel(t, drug(s.drug_code)?.unit)}</div>
                </label>
              ))}
              {FIELDS.map((k) => (
                <label key={k} className="f" style={flagged.has(k) ? FLAG_STYLE : rep[k] == null ? { borderStyle: 'dashed' } : null}>
                  <div className="l">{t(`field.${k}`)}</div>
                  <input type="number" value={rep[k] ?? ''} placeholder="–" onChange={(e) => edit(k, e.target.value)} />
                </label>
              ))}
            </div>
            {warnings.length > 0 && !saved && (
              <div className="err" role="alert">
                <b>{t('voice.recheck')}</b>
                <ul className="small" style={{ margin: '6px 0 0', paddingLeft: 18 }}>{warnings.map((w, i) => <li key={i}>{warningText(w)}</li>)}</ul>
              </div>
            )}
            {rep.notes && <div className="note">{t('voice.notes')} {rep.notes}</div>}
            {rep.follow_up_question && !saved && (
              <div className="note" style={{ borderColor: '#ffc68a', background: 'var(--orange-100)' }}>
                <div className="row"><b style={{ flex: 1 }} lang={language}>{t('voice.followUp')} {rep.follow_up_question}</b>
                  {mode === 'voice'
                    ? <button className="btn orange sm" onClick={() => (rec ? stop() : start(true))}>{rec ? t('voice.stopShort') : <><Icon name="mic" size={14} />{t('voice.answer')}</>}</button>
                    : <span className="muted small">{t('voice.followUpType')}</span>}
                </div>
              </div>
            )}
            {!saved ? (
              <div className="row">
                <button className="btn primary" onClick={submit} disabled={busy}><Icon name="check" size={15} />{warnings.length ? t('voice.submitChecked') : t('voice.submit')}</button>
                <button className="btn" onClick={reset}>{t('voice.discard')}</button>
                {mode === 'text' && <button className="btn ghost" onClick={() => { followUp.current = true; setText('') }}>{t('voice.addFollowUp')}</button>}
                {rep.confidence != null && <span className="muted small">{t('voice.confidence', { pct: Math.round(rep.confidence * 100) })}</span>}
              </div>
            ) : (
              <div className="stack">
                <div className="row"><span className="pill ok"><Icon name="check" size={12} />{t('voice.savedPill', { id: saved.report_id })}</span>
                  <Link to={`/phc/${phcId}`} className="btn sm">{t('voice.openForecast', { phc: saved.phc })}</Link>
                  <button className="btn sm" onClick={reset}>{t('voice.newReport')}</button></div>
                <div className="table-wrap">
                  <table className="t">
                    <thead><tr><th>{t('th.drug')}</th><th className="r">{t('th.stock')}</th><th className="r">{t('th.cover')}</th><th>{t('th.runsOut')}</th><th>{t('th.status')}</th></tr></thead>
                    <tbody>{saved.items.filter((i) => rep.stock.some((s) => s.drug_code === i.drug_code) || ['critical', 'stocked_out', 'high'].includes(i.status)).map((i) => (
                      <tr key={i.drug_code}><td>{drugLabel(drug(i.drug_code), uiLang)}</td><td className="r num">{fmt(i.stock)}</td>
                        <td className="r num">{t('common.daysShort', { n: fmt(i.cover_days) })}</td><td>{daysText(t, i.days_to_stockout)}</td><td><StatusPill status={i.status} /></td></tr>))}
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
