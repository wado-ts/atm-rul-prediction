"""
Sequence construction for component_1.

Owns the feature engineering / windowing logic that turns one ATM's raw
monetary-server rows into the exact sequence shape component_1's
downstream inference model expects. That output shape is this file's
responsibility together with app/components/component_1.py in the
inference service - keep the two in sync.
"""
from __future__ import annotations

from typing import Any


def build_sequence(pid: str, records: list[dict[str, Any]], component: str) -> dict[str, Any]:
    """Build the model-ready sequence for component_1 for one ATM.

    Input:
        pid: the ATM identifier.
        records: that ATM's raw monetary-server rows for the lookback
            window, sorted ascending by query_date, each shaped like:
            {
                "pid": str, "query_date": iso-datetime, "version": str | None,
                "institution": str | None, "nbre_cas_1": int, "nbre_cas_2": int,
                "nbre3": int, "nbre_cas_4": int, "cmd_cas_1": int | None,
                "cmd_cas_2": int | None, "cmd_cas_3": int | None,
                "cmd_cas_4": int | None, "rece_print": int | None
            }

    Output:
        A component_1-specific sequence, in whatever structure
        component_1's downstream inference model expects (e.g. a
        fixed-length window of feature vectors).
    """
    raise NotImplementedError("Implement component_1 feature engineering / sequence construction")
