"""Estabilizacion y deteccion de agrupaciones en la matriz LiDAR."""
from __future__ import annotations

from collections import deque

import numpy as np

from .baseline import Baseline
from .config import RadarConfig


class FrameStabilizer:
    def __init__(self, config: RadarConfig) -> None:
        self.config = config
        self.frames: deque[np.ndarray] = deque(maxlen=config.history_frames)

    def add(self, frame: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
        self.frames.append(frame.copy())
        if len(self.frames) < self.config.minimum_stable_frames:
            return None
        frames = np.array(self.frames)
        valid = (frames > 0) & (frames < 4000)
        stable = np.sum(valid, axis=0) >= self.config.minimum_stable_frames
        result = np.full((8, 8), 4000.0)
        for row in range(8):
            for column in range(8):
                values = frames[:, row, column]
                values = values[(values > 0) & (values < 4000)]
                if len(values) >= self.config.minimum_stable_frames:
                    result[row, column] = np.median(values)
        return result, stable


def object_mask(matrix: np.ndarray, stable: np.ndarray, config: RadarConfig, baseline: Baseline | None = None) -> np.ndarray:
    """Celdas candidatas a objeto: estables, dentro del umbral y (si hay) nuevas respecto al fondo."""
    mask = stable & (matrix > 0) & (matrix < 4000) & (matrix <= config.object_threshold_mm)
    if baseline is not None:
        mask &= baseline.foreground(matrix)
    return mask


def detect_objects(matrix: np.ndarray, stable: np.ndarray, angle_degrees: float, config: RadarConfig, baseline: Baseline | None = None) -> list[dict[str, float]]:
    valid = object_mask(matrix, stable, config, baseline)
    visited = np.zeros((8, 8), dtype=bool)
    detections: list[dict[str, float]] = []
    for row in range(8):
        for column in range(8):
            if visited[row, column] or not valid[row, column]:
                continue
            group, pending = [(row, column)], [(row, column)]
            visited[row, column] = True
            while pending:
                current_row, current_column = pending.pop()
                for next_row, next_column in ((current_row - 1, current_column), (current_row + 1, current_column), (current_row, current_column - 1), (current_row, current_column + 1)):
                    if not (0 <= next_row < 8 and 0 <= next_column < 8):
                        continue
                    if visited[next_row, next_column] or not valid[next_row, next_column]:
                        continue
                    if abs(matrix[next_row, next_column] - matrix[current_row, current_column]) <= config.group_distance_delta_mm:
                        visited[next_row, next_column] = True
                        pending.append((next_row, next_column))
                        group.append((next_row, next_column))
            columns = [item[1] for item in group]
            distances = [matrix[item[0], item[1]] for item in group]
            object_angle = angle_degrees + (float(np.mean(columns)) - 3.5) * (60 / 8)
            detections.append({"angle": max(0, min(180, object_angle)), "distance": float(np.median(distances))})
    return detections
