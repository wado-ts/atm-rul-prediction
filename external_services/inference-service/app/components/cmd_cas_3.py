"""
RUL inference for CMD_CAS_3.

Owns loading and running CMD_CAS_3's trained model against the
sequence produced by the sequence-building service.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import torch

from app.model_registry import get_model, get_bin_edges, get_device, get_model_lock
from app.inference_utils import sequence_to_tensors, pmf_to_rul, compute_confidence, get_risk_level
from app.config import get_settings


def predict(sequence: dict[str, Any]) -> dict[str, Any]:
    """Run CMD_CAS_3's RUL model on its sequence."""
    model = get_model("CMD_CAS_3")
    bin_edges = get_bin_edges("CMD_CAS_3")

    if model is None or bin_edges is None:
        return {
            "predicted_rul_days": None,
            "risk_level": "unknown",
            "confidence": None,
            "confidence_entropy": None,
            "overdue": None,
            "model_version": None
        }

    device = get_device("CMD_CAS_3")

    X, mask = sequence_to_tensors(sequence, device)

    with get_model_lock("CMD_CAS_3"), torch.inference_mode():
        pmf = model(X, mask).squeeze(0).cpu().numpy()

    rul_result = pmf_to_rul(pmf, bin_edges)
    confidence = compute_confidence(pmf)
    expected_rul_minutes = rul_result["expected_rul_minutes"]

    # Adjust RUL based on elapsed time since episode start (cutoff time = now)
    settings = get_settings()
    episode_start_str = sequence.get("episode_start_timestamp")
    if episode_start_str:
        episode_start = datetime.fromisoformat(episode_start_str)
        # Use reference_time from settings if available, otherwise fallback to utcnow
        if settings.reference_time:
            cutoff_time = datetime.fromisoformat(settings.reference_time)
        else:
            cutoff_time = datetime.utcnow()
        elapsed_minutes = (cutoff_time - episode_start).total_seconds() / 60.0
        rul_minutes = expected_rul_minutes - elapsed_minutes
        overdue = rul_minutes < 0
        rul_days = rul_minutes / (60 * 24)
    else:
        # Fallback: use total expected RUL if no episode start timestamp
        rul_days = expected_rul_minutes / (60 * 24)
        overdue = None

    risk = get_risk_level(rul_days, settings.rul_critical_threshold_days, settings.rul_warning_threshold_days)

    return {
        "predicted_rul_days": float(rul_days),
        "risk_level": risk,
        "confidence": float(confidence["survival"]),
        "confidence_entropy": float(confidence["entropy"]),
        "overdue": overdue,
        "model_version": "dynamic_deephit_v1"
    }
