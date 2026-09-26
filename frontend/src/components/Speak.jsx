import { useCallback, useState } from 'react'
import { useApp } from '../App'
import { useI18n } from '../i18n'
import { ttsAudio } from '../lib/api'
import { SPEECH } from '../lib/speech'
import { speak } from '../lib/wav'
import Icon from './Icon'

/** say(text, languageCode): device voice if the device has one, else Gemini read-aloud.
 *  Failures surface as a toast instead of silence. */
export function useSpeak() {
  const { meta, notify } = useApp()
  const { t } = useI18n()
  return useCallback(async (text, language) => {
    const bcp = meta.languages[language]?.bcp47 || 'en-IN'
    const near = SPEECH[language]?.voice
    try {
      const how = await speak(text, bcp, {
        fetchAudio: meta.gemini.enabled ? (x) => ttsAudio(x, language) : null,
        nearBcp47: near && meta.languages[near]?.bcp47,
      })
      if (how === 'near') {
        notify(t('speech.nearVoice', { language: meta.languages[language].native, near: meta.languages[near].native }))
      }
      return how
    } catch (e) {
      const reason = e.code === 'no-voice' ? t('speech.noVoice') : e.message
      notify(t('speech.unavailable', { language: meta.languages[language]?.native || language, reason }))
      return null
    }
  }, [meta, notify, t])
}

export function SpeakButton({ text, language, title }) {
  const say = useSpeak()
  const { t } = useI18n()
  const [busy, setBusy] = useState(false)
  return (
    <button className="btn ghost sm" type="button" title={title || t('speech.readAloud')} aria-label={title || t('speech.readAloud')}
      disabled={busy || !text} onClick={async () => { setBusy(true); try { await say(text, language) } finally { setBusy(false) } }}>
      {busy ? <span className="spinner" /> : <Icon name="speaker" size={15} />}
    </button>
  )
}
