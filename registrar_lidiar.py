
import serial
import re
import csv
import time
from datetime import datetime

PUERTO = "COM3"
BAUDIOS = 115200
DURACION = 30

ARCHIVO = "mediciones_lidar.csv"

sensor = serial.Serial(
    PUERTO,
    BAUDIOS,
    timeout=0.2
)

time.sleep(2)
sensor.reset_input_buffer()

matriz = [4000] * 64
filas_recibidas = set()

inicio = time.time()
lectura = 0

print("Registrando mediciones del LiDAR...")
print("Duracion:", DURACION, "segundos")
print("No muevas el sensor durante esta prueba.")

try:
    with open(
        ARCHIVO,
        "w",
        newline="",
        encoding="utf-8"
    ) as archivo:

        escritor = csv.writer(archivo)

        encabezado = [
            "tiempo",
            "lectura",
            "filas_recibidas"
        ]

        encabezado += [
            "celda_" + str(i)
            for i in range(64)
        ]

        escritor.writerow(encabezado)

        while time.time() - inicio < DURACION:
            linea = sensor.readline().decode(
                "utf-8",
                errors="ignore"
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
                r"\d+",
                coincidencia.group(2)
            )

            if len(valores) < 8:
                continue

            valores = [
                int(valor)
                for valor in valores[:8]
            ]

            for columna in range(8):
                posicion = fila * 8 + columna
                matriz[posicion] = valores[columna]

            filas_recibidas.add(fila)

            # Guardar una matriz cuando llegan
            # las ocho filas del sensor.
            if len(filas_recibidas) == 8:
                lectura += 1

                escritor.writerow([
                    round(time.time() - inicio, 3),
                    lectura,
                    len(filas_recibidas)
                ] + matriz)

                filas_recibidas.clear()

                print(
                    "Lectura:",
                    lectura,
                    "| Tiempo:",
                    round(time.time() - inicio, 1),
                    "s"
                )

finally:
    sensor.close()

print("\nRegistro terminado.")
print("Archivo guardado:", ARCHIVO)
print("Total de lecturas:", lectura)
