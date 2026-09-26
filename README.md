# PHC Pulse: a heartbeat for every health centre in India

**Build with AI: Code for Communities (Second Edition) · Problem Statement 03: Smart Health & Supply Chain Resilience**

> **In brief (submission description):** PHC Pulse gives every Primary Health Centre a
> one-minute daily report by voice (in the worker's own language), USSD, SMS or IVR. Gemini turns
> it into structured data. Per-PHC, per-drug forecasts then flag stock-outs 2+ weeks ahead,
> outbreak footfall spikes are detected automatically, and a MILP optimiser recommends which PHC
> should ship what to whom, with one-tap approval and delivery tracking.

---

## What works end to end

| Deck promise | Where it is in the prototype |
|---|---|
| **Voice-first reporting, < 60 s, own language** | `Voice report` page. Record up to 60 s; **Gemini** (multimodal audio) returns transcript + English translation + validated structured report, reads the numbers back in the worker's language, and asks a follow-up question for anything missing. English + all 22 scheduled Indian languages (UI, read-back, IVR phrases); Kashmiri, Sindhi, Bodo, Santali and Manipuri UI text is partial and falls back to English. |
| **Feature phones: USSD / SMS / IVR** | `USSD · SMS · IVR` page: working `*123#` USSD menu (Africa's Talking-style gateway protocol), SMS shortcode grammar (`PCM 120 ORS 40 BED 4`), and a **Dialogflow CX** webhook for IVR calls. |
| **Demand forecasting, stock-outs flagged 2-3 weeks ahead** | Damped Holt-Winters per PHC × drug (1,200 series, vectorised). A warning fires when projected stock hits zero *before the next scheduled indent*. **Walk-forward backtest: 81% of real stock-outs flagged ≥ 14 days ahead** (67% precision, 79% weekly accuracy). Shown on `Models & HMIS`. |
| **Redistribution recommender under transport-cost constraints** | Mixed-integer program (HiGHS): trip cost (fixed + ₹/km + inter-state paperwork), urgency- and criticality-weighted shortage penalty, donor safety stock, **multi-drug consolidation per lane**. Produces the deck's own example: *"PHC-14 has surplus paracetamol; PHC-22 needs it in 9 days."* |
| **One-tap approval → delivery tracking** | `Redistribution` page: Approve → Dispatch → Delivered. Stock moves out of the donor's ledger and into the recipient's, and forecasts recompute instantly. |
| **Outbreak anomaly detection** | Weekday-adjusted robust z-scores on fever / diarrhoea / respiratory footfall; ≥ 2 PHCs within 50 km → cluster. Detects the seeded Koraput diarrhoea and Gorakhpur fever clusters. **Gemini drafts the IDSP alert** in English + the local language. Linked drugs (ORS/zinc, paracetamol/ACT) get outbreak-adjusted forecasts. |
| **District / State / National dashboards** | `Command centre` with map, KPIs, resilience scores, district roll-up, **Gemini daily briefing** in any of the 23 languages and an **Ask Pulse** copilot grounded in the live snapshot. |
| **Row-level access by jurisdiction** | Signed role tokens: national, state, district (DHO) and PHC personas. Every API filters rows by scope and a DHO cannot widen it (mirrors BigQuery row access policies in `bigquery/schema.sql`). Only the donor side (its DHO, state or national) can release stock; tokens expire after a 12-hour shift. |
| **Health-emergency simulator** | `Emergency simulator` page: pick a flood, cyclone, dengue/malaria, cholera or heatwave scenario, districts and severity. The engine re-runs forecasts and the MILP on the what-if demand and shows new stock-out risks (life-saving drugs first), bed pressure, transfers to make in advance and emergency indents; **Gemini writes a 48-hour action plan** in any of 23 languages. Nothing is saved. |
| **Shared predictive modelling across states (federated)** | Each state tunes its own forecaster on its own data; only 85 numbers per state (settings, weekday patterns, demand per 100 OPD) are pooled with **FedAvg** into a national prior. Leave-one-state-out test: a newly onboarded state with 7 days of history forecasts at **65% vs 56%** accuracy with the shared prior; a PHC with no history at all gets 64% from its OPD alone. Raw rows shared: 0. |
| **Ask Pulse agent (Gemini function calling)** | Gemini calls scoped tools (stock, surplus nearby, recommended transfers, outbreak signals, emergency simulation, impact) and can **propose** a transfer; the officer confirms with a button and the normal approval rules apply. |
| **Photo of a paper register** | `Voice report` → Photo: Gemini reads a photographed stock register or daily sheet (handwritten, any script) into the same checked report as voice. |
| **Impact** | Stock-out days prevented, patients covered and money saved vs emergency purchase for the current plan, per jurisdiction, with a clearly labelled national projection. |
| **National scale** | `scripts/scale_benchmark.py`: 24,937 PHCs in 36 states/UTs (249,370 series) through forecasting, early warning, outbreak detection and the MILP in ~33 s on one machine; ~8 s for the largest state, so ~10 s nationally with one worker per state. |
| **DHIS2 / HMIS integration** | `GET /api/dhis2/dataValueSets` (DHIS2 import format, org units by HMIS NIN) + `/api/dhis2/metadata`; see [docs/DEPLOYMENT_PLAYBOOK.md](docs/DEPLOYMENT_PLAYBOOK.md) for the pilot plan, costs and DPDP notes. |
| **Easy for first-time users** | `Help` → **Take the guided tour**: an 18-step interactive walkthrough of every page (spotlight on each feature, auto-navigates, keyboard + read-aloud, works on phones and right-to-left scripts), in all fully translated languages. First-time visitors get a one-time invitation. |
| **HMIS-compatible** | Facilities keyed by HMIS NIN; monthly HMIS-style CSV export (OPD, syndromic counts, receipts, consumption, closing balance, stock-out days). |
| **Scales state by state** | Engine decomposes the MILP per state (cross-state lanes are a Phase-3 toggle); BigQuery schema is partitioned by day and clustered by state; BQML / Vertex AI training scripts included. |

## Architecture

```mermaid
flowchart LR
  subgraph Channels
    V[Web voice note<br/>any Indian language] --> G
    U[USSD *123#] --> API
    S[SMS shortcode] --> API
    I[IVR call<br/>Dialogflow CX] -->|webhook| API
  end
  G[Gemini<br/>audio → structured JSON<br/>+ local-language read-back] --> API
  API[FastAPI on Cloud Run] --> W[(Warehouse<br/>SQLite → BigQuery)]
  W --> F[Forecast<br/>Holt-Winters ×1200 series<br/>→ Vertex AI / BQML]
  W --> A[Anomaly + cluster<br/>detection]
  A -->|surge factor| F
  F --> O[MILP redistribution<br/>HiGHS]
  O --> D[Dashboards<br/>National · State · District · PHC]
  A --> D
  D --> GB[Gemini briefings,<br/>copilot, IDSP alerts]
```

```
backend/app/
  seed.py            synthetic-but-realistic HMIS-like history (120 PHCs, 8 districts, 4 states, 180 days)
  forecasting.py     vectorised damped Holt-Winters + walk-forward backtest
  anomaly.py         robust weekday-adjusted z-scores + spatial clustering
  redistribution.py  MILP (scipy.optimize.milp / HiGHS) with lane consolidation
  engine.py          loads warehouse → forecasts → early warning → plan → cached read model
  gemini.py          voice/photo report understanding, briefings, emergency plans, alerts, read-aloud (+ fallbacks)
  agent.py           Ask Pulse agent: scoped tools for Gemini function calling
  federated.py       per-state training, FedAvg prior, leave-one-state-out evaluation
  scenarios.py       health-emergency simulator (what-if demand -> forecasts + MILP)
  dhis2.py           DHIS2 dataValueSets export + metadata
  channels.py        USSD state machine, SMS grammar, Dialogflow CX webhook
  service.py         report ingestion into the stock ledger, transfer lifecycle, scoping
  auth.py            signed persona tokens, row-level jurisdiction scoping
  main.py            REST API + serves the React app
frontend/            React + Vite dashboard (Leaflet map, Recharts)
bigquery/            warehouse schema with row access policies; BQML ARIMA_PLUS forecast + anomaly SQL
vertex/              Vertex AI AutoML Forecasting training job
dialogflow/          IVR agent design + webhook contract
scripts/             Cloud Run deploy, BigQuery export
```

## Google AI & Cloud usage

* **Gemini** (`gemini-2.5-flash` by default, set `GEMINI_MODEL` to change it), via AI Studio key or Vertex AI:
  1. **Multimodal voice understanding:** 16 kHz WAV → transcript, translation and a schema-validated `ParsedReport` (response schema, so no free-text parsing). Hallucinated drug codes are dropped server-side. Follow-up answers are merged into the earlier partial report.
  2. **Daily briefing** for the officer's jurisdiction in their language.
  3. **Ask Pulse agent:** function calling over scoped tools; proposes transfers for the officer to confirm.
  4. **IDSP outbreak alert drafting** in English + the local language.
  5. **Emergency action plans** from the simulator, in any of 23 languages.
  6. **Photo understanding:** handwritten stock registers → structured reports.
  7. **Read-aloud (Gemini TTS)** for languages the device has no voice for.
* **Dialogflow CX:** IVR for feature phones (webhook implemented and tested).
* **Cloud Run:** a single container serves API + UI.
* **BigQuery / BigQuery ML / Vertex AI:** warehouse schema, row-level security, ARIMA_PLUS forecasting and anomaly detection, and an AutoML Forecasting training job, all scripted for the production path.

Without Gemini credentials the app still runs end to end: the browser's speech-to-text plus a
multilingual rule parser handle reports, and briefings and alerts use templates. Every AI output
is tagged with the engine that produced it.

## Run locally

```bash
# backend (Python 3.11+)
cd backend
pip install -r requirements-dev.txt
set GEMINI_API_KEY=...          # PowerShell: $env:GEMINI_API_KEY="..."; bash: export GEMINI_API_KEY=...
python -m uvicorn app.main:app --port 8000

# frontend (dev server with hot reload, proxies /api to :8000)
cd frontend
npm install
npm run dev                     # http://localhost:5173
# or: npm run build and open http://localhost:8000 (FastAPI serves frontend/dist)
```

Tests: `cd backend && python -m pytest -q` (105 tests, including the deck
scenario, row-level scoping, the transfer ledger, USSD/SMS/IVR and the Gemini path with a mocked model).

## Deploy to Cloud Run

```bash
GEMINI_API_KEY=... ./scripts/deploy.sh          # key stored in Secret Manager
# or
USE_VERTEX=1 ./scripts/deploy.sh                # Gemini through Vertex AI with the service account
```

Or with Docker: `docker build -t phc-pulse . && docker run -p 8080:8080 -e GEMINI_API_KEY=... phc-pulse`.

The prototype keeps its warehouse in SQLite inside the container, so it runs as one instance
and re-seeds on a cold start (`MIN_INSTANCES=1` keeps demo state alive). Production moves the
store to BigQuery / Firestore; the engine only depends on the table shapes in `bigquery/schema.sql`.

## Demo script (3-5 minute video)

1. **Command centre** (national): 120 PHCs, predicted stock-outs, 2 outbreak clusters on the map. Generate the **AI briefing** and switch it to Hindi.
2. **Outbreak signals:** Koraput diarrhoea cluster (4 PHCs, up to 4.8× expected). Click **Draft IDSP alert**, then show that ORS/zinc forecasts were raised automatically.
3. Switch role to **DHO Tiruvannamalai** (row-level scope): the lane *"PHC-14 has surplus paracetamol; PHC-22 needs it in 9 days"* shows as awaiting the donor side, because PHC-14 is in Villupuram. Switch to **DHO Villupuram** (or **State Health Officer, Tamil Nadu**), then **Approve → Dispatch → Delivered**, and show that stock moved.
4. **Voice report** for PHC-22 in Tamil: speak for about 20 s. Gemini returns the transcript, translation and fields, reads back in Tamil, and asks a follow-up. Submit, and the forecast updates.
5. **USSD · SMS · IVR:** dial `*123#` on the feature phone, then send an SMS report and simulate a Hindi IVR call.
6. **Emergency simulator:** severe flood in Koraput → medicine lines at risk jump from 26 to 53, 23 advance transfers, 56 emergency indents; click **Write the plan** for Gemini's 48-hour plan (switch it to Odia).
7. **Ask Pulse:** "What happens if a flood hits Koraput? What should we move in advance?" Watch the tool chips, then approve a proposed transfer from the chat.
8. **Models & HMIS:** backtest, impact of today's plan with national projection, federated forecasting across states (65% vs 56% for a new state), national-scale benchmark, DHIS2 export.

## Data

All data is **synthetic**, generated to be realistic. PHC OPD volumes match HMIS PHC ranges, the
10 drugs come from India's NLEM, and the simulation includes monsoon seasonality, state
epidemiology (malaria in Odisha, snakebite in TN/KA), monthly indents with uneven supply,
partial and late deliveries, and three injected outbreak signals. District centroids and block
names are real; PHC coordinates are jittered. No patient-level data is stored anywhere.

## Roadmap (from the deck)

1. **Pilot:** 100 PHCs in 2 districts of one state; validate the voice workflow.
2. **State rollout:** connect the state HMIS pipeline; add a language pack.
3. **Cross-state redistribution:** already a toggle in the optimiser.
4. **Resource generalisation:** blood banks, oxygen and ambulances with the same forecast + MILP engine.

## Watch Demo on YouTube

[![Watch the Demo](https://img.youtube.com/vi/OK-mlieQLTc/maxresdefault.jpg)](https://youtu.be/OK-mlieQLTc)

## Credits and open-source components

Built during the hackathon on these open-source projects (licences in brackets):
FastAPI, Pydantic (MIT) · Uvicorn, NumPy, SciPy (BSD-3-Clause) with the **HiGHS** MILP solver (MIT) ·
python-multipart (Apache-2.0) · Google Gen AI SDK `google-genai` (Apache-2.0) · React, React Router,
Recharts (MIT) · Leaflet (BSD-2-Clause) and react-leaflet (Hippocratic 2.1) · map tiles © OpenStreetMap
contributors (ODbL) · Noto fonts via Google Fonts (SIL OFL 1.1). Facility counts: Rural Health
Statistics 2021-22 (MoHFW). Drug list: National List of Essential Medicines.
