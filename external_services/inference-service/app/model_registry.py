"""
Loads each component's trained DeepHit model at startup.
Checkpoint is raw state dict; bin_edges loaded from separate .npy file.
Architecture params from config JSON.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

import numpy as np
import torch

from app.config import get_settings
from app.model_architecture import DynamicDeepHit

logger = logging.getLogger(__name__)

_models: Dict[str, Dict[str, Any]] = {}

COMPONENT_MAPPING = {
    "CMD_CAS_1": "CMD_CAS_1",
    "CMD_CAS_2": "CMD_CAS_2",
    "CMD_CAS_3": "CMD_CAS_3",
    "CMD_CAS_4": "CMD_CAS_4",
    "RECE_PRINT": "RECE_PRINT",
}


def load_all_models() -> None:
    """Called once from the FastAPI lifespan on startup."""
    settings = get_settings()
    model_dir = Path(settings.trained_models_dir)

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
            bin_edges = np.load(bin_edges_path) if bin_edges_path.exists() else None
            if bin_edges is None:
                logger.warning("Bin edges not found for %s at %s", component_id, bin_edges_path)

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
    return _models.get(component_id, {}).get("model")


def get_bin_edges(component_id: str):
    """dispatch_id -> bin_edges"""
    return _models.get(component_id, {}).get("bin_edges")