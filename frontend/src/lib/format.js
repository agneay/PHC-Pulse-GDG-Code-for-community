export const STATUS_LABEL = {
  stocked_out: 'Stocked out', critical: 'Critical ≤7d', high: 'High ≤14d', watch: 'Watch ≤21d',
  ok: 'OK', surplus: 'Surplus',
}
export const HEALTH_COLOR = { green: '#2e7d32', amber: '#e69100', red: '#c62828' }
export const SYNDROME_LABEL = {
  fever: 'Fever', diarrhoea: 'Diarrhoea', respiratory: 'Respiratory', opd: 'Total OPD',
}
export const TRANSFER_LABEL = {
  approved: 'Approved', in_transit: 'In transit', delivered: 'Delivered', cancelled: 'Cancelled',
}

export const fmt = (n, d = 0) =>
  n === null || n === undefined || Number.isNaN(n) ? '–' : Number(n).toLocaleString('en-IN', { maximumFractionDigits: d })
export const pct = (x) => (x === null || x === undefined ? '–' : `${Math.round(x * 100)}%`)
export const inr = (n) => `₹${fmt(n)}`
export const shortDay = (iso) => {
  const d = new Date(iso)
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
}
export const daysText = (d) => (d === null || d === undefined ? '>28 days' : d <= 0 ? 'now' : `${d} day${d === 1 ? '' : 's'}`)
