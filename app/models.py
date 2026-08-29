"""
Shared data contracts used between the pipeline stages
(Oracle fetch -> sequence-building service -> inference service -> frontend).
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class MonetaryLogRecord(BaseModel):
    """One row pulled from the monetary server, before sequencing.

    Snapshots arrive roughly every 15 minutes per ATM; every row in the
    lookback window is kept (no downsampling).
    """

    pid: str = Field(..., description="ATM identifier")
    query_date: datetime
    version: str | None = None
    institution: str | None = None
    nbre_cas_1: int
    nbre_cas_2: int
    nbre3: int
    nbre_cas_4: int
    cmd_cas_1: int | None = None
    cmd_cas_2: int | None = None
    cmd_cas_3: int | None = None
    cmd_cas_4: int | None = None
    rece_print: int | None = None


class PidLogGroup(BaseModel):
    """All of a single ATM's monetary-server rows for the lookback window,
    ready to hand to the sequence-building service."""

    pid: str
    records: list[MonetaryLogRecord]


class RiskLevel(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    HEALTHY = "healthy"
    UNKNOWN = "unknown"


# Severity ordering used to pick an ATM's "weakest" component and its
# overall risk level (the worst of its 5 components). Higher = more severe.
RISK_SEVERITY: dict[RiskLevel, int] = {
    RiskLevel.CRITICAL: 3,
    RiskLevel.WARNING: 2,
    RiskLevel.HEALTHY: 1,
    RiskLevel.UNKNOWN: 0,
}


class ComponentPrediction(BaseModel):
    """One component's RUL prediction for one ATM, as returned by the
    inference service (before/after risk-level thresholding is applied)."""

    component_id: str
    predicted_rul_days: float | None = Field(
        None, description="Estimated remaining useful life for this component, in days"
    )
    risk_level: RiskLevel = RiskLevel.UNKNOWN
    confidence: float | None = Field(None, description="Model confidence/score, 0-1")
    model_version: str | None = None


class AtmPrediction(BaseModel):
    """One ATM's full prediction result: all 5 components plus derived
    overall risk, as shown on the dashboard."""

    pid: str
    last_query_date: datetime | None = None
    components: list[ComponentPrediction] = Field(default_factory=list)
    overall_risk: RiskLevel = RiskLevel.UNKNOWN
    weakest_component_id: str | None = None
    weakest_component_rul_days: float | None = None


class FleetPredictionResult(BaseModel):
    """The full response of one prediction run, as displayed on the dashboard."""

    run_id: str
    triggered_by: str  # "scheduler" | "manual"
    started_at: datetime
    completed_at: datetime | None = None
    status: str = "pending"  # pending | success | failed
    error_message: str | None = None
    fleet_size: int = 0
    predictions: list[AtmPrediction] = Field(default_factory=list)


class RunPipelineRequest(BaseModel):
    triggered_by: str = "manual"
