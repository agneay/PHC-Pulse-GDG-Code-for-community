import { useApp } from '../App'
import Icon from '../components/Icon'
import { Card, ErrorBox, Kpi, Loading, useAsync } from '../components/ui'
import { api } from '../lib/api'
import { fmt, pct } from '../lib/format'

const PIPE = [
  ['phone', 'Worker reports', 'Voice (web), USSD, SMS, IVR via Dialogflow CX webhook'],
  ['spark', 'Gemini understanding', 'Audio → transcript, translation, structured JSON, local-language read-back'],
  ['pulse', 'Forecast', 'Per-PHC × per-drug demand, outbreak-aware; stock-out before next supply'],
  ['truck', 'Optimise', 'MILP redistribution with lane consolidation & cost constraints'],
  ['grid', 'Dashboards', 'National → state → district → PHC with row-level scoping'],
]

export default function ModelPage() {
  const { version, meta, refresh, notify, scopeQs } = useApp()
  const { data, error, loading } = useAsync(() => api.get('/api/model'), [version])
  if (error) return <ErrorBox error={error} />
  if (loading && !data) return <Loading />
  const bt = data.backtest
  const month = meta.today.slice(0, 7)

  const reset = async () => {
    if (!window.confirm('Reset all demo data (reports, transfers) to the seeded state?')) return
    await api.post('/api/admin/reset')
    refresh(); notify('Demo data reset')
  }

  return (
    <>
      <div className="page-h">
        <div>
          <div className="eyebrow">Transparency</div>
          <h1>Models, validation & HMIS integration</h1>
          <p>How the engine works, how well it performs on held-out history, and how it plugs into existing HMIS pipelines instead of replacing them.</p>
        </div>
        <div className="right">
          <a className="btn" href={`/api/hmis/export.csv${scopeQs}${scopeQs ? '&' : '?'}month=${month}`}><Icon name="download" size={15} />HMIS export ({month})</a>
          <a className="btn" href="/docs" target="_blank" rel="noreferrer">API docs</a>
          <button className="btn ghost" onClick={reset}><Icon name="refresh" size={15} />Reset demo</button>
        </div>
      </div>

      <div className="grid g-kpi">
        <Kpi icon="alert" tone="good" label="Stock-outs flagged ≥14 days ahead" value={pct(bt.recall_14d_ahead)} sub={`${bt.flagged_14d_ahead} of ${bt.stockout_events} real stock-out events (last 60 days, walk-forward)`} />
        <Kpi icon="check" label="Warning precision" value={pct(bt.precision)} sub="flags followed by a real stock-out within 21 days" />
        <Kpi icon="pulse" label="Weekly demand forecast accuracy" value={pct(bt.weekly_accuracy)} sub={`1 − wMAPE on weekly totals, 4 weeks held out · daily: ${pct(bt.forecast_accuracy)}`} />
        <Kpi icon="chip" label="Engine recompute" value={`${fmt(data.compute_ms)} ms`} sub={`${data.forecaster.series} series + MILP + anomalies`} />
      </div>

      <Card title="Pipeline" icon="pulse" hint="from a health worker's voice note to a same-day resupply">
        <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 10 }}>
          {PIPE.map(([ic, t, d], i) => (
            <div key={t} className="rec" style={{ background: 'var(--blush-50)' }}>
              <div className="row"><span className="badge">{i + 1}</span><Icon name={ic} size={16} /><b>{t}</b></div>
              <div className="small muted">{d}</div>
            </div>
          ))}
        </div>
      </Card>

      <div className="grid g-3">
        <Card title="Demand forecasting" icon="pulse">
          <div className="small stack">
            <div><b>{data.forecaster.name}</b>, fitted per PHC × drug, all series vectorised in one pass.</div>
            <div className="muted">α={data.forecaster.alpha} β={data.forecaster.beta} γ={data.forecaster.gamma} φ={data.forecaster.phi} · horizon {data.forecaster.horizon_days} days</div>
            <div><b>Outbreak-aware:</b> {data.forecaster.outbreak_adjustment}.</div>
            <div><b>Early warning rule:</b> projected stock (incl. in-transit transfers) reaches zero within {meta.params.warning_window} days <i>and</i> before the next scheduled indent delivery.</div>
            <div className="note">Production path: the same features are exported to BigQuery and trained with Vertex AI Forecasting / BigQuery ML ARIMA_PLUS (scripts in <code>/vertex</code> and <code>/bigquery</code>). This in-process model is the low-latency fallback.</div>
          </div>
        </Card>
        <Card title="Redistribution optimiser" icon="truck">
          <div className="small stack">
            <div><b>{data.optimizer.name}</b>. Objective: {data.optimizer.objective}.</div>
            <div>Constraints: donors keep {meta.params.safety_days} days safety stock plus 120% of their own forecast until their next supply; recipients are topped up to their next supply + safety days.</div>
            <div>Lane cost = ₹{meta.params.fixed_trip_cost} fixed + ₹{meta.params.cost_per_km}/road-km (+ inter-state paperwork). {data.optimizer.consolidation}.</div>
            <div className="muted">Last solve: {data.plan_stats.solver} · {data.plan_stats.variables} variables · {data.plan_stats.lanes} lanes</div>
          </div>
        </Card>
        <Card title="Outbreak anomaly detection" icon="bug">
          <div className="small stack">
            <div><b>{data.anomaly.method}</b>, run on total OPD and fever / diarrhoea / respiratory syndromes.</div>
            <div>PHC flag: z ≥ {data.anomaly.threshold_z}, ≥1.5× expected and ≥5 excess cases. Cluster: ≥2 PHCs, same syndrome, within {data.anomaly.cluster_km} km over the last 3 days.</div>
            <div>Gemini drafts the IDSP alert (English + local language) with the recommended response.</div>
          </div>
        </Card>
      </div>

      <div className="grid g-2e">
        <Card title="Google AI & Cloud" icon="spark">
          <table className="t">
            <tbody>
              <tr><td><b>Gemini</b> ({meta.gemini.enabled ? meta.gemini.model : 'not configured'})</td><td className="small">Multimodal voice-report understanding in 8 Indian languages; briefings; copilot; outbreak alerts</td></tr>
              <tr><td><b>Dialogflow CX</b></td><td className="small">IVR agent for feature phones → <code>/api/dialogflow/webhook</code></td></tr>
              <tr><td><b>Cloud Run</b></td><td className="small">Single container serving the API and dashboard</td></tr>
              <tr><td><b>BigQuery</b></td><td className="small">Warehouse schema + row-level security by state (<code>/bigquery/schema.sql</code>)</td></tr>
              <tr><td><b>Vertex AI / BQML</b></td><td className="small">Forecast training at national scale (<code>/vertex</code>, <code>/bigquery/forecast.sql</code>)</td></tr>
            </tbody>
          </table>
        </Card>
        <Card title="HMIS-compatible by design" icon="download">
          <div className="small stack">
            <div>Facilities are keyed by their HMIS <b>National Identification Number (NIN)</b>. Historical daily data is backfilled from HMIS, and PHC Pulse exports a monthly facility report (OPD, syndromic counts, item receipts, consumption, closing balance, stock-out days) in a flat HMIS-style layout.</div>
            <div>The same redistribution engine generalises to <b>blood banks, oxygen and ambulances</b>: any resource with a stock, a forecastable demand and a transport cost.</div>
            <div className="muted">Data in this prototype is synthetic, generated to match HMIS PHC volumes, NLEM drug lists, monsoon seasonality and state epidemiology. No patient-level data is stored.</div>
          </div>
        </Card>
      </div>
    </>
  )
}
