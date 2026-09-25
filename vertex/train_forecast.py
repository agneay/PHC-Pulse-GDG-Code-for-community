"""Train the per-PHC x per-drug demand forecaster with Vertex AI AutoML Forecasting.

This is the production training path described in the pitch deck; the prototype serves the
in-process Holt-Winters model (backend/app/forecasting.py) so the demo runs without training
credits. Run after `scripts/export_bigquery.py`:

    pip install google-cloud-aiplatform
    python vertex/train_forecast.py --project my-project --region asia-south1 --dataset phc_pulse

The training view adds calendar and outbreak covariates (syndromic footfall), so the model
learns the monsoon/outbreak effects that the in-process model applies as a surge factor.
"""
import argparse

TRAINING_VIEW = """
CREATE OR REPLACE VIEW `{project}.{dataset}.forecast_training` AS
SELECT
  CONCAT(CAST(s.phc_id AS STRING), '-', s.drug_code) AS series_id,
  s.day,
  s.dispensed + IFNULL(s.unmet, 0) AS demand,
  s.state_code, s.drug_code,
  f.opd, f.fever, f.diarrhoea, f.respiratory,
  EXTRACT(DAYOFWEEK FROM s.day) AS dow,
  EXTRACT(MONTH FROM s.day) AS month
FROM `{project}.{dataset}.stock_daily` s
JOIN `{project}.{dataset}.footfall_daily` f USING (phc_id, day)
WHERE s.dispensed IS NOT NULL
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--region", default="asia-south1")
    ap.add_argument("--dataset", default="phc_pulse")
    ap.add_argument("--budget-milli-node-hours", type=int, default=1000)
    args = ap.parse_args()

    from google.cloud import aiplatform, bigquery

    bigquery.Client(project=args.project).query(
        TRAINING_VIEW.format(project=args.project, dataset=args.dataset)).result()
    aiplatform.init(project=args.project, location=args.region)

    ds = aiplatform.TimeSeriesDataset.create(
        display_name="phc-pulse-demand",
        bq_source=f"bq://{args.project}.{args.dataset}.forecast_training")

    job = aiplatform.AutoMLForecastingTrainingJob(
        display_name="phc-pulse-demand-automl",
        optimization_objective="minimize-quantile-loss",
        column_specs={"day": "timestamp", "demand": "numeric", "opd": "numeric",
                      "fever": "numeric", "diarrhoea": "numeric", "respiratory": "numeric",
                      "dow": "categorical", "month": "categorical", "state_code": "categorical",
                      "drug_code": "categorical"})
    model = job.run(
        dataset=ds, target_column="demand", time_column="day", time_series_identifier_column="series_id",
        available_at_forecast_columns=["day", "dow", "month"],
        unavailable_at_forecast_columns=["demand", "opd", "fever", "diarrhoea", "respiratory"],
        time_series_attribute_columns=["state_code", "drug_code"],
        forecast_horizon=28, context_window=56, data_granularity_unit="day", data_granularity_count=1,
        quantiles=[0.1, 0.5, 0.9], budget_milli_node_hours=args.budget_milli_node_hours,
        model_display_name="phc-pulse-demand")
    print("trained:", model.resource_name)


if __name__ == "__main__":
    main()
