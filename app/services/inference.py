"""
Client for the RUL inference service.

This service's own implementation (5 separate models, one per component) is
out of scope here (see external_services_skeletons/inference_service_skeleton.py
for the function-level contract it needs to satisfy) - it is treated as an
external HTTP dependency.

Unlike the sequence-building service (one batched call for the whole
fleet), the inference service is called ONCE PER ATM: each call sends that
ATM's 5 component sequences and gets back all 5 component predictions
nested in a single response.

Expected contract (adjust to match the real service once it exists):
    POST {inference_service_url}
    body: {
        "pid": str,
        "component_sequences": [
            {"component_id": "component_1", "sequence": [...]},
            ...
        ]
    }
    response: {
        "pid": str,
        "components": [
            {
                "component_id": "component_1",
                "predicted_rul_days": float | null,
                "risk_level": "critical" | "warning" | "healthy" | "unknown",
                "confidence": float | null,
                "model_version": str | null
            },
            ... (5 total)
        ]
    }

Note: risk_level here is only a fallback. app/risk.py overrides it with the
day-threshold rule whenever predicted_rul_days is present.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.models import ComponentPrediction, RiskLevel

logger = logging.getLogger(__name__)


async def predict_rul_for_atm(
    pid: str, component_sequences: list[dict[str, Any]]
) -> list[ComponentPrediction]:
    """Send one ATM's 5 component sequences to the inference service and
    return its 5 component predictions (risk_level not yet thresholded -
    that happens in app/risk.py)."""
    settings = get_settings()

    payload = {"pid": pid, "component_sequences": component_sequences}

    async with httpx.AsyncClient(timeout=settings.inference_service_timeout_seconds) as client:
        response = await client.post(settings.inference_service_url, json=payload)
        response.raise_for_status()
        body = response.json()

    predictions: list[ComponentPrediction] = []
    for item in body.get("components", []):
        try:
            predictions.append(
                ComponentPrediction(
                    component_id=item["component_id"],
                    predicted_rul_days=item.get("predicted_rul_days"),
                    risk_level=RiskLevel(item.get("risk_level", "unknown")),
                    confidence=item.get("confidence"),
                    model_version=item.get("model_version"),
                )
            )
        except (KeyError, ValueError) as exc:
            logger.warning(
                "Skipping malformed component prediction for pid=%s: %r (%s)", pid, item, exc
            )

    return predictions
