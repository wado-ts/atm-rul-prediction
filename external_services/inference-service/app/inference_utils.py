"""
Shared inference utilities.
"""
from __future__ import annotations

import numpy as np
import torch
from typing import Dict, Any


def sequence_to_tensors(sequence: Dict[str, Any], device: str = "cpu") -> tuple:
    """
    Convert sequence dict to tensors.
    NO SCALING - already done upstream in sequence-building service.
    """
    X = torch.tensor(sequence["X"], dtype=torch.float32).to(device)      # [1, MAX_LEN, n_features]
    mask = torch.tensor(sequence["mask"], dtype=torch.float32).to(device) # [1, MAX_LEN]
    return X, mask


def pmf_to_rul(pmf: np.ndarray, bin_edges: np.ndarray) -> Dict[str, Any]:
    """
    Compute RUL statistics from PMF.
    """
    pmf = np.asarray(pmf).squeeze()
    K = pmf.shape[-1] - 1

    # Dynamically resample bin_edges if size mismatch
    if len(bin_edges) - 1 != K:
        old_grid = np.linspace(0, 1, len(bin_edges))
        new_grid = np.linspace(0, 1, K + 1)
        edges = np.interp(new_grid, old_grid, bin_edges)
    else:
        edges = bin_edges.copy()

    if np.isinf(edges[-1]):
        last_finite_width = edges[-2] - edges[-3]
        edges[-1] = edges[-2] + last_finite_width

    midpoints = (edges[:-1] + edges[1:]) / 2.0
    tail_midpoint = edges[-1] + (edges[-1] - edges[-2]) / 2.0
    all_midpoints = np.append(midpoints, tail_midpoint)

    expected_rul_minutes = float(np.sum(pmf * all_midpoints))
    survival_tail = float(pmf[-1])

    # Survival curve
    failure_pmf = pmf[:K]
    surv = 1.0 - np.cumsum(failure_pmf)

    # Median RUL
    median_rul = None
    for i, s in enumerate(surv):
        if s <= 0.5:
            median_rul = float(edges[i])
            break
    if median_rul is None:
        median_rul = float(tail_midpoint)

    # Risk score
    risk_score = float(np.cumsum(failure_pmf).sum())

    return {
        "expected_rul_minutes": expected_rul_minutes,
        "median_rul_minutes": median_rul,
        "survival_tail": survival_tail,
        "risk_score": risk_score,
        "survival_curve": surv.tolist(),
    }


def compute_confidence(pmf: np.ndarray) -> Dict[str, float]:
    """
    Compute both confidence metrics from PMF.
    """
    # Survival tail confidence
    survival_tail = float(pmf[-1])
    confidence_survival = 1.0 - survival_tail

    # Entropy confidence (normalized)
    pmf_clipped = np.clip(pmf, 1e-12, 1.0)
    entropy = -np.sum(pmf_clipped * np.log(pmf_clipped))
    max_entropy = np.log(len(pmf))
    confidence_entropy = 1.0 - (entropy / max_entropy)

    return {
        "survival": confidence_survival,
        "entropy": confidence_entropy,
    }


def get_risk_level(rul_days: float, critical_days: float = 7.0, warning_days: float = 14.0) -> str:
    if rul_days <= critical_days:
        return "critical"
    elif rul_days <= warning_days:
        return "warning"
    else:
        return "healthy"