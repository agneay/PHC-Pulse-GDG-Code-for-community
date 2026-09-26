import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useApp } from '../App'
import { Card, ErrorBox, Loading, StatusPill, useAsync } from '../components/ui'
import { useI18n } from '../i18n'
import { api } from '../lib/api'
import { daysText, drugLabel, fmt, rich, surgeText, unitLabel } from '../lib/format'

const ORDER = { stocked_out: 0, critical: 1, high: 2, watch: 3, ok: 4, surplus: 5 }

export default function Stock() {
  const { scopeQs, version, meta } = useApp()
  const { t, lang } = useI18n()
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
  const drugs = Object.fromEntries(data.drugs.map((d) => [d.code, d]))
  const warnings = data.items.filter((i) => ORDER[i.status] <= 3 && (!drug || i.drug_code === drug))
    .sort((a, b) => ORDER[a.status] - ORDER[b.status] || (a.days_to_stockout ?? 99) - (b.days_to_stockout ?? 99))
  const counts = Object.fromEntries(Object.keys(ORDER).map((s) => [s, data.items.filter((i) => i.status === s).length]))

  return (
    <>
      <div className="page-h">
        <div>
          <div className="eyebrow">{t('stock.eyebrow')}</div>
          <h1>{t('stock.title')}</h1>
          <p>{rich(t('stock.intro'))}</p>
        </div>
      </div>
      <div className="row">
        {Object.keys(ORDER).map((s) => <span key={s} className={`pill ${s}`}>{t(`status.${s}`)}: {counts[s]}</span>)}
      </div>

      <Card tour="stock-matrix" title={t('stock.matrix')} hint={t('stock.matrixHint')}
        right={<label className="row small"><input type="checkbox" checked={onlyRisk} onChange={(e) => setOnlyRisk(e.target.checked)} /> {t('stock.onlyRisk')}</label>}
        bodyClass="card-b table-wrap">
        <table className="heat">
          <thead><tr><th style={{ textAlign: 'left' }}>{t('th.phc')}</th>{data.drugs.map((d) => <th key={d.code} title={drugLabel(d, lang)}>{d.code}</th>)}</tr></thead>
          <tbody>
            {matrix.map((p) => (
              <tr key={p.id}>
                <td className="name"><Link to={`/phc/${p.id}`}><b>{p.code}</b></Link> <span className="muted">{p.name.replace('PHC ', '')} · {dname[p.district_code]}</span></td>
                {data.drugs.map((d) => {
                  const c = p.cells[d.code]
                  if (!c) return <td key={d.code} />
                  return (
                    <td key={d.code} className={`c ${c.status}`} onClick={() => nav(`/phc/${p.id}?drug=${d.code}`)}
                      title={t('stock.cellTitle', { drug: drugLabel(d, lang), stock: fmt(c.stock), unit: unitLabel(t, d.unit), rate: fmt(c.daily_forecast, 1), status: t(`status.${c.status}`) })}>
                      {c.status === 'stocked_out' ? '0' : c.cover_days >= 99 ? '99+' : Math.round(c.cover_days)}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
        {!matrix.length && <div className="empty">{t('stock.noRisk')}</div>}
      </Card>

      <Card tour="stock-warnings" title={t('stock.warnings')} icon="alert" hint={t('stock.lines', { n: warnings.length })}
        right={<select className="select" value={drug} onChange={(e) => setDrug(e.target.value)} aria-label={t('stock.filterDrug')}>
          <option value="">{t('stock.allDrugs')}</option>
          {data.drugs.map((d) => <option key={d.code} value={d.code}>{drugLabel(d, lang)}</option>)}
        </select>} bodyClass="table-wrap">
        <table className="t">
          <thead><tr><th>{t('th.status')}</th><th>{t('th.phc')}</th><th>{t('th.drug')}</th><th className="r">{t('th.stock')}</th><th className="r">{t('th.forecastDay')}</th><th className="r">{t('th.runsOutIn')}</th><th className="r">{t('th.nextSupply')}</th><th className="r">{t('th.pStockout')}</th><th>{t('th.signal')}</th></tr></thead>
          <tbody>
            {warnings.slice(0, 150).map((i) => (
              <tr key={`${i.phc_id}-${i.drug_code}`} className="click" onClick={() => nav(`/phc/${i.phc_id}?drug=${i.drug_code}`)}>
                <td><StatusPill status={i.status} /></td>
                <td><b>{i.phc_code}</b> <span className="muted">{i.phc_name}</span></td>
                <td>{drugLabel(drugs[i.drug_code], lang)}</td>
                <td className="r num">{fmt(i.stock)} <span className="muted small">{unitLabel(t, i.unit)}</span></td>
                <td className="r num">{fmt(i.daily_forecast, 1)}</td>
                <td className="r num"><b>{daysText(t, i.days_to_stockout)}</b></td>
                <td className="r num">{t('common.daysShort', { n: i.next_supply_in })}</td>
                <td className="r num">{Math.round(i.p_stockout * 100)}%</td>
                <td>{i.surge_reason && <span className="pill red" title={t('stock.outbreakAdjusted')}>↑ {surgeText(t, i.surge_reason)}</span>}
                  {i.incoming > 0 && <span className="pill in_transit">{t('stock.incoming', { n: fmt(i.incoming) })}</span>}
                  {i.stale && <span className="pill grey" title={t('report.silentTitle')}>{t('stock.unverified')}</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!warnings.length && <div className="empty">{t('stock.noWarnings')}</div>}
      </Card>
    </>
  )
}
