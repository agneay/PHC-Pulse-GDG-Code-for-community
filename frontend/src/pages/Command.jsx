import { Link, useNavigate } from 'react-router-dom'
import { useApp } from '../App'
import Briefing from '../components/Briefing'
import Icon from '../components/Icon'
import MapView from '../components/MapView'
import { Card, ErrorBox, Kpi, Loading, useAsync } from '../components/ui'
import { api } from '../lib/api'
import { fmt, HEALTH_COLOR, pct, SYNDROME_LABEL } from '../lib/format'

export default function Command() {
  const { scopeQs, version, meta } = useApp()
  const { data, error, loading } = useAsync(() => api.get(`/api/overview${scopeQs}`), [scopeQs, version])
  const nav = useNavigate()
  if (error) return <ErrorBox error={error} />
  if (loading && !data) return <Loading />
  const k = data.kpis
  const dname = Object.fromEntries(meta.districts.map((d) => [d.code, d.name]))

  return (
    <>
      <div className="page-h">
        <div>
          <div className="eyebrow">Live resilience status</div>
          <h1>{data.scope_label}</h1>
          <p>Every PHC's stock, beds, staff and footfall, with stock-outs forecast before they happen and the transfers that prevent them.</p>
        </div>
        <div className="right">
          <Link className="btn" to="/report"><Icon name="mic" size={15} />File a voice report</Link>
          <Link className="btn primary" to="/redistribution"><Icon name="truck" size={15} />Review {k.recommended_transfers} transfers</Link>
        </div>
      </div>

      <div className="grid g-kpi">
        <Kpi icon="pulse" label="PHCs reporting today" value={`${k.phcs_reporting_today}/${k.phcs}`} sub={`${pct(k.phcs_reporting_today / k.phcs)} compliance${k.stale_phcs ? ` · ${k.stale_phcs} silent 3+ days` : ''}`} />
        <Kpi icon="alert" tone="alert" label="Predicted stock-outs" value={k.predicted_stockouts} sub={`before next supply · ${k.critical_items} within 7 days`} />
        <Kpi icon="pill" tone="warn" label="Stocked out now" value={k.stocked_out_items} sub="drug lines at zero" />
        <Kpi icon="bug" tone={k.outbreak_clusters ? 'alert' : ''} label="Outbreak clusters" value={k.outbreak_clusters} sub={`${k.anomalies} PHC-level footfall anomalies`} />
        <Kpi icon="truck" label="Transfers recommended" value={k.recommended_transfers} sub={`${k.surplus_items} surplus lines available`} />
        <Kpi icon="bed" label="Bed occupancy" value={pct(k.bed_occupancy)} sub={`Staff attendance ${pct(k.staff_attendance)}`} />
      </div>

      <div className="grid g-2">
        <Card title="PHC network" icon="map" hint="Click a PHC for its forecast"
          right={<div className="legend">
            {Object.entries(HEALTH_COLOR).map(([h, c]) => <span key={h}><span className="dot" style={{ background: c }} />{h} ({k.health[h]})</span>)}
            <span><span className="dot" style={{ border: '2px dashed #c62828' }} />outbreak cluster</span>
          </div>} bodyClass="">
          <MapView phcs={data.phcs} clusters={data.clusters} />
        </Card>
        <div className="stack" style={{ gap: 18 }}>
          <Briefing />
          <Card title="Outbreak signals" icon="bug" right={<Link to="/outbreaks" className="small">All signals →</Link>}>
            {!data.clusters.length && !data.anomalies.length && <div className="muted small">No unusual footfall today.</div>}
            <div className="stack">
              {data.clusters.map((c) => (
                <div key={c.id} className="rec" style={{ borderColor: '#f3c2c2' }}>
                  <div className="lane"><span className={`pill ${c.severity}-sev`}>{c.severity} · cluster</span>
                    {SYNDROME_LABEL[c.syndrome]} in {dname[c.district_code]}</div>
                  <div className="small muted">{c.phc_codes.join(', ')} · up to {c.max_ratio}× expected · ~{fmt(c.excess_cases)} excess cases</div>
                </div>
              ))}
              {data.anomalies.filter((a) => !a.in_cluster).slice(0, 3).map((a) => (
                <div key={a.phc_id + a.syndrome} className="row small">
                  <span className="pill amber">{SYNDROME_LABEL[a.syndrome]}</span>
                  <Link to={`/phc/${a.phc_id}`}>{a.phc_code} {a.phc_name}</Link>
                  <span className="muted">{a.observed} vs {a.expected} expected</span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>

      <div className="grid g-2">
        <Card title="Districts" icon="grid" hint="Resilience score = stock risk + outbreak + beds + staff + reporting" bodyClass="table-wrap">
          <table className="t">
            <thead><tr><th>District</th><th className="r">PHCs</th><th className="r">Reported</th><th className="r">Score</th><th className="r">Red PHCs</th><th className="r">Critical lines</th><th className="r">Anomalies</th></tr></thead>
            <tbody>
              {data.districts.sort((a, b) => a.score - b.score).map((d) => (
                <tr key={d.code}>
                  <td><b>{d.name}</b> <span className="muted small">{d.state_code}</span></td>
                  <td className="r num">{d.phcs}</td>
                  <td className="r num">{d.reported}/{d.phcs}</td>
                  <td className="r num"><b style={{ color: d.score < 60 ? 'var(--red)' : d.score < 80 ? 'var(--amber)' : 'var(--green)' }}>{d.score}</b></td>
                  <td className="r num">{d.red}</td>
                  <td className="r num">{d.critical_items}</td>
                  <td className="r num">{d.anomalies}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card title="Top redistribution moves" icon="truck" right={<Link to="/redistribution" className="small">Open planner →</Link>}>
          <div className="stack">
            {data.shipments.map((s) => (
              <div key={s.id} className="rec" onClick={() => nav('/redistribution')} style={{ cursor: 'pointer' }}>
                <div className="lane">{s.from.code} <Icon name="arrow" size={14} /> {s.to.code}
                  <span className="pill critical" style={{ marginLeft: 'auto' }}>{s.urgency_days <= 0 ? "stocked out" : `needed in ${s.urgency_days}d`}</span></div>
                <div className="small muted">{s.lines.map((l) => `${fmt(l.qty)} ${l.drug_code}`).join(' + ')} · {fmt(s.distance_km)} km</div>
              </div>
            ))}
            {!data.shipments.length && <div className="muted small">No transfers needed.</div>}
          </div>
        </Card>
      </div>

      <Card title="Weakest PHCs today" icon="alert" bodyClass="table-wrap">
        <table className="t">
          <thead><tr><th>PHC</th><th>District</th><th className="r">Score</th><th className="r">Critical</th><th className="r">High</th><th className="r">Beds</th><th className="r">Staff</th><th>Report</th></tr></thead>
          <tbody>
            {[...data.phcs].sort((a, b) => a.score - b.score).slice(0, 10).map((p) => (
              <tr key={p.id} className="click" onClick={() => nav(`/phc/${p.id}`)}>
                <td><b>{p.code}</b> {p.name}</td>
                <td>{dname[p.district_code]}</td>
                <td className="r"><span className={`pill ${p.health}`}>{p.score}</span></td>
                <td className="r num">{p.critical_items}</td>
                <td className="r num">{p.high_items}</td>
                <td className="r num">{p.beds_occupied ?? '–'}/{p.beds_total}</td>
                <td className="r num">{p.staff_present ?? '–'}/{p.staff_sanctioned}</td>
                <td><ReportAge p={p} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <div className="muted small">Engine recomputed {data.computed_at} in {data.compute_ms} ms · forecasts {fmt(data.phcs.length * 10)} PHC×drug series</div>
    </>
  )
}

// Reporting freshness: silent PHCs are shown as unverified, not trusted as current.
export function ReportAge({ p }) {
  if (p.reported_today) return <span className="pill ok">today</span>
  if (p.stale) return <span className="pill red" title="No report for 3+ days: numbers unverified, excluded from outbreak detection and transfers">silent {p.days_since_report}d</span>
  return <span className="pill grey">due</span>
}
