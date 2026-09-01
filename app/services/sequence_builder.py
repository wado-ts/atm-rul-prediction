"""
Client for the sequence-building service.

This service's own implementation is out of scope here (see
external_services_skeletons/sequence_building_service_skeleton.py for the
function-level contract it needs to satisfy) - it is treated as an external
HTTP dependency. This module's only job is to shape the Oracle-sourced,
PID-grouped monetary-server rows into the request payload the service
expects, call it once for the whole fleet, and parse the sequences it hands
back.

Each ATM has 5 components (CMD_CAS_1..CMD_CAS_4, RECE_PRINT), each needing its own
sequence for its own model - so the service returns 5 sequences per PID,
not 1.

Expected contract:
    POST {sequence_builder_url}
    body: {
        "lookback_days": int,
        "pid_groups": [{"pid": str, "records": [...]}]
    }
    response: {
        "fleet_sequences": [
            {
                "pid": str,
                "components": [
                    {"component_id": "CMD_CAS_1", "sequence": [...]},
                    {"component_id": "CMD_CAS_2", "sequence": [...]},
                    {"component_id": "CMD_CAS_3", "sequence": [...]},
                    {"component_id": "CMD_CAS_4", "sequence": [...]},
                    {"component_id": "RECE_PRINT", "sequence": [...]}
                ]
            },
            ...
        ]
    }
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.models import PidLogGroup

logger = logging.getLogger(__name__)

# Number of ATMs to send per request to the sequence-building service.
# This prevents MemoryError from large payloads.
CHUNK_SIZE = 10


async def build_sequences(pid_groups: list[PidLogGroup]) -> dict[str, list[dict[str, Any]]]:
    """Send the last-month, PID-grouped monetary-server rows to the
    sequence-building service (in chunks to avoid memory issues) and
    return, per PID, the 5 component sequences it responds with.

    Returns: {pid: [{"component_id": "CMD_CAS_1", "sequence": [...]}, ...]}
    """
    settings = get_settings()

    async def _call_sequence_builder(chunk: list[PidLogGroup]) -> dict[str, list[dict[str, Any]]]:
        payload = {
            "lookback_days": settings.lookback_days,
            "pid_groups": [group.model_dump(mode="json") for group in chunk],
        }
        async with httpx.AsyncClient(timeout=settings.sequence_builder_timeout_seconds) as client:
            logger.info(
                "Calling sequence-building service with %d ATM(s) of monetary-server data",
                len(chunk),
            )
            response = await client.post(settings.sequence_builder_url, json=payload)
            response.raise_for_status()
            body = response.json()

        fleet_sequences = body.get("fleet_sequences", [])
        return {entry["pid"]: entry.get("components", []) for entry in fleet_sequences}

    # Process in chunks to avoid MemoryError on large payloads
    all_results: dict[str, list[dict[str, Any]]] = {}
    for i in range(0, len(pid_groups), CHUNK_SIZE):
        chunk = pid_groups[i : i + CHUNK_SIZE]
        chunk_result = await _call_sequence_builder(chunk)
        all_results.update(chunk_result)

    logger.info(
        "Sequence-building service returned sequences for %d ATM(s) (in %d chunks)",
        len(all_results),
        (len(pid_groups) + CHUNK_SIZE - 1) // CHUNK_SIZE,
    )
    return all_results
