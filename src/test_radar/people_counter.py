"""Contador experimental de cruces para una puerta usando el LiDAR 8x8.

El algoritmo cuenta cruces de una zona lateral a la opuesta; no identifica personas.
La frecuencia de salida depende del sensor y del flujo serie real.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np


@dataclass
class CountSnapshot:
    people_in: int = 0
    people_out: int = 0
    occupancy: int = 0
    sample_hz: float = 0.0
    active_cells: int = 0
    centroid_column: float | None = None
    last_direction: str | None = None


class DoorwayCounter:
    """Cuenta cruces de izquierda/derecha en una zona de paso, con anti-rebote."""

    def __init__(
        self,
        threshold_mm: float = 1800.0,
        entry_side: str = "left",
        initial_occupancy: int = 0,
        stable_frames: int = 2,
        cooldown_seconds: float = 1.0,
        release_seconds: float = 0.8,
    ) -> None:
        if entry_side not in {"left", "right"}:
            raise ValueError("entry_side debe ser 'left' o 'right'.")
        self.threshold_mm = threshold_mm
        self.entry_side = entry_side
        self.stable_frames = max(1, stable_frames)
        self.cooldown_seconds = cooldown_seconds
        self.release_seconds = release_seconds
        self.snapshot = CountSnapshot(occupancy=max(0, initial_occupancy))
        self._candidate_side: str | None = None
        self._candidate_count = 0
        self._last_side: str | None = None
        self._last_cross = 0.0
        self._last_presence = 0.0
        self._last_frame = 0.0
        self._rate_frames = 0
        self._rate_started = time.monotonic()

    def update(self, frame: np.ndarray, now: float | None = None) -> dict | None:
        now = time.monotonic() if now is None else now
        matrix = np.asarray(frame, dtype=float).reshape(8, 8)
        valid = np.isfinite(matrix) & (matrix > 0) & (matrix < 4000) & (matrix <= self.threshold_mm)
        rows, cols = np.where(valid)
        self.snapshot.active_cells = int(len(cols))
        self._rate_frames += 1
        elapsed = max(now - self._rate_started, 1e-6)
        self.snapshot.sample_hz = self._rate_frames / elapsed
        self._last_frame = now

        if len(cols) == 0:
            if self._last_presence and now - self._last_presence >= self.release_seconds:
                self._last_side = None
                self._candidate_side = None
                self._candidate_count = 0
            return None

        self._last_presence = now
        centroid = float(np.mean(cols))
        self.snapshot.centroid_column = centroid
        side = "left" if centroid <= 2.75 else "right" if centroid >= 4.25 else None
        if side is None:
            return None

        if side == self._candidate_side:
            self._candidate_count += 1
        else:
            self._candidate_side = side
            self._candidate_count = 1
        if self._candidate_count < self.stable_frames:
            return None

        if self._last_side is None:
            self._last_side = side
            return None
        if side == self._last_side:
            return None
        if now - self._last_cross < self.cooldown_seconds:
            self._last_side = side
            return None

        entering = (self._last_side == self.entry_side and side != self.entry_side)
        direction = "in" if entering else "out"
        if direction == "in":
            self.snapshot.people_in += 1
            self.snapshot.occupancy += 1
        else:
            self.snapshot.people_out += 1
            self.snapshot.occupancy = max(0, self.snapshot.occupancy - 1)
        self.snapshot.last_direction = direction
        self._last_cross = now
        self._last_side = side
        return {
            "direction": direction,
            "people_in": self.snapshot.people_in,
            "people_out": self.snapshot.people_out,
            "occupancy": self.snapshot.occupancy,
            "centroid_column": round(centroid, 2),
            "sample_hz": round(self.snapshot.sample_hz, 1),
            "timestamp": time.time(),
        }

    def telemetry(self) -> dict:
        return {
            "sample_hz": round(self.snapshot.sample_hz, 1),
            "people_in": self.snapshot.people_in,
            "people_out": self.snapshot.people_out,
            "occupancy": self.snapshot.occupancy,
        }
