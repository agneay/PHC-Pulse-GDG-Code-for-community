import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useApp } from '../App'
import Icon from '../components/Icon'
import MapView from '../components/MapView'
import { Card, ErrorBox, Kpi, Loading, useAsync } from '../components/ui'
import { useI18n } from '../i18n'
import { api } from '../lib/api'
import { drugLabel, fmt, inr, unitLabel } from '../lib/format'

const STEPS = ['approved', 'in_transit', 'delivered']

export default function Redistribution() {
  const { scopeQs, version, refresh, notify, meta } = useApp()
  const { t, lang } = useI18n()
  const [cross, setCross] = useState(false)
  const [sel, setSel] = useState(null)
  const [busy, setBusy] = useState(null)
  const sep = scopeQs ? '&' : '?'
  const { data, error, loading } = useAsync(
    () => api.get(`/api/redistribution${scopeQs}${sep}cross_state=${cross}`), [scopeQs, version, cross])
  const drug = Object.fromEntries(meta.drugs.map((d) => [d.code, d]))
  const dname = (code) => drugLabel(drug[code], lang)
  const canApprove = meta.user.role !== 'phc'

  if (error) return <ErrorBox error={error} />
  if (loading && !data) return <Loading label={t('redis.solving')} />

  const approve = async (s) => {
    const items = s.lines.map((l) => `${fmt(l.qty)} ${unitLabel(t, drug[l.drug_code].unit)} ${dname(l.drug_code)}`).join(', ')
    if (!window.confirm(t('redis.confirm', { from: s.from.code, to: s.to.code, items, km: fmt(s.distance_km), cost: inr(s.cost_inr) }))) return
    setBusy(s.id)
    try {
      await api.post(`/api/redistribution/${s.id}/approve?cross_state=${cross}`)
      notify(t('redis.approved', { from: s.from.code, to: s.to.code }))
      refresh()
    } catch (e) { notify(e.message) } finally { setBusy(null) }
  }
  const advance = async (tr, status) => {
    setBusy(`t${tr.id}`)
    try {
      await api.post(`/api/transfers/${tr.id}/status`, { status })
      notify(`${tr.from_code} → ${tr.to_code}: ${t(`transfer.${status}`)}`)
      refresh()
    } catch (e) { notify(e.message) } finally { setBusy(null) }
  }

  const st = data.stats
  const active = data.transfers.filter((tr) => tr.status !== 'cancelled')
  const lanes = [
    ...data.shipments,
    ...active.filter((tr) => tr.status !== 'delivered').map((tr) => ({
      id: `t${tr.id}`, status: tr.status, lines: tr.lines,
      from: { code: tr.from_code, lat: tr.from_lat, lon: tr.from_lon }, to: { code: tr.to_code, lat: tr.to_lat, lon: tr.to_lon } })),
  ]
  const endpoints = {}
  data.shipments.forEach((s) => { endpoints[s.from.id] = s.from; endpoints[s.to.id] = s.to })
  const mapPhcs = Object.values(endpoints).map((p) => ({ ...p, health: 'amber', score: '–', critical_items: '–' }))

  return (
    <>
      <div className="page-h">
        <div>
          <div className="eyebrow">{t('redis.eyebrow')}</div>
          <h1>{t('redis.title')}</h1>
          <p>{t('redis.intro')}</p>
        </div>
        <div className="right">
          <label className="btn" title={t('redis.crossTitle')}>
            <input type="checkbox" checked={cross} onChange={(e) => setCross(e.target.checked)} /> {t('redis.cross')}
          </label>
        </div>
      </div>

      {st.failed && <div className="err" role="alert">{t('redis.failed', { solver: st.solver })}</div>}
      {!st.failed && st.time_limited && <div className="note">{t('redis.timeLimited')}</div>}

      <div className="grid g-kpi">
        <Kpi icon="truck" label={t('redis.kpiShipments')} value={data.shipments.length} sub={t('redis.kpiShipmentsSub', { n: st.lanes ?? 0 })} />
        <Kpi icon="pill" label={t('redis.kpiUnits')} value={fmt(st.units_moved)} sub={t('redis.kpiUnitsSub', { pct: st.coverage != null ? Math.round(st.coverage * 100) : 0 })} tone="good" />
        <Kpi icon="map" label={t('redis.kpiCost')} value={inr(st.cost)} sub={t('redis.kpiCostSub')} />
        <Kpi icon="alert" label={t('redis.kpiEscalate')} value={data.escalations.length} sub={t('redis.kpiEscalateSub')} tone="warn" />
      </div>

      <div className="grid g-2">
        <Card title={t('redis.recommended')} icon="truck" hint={t('redis.byUrgency')}
          bodyClass="card-b" right={<span className="muted small">{st.solver}</span>}>
          <div className="stack" style={{ maxHeight: 620, overflowY: 'auto', paddingRight: 4 }}>
            {data.shipments.map((s) => (
              <div key={s.id} className={`rec ${sel === s.id ? 'sel' : ''}`} onMouseEnter={() => setSel(s.id)}>
                <div className="lane">
                  <Link to={`/phc/${s.from.id}`}>{s.from.code}</Link><span className="muted small">{s.from.name.replace('PHC ', '')}</span>
                  <Icon name="arrow" size={15} />
                  <Link to={`/phc/${s.to.id}`}>{s.to.code}</Link><span className="muted small">{s.to.name.replace('PHC ', '')}</span>
                  <span className={`pill ${s.urgency_days <= 7 ? 'critical' : 'high'}`} style={{ marginLeft: 'auto' }}>{s.urgency_days <= 0 ? t('ship.stockedOut') : t('ship.neededIn', { n: s.urgency_days })}</span>
                </div>
                {s.lines.map((l) => (
                  <div key={l.drug_code} className="msg">
                    “{l.needed_in_days <= 0
                      ? t('redis.lineOut', { from: s.from.code, to: s.to.code, drug: dname(l.drug_code) })
                      : t('redis.lineNeeds', { from: s.from.code, to: s.to.code, drug: dname(l.drug_code), n: l.needed_in_days })}”
                    <b> {t('redis.ship', { qty: fmt(l.qty), unit: unitLabel(t, drug[l.drug_code].unit) })}</b>
                  </div>
                ))}
                <div className="meta">
                  <span>{t('redis.byRoad', { km: fmt(s.distance_km) })}</span><span>{t('redis.eta', { h: s.eta_hours })}</span><span>{inr(s.cost_inr)}</span>
                  {s.cross_state ? <span className="pill surplus">{t('redis.interState')}</span> : s.cross_district ? <span className="pill grey">{t('redis.crossDistrict')}</span> : <span className="pill grey">{t('redis.sameDistrict')}</span>}
                  {s.lines.length > 1 && <span className="pill ok">{t('redis.consolidated', { n: s.lines.length })}</span>}
                </div>
                {canApprove && (
                  <div className="row">
                    <button className="btn primary sm" onClick={() => approve(s)} disabled={busy === s.id}>
                      {busy === s.id ? <span className="spinner" /> : <Icon name="check" size={14} />}{t('redis.approve')}
                    </button>
                  </div>
                )}
              </div>
            ))}
            {!data.shipments.length && !st.failed && <div className="empty">{t('redis.none')}</div>}
          </div>
        </Card>
        <Card title={t('redis.lanes')} icon="map" hint={t('redis.lanesHint')} bodyClass="">
          <MapView phcs={mapPhcs} lanes={lanes} selectedLane={sel} onLaneClick={setSel} tall />
        </Card>
      </div>

      <Card title={t('redis.tracker')} icon="refresh" hint={t('redis.trackerHint')} bodyClass="table-wrap">
        {!active.length ? <div className="empty">{t('redis.noTransfers')}</div> : (
          <table className="t">
            <thead><tr><th>{t('th.lane')}</th><th>{t('th.items')}</th><th>{t('th.progress')}</th><th>{t('th.approvedBy')}</th><th /></tr></thead>
            <tbody>
              {active.map((tr) => {
                const idx = STEPS.indexOf(tr.status)
                return (
                  <tr key={tr.id}>
                    <td><b>{tr.from_code}</b> → <b>{tr.to_code}</b><div className="muted small">{fmt(tr.distance_km)} km · {inr(tr.cost_inr)}</div></td>
                    <td className="small">{tr.lines.map((l) => `${fmt(l.qty)} ${unitLabel(t, l.unit)} ${dname(l.drug_code)}`).join(', ')}</td>
                    <td>
                      <div className="timeline">
                        {STEPS.map((s, i) => (
                          <span key={s} style={{ display: 'contents' }}>
                            {i > 0 && <span className={`bar ${i <= idx ? 'done' : ''}`} />}
                            <span className={`st ${i < idx || tr.status === 'delivered' ? 'done' : i === idx ? 'cur' : ''}`}><span className="d" />{t(`transfer.${s}`)}</span>
                          </span>
                        ))}
                      </div>
                      {tr.eta_at && <div className="muted small">{t('redis.etaAt', { at: tr.eta_at.replace('T', ' ') })}</div>}
                    </td>
                    <td className="small">{tr.approved_by}<div className="muted">{tr.created_at.replace('T', ' ')}</div></td>
                    <td>
                      {tr.status === 'approved' && <button className="btn sm orange" disabled={busy === `t${tr.id}`} onClick={() => advance(tr, 'in_transit')}>{t('redis.dispatch')}</button>}
                      {tr.status === 'in_transit' && <button className="btn sm primary" disabled={busy === `t${tr.id}`} onClick={() => advance(tr, 'delivered')}>{t('redis.markDelivered')}</button>}
                      {tr.status === 'approved' && canApprove && <button className="btn sm ghost" onClick={() => advance(tr, 'cancelled')}>{t('redis.cancel')}</button>}
                      {tr.status === 'delivered' && <span className="pill delivered"><Icon name="check" size={12} />{t('redis.resolved')}</span>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </Card>

      <Card title={t('redis.escalations')} icon="alert" hint={t('redis.escalationsHint')} bodyClass="table-wrap">
        <table className="t">
          <thead><tr><th>{t('th.phc')}</th><th>{t('th.drug')}</th><th className="r">{t('th.shortfall')}</th><th className="r">{t('th.neededIn')}</th></tr></thead>
          <tbody>
            {data.escalations.slice(0, 40).map((e) => (
              <tr key={e.phc.id + e.drug_code}>
                <td><Link to={`/phc/${e.phc.id}`}><b>{e.phc.code}</b></Link> {e.phc.name}</td>
                <td>{dname(e.drug_code)}</td>
                <td className="r num">{fmt(e.qty)} {unitLabel(t, drug[e.drug_code].unit)}</td>
                <td className="r num">{e.needed_in_days <= 0 ? <span className="pill stocked_out">{t('days.now')}</span> : t('days.many', { n: e.needed_in_days })}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!data.escalations.length && <div className="empty">{t('redis.noEscalations')}</div>}
      </Card>
    </>
  )
}
