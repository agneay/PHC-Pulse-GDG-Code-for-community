import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useApp } from '../App'
import { Card, ErrorBox, Loading, StatusPill, useAsync } from '../components/ui'
import { api } from '../lib/api'
import { daysText, fmt, STATUS_LABEL } from '../lib/format'

const ORDER = { stocked_out: 0, critical: 1, high: 2, watch: 3, ok: 4, surplus: 5 }

export default function Stock() {
  const { scopeQs, version, meta } = useApp()
  const { data, error, loading } = useAsync(() => api.get(`/api/stock${scopeQs}`), [scopeQs, version])
  const [drug, setDrug] = useState('')
  const [onlyRisk, setOnlyRisk] = useState(true)
  const nav = useNavigate()
  const dname = Object.fromEntries(meta.districts.map((d) => [d.code, d.name]))

  const matrix = useMemo(() => {
    if (!data) return []
    const by = {}
    data.items.forEach((i) => { (by[i.phc_id] ||= {})[i.drug_code] = i })
    let phcs = data.phcs.map((p) => ({ ...p, cells: by[p.id] || {} }))
    if (onlyRisk) phcs = phcs.filter((p) => Object.values(p.cells).some((c) => ORDER[c.status] <= 3))
    return phcs.sort((a, b) => a.score - b.score)
  }, [data, onlyRisk])

  if (error) return <ErrorBox error={error} />
  if (loading && !data) return <Loading />
  const warnings = data.items.filter((i) => ORDER[i.status] <= 3 && (!drug || i.drug_code === drug))
    .sort((a, b) => ORDER[a.status] - ORDER[b.status] || (a.days_to_stockout ?? 99) - (b.days_to_stockout ?? 99))
  const counts = Object.fromEntries(Object.keys(ORDER).map((s) => [s, data.items.filter((i) => i.status === s).length]))

  return (
    <>
      <div className="page-h">
        <div>
          <div className="eyebrow">Demand forecasting · early warning</div>
          <h1>Stock early warning</h1>
          <p>Per-PHC, per-drug demand forecasts. A line is flagged when projected stock hits zero <b>before the next scheduled supply</b>. Forecasts are outbreak-aware: if footfall spikes, the linked drugs are forecast higher.</p>
        </div>
      </div>
      <div className="row">
        {Object.keys(ORDER).map((s) => <span key={s} className={`pill ${s}`}>{STATUS_LABEL[s]}: {counts[s]}</span>)}
      </div>

      <Card title="PHC × drug risk matrix" hint="cell = days of cover · click to open PHC"
        right={<label className="row small"><input type="checkbox" checked={onlyRisk} onChange={(e) => setOnlyRisk(e.target.checked)} /> only PHCs at risk</label>}
        bodyClass="card-b table-wrap">
        <table className="heat">
          <thead><tr><th style={{ textAlign: 'left' }}>PHC</th>{data.drugs.map((d) => <th key={d.code} title={d.name}>{d.code}</th>)}</tr></thead>
          <tbody>
            {matrix.map((p) => (
              <tr key={p.id}>
                <td className="name"><Link to={`/phc/${p.id}`}><b>{p.code}</b></Link> <span className="muted">{p.name.replace('PHC ', '')} · {dname[p.district_code]}</span></td>
                {data.drugs.map((d) => {
                  const c = p.cells[d.code]
                  if (!c) return <td key={d.code} />
                  return (
                    <td key={d.code} className={`c ${c.status}`} onClick={() => nav(`/phc/${p.id}?drug=${d.code}`)}
                      title={`${d.name}: ${fmt(c.stock)} ${d.unit}, ${fmt(c.daily_forecast, 1)}/day forecast, ${STATUS_LABEL[c.status]}`}>
                      {c.status === 'stocked_out' ? '0' : c.cover_days >= 99 ? '99+' : Math.round(c.cover_days)}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
        {!matrix.length && <div className="empty">No PHCs at risk in this scope.</div>}
      </Card>

      <Card title="Early warnings" icon="alert" hint={`${warnings.length} lines`}
        right={<select className="select" value={drug} onChange={(e) => setDrug(e.target.value)} aria-label="Filter drug">
          <option value="">All drugs</option>
          {data.drugs.map((d) => <option key={d.code} value={d.code}>{d.name}</option>)}
        </select>} bodyClass="table-wrap">
        <table className="t">
          <thead><tr><th>Status</th><th>PHC</th><th>Drug</th><th className="r">Stock</th><th className="r">Forecast/day</th><th className="r">Runs out in</th><th className="r">Next supply</th><th className="r">P(stock-out)</th><th>Signal</th></tr></thead>
          <tbody>
            {warnings.slice(0, 150).map((i) => (
              <tr key={`${i.phc_id}-${i.drug_code}`} className="click" onClick={() => nav(`/phc/${i.phc_id}?drug=${i.drug_code}`)}>
                <td><StatusPill status={i.status} /></td>
                <td><b>{i.phc_code}</b> <span className="muted">{i.phc_name}</span></td>
                <td>{i.drug_name}</td>
                <td className="r num">{fmt(i.stock)} <span className="muted small">{i.unit}</span></td>
                <td className="r num">{fmt(i.daily_forecast, 1)}</td>
                <td className="r num"><b>{daysText(i.days_to_stockout)}</b></td>
                <td className="r num">{i.next_supply_in}d</td>
                <td className="r num">{Math.round(i.p_stockout * 100)}%</td>
                <td>{i.surge_reason && <span className="pill red" title="Outbreak-adjusted forecast">↑ {i.surge_reason}</span>}
                  {i.incoming > 0 && <span className="pill in_transit">+{fmt(i.incoming)} incoming</span>}
                  {i.stale && <span className="pill grey" title="PHC has not reported for 3+ days: verify before acting">unverified</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!warnings.length && <div className="empty">No early warnings.</div>}
      </Card>
    </>
  )
}
