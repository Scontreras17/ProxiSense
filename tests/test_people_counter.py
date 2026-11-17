import unittest

import numpy as np

from test_radar.baseline import Baseline
from test_radar.config import BaselineConfig
from test_radar.people_counter import DoorwayCounter, largest_group


def frame_at(column: int) -> np.ndarray:
    frame = np.full((8, 8), 4000.0)
    frame[3:5, column:column + 1] = 900.0
    return frame


class DoorwayCounterTests(unittest.TestCase):
    def test_counts_left_to_right_as_entry(self) -> None:
        counter = DoorwayCounter(entry_side="left", initial_occupancy=2, stable_frames=2)
        counter.update(frame_at(1), now=1.00)
        counter.update(frame_at(1), now=1.01)
        counter.update(frame_at(3), now=1.02)
        counter.update(frame_at(6), now=1.03)
        event = counter.update(frame_at(6), now=1.04)
        self.assertIsNotNone(event)
        self.assertEqual(event["direction"], "in")
        self.assertEqual(event["people_in"], 1)
        self.assertEqual(event["occupancy"], 3)

    def test_counts_reverse_crossing_as_exit(self) -> None:
        counter = DoorwayCounter(entry_side="left", stable_frames=1, cooldown_seconds=0.1)
        counter.update(frame_at(6), now=1.00)
        event = counter.update(frame_at(1), now=1.20)
        self.assertIsNotNone(event)
        self.assertEqual(event["direction"], "out")
        self.assertEqual(event["people_out"], 1)
        self.assertEqual(event["occupancy"], 0)

    def test_occupancy_never_goes_negative(self) -> None:
        counter = DoorwayCounter(entry_side="left", stable_frames=1, cooldown_seconds=0.1)
        counter.update(frame_at(6), now=1.00)
        counter.update(frame_at(1), now=1.20)
        self.assertEqual(counter.snapshot.occupancy, 0)

    def test_rejects_invalid_entry_side(self) -> None:
        with self.assertRaises(ValueError):
            DoorwayCounter(entry_side="up")


def room_with_wall(wall_mm: float = 1200.0) -> np.ndarray:
    return np.full((8, 8), wall_mm)


def person_in(room: np.ndarray, column: int) -> np.ndarray:
    frame = room.copy()
    frame[3:6, column:column + 1] = 700.0
    return frame


class BaselineCounterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.room = room_with_wall()
        self.baseline = Baseline.from_frames([self.room] * 10, BaselineConfig(margin_mm=150.0))

    def test_static_background_inside_threshold_is_not_presence(self) -> None:
        without = DoorwayCounter(threshold_mm=1800)
        without.update(self.room, now=1.0)
        self.assertEqual(without.snapshot.active_cells, 64)  # sin fondo, la pared cuenta como presencia
        with_baseline = DoorwayCounter(threshold_mm=1800, baseline=self.baseline)
        self.assertIsNone(with_baseline.update(self.room, now=1.0))
        self.assertEqual(with_baseline.snapshot.active_cells, 0)

    def test_person_crossing_is_counted_over_background(self) -> None:
        counter = DoorwayCounter(entry_side="left", stable_frames=2, baseline=self.baseline)
        events = [counter.update(person_in(self.room, column), now=1.0 + i * 0.066)
                  for i, column in enumerate([1, 1, 2, 3, 4, 5, 6, 6])]
        events = [event for event in events if event]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["direction"], "in")

    def test_single_cell_noise_is_ignored(self) -> None:
        counter = DoorwayCounter(entry_side="left", stable_frames=1, cooldown_seconds=0.0, baseline=self.baseline)
        noisy_left, noisy_right = self.room.copy(), self.room.copy()
        noisy_left[4, 1] = 500.0
        noisy_right[4, 6] = 500.0
        self.assertIsNone(counter.update(noisy_left, now=1.0))
        self.assertIsNone(counter.update(noisy_right, now=1.1))
        self.assertEqual(counter.snapshot.people_in + counter.snapshot.people_out, 0)

    def test_largest_group_picks_biggest_connected_blob(self) -> None:
        mask = np.zeros((8, 8), dtype=bool)
        mask[0, 0] = True
        mask[3:6, 5:7] = True
        group, kept = largest_group(mask, min_cells=2)
        self.assertEqual(len(group), 6)
        self.assertEqual(kept, 6)


if __name__ == "__main__":
    unittest.main()
