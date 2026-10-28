"""Calibracion de fondo: aprende la habitacion vacia y separa lo que es nuevo.

Para cada una de las 64 celdas se guarda lo mas cerca que llego a medir el fondo (percentil bajo, que
ignora lecturas espurias aisladas). Despues, una celda cuenta como objeto solo si mide mas cerca
que eso por un margen. Las celdas que casi nunca devuelven señal se tratan como "sin fondo". Asi paredes, mesas o
el propio soporte del sensor dejan de aparecer como objetivos permanentes.
"""
from __future__ import annotations

import json
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence

import numpy as np

from .config import BaselineConfig

NO_RETURN_MM = 4000.0


@dataclass(frozen=True)
class Baseline:
    near_mm: np.ndarray         # 8x8 limite cercano del fondo (percentil bajo); 4000 = la celda no devuelve señal
    median_mm: np.ndarray       # 8x8 distancia tipica del fondo (informativa)
    valid_ratio: np.ndarray     # 8x8 fraccion de lecturas validas durante la calibracion
    spread_mm: np.ndarray       # 8x8 dispersion (p95 - p5) de las lecturas: indica si la escena estaba quieta
    margin_mm: float
    frames: int
    created: str

    @classmethod
    def from_frames(cls, frames: Sequence[np.ndarray], config: BaselineConfig = BaselineConfig()) -> "Baseline":
        if len(frames) < 5:
            raise ValueError("Se necesitan al menos 5 lecturas para calibrar el fondo.")
        stack = np.array(frames, dtype=float)
        valid = (stack > 0) & (stack < NO_RETURN_MM)
        masked = np.where(valid, stack, np.nan)
        ratio = valid.mean(axis=0)
        with np.errstate(all="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)  # celdas sin ninguna lectura valida
            median = np.nanmedian(masked, axis=0)
            near = np.nanpercentile(masked, config.near_percentile, axis=0)
            spread = np.nan_to_num(np.nanpercentile(masked, 95, axis=0) - np.nanpercentile(masked, 5, axis=0), nan=0.0)
        has_background = ratio >= config.min_valid_ratio
        median = np.where(has_background, np.nan_to_num(median, nan=NO_RETURN_MM), NO_RETURN_MM)
        near = np.where(has_background, np.nan_to_num(near, nan=NO_RETURN_MM), NO_RETURN_MM)
        return cls(near, median, ratio, spread, config.margin_mm, len(frames), datetime.now().isoformat(timespec="seconds"))

    def unstable_cells(self, max_spread_mm: float = 300.0) -> int:
        """Celdas cuyas lecturas variaron mucho durante la calibracion (escena en movimiento)."""
        return int((self.spread_mm > max_spread_mm).sum())

    def threshold_mm(self) -> np.ndarray:
        """Distancia maxima a la que una celda se considera objeto nuevo."""
        return self.near_mm - self.margin_mm

    def foreground(self, matrix: np.ndarray) -> np.ndarray:
        """Mascara 8x8 de celdas con lectura valida y mas cercana que todo lo visto en el fondo."""
        valid = (matrix > 0) & (matrix < NO_RETURN_MM)
        had_background = self.near_mm < NO_RETURN_MM
        return valid & (~had_background | (matrix <= self.threshold_mm()))

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "created": self.created, "frames": self.frames, "margin_mm": self.margin_mm,
            "near_mm": np.round(self.near_mm, 1).tolist(),
            "median_mm": np.round(self.median_mm, 1).tolist(),
            "valid_ratio": np.round(self.valid_ratio, 3).tolist(),
            "spread_mm": np.round(self.spread_mm, 1).tolist(),
        }
        path.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Baseline":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        arrays = [np.array(data[key], dtype=float) for key in ("near_mm", "median_mm", "valid_ratio", "spread_mm")]
        if any(a.shape != (8, 8) for a in arrays):
            raise ValueError(f"{path}: la linea base debe ser de 8x8.")
        return cls(*arrays, float(data["margin_mm"]), int(data["frames"]), str(data["created"]))

    def summary(self) -> str:
        known = int((self.near_mm < NO_RETURN_MM).sum())
        return f"{self.frames} lecturas, {known}/64 celdas con fondo, margen {self.margin_mm:.0f} mm, creada {self.created}"
