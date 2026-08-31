"""
Sequence-building service.

Single endpoint, called once per prediction run by the main ATM
predictive-maintenance app, batched for the whole fleet. For every ATM in
the request it dispatches to all 5 component builders and returns their
5 sequences bundled per PID - the exact shape
app/services/sequence_builder.py in the main app expects back.
"""
from __future__ import annotations

from fastapi import FastAPI
from app.builder import build_sequence

from app.config import get_settings
from app.schemas import (
    AtmSequences,
    ComponentSequence,
    FleetSequenceRequest,
    FleetSequenceResponse,
)

app = FastAPI(title=get_settings().app_name)

COMPONENTS = ["CMD_CAS_1", "CMD_CAS_2", "CMD_CAS_3", "CMD_CAS_4", "RECE_PRINT"]


@app.post("/build-sequences", response_model=FleetSequenceResponse)
def build_sequences(payload: FleetSequenceRequest) -> FleetSequenceResponse:
    fleet_sequences: list[AtmSequences] = []

    for group in payload.pid_groups:
        records = [record.model_dump(mode="json") for record in group.records]

        components = [
            ComponentSequence(
                component_id=component,
                sequence=build_sequence(group.pid, records, component),
            )
            for component in COMPONENTS
        ]

        fleet_sequences.append(AtmSequences(pid=group.pid, components=components))

    return FleetSequenceResponse(fleet_sequences=fleet_sequences)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
