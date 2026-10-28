
import serial
import re
import time
import math
import numpy as np
import matplotlib.pyplot as plt

from matplotlib.animation import FuncAnimation


# ============== CONFIGURACION ==============

PUERTO = "COM3"
BAUDIOS = 115200

ALCANCE = 2000
UMBRAL_OBJETO = 800

MIN_CELDAS = 1
DIFERENCIA_GRUPO = 250

LECTURAS_HISTORIAL = 3
LECTURAS_MINIMAS = 2

CONFIRMACIONES_NECESARIAS = 2
LECTURAS_PERDIDAS_MAX = 4

TOLERANCIA_ANGULO = 12
TOLERANCIA_DISTANCIA = 350

FACTOR_SUAVIZADO = 0.30

ANGULO_INICIAL = 90
CAMBIO_ANGULO = 5

# ===========================================


try:
    sensor = serial.Serial(PUERTO, BAUDIOS, timeout=0.05)
    time.sleep(2)
    sensor.reset_input_buffer()
except Exception as error:
    print("Error al abrir el sensor:", error)
    raise SystemExit


distancias = np.full((8, 8), 4000.0)
historial = []

angulo = ANGULO_INICIAL
objetivos = []
siguiente_id = 1


# ============== LECTURA DEL SENSOR ==============

def leer_sensor():
    global distancias

    for _ in range(40):
        try:
            linea = sensor.readline().decode(
                "utf-8", errors="ignore"
            ).strip()

            coincidencia = re.match(
                r"y([0-7])\s*:\s*(.*)",
                linea,
                re.IGNORECASE
            )

            if not coincidencia:
                continue

            fila = int(coincidencia.group(1))
            valores = re.findall(
                r"\d+(?:\.\d+)?",
                coincidencia.group(2)
            )

            if len(valores) >= 8:
                distancias[fila] = [
                    float(v) for v in valores[:8]
                ]

        except (ValueError, serial.SerialException):
            continue


# ============== ESTABILIZAR MATRIZ ==============

def obtener_matriz_estable():
    if len(historial) < LECTURAS_MINIMAS:
        return None, None

    matrices = np.array(historial)

    validas = (matrices > 0) & (matrices < 4000)
    cantidad = np.sum(validas, axis=0)
    estables = cantidad >= LECTURAS_MINIMAS

    resultado = np.full((8, 8), 4000.0)

    for fila in range(8):
        for columna in range(8):
            valores = matrices[:, fila, columna]
            valores = valores[
                (valores > 0) & (valores < 4000)
            ]

            if len(valores) >= LECTURAS_MINIMAS:
                resultado[fila, columna] = np.median(valores)

    return resultado, estables


# ============== DETECTAR GRUPOS ==============

def detectar_objetos(matriz, estables):
    validas = (
        estables
        & (matriz > 0)
        & (matriz < 4000)
        & (matriz <= UMBRAL_OBJETO)
    )

    visitadas = np.zeros((8, 8), dtype=bool)
    detecciones = []

    for fila in range(8):
        for columna in range(8):

            if visitadas[fila, columna]:
                continue

            if not validas[fila, columna]:
                continue

            grupo = [(fila, columna)]
            pendientes = [(fila, columna)]
            visitadas[fila, columna] = True

            while pendientes:
                f, c = pendientes.pop()

                vecinos = [
                    (f - 1, c),
                    (f + 1, c),
                    (f, c - 1),
                    (f, c + 1)
                ]

                for nf, nc in vecinos:
                    if not (0 <= nf < 8 and 0 <= nc < 8):
                        continue

                    if visitadas[nf, nc] or not validas[nf, nc]:
                        continue

                    diferencia = abs(
                        matriz[nf, nc] - matriz[f, c]
                    )

                    if diferencia <= DIFERENCIA_GRUPO:
                        visitadas[nf, nc] = True
                        pendientes.append((nf, nc))
                        grupo.append((nf, nc))

            if len(grupo) < MIN_CELDAS:
                continue

            columnas = [c for f, c in grupo]
            medidas = [matriz[f, c] for f, c in grupo]

            columna_central = float(np.mean(columnas))
            distancia = float(np.median(medidas))

            angulo_objeto = (
                angulo + (columna_central - 3.5) * (60 / 8)
            )

            angulo_objeto = max(
                0, min(180, angulo_objeto)
            )

            detecciones.append({
                "angulo": angulo_objeto,
                "distancia": distancia
            })

    return detecciones


