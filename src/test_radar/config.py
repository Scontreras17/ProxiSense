"""Valores de configuracion del radar.

Los parametros pueden cambiarse desde la linea de comandos para no editar codigo.
Las credenciales (Telegram) y el puerto se leen de variables de entorno o de un
archivo `.env` (ver `.env.example`), nunca del codigo.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SerialConfig:
    port: str = "COM3"
    baudrate: int = 115200
    timeout: float = 0.2
    warmup_seconds: float = 2.0


@dataclass(frozen=True)
class RadarConfig:
    max_distance_mm: int = 2000
    object_threshold_mm: int = 800
    group_distance_delta_mm: int = 250
    history_frames: int = 3
    minimum_stable_frames: int = 2
    confirmations_needed: int = 2
    maximum_missed_frames: int = 4
    angle_tolerance_degrees: int = 12
    distance_tolerance_mm: int = 350
    smoothing_factor: float = 0.30
    initial_angle_degrees: int = 90
    angle_step_degrees: int = 5


@dataclass(frozen=True)
class BaselineConfig:
    """Calibracion de fondo: que cuenta como 'objeto nuevo' respecto a la habitacion vacia."""
    path: str = "data/baseline.json"
    duration_seconds: float = 10.0
    margin_mm: float = 150.0        # un objeto debe estar al menos este margen mas cerca que el fondo
    near_percentile: float = 5.0    # el "fondo cercano" ignora el 5 % de lecturas mas cercanas (ruido)
    min_valid_ratio: float = 0.05   # celdas con menos retornos validos se consideran 'sin retorno'


@dataclass(frozen=True)
class MonitorConfig:
    """Servicio de presencia con alertas (antes proxisense.py)."""
    distance_mm: float = 1500.0
    confirm_seconds: float = 1.0
    reconnect_seconds: float = 5.0
    privacy_enabled: bool = True
    privacy_start: str = "22:00"
    privacy_end: str = "08:00"


def load_env(path: str | Path | None = None) -> list[Path]:
    """Carga variables desde `.env` sin pisar las ya definidas. Devuelve los archivos leidos."""
    if path is not None:
        candidates = [Path(path)]
    else:
        candidates = [Path.cwd() / ".env"]
        try:
            candidates.append(Path(__file__).resolve().parents[2] / ".env")
        except IndexError:
            pass
    loaded: list[Path] = []
    for candidate in candidates:
        if candidate in loaded or not candidate.is_file():
            continue
        for raw in candidate.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.removeprefix("export ").strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            if key:
                os.environ.setdefault(key, value)
        loaded.append(candidate)
    return loaded


def default_port() -> str:
    return os.environ.get("LIDAR_PORT", SerialConfig.port)
