"""Interfaz grafica: radar polar y, opcionalmente, mapa de calor 8x8."""
from __future__ import annotations

import math

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation

from .baseline import Baseline
from .config import RadarConfig
from .processing import FrameStabilizer, detect_objects, object_mask
from .tracking import ObjectTracker

GREEN = "#42ff83"


def run_radar(sensor, config: RadarConfig, baseline: Baseline | None = None, heatmap: bool = True) -> None:
    """Abre el radar. `sensor` es cualquier fuente con `read_rows()` (LidarSensor o CsvReplaySensor)."""
    angle = config.initial_angle_degrees
    stabilizer, tracker = FrameStabilizer(config), ObjectTracker(config)
    plt.style.use("dark_background")
    if heatmap:
        figure = plt.figure(figsize=(15, 8))
        grid = figure.add_gridspec(1, 2, width_ratios=[1.6, 1])
        axis = figure.add_subplot(grid[0, 0], projection="polar")
        heat_axis = figure.add_subplot(grid[0, 1])
    else:
        figure = plt.figure(figsize=(11, 8))
        axis = figure.add_subplot(111, projection="polar")
        heat_axis = None
    figure.patch.set_facecolor("#050a08"); axis.set_facecolor("#050a08")
    axis.set_theta_zero_location("E"); axis.set_thetamin(0); axis.set_thetamax(180); axis.set_ylim(0, config.max_distance_mm)
    axis.set_title("TACTICAL RADAR | BETA 4", color=GREEN, fontsize=16, pad=20)
    axis.set_thetagrids([0, 30, 60, 90, 120, 150, 180], color=GREEN)
    axis.set_rgrids([500, 1000, 1500, 2000], labels=["500 mm", "1000 mm", "1500 mm", "2000 mm"], color=GREEN, alpha=.6)
    axis.grid(color="#1b7040", alpha=.65)
    beam, = axis.plot([], [], color=GREEN, linewidth=1.5)
    points, = axis.plot([], [], "o", color="red", markersize=9, markeredgecolor="#ff7777", linestyle="None")
    status = axis.text(.5, -.1, "ESPERANDO LECTURAS...", transform=axis.transAxes, ha="center", color=GREEN)
    panel = axis.text(.02, .97, "", transform=axis.transAxes, ha="left", va="top", color="#b8ffc9", family="monospace")
    labels: list = []  # etiquetas OBJ-xx sobre el grafico (como en Radar.py)

    image = marks = None
    if heat_axis is not None:
        palette = plt.get_cmap("viridis_r").copy()
        palette.set_bad("#0b1410")  # celdas sin retorno
        heat_axis.set_facecolor("#0b1410")
        image = heat_axis.imshow(np.full((8, 8), np.nan), cmap=palette, vmin=0, vmax=config.max_distance_mm, interpolation="nearest")
        heat_axis.set_title("MATRIZ 8x8 (mm)", color=GREEN, fontsize=13)
        heat_axis.set_xticks(range(8)); heat_axis.set_yticks(range(8))
        heat_axis.tick_params(colors=GREEN)
        heat_axis.set_xlabel("columna", color=GREEN); heat_axis.set_ylabel("fila", color=GREEN)
        figure.colorbar(image, ax=heat_axis, fraction=.046, pad=.04).ax.tick_params(colors=GREEN)
        marks, = heat_axis.plot([], [], "s", markerfacecolor="none", markeredgecolor="red", markeredgewidth=2, markersize=26, linestyle="None")

    def artists() -> tuple:
        extra = (image, marks) if image is not None else ()
        return (beam, points, status, panel, *extra, *labels)

    def update(_: int):
        nonlocal angle
        frame = sensor.read_rows()
        if image is not None:
            image.set_data(np.where((frame > 0) & (frame < 4000), frame, np.nan))
        stable_frame = stabilizer.add(frame)
        beam.set_data([math.radians(angle), math.radians(angle)], [0, config.max_distance_mm])
        if stable_frame is None:
            status.set_text("ESTABILIZANDO LECTURAS...")
            return artists()
        matrix, stable = stable_frame
        if marks is not None:
            rows, columns = np.nonzero(object_mask(matrix, stable, config, baseline))
            marks.set_data(columns, rows)
        detections = detect_objects(matrix, stable, angle, config, baseline)
        tracker.update(detections)
        active = tracker.active
        points.set_data([math.radians(float(item["angle"])) for item in active], [float(item["distance"]) for item in active])
        while len(labels) < len(active):
            labels.append(axis.text(0, 0, "", color="#ff7777", fontsize=8, ha="center"))
        panel_lines = []
        for label, item in zip(labels, active):
            label.set_position((math.radians(float(item["angle"])), min(config.max_distance_mm, float(item["distance"]) + 80)))
            label.set_text(f"OBJ-{int(item['id']):02d}")
            label.set_visible(True)
            state = "CONFIRMADO" if int(item["missed"]) == 0 else "ESPERANDO"
            panel_lines.append(f"OBJ-{int(item['id']):02d} | {float(item['distance']):4.0f} mm | {state}")
        for label in labels[len(active):]:
            label.set_visible(False)
        panel.set_text("\n".join(panel_lines[:10]))
        status.set_text(f"OBJETIVOS: {len(active)} | DETECCIONES: {len(detections)}" + (" | FONDO CALIBRADO" if baseline else ""))
        status.set_color("#ff4444" if active else GREEN)
        return artists()

    def on_key(event):
        nonlocal angle
        if event.key == "left": angle = max(0, angle - config.angle_step_degrees)
        elif event.key == "right": angle = min(180, angle + config.angle_step_degrees)
        elif event.key == " ": points.set_data([], [])
        elif event.key == "escape": plt.close(figure)

    figure.canvas.mpl_connect("key_press_event", on_key)
    # La animacion debe guardarse en una variable: si no, matplotlib la descarta y el radar nunca se actualiza.
    animation = FuncAnimation(figure, update, interval=100, blit=False, cache_frame_data=False)
    print("Radar iniciado. Flechas: ajustar angulo | ESPACIO: limpiar puntos | ESC: cerrar.")
    plt.show()
    del animation
