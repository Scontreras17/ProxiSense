import serial
import time

PUERTO = "COM3"
BAUDIOS = 115200

try:
    lidar = serial.Serial(PUERTO, BAUDIOS, timeout=2)

    time.sleep(2)
    print("LiDAR conectado. Leyendo datos...\n")

    while True:
        datos = lidar.readline()

        if datos:
            texto = datos.decode("utf-8", errors="replace").strip()
            print(texto)

except serial.SerialException as error:
    print("Error al conectar con el sensor:", error)

except KeyboardInterrupt:
    print("\nLectura detenida.")

finally:
    if "lidar" in locals() and lidar.is_open:
        lidar.close()