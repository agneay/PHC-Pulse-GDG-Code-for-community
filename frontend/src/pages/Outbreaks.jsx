import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useApp } from '../App'
import Icon from '../components/Icon'
import MapView from '../components/MapView'
import { Card, EngineTag, ErrorBox, Loading, useAsync } from '../components/ui'
import { api } from '../lib/api'
import { fmt, SYNDROME_LABEL } from '../lib/format'
import { speak } from '../lib/wav'

export default function Outbreaks() {
  const { scopeQs, version, meta, notify } = useApp()
  const { data, error, loading } = useAsync(() => api.get(`/api/alerts${scopeQs}`), [scopeQs, version])
  const ov = useAsync(() => api.get(`/api/overview${scopeQs}`), [scopeQs, version])
  const [drafts, setDrafts] = useState({})
  const [busy, setBusy] = useState(null)
  const dname = Object.fromEntries(meta.districts.map((d) => [d.code, d.name]))

  if (error) return <ErrorBox error={error} />
  if ((loading && !data) || !ov.data) return <Loading />

  const draft = async (c) => {
    setBusy(c.id)
    try {
      const r = await api.post(`/api/clusters/${c.id}/alert`, {})
      setDrafts((d) => ({ ...d, [c.id]: r }))
    } catch (e) { notify(e.message) } finally { setBusy(null) }
  }
  const atRisk = (c) => data.stock_warnings.filter((w) => c.phc_ids.includes(w.phc_id) && w.surge_reason)

  return (
    <>
      <div className="page-h">
        <div>
          <div className="eyebrow">Anomaly detection · early emergency signals</div>
          <h1>Outbreak signals</h1>
          <p>Daily footfall by syndrome is compared with each PHC's own weekday-adjusted baseline (robust z-score). When two or more PHCs within 50 km spike on the same syndrome, it is raised as a cluster: an early outbreak signal for the District Surveillance Unit.</p>
        </div>
      </div>

      <div className="grid g-2">
        <div className="stack" style={{ gap: 18 }}>
          {!data.clusters.length && <Card><div className="empty">No clusters detected in this scope.</div></Card>}
          {data.clusters.map((c) => {
            const d = drafts[c.id]
            const risk = atRisk(c)
            return (
              <Card key={c.id} icon="bug" title={`${SYNDROME_LABEL[c.syndrome]} cluster · ${(c.district_codes || [c.district_code]).map((d) => dname[d]).join(' / ')}`}
                right={<span className={`pill ${c.severity}-sev`}>{c.severity} severity</span>}>
                <div className="stack">
                  <div className="row small">
                    {c.phc_ids.map((id, i) => <Link key={id} className="pill red" to={`/phc/${id}`}>{c.phc_codes[i]}</Link>)}
                  </div>
                  <div className="small">Footfall up to <b>{c.max_ratio}×</b> expected for <b>{c.max_consecutive_days}</b> consecutive day(s), roughly <b>{fmt(c.excess_cases)}</b> excess cases.</div>
                  {risk.length > 0 && (
                    <div className="note">
                      <b>Stock impact:</b> forecasts for linked drugs were raised automatically. {risk.slice(0, 4).map((w) => `${w.phc_code} ${w.drug_code} runs out in ${w.days_to_stockout ?? 0}d`).join(' · ')}
                    </div>
                  )}
                  {!d && (
                    <div><button className="btn primary sm" onClick={() => draft(c)} disabled={busy === c.id}>
                      {busy === c.id ? <span className="spinner" /> : <Icon name="spark" size={14} />}Draft IDSP alert
                    </button></div>
                  )}
                  {d && (
                    <div className="ai-card" style={{ borderRadius: 12, padding: 12, border: '1px solid #e3def7' }}>
                      <div className="row"><b>{d.title}</b><span style={{ marginLeft: 'auto' }}><EngineTag engine={d.engine} /></span></div>
                      <p className="small" style={{ lineHeight: 1.55 }}>{d.english}</p>
                      {d.local_language && d.local_language !== d.english && (
                        <div className="row" style={{ alignItems: 'flex-start' }}>
                          <p className="small" style={{ lineHeight: 1.6, flex: 1, margin: 0 }}>{d.local_language}</p>
                          <button className="btn ghost sm" onClick={() => speak(d.local_language, meta.languages[d.language]?.bcp47 || 'en-IN')} title="Read aloud"><Icon name="speaker" size={15} /></button>
                        </div>
                      )}
                      <div className="eyebrow" style={{ marginTop: 8 }}>Recommended response</div>
                      <ul className="small">{d.recommended_response.map((s, i) => <li key={i}>{s}</li>)}</ul>
                    </div>
                  )}
                </div>
              </Card>
            )
          })}
        </div>
        <Card title="Signal map" icon="map" bodyClass="">
          <MapView phcs={ov.data.phcs.filter((p) => p.anomalies)} clusters={data.clusters} />
        </Card>
      </div>

      <Card title="PHC-level footfall anomalies" icon="alert" bodyClass="table-wrap">
        <table className="t">
          <thead><tr><th>PHC</th><th>District</th><th>Syndrome</th><th className="r">Observed</th><th className="r">Expected</th><th className="r">Ratio</th><th className="r">z</th><th className="r">Days</th><th>Type</th></tr></thead>
          <tbody>
            {data.anomalies.map((a) => (
              <tr key={a.phc_id + a.syndrome}>
                <td><Link to={`/phc/${a.phc_id}`}><b>{a.phc_code}</b></Link> {a.phc_name}</td>
                <td>{dname[a.district_code]}</td>
                <td>{SYNDROME_LABEL[a.syndrome]}</td>
                <td className="r num"><b>{a.observed}</b></td>
                <td className="r num">{a.expected}</td>
                <td className="r num">{a.ratio}×</td>
                <td className="r num">{a.z}</td>
                <td className="r num">{a.consecutive_days}</td>
                <td>{a.in_cluster ? <span className="pill red">cluster</span> : <span className="pill amber">isolated</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!data.anomalies.length && <div className="empty">No anomalies.</div>}
      </Card>
    </>
  )
}
