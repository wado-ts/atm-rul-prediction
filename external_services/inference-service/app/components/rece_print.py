"""
RUL inference for RECE_PRINT.

Owns loading and running RECE_PRINT's trained model against the
sequence produced by the sequence-building service.
"""
from __future__ import annotations

from typing import Any

import torch

from app.model_registry import get_model, get_bin_edges
from app.inference_utils import sequence_to_tensors, pmf_to_rul, compute_confidence, get_risk_level
from app.config import get_settings


def predict(sequence: dict[str, Any]) -> dict[str, Any]:
    """Run RECE_PRINT's RUL model on its sequence."""
    model = get_model("RECE_PRINT")
    bin_edges = get_bin_edges("RECE_PRINT")

    if model is None or bin_edges is None:
        return {
            "predicted_rul_days": None,
            "risk_level": "unknown",
            "confidence": None,
            "confidence_entropy": None,
            "model_version": None
        }

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)

    X = torch.tensor(sequence["X"], dtype=torch.float32).to(device)
    mask = torch.tensor(sequence["mask"], dtype=torch.float32).to(device)

    with torch.no_grad():
        pmf = model(X, mask).squeeze(0).cpu().numpy()

    rul_result = pmf_to_rul(pmf, bin_edges)
    confidence = compute_confidence(pmf)
    rul_days = rul_result["expected_rul_minutes"] / (60 * 24)

    settings = get_settings()
    risk = get_risk_level(rul_days, settings.rul_critical_threshold_days, settings.rul_warning_threshold_days)

    return {
        "predicted_rul_days": float(rul_days),
        "risk_level": risk,
        "confidence": float(confidence["survival"]),
        "confidence_entropy": float(confidence["entropy"]),
        "model_version": "dynamic_deephit_v1"
    }