from __future__ import annotations

from fastapi import APIRouter, Query, Depends
from typing import Any

from app.models import (
    FleetPredictionResult, 
    RunPipelineRequest,
    PaginatedPredictionsResponse,
    ActiveFilters,
    Institution,
    AtmPrediction,
    RiskLevel
)
from app.pipeline import run_pipeline
from app.store import prediction_store
from app.auth import get_current_user
from app.auth_db import User, get_institutions as get_all_institutions
from app.config import get_settings

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.post("/run", response_model=FleetPredictionResult)
async def trigger_prediction_run(
    payload: RunPipelineRequest,
    current_user: User = Depends(get_current_user)
) -> FleetPredictionResult:
    """Manually trigger the fetch -> sequence-build -> inference pipeline.

    This is the same code path the midnight scheduler uses; the only
    difference is `triggered_by` for display/audit purposes.
    """
    return await run_pipeline(triggered_by=payload.triggered_by)


@router.get("/latest", response_model=PaginatedPredictionsResponse)
async def get_latest_prediction(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    institution_code: str | None = Query(None),
    risk_level: RiskLevel | None = Query(None),
    search: str | None = Query(None, max_length=100),
    current_user: User = Depends(get_current_user),
) -> PaginatedPredictionsResponse:
    """Get the latest prediction run with filtering and pagination."""
    settings = get_settings()
    
    current_run = prediction_store.get_current_run()
    if not current_run:
        return PaginatedPredictionsResponse(
            predictions=[],
            total=0,
            page=1,
            page_size=page_size,
            total_pages=0,
            institutions=[],
            risk_levels=list(RiskLevel),
            active_filters=ActiveFilters(
                institution_code=institution_code,
                risk_level=risk_level,
                search=search,
                page=page,
                page_size=page_size
            )
        )


    # Get all predictions for this run
    predictions = current_run.predictions
    
    # Apply user-based institution filtering
    # If user has an institution_code and it's not the global '0', filter to their institution
    if current_user.institution_code and current_user.institution_code != '0':
        predictions = [p for p in predictions if p.institution_code == current_user.institution_code]
    
    # Calculate overall statistics from all predictions (before filtering)
    fleet_size = len(predictions)
    critical_count = sum(1 for p in predictions if p.overall_risk == RiskLevel.CRITICAL)
    warning_count = sum(1 for p in predictions if p.overall_risk == RiskLevel.WARNING)
    healthy_count = sum(1 for p in predictions if p.overall_risk == RiskLevel.HEALTHY)
    
    # Apply institution filter (only allow filtering within user's accessible institutions)
    if institution_code:
        # If user has a specific institution, only allow filtering that institution
        if current_user.institution_code and current_user.institution_code != '0':
            if institution_code != current_user.institution_code:
                institution_code = None  # Ignore invalid institution filter
        predictions = [p for p in predictions if p.institution_code == institution_code]
    
    # Apply risk level filter
    if risk_level:
        predictions = [p for p in predictions if p.overall_risk == risk_level]
    
    # Apply search filter (searches address and PID)
    if search:
        search_lower = search.lower()
        predictions = [
            p for p in predictions 
            if search_lower in (p.address or "").lower() or search_lower in p.pid.lower()
        ]
    
    # Get unique institutions from current run for filter dropdown
    institutions = []
    seen_codes = set()
    for p in current_run.predictions:
        if p.institution_code and p.institution_code not in seen_codes:
            seen_codes.add(p.institution_code)
            institutions.append(Institution(
                code=p.institution_code,
                name=p.institution_name or p.institution_code,
                is_global=(p.institution_code == '0')
            ))
    
    # Sort institutions: INTELLIGENTSIA (code '0') first, then alphabetical
    institutions.sort(key=lambda i: (i.code != '0', i.name))
    
    # Pagination
    total = len(predictions)
    total_pages = (total + page_size - 1) // page_size
    start = (page - 1) * page_size
    end = start + page_size
    paginated = predictions[start:end]
    
    # Build active filters response
    active_filters = ActiveFilters(
        institution_code=institution_code,
        risk_level=risk_level,
        search=search,
        page=page,
        page_size=page_size
    )
    
    # Get all institutions for dropdown (including those not in current run)
    all_institutions = get_all_institutions()
    # Filter institutions based on user's access
    if current_user.institution_code and current_user.institution_code != '0':
        all_institutions = [inst for inst in all_institutions if inst.code == current_user.institution_code]
    
    # Convert auth_db Institution dataclass to models Institution Pydantic model
    all_institutions_models = [
        Institution(code=inst.code, name=inst.name, is_global=inst.is_global)
        for inst in all_institutions
    ]
    
    return PaginatedPredictionsResponse(
        predictions=paginated,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        institutions=all_institutions_models,
        risk_levels=list(RiskLevel),
        fleet_size=fleet_size,
        critical_count=critical_count,
        warning_count=warning_count,
        healthy_count=healthy_count,
        active_filters=ActiveFilters(
            institution_code=institution_code,
            risk_level=risk_level,
            search=search,
            page=page,
            page_size=page_size
        )
    )


@router.get("/institutions", response_model=list[Institution])
async def list_institutions(current_user: User = Depends(get_current_user)) -> list[Institution]:
    """Get all institutions for filter dropdown."""
    return get_all_institutions()


@router.get("/history", response_model=list[FleetPredictionResult])
async def get_prediction_history(current_user: User = Depends(get_current_user)) -> list[FleetPredictionResult]:
    return prediction_store.get_history()