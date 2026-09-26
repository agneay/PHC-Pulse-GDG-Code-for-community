import { useI18n } from '../i18n'
import { fmt, inr } from '../lib/format'
import Icon from './Icon'
import { Card } from './ui'

const lakh = (n) => (Math.abs(n) >= 1e7 ? `₹${fmt(n / 1e7, 1)} Cr` : Math.abs(n) >= 1e5 ? `₹${fmt(n / 1e5, 1)} L` : inr(n))

/** What the recommended transfers achieve, plus a clearly labelled national projection. */
export default function ImpactCard({ impact, national = false }) {
  const { t } = useI18n()
  if (!impact || !impact.units_moved) return null
  const p = impact.national_projection
  const cells = [
    ['alert', fmt(impact.stockout_days_prevented), t('impact.days')],
    ['users', fmt(impact.patients_covered), t('impact.patients')],
    ['download', lakh(impact.net_saving_inr), t('impact.saving')],
    ['pill', fmt(impact.lifesaving_lines), t('impact.lifesaving')],
  ]
  return (
    <Card tour="impact" title={t('impact.title')} icon="check" hint={t('impact.hint')}>
      <div className="impact-grid">
        {cells.map(([icon, v, l]) => (
          <div key={l} className="impact-cell"><Icon name={icon} size={16} /><b className="num">{v}</b><span>{l}</span></div>
        ))}
      </div>
      {national && p && <p className="small" style={{ margin: '12px 0 0' }}>{t('impact.national', {
        phcs: fmt(p.phcs), days: fmt(p.stockout_days_prevented), patients: fmt(p.patients_covered), saving: lakh(p.net_saving_inr) })}</p>}
      <p className="muted small" style={{ margin: '8px 0 0' }}>{t('impact.assumptions')}</p>
    </Card>
  )
}
