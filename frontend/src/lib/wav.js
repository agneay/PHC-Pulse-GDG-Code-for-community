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

export function speak(text, bcp47) {
  if (!('speechSynthesis' in window) || !text) return false
  const u = new SpeechSynthesisUtterance(text)
  u.lang = bcp47
  const voice = speechSynthesis.getVoices().find((v) => v.lang === bcp47)
    || speechSynthesis.getVoices().find((v) => v.lang?.startsWith(bcp47.split('-')[0]))
  if (voice) u.voice = voice
  u.rate = 0.95
  speechSynthesis.cancel()
  speechSynthesis.speak(u)
  return !!voice || bcp47.startsWith('en')
}
