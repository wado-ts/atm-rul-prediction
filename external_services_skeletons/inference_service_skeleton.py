"""
Skeleton for the RUL inference service.

This is NOT part of the FastAPI app - it's a function-level contract for
whoever implements the actual inference service, matching exactly what
app/services/inference.py sends and expects back. No logic is implemented
here (see NotImplementedError bodies); each function's docstring specifies
its input and output shape.

Unlike the sequence-building service, this service is called once PER ATM
(not batched for the fleet). Each of the 5 components is predicted by its
own separate model; risk_level returned here is only a fallback - the app
overrides it with a day-threshold rule whenever predicted_rul_days is
present, so it's fine for these functions to return "unknown" if the model
itself doesn't produce a risk category.
"""
from __future__ import annotations

from typing import Any


def predict_component_1(sequence: dict[str, Any]) -> dict[str, Any]:
    """Run component_1's RUL model on its sequence.

    Input:
        sequence: the component_1 sequence produced by
            build_sequence_for_component_1 in the sequence-building service
            (structure owned by that service and this model together).

    Output:
        {
            "predicted_rul_days": float | None,
            "risk_level": "critical" | "warning" | "healthy" | "unknown",
            "confidence": float | None,
            "model_version": str | None
        }
    """
    raise NotImplementedError


def predict_component_2(sequence: dict[str, Any]) -> dict[str, Any]:
    """Run component_2's RUL model on its sequence.

    Same input/output contract as predict_component_1, using component_2's
    own model.
    """
    raise NotImplementedError


def predict_component_3(sequence: dict[str, Any]) -> dict[str, Any]:
    """Run component_3's RUL model on its sequence.

    Same input/output contract as predict_component_1, using component_3's
    own model.
    """
    raise NotImplementedError


def predict_component_4(sequence: dict[str, Any]) -> dict[str, Any]:
    """Run component_4's RUL model on its sequence.

    Same input/output contract as predict_component_1, using component_4's
    own model.
    """
    raise NotImplementedError


def predict_component_5(sequence: dict[str, Any]) -> dict[str, Any]:
    """Run component_5's RUL model on its sequence.

    Same input/output contract as predict_component_1, using component_5's
    own model.
    """
    raise NotImplementedError


def predict_rul_for_atm(pid: str, component_sequences: list[dict[str, Any]]) -> dict[str, Any]:
    """Top-level handler for the service's HTTP endpoint
    (POST {inference_service_url}, called once PER ATM).

    Input (the full HTTP request body):
        {
            "pid": str,
            "component_sequences": [
                {"component_id": "component_1", "sequence": <...>},
                {"component_id": "component_2", "sequence": <...>},
                {"component_id": "component_3", "sequence": <...>},
                {"component_id": "component_4", "sequence": <...>},
                {"component_id": "component_5", "sequence": <...>}
            ]
        }

    Dispatches each component's sequence to its matching predict_component_*
    function above.

    Output (the full HTTP response body):
        {
            "pid": pid,
            "components": [
                {"component_id": "component_1", **predict_component_1(...)},
                {"component_id": "component_2", **predict_component_2(...)},
                {"component_id": "component_3", **predict_component_3(...)},
                {"component_id": "component_4", **predict_component_4(...)},
                {"component_id": "component_5", **predict_component_5(...)}
            ]
        }
    """
    raise NotImplementedError
