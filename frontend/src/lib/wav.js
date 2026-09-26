// Convert a MediaRecorder blob (webm/opus, mp4...) to 16 kHz mono 16-bit WAV, a format Gemini
// accepts everywhere and that stays small (~32 KB/s, so a 60 s report is ~2 MB).
export async function blobToWav(blob, targetRate = 16000) {
  const buf = await blob.arrayBuffer()
  const Ctx = window.AudioContext || window.webkitAudioContext
  const ctx = new Ctx()
  const decoded = await ctx.decodeAudioData(buf)
  ctx.close()
  const length = Math.ceil(decoded.duration * targetRate)
  const off = new OfflineAudioContext(1, length, targetRate)
  const src = off.createBufferSource()
  src.buffer = decoded
  src.connect(off.destination)
  src.start()
  const rendered = await off.startRendering()
  return encodeWav(rendered.getChannelData(0), targetRate)
}

function encodeWav(samples, rate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2)
  const v = new DataView(buffer)
  const w = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)) }
  w(0, 'RIFF'); v.setUint32(4, 36 + samples.length * 2, true); w(8, 'WAVE'); w(12, 'fmt ')
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true)
  v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true)
  v.setUint16(34, 16, true); w(36, 'data'); v.setUint32(40, samples.length * 2, true)
  let o = 44
  for (let i = 0; i < samples.length; i++, o += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]))
    v.setInt16(o, s < 0 ? s * 0x8000 : s * 0x7fff, true)
  }
  return new Blob([buffer], { type: 'audio/wav' })
}

// ---------------------------------------------------------------- read-aloud
// The browser's voice list loads asynchronously (it is empty on the first call), and most
// Windows / many Android devices have no Tamil, Kannada or Odia voice at all. So: use a device
// voice when one exists for the language, otherwise play Gemini TTS audio from the server.
let voicesPromise = null
function deviceVoices() {
  if (!('speechSynthesis' in window)) return Promise.resolve([])
  const now = speechSynthesis.getVoices()
  if (now.length) return Promise.resolve(now)
  voicesPromise ||= new Promise((resolve) => {
    const done = () => resolve(speechSynthesis.getVoices())
    speechSynthesis.addEventListener('voiceschanged', done, { once: true })
    setTimeout(done, 1500)
  })
  return voicesPromise
}

function voiceFor(voices, bcp47) {
  const lang = bcp47.toLowerCase()
  const base = lang.split('-')[0]
  return voices.find((v) => v.lang?.toLowerCase().replace('_', '-') === lang)
    || voices.find((v) => v.lang?.toLowerCase().split(/[-_]/)[0] === base)
}

let playing = null
export function stopSpeaking() {
  if ('speechSynthesis' in window) speechSynthesis.cancel()
  if (playing) { playing.pause(); playing = null }
}

/** Speak `text` in `bcp47` (e.g. "ta-IN"). Order: a device voice for the language, then Gemini
 *  read-aloud, then a device voice for `nearBcp47` (a language sharing the script, e.g. Hindi for
 *  Maithili). Resolves to 'device' | 'gemini' | 'near'; rejects when none of them is available. */
export async function speak(text, bcp47, { fetchAudio, nearBcp47 } = {}) {
  if (!text) return null
  stopSpeaking()
  const voices = await deviceVoices()
  const say = (voice) => {
    const u = new SpeechSynthesisUtterance(text)
    u.lang = voice.lang; u.voice = voice; u.rate = 0.95
    speechSynthesis.speak(u)
  }
  const own = voiceFor(voices, bcp47)
  if (own) { say(own); return 'device' }
  const near = nearBcp47 && voiceFor(voices, nearBcp47)
  if (fetchAudio) {
    try {
      const url = URL.createObjectURL(await fetchAudio(text))
      const audio = new Audio(url)
      audio.onended = () => URL.revokeObjectURL(url)
      playing = audio
      await audio.play()
      return 'gemini'
    } catch (e) {
      if (!near) throw e
    }
  }
  if (near) { say(near); return 'near' }
  throw Object.assign(new Error(`No voice for ${bcp47} on this device`), { code: 'no-voice' })
}
