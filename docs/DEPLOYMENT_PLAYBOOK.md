# PHC Pulse: deployment playbook

How a state health department (or the ministry) can pilot PHC Pulse in weeks, what it connects
to, what it costs to run, and how data is protected. Figures marked *estimate* are planning
assumptions; confirm prices in the Google Cloud pricing calculator before budgeting.

## 1. Pilot plan (6 weeks, one state, ~100 PHCs in 2 districts)

| Week | What happens | Who |
|---|---|---|
| 0 | Sign-off; pick 2 districts; nominate a state nodal officer and 2 DHOs | State NHM |
| 1 | Deploy to the state's Google Cloud project (`scripts/deploy.sh`, region `asia-south1`); load the facility list (HMIS NIN, coordinates, beds, sanctioned staff) and the last 6 months of HMIS stock and OPD data | State IT + PHC Pulse team |
| 1 | Import the DHIS2 data elements once (`GET /api/dhis2/metadata`) | HMIS team |
| 2 | Train MOs, pharmacists and ANMs: 45 minutes per block, using the in-app guided tour (Help → Take the guided tour) in their language | DHO + block trainers |
| 2–5 | Daily reports by voice / USSD / SMS / IVR; DHOs approve transfers; weekly review call | PHCs, DHOs |
| 3 | Run the emergency simulator for the season's main risk (flood, heatwave, dengue) and pre-position stock | DHO, state logistics |
| 6 | Evaluate: reporting compliance, stock-out days vs the same weeks last year, transfer lead time, time to file a report (target < 60 s) | State NHM |

Scale-up after the pilot is configuration, not development: add districts to the facility list;
the optimiser and federated training already run per state.

## 2. Integrations

| System | How | Status in the prototype |
|---|---|---|
| **HMIS (DHIS2)** | Monthly facility report as a DHIS2 `dataValueSets` payload: `GET /api/dhis2/dataValueSets?month=YYYY-MM`, then `POST` to `<dhis2>/api/dataValueSets?dataElementIdScheme=CODE&orgUnitIdScheme=CODE`. Org units are identified by HMIS NIN. | Working export + metadata |
| HMIS CSV | `GET /api/hmis/export.csv` (flat facility × item layout) | Working |
| State drug inventory (e-Aushadhi / DVDMS) | Daily stock and receipt feed mapped to `stock_daily` (receipts, issues, closing balance per facility × drug) | Adapter to build per state (table shapes in `bigquery/schema.sql`) |
| IDSP / IHIP | Gemini-drafted outbreak alert (English + local language) for the district surveillance officer | Draft generated; submission stays manual |
| Telecom | USSD gateway (Africa's Talking-style protocol), SMS shortcode, Dialogflow CX IVR webhook | Working endpoints |

DHIS2 also runs the national health information systems of 80+ countries, including several BRICS
members, so the same export works outside India without a custom connector. Language packs are
plain dictionaries (`frontend/src/i18n/*.js`).

## 3. Architecture for a state

* **Cloud Run** (one service) for the API and dashboard; `MIN_INSTANCES=1` so officers never wait for a cold start.
* **BigQuery** as the warehouse (`bigquery/schema.sql`, row access policies per district), partitioned by day.
* **Gemini** through Vertex AI in `asia-south1` using the service account, so no API keys in the app.
* **Vertex AI / BigQuery ML** for the national forecasting model (`vertex/`, `bigquery/forecast.sql`); the in-process forecaster stays as the fallback.
* **Federated modelling:** each state trains on its own data; only the model update (85 numbers per state: smoothing settings, weekday patterns, demand per 100 OPD) goes to the national prior. See Models → *Shared forecasting across states*.

National-scale benchmark (`scripts/scale_benchmark.py`): 24,937 PHCs in 36 states/UTs (249,370
forecast series) run the full pipeline in about 33 s on one machine; the largest state (UP) takes
about 8 s, so with one worker per state the country refreshes in under 10 s.

## 4. Running cost per state (*estimate*)

Assumptions: 1,500 PHCs, one voice report per PHC per day, 50 officers using briefings and Ask Pulse.

| Item | Basis | Monthly |
|---|---|---|
| Cloud Run | 1–2 always-on instances (2 vCPU, 4 GiB) | ₹8,000–15,000 |
| BigQuery | < 50 GB stored; daily queries well inside on-demand pricing | ₹1,000–3,000 |
| Gemini voice reports | 45,000 reports × ~40 s audio + prompt ≈ 2–3k tokens each on a Flash model | ₹10,000–25,000 |
| Gemini briefings, Ask Pulse, plans, read-aloud | ~3,000 requests | ₹2,000–6,000 |
| SMS / USSD / IVR | depends on the telecom contract; free for workers | contract |
| **Total (cloud)** | | **≈ ₹21,000–49,000 per month** |

For comparison, the prototype's impact estimate for 120 PHCs is ₹1.3 lakh net saving per supply
cycle from transfers alone (Models → *Impact of today's plan*), before counting stock-out days
avoided.

## 5. Security, privacy and the DPDP Act, 2023

* **No patient-level data.** Reports carry counts (OPD, syndromes, beds, staff) and stock, never names, phone numbers of patients or diagnoses of individuals.
* **Data stays in India:** deploy in `asia-south1` (Mumbai) or `asia-south2` (Delhi); Gemini via Vertex AI in the same region.
* **Least privilege:** every API filters rows by the officer's jurisdiction; a DHO can only release stock from PHCs in their own district (donor-side approval); tokens expire after 12 hours.
* **Human in the loop:** the AI proposes (transfers, alerts, plans); an officer confirms every action. The emergency simulator never changes stored data.
* **Audit:** every report records channel, language, engine and reporter; every transfer keeps its status history.
* Production hardening checklist: `SECURITY.md`.

## 6. Support model

* Guided tour and full UI in 17 languages (5 more partially), so training material is the app itself.
* Feature phones: USSD / SMS / IVR, so no smartphone is needed at the PHC.
* Offline resilience: SMS and IVR work without mobile data; the web app installs on a phone.
