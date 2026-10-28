import serial

try:
    with serial.Serial("COM3", 115200, timeout=2) as lidar:
        print("Conectado. Leyendo datos reales...\n")

        for i in range(20):
            datos = lidar.readline()
            texto = datos.decode(
                "utf-8", errors="replace"
            ).strip()

            print(repr(texto))

except serial.SerialException as error:
    print("Error de conexión:", error)