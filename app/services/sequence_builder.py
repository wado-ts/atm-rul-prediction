"""
Client for the sequence-building service.

This service's own implementation is out of scope here (see
external_services_skeletons/sequence_building_service_skeleton.py for the
function-level contract it needs to satisfy) - it is treated as an external
HTTP dependency. This module's only job is to shape the Oracle-sourced,
PID-grouped monetary-server rows into the request payload the service
expects, call it once for the whole fleet, and parse the sequences it hands
back.

Each ATM has 5 components (component_1..component_5), each needing its own
sequence for its own model - so the service returns 5 sequences per PID,
not 1.

Expected contract (adjust to match the real service once it exists):
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
                    {"component_id": "component_1", "sequence": [...]},
                    {"component_id": "component_2", "sequence": [...]},
                    {"component_id": "component_3", "sequence": [...]},
                    {"component_id": "component_4", "sequence": [...]},
                    {"component_id": "component_5", "sequence": [...]}
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


async def build_sequences(pid_groups: list[PidLogGroup]) -> dict[str, list[dict[str, Any]]]:
    """Send the last-month, PID-grouped monetary-server rows to the
    sequence-building service (one batched call for the whole fleet) and
    return, per PID, the 5 component sequences it responds with.

    Returns: {pid: [{"component_id": "component_1", "sequence": [...]}, ...]}
    """
    settings = get_settings()

    payload = {
        "lookback_days": settings.lookback_days,
        "pid_groups": [group.model_dump(mode="json") for group in pid_groups],
    }

    async with httpx.AsyncClient(timeout=settings.sequence_builder_timeout_seconds) as client:
        logger.info(
            "Calling sequence-building service with %d ATM(s) of monetary-server data",
            len(pid_groups),
        )
        response = await client.post(settings.sequence_builder_url, json=payload)
        response.raise_for_status()
        body = response.json()

    fleet_sequences = body.get("fleet_sequences", [])
    result = {entry["pid"]: entry.get("components", []) for entry in fleet_sequences}

    logger.info(
        "Sequence-building service returned sequences for %d ATM(s)", len(result)
    )
    return result
