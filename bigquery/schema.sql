-- PHC Pulse national warehouse (BigQuery). Mirrors backend/app/db.py.
-- Replace `phc_pulse` with your dataset:  bq mk --location=asia-south1 phc_pulse

CREATE TABLE IF NOT EXISTS phc_pulse.phcs (
  id INT64 NOT NULL, code STRING NOT NULL, name STRING, block STRING,
  district_code STRING NOT NULL, state_code STRING NOT NULL,
  lat FLOAT64, lon FLOAT64, beds_total INT64, staff_sanctioned INT64, is_24x7 BOOL,
  language STRING, supply_anchor DATE,
  nin STRING OPTIONS(description = 'HMIS National Identification Number of the facility')
);

CREATE TABLE IF NOT EXISTS phc_pulse.stock_daily (
  phc_id INT64 NOT NULL, state_code STRING NOT NULL, drug_code STRING NOT NULL, day DATE NOT NULL,
  opening FLOAT64, received FLOAT64, dispensed FLOAT64, unmet FLOAT64, adjustment FLOAT64,
  closing FLOAT64, source STRING
)
PARTITION BY day
CLUSTER BY state_code, phc_id, drug_code;

CREATE TABLE IF NOT EXISTS phc_pulse.footfall_daily (
  phc_id INT64 NOT NULL, state_code STRING NOT NULL, day DATE NOT NULL,
  opd INT64, fever INT64, diarrhoea INT64, respiratory INT64,
  beds_occupied INT64, staff_present INT64, source STRING
)
PARTITION BY day
CLUSTER BY state_code, phc_id;

CREATE TABLE IF NOT EXISTS phc_pulse.reports (
  id INT64, phc_id INT64, state_code STRING, created_at TIMESTAMP, channel STRING,
  language STRING, transcript STRING, parsed_json JSON, confirmation STRING,
  reporter STRING, engine STRING
);

CREATE TABLE IF NOT EXISTS phc_pulse.transfers (
  id INT64, code STRING, from_phc INT64, to_phc INT64, from_state STRING, to_state STRING,
  lines_json JSON, distance_km FLOAT64, cost_inr FLOAT64, eta_hours FLOAT64, status STRING,
  reason STRING, created_at TIMESTAMP, updated_at TIMESTAMP, approved_by STRING, history_json JSON
);

-- Row-level security: each state's health department sees only its own facilities.
-- (Create one policy per state group; the national group sees everything.)
CREATE OR REPLACE ROW ACCESS POLICY state_tn ON phc_pulse.stock_daily
  GRANT TO ('group:tn-health-officers@example.gov.in') FILTER USING (state_code = 'TN');
CREATE OR REPLACE ROW ACCESS POLICY national ON phc_pulse.stock_daily
  GRANT TO ('group:mohfw-command-centre@example.gov.in') FILTER USING (TRUE);
CREATE OR REPLACE ROW ACCESS POLICY state_tn ON phc_pulse.footfall_daily
  GRANT TO ('group:tn-health-officers@example.gov.in') FILTER USING (state_code = 'TN');
CREATE OR REPLACE ROW ACCESS POLICY national ON phc_pulse.footfall_daily
  GRANT TO ('group:mohfw-command-centre@example.gov.in') FILTER USING (TRUE);
