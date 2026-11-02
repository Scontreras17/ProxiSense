import unittest

import numpy as np

from test_radar.people_counter import DoorwayCounter


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


if __name__ == "__main__":
    unittest.main()
