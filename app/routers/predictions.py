from __future__ import annotations

from fastapi import APIRouter

from app.models import FleetPredictionResult, RunPipelineRequest
from app.pipeline import run_pipeline
from app.store import prediction_store

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


@router.post("/run", response_model=FleetPredictionResult)
async def trigger_prediction_run(payload: RunPipelineRequest) -> FleetPredictionResult:
    """Manually trigger the fetch -> sequence-build -> inference pipeline.

    This is the same code path the midnight scheduler uses; the only
    difference is `triggered_by` for display/audit purposes.
    """
    return await run_pipeline(triggered_by=payload.triggered_by)


@router.get("/latest", response_model=FleetPredictionResult | None)
async def get_latest_prediction() -> FleetPredictionResult | None:
    return prediction_store.get_current_run()


@router.get("/history", response_model=list[FleetPredictionResult])
async def get_prediction_history() -> list[FleetPredictionResult]:
    return prediction_store.get_history()
