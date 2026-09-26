// Labels the server sends in English (persona names, scope), rebuilt in the UI language.
const stateName = (meta, code) => meta.states.find((s) => s.code === code)?.name || code
const districtName = (meta, code) => meta.districts.find((d) => d.code === code)?.name || code

export function personaName(p, t, meta) {
  if (!p) return ''
  if (p.role === 'national') return t('persona.national')
  if (p.role === 'state') return t('persona.state', { state: stateName(meta, p.scope.state) })
  if (p.role === 'district') return t('persona.district', { district: districtName(meta, p.scope.district) })
  return t('persona.phc', { phc: p.name.replace(/^Medical Officer, /, '') })
}

export function scopeLabel(scope, t, meta, fallback) {
  if (scope?.phc_id) return fallback
  if (scope?.district) return t('scope.district', { district: districtName(meta, scope.district), state: stateName(meta, scope.state) })
  if (scope?.state) return stateName(meta, scope.state)
  return t('scope.india')
}
