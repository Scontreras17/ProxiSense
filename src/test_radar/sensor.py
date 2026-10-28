"""Comunicacion y parseo de las tramas emitidas por el LiDAR."""
from __future__ import annotations

import re
import time
from collections.abc import Iterator

import numpy as np
import serial

from .config import SerialConfig

_ROW_PATTERN = re.compile(r"y([0-7])\s*:\s*(.*)", re.IGNORECASE)
_NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?")


def parse_row(line: str) -> tuple[int, list[float]] | None:
    """Convierte una linea `y0: ...` en su indice de fila y ocho distancias."""
    match = _ROW_PATTERN.match(line.strip())
    if not match:
        return None
    values = [float(value) for value in _NUMBER_PATTERN.findall(match.group(2))]
    if len(values) < 8:
        return None
    return int(match.group(1)), values[:8]


class LidarSensor:
    """Sensor LiDAR 8x8 conectado mediante un puerto serie."""

    def __init__(self, config: SerialConfig) -> None:
        self.config = config
        self.connection: serial.Serial | None = None
        self._latest_matrix = np.full((8, 8), 4000.0)

    def open(self) -> None:
        self.connection = serial.Serial(
            self.config.port, self.config.baudrate, timeout=self.config.timeout
        )
        time.sleep(self.config.warmup_seconds)
        self.connection.reset_input_buffer()

    def close(self) -> None:
        if self.connection and self.connection.is_open:
            self.connection.close()

    def __enter__(self) -> "LidarSensor":
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def lines(self) -> Iterator[str]:
        if self.connection is None:
            raise RuntimeError("El sensor no esta conectado.")
        while True:
            line = self.connection.readline().decode("utf-8", errors="replace").strip()
            if line:
                yield line

    def read_rows(self, maximum_lines: int = 40) -> np.ndarray:
        """Lee las tramas disponibles y devuelve una matriz parcial 8x8.

        Las celdas sin datos se representan con 4000 mm, igual que el programa original.
        """
        if self.connection is None:
            raise RuntimeError("El sensor no esta conectado.")
        for _ in range(maximum_lines):
            line = self.connection.readline().decode("utf-8", errors="ignore")
            parsed = parse_row(line)
            if parsed is not None:
                row, values = parsed
                self._latest_matrix[row] = values
        return self._latest_matrix.copy()
