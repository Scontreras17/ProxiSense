"""Envio de eventos y latidos al servidor ProxiSense (AWS) sin bloquear el monitor.

Todo el trabajo de red ocurre en un hilo aparte. Si el servidor no responde, el monitor sigue
funcionando: los eventos se guardan en memoria y se reintentan; los latidos se descartan.
"""
from __future__ import annotations

import logging
import os
import socket
import threading
import time
from collections import deque

import numpy as np
import requests

MAX_PENDING_EVENTS = 200


class Reporter:
    def __init__(self, url: str, api_key: str, device: str | None = None, heartbeat_seconds: float = 5.0, timeout: float = 5.0) -> None:
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.device = (device or socket.gethostname() or "proxisense")[:64]
        self.heartbeat_seconds = heartbeat_seconds
        self.timeout = timeout
        self._events: deque[dict] = deque(maxlen=MAX_PENDING_EVENTS)
        self._heartbeat: dict | None = None
        self._last_heartbeat = 0.0
        self._last_error_log = 0.0
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._session = requests.Session()
        self._session.headers.update({"X-API-Key": api_key})
        threading.Thread(target=self._run, name="proxisense-reporter", daemon=True).start()

    @classmethod
    def from_env(cls, url: str | None = None, device: str | None = None) -> "Reporter | None":
        url = url or os.environ.get("PROXISENSE_SERVER_URL", "")
        key = os.environ.get("PROXISENSE_API_KEY", "")
        if not url:
            return None
        if not key:
            logging.warning("Hay servidor (%s) pero falta PROXISENSE_API_KEY: no se enviaran datos.", url)
            return None
        return cls(url, key, device or os.environ.get("PROXISENSE_DEVICE"))

    # ------------------------------------------------------------ API para el monitor
    def event(self, kind: str, distance_mm: float | None, silenced: bool = False, message: str | None = None) -> None:
        payload = {"device": self.device, "kind": kind, "distance_mm": None if distance_mm is None else round(float(distance_mm), 1),
                   "silenced": silenced, "message": message}
        with self._lock:
            self._events.append(payload)
        self._wake.set()

    def heartbeat(self, frame: np.ndarray | None, nearest_mm: float | None, cells_near: int | None) -> None:
        """Se puede llamar con cada lectura: solo se envia uno cada `heartbeat_seconds`."""
        now = time.monotonic()
        if now - self._last_heartbeat < self.heartbeat_seconds:
            return
        self._last_heartbeat = now
        payload = {"device": self.device, "nearest_mm": None if nearest_mm is None else round(float(nearest_mm), 1), "cells_near": cells_near}
        if frame is not None:
            payload["frame"] = [round(float(v)) for v in np.asarray(frame).reshape(-1)]
        with self._lock:
            self._heartbeat = payload
        self._wake.set()

    # ------------------------------------------------------------ hilo de red
    def _post(self, path: str, payload: dict) -> bool:
        try:
            response = self._session.post(self.url + path, json=payload, timeout=self.timeout)
            if response.status_code == 401:
                self._log_error("El servidor rechazo la clave (PROXISENSE_API_KEY incorrecta).")
                return False
            response.raise_for_status()
            return True
        except requests.RequestException as error:
            self._log_error(f"No se pudo contactar al servidor: {str(error).replace(self.api_key, '***')}")
            return False

    def _log_error(self, message: str) -> None:
        if time.monotonic() - self._last_error_log > 60:   # como maximo un aviso por minuto
            self._last_error_log = time.monotonic()
            logging.warning(message)

    def _run(self) -> None:
        while True:
            self._wake.wait(timeout=1.0)
            self._wake.clear()
            while True:
                with self._lock:
                    event = self._events.popleft() if self._events else None
                if event is None:
                    break
                if not self._post("/api/events", event):
                    with self._lock:
                        self._events.appendleft(event)   # reintentar despues
                    time.sleep(2.0)
                    break
            with self._lock:
                beat, self._heartbeat = self._heartbeat, None
            if beat is not None:
                self._post("/api/heartbeat", beat)
