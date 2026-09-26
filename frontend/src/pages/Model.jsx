import { useApp } from '../App'
import Icon from '../components/Icon'
import ImpactCard from '../components/Impact'
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

      <Card tour="model-pipeline" title={t('model.pipeline')} icon="pulse" hint={t('model.pipelineHint')}>
        <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 10 }}>
          {PIPE.map(([ic, k], i) => (
            <div key={k} className="rec" style={{ background: 'var(--blush-50)' }}>
              <div className="row"><span className="badge">{i + 1}</span><Icon name={ic} size={16} /><b>{t(`${k}.title`)}</b></div>
              <div className="small muted">{t(`${k}.text`)}</div>
            </div>
          ))}
        </div>
      </Card>

      <div className="grid g-2e">
        <ImpactCard impact={data.impact} national />
        <ScaleCard />
      </div>

      <FederatedCard />

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

      <Card tour="integrations" title={t('integ.title')} icon="download" hint={t('integ.hint')}>
        <div className="small stack">
          <div>{rich(t('integ.text'))}</div>
          <div className="row" style={{ flexWrap: 'wrap' }}>
            <button className="btn" onClick={() => download(`/api/dhis2/dataValueSets${scopeQs}${scopeQs ? '&' : '?'}month=${month}`, `phc_pulse_dhis2_${month}.json`).catch((e) => notify(e.message))}>
              <Icon name="download" size={15} />{t('integ.dhis2', { month })}</button>
            <button className="btn" onClick={() => download('/api/dhis2/metadata', 'phc_pulse_dhis2_metadata.json').catch((e) => notify(e.message))}>
              <Icon name="download" size={15} />{t('integ.dhis2Meta')}</button>
            <button className="btn" onClick={() => download(`/api/hmis/export.csv${scopeQs}${scopeQs ? '&' : '?'}month=${month}`, `phc_pulse_hmis_${month}.csv`).catch((e) => notify(e.message))}>
              <Icon name="download" size={15} />{t('model.export', { month })}</button>
          </div>
        </div>
      </Card>
    </>
  )
}

/** Federated round: per-state local training, FedAvg prior, leave-one-state-out cold start. */
function FederatedCard() {
  const { meta } = useApp()
  const { t } = useI18n()
  const { data, error } = useAsync(() => api.get('/api/federated'), [])
  const sname = Object.fromEntries(meta.states.map((s) => [s.code, s.name]))
  return (
    <Card tour="federated" title={t('fed.title')} icon="users" hint={t('fed.hint')}>
      {error ? <ErrorBox error={error} /> : !data ? <Loading label={t('fed.loading')} /> : (
        <div className="stack">
          <div className="small">{rich(t('fed.intro', { n: data.summary.numbers_shared_per_state }))}</div>
          <div className="impact-grid">
            <div className="impact-cell"><b className="num">{pct(data.summary.local_accuracy)}</b><span>{t('fed.local')}</span></div>
            <div className="impact-cell good"><b className="num">{pct(data.summary.federated_accuracy)}</b><span>{t('fed.federated')}</span></div>
            <div className="impact-cell"><b className="num">{pct(data.summary.zero_history_accuracy)}</b><span>{t('fed.zero')}</span></div>
          </div>
          <div className="muted small">{t('fed.coldStart', { n: data.cold_start_days })}</div>
          <div className="table-wrap">
            <table className="t">
              <thead><tr><th>{t('filter.state')}</th><th className="r">{t('fed.local')}</th><th className="r">{t('fed.federated')}</th>
                <th className="r">{t('fed.shared')}</th><th className="r">{t('fed.kept')}</th><th>{t('fed.params')}</th></tr></thead>
              <tbody>
                {data.states.map((s) => (
                  <tr key={s.state}>
                    <td>{sname[s.state] || s.state}</td>
                    <td className="r num">{pct(s.local_accuracy)}</td>
                    <td className="r num"><b>{pct(s.federated_accuracy)}</b></td>
                    <td className="r num">{fmt(s.numbers_shared)}</td>
                    <td className="r num">{fmt(s.raw_rows_kept_local)}</td>
                    <td className="small muted">α {s.params.alpha} · γ {s.params.gamma} · φ {s.params.phi}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Card>
  )
}

function ScaleCard() {
  const { t } = useI18n()
  const { data, error } = useAsync(() => api.get('/api/scale'), [])
  const st = data?.stage_totals_s
  return (
    <Card tour="scale" title={t('scale.title')} icon="grid" hint={t('scale.hint')}>
      {error ? <div className="muted small">{t('scale.missing')}</div> : !data ? <Loading /> : (
        <div className="small stack">
          <div>{rich(t('scale.text', { phcs: fmt(data.phcs), states: data.states, series: fmt(data.series),
            seq: fmt(data.sequential_s, 1), slow: fmt(data.slowest_state_s, 1), state: data.slowest_state }))}</div>
          <div className="muted">{t('scale.stages', { f: fmt(st.forecast_s, 1), w: fmt(st.early_warning_s, 1), a: fmt(st.anomaly_s, 1), m: fmt(st.milp_s, 1) })}</div>
          <div className="muted">{data.machine}</div>
        </div>
      )}
    </Card>
  )
}
