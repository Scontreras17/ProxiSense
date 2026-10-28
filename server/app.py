"""Servidor ProxiSense: recibe eventos y latidos desde casa y los muestra en un panel web.

Variables de entorno:
    PROXISENSE_API_KEY    clave que deben enviar los dispositivos (cabecera X-API-Key). Obligatoria.
    DASHBOARD_PASSWORD    contrasena para abrir el panel en el navegador. Obligatoria.
    DASHBOARD_USER        usuario del panel (por defecto "admin").
    PROXISENSE_DB         ruta de la base SQLite (por defecto data/proxisense.db).
    PROXISENSE_RETENTION_DAYS  dias que se conserva el historial (por defecto 90).

Si falta alguna clave obligatoria, el servidor rechaza las peticiones en vez de quedar abierto.
"""
from __future__ import annotations

import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

STATIC = Path(__file__).resolve().parent / "static"
ONLINE_SECONDS = 30.0        # sin latidos durante este tiempo = "sin señal"
RECENT_EVENTS = 30
HOURS = 24

app = FastAPI(title="ProxiSense", docs_url=None, redoc_url=None, openapi_url=None)
basic = HTTPBasic(auto_error=False)


# ---------------------------------------------------------------- base de datos
def db_path() -> Path:
    return Path(os.environ.get("PROXISENSE_DB", "data/proxisense.db"))


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS devices (
                device TEXT PRIMARY KEY, last_seen REAL NOT NULL,
                nearest_mm REAL, cells_near INTEGER, frame TEXT);
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, device TEXT NOT NULL,
                kind TEXT NOT NULL, distance_mm REAL, silenced INTEGER NOT NULL DEFAULT 0, message TEXT);
            CREATE INDEX IF NOT EXISTS events_ts ON events(ts);
            """
        )
        yield conn
        conn.commit()
    finally:
        conn.close()


def purge_old(conn: sqlite3.Connection) -> None:
    days = float(os.environ.get("PROXISENSE_RETENTION_DAYS", "90"))
    conn.execute("DELETE FROM events WHERE ts < ?", (time.time() - days * 86400,))


# ---------------------------------------------------------------- autenticacion
def _same(a: str, b: str) -> bool:
    return secrets.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def require_device_key(x_api_key: str = Header(default="")) -> None:
    expected = os.environ.get("PROXISENSE_API_KEY", "")
    if not expected:
        raise HTTPException(503, "Servidor sin PROXISENSE_API_KEY configurada.")
    if not _same(x_api_key, expected):
        raise HTTPException(401, "Clave de API invalida.")


def require_dashboard_login(credentials: HTTPBasicCredentials | None = Depends(basic)) -> None:
    password = os.environ.get("DASHBOARD_PASSWORD", "")
    if not password:
        raise HTTPException(503, "Servidor sin DASHBOARD_PASSWORD configurada.")
    user = os.environ.get("DASHBOARD_USER", "admin")
    if credentials is None or not (_same(credentials.username, user) and _same(credentials.password, password)):
        raise HTTPException(401, "Usuario o contrasena incorrectos.", headers={"WWW-Authenticate": 'Basic realm="ProxiSense"'})


# ---------------------------------------------------------------- modelos
class Heartbeat(BaseModel):
    device: str = Field(min_length=1, max_length=64)
    frame: list[float] | None = Field(default=None, min_length=64, max_length=64, description="matriz 8x8 por filas, en mm")
    nearest_mm: float | None = None
    cells_near: int | None = Field(default=None, ge=0, le=64)


class Event(BaseModel):
    device: str = Field(min_length=1, max_length=64)
    kind: str = Field(pattern="^(alert|presence|info)$", description="alert = aviso enviado, presence = detectada pero silenciada, info = otro")
    distance_mm: float | None = None
    silenced: bool = False
    message: str | None = Field(default=None, max_length=300)


# ---------------------------------------------------------------- API para los dispositivos
@app.post("/api/heartbeat", dependencies=[Depends(require_device_key)])
def heartbeat(body: Heartbeat) -> dict[str, bool]:
    import json

    frame = json.dumps([round(v) for v in body.frame]) if body.frame is not None else None
    with connect() as conn:
        conn.execute(
            """INSERT INTO devices(device, last_seen, nearest_mm, cells_near, frame) VALUES(?,?,?,?,?)
               ON CONFLICT(device) DO UPDATE SET last_seen=excluded.last_seen, nearest_mm=excluded.nearest_mm,
               cells_near=excluded.cells_near, frame=COALESCE(excluded.frame, devices.frame)""",
            (body.device, time.time(), body.nearest_mm, body.cells_near, frame),
        )
    return {"ok": True}


@app.post("/api/events", dependencies=[Depends(require_device_key)])
def add_event(body: Event) -> dict[str, bool]:
    with connect() as conn:
        conn.execute(
            "INSERT INTO events(ts, device, kind, distance_mm, silenced, message) VALUES(?,?,?,?,?,?)",
            (time.time(), body.device, body.kind, body.distance_mm, int(body.silenced), body.message),
        )
        conn.execute(
            "INSERT INTO devices(device, last_seen) VALUES(?, ?) ON CONFLICT(device) DO UPDATE SET last_seen=excluded.last_seen",
            (body.device, time.time()),
        )
        purge_old(conn)
    return {"ok": True}


# ---------------------------------------------------------------- panel
def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")


@app.get("/api/state", dependencies=[Depends(require_dashboard_login)])
def state() -> JSONResponse:
    import json

    now = time.time()
    with connect() as conn:
        devices = [
            {
                "device": row["device"], "online": now - row["last_seen"] <= ONLINE_SECONDS,
                "seconds_ago": round(now - row["last_seen"], 1), "nearest_mm": row["nearest_mm"],
                "cells_near": row["cells_near"], "frame": json.loads(row["frame"]) if row["frame"] else None,
            }
            for row in conn.execute("SELECT * FROM devices ORDER BY device")
        ]
        events = [
            {"ts": _iso(row["ts"]), "device": row["device"], "kind": row["kind"], "distance_mm": row["distance_mm"],
             "silenced": bool(row["silenced"]), "message": row["message"]}
            for row in conn.execute("SELECT * FROM events ORDER BY ts DESC LIMIT ?", (RECENT_EVENTS,))
        ]
        buckets = [{"alerts": 0, "presences": 0} for _ in range(HOURS)]
        for row in conn.execute(
            "SELECT CAST((? - ts) / 3600 AS INTEGER) AS age, kind, COUNT(*) AS n FROM events "
            "WHERE ts > ? AND kind IN ('alert','presence') GROUP BY age, kind", (now, now - HOURS * 3600)
        ):
            if 0 <= row["age"] < HOURS:
                buckets[HOURS - 1 - row["age"]]["alerts" if row["kind"] == "alert" else "presences"] += row["n"]
    for index, bucket in enumerate(buckets):
        bucket["hour_start"] = _iso(now - (HOURS - index) * 3600)
    return JSONResponse({"now": _iso(now), "online_seconds": ONLINE_SECONDS, "devices": devices, "events": events, "hourly": buckets},
                        headers={"Cache-Control": "no-store"})


@app.get("/", dependencies=[Depends(require_dashboard_login)])
def dashboard() -> FileResponse:
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
