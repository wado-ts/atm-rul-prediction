"""
Loads each component's trained DeepHit model at startup.
Each checkpoint contains model_state + bin_edges. Architecture params from config JSON.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict

import numpy as np
import torch

from app.config import get_settings
from app.model_architecture import DynamicDeepHit

logger = logging.getLogger(__name__)

_models: Dict[str, Dict[str, Any]] = {}
_model_locks: Dict[str, threading.Lock] = {}

# Device mapping per component (can be configured via settings if needed)
_DEFAULT_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

COMPONENT_MAPPING = {
    "CMD_CAS_1": "CMD_CAS_1",
    "CMD_CAS_2": "CMD_CAS_2",
    "CMD_CAS_3": "CMD_CAS_3",
    "CMD_CAS_4": "CMD_CAS_4",
    "RECE_PRINT": "RECE_PRINT",
}


def get_device(component_id: str) -> str:
    """Get the device for a specific component.
    
    Returns the device string (e.g., "cuda", "cpu") for the given component.
    Can be extended to support per-component device configuration via settings.
    """
    # For now, all components use the same default device
    # Can be extended to read from settings per component if needed
    return _DEFAULT_DEVICE


def get_model_lock(component_id: str) -> threading.Lock:
    """Get the thread lock for a specific component's model.
    
    Creates the lock lazily if it doesn't exist yet.
    Used to ensure thread-safe inference when multiple requests
    might hit the same model concurrently.
    """
    if component_id not in _model_locks:
        _model_locks[component_id] = threading.Lock()
    return _model_locks[component_id]


def load_all_models() -> None:
    """Called once from the FastAPI lifespan on startup."""
    settings = get_settings()
    model_dir = Path(settings.trained_models_dir)
    _models.clear()

    for dispatch_id, component_id in COMPONENT_MAPPING.items():
        checkpoint_path = model_dir / settings.deephit_model_pattern.format(component=component_id)
        config_path = model_dir / "configs" / f"config_{component_id}.json"
        bin_edges_path = model_dir / f"bin_edges_{component_id}.npy"

        try:
            # Load checkpoint (raw state dict)
            state_dict = torch.load(checkpoint_path, map_location="cpu")

            # Load architecture config from JSON
            with open(config_path) as f:
                arch_config = json.load(f)

            model = DynamicDeepHit(
                n_features=arch_config["n_features"],
                hidden_dim=arch_config["hidden_dim"],
                n_time_bins=arch_config["n_time_bins"],
                dropout=arch_config["dropout"]
            )
            model.load_state_dict(state_dict)
            model.eval()

            # Load bin_edges from separate .npy file
            bin_edges = None
            if bin_edges_path.exists():
                bin_edges = np.load(bin_edges_path)
            else:
                logger.warning("Bin edges file not found for %s at %s", component_id, bin_edges_path)

            _models[dispatch_id] = {
                "model": model,
                "bin_edges": bin_edges,
            }
            logger.info("Loaded model for %s (%s) from %s", dispatch_id, component_id, checkpoint_path)

        except FileNotFoundError as e:
            _models[dispatch_id] = None
            logger.warning("Missing artifact for %s: %s", dispatch_id, e)
        except Exception as e:
            _models[dispatch_id] = None
            logger.error("Failed to load model for %s: %s", dispatch_id, e)


def get_model(component_id: str):
    """dispatch_id -> model"""
    record = _models.get(component_id)
    return record.get("model") if record else None


def get_bin_edges(component_id: str):
    """dispatch_id -> bin_edges"""
    record = _models.get(component_id)
    return record.get("bin_edges") if record else None


def get_model_status() -> dict[str, bool]:
    """Return readiness for each required component artifact bundle."""
    return {
        component_id: bool(
            record
            and record.get("model") is not None
            and record.get("bin_edges") is not None
        )
        for component_id, record in _models.items()
    }


def is_ready() -> bool:
    """Whether every required component has a usable model bundle loaded."""
    status = get_model_status()
    return len(status) == len(COMPONENT_MAPPING) and all(status.values())