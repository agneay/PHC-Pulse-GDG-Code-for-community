export const HEALTH_COLOR = { green: '#2e7d32', amber: '#e69100', red: '#c62828' }

// Numbers stay in Western digits with Indian grouping (1,20,000), as in government forms.
export const fmt = (n, d = 0) =>
  n === null || n === undefined || Number.isNaN(n) ? '–' : Number(n).toLocaleString('en-IN', { maximumFractionDigits: d })
export const pct = (x) => (x === null || x === undefined ? '–' : `${Math.round(x * 100)}%`)
export const inr = (n) => `₹${fmt(n)}`
export const shortDay = (iso, locale = 'en-IN') => {
  const d = new Date(iso)
  return d.toLocaleDateString(locale, { day: 'numeric', month: 'short' })
}
export const daysText = (t, d) =>
  d === null || d === undefined ? t('days.none') : d <= 0 ? t('days.now') : d === 1 ? t('days.one') : t('days.many', { n: d })

/** Local-language drug name where the catalogue has one (hi/ta/kn/or), else the generic name. */
export const drugLabel = (d, lang) => (d ? (lang !== 'en' && d.names?.[lang]) || d.name : '')
export const unitLabel = (t, unit) => t(`unit.${unit}`)

/** "diarrhoea anomaly (x4.2)" from the engine -> localised text. */
export function surgeText(t, reason) {
  const m = /^(\w+) anomaly \(x([\d.]+)\)$/.exec(reason || '')
  return m ? t('stock.surgeReason', { syndrome: t(`syndrome.${m[1]}`), ratio: m[2] }) : reason
}

/** "text with **bold** parts" -> React children (translations keep their own word order). */
export function rich(text) {
  return String(text).split('**').map((part, i) => (i % 2 ? <b key={i}>{part}</b> : part))
}
