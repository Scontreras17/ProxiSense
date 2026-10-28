"""Registro y lectura de matrices completas LiDAR en formato CSV.

El formato es el mismo de registrar_lidiar.py y habitacion_vacia.csv:
`tiempo, lectura, filas_recibidas, celda_0 ... celda_63`.
Al leer tambien se aceptan las cabeceras en ingles (`elapsed_seconds`, `cell_N`).
"""
from __future__ import annotations

import csv
import re
import time
from pathlib import Path

import numpy as np

from .sensor import LidarSensor, parse_row

_CELL_NAME = re.compile(r"^(?:celda|cell)_(\d+)$", re.IGNORECASE)


def record_csv(sensor: LidarSensor, output: Path, duration_seconds: float) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    matrix = [4000.0] * 64
    rows_received: set[int] = set()
    started_at, count = time.time(), 0
    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["tiempo", "lectura", "filas_recibidas"] + [f"celda_{index}" for index in range(64)])
        for line in sensor.lines():
            parsed = parse_row(line)
            if parsed is None:
                if time.time() - started_at >= duration_seconds:
                    break
                continue
            row, values = parsed
            matrix[row * 8 : row * 8 + 8] = values
            rows_received.add(row)
            if len(rows_received) == 8:
                count += 1
                writer.writerow([round(time.time() - started_at, 3), count, 8] + matrix)
                rows_received.clear()
                print(f"Lectura: {count} | Tiempo: {time.time() - started_at:.1f} s")
            if time.time() - started_at >= duration_seconds:
                break
    return count


def read_csv_frames(path: str | Path) -> tuple[list[float], list[np.ndarray]]:
    """Lee un CSV de mediciones y devuelve (tiempos en segundos, matrices 8x8)."""
    with Path(path).open(newline="", encoding="utf-8") as file:
        reader = csv.reader(file)
        header = [name.strip() for name in next(reader, [])]
        cells = {int(m.group(1)): i for i, name in enumerate(header) if (m := _CELL_NAME.match(name))}
        if sorted(cells) != list(range(64)):
            raise ValueError(f"{path}: se esperaban las columnas celda_0..celda_63 (o cell_0..cell_63).")
        order = [cells[i] for i in range(64)]
        time_column = next((i for i, n in enumerate(header) if n.lower() in {"tiempo", "elapsed_seconds"}), 0)
        times: list[float] = []
        frames: list[np.ndarray] = []
        for number, row in enumerate(reader):
            if len(row) < len(header):
                continue
            try:
                frames.append(np.array([float(row[i]) for i in order]).reshape(8, 8))
                times.append(float(row[time_column]))
            except ValueError:
                continue
    if not frames:
        raise ValueError(f"{path}: no contiene lecturas.")
    return times, frames
