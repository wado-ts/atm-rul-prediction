# Inference Service

Runs each ATM's 5 component-specific RUL models and returns all 5
predictions nested in one response. Called ONCE PER ATM by the main ATM
predictive-maintenance app (not batched for the fleet).

## Contract

```
POST /predict-rul
```

Request body:

```json
{
  "pid": "ATM-004",
  "component_sequences": [
    {"component_id": "component_1", "sequence": {}},
    {"component_id": "component_2", "sequence": {}},
    {"component_id": "component_3", "sequence": {}},
    {"component_id": "component_4", "sequence": {}},
    {"component_id": "component_5", "sequence": {}}
  ]
}
```

Response body:

```json
{
  "pid": "ATM-004",
  "components": [
    {
      "component_id": "component_1",
      "predicted_rul_days": 18.2,
      "risk_level": "healthy",
      "confidence": 0.91,
      "model_version": "coxph_v1"
    }
  ]
}
```

`risk_level` here is only a fallback - the main app overrides it with a
day-threshold rule (≤7 critical, ≤14 warning, >14 healthy) whenever
`predicted_rul_days` is present. This exactly matches what the main app's
`app/services/inference.py` sends and parses - no changes needed on that
side as long as this shape holds.

## What's implemented vs. what isn't

- `app/main.py`, `app/schemas.py`, `app/config.py`, `app/model_registry.py`
  are fully functional: routing, validation, per-ATM dispatch to the 5
  component predictors, and loading trained model artifacts from disk at
  startup all work out of the box.
- `app/components/component_1.py` .. `component_5.py` are skeletons -
  each raises `NotImplementedError`. Implement the actual model inference
  logic for each component there (using `get_model("component_N")` to
  retrieve the artifact `model_registry.py` already loaded). The docstring
  in each file specifies its exact input and output shape.
- `trained_models/` is where each component's serialized model file goes
  (see `.env.example` for the expected filenames) - none are included
  here since no models have been trained yet. Until a component's model
  file exists, `get_model()` returns `None` and a warning is logged at
  startup; that component's `predict()` needs to handle that case
  explicitly once implemented.

## Running locally

```bash
python -m venv .venv
.venv/bin/activate   # .venv\Scripts\activate.bat on Windows
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 9002
```

Point the main app's `INFERENCE_SERVICE_URL` at
`http://localhost:9002/predict-rul` once the component predictors are
implemented and their model files are in place.
