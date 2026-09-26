import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useApp } from '../App'
import Icon from '../components/Icon'
import MapView from '../components/MapView'
import { SpeakButton } from '../components/Speak'
import { Card, EngineTag, ErrorBox, Kpi, Loading, useAsync } from '../components/ui'
import { useI18n } from '../i18n'
import { api } from '../lib/api'
import { drugLabel, fmt, inr, rich, unitLabel } from '../lib/format'
import { inScope } from '../lib/labels'

const KINDS = [['flood', 'wave'], ['cyclone', 'wind'], ['vector', 'bug'], ['cholera', 'drop'], ['heatwave', 'sun']]
const SEVERITIES = ['moderate', 'severe', 'extreme']
const DURATIONS = [7, 14, 21, 28]

export default function Emergency() {
  const { meta, filter, scopeQs } = useApp()
  const { t, lang } = useI18n()
  const scope = meta.user.scope || {}
  const presets = useAsync(() => api.get('/api/scenarios'), [])
  const overview = useAsync(() => api.get(`/api/overview${scopeQs}`), [scopeQs])
  const districts = meta.districts.filter((d) => inScope(scope, { id: null, district_code: d.code, state_code: d.state })
    && (!filter.state || d.state === filter.state))
  const [kind, setKind] = useState('flood')
  const [severity, setSeverity] = useState('severe')
  const [duration, setDuration] = useState(null)          // null = the preset's typical duration
  const [sel, setSel] = useState(() => (scope.district ? [scope.district] : []))
  const [res, setRes] = useState(null)
  const [plan, setPlan] = useState(null)
  const [planLang, setPlanLang] = useState(meta.languages[lang] ? lang : 'en')
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)
  const drug = useMemo(() => Object.fromEntries(meta.drugs.map((d) => [d.code, d])), [meta.drugs])
  const dname = Object.fromEntries(meta.districts.map((d) => [d.code, d.name]))

  if (meta.user.role === 'phc') return <Card><div className="empty">{t('emg.phcOnly')}</div></Card>
  if (presets.error) return <ErrorBox error={presets.error} />
  if (!presets.data) return <Loading />
  const preset = presets.data.presets[kind]
  const body = { kind, severity, districts: sel, ...(duration ? { duration } : {}) }

  const run = async () => {
    if (!sel.length) { setErr(t('emg.pickDistrict')); return }
    setBusy('run'); setErr(null); setPlan(null)
    try { setRes(await api.post('/api/scenarios/run', body)) } catch (e) { setErr(e.message) } finally { setBusy(null) }
  }
  const writePlan = async () => {
    setBusy('plan'); setErr(null)
    try { setPlan(await api.post('/api/scenarios/plan', { ...body, language: planLang })) } catch (e) { setErr(e.message) } finally { setBusy(null) }
  }
  const toggle = (c) => { setSel((s) => (s.includes(c) ? s.filter((x) => x !== c) : [...s, c])); setRes(null); setPlan(null) }
  const change = (fn) => (v) => { fn(v); setRes(null); setPlan(null) }
  const drivers = Object.entries(preset.drugs).map(([c, m]) => `${drugLabel(drug[c], lang)} ×${fmt(1 + (m - 1) * presets.data.severity[severity], 1)}`).join(' · ')

  const riskIds = new Set((res?.new_risks || []).map((r) => r.phc.id))
  const mapPhcs = res ? (overview.data?.phcs || []).filter((p) => res.districts.includes(p.district_code))
    .map((p) => ({ ...p, health: riskIds.has(p.id) ? 'red' : 'green' })) : []

  return (
    <>
      <div className="page-h">
        <div>
          <div className="eyebrow">{t('emg.eyebrow')}</div>
          <h1>{t('emg.title')}</h1>
          <p>{rich(t('emg.intro'))}</p>
        </div>
      </div>

      <div className="grid g-2">
        <Card tour="emergency" title={t('emg.step1')} icon="siren">
          <div className="scn-kinds" role="radiogroup" aria-label={t('emg.step1')}>
            {KINDS.map(([k, icon]) => (
              <button key={k} role="radio" aria-checked={kind === k} className={`scn-kind ${kind === k ? 'on' : ''}`}
                onClick={() => change(setKind)(k)}>
                <Icon name={icon} size={22} /><span>{t(`emg.kind.${k}`)}</span>
              </button>
            ))}
          </div>
          <p className="muted small" style={{ marginBottom: 0 }}>{t('emg.drivers', { list: drivers })}</p>
        </Card>
        <Card title={t('emg.step2')} icon="map">
          <div className="stack">
            <div>
              <div className="eyebrow">{t('emg.districts')}</div>
              <div className="lang-tabs" style={{ marginTop: 6 }}>
                {districts.map((d) => (
                  <button key={d.code} className={sel.includes(d.code) ? 'on' : ''} aria-pressed={sel.includes(d.code)}
                    onClick={() => toggle(d.code)}>{d.name}</button>
                ))}
              </div>
            </div>
            <div className="row" style={{ flexWrap: 'wrap', gap: 16 }}>
              <div>
                <div className="eyebrow">{t('emg.severity')}</div>
                <div className="lang-tabs" style={{ marginTop: 6 }}>
                  {SEVERITIES.map((s) => <button key={s} className={severity === s ? 'on' : ''} onClick={() => change(setSeverity)(s)}>{t(`emg.sev.${s}`)}</button>)}
                </div>
              </div>
              <label>
                <div className="eyebrow">{t('emg.duration')}</div>
                <select className="select" style={{ marginTop: 6 }} value={duration ?? ''} onChange={(e) => change(setDuration)(e.target.value ? Number(e.target.value) : null)}>
                  <option value="">{t('emg.days', { n: preset.duration })}</option>
                  {DURATIONS.filter((d) => d !== preset.duration).map((d) => <option key={d} value={d}>{t('emg.days', { n: d })}</option>)}
                </select>
              </label>
            </div>
            <div className="row">
              <button className="btn primary" onClick={run} disabled={!!busy}>
                {busy === 'run' ? <><span className="spinner" />{t('emg.running')}</> : <><Icon name="siren" size={16} />{t('emg.run')}</>}
              </button>
              <span className="muted small">{t('emg.simOnly')}</span>
            </div>
            {err && <div className="note" style={{ borderColor: 'var(--red)' }}>{err}</div>}
          </div>
        </Card>
      </div>

      {res && (
        <>
          <div className="grid g-kpi">
            <Kpi icon="alert" tone="alert" label={t('emg.kpiRisk')} value={`${res.baseline.at_risk_lines} → ${res.scenario.at_risk_lines}`}
              sub={t('emg.kpiRiskSub')} />
            <Kpi icon="users" label={t('emg.kpiPhcs')} value={res.affected_phcs} sub={t('emg.kpiPhcsSub', { x: fmt(res.opd_multiplier, 1) })} />
            <Kpi icon="bed" tone={res.scenario.phcs_over_bed_capacity ? 'warn' : ''} label={t('emg.kpiBeds')} value={res.scenario.phcs_over_bed_capacity} sub={t('emg.kpiBedsSub')} />
            <Kpi icon="truck" label={t('emg.kpiMoves')} value={res.plan.shipment_count} sub={t('emg.kpiMovesSub', { units: fmt(res.plan.units), cost: inr(res.plan.cost_inr) })} />
            <Kpi icon="pill" tone={res.plan.escalation_count ? 'warn' : ''} label={t('emg.kpiIndents')} value={res.plan.escalation_count} sub={t('emg.kpiIndentsSub', { units: fmt(res.plan.escalation_units) })} />
          </div>

          <div className="grid g-2">
            <Card title={t('emg.newRisks')} icon="alert" hint={t('emg.newRisksHint')} bodyClass="table-wrap">
              {!res.new_risks.length ? <div className="empty">{t('emg.noNewRisks')}</div> : (
                <table className="t">
                  <thead><tr><th>{t('th.phc')}</th><th>{t('th.drug')}</th><th className="r">{t('th.runsOutIn')}</th><th className="r">{t('emg.usesPerDay')}</th></tr></thead>
                  <tbody>
                    {res.new_risks.map((r) => (
                      <tr key={`${r.phc.id}-${r.drug_code}`}>
                        <td><Link to={`/phc/${r.phc.id}`}><b>{r.phc.code}</b></Link> <span className="muted">{r.phc.name.replace('PHC ', '')}</span></td>
                        <td>{drugLabel(drug[r.drug_code], lang)} {r.lifesaving && <span className="pill critical">{t('emg.lifesaving')}</span>}</td>
                        <td className="r num"><b>{t('days.many', { n: r.days_to_stockout ?? 0 })}</b></td>
                        <td className="r num">{fmt(r.daily_forecast, 1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Card>
            <Card title={t('emg.map')} icon="map" bodyClass="">
              <MapView phcs={mapPhcs} lanes={res.plan.shipments} />
            </Card>
          </div>

          <div className="grid g-2">
            <Card title={t('emg.moves')} icon="truck" bodyClass="table-wrap">
              {!res.plan.shipments.length ? <div className="empty">{t('emg.noMoves')}</div> : (
                <table className="t">
                  <thead><tr><th>{t('th.lane')}</th><th>{t('th.items')}</th><th className="r">km</th></tr></thead>
                  <tbody>
                    {res.plan.shipments.map((s) => (
                      <tr key={s.id}>
                        <td className="small"><b>{s.from.name.replace('PHC ', '')}</b> → <b>{s.to.name.replace('PHC ', '')}</b></td>
                        <td className="small">{s.lines.map((l) => `${fmt(l.qty)} ${unitLabel(t, drug[l.drug_code].unit)} ${drugLabel(drug[l.drug_code], lang)}`).join(', ')}</td>
                        <td className="r num">{fmt(s.distance_km)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Card>
            <Card title={t('emg.indents')} icon="pill" bodyClass="table-wrap">
              {!res.plan.escalations.length ? <div className="empty">{t('emg.noMoves')}</div> : (
                <table className="t">
                  <thead><tr><th>{t('th.phc')}</th><th>{t('th.drug')}</th><th className="r">{t('emg.qty')}</th><th className="r">{t('th.neededIn')}</th></tr></thead>
                  <tbody>
                    {res.plan.escalations.map((e) => (
                      <tr key={e.phc.id + e.drug_code}>
                        <td className="small"><b>{e.phc.name.replace('PHC ', '')}</b> <span className="muted">{dname[e.phc.district_code]}</span></td>
                        <td className="small">{drugLabel(drug[e.drug_code], lang)}</td>
                        <td className="r num">{fmt(e.qty)} {unitLabel(t, drug[e.drug_code].unit)}</td>
                        <td className="r num">{t('days.many', { n: e.needed_in_days })}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Card>
          </div>

          <Card className="ai-card" title={t('emg.plan')} icon="spark"
            right={<div className="row">
              <select className="select" value={planLang} onChange={(e) => setPlanLang(e.target.value)} aria-label={t('brief.language')}>
                {Object.entries(meta.languages).map(([c, l]) => <option key={c} value={c} lang={c}>{l.native} · {l.name}</option>)}
              </select>
              <button className="btn primary sm" onClick={writePlan} disabled={!!busy}>
                {busy === 'plan' ? <span className="spinner" /> : <Icon name="spark" size={14} />}{t('emg.generate')}
              </button>
            </div>}>
            {!plan ? <p className="muted small" style={{ margin: 0 }}>{t('emg.planIntro')}</p> : (
              <div className="stack" lang={planLang}>
                <div className="row" style={{ justifyContent: 'space-between' }}>
                  <b>{plan.headline}</b>
                  <div className="row"><EngineTag engine={plan.engine} />
                    <SpeakButton text={`${plan.headline}. ${plan.summary}. ${plan.actions.join('. ')}`} language={planLang} /></div>
                </div>
                <p className="small" style={{ margin: 0 }}>{plan.summary}</p>
                <div className="eyebrow">{t('brief.doToday')}</div>
                <ol className="small" style={{ margin: 0 }}>{plan.actions.map((a, i) => <li key={i}>{a}</li>)}</ol>
                {!!plan.risks?.length && <><div className="eyebrow">{t('brief.watch')}</div>
                  <ul className="small" style={{ margin: 0 }}>{plan.risks.map((a, i) => <li key={i}>{a}</li>)}</ul></>}
              </div>
            )}
          </Card>
        </>
      )}
    </>
  )
}
