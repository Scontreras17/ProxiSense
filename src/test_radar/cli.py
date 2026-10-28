"""Punto de entrada de linea de comandos.

Ejemplos:
    test-radar radar --port COM3
    test-radar calibrate --port COM3            # con la habitacion vacia
    test-radar monitor --port COM3              # alertas por Telegram
    test-radar radar --replay data/habitacion_vacia.csv   # sin sensor conectado
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import replace
from pathlib import Path

import serial

from .baseline import Baseline
from .config import BaselineConfig, MonitorConfig, RadarConfig, SerialConfig, default_port, load_env
from .recorder import read_csv_frames, record_csv
from .replay import CsvReplaySensor
from .sensor import LidarSensor

_SUPPRESS = argparse.SUPPRESS


def _add_source_options(command: argparse.ArgumentParser, nested: bool) -> None:
    """Opciones de la fuente de datos; se aceptan antes o despues del subcomando."""
    default = lambda value: _SUPPRESS if nested else value  # noqa: E731
    command.add_argument("--port", default=default(default_port()), help="Puerto serie (COM3, /dev/ttyUSB0...). Tambien LIDAR_PORT en .env.")
    command.add_argument("--baudrate", default=default(115200), type=int)
    command.add_argument("--replay", default=default(None), metavar="CSV", help="Usar una grabacion CSV en lugar del sensor.")
    command.add_argument("--speed", default=default(1.0), type=float, help="Velocidad de reproduccion (1 = tiempo real).")
    command.add_argument("--once", default=default(False), action="store_true", help="Reproducir la grabacion una sola vez.")


def _add_baseline_options(command: argparse.ArgumentParser) -> None:
    command.add_argument("--baseline", help=f"Archivo de fondo calibrado (por defecto {BaselineConfig.path} si existe).")
    command.add_argument("--no-baseline", action="store_true", help="Ignorar el fondo calibrado.")


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(prog="test-radar", description="Herramientas para el LiDAR 8x8 (ProxiSense).")
    _add_source_options(command, nested=False)
    actions = command.add_subparsers(dest="action", required=True)

    radar = actions.add_parser("radar", help="Radar polar en tiempo real con mapa de calor 8x8.")
    _add_source_options(radar, nested=True); _add_baseline_options(radar)
    radar.add_argument("--no-heatmap", action="store_true", help="Mostrar solo el radar polar.")

    record = actions.add_parser("record", help="Registrar matrices completas en un CSV.")
    _add_source_options(record, nested=True)
    record.add_argument("--duration", default=30, type=float, help="Duracion en segundos.")
    record.add_argument("--output", default="data/mediciones_lidar.csv", help="Ruta del CSV de salida.")

    stream = actions.add_parser("stream", help="Mostrar las lineas recibidas en pantalla.")
    _add_source_options(stream, nested=True)
    stream.add_argument("--count", default=20, type=int, help="Numero de lineas a mostrar.")

    calibrate = actions.add_parser("calibrate", help="Aprender la habitacion vacia como fondo (con el sensor o desde un CSV).")
    _add_source_options(calibrate, nested=True)
    calibrate.add_argument("--duration", default=BaselineConfig.duration_seconds, type=float, help="Segundos de captura con el sensor.")
    calibrate.add_argument("--margin", default=BaselineConfig.margin_mm, type=float, help="Margen minimo (mm) por debajo del fondo para contar como objeto.")
    calibrate.add_argument("--from-csv", metavar="CSV", help="Calibrar desde una grabacion existente (ej. data/habitacion_vacia.csv).")
    calibrate.add_argument("--start", default=0.0, type=float, help="Con --from-csv: segundo de la grabacion donde empieza el tramo estable.")
    calibrate.add_argument("--end", default=None, type=float, help="Con --from-csv: segundo donde termina el tramo estable.")
    calibrate.add_argument("--output", default=BaselineConfig.path, help="Donde guardar el fondo.")

    monitor = actions.add_parser("monitor", help="Servicio de presencia con alertas por Telegram.")
    _add_source_options(monitor, nested=True); _add_baseline_options(monitor)
    monitor.add_argument("--distance", default=MonitorConfig.distance_mm, type=float, help="Distancia de deteccion en mm.")
    monitor.add_argument("--confirm", default=MonitorConfig.confirm_seconds, type=float, help="Segundos que debe mantenerse la presencia.")
    monitor.add_argument("--no-privacy", action="store_true", help="Desactivar el modo privacidad (silencio nocturno).")
    monitor.add_argument("--privacy-start", default=MonitorConfig.privacy_start, metavar="HH:MM")
    monitor.add_argument("--privacy-end", default=MonitorConfig.privacy_end, metavar="HH:MM")
    monitor.add_argument("--server", metavar="URL", help="Servidor ProxiSense (AWS) al que enviar eventos y estado. Tambien PROXISENSE_SERVER_URL en .env.")
    monitor.add_argument("--device", metavar="NOMBRE", help="Nombre de este dispositivo en el panel (por defecto, el nombre del equipo).")
    return command


def _source_factory(args: argparse.Namespace, timeout: float):
    if args.replay:
        return lambda: CsvReplaySensor(args.replay, speed=args.speed, loop=not args.once)
    config = SerialConfig(port=args.port, baudrate=args.baudrate, timeout=timeout)
    return lambda: LidarSensor(config)


def _resolve_baseline(args: argparse.Namespace) -> Baseline | None:
    if args.no_baseline:
        return None
    path = Path(args.baseline or BaselineConfig.path)
    if not path.is_file():
        if args.baseline:
            raise SystemExit(f"No existe el archivo de fondo: {path}")
        return None
    baseline = Baseline.load(path)
    print(f"Fondo calibrado cargado ({path}): {baseline.summary()}")
    return baseline


def _calibrate(args: argparse.Namespace) -> None:
    settings = replace(BaselineConfig(), margin_mm=args.margin, duration_seconds=args.duration)
    if args.from_csv:
        times, all_frames = read_csv_frames(args.from_csv)
        frames = [f for t, f in zip(times, all_frames) if t >= args.start and (args.end is None or t <= args.end)]
        origin = f"{args.from_csv} ({args.start:g} s a {'el final' if args.end is None else f'{args.end:g} s'})"
    else:
        print(f"Calibrando {settings.duration_seconds:.0f} s. Deja la habitacion vacia y no muevas el sensor...")
        frames, warmup = [], 1.0   # el primer segundo se descarta (el sensor aun esta llenando la matriz)
        with _source_factory(args, 0.2)() as sensor:
            begin = time.monotonic()
            while time.monotonic() - begin < settings.duration_seconds + warmup:
                frame = sensor.read_rows()
                if time.monotonic() - begin >= warmup:
                    frames.append(frame)
        origin = "el sensor"
    if len(frames) < 5:
        raise SystemExit("Muy pocas lecturas en el tramo elegido para calibrar el fondo.")
    baseline = Baseline.from_frames(frames, settings)
    baseline.save(args.output)
    print(f"Fondo calibrado desde {origin}: {baseline.summary()}\nGuardado en {args.output}")
    unstable = baseline.unstable_cells()
    if unstable > 8:
        print(f"AVISO: {unstable}/64 celdas variaron mucho durante la calibracion: la escena no estaba quieta, "
              "asi que el fondo sera poco fiable. Repite con la habitacion vacia y el sensor inmovil"
              + (" o elige un tramo estable con --start/--end." if args.from_csv else "."))


def main(argv: list[str] | None = None) -> None:
    load_env()
    args = parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    try:
        if args.action == "calibrate":
            _calibrate(args)
        elif args.action == "radar":
            from .visualization import run_radar  # matplotlib solo cuando hace falta
            baseline = _resolve_baseline(args)
            with _source_factory(args, 0.05)() as sensor:
                run_radar(sensor, RadarConfig(), baseline, heatmap=not args.no_heatmap)
        elif args.action == "record":
            if args.replay:
                raise SystemExit("record necesita el sensor real; --replay solo sirve para radar, stream y monitor.")
            with _source_factory(args, 0.2)() as sensor:
                total = record_csv(sensor, Path(args.output), args.duration)
            print(f"Registro terminado. Lecturas guardadas: {total}. Archivo: {args.output}")
        elif args.action == "monitor":
            from .monitor import TelegramNotifier, run_monitor
            from .reporter import Reporter
            config = MonitorConfig(distance_mm=args.distance, confirm_seconds=args.confirm, privacy_enabled=not args.no_privacy,
                                   privacy_start=args.privacy_start, privacy_end=args.privacy_end)
            notifier = TelegramNotifier()
            if not notifier.configured:
                logging.warning("Telegram sin configurar: copia .env.example a .env y completa TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID.")
            baseline = _resolve_baseline(args)
            logging.info("Monitor iniciado: alerta a %.0f mm sostenidos %.1f s.", config.distance_mm, config.confirm_seconds)
            reporter = Reporter.from_env(args.server, args.device)
            if reporter is not None:
                logging.info("Enviando estado y eventos a %s como '%s'.", reporter.url, reporter.device)
            run_monitor(_source_factory(args, 1.0), config, baseline, notifier, reporter)
            if reporter is not None:
                time.sleep(1.0)   # deja salir los ultimos eventos antes de cerrar
        else:  # stream
            with _source_factory(args, 0.2)() as sensor:
                for index, line in zip(range(args.count), sensor.lines()):
                    print(f"{index + 1:02d}: {line!r}")
    except serial.SerialException as error:
        raise SystemExit(f"No se pudo abrir {args.port}: {error}") from error
    except KeyboardInterrupt:
        print("\nDetenido por el usuario.", file=sys.stderr)


if __name__ == "__main__":
    main()
