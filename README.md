# ProxiSense

Proyecto unificado para el sensor LiDAR 8x8 conectado por USB/serie: radar en tiempo real con mapa de calor, calibración del fondo, registro de mediciones en CSV y servicio de presencia con alertas por Telegram. El computador abre directamente el puerto serie; no necesita ESP32 ni Arduino.

## Estructura

```
Radar.py              # lanzador del radar:            python Radar.py
proxisense.py         # lanzador del servicio Telegram: python proxisense.py
src/test_radar/       # todo el codigo (comando `test-radar`)
  sensor.py           #   conexion serie y parseo de tramas y0..y7
  replay.py           #   reproduce un CSV como si fuera el sensor (sin hardware)
  processing.py       #   estabilizacion y deteccion por agrupaciones
  baseline.py         #   calibracion del fondo (habitacion vacia)
  tracking.py         #   identidad y suavizado de objetivos
  visualization.py    #   radar polar + mapa de calor 8x8
  recorder.py         #   registro y lectura de CSV
  monitor.py          #   presencia + alertas de Telegram
  config.py           #   parametros y carga del .env
  cli.py              #   punto de entrada
data/                 # CSV y baseline.json; habitacion_vacia.csv queda como referencia
legacy/               # scripts originales v1.0, intactos (Radar.py, proxisense.py, Main.py, ...)
.env.example          # plantilla de credenciales
```

`Radar.py` y `proxisense.py` de la raíz ahora solo lanzan el paquete. El código original de la v1.0 está sin cambios en `legacy/`; se comprobó que el paquete produce exactamente los mismos objetivos que el `Radar.py` original con las mismas lecturas.

## Instalación

Requiere Python 3.10 o superior.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Ubuntu
pip install -r requirements.txt
pip install -e .                # habilita el comando test-radar
```

Copia `.env.example` como `.env` y completa los valores (el archivo `.env` no se sube a Git):

```
LIDAR_PORT=COM3                 # Linux: /dev/ttyUSB0 o /dev/ttyACM0
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

## Uso

Todas las opciones de puerto (`--port COM3`) se pueden poner antes o después del subcomando. Sin `--port` se usa `LIDAR_PORT` del `.env`.

| Comando | Qué hace |
| --- | --- |
| `python Radar.py` o `test-radar radar` | Radar polar + mapa de calor 8x8. Flechas: ángulo, ESPACIO: limpiar puntos, ESC: cerrar. `--no-heatmap` para ver solo el radar. |
| `test-radar calibrate` | Aprende la habitación vacía (10 s, sensor quieto) y guarda `data/baseline.json`. |
| `python proxisense.py` o `test-radar monitor` | Servicio de presencia con alertas por Telegram. |
| `test-radar record --duration 30 --output data/prueba.csv` | Registra matrices 8x8 completas en un CSV. |
| `test-radar stream --count 20` | Muestra las líneas crudas que llegan del sensor. |

### Calibración de fondo

Sin calibrar, todo lo que esté cerca del sensor (una pared, una mesa) cuenta como objeto. Después de `calibrate`, `radar` y `monitor` cargan automáticamente `data/baseline.json` y solo reportan lo que está **más cerca que el fondo** por un margen (150 mm por defecto, `--margin` al calibrar). Usa `--no-baseline` para ignorarlo. Si el fondo no estaba quieto al calibrar, el comando lo avisa.

Con tu grabación de ejemplo, que no es estática (en los segundos 4 a 10 hay algo muy cerca y desde el 14 queda estable), se calibra con el tramo estable:

```bash
test-radar calibrate --from-csv data/habitacion_vacia.csv --start 14
```

### Reproducir sin sensor

Cualquier grabación sirve como fuente de datos para probar el radar o el monitor:

```bash
test-radar radar --replay data/habitacion_vacia.csv
test-radar monitor --replay data/habitacion_vacia.csv --once --speed 4
```

`--speed` acelera o frena la reproducción y `--once` la reproduce una sola vez.

### Servicio de presencia

- Una distancia válida de 1500 mm o menos (`--distance`) inicia la detección.
- Debe mantenerse un segundo (`--confirm`) para confirmar y descartar pasos breves o mascotas.
- Solo se envía una alerta por evento; al desaparecer el objeto se rearma el detector.
- Entre 22:00 y 08:00 Telegram queda silenciado (`--privacy-start`, `--privacy-end`, `--no-privacy`).
- Si se desconecta el cable USB, registra el error y reintenta cada cinco segundos.
- El token de Telegram nunca aparece en los registros de error.

## Formatos de datos

El sensor emite filas 8x8 como `y0: 1200 1300 1400 1500 1600 1700 1800 1900`; el monitor también acepta una distancia por línea (`742`). Los CSV usan las cabeceras `tiempo, lectura, filas_recibidas, celda_0 ... celda_63` (también se leen las equivalentes en inglés).

## Ajustes

Umbral, tolerancias, historial y alcance del radar están en `src/test_radar/config.py` (`RadarConfig`); los de calibración en `BaselineConfig` y los del servicio en `MonitorConfig`.