# ============== SEGUIMIENTO DE OBJETIVOS ==============

def actualizar_objetivos(detecciones):
    global objetivos, siguiente_id

    for objetivo in objetivos:
        objetivo["asignado"] = False
        objetivo["perdido"] += 1

    pares = []

    # Buscar objetivos existentes cercanos a cada deteccion.
    for i, objetivo in enumerate(objetivos):
        for j, deteccion in enumerate(detecciones):

            diferencia_angulo = abs(
                objetivo["angulo"] - deteccion["angulo"]
            )

            diferencia_distancia = abs(
                objetivo["distancia"] - deteccion["distancia"]
            )

            if (
                diferencia_angulo <= TOLERANCIA_ANGULO
                and diferencia_distancia <= TOLERANCIA_DISTANCIA
            ):
                coste = (
                    diferencia_angulo / TOLERANCIA_ANGULO
                    + diferencia_distancia / TOLERANCIA_DISTANCIA
                )

                pares.append((coste, i, j))

    pares.sort(key=lambda p: p[0])

    objetivos_usados = set()
    detecciones_usadas = set()

    for coste, i, j in pares:
        if i in objetivos_usados or j in detecciones_usadas:
            continue

        objetivo = objetivos[i]
        deteccion = detecciones[j]

        factor = FACTOR_SUAVIZADO

        objetivo["angulo"] = (
            objetivo["angulo"] * (1 - factor)
            + deteccion["angulo"] * factor
        )

        objetivo["distancia_anterior"] = objetivo["distancia"]

        objetivo["distancia"] = (
            objetivo["distancia"] * (1 - factor)
            + deteccion["distancia"] * factor
        )

        objetivo["confirmaciones"] += 1
        objetivo["perdido"] = 0
        objetivo["ultima_deteccion"] = time.time()
        objetivo["asignado"] = True

        objetivos_usados.add(i)
        detecciones_usadas.add(j)

    # Crear nuevos objetivos provisionales.
    for j, deteccion in enumerate(detecciones):
        if j in detecciones_usadas:
            continue

        objetivos.append({
            "id": siguiente_id,
            "angulo": deteccion["angulo"],
            "distancia": deteccion["distancia"],
            "distancia_anterior": deteccion["distancia"],
            "confirmaciones": 1,
            "perdido": 0,
            "ultima_deteccion": time.time(),
            "asignado": True
        })

        siguiente_id += 1

    # Eliminar objetivos que han permanecido ausentes demasiado tiempo.
    objetivos = [
        objetivo for objetivo in objetivos
        if objetivo["perdido"] <= LECTURAS_PERDIDAS_MAX
    ]


# ============== INTERFAZ ==============

plt.style.use("dark_background")

fig = plt.figure(figsize=(11, 8))
ax = fig.add_subplot(111, projection="polar")

fig.patch.set_facecolor("#050a08")
ax.set_facecolor("#050a08")

ax.set_theta_zero_location("E")
ax.set_theta_direction(1)
ax.set_thetamin(0)
ax.set_thetamax(180)
ax.set_ylim(0, ALCANCE)

ax.set_title(
    "TACTICAL RADAR | BETA 4",
    color="#42ff83",
    fontsize=16,
    pad=20
)

ax.set_thetagrids(
    [0, 30, 60, 90, 120, 150, 180],
    labels=["0°", "30°", "60°", "90°", "120°", "150°", "180°"],
    color="#42ff83"
)

ax.set_rgrids(
    [500, 1000, 1500, 2000],
    labels=["500 mm", "1000 mm", "1500 mm", "2000 mm"],
    color="#42ff83",
    alpha=0.6
)

ax.grid(color="#1b7040", alpha=0.65)

