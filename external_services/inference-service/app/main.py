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

from app.components import component_1, component_2, component_3, component_4, component_5
from app.config import get_settings
from app.model_registry import load_all_models
from app.schemas import AtmInferenceRequest, AtmInferenceResponse, ComponentPredictionOut

# component_id -> that component's predict(sequence) function
_DISPATCH = {
    "component_1": component_1.predict,
    "component_2": component_2.predict,
    "component_3": component_3.predict,
    "component_4": component_4.predict,
    "component_5": component_5.predict,
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
