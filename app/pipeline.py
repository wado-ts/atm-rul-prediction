"""
Orchestrates one end-to-end prediction run:

    Oracle monetary-server data (last 30 days, grouped by PID)
        -> sequence-building service (1 batched call, 5 sequences per ATM)
        -> inference service (1 call PER ATM, 5 component predictions back)
        -> risk-level thresholding + overall-risk/weakest-component rollup
        -> in-memory store (read by the frontend)

Both the midnight scheduler and the manual "Run prediction now" button call
run_pipeline() - there is exactly one code path for producing a fleet
prediction, regardless of what triggered it.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime

from app.database import fetch_last_month_data_grouped_by_pid
from app.models import AtmPrediction, ComponentPrediction, FleetPredictionResult, PidLogGroup, RiskLevel
from app.risk import compute_overall_risk, derive_component_risk, find_weakest_component
from app.services.inference import predict_rul_for_atm
from app.services.sequence_builder import build_sequences
from app.store import prediction_store

logger = logging.getLogger(__name__)

# Bounds how many ATMs are sent to the inference service concurrently, since
# it's called once per ATM rather than once for the whole fleet.
_MAX_CONCURRENT_INFERENCE_CALLS = 8


def _generate_synthesized_predictions() -> list[AtmPrediction]:
    now = datetime.utcnow()
    raw_fleet = [
        ("ATM-1042", [("Dispenser_Cassette_1", 18.2, RiskLevel.HEALTHY), ("Dispenser_Cassette_2", 2.4, RiskLevel.CRITICAL), ("Receipt_Printer", 12.0, RiskLevel.WARNING), ("Card_Reader", 25.0, RiskLevel.HEALTHY), ("PIN_Pad", 28.5, RiskLevel.HEALTHY)]),
        ("ATM-2089", [("Dispenser_Cassette_1", 4.1, RiskLevel.CRITICAL), ("Dispenser_Cassette_2", 15.0, RiskLevel.HEALTHY), ("Receipt_Printer", 22.4, RiskLevel.HEALTHY), ("Card_Reader", 19.8, RiskLevel.HEALTHY), ("PIN_Pad", 27.0, RiskLevel.HEALTHY)]),
        ("ATM-3105", [("Dispenser_Cassette_1", 14.5, RiskLevel.HEALTHY), ("Dispenser_Cassette_2", 16.2, RiskLevel.HEALTHY), ("Receipt_Printer", 7.8, RiskLevel.WARNING), ("Card_Reader", 11.4, RiskLevel.WARNING), ("PIN_Pad", 24.0, RiskLevel.HEALTHY)]),
        ("ATM-4012", [("Dispenser_Cassette_1", 28.0, RiskLevel.HEALTHY), ("Dispenser_Cassette_2", 26.5, RiskLevel.HEALTHY), ("Receipt_Printer", 22.1, RiskLevel.HEALTHY), ("Card_Reader", 29.0, RiskLevel.HEALTHY), ("PIN_Pad", 27.8, RiskLevel.HEALTHY)]),
        ("ATM-5120", [("Dispenser_Cassette_1", 22.0, RiskLevel.HEALTHY), ("Dispenser_Cassette_2", 24.1, RiskLevel.HEALTHY), ("Receipt_Printer", 21.0, RiskLevel.HEALTHY), ("Card_Reader", 25.5, RiskLevel.HEALTHY), ("PIN_Pad", 29.0, RiskLevel.HEALTHY)]),
        ("ATM-6034", [("Dispenser_Cassette_1", 9.2, RiskLevel.WARNING), ("Dispenser_Cassette_2", 18.0, RiskLevel.HEALTHY), ("Receipt_Printer", 14.2, RiskLevel.HEALTHY), ("Card_Reader", 17.5, RiskLevel.HEALTHY), ("PIN_Pad", 23.0, RiskLevel.HEALTHY)]),
        ("ATM-7198", [("Dispenser_Cassette_1", 27.5, RiskLevel.HEALTHY), ("Dispenser_Cassette_2", 25.0, RiskLevel.HEALTHY), ("Receipt_Printer", 24.8, RiskLevel.HEALTHY), ("Card_Reader", 28.2, RiskLevel.HEALTHY), ("PIN_Pad", 29.5, RiskLevel.HEALTHY)]),
        ("ATM-7198", [("Dispenser_Cassette_1", 27.5, RiskLevel.HEALTHY), ("Dispenser_Cassette_2", 25.0, RiskLevel.HEALTHY), ("Receipt_Printer", 24.8, RiskLevel.HEALTHY), ("Card_Reader", 28.2, RiskLevel.HEALTHY), ("PIN_Pad", 29.5, RiskLevel.HEALTHY)]),
        ("ATM-7198", [("Dispenser_Cassette_1", 27.5, RiskLevel.HEALTHY), ("Dispenser_Cassette_2", 25.0, RiskLevel.HEALTHY), ("Receipt_Printer", 24.8, RiskLevel.HEALTHY), ("Card_Reader", 28.2, RiskLevel.HEALTHY), ("PIN_Pad", 29.5, RiskLevel.HEALTHY)]),
        ("ATM-8051", [("Dispenser_Cassette_1", 1.9, RiskLevel.CRITICAL), ("Dispenser_Cassette_2", 8.4, RiskLevel.WARNING), ("Receipt_Printer", 15.0, RiskLevel.HEALTHY), ("Card_Reader", 12.1, RiskLevel.WARNING), ("PIN_Pad", 26.0, RiskLevel.HEALTHY)]),
    ]

    predictions: list[AtmPrediction] = []
    for pid, comps in raw_fleet:
        components = [
            ComponentPrediction(
                component_id=cid,
                predicted_rul_days=rul,
                risk_level=risk,
                confidence=0.94,
                model_version="v1.2.0"
            )
            for cid, rul, risk in comps
        ]
        overall = compute_overall_risk([c.risk_level for c in components])
        weakest = find_weakest_component(components)
        predictions.append(
            AtmPrediction(
                pid=pid,
                last_query_date=now,
                components=components,
                overall_risk=overall,
                weakest_component_id=weakest.component_id if weakest else None,
                weakest_component_rul_days=weakest.predicted_rul_days if weakest else None,
            )
        )
    return predictions


def _latest_query_date(group: PidLogGroup) -> datetime | None:
    if not group.records:
        return None
    return max(record.query_date for record in group.records)


async def _predict_one_atm(
    pid: str,
    component_sequences: list[dict],
    last_query_date: datetime | None,
    semaphore: asyncio.Semaphore,
) -> AtmPrediction:
    async with semaphore:
        raw_components = await predict_rul_for_atm(pid, component_sequences)

    resolved_components: list[ComponentPrediction] = []
    for component in raw_components:
        risk_level = derive_component_risk(component.predicted_rul_days, component.risk_level)
        resolved_components.append(component.model_copy(update={"risk_level": risk_level}))

    overall_risk = compute_overall_risk([c.risk_level for c in resolved_components])
    weakest = find_weakest_component(resolved_components)

    return AtmPrediction(
        pid=pid,
        last_query_date=last_query_date,
        components=resolved_components,
        overall_risk=overall_risk,
        weakest_component_id=weakest.component_id if weakest else None,
        weakest_component_rul_days=weakest.predicted_rul_days if weakest else None,
    )


async def run_pipeline(triggered_by: str = "manual") -> FleetPredictionResult:
    run_id = str(uuid.uuid4())
    started_at = datetime.utcnow()
    result = FleetPredictionResult(
        run_id=run_id,
        triggered_by=triggered_by,
        started_at=started_at,
        status="pending",
    )
    prediction_store.set_current_run(result)

    try:
        # 1. Fetch last month of monetary-server data, grouped by PID.
        pid_groups = fetch_last_month_data_grouped_by_pid()

        # if not pid_groups:
        #     logger.info("No DB records returned; using synthesized fleet predictions for demonstration.")
        #     synthesized = _generate_synthesized_predictions()
        #     result.fleet_size = len(synthesized)
        #     result.predictions = synthesized
        #     result.status = "success"
        #     result.completed_at = datetime.utcnow()
        #     prediction_store.set_current_run(result)
        #     prediction_store.push_history(result)
        #     return result

        last_query_dates = {group.pid: _latest_query_date(group) for group in pid_groups}

        # 2. Build sequences via the sequence-building service - one batched
        #    call for the whole fleet, 5 sequences (one per component) per ATM.
        fleet_sequences = await build_sequences(pid_groups)

        # 3. Compute RUL predictions via the inference service - one call
        #    PER ATM, each returning all 5 component predictions nested.
        semaphore = asyncio.Semaphore(_MAX_CONCURRENT_INFERENCE_CALLS)
        atm_predictions = await asyncio.gather(
            *(
                _predict_one_atm(pid, component_sequences, last_query_dates.get(pid), semaphore)
                for pid, component_sequences in fleet_sequences.items()
            )
        )

        result.predictions = list(atm_predictions)
        result.status = "success"

    except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
        logger.exception("Prediction pipeline run %s failed", run_id)
        result.status = "failed"
        result.error_message = str(exc)

    result.completed_at = datetime.utcnow()
    prediction_store.set_current_run(result)
    prediction_store.push_history(result)
    return result
