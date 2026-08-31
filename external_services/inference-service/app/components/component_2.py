"""
RUL inference for component_2.

Owns loading and running component_2's trained model against the
sequence produced by app/components/component_2.py in the
sequence-building service - keep the two in sync, since this file's
input shape is that file's output shape.
"""
from __future__ import annotations

from typing import Any

from app.model_registry import get_model


def predict(sequence: dict[str, Any]) -> dict[str, Any]:
    """Run component_2's RUL model on its sequence.

    Input:
        sequence: the component_2 sequence produced by
            build_sequence() in the sequence-building service's
            app/components/component_2.py.

    Output:
        {
            "predicted_rul_days": float | None,
            "risk_level": "critical" | "warning" | "healthy" | "unknown",
            "confidence": float | None,
            "model_version": str | None
        }
    """
    model = get_model("component_2")
    raise NotImplementedError("Implement component_2 inference using `model`")
