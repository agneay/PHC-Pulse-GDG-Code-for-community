-- National-scale demand forecasting inside the warehouse with BigQuery ML ARIMA_PLUS.
-- One model trains a separate time series per (PHC, drug), with automatic holiday/seasonality
-- handling, and is the warehouse-side counterpart of backend/app/forecasting.py.

CREATE OR REPLACE MODEL phc_pulse.demand_arima
OPTIONS (
  model_type = 'ARIMA_PLUS',
  time_series_timestamp_col = 'day',
  time_series_data_col = 'demand',
  time_series_id_col = ['phc_id', 'drug_code'],
  horizon = 28,
  holiday_region = 'IN',
  auto_arima = TRUE,
  data_frequency = 'DAILY'
) AS
SELECT phc_id, drug_code, day, dispensed + IFNULL(unmet, 0) AS demand
FROM phc_pulse.stock_daily
WHERE dispensed IS NOT NULL
  AND day >= DATE_SUB(CURRENT_DATE('Asia/Kolkata'), INTERVAL 365 DAY);

-- Early warning: days until cumulative forecast demand exceeds the latest closing stock.
WITH fc AS (
  SELECT phc_id, drug_code, DATE(forecast_timestamp) AS day, forecast_value,
         SUM(forecast_value) OVER (PARTITION BY phc_id, drug_code ORDER BY forecast_timestamp) AS cum
  FROM ML.FORECAST(MODEL phc_pulse.demand_arima, STRUCT(28 AS horizon, 0.8 AS confidence_level))
),
stock AS (
  SELECT phc_id, drug_code, ARRAY_AGG(closing ORDER BY day DESC LIMIT 1)[OFFSET(0)] AS closing
  FROM phc_pulse.stock_daily GROUP BY phc_id, drug_code
)
SELECT s.phc_id, s.drug_code, s.closing,
       MIN(IF(fc.cum >= s.closing, fc.day, NULL)) AS predicted_stockout_date
FROM stock s JOIN fc USING (phc_id, drug_code)
GROUP BY s.phc_id, s.drug_code, s.closing
HAVING predicted_stockout_date IS NOT NULL
ORDER BY predicted_stockout_date;

-- Outbreak signal counterpart: ML.DETECT_ANOMALIES on daily syndromic footfall.
CREATE OR REPLACE MODEL phc_pulse.footfall_arima
OPTIONS (model_type = 'ARIMA_PLUS', time_series_timestamp_col = 'day',
         time_series_data_col = 'diarrhoea', time_series_id_col = ['phc_id'],
         data_frequency = 'DAILY') AS
SELECT phc_id, day, diarrhoea FROM phc_pulse.footfall_daily
WHERE day < DATE_SUB(CURRENT_DATE('Asia/Kolkata'), INTERVAL 7 DAY);

SELECT * FROM ML.DETECT_ANOMALIES(
  MODEL phc_pulse.footfall_arima, STRUCT(0.99 AS anomaly_prob_threshold),
  (SELECT phc_id, day, diarrhoea FROM phc_pulse.footfall_daily
   WHERE day >= DATE_SUB(CURRENT_DATE('Asia/Kolkata'), INTERVAL 7 DAY)))
WHERE is_anomaly;
