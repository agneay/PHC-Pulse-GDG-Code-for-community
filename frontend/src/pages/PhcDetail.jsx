import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { Area, CartesianGrid, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useApp } from '../App'
import Icon from '../components/Icon'
import { Card, ErrorBox, Kpi, Loading, StatusPill, useAsync } from '../components/ui'
import { useI18n } from '../i18n'
import { api } from '../lib/api'
import { daysText, drugLabel, fmt, pct, shortDay, unitLabel } from '../lib/format'

const ORDER = ['stocked_out', 'critical', 'high', 'watch', 'ok', 'surplus']

export default function PhcDetail() {
  const { id } = useParams()
  const [sp, setSp] = useSearchParams()
  const { version, meta } = useApp()
  const { t, lang, locale, fontScale } = useI18n()
  const fs = Math.round(11 * fontScale)          // chart text follows the text-size setting
  const { data, error, loading } = useAsync(() => api.get(`/api/phcs/${id}`), [id, version])
  const [syn, setSyn] = useState('opd')

  if (error) return <ErrorBox error={error} />
  if (loading && !data) return <Loading />
  const p = data.phc
  const drugCode = sp.get('drug') || [...data.drugs].sort((a, b) => ORDER.indexOf(a.status) - ORDER.indexOf(b.status))[0].code
  const d = data.drugs.find((x) => x.code === drugCode)
  const name = (x) => drugLabel(meta.drugs.find((m) => m.code === x.code), lang)
  const day = (iso) => shortDay(iso, locale)
  const series = [
    ...d.history.map((h) => ({ day: h.day, demand: h.demand, stock: h.stock })),
    ...d.forecast.map((f) => ({ day: f.day, forecast: f.forecast, band: [f.lo, f.hi], projected: f.projected_stock })),
  ]
  const supplyDay = new Date(meta.today); supplyDay.setDate(supplyDay.getDate() + d.next_supply_in)
  const supplyIso = supplyDay.toISOString().slice(0, 10)
  const reportLang = meta.languages[p.language]

  return (
    <>
      <div className="page-h">
        <div>
          <div className="eyebrow">{data.district_name} · {data.state_name} · NIN {p.nin}</div>
          <h1>{p.code} · {p.name}</h1>
          <p>{t('phc.facts', { kind: p.is_24x7 ? t('phc.24x7') : t('phc.day'), beds: p.beds_total, staff: p.staff_sanctioned, language: reportLang.native, last: p.last_report })}</p>
        </div>
        <div className="right">
          {p.stale && <span className="pill red" style={{ fontSize: 'calc(14px * var(--fs, 1))', padding: '4px 12px' }} title={t('phc.staleTitle')}>{t('phc.stale', { n: p.days_since_report })}</span>}
          <span className={`pill ${p.health}`} style={{ fontSize: 'calc(14px * var(--fs, 1))', padding: '4px 12px' }}>{t('phc.resilience', { score: p.score })}</span>
          <Link className="btn" to={`/report?phc=${p.id}`}><Icon name="mic" size={15} />{t('phc.reportHere')}</Link>
        </div>
      </div>
      <div className="grid g-kpi">
        <Kpi icon="alert" tone={p.critical_items ? 'alert' : ''} label={t('phc.kpiCritical')} value={p.critical_items} sub={t('phc.kpiCriticalSub', { high: p.high_items, watch: p.watch_items })} />
        <Kpi icon="bed" label={t('phc.kpiBeds')} value={`${p.beds_occupied ?? '–'}/${p.beds_total}`} sub={pct(p.bed_occupancy)} />
        <Kpi icon="users" label={t('phc.kpiStaff')} value={`${p.staff_present ?? '–'}/${p.staff_sanctioned}`} sub={pct(p.attendance)} />
        <Kpi icon="pulse" label={t('phc.kpiOpd')} value={fmt(p.opd_last)} sub={p.reported_today ? t('phc.reportedToday') : t('phc.reportDue')} />
        <Kpi icon="truck" label={t('phc.kpiSupply')} value={p.next_supply_in === 1 ? t('days.one') : t('days.many', { n: p.next_supply_in })} sub={t('phc.kpiSupplySub')} />
      </div>

      <div className="grid g-2">
        <Card title={t('phc.chartTitle', { drug: name(d) })} icon="pill"
          right={<select className="select" value={drugCode} onChange={(e) => setSp({ drug: e.target.value })} aria-label={t('th.drug')}>
            {data.drugs.map((x) => <option key={x.code} value={x.code}>{name(x)} · {t(`status.${x.status}`)}</option>)}
          </select>}>
          <div className="row small" style={{ marginBottom: 8 }}>
            <StatusPill status={d.status} />
            <span>{t('phc.stockNow', { n: fmt(d.stock), unit: unitLabel(t, d.unit) })}</span>
            <span>· {t('phc.perDay', { n: fmt(d.daily_forecast, 1) })}</span>
            <span>· {t('phc.runsOut', { when: daysText(t, d.days_to_stockout) })}</span>
            <span>· {t('phc.pOut', { pct: Math.round(d.p_stockout * 100) })}</span>
            {d.surge_reason && <span className="pill red">{t('phc.outbreakAdjusted', { x: d.surge })}</span>}
          </div>
          <ResponsiveContainer width="100%" height={300}>
            <ComposedChart data={series} margin={{ left: -10, right: 10 }}>
              <CartesianGrid stroke="#f3e6e6" vertical={false} />
              <XAxis dataKey="day" tickFormatter={day} minTickGap={28} fontSize={fs} />
              <YAxis yAxisId="d" fontSize={fs} />
              <YAxis yAxisId="s" orientation="right" fontSize={fs} />
              <Tooltip labelFormatter={day} formatter={(v, n) => [Array.isArray(v) ? `${v[0]}–${v[1]}` : fmt(v, 1), n]} />
              <Legend wrapperStyle={{ fontSize: 'calc(12px * var(--fs, 1))' }} />
              <Area isAnimationActive={false} yAxisId="s" dataKey="stock" name={t('chart.stock')} fill="#cfe2fb" stroke="#1565c0" strokeWidth={1.5} fillOpacity={0.5} />
              <Area isAnimationActive={false} yAxisId="s" dataKey="projected" name={t('chart.projected')} fill="#ffe0c2" stroke="#ef6c00" strokeDasharray="5 4" fillOpacity={0.5} />
              <Area isAnimationActive={false} yAxisId="d" dataKey="band" name={t('chart.band')} fill="#f5c9c9" stroke="none" fillOpacity={0.5} />
              <Line isAnimationActive={false} yAxisId="d" dataKey="demand" name={t('chart.demand')} stroke="#7a1f1f" dot={false} strokeWidth={1.4} />
              <Line isAnimationActive={false} yAxisId="d" dataKey="forecast" name={t('chart.forecast')} stroke="#c62828" dot={false} strokeWidth={2} />
              <ReferenceLine yAxisId="d" x={meta.today} stroke="#5c1515" label={{ value: t('chart.today'), fontSize: fs, fill: '#5c1515' }} />
              {d.next_supply_in <= 28 && <ReferenceLine yAxisId="d" x={supplyIso} stroke="#2e7d32" strokeDasharray="4 4" label={{ value: t('chart.nextSupply'), fontSize: fs, fill: '#2e7d32' }} />}
            </ComposedChart>
          </ResponsiveContainer>
        </Card>
        <Card title={t('phc.allLines')} icon="pill" bodyClass="table-wrap">
          <table className="t">
            <thead><tr><th>{t('th.drug')}</th><th className="r">{t('th.stock')}</th><th className="r">{t('th.cover')}</th><th>{t('th.status')}</th></tr></thead>
            <tbody>
              {data.drugs.map((x) => (
                <tr key={x.code} className="click" onClick={() => setSp({ drug: x.code })} style={x.code === drugCode ? { background: 'var(--blush-50)' } : null}>
                  <td>{name(x)}</td>
                  <td className="r num">{fmt(x.stock)}</td>
                  <td className="r num">{x.cover_days >= 999 ? '–' : t('common.daysShort', { n: fmt(x.cover_days) })}</td>
                  <td><StatusPill status={x.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>

      <div className="grid g-2">
        <Card title={t('phc.footfall')} icon="pulse" hint={t('phc.footfallHint')}
          right={<div className="lang-tabs">{['opd', 'fever', 'diarrhoea', 'respiratory'].map((s) => (
            <button key={s} className={syn === s ? 'on' : ''} onClick={() => setSyn(s)}>{t(`syndrome.${s}`)}</button>))}</div>}>
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart data={data.footfall} margin={{ left: -10, right: 10 }}>
              <CartesianGrid stroke="#f3e6e6" vertical={false} />
              <XAxis dataKey="day" tickFormatter={day} minTickGap={28} fontSize={fs} />
              <YAxis fontSize={fs} />
              <Tooltip labelFormatter={day} />
              <Legend wrapperStyle={{ fontSize: 'calc(12px * var(--fs, 1))' }} />
              <Line isAnimationActive={false} dataKey={`${syn}_threshold`} name={t('chart.threshold')} stroke="#ef6c00" strokeDasharray="5 4" dot={false} />
              <Line isAnimationActive={false} dataKey={`${syn}_expected`} name={t('chart.expected')} stroke="#9e8a8a" dot={false} />
              <Line isAnimationActive={false} dataKey={syn} name={t('chart.observed')} stroke="#c62828" strokeWidth={2} dot={{ r: 1.5 }} />
            </ComposedChart>
          </ResponsiveContainer>
          {data.anomalies.length > 0 && (
            <div className="row small">{data.anomalies.map((a) => (
              <span key={a.syndrome} className={`pill ${a.in_cluster ? 'red' : 'amber'}`}>{t('phc.anomalyPill', { syndrome: t(`syndrome.${a.syndrome}`), ratio: a.ratio })}{a.in_cluster ? ` · ${t('out.cluster')}` : ''}</span>))}</div>
          )}
        </Card>
        <Card title={t('phc.transfersReports')} icon="truck">
          <div className="stack">
            {data.recommendations.map((s) => (
              <div key={s.id} className="rec">
                <div className="lane">{s.from.code} <Icon name="arrow" size={14} /> {s.to.code}<span className="pill approved" style={{ marginLeft: 'auto' }}>{t('phc.recommended')}</span></div>
                <div className="small muted">{s.lines.map((l) => `${fmt(l.qty)} ${l.drug_code}`).join(' + ')} · {t('ship.neededInShort', { n: s.urgency_days })} · <Link to="/redistribution">{t('phc.review')}</Link></div>
              </div>
            ))}
            {data.transfers.map((tr) => (
              <div key={tr.id} className="row small"><span className={`pill ${tr.status}`}>{t(`transfer.${tr.status}`)}</span>{tr.from_code} → {tr.to_code}: {tr.lines.map((l) => `${fmt(l.qty)} ${l.drug_code}`).join(', ')}</div>
            ))}
            <div className="sep" />
            {data.reports.length === 0 && <div className="muted small">{t('phc.noReports')}</div>}
            {data.reports.map((r) => (
              <div key={r.id} className="small">
                <span className="pill grey">{r.channel}</span> <span className="muted">{r.created_at.replace('T', ' ')}</span>
                {r.transcript && <div style={{ marginTop: 3 }} lang={r.language}>“{r.transcript}”</div>}
              </div>
            ))}
          </div>
        </Card>
      </div>
    </>
  )
}
