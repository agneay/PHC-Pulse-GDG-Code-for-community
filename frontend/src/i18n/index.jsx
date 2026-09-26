import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import en from './en'
import hi from './hi'
import kn from './kn'
import or from './or'
import ta from './ta'

// Languages the whole interface is translated into. The voice-report channel understands more
// (te, bn, mr) through Gemini; adding one here only needs another dictionary file like ta.js.
export const UI_LANGS = {
  en: { native: 'English', english: 'English' },
  ta: { native: 'தமிழ்', english: 'Tamil' },
  hi: { native: 'हिन्दी', english: 'Hindi' },
  kn: { native: 'ಕನ್ನಡ', english: 'Kannada' },
  or: { native: 'ଓଡ଼ିଆ', english: 'Odia' },
}
const DICTS = { en, ta, hi, kn, or }
export const FONT_STEPS = [0.9, 1, 1.12, 1.25, 1.4]

const LANG_KEY = 'phcpulse.lang'
const FONT_KEY = 'phcpulse.fontScale'
const load = (k) => { try { return localStorage.getItem(k) } catch { return null } }
const save = (k, v) => { try { localStorage.setItem(k, v) } catch { /* private mode */ } }

const Ctx = createContext(null)
export const useI18n = () => useContext(Ctx)

/** t('key', { n: 3 }) -> the string in the current language (English if missing), with {n} filled. */
export function translate(lang, key, vars) {
  let s = DICTS[lang]?.[key] ?? en[key] ?? key
  if (vars) s = s.replace(/\{(\w+)\}/g, (m, k) => (vars[k] ?? m))
  return s
}

export function I18nProvider({ children }) {
  const stored = load(LANG_KEY)
  const [lang, setLangState] = useState(stored in UI_LANGS ? stored : null)   // null = not chosen yet
  const [fontScale, setFontScale] = useState(() => {
    const f = Number(load(FONT_KEY))
    return FONT_STEPS.includes(f) ? f : 1
  })

  useEffect(() => {
    document.documentElement.lang = lang || 'en'
  }, [lang])
  useEffect(() => {
    document.documentElement.style.setProperty('--fs', String(fontScale))
    save(FONT_KEY, String(fontScale))
  }, [fontScale])

  const setLang = useCallback((l) => { setLangState(l); save(LANG_KEY, l) }, [])
  const stepFont = useCallback((dir) => setFontScale((f) => {
    const i = FONT_STEPS.indexOf(f) + dir
    return FONT_STEPS[Math.max(0, Math.min(FONT_STEPS.length - 1, i))]
  }), [])

  const active = lang || 'en'
  const t = useCallback((key, vars) => translate(active, key, vars), [active])
  const value = useMemo(() => ({
    lang: active, chosen: !!lang, setLang, t, fontScale, stepFont,
    locale: `${active}-IN`,
  }), [active, lang, setLang, t, fontScale, stepFont])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
