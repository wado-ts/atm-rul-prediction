# Sequence Building Service

Turns raw monetary-server rows into model-ready sequences, one per
component, for every ATM in the fleet. Called once per prediction run by
the main ATM predictive-maintenance app, batched for the whole fleet.

## Contract

```
POST /build-sequences
```

Request body:

```json
{
  "lookback_days": 30,
  "pid_groups": [
    {
      "pid": "ATM-004",
      "records": [
        {
          "pid": "ATM-004",
          "query_date": "2026-08-01T00:15:00",
          "version": "3.2.1",
          "institution": "BANK01",
          "nbre_cas_1": 120,
          "nbre_cas_2": 98,
          "nbre3": 4,
          "nbre_cas_4": 200,
          "cmd_cas_1": 12,
          "cmd_cas_2": null,
          "cmd_cas_3": 3,
          "cmd_cas_4": 0,
          "rece_print": 45
        }
      ]
    }
  ]
}
```

Response body:

```json
{
  "fleet_sequences": [
    {
      "pid": "ATM-004",
      "components": [
        {"component_id": "component_1", "sequence": {}},
        {"component_id": "component_2", "sequence": {}},
        {"component_id": "component_3", "sequence": {}},
        {"component_id": "component_4", "sequence": {}},
        {"component_id": "component_5", "sequence": {}}
      ]
    }
  ]
}
```

This exactly matches what the main app's `app/services/sequence_builder.py`
sends and parses - no changes needed on that side as long as this shape
holds.

## What's implemented vs. what isn't

- `app/main.py`, `app/schemas.py`, `app/config.py` are fully functional:
  routing, validation, and dispatch to the 5 component builders all work
  out of the box.
- `app/components/component_1.py` .. `component_5.py` are skeletons -
  each raises `NotImplementedError`. Implement the actual feature
  engineering / windowing logic for each component there. The docstring
  in each file specifies its exact input and output shape.

## Running locally

```bash
python -m venv .venv
.venv/bin/activate   # .venv\Scripts\activate.bat on Windows
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 9001
```

Point the main app's `SEQUENCE_BUILDER_URL` at
`http://localhost:9001/build-sequences` once the component builders are
implemented.
