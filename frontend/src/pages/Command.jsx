import { Link, useNavigate } from 'react-router-dom'
import { useApp } from '../App'
import Briefing from '../components/Briefing'
import Icon from '../components/Icon'
import MapView from '../components/MapView'
import { Card, ErrorBox, Kpi, Loading, useAsync } from '../components/ui'
import { useI18n } from '../i18n'
import { api } from '../lib/api'
import { fmt, HEALTH_COLOR, pct } from '../lib/format'
import { scopeLabel } from '../lib/labels'

export default function Command() {
  const { scopeQs, version, meta } = useApp()
  const { t } = useI18n()
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
          <div className="eyebrow">{t('cmd.eyebrow')}</div>
          <h1>{scopeLabel(data.scope, t, meta, data.scope_label)}</h1>
          <p>{t('cmd.intro')}</p>
        </div>
        <div className="right">
          <Link className="btn" to="/report"><Icon name="mic" size={15} />{t('cmd.fileReport')}</Link>
          <Link className="btn primary" to="/redistribution"><Icon name="truck" size={15} />{t('cmd.review', { n: k.recommended_transfers })}</Link>
        </div>
      </div>

      <div className="grid g-kpi" data-tour="kpis">
        <Kpi icon="pulse" label={t('kpi.reporting')} value={`${k.phcs_reporting_today}/${k.phcs}`}
          sub={t('kpi.compliance', { pct: pct(k.phcs_reporting_today / k.phcs) }) + (k.stale_phcs ? ` · ${t('kpi.silent', { n: k.stale_phcs })}` : '')} />
        <Kpi icon="alert" tone="alert" label={t('kpi.predicted')} value={k.predicted_stockouts} sub={t('kpi.predictedSub', { n: k.critical_items })} />
        <Kpi icon="pill" tone="warn" label={t('kpi.stockedOut')} value={k.stocked_out_items} sub={t('kpi.stockedOutSub')} />
        <Kpi icon="bug" tone={k.outbreak_clusters ? 'alert' : ''} label={t('kpi.clusters')} value={k.outbreak_clusters} sub={t('kpi.clustersSub', { n: k.anomalies })} />
        <Kpi icon="truck" label={t('kpi.transfers')} value={k.recommended_transfers} sub={t('kpi.transfersSub', { n: k.surplus_items })} />
        <Kpi icon="bed" label={t('kpi.beds')} value={pct(k.bed_occupancy)} sub={t('kpi.bedsSub', { pct: pct(k.staff_attendance) })} />
      </div>

      <div className="grid g-2">
        <Card tour="map" title={t('cmd.network')} icon="map" hint={t('cmd.networkHint')}
          right={<div className="legend">
            {Object.entries(HEALTH_COLOR).map(([h, c]) => <span key={h}><span className="dot" style={{ background: c }} />{t(`health.${h}`)} ({k.health[h]})</span>)}
            <span><span className="dot" style={{ border: '2px dashed #c62828' }} />{t('cmd.legendCluster')}</span>
          </div>} bodyClass="">
          <MapView phcs={data.phcs} clusters={data.clusters} />
        </Card>
        <div className="stack" style={{ gap: 18 }}>
          <Briefing />
          <Card title={t('cmd.signals')} icon="bug" right={<Link to="/outbreaks" className="small">{t('cmd.allSignals')}</Link>}>
            {!data.clusters.length && !data.anomalies.length && <div className="muted small">{t('cmd.noSignals')}</div>}
            <div className="stack">
              {data.clusters.map((c) => (
                <div key={c.id} className="rec" style={{ borderColor: '#f3c2c2' }}>
                  <div className="lane"><span className={`pill ${c.severity}-sev`}>{t('cmd.clusterPill', { severity: t(`severity.${c.severity}`) })}</span>
                    {t('cmd.clusterIn', { syndrome: t(`syndrome.${c.syndrome}`), district: (c.district_codes || [c.district_code]).map((d) => dname[d]).join(' / ') })}</div>
                  <div className="small muted">{t('cmd.clusterDetail', { phcs: c.phc_codes.join(', '), ratio: c.max_ratio, n: fmt(c.excess_cases) })}</div>
                </div>
              ))}
              {data.anomalies.filter((a) => !a.in_cluster).slice(0, 3).map((a) => (
                <div key={a.phc_id + a.syndrome} className="row small">
                  <span className="pill amber">{t(`syndrome.${a.syndrome}`)}</span>
                  <Link to={`/phc/${a.phc_id}`}>{a.phc_code} {a.phc_name}</Link>
                  <span className="muted">{t('cmd.vsExpected', { obs: a.observed, exp: a.expected })}</span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>

      <div className="grid g-2">
        <Card title={t('cmd.districts')} icon="grid" hint={t('cmd.districtsHint')} bodyClass="table-wrap">
          <table className="t">
            <thead><tr><th>{t('th.district')}</th><th className="r">{t('th.phcs')}</th><th className="r">{t('th.reported')}</th><th className="r">{t('th.score')}</th><th className="r">{t('th.redPhcs')}</th><th className="r">{t('th.criticalLines')}</th><th className="r">{t('th.anomalies')}</th></tr></thead>
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
        <Card title={t('cmd.topMoves')} icon="truck" right={<Link to="/redistribution" className="small">{t('cmd.openPlanner')}</Link>}>
          <div className="stack">
            {data.shipments.map((s) => (
              <div key={s.id} className="rec" onClick={() => nav('/redistribution')} style={{ cursor: 'pointer' }}>
                <div className="lane">{s.from.code} <Icon name="arrow" size={14} /> {s.to.code}
                  <span className="pill critical" style={{ marginLeft: 'auto' }}>{s.urgency_days <= 0 ? t('ship.stockedOut') : t('ship.neededInShort', { n: s.urgency_days })}</span></div>
                <div className="small muted">{s.lines.map((l) => `${fmt(l.qty)} ${l.drug_code}`).join(' + ')} · {fmt(s.distance_km)} km</div>
              </div>
            ))}
            {!data.shipments.length && <div className="muted small">{t('cmd.noTransfers')}</div>}
          </div>
        </Card>
      </div>

      <Card title={t('cmd.weakest')} icon="alert" bodyClass="table-wrap">
        <table className="t">
          <thead><tr><th>{t('th.phc')}</th><th>{t('th.district')}</th><th className="r">{t('th.score')}</th><th className="r">{t('th.critical')}</th><th className="r">{t('th.high')}</th><th className="r">{t('th.beds')}</th><th className="r">{t('th.staff')}</th><th>{t('th.report')}</th></tr></thead>
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
      <div className="muted small">{t('cmd.footer', { at: data.computed_at, ms: data.compute_ms, n: fmt(data.phcs.length * 10) })}</div>
    </>
  )
}

// Reporting freshness: silent PHCs are shown as unverified, not trusted as current.
export function ReportAge({ p }) {
  const { t } = useI18n()
  if (p.reported_today) return <span className="pill ok">{t('report.today')}</span>
  if (p.stale) return <span className="pill red" title={t('report.silentTitle')}>{t('report.silent', { n: p.days_since_report })}</span>
  return <span className="pill grey">{t('report.due')}</span>
}
