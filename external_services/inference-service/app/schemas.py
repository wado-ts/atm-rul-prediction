"""
Request/response schemas for the inference service.

These mirror exactly what the main ATM predictive-maintenance app sends
from app/services/inference.py and expects back. This service has no
dependency on that app's codebase - the schemas are redefined here so this
service can be developed, tested, and deployed completely independently.

Unlike the sequence-building service (batched for the whole fleet), this
service is called ONCE PER ATM.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ComponentSequenceIn(BaseModel):
    """One component's sequence for one ATM, as produced by the
    sequence-building service."""

    component_id: str
    sequence: Any = Field(..., description="Model-ready sequence for this component")


class AtmInferenceRequest(BaseModel):
    """POST /predict-rul request body - one call per ATM."""

    pid: str
    component_sequences: list[ComponentSequenceIn]


class ComponentPredictionOut(BaseModel):
    """One component's RUL prediction.

    risk_level here is only a fallback - the main app overrides it with a
    day-threshold rule whenever predicted_rul_days is present, so it's
    fine to return "unknown" if a model doesn't produce its own category.
    """

    component_id: str
    predicted_rul_days: float | None = None
    risk_level: str = "unknown"
    confidence: float | None = None
    confidence_entropy: float | None = None
    model_version: str | None = None


class AtmInferenceResponse(BaseModel):
    """POST /predict-rul response body - all 5 component predictions for
    the one ATM that was requested."""

    pid: str
    components: list[ComponentPredictionOut]
