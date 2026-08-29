"""
Risk-level derivation.

Rule: for a given component, if the inference service returned a numeric
predicted_rul_days, that value - not whatever risk_level the service sent -
determines the risk level:

    predicted_rul_days <= RUL_CRITICAL_THRESHOLD_DAYS  -> critical
    predicted_rul_days <= RUL_WARNING_THRESHOLD_DAYS   -> warning
    predicted_rul_days >  RUL_WARNING_THRESHOLD_DAYS   -> healthy

If predicted_rul_days is missing/null, there's nothing to threshold against,
so we fall back to whatever risk_level the inference service provided (or
"unknown" if it didn't provide one either).

An ATM's overall risk is the most severe (worst) risk level among its 5
components.
"""
from __future__ import annotations

from app.config import get_settings
from app.models import ComponentPrediction, RISK_SEVERITY, RiskLevel


def derive_component_risk(
    predicted_rul_days: float | None,
    service_risk_level: RiskLevel = RiskLevel.UNKNOWN,
) -> RiskLevel:
    """Apply the day-threshold rule to one component's prediction."""
    if predicted_rul_days is not None:
        settings = get_settings()
        if predicted_rul_days <= settings.rul_critical_threshold_days:
            return RiskLevel.CRITICAL
        if predicted_rul_days <= settings.rul_warning_threshold_days:
            return RiskLevel.WARNING
        return RiskLevel.HEALTHY

    return service_risk_level or RiskLevel.UNKNOWN


def compute_overall_risk(component_risks: list[RiskLevel]) -> RiskLevel:
    """An ATM's overall risk = the worst (most severe) of its components."""
    if not component_risks:
        return RiskLevel.UNKNOWN
    return max(component_risks, key=lambda level: RISK_SEVERITY[level])


def find_weakest_component(
    components: list[ComponentPrediction],
) -> ComponentPrediction | None:
    """The component driving the ATM's overall risk: highest severity first,
    tie-broken by the lowest predicted_rul_days (nulls sort last)."""
    if not components:
        return None

    def sort_key(component: ComponentPrediction) -> tuple[int, float]:
        severity = RISK_SEVERITY[component.risk_level]
        rul = component.predicted_rul_days if component.predicted_rul_days is not None else float("inf")
        return (-severity, rul)

    return sorted(components, key=sort_key)[0]
