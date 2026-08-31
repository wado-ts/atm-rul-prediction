"""
RUL inference for component_1.

Owns loading and running component_1's trained model against the
sequence produced by app/components/component_1.py in the
sequence-building service - keep the two in sync, since this file's
input shape is that file's output shape.
"""
from __future__ import annotations

from typing import Any

from app.model_registry import get_model


def predict(sequence: dict[str, Any]) -> dict[str, Any]:
    """Run component_1's RUL model on its sequence.

    Input:
        sequence: the component_1 sequence produced by
            build_sequence() in the sequence-building service's
            app/components/component_1.py.

    Output:
        {
            "predicted_rul_days": float | None,
            "risk_level": "critical" | "warning" | "healthy" | "unknown",
            "confidence": float | None,
            "model_version": str | None
        }
    """
    model = get_model("component_1")
    raise NotImplementedError("Implement component_1 inference using `model`")
