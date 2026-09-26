// Speech settings per language.
// stt:   codes to try, in order, for the browser's speech-to-text (used only when Gemini is off;
//        Gemini hears all 23 languages directly). The last entry may be a closely related
//        spoken language: numbers and drug names still come through for the rules parser.
// voice: a language whose device voice can read this one's script aloud, used only when there
//        is neither a voice for the language itself nor Gemini read-aloud.
export const SPEECH = {
  en: { stt: ['en-IN'] },
  hi: { stt: ['hi-IN'] },
  bn: { stt: ['bn-IN', 'bn-BD'] },
  te: { stt: ['te-IN'] },
  mr: { stt: ['mr-IN'] },
  ta: { stt: ['ta-IN'] },
  ur: { stt: ['ur-IN', 'ur-PK', 'hi-IN'] },
  gu: { stt: ['gu-IN'] },
  kn: { stt: ['kn-IN'] },
  or: { stt: ['or-IN'] },
  ml: { stt: ['ml-IN'] },
  pa: { stt: ['pa-Guru-IN', 'pa-IN'] },
  as: { stt: ['as-IN', 'bn-IN'], voice: 'bn' },
  mai: { stt: ['mai-IN', 'hi-IN'], voice: 'hi' },
  sat: { stt: ['sat-IN', 'hi-IN'] },
  ks: { stt: ['ks-IN', 'ur-IN'], voice: 'ur' },
  ne: { stt: ['ne-IN', 'ne-NP', 'hi-IN'], voice: 'hi' },
  sd: { stt: ['sd-IN', 'ur-IN'], voice: 'ur' },
  kok: { stt: ['kok-IN', 'mr-IN'], voice: 'mr' },
  doi: { stt: ['doi-IN', 'hi-IN'], voice: 'hi' },
  mni: { stt: ['mni-IN', 'en-IN'] },
  brx: { stt: ['brx-IN', 'hi-IN'], voice: 'hi' },
  sa: { stt: ['sa-IN', 'hi-IN'], voice: 'hi' },
}

/** Recognition codes to try for `language`, most specific first. */
export const sttCodes = (language, bcp47) => SPEECH[language]?.stt || [bcp47 || 'en-IN']
