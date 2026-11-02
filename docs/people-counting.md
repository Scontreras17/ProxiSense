# Conteo experimental de personas por puerta

Esta versión añade un comando local de experimentación para contar cruces laterales con el LiDAR 8×8.

## Ejecutar

```bash
test-radar count --port COM3
```

En Windows también se puede usar:

```bash
python -m test_radar.cli count --port COM3
```

Opciones útiles:

- `--target-ms 10`: intervalo objetivo de 10 ms (100 Hz). El programa limita el ritmo si puede, pero muestra la frecuencia real alcanzada; el sensor/puerto serie puede ser más lento.
- `--threshold 1800`: distancia máxima en mm para considerar celdas de la zona.
- `--entry-side left` o `right`: lado desde el que una detección debe cruzar para contar entrada.
- `--initial-occupancy N`: ocupación conocida al iniciar.
- `--server URL --device nombre`: envío de telemetría a AWS. También puede configurarse con `PROXISENSE_SERVER_URL`, `PROXISENSE_API_KEY` y `PROXISENSE_DEVICE` en `.env`.

## Montaje experimental

Coloca el sensor fijo y orientado para que el paso por la puerta se proyecte de izquierda a derecha (o al revés) sobre las columnas de la matriz. Evita que una pared u objeto fijo ocupe la zona de detección. La orientación exacta depende de cómo esté montado el sensor; configura `--entry-side` según el sentido físico de entrada.

Haz pruebas con una persona a la vez y compara el contador con un registro manual. Reinicia el proceso para una nueva sesión. Para buses, configura la ocupación inicial antes de comenzar; la ocupación estimada es entradas menos salidas más ese valor inicial.

## Limitaciones

- Es un algoritmo experimental de cruce lateral, no un clasificador de personas.
- El LiDAR 8×8 tiene baja resolución; grupos de personas, objetos, trayectorias diagonales o cruces rápidos pueden generar errores.
- El objetivo de 100 Hz no garantiza 100 matrices por segundo. La frecuencia real depende de la tasa del sensor, el puerto serie y el tiempo de lectura/procesamiento.
- La ocupación no se sincroniza automáticamente con un conteo real al iniciar. Introduce un valor conocido con `--initial-occupancy`.
- AWS recibe resúmenes y eventos; el conteo se ejecuta localmente y continúa si la red falla.
