"""
Minimal in-memory store for the latest prediction run and recent history.

This is intentionally simple (a process-local singleton) since the app has
a single writer path (the pipeline) and read-mostly frontend traffic. Swap
this for Redis/a DB table if the app needs to run as multiple replicas.
"""
from __future__ import annotations

import threading

from app.models import FleetPredictionResult


class PredictionStore:
    def __init__(self, history_limit: int = 20) -> None:
        self._lock = threading.Lock()
        self._current: FleetPredictionResult | None = None
        self._history: list[FleetPredictionResult] = []
        self._history_limit = history_limit

    def set_current_run(self, result: FleetPredictionResult) -> None:
        with self._lock:
            self._current = result

    def get_current_run(self) -> FleetPredictionResult | None:
        with self._lock:
            return self._current

    def push_history(self, result: FleetPredictionResult) -> None:
        with self._lock:
            self._history.insert(0, result)
            self._history = self._history[: self._history_limit]

    def get_history(self) -> list[FleetPredictionResult]:
        with self._lock:
            return list(self._history)


prediction_store = PredictionStore()
