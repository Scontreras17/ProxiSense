"""Seguimiento simple de objetivos detectados entre lecturas."""
from __future__ import annotations

import time

from .config import RadarConfig


class ObjectTracker:
    def __init__(self, config: RadarConfig) -> None:
        self.config = config
        self.targets: list[dict[str, float | int]] = []
        self._next_id = 1

    def update(self, detections: list[dict[str, float]]) -> None:
        for target in self.targets:
            target["missed"] = int(target["missed"]) + 1
        pairs: list[tuple[float, int, int]] = []
        for target_index, target in enumerate(self.targets):
            for detection_index, detection in enumerate(detections):
                angle_delta = abs(float(target["angle"]) - detection["angle"])
                distance_delta = abs(float(target["distance"]) - detection["distance"])
                if angle_delta <= self.config.angle_tolerance_degrees and distance_delta <= self.config.distance_tolerance_mm:
                    pairs.append((angle_delta / self.config.angle_tolerance_degrees + distance_delta / self.config.distance_tolerance_mm, target_index, detection_index))
        used_targets, used_detections = set(), set()
        for _, target_index, detection_index in sorted(pairs):
            if target_index in used_targets or detection_index in used_detections:
                continue
            target, detection = self.targets[target_index], detections[detection_index]
            factor = self.config.smoothing_factor
            target["angle"] = float(target["angle"]) * (1 - factor) + detection["angle"] * factor
            target["distance"] = float(target["distance"]) * (1 - factor) + detection["distance"] * factor
            target["confirmations"] = int(target["confirmations"]) + 1
            target["missed"] = 0
            target["last_seen"] = time.time()
            used_targets.add(target_index); used_detections.add(detection_index)
        for index, detection in enumerate(detections):
            if index not in used_detections:
                self.targets.append({"id": self._next_id, "angle": detection["angle"], "distance": detection["distance"], "confirmations": 1, "missed": 0, "last_seen": time.time()})
                self._next_id += 1
        self.targets = [target for target in self.targets if int(target["missed"]) <= self.config.maximum_missed_frames]

    @property
    def active(self) -> list[dict[str, float | int]]:
        return [target for target in self.targets if int(target["confirmations"]) >= self.config.confirmations_needed and int(target["missed"]) <= self.config.maximum_missed_frames]
