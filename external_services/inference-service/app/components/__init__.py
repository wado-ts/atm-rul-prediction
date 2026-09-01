"""
Inference components for each ATM component.

Each module provides a `predict(sequence)` function that returns
a dict with predicted_rul_days, risk_level, confidence, confidence_entropy, model_version.
"""
from app.components import cmd_cas_1, cmd_cas_2, cmd_cas_3, cmd_cas_4, rece_print

__all__ = ["cmd_cas_1", "cmd_cas_2", "cmd_cas_3", "cmd_cas_4", "rece_print"]