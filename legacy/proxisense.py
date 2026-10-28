"""ProxiSense: deteccion LiDAR por serie con alertas de Telegram."""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, time as clock_time
from typing import Iterable

import requests
import serial

# CONFIGURACION: completa las credenciales antes de ejecutar.
SERIAL_PORT = "COM3"  # Linux: normalmente /dev/ttyUSB0 o /dev/ttyACM0.
BAUDRATE = 115200
TELEGRAM_BOT_TOKEN = "PON_AQUI_TU_TOKEN"
TELEGRAM_CHAT_ID = "PON_AQUI_TU_CHAT_ID"
DISTANCIA_PERSONA_MM = 1500
DURACION_CONFIRMACION_SEGUNDOS = 1.0
TIEMPO_RECONEXION_SEGUNDOS = 5.0
MODO_PRIVACIDAD_ACTIVO = True
INICIO_PRIVACIDAD = "22:00"
FIN_PRIVACIDAD = "08:00"

@dataclass
class DetectionState:
    """Exige que la presencia se mantenga antes de notificar."""
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
        if now - self.detected_since >= DURACION_CONFIRMACION_SEGUNDOS and not self.notification_sent:
            self.notification_sent = True
            return True
        return False

def parse_distances(line: str) -> list[float]:
    """Acepta `742` y filas 8x8 como `y0: 1200 1300 ...`. Todo esta en mm."""
    line = re.sub(r"^\s*y[0-7]\s*:\s*", "", line, flags=re.IGNORECASE)
    return [float(value) for value in re.findall(r"\d+(?:\.\d+)?", line)]

def parse_clock(value: str) -> clock_time:
    return datetime.strptime(value, "%H:%M").time()

def privacy_active(now: datetime | None = None) -> bool:
    if not MODO_PRIVACIDAD_ACTIVO:
        return False
    current = (now or datetime.now()).time()
    start, end = parse_clock(INICIO_PRIVACIDAD), parse_clock(FIN_PRIVACIDAD)
    if start == end:
        return True
    return start <= current < end if start < end else current >= start or current < end

def telegram_configured() -> bool:
    return not (TELEGRAM_BOT_TOKEN.startswith("PON_AQUI") or TELEGRAM_CHAT_ID.startswith("PON_AQUI"))

def send_telegram_alert(distance_mm: float) -> bool:
    """Un fallo de red queda registrado, sin detener el servicio."""
    if not telegram_configured():
        logging.warning("Telegram no esta configurado: alerta omitida.")
        return False
    message = ("ProxiSense detecto una presencia sostenida.\n"
               f"Distancia minima: {distance_mm:.0f} mm.\n"
               f"Hora: {datetime.now():%Y-%m-%d %H:%M:%S}")
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=10,
        )
        response.raise_for_status()
        logging.info("Alerta de Telegram enviada.")
        return True
    except requests.RequestException as error:
        logging.error("No se pudo enviar Telegram: %s", error)
        return False

def process_stream(connection: serial.Serial, state: DetectionState) -> None:
    while True:
        raw_line = connection.readline()
        if not raw_line:
            continue
        distances = parse_distances(raw_line.decode("utf-8", errors="replace").strip())
        valid = [value for value in distances if 0 < value < 10000]
        if not valid:
            continue
        nearest = min(valid)
        if state.update(any(value <= DISTANCIA_PERSONA_MM for value in valid), time.monotonic()):
            if privacy_active():
                logging.info("Presencia a %.0f mm; alerta silenciada por privacidad.", nearest)
            else:
                logging.warning("Presencia confirmada a %.0f mm.", nearest)
                send_telegram_alert(nearest)

def run() -> None:
    """Servicio de fondo con reconexion ante una desconexion USB-C."""
    state = DetectionState()
    logging.info("ProxiSense iniciado: %s a %s baudios.", SERIAL_PORT, BAUDRATE)
    while True:
        try:
            with serial.Serial(SERIAL_PORT, BAUDRATE, timeout=1) as connection:
                logging.info("Sensor conectado en %s.", SERIAL_PORT)
                connection.reset_input_buffer()
                process_stream(connection, state)
        except serial.SerialException as error:
            logging.error("Sensor no disponible o desconectado: %s", error)
        except (OSError, UnicodeError) as error:
            logging.error("Error durante la lectura: %s", error)
        except KeyboardInterrupt:
            logging.info("ProxiSense detenido por el usuario.")
            return
        logging.info("Reintentando en %.0f segundos...", TIEMPO_RECONEXION_SEGUNDOS)
        time.sleep(TIEMPO_RECONEXION_SEGUNDOS)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    run()


