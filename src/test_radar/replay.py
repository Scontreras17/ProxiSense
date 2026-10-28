"""Reproduccion de grabaciones CSV como si fueran un sensor en vivo (sin hardware)."""
from __future__ import annotations

import bisect
import time
from collections.abc import Iterator
from pathlib import Path

import numpy as np

from .recorder import read_csv_frames


class CsvReplaySensor:
    """Mismo contrato que LidarSensor: open/close, read_rows() y lines()."""

    def __init__(self, path: str | Path, speed: float = 1.0, loop: bool = True) -> None:
        if speed <= 0:
            raise ValueError("La velocidad de reproduccion debe ser positiva.")
        self.path, self.speed, self.loop = Path(path), speed, loop
        raw_times, self.frames = read_csv_frames(path)
        start = raw_times[0]
        self.times = [t - start for t in raw_times]
        step = self.times[-1] / (len(self.times) - 1) if len(self.times) > 1 else 0.1
        self.period = self.times[-1] + step
        self._started = time.monotonic()

    def open(self) -> None:
        self._started = time.monotonic()

    def close(self) -> None:
        pass

    def __enter__(self) -> "CsvReplaySensor":
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def read_rows(self, maximum_lines: int = 40) -> np.ndarray:
        """Devuelve la matriz que correspondia al instante actual de la grabacion."""
        position = (time.monotonic() - self._started) * self.speed
        position = position % self.period if self.loop else min(position, self.times[-1])
        index = max(0, bisect.bisect_right(self.times, position) - 1)
        return self.frames[index].copy()

    def lines(self) -> Iterator[str]:
        """Emite las tramas y0..y7 al ritmo original; termina al acabar si no hay bucle."""
        while True:
            base = time.monotonic()
            for moment, frame in zip(self.times, self.frames):
                wait = moment / self.speed - (time.monotonic() - base)
                if wait > 0:
                    time.sleep(wait)
                for row in range(8):
                    yield f"y{row}: " + " ".join(str(int(value)) for value in frame[row])
            if not self.loop:
                return
