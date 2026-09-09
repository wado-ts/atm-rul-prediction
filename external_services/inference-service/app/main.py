"""
Inference service.

Single endpoint, called ONCE PER ATM by the main ATM predictive-maintenance
app (not batched for the fleet, unlike the sequence-building service).
Each call carries one ATM's 5 component sequences; this service dispatches
each to its own component's model and returns all 5 predictions nested in
one response - the exact shape app/services/inference.py in the main app
expects back.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.components import cmd_cas_1, cmd_cas_2, cmd_cas_3, cmd_cas_4, rece_print
from app.config import get_settings
from app.model_registry import get_model_status, is_ready, load_all_models
from app.schemas import AtmInferenceRequest, AtmInferenceResponse, ComponentPredictionOut

# component_id -> that component's predict(sequence) function
_DISPATCH = {
    "CMD_CAS_1": cmd_cas_1.predict,
    "CMD_CAS_2": cmd_cas_2.predict,
    "CMD_CAS_3": cmd_cas_3.predict,
    "CMD_CAS_4": cmd_cas_4.predict,
    "RECE_PRINT": rece_print.predict,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_all_models()
    yield


app = FastAPI(title=get_settings().app_name, lifespan=lifespan)


@app.post("/predict-rul", response_model=AtmInferenceResponse)
def predict_rul(payload: AtmInferenceRequest) -> AtmInferenceResponse:
    components: list[ComponentPredictionOut] = []

    for component_seq in payload.component_sequences:
        predictor = _DISPATCH.get(component_seq.component_id)
        if predictor is None:
            continue
        result = predictor(component_seq.sequence)
        components.append(ComponentPredictionOut(component_id=component_seq.component_id, **result))

    return AtmInferenceResponse(pid=payload.pid, components=components)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> JSONResponse:
    status = get_model_status()
    if not is_ready():
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "models": status},
        )
    return JSONResponse(status_code=200, content={"status": "ready", "models": status})
