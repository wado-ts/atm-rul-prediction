"""
Request/response schemas for the sequence-building service.

These mirror exactly what the main ATM predictive-maintenance app sends
from app/services/sequence_builder.py and expects back. This service has
no dependency on that app's codebase - the schemas are redefined here so
this service can be developed, tested, and deployed completely
independently.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class MonetaryRecord(BaseModel):
    """One raw monetary-server snapshot row for one ATM (~15-minute cadence)."""

    pid: str
    query_date: datetime
    version: int | str | None = None
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


class PidGroup(BaseModel):
    """All of one ATM's rows for the lookback window."""

    pid: str
    records: list[MonetaryRecord]


class FleetSequenceRequest(BaseModel):
    """POST /build-sequences request body - one batched call for the whole fleet."""

    lookback_days: int
    pid_groups: list[PidGroup]


class ComponentSequence(BaseModel):
    """One component's sequence for one ATM. `sequence` shape is owned by
    this service together with that component's downstream inference
    model - the main app only passes it through untouched."""

    component_id: str
    sequence: Any = Field(..., description="Model-ready sequence, shape defined by this service")


class AtmSequences(BaseModel):
    """All 5 component sequences for one ATM."""

    pid: str
    components: list[ComponentSequence]


class FleetSequenceResponse(BaseModel):
    """POST /build-sequences response body."""

    fleet_sequences: list[AtmSequences]
