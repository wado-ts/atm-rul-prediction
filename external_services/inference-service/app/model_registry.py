"""
Loads each component's trained model artifact once at service startup and
keeps it in memory for reuse across requests - deserializing a model on
every call would be far too slow.

This registry is plumbing only: it doesn't care what kind of model each
component uses (a lifelines CoxPHFitter, a scikit-learn IsolationForest,
anything joblib-serializable), as long as each component's trained model
is saved as a single file named per COMPONENT_*_MODEL_FILE in .env and
sits under TRAINED_MODELS_DIR.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import joblib

from app.config import get_settings

logger = logging.getLogger(__name__)

_models: dict[str, Any] = {}


def load_all_models() -> None:
    """Called once from the FastAPI lifespan on startup."""
    settings = get_settings()
    model_dir = Path(settings.trained_models_dir)

    files = {
        "component_1": settings.component_1_model_file,
        "component_2": settings.component_2_model_file,
        "component_3": settings.component_3_model_file,
        "component_4": settings.component_4_model_file,
        "component_5": settings.component_5_model_file,
    }

    for component_id, filename in files.items():
        path = model_dir / filename
        try:
            _models[component_id] = joblib.load(path)
            logger.info("Loaded model for %s from %s", component_id, path)
        except FileNotFoundError:
            _models[component_id] = None
            logger.warning(
                "No trained model file found for %s at %s - "
                "predict() for that component will need to handle this",
                component_id,
                path,
            )


def get_model(component_id: str) -> Any:
    """Returns the loaded model object for a component, or None if it
    wasn't found at startup (see load_all_models)."""
    return _models.get(component_id)
