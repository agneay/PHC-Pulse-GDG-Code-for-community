import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useApp } from '../App'
import Icon from '../components/Icon'
import MapView from '../components/MapView'
import { Card, ErrorBox, Kpi, Loading, useAsync } from '../components/ui'
import { api } from '../lib/api'
import { fmt, inr, TRANSFER_LABEL } from '../lib/format'

const STEPS = ['approved', 'in_transit', 'delivered']

export default function Redistribution() {
  const { scopeQs, version, refresh, notify, meta } = useApp()
  const [cross, setCross] = useState(false)
  const [sel, setSel] = useState(null)
  const [busy, setBusy] = useState(null)
  const sep = scopeQs ? '&' : '?'
  const { data, error, loading } = useAsync(
    () => api.get(`/api/redistribution${scopeQs}${sep}cross_state=${cross}`), [scopeQs, version, cross])
  const drug = Object.fromEntries(meta.drugs.map((d) => [d.code, d]))
  const canApprove = meta.user.role !== 'phc'

  if (error) return <ErrorBox error={error} />
  if (loading && !data) return <Loading label="Solving the redistribution MILP…" />

  const approve = async (s) => {
    const items = s.lines.map((l) => `${fmt(l.qty)} ${drug[l.drug_code].unit} ${drug[l.drug_code].name}`).join(', ')
    if (!window.confirm(`Approve transfer ${s.from.code} → ${s.to.code}?

${items}
${fmt(s.distance_km)} km · ${inr(s.cost_inr)}

This reserves the stock at ${s.from.code}.`)) return
    setBusy(s.id)
    try {
      await api.post(`/api/redistribution/${s.id}/approve?cross_state=${cross}`)
      notify(`Transfer ${s.from.code} → ${s.to.code} approved`)
      refresh()
    } catch (e) { notify(e.message) } finally { setBusy(null) }
  }
  const advance = async (t, status) => {
    setBusy(`t${t.id}`)
    try {
      await api.post(`/api/transfers/${t.id}/status`, { status })
      notify(`${t.from_code} → ${t.to_code}: ${TRANSFER_LABEL[status]}`)
      refresh()
    } catch (e) { notify(e.message) } finally { setBusy(null) }
  }

  const st = data.stats
  const active = data.transfers.filter((t) => t.status !== 'cancelled')
  const lanes = [
    ...data.shipments,
    ...active.filter((t) => t.status !== 'delivered').map((t) => ({
      id: `t${t.id}`, status: t.status, lines: t.lines,
      from: { code: t.from_code, lat: t.from_lat, lon: t.from_lon }, to: { code: t.to_code, lat: t.to_lat, lon: t.to_lon } })),
  ]
  const endpoints = {}
  data.shipments.forEach((s) => { endpoints[s.from.id] = s.from; endpoints[s.to.id] = s.to })
  const mapPhcs = Object.values(endpoints).map((p) => ({ ...p, health: 'amber', score: '–', critical_items: '–' }))

  return (
    <>
      <div className="page-h">
        <div>
          <div className="eyebrow">Prescriptive optimisation</div>
          <h1>Redistribution planner</h1>
          <p>A mixed-integer program chooses which PHC ships what, to whom, under transport-cost constraints. It weighs trip cost against how soon each shortage hits and how critical the drug is, and puts several medicines on one vehicle when the lane is shared.</p>
        </div>
        <div className="right">
          <label className="btn" title="Phase 3: allow transfers across state boundaries">
            <input type="checkbox" checked={cross} onChange={(e) => setCross(e.target.checked)} /> Cross-state transfers
          </label>
        </div>
      </div>

      {st.failed && <div className="err" role="alert"><b>The optimiser could not produce a plan</b> ({st.solver}). Shortages below are real, but no transfers were computed: this is not "nothing to move". Raise emergency indents or retry.</div>}
      {!st.failed && st.time_limited && <div className="note">The optimiser hit its time limit, so this plan is feasible but may not be the cheapest.</div>}

      <div className="grid g-kpi">
        <Kpi icon="truck" label="Recommended shipments" value={data.shipments.length} sub={`${st.lanes ?? 0} candidate lanes evaluated`} />
        <Kpi icon="pill" label="Units rebalanced" value={fmt(st.units_moved)} sub={`${st.coverage != null ? Math.round(st.coverage * 100) : 0}% of forecast shortfall covered from surplus`} tone="good" />
        <Kpi icon="map" label="Plan transport cost" value={inr(st.cost)} sub="fixed + ₹/km + inter-state paperwork" />
        <Kpi icon="alert" label="Escalate to warehouse" value={data.escalations.length} sub="shortfalls no nearby surplus can cover" tone="warn" />
      </div>

      <div className="grid g-2">
        <Card title="Recommended transfers" icon="truck" hint="sorted by urgency"
          bodyClass="card-b" right={<span className="muted small">{st.solver}</span>}>
          <div className="stack" style={{ maxHeight: 620, overflowY: 'auto', paddingRight: 4 }}>
            {data.shipments.map((s) => (
              <div key={s.id} className={`rec ${sel === s.id ? 'sel' : ''}`} onMouseEnter={() => setSel(s.id)}>
                <div className="lane">
                  <Link to={`/phc/${s.from.id}`}>{s.from.code}</Link><span className="muted small">{s.from.name.replace('PHC ', '')}</span>
                  <Icon name="arrow" size={15} />
                  <Link to={`/phc/${s.to.id}`}>{s.to.code}</Link><span className="muted small">{s.to.name.replace('PHC ', '')}</span>
                  <span className={`pill ${s.urgency_days <= 7 ? 'critical' : 'high'}`} style={{ marginLeft: 'auto' }}>{s.urgency_days <= 0 ? "stocked out" : `needed in ${s.urgency_days} days`}</span>
                </div>
                {s.lines.map((l) => (
                  <div key={l.drug_code} className="msg">
                    “{s.from.code} has surplus {drug[l.drug_code].name.toLowerCase()}; {s.to.code} {l.needed_in_days <= 0
                      ? 'has already run out'
                      : `needs it in ${l.needed_in_days} day${l.needed_in_days === 1 ? '' : 's'}`}.”
                    <b> Ship {fmt(l.qty)} {drug[l.drug_code].unit}.</b>
                  </div>
                ))}
                <div className="meta">
                  <span>{fmt(s.distance_km)} km by road</span><span>ETA {s.eta_hours} h</span><span>{inr(s.cost_inr)}</span>
                  {s.cross_state ? <span className="pill surplus">inter-state</span> : s.cross_district ? <span className="pill grey">cross-district</span> : <span className="pill grey">same district</span>}
                  {s.lines.length > 1 && <span className="pill ok">consolidated · {s.lines.length} drugs</span>}
                </div>
                {canApprove && (
                  <div className="row">
                    <button className="btn primary sm" onClick={() => approve(s)} disabled={busy === s.id}>
                      {busy === s.id ? <span className="spinner" /> : <Icon name="check" size={14} />}Approve transfer
                    </button>
                  </div>
                )}
              </div>
            ))}
            {!data.shipments.length && !st.failed && <div className="empty">No transfers needed in this scope. Surplus and shortages are balanced.</div>}
          </div>
        </Card>
        <Card title="Lanes" icon="map" hint="orange = recommended · blue = approved / in transit" bodyClass="">
          <MapView phcs={mapPhcs} lanes={lanes} selectedLane={sel} onLaneClick={setSel} tall />
        </Card>
      </div>

      <Card title="Transfer tracker" icon="refresh" hint="one-tap approval → dispatch → delivery updates both PHCs' stock" bodyClass="table-wrap">
        {!active.length ? <div className="empty">No transfers yet. Approve a recommendation above.</div> : (
          <table className="t">
            <thead><tr><th>Lane</th><th>Items</th><th>Progress</th><th>Approved by</th><th /></tr></thead>
            <tbody>
              {active.map((t) => {
                const idx = STEPS.indexOf(t.status)
                return (
                  <tr key={t.id}>
                    <td><b>{t.from_code}</b> → <b>{t.to_code}</b><div className="muted small">{fmt(t.distance_km)} km · {inr(t.cost_inr)}</div></td>
                    <td className="small">{t.lines.map((l) => `${fmt(l.qty)} ${l.unit} ${l.drug_name}`).join(', ')}</td>
                    <td>
                      <div className="timeline">
                        {STEPS.map((s, i) => (
                          <span key={s} style={{ display: 'contents' }}>
                            {i > 0 && <span className={`bar ${i <= idx ? 'done' : ''}`} />}
                            <span className={`st ${i < idx || t.status === 'delivered' ? 'done' : i === idx ? 'cur' : ''}`}><span className="d" />{TRANSFER_LABEL[s]}</span>
                          </span>
                        ))}
                      </div>
                      {t.eta_at && <div className="muted small">ETA {t.eta_at.replace('T', ' ')}</div>}
                    </td>
                    <td className="small">{t.approved_by}<div className="muted">{t.created_at.replace('T', ' ')}</div></td>
                    <td>
                      {t.status === 'approved' && <button className="btn sm orange" disabled={busy === `t${t.id}`} onClick={() => advance(t, 'in_transit')}>Dispatch</button>}
                      {t.status === 'in_transit' && <button className="btn sm primary" disabled={busy === `t${t.id}`} onClick={() => advance(t, 'delivered')}>Mark delivered</button>}
                      {t.status === 'approved' && canApprove && <button className="btn sm ghost" onClick={() => advance(t, 'cancelled')}>Cancel</button>}
                      {t.status === 'delivered' && <span className="pill delivered"><Icon name="check" size={12} />Resolved</span>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </Card>

      <Card title="Escalations to district warehouse" icon="alert" hint="shortfalls with no economical donor: raise an emergency indent" bodyClass="table-wrap">
        <table className="t">
          <thead><tr><th>PHC</th><th>Drug</th><th className="r">Shortfall</th><th className="r">Needed in</th></tr></thead>
          <tbody>
            {data.escalations.slice(0, 40).map((e) => (
              <tr key={e.phc.id + e.drug_code}>
                <td><Link to={`/phc/${e.phc.id}`}><b>{e.phc.code}</b></Link> {e.phc.name}</td>
                <td>{drug[e.drug_code].name}</td>
                <td className="r num">{fmt(e.qty)} {drug[e.drug_code].unit}</td>
                <td className="r num">{e.needed_in_days <= 0 ? <span className="pill stocked_out">now</span> : `${e.needed_in_days} days`}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!data.escalations.length && <div className="empty">Nothing to escalate.</div>}
      </Card>
    </>
  )
}
