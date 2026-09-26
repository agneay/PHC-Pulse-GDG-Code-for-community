import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useApp } from '../App'
import Icon from '../components/Icon'
import MapView from '../components/MapView'
import { SpeakButton } from '../components/Speak'
import { Card, EngineTag, ErrorBox, Loading, useAsync } from '../components/ui'
import { useI18n } from '../i18n'
import { api } from '../lib/api'
import { fmt, rich } from '../lib/format'

export default function Outbreaks() {
  const { scopeQs, version, meta, notify } = useApp()
  const { t } = useI18n()
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
          <div className="eyebrow">{t('out.eyebrow')}</div>
          <h1>{t('out.title')}</h1>
          <p>{t('out.intro')}</p>
        </div>
      </div>

      <div className="grid g-2">
        <div className="stack" style={{ gap: 18 }}>
          {!data.clusters.length && <Card><div className="empty">{t('out.noClusters')}</div></Card>}
          {data.clusters.map((c) => {
            const d = drafts[c.id]
            const risk = atRisk(c)
            return (
              <Card key={c.id} icon="bug"
                title={t('out.clusterTitle', { syndrome: t(`syndrome.${c.syndrome}`), district: (c.district_codes || [c.district_code]).map((x) => dname[x]).join(' / ') })}
                right={<span className={`pill ${c.severity}-sev`}>{t('out.severity', { severity: t(`severity.${c.severity}`) })}</span>}>
                <div className="stack">
                  <div className="row small">
                    {c.phc_ids.map((id, i) => <Link key={id} className="pill red" to={`/phc/${id}`}>{c.phc_codes[i]}</Link>)}
                  </div>
                  <div className="small">{rich(t('out.clusterDetail', { ratio: c.max_ratio, days: c.max_consecutive_days, n: fmt(c.excess_cases) }))}</div>
                  {risk.length > 0 && (
                    <div className="note">
                      <b>{t('out.stockImpact')}</b> {t('out.stockImpactText')} {risk.slice(0, 4).map((w) => t('out.runsOut', { phc: w.phc_code, drug: w.drug_code, n: w.days_to_stockout ?? 0 })).join(' · ')}
                    </div>
                  )}
                  {!d && (
                    <div><button className="btn primary sm" onClick={() => draft(c)} disabled={busy === c.id}>
                      {busy === c.id ? <span className="spinner" /> : <Icon name="spark" size={14} />}{t('out.draft')}
                    </button></div>
                  )}
                  {d && (
                    <div className="ai-card" style={{ borderRadius: 12, padding: 12, border: '1px solid #e3def7' }}>
                      <div className="row"><b>{d.title}</b><span style={{ marginLeft: 'auto' }}><EngineTag engine={d.engine} /></span></div>
                      <p className="small" style={{ lineHeight: 1.55 }} lang="en">{d.english}</p>
                      {d.local_language && d.local_language !== d.english && (
                        <div className="row" style={{ alignItems: 'flex-start' }}>
                          <p className="small" style={{ lineHeight: 1.6, flex: 1, margin: 0 }} lang={d.language}>{d.local_language}</p>
                          <SpeakButton text={d.local_language} language={d.language} />
                        </div>
                      )}
                      <div className="eyebrow" style={{ marginTop: 8 }}>{t('out.response')}</div>
                      <ul className="small">{d.recommended_response.map((s, i) => <li key={i}>{s}</li>)}</ul>
                    </div>
                  )}
                </div>
              </Card>
            )
          })}
        </div>
        <Card title={t('out.map')} icon="map" bodyClass="">
          <MapView phcs={ov.data.phcs.filter((p) => p.anomalies)} clusters={data.clusters} />
        </Card>
      </div>

      <Card title={t('out.anomalies')} icon="alert" bodyClass="table-wrap">
        <table className="t">
          <thead><tr><th>{t('th.phc')}</th><th>{t('th.district')}</th><th>{t('th.syndrome')}</th><th className="r">{t('th.observed')}</th><th className="r">{t('th.expected')}</th><th className="r">{t('th.ratio')}</th><th className="r">z</th><th className="r">{t('th.days')}</th><th>{t('th.type')}</th></tr></thead>
          <tbody>
            {data.anomalies.map((a) => (
              <tr key={a.phc_id + a.syndrome}>
                <td><Link to={`/phc/${a.phc_id}`}><b>{a.phc_code}</b></Link> {a.phc_name}</td>
                <td>{dname[a.district_code]}</td>
                <td>{t(`syndrome.${a.syndrome}`)}</td>
                <td className="r num"><b>{a.observed}</b></td>
                <td className="r num">{a.expected}</td>
                <td className="r num">{a.ratio}×</td>
                <td className="r num">{a.z}</td>
                <td className="r num">{a.consecutive_days}</td>
                <td>{a.in_cluster ? <span className="pill red">{t('out.cluster')}</span> : <span className="pill amber">{t('out.isolated')}</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!data.anomalies.length && <div className="empty">{t('out.noAnomalies')}</div>}
      </Card>
    </>
  )
}
