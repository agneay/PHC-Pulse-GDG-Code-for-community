import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import as from './as'
import bn from './bn'
import brx from './brx'
import doi from './doi'
import en from './en'
import gu from './gu'
import hi from './hi'
import kn from './kn'
import kok from './kok'
import ks from './ks'
import mai from './mai'
import ml from './ml'
import mni from './mni'
import mr from './mr'
import ne from './ne'
import or from './or'
import pa from './pa'
import sa from './sa'
import sat from './sat'
import sd from './sd'
import ta from './ta'
import te from './te'
import ur from './ur'

// English + the 22 languages of the Eighth Schedule. Any key a dictionary lacks falls back to
// English. `draft` = machine-assisted, awaiting native review; `partial` = only the core interface.
export const UI_LANGS = {
  en: { native: 'English', english: 'English' },
  hi: { native: 'हिन्दी', english: 'Hindi' },
  bn: { native: 'বাংলা', english: 'Bengali' },
  te: { native: 'తెలుగు', english: 'Telugu' },
  mr: { native: 'मराठी', english: 'Marathi' },
  ta: { native: 'தமிழ்', english: 'Tamil' },
  ur: { native: 'اردو', english: 'Urdu', rtl: true },
  gu: { native: 'ગુજરાતી', english: 'Gujarati' },
  kn: { native: 'ಕನ್ನಡ', english: 'Kannada' },
  or: { native: 'ଓଡ଼ିଆ', english: 'Odia' },
  ml: { native: 'മലയാളം', english: 'Malayalam' },
  pa: { native: 'ਪੰਜਾਬੀ', english: 'Punjabi' },
  as: { native: 'অসমীয়া', english: 'Assamese', draft: true },
  mai: { native: 'मैथिली', english: 'Maithili', draft: true },
  ne: { native: 'नेपाली', english: 'Nepali', draft: true },
  kok: { native: 'कोंकणी', english: 'Konkani', draft: true },
  doi: { native: 'डोगरी', english: 'Dogri', draft: true },
  sa: { native: 'संस्कृतम्', english: 'Sanskrit', draft: true },
  ks: { native: 'کٲشُر', english: 'Kashmiri', rtl: true, draft: true, partial: true },
  sd: { native: 'سنڌي', english: 'Sindhi', rtl: true, draft: true, partial: true },
  brx: { native: "बर'", english: 'Bodo', draft: true, partial: true },
  sat: { native: 'ᱥᱟᱱᱛᱟᱲᱤ', english: 'Santali', draft: true, partial: true },
  mni: { native: 'ꯃꯩꯇꯩꯂꯣꯟ', english: 'Manipuri', draft: true, partial: true },
}
const DICTS = { as, bn, brx, doi, en, gu, hi, kn, kok, ks, mai, ml, mni, mr, ne, or, pa, sa, sat, sd, ta, te, ur }
export const FONT_STEPS = [0.9, 1, 1.12, 1.25, 1.4]

// Scripts that many devices lack a font for; fetched only when that language is picked.
const WEB_FONTS = {
  ur: 'Noto+Nastaliq+Urdu:wght@400;700',
  ks: 'Noto+Nastaliq+Urdu:wght@400;700',
  sd: 'Noto+Naskh+Arabic:wght@400;700',
  sat: 'Noto+Sans+Ol+Chiki:wght@400;700',
  mni: 'Noto+Sans+Meetei+Mayek:wght@400;700',
}
function loadFont(lang) {
  const family = WEB_FONTS[lang]
  if (!family || document.getElementById(`font-${lang}`)) return
  const link = document.createElement('link')
  link.id = `font-${lang}`
  link.rel = 'stylesheet'
  link.href = `https://fonts.googleapis.com/css2?family=${family}&display=swap`
  document.head.appendChild(link)
}

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
    const l = lang || 'en'
    document.documentElement.lang = l
    document.documentElement.dir = UI_LANGS[l]?.rtl ? 'rtl' : 'ltr'
    loadFont(l)
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
    locale: `${active}-IN-u-nu-latn`, rtl: !!UI_LANGS[active]?.rtl,
  }), [active, lang, setLang, t, fontScale, stepFont])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
