# ATM Predictive Maintenance — RUL Dashboard

A FastAPI application that displays Remaining-Useful-Life (RUL) predictions
for a fleet of ATMs. Each ATM has 5 components (`component_1` .. `component_5`),
each predicted independently by its own model.

## How it works

There are two ways a prediction run is triggered:

1. **Automatic** — an in-process scheduler (APScheduler) fires the pipeline
   every day at midnight (configurable via `DAILY_RUN_HOUR` / `DAILY_RUN_MINUTE`).
2. **Manual** — clicking **"Run prediction now"** on the dashboard calls
   `POST /api/predictions/run`, which runs the exact same pipeline and
   returns the fresh result.

Both paths call the single pipeline function in `app/pipeline.py`:

```
Oracle monetary server (last 30 days, grouped by PID)
      │
      ▼
sequence-building service        1 batched call for the whole fleet
      │                          → 5 sequences per ATM (one per component)
      ▼
inference service                 1 call PER ATM
      │                          → 5 component predictions nested in one response
      ▼
risk-level thresholding + overall-risk / weakest-component rollup
      │
      ▼
in-memory store  →  dashboard (Jinja2 + vanilla JS, polls /api/predictions/latest)
```

### What this app owns vs. what's external

- **Owned / implemented here:** the Oracle fetch-and-group-by-PID logic
  (`app/database.py`), the HTTP clients that shape and send that data to the
  sequence-building and inference services (`app/services/`), the risk-level
  rule (`app/risk.py`), the orchestration (`app/pipeline.py`), the
  scheduler, the API, and the dashboard.
- **Explicitly out of scope (per requirements):** the internal logic of the
  sequence-building service and the inference service (the 10 actual
  models: 5 sequence-builders + 5 RUL models). They are treated as
  black-box HTTP APIs. `app/services/sequence_builder.py` and
  `app/services/inference.py` document the request/response contract each
  is expected to follow. `external_services_skeletons/` contains
  function-level skeletons (signatures + docstrings, no logic) for whoever
  implements those two services, matching those contracts exactly.

## Data source

Pulled from the monetary server (Oracle) — not event/journal logs. Columns:

```
PID, QUERY_DATE, VERSION, INSTITUTION,
NBRE_CAS_1, NBRE_CAS_2, NBRE3, NBRE_CAS_4,
CMD_CAS_1, CMD_CAS_2, CMD_CAS_3, CMD_CAS_4,
RECE_PRINT
```

- Snapshots arrive roughly every 15 minutes per ATM. The 15-minute cadence
  is **not** used as a filter or downsample key — every row in the 30-day
  lookback window is fetched as-is.
- `CMD_CAS_1..4` and `RECE_PRINT` are nullable; the rest are plain integers.
- `VERSION` / `INSTITUTION` are usually static per ATM but can drift, so
  they're kept per-row rather than hoisted to the PID-group level.
- Query only filters on `QUERY_DATE >= window_start`; grouping by PID
  happens in Python, with rows pre-sorted by `ORDER BY PID, QUERY_DATE`.
- The table name comes from `.env` (`ORACLE_SOURCE_TABLE`) — nothing is
  hardcoded.

## Risk logic (`app/risk.py`)

For each component, if the inference service returned a numeric
`predicted_rul_days`, that value determines the risk level — overriding
whatever `risk_level` the service also sent:

| `predicted_rul_days` | Risk level |
| --- | --- |
| ≤ 7 | critical |
| ≤ 14 | warning |
| > 14 | healthy |

If `predicted_rul_days` is null, there's nothing to threshold, so the
service's own `risk_level` is used as a fallback (or `unknown` if absent).

An ATM's **overall risk** is the most severe of its 5 components. Its
**weakest component** is whichever one is driving that overall risk (ties
broken by lowest RUL) — shown directly in the fleet table so you don't have
to expand a row just to see what's wrong.

## Project layout

```
app/
  main.py            FastAPI app, routes, startup/shutdown (scheduler + Oracle pool)
  config.py          All settings, loaded from environment variables / .env
  constants.py        COMPONENT_IDS (component_1..component_5)
  database.py        Oracle connection pool + fetch-last-month-grouped-by-PID query
  models.py          Shared pydantic schemas (MonetaryLogRecord, AtmPrediction, ...)
  risk.py            Day-threshold rule + overall-risk / weakest-component rollup
  pipeline.py         Orchestrates fetch -> sequence-build -> per-ATM infer -> risk -> store
  scheduler.py        APScheduler cron job (daily midnight run)
  store.py            In-memory latest-run / history store
  routers/
    predictions.py    POST /api/predictions/run, GET /latest, GET /history
  services/
    sequence_builder.py   HTTP client: 1 batched call, 5 sequences per ATM back
    inference.py           HTTP client: 1 call per ATM, 5 component predictions back
external_services_skeletons/
  sequence_building_service_skeleton.py   Function-level contract for that service
  inference_service_skeleton.py            Function-level contract for that service
templates/
  index.html          Dashboard page (expandable per-ATM rows)
static/
  css/style.css        Chrome in bronze/black/grey/white; risk indicators in
                         a green (healthy) → yellow (warning) → red (critical) scale
  js/app.js             Fetches latest run, renders expandable rows, wires up "Run now"
  img/logo.jpeg         Provided brand logo
```

## Running locally

```bash
python -m venv .venv
.venv\Scripts\activate.bat
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env
# macOS/Linux: cp .env.example .env
uvicorn app.main:app --reload --reload-dir app --reload-dir templates --reload-dir static
```

Visit `http://localhost:8000`. Fill in real Oracle credentials and service
URLs in `.env` before expecting a successful run — with placeholders,
clicking "Run prediction now" will fail at whichever step isn't reachable,
and the dashboard surfaces that error directly rather than failing silently.

## Configuration

All configuration is via environment variables (see `.env.example`):

| Variable | Purpose |
| --- | --- |
| `ORACLE_USER`, `ORACLE_PASSWORD`, `ORACLE_DSN` | Oracle connection (python-oracledb, thin mode) |
| `ORACLE_SOURCE_TABLE` | Monetary-server table/view holding the snapshot rows |
| `LOOKBACK_DAYS` | Rolling window fetched on every run (default 30) |
| `SEQUENCE_BUILDER_URL` | Endpoint of the sequence-building service |
| `INFERENCE_SERVICE_URL` | Endpoint of the inference service |
| `RUL_CRITICAL_THRESHOLD_DAYS` / `RUL_WARNING_THRESHOLD_DAYS` | Day thresholds for risk levels (default 7 / 14) |
| `DAILY_RUN_HOUR` / `DAILY_RUN_MINUTE` | Time of the automatic daily run |

**Adjusting to the real sequence-building / inference services:** once those
services exist, confirm their actual request/response shape and update the
payload construction and response parsing in `app/services/sequence_builder.py`
and `app/services/inference.py` accordingly — the rest of the app
(pipeline, risk rollup, store, dashboard) does not need to change as long
as the shape stays the same.

## API

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/` | GET | Dashboard |
| `/api/predictions/run` | POST | Trigger a prediction run now |
| `/api/predictions/latest` | GET | Latest run (used by the dashboard on load) |
| `/api/predictions/history` | GET | Last 20 runs |
| `/healthz` | GET | Liveness check |
