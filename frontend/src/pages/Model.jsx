import { useApp } from '../App'
import Icon from '../components/Icon'
import { Card, ErrorBox, Kpi, Loading, useAsync } from '../components/ui'
import { useI18n } from '../i18n'
import { api, download } from '../lib/api'
import { fmt, pct, rich } from '../lib/format'

const PIPE = [['phone', 'pipe.report'], ['spark', 'pipe.gemini'], ['pulse', 'pipe.forecast'], ['truck', 'pipe.optimise'], ['grid', 'pipe.dashboards']]

export default function ModelPage() {
  const { version, meta, refresh, notify, scopeQs } = useApp()
  const { t } = useI18n()
  const { data, error, loading } = useAsync(() => api.get('/api/model'), [version])
  if (error) return <ErrorBox error={error} />
  if (loading && !data) return <Loading />
  const bt = data.backtest
  const month = meta.today.slice(0, 7)

  const reset = async () => {
    if (!window.confirm(t('model.resetConfirm'))) return
    try {
      await api.post('/api/admin/reset')
      refresh(); notify(t('model.resetDone'))
    } catch (e) { notify(e.message) }
  }

  return (
    <>
      <div className="page-h">
        <div>
          <div className="eyebrow">{t('model.eyebrow')}</div>
          <h1>{t('model.title')}</h1>
          <p>{t('model.intro')}</p>
        </div>
        <div className="right">
          <button className="btn" onClick={() => download(`/api/hmis/export.csv${scopeQs}${scopeQs ? '&' : '?'}month=${month}`, `phc_pulse_hmis_${month}.csv`).catch((e) => notify(e.message))}><Icon name="download" size={15} />{t('model.export', { month })}</button>
          <a className="btn" href="/docs" target="_blank" rel="noreferrer">{t('model.apiDocs')}</a>
          <button className="btn ghost" onClick={reset}><Icon name="refresh" size={15} />{t('model.reset')}</button>
        </div>
      </div>

      <div className="grid g-kpi">
        <Kpi icon="alert" tone="good" label={t('model.kpiRecall')} value={pct(bt.recall_14d_ahead)} sub={t('model.kpiRecallSub', { n: bt.flagged_14d_ahead, total: bt.stockout_events })} />
        <Kpi icon="check" label={t('model.kpiPrecision')} value={pct(bt.precision)} sub={t('model.kpiPrecisionSub')} />
        <Kpi icon="pulse" label={t('model.kpiAccuracy')} value={pct(bt.weekly_accuracy)} sub={t('model.kpiAccuracySub', { daily: pct(bt.forecast_accuracy) })} />
        <Kpi icon="chip" label={t('model.kpiCompute')} value={`${fmt(data.compute_ms)} ms`} sub={t('model.kpiComputeSub', { n: data.forecaster.series })} />
      </div>

      <Card title={t('model.pipeline')} icon="pulse" hint={t('model.pipelineHint')}>
        <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 10 }}>
          {PIPE.map(([ic, k], i) => (
            <div key={k} className="rec" style={{ background: 'var(--blush-50)' }}>
              <div className="row"><span className="badge">{i + 1}</span><Icon name={ic} size={16} /><b>{t(`${k}.title`)}</b></div>
              <div className="small muted">{t(`${k}.text`)}</div>
            </div>
          ))}
        </div>
      </Card>

      <div className="grid g-3">
        <Card title={t('model.forecasting')} icon="pulse">
          <div className="small stack">
            <div>{rich(t('model.fcModel', { name: data.forecaster.name }))}</div>
            <div className="muted">α={data.forecaster.alpha} β={data.forecaster.beta} γ={data.forecaster.gamma} φ={data.forecaster.phi} · {t('model.horizon', { n: data.forecaster.horizon_days })}</div>
            <div>{rich(t('model.fcOutbreak'))}</div>
            <div>{rich(t('model.fcRule', { n: meta.params.warning_window }))}</div>
            <div className="note">{t('model.fcProduction')}</div>
          </div>
        </Card>
        <Card title={t('model.optimiser')} icon="truck">
          <div className="small stack">
            <div>{rich(t('model.optModel'))}</div>
            <div>{t('model.optConstraints', { n: meta.params.safety_days })}</div>
            <div>{t('model.optCost', { fixed: meta.params.fixed_trip_cost, km: meta.params.cost_per_km })}</div>
            <div className="muted">{t('model.optLast', { solver: data.plan_stats.solver, vars: data.plan_stats.variables, lanes: data.plan_stats.lanes })}</div>
          </div>
        </Card>
        <Card title={t('model.anomaly')} icon="bug">
          <div className="small stack">
            <div>{rich(t('model.anModel'))}</div>
            <div>{t('model.anRule', { z: data.anomaly.threshold_z, km: data.anomaly.cluster_km })}</div>
            <div>{t('model.anGemini')}</div>
          </div>
        </Card>
      </div>

      <div className="grid g-2e">
        <Card title={t('model.google')} icon="spark">
          <table className="t">
            <tbody>
              <tr><td><b>Gemini</b> ({meta.gemini.enabled ? meta.gemini.model : t('model.notConfigured')})</td><td className="small">{t('model.gGemini')}</td></tr>
              <tr><td><b>Dialogflow CX</b></td><td className="small">{t('model.gDialogflow')} → <code>/api/dialogflow/webhook</code></td></tr>
              <tr><td><b>Cloud Run</b></td><td className="small">{t('model.gRun')}</td></tr>
              <tr><td><b>BigQuery</b></td><td className="small">{t('model.gBigQuery')} (<code>/bigquery/schema.sql</code>)</td></tr>
              <tr><td><b>Vertex AI / BQML</b></td><td className="small">{t('model.gVertex')} (<code>/vertex</code>, <code>/bigquery/forecast.sql</code>)</td></tr>
            </tbody>
          </table>
        </Card>
        <Card title={t('model.hmis')} icon="download">
          <div className="small stack">
            <div>{rich(t('model.hmisText'))}</div>
            <div>{rich(t('model.hmisGeneral'))}</div>
            <div className="muted">{t('model.hmisSynthetic')}</div>
          </div>
        </Card>
      </div>
    </>
  )
}