linea, = ax.plot(
    [math.radians(angulo), math.radians(angulo)],
    [0, ALCANCE],
    color="#42ff83",
    linewidth=1.5
)

puntos_objetos, = ax.plot(
    [],
    [],
    "o",
    color="red",
    markersize=9,
    markeredgecolor="#ff7777",
    linestyle="None"
)

etiquetas = []

estado = ax.text(
    0.5, -0.10,
    "ESPERANDO LECTURAS...",
    transform=ax.transAxes,
    ha="center",
    color="#42ff83",
    fontsize=11
)

panel = ax.text(
    0.02, 0.97,
    "",
    transform=ax.transAxes,
    ha="left",
    va="top",
    color="#b8ffc9",
    fontsize=9,
    family="monospace"
)


# ============== ACTUALIZACION ==============

def actualizar(_):
    leer_sensor()

    historial.append(distancias.copy())

    while len(historial) > LECTURAS_HISTORIAL:
        historial.pop(0)

    matriz, estables = obtener_matriz_estable()

    if matriz is None:
        estado.set_text("ESTABILIZANDO LECTURAS...")
        return linea, puntos_objetos, estado, panel, *etiquetas

    detecciones = detectar_objetos(matriz, estables)
    actualizar_objetivos(detecciones)

    activos = [
        objetivo for objetivo in objetivos
        if objetivo["confirmaciones"] >= CONFIRMACIONES_NECESARIAS
        and objetivo["perdido"] <= LECTURAS_PERDIDAS_MAX
    ]

    angulos = [
        math.radians(objetivo["angulo"])
        for objetivo in activos
    ]

    radios = [
        objetivo["distancia"]
        for objetivo in activos
    ]

    puntos_objetos.set_data(angulos, radios)

    while len(etiquetas) < len(activos):
        etiqueta = ax.text(
            0, 0, "",
            color="#ff7777",
            fontsize=8,
            ha="center"
        )
        etiquetas.append(etiqueta)

    lineas_panel = []

    for i, objetivo in enumerate(activos):
        etiqueta = etiquetas[i]

        etiqueta.set_position((
            math.radians(objetivo["angulo"]),
            min(ALCANCE, objetivo["distancia"] + 80)
        ))

        etiqueta.set_text("OBJ-{:02d}".format(objetivo["id"]))
        etiqueta.set_visible(True)

        tiempo = time.time() - objetivo["ultima_deteccion"]

        if objetivo["perdido"] == 0:
            estado_objeto = "CONFIRMADO"
        else:
            estado_objeto = "ESPERANDO"

        lineas_panel.append(
            "OBJ-{:02d} | {:4.0f} mm | {}".format(
                objetivo["id"],
                objetivo["distancia"],
                estado_objeto
            )
        )

    for i in range(len(activos), len(etiquetas)):
        etiquetas[i].set_visible(False)

    panel.set_text("\n".join(lineas_panel[:10]))

    linea.set_data(
        [math.radians(angulo), math.radians(angulo)],
        [0, ALCANCE]
    )

    estado.set_text(
        "OBJETIVOS: {} | DETECCIONES: {}".format(
            len(activos), len(detecciones)
        )
    )

    estado.set_color(
        "#ff4444" if activos else "#42ff83"
    )

    return linea, puntos_objetos, estado, panel, *etiquetas


# ============== CONTROLES ==============

def pulsar_tecla(evento):
    global angulo

    if evento.key == "left":
        angulo = max(0, angulo - CAMBIO_ANGULO)

    elif evento.key == "right":
        angulo = min(180, angulo + CAMBIO_ANGULO)

    elif evento.key == " ":
        puntos_objetos.set_data([], [])

    elif evento.key == "escape":
        plt.close()


fig.canvas.mpl_connect("key_press_event", pulsar_tecla)

animacion = FuncAnimation(
    fig,
    actualizar,
    interval=100,
    blit=False,
    cache_frame_data=False
)

print("Radar Beta 4 iniciado.")
print("Flechas izquierda/derecha: ajustar angulo.")
print("ESPACIO: limpiar visualmente los puntos.")
print("ESC: cerrar.")

try:
    plt.show()
finally:
    sensor.close()
