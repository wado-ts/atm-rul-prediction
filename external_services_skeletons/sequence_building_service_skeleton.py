"""
Skeleton for the sequence-building service.

This is NOT part of the FastAPI app - it's a function-level contract for
whoever implements the actual sequence-building service, matching exactly
what app/services/sequence_builder.py sends and expects back. No logic is
implemented here (see NotImplementedError bodies); each function's
docstring specifies its input and output shape.

The service is called once per prediction run, batched for the whole
fleet. For each ATM it must produce 5 sequences - one per component
(component_1 .. component_5) - since each component is predicted by its
own separate model downstream.
"""
from __future__ import annotations

from typing import Any


def build_sequence_for_component_1(pid: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the model-ready sequence for component_1 for one ATM.

    Input:
        pid: the ATM identifier.
        records: that ATM's raw monetary-server rows for the lookback
            window (~15-minute cadence), each shaped like:
            {
                "pid": str, "query_date": iso-datetime, "version": str | None,
                "institution": str | None, "nbre_cas_1": int, "nbre_cas_2": int,
                "nbre3": int, "nbre_cas_4": int, "cmd_cas_1": int | None,
                "cmd_cas_2": int | None, "cmd_cas_3": int | None,
                "cmd_cas_4": int | None, "rece_print": int | None
            }
            sorted ascending by query_date.

    Output:
        A component_1-specific sequence, in whatever structure component_1's
        downstream inference model expects (e.g. a fixed-length window of
        feature vectors). Shape is owned by this service and the
        corresponding inference model - the app only passes it through.
    """
    raise NotImplementedError


def build_sequence_for_component_2(pid: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the model-ready sequence for component_2 for one ATM.

    Same input contract as build_sequence_for_component_1. Output shape is
    specific to component_2's downstream inference model.
    """
    raise NotImplementedError


def build_sequence_for_component_3(pid: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the model-ready sequence for component_3 for one ATM.

    Same input contract as build_sequence_for_component_1. Output shape is
    specific to component_3's downstream inference model.
    """
    raise NotImplementedError


def build_sequence_for_component_4(pid: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the model-ready sequence for component_4 for one ATM.

    Same input contract as build_sequence_for_component_1. Output shape is
    specific to component_4's downstream inference model.
    """
    raise NotImplementedError


def build_sequence_for_component_5(pid: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the model-ready sequence for component_5 for one ATM.

    Same input contract as build_sequence_for_component_1. Output shape is
    specific to component_5's downstream inference model.
    """
    raise NotImplementedError


def build_sequences_for_atm(pid: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    """Build all 5 component sequences for one ATM by calling each
    build_sequence_for_component_* function above.

    Input:
        pid: the ATM identifier.
        records: that ATM's raw monetary-server rows (see
            build_sequence_for_component_1 for the row shape).

    Output:
        {
            "pid": pid,
            "components": [
                {"component_id": "component_1", "sequence": <from component_1>},
                {"component_id": "component_2", "sequence": <from component_2>},
                {"component_id": "component_3", "sequence": <from component_3>},
                {"component_id": "component_4", "sequence": <from component_4>},
                {"component_id": "component_5", "sequence": <from component_5>}
            ]
        }
    """
    raise NotImplementedError


def build_fleet_sequences(pid_groups: list[dict[str, Any]]) -> dict[str, Any]:
    """Top-level handler for the service's HTTP endpoint
    (POST {sequence_builder_url}, called once per prediction run for the
    whole fleet).

    Input:
        {
            "lookback_days": int,
            "pid_groups": [
                {"pid": str, "records": [<row dicts, see above>]},
                ...  (one entry per ATM seen in the lookback window)
            ]
        }
        (equivalently, pid_groups here is the "pid_groups" list from that body)

    Output (the full HTTP response body):
        {
            "fleet_sequences": [
                <one build_sequences_for_atm(...) result per ATM>,
                ...
            ]
        }
    """
    raise NotImplementedError
