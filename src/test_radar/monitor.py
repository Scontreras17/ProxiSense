"""Servicio de presencia: avisa por Telegram cuando algo se queda cerca del LiDAR.

Es el antiguo proxisense.py, con la misma logica (confirmacion sostenida, una alerta por evento,
modo privacidad, reconexion) pero con las credenciales en variables de entorno y, opcionalmente,
ignorando el fondo calibrado.
"""
from __future__ import annotations

import logging
import os
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, time as clock_time

import numpy as np
import requests
import serial

from .baseline import Baseline
from .config import MonitorConfig
from .sensor import parse_row


@dataclass
class DetectionState:
    """Exige que la presencia se mantenga antes de notificar."""
    confirm_seconds: float = 1.0
    detected_since: float | None = None
    notification_sent: bool = False
    last_near_at: float | None = None

    def update(self, object_near: bool, now: float) -> bool:
        if object_near:
            self.last_near_at = now
        elif self.last_near_at is None or now - self.last_near_at > 0.5:
            self.detected_since, self.notification_sent = None, False
            return False
        if self.detected_since is None:
            self.detected_since = now
            return False
        if now - self.detected_since >= self.confirm_seconds and not self.notification_sent:
            self.notification_sent = True
            return True
        return False


def parse_distances(line: str) -> list[float]:
    """Acepta `742` y filas como `y0: 1200 1300 ...`. Todo esta en mm."""
    line = re.sub(r"^\s*y[0-7]\s*:\s*", "", line, flags=re.IGNORECASE)
    return [float(value) for value in re.findall(r"\d+(?:\.\d+)?", line)]


def privacy_active(config: MonitorConfig, now: datetime | None = None) -> bool:
    if not config.privacy_enabled:
        return False
    current = (now or datetime.now()).time()
    start = datetime.strptime(config.privacy_start, "%H:%M").time()
    end = datetime.strptime(config.privacy_end, "%H:%M").time()
    if start == end:
        return True
    return start <= current < end if start < end else current >= start or current < end


class TelegramNotifier:
    """Envia alertas; un fallo de red queda registrado sin detener el servicio."""

    def __init__(self, token: str | None = None, chat_id: str | None = None) -> None:
        self.token = (token if token is not None else os.environ.get("TELEGRAM_BOT_TOKEN", "")).strip()
        self.chat_id = (chat_id if chat_id is not None else os.environ.get("TELEGRAM_CHAT_ID", "")).strip()

    @property
    def configured(self) -> bool:
        return bool(self.token and self.chat_id) and not (self.token.startswith("PON_AQUI") or self.chat_id.startswith("PON_AQUI"))

    def send(self, distance_mm: float) -> bool:
        if not self.configured:
            logging.warning("Telegram no esta configurado (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID): alerta omitida.")
            return False
        message = ("ProxiSense detecto una presencia sostenida.\n"
                   f"Distancia minima: {distance_mm:.0f} mm.\n"
                   f"Hora: {datetime.now():%Y-%m-%d %H:%M:%S}")
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={"chat_id": self.chat_id, "text": message}, timeout=10,
            )
            response.raise_for_status()
            logging.info("Alerta de Telegram enviada.")
            return True
        except requests.RequestException as error:
            # El mensaje de requests incluye la URL, y la URL contiene el token: se oculta.
            logging.error("No se pudo enviar Telegram: %s", str(error).replace(self.token, "***"))
            return False


def process_stream(lines: Iterable[str], state: DetectionState, config: MonitorConfig,
                   baseline: Baseline | None, notifier: TelegramNotifier) -> None:
    matrix = np.full((8, 8), 4000.0)
    for line in lines:
        parsed = parse_row(line)
        if parsed is not None:           # trama 8x8: fila yN
            row, values = parsed
            matrix[row] = values
            visible = (matrix > 0) & (matrix < 4000)
            if baseline is not None:
                visible &= baseline.foreground(matrix)
            valid = matrix[visible].tolist()
        else:                            # una distancia por linea
            valid = [v for v in parse_distances(line) if 0 < v < 10000]
        if not valid:                    # nada nuevo a la vista: rearma el detector si corresponde
            state.update(False, time.monotonic())
            continue
        nearest = min(valid)
        if state.update(nearest <= config.distance_mm, time.monotonic()):
            if privacy_active(config):
                logging.info("Presencia a %.0f mm; alerta silenciada por privacidad.", nearest)
            else:
                logging.warning("Presencia confirmada a %.0f mm.", nearest)
                notifier.send(nearest)


def run_monitor(open_source: Callable[[], object], config: MonitorConfig,
                baseline: Baseline | None, notifier: TelegramNotifier) -> None:
    """Servicio de fondo con reconexion ante una desconexion USB."""
    state = DetectionState(config.confirm_seconds)
    while True:
        try:
            with open_source() as source:
                logging.info("Sensor conectado.")
                process_stream(source.lines(), state, config, baseline, notifier)
            logging.info("La fuente de datos termino.")
            return
        except serial.SerialException as error:
            logging.error("Sensor no disponible o desconectado: %s", error)
        except (OSError, UnicodeError) as error:
            logging.error("Error durante la lectura: %s", error)
        except KeyboardInterrupt:
            logging.info("Monitor detenido por el usuario.")
            return
        logging.info("Reintentando en %.0f segundos...", config.reconnect_seconds)
        time.sleep(config.reconnect_seconds)
