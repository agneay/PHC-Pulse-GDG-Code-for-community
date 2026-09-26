import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { Area, CartesianGrid, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useApp } from '../App'
import Icon from '../components/Icon'
import { Card, ErrorBox, Kpi, Loading, StatusPill, useAsync } from '../components/ui'
import { api } from '../lib/api'
import { daysText, fmt, pct, shortDay, SYNDROME_LABEL } from '../lib/format'

export default function PhcDetail() {
  const { id } = useParams()
  const [sp, setSp] = useSearchParams()
  const { version, meta } = useApp()
  const { data, error, loading } = useAsync(() => api.get(`/api/phcs/${id}`), [id, version])
  const [syn, setSyn] = useState('opd')

  if (error) return <ErrorBox error={error} />
  if (loading && !data) return <Loading />
  const p = data.phc
  const drugCode = sp.get('drug') || [...data.drugs].sort((a, b) =>
    ['stocked_out', 'critical', 'high', 'watch', 'ok', 'surplus'].indexOf(a.status) -
    ['stocked_out', 'critical', 'high', 'watch', 'ok', 'surplus'].indexOf(b.status))[0].code
  const d = data.drugs.find((x) => x.code === drugCode)
  const series = [
    ...d.history.map((h) => ({ day: h.day, demand: h.demand, stock: h.stock })),
    ...d.forecast.map((f) => ({ day: f.day, forecast: f.forecast, band: [f.lo, f.hi], projected: f.projected_stock })),
  ]
  const supplyDay = new Date(meta.today); supplyDay.setDate(supplyDay.getDate() + d.next_supply_in)
  const supplyIso = supplyDay.toISOString().slice(0, 10)
  const lang = meta.languages[p.language]

  return (
    <>
      <div className="page-h">
        <div>
          <div className="eyebrow">{data.district_name} · {data.state_name} · NIN {p.nin}</div>
          <h1>{p.code} · {p.name}</h1>
          <p>{p.is_24x7 ? '24×7 PHC' : 'Day PHC'} · {p.beds_total} beds · {p.staff_sanctioned} sanctioned staff · reporting language {lang.native} · last report {p.last_report}</p>
        </div>
        <div className="right">
          {p.stale && <span className="pill red" style={{ fontSize: 14, padding: '4px 12px' }} title="Numbers below are from the last report and may be out of date. This PHC is excluded from outbreak detection and transfers until it reports.">No report for {p.days_since_report} days</span>}
          <span className={`pill ${p.health}`} style={{ fontSize: 14, padding: '4px 12px' }}>Resilience {p.score}/100</span>
          <Link className="btn" to={`/report?phc=${p.id}`}><Icon name="mic" size={15} />Report for this PHC</Link>
        </div>
      </div>
      <div className="grid g-kpi">
        <Kpi icon="alert" tone={p.critical_items ? 'alert' : ''} label="Critical / stocked-out lines" value={p.critical_items} sub={`${p.high_items} high · ${p.watch_items} watch`} />
        <Kpi icon="bed" label="Beds occupied" value={`${p.beds_occupied ?? '–'}/${p.beds_total}`} sub={pct(p.bed_occupancy)} />
        <Kpi icon="users" label="Staff present" value={`${p.staff_present ?? '–'}/${p.staff_sanctioned}`} sub={pct(p.attendance)} />
        <Kpi icon="pulse" label="OPD (last report)" value={fmt(p.opd_last)} sub={p.reported_today ? 'reported today' : 'today\'s report due'} />
        <Kpi icon="truck" label="Next scheduled supply" value={`${p.next_supply_in} day${p.next_supply_in === 1 ? '' : 's'}`} sub="monthly indent" />
      </div>

      <div className="grid g-2">
        <Card title={`${d.name}: forecast & stock projection`} icon="pill"
          right={<select className="select" value={drugCode} onChange={(e) => setSp({ drug: e.target.value })} aria-label="Drug">
            {data.drugs.map((x) => <option key={x.code} value={x.code}>{x.name} · {x.status}</option>)}
          </select>}>
          <div className="row small" style={{ marginBottom: 8 }}>
            <StatusPill status={d.status} />
            <span>Stock <b>{fmt(d.stock)}</b> {d.unit}</span>
            <span>· forecast <b>{fmt(d.daily_forecast, 1)}</b>/day</span>
            <span>· runs out in <b>{daysText(d.days_to_stockout)}</b></span>
            <span>· P(stock-out before supply) <b>{Math.round(d.p_stockout * 100)}%</b></span>
            {d.surge_reason && <span className="pill red">outbreak-adjusted ×{d.surge}</span>}
          </div>
          <ResponsiveContainer width="100%" height={300}>
            <ComposedChart data={series} margin={{ left: -10, right: 10 }}>
              <CartesianGrid stroke="#f3e6e6" vertical={false} />
              <XAxis dataKey="day" tickFormatter={shortDay} minTickGap={28} fontSize={11} />
              <YAxis yAxisId="d" fontSize={11} />
              <YAxis yAxisId="s" orientation="right" fontSize={11} />
              <Tooltip labelFormatter={shortDay} formatter={(v, n) => [Array.isArray(v) ? `${v[0]}–${v[1]}` : fmt(v, 1), n]} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Area isAnimationActive={false} yAxisId="s" dataKey="stock" name="Stock on hand" fill="#cfe2fb" stroke="#1565c0" strokeWidth={1.5} fillOpacity={0.5} />
              <Area isAnimationActive={false} yAxisId="s" dataKey="projected" name="Projected stock" fill="#ffe0c2" stroke="#ef6c00" strokeDasharray="5 4" fillOpacity={0.5} />
              <Area isAnimationActive={false} yAxisId="d" dataKey="band" name="80% interval" fill="#f5c9c9" stroke="none" fillOpacity={0.5} />
              <Line isAnimationActive={false} yAxisId="d" dataKey="demand" name="Daily demand" stroke="#7a1f1f" dot={false} strokeWidth={1.4} />
              <Line isAnimationActive={false} yAxisId="d" dataKey="forecast" name="Forecast" stroke="#c62828" dot={false} strokeWidth={2} />
              <ReferenceLine yAxisId="d" x={meta.today} stroke="#5c1515" label={{ value: 'today', fontSize: 11, fill: '#5c1515' }} />
              {d.next_supply_in <= 28 && <ReferenceLine yAxisId="d" x={supplyIso} stroke="#2e7d32" strokeDasharray="4 4" label={{ value: 'next supply', fontSize: 11, fill: '#2e7d32' }} />}
            </ComposedChart>
          </ResponsiveContainer>
        </Card>
        <Card title="All drug lines" icon="pill" bodyClass="table-wrap">
          <table className="t">
            <thead><tr><th>Drug</th><th className="r">Stock</th><th className="r">Cover</th><th>Status</th></tr></thead>
            <tbody>
              {data.drugs.map((x) => (
                <tr key={x.code} className="click" onClick={() => setSp({ drug: x.code })} style={x.code === drugCode ? { background: 'var(--blush-50)' } : null}>
                  <td>{x.name}</td>
                  <td className="r num">{fmt(x.stock)}</td>
                  <td className="r num">{x.cover_days >= 999 ? '–' : `${fmt(x.cover_days)}d`}</td>
                  <td><StatusPill status={x.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>

      <div className="grid g-2">
        <Card title="Footfall vs expected" icon="pulse" hint="alert threshold = baseline + 3 robust SD"
          right={<div className="lang-tabs">{['opd', 'fever', 'diarrhoea', 'respiratory'].map((s) => (
            <button key={s} className={syn === s ? 'on' : ''} onClick={() => setSyn(s)}>{SYNDROME_LABEL[s]}</button>))}</div>}>
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart data={data.footfall} margin={{ left: -10, right: 10 }}>
              <CartesianGrid stroke="#f3e6e6" vertical={false} />
              <XAxis dataKey="day" tickFormatter={shortDay} minTickGap={28} fontSize={11} />
              <YAxis fontSize={11} />
              <Tooltip labelFormatter={shortDay} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line isAnimationActive={false} dataKey={`${syn}_threshold`} name="Alert threshold" stroke="#ef6c00" strokeDasharray="5 4" dot={false} />
              <Line isAnimationActive={false} dataKey={`${syn}_expected`} name="Expected" stroke="#9e8a8a" dot={false} />
              <Line isAnimationActive={false} dataKey={syn} name="Observed" stroke="#c62828" strokeWidth={2} dot={{ r: 1.5 }} />
            </ComposedChart>
          </ResponsiveContainer>
          {data.anomalies.length > 0 && (
            <div className="row small">{data.anomalies.map((a) => (
              <span key={a.syndrome} className={`pill ${a.in_cluster ? 'red' : 'amber'}`}>{SYNDROME_LABEL[a.syndrome]} {a.ratio}× expected{a.in_cluster ? ' · cluster' : ''}</span>))}</div>
          )}
        </Card>
        <Card title="Transfers & recent reports" icon="truck">
          <div className="stack">
            {data.recommendations.map((s) => (
              <div key={s.id} className="rec">
                <div className="lane">{s.from.code} <Icon name="arrow" size={14} /> {s.to.code}<span className="pill approved" style={{ marginLeft: 'auto' }}>recommended</span></div>
                <div className="small muted">{s.lines.map((l) => `${fmt(l.qty)} ${l.drug_code}`).join(' + ')} · needed in {s.urgency_days}d · <Link to="/redistribution">review</Link></div>
              </div>
            ))}
            {data.transfers.map((t) => (
              <div key={t.id} className="row small"><span className={`pill ${t.status}`}>{t.status.replace('_', ' ')}</span>{t.from_code} → {t.to_code}: {t.lines.map((l) => `${fmt(l.qty)} ${l.drug_code}`).join(', ')}</div>
            ))}
            <div className="sep" />
            {data.reports.length === 0 && <div className="muted small">No voice/USSD/SMS reports yet today. Earlier days came in via the HMIS backfill.</div>}
            {data.reports.map((r) => (
              <div key={r.id} className="small">
                <span className="pill grey">{r.channel}</span> <span className="muted">{r.created_at.replace('T', ' ')}</span>
                {r.transcript && <div style={{ marginTop: 3 }}>“{r.transcript}”</div>}
              </div>
            ))}
          </div>
        </Card>
      </div>
    </>
  )
}
