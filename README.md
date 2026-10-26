# ProxiSense

Servicio Python para detectar presencia con un LiDAR conectado por USB-C y avisar por Telegram. No necesita ESP32 ni Arduino: el computador abre directamente el puerto serie del sensor.

## Preparacion

1. Instala Python 3.10 o superior.
2. Dentro de esta carpeta, ejecuta:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

   En Ubuntu, activa con `source .venv/bin/activate`.
3. En `proxisense.py`, configura `SERIAL_PORT`, `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`.
4. Inicia el servicio con `python proxisense.py`. Se detiene con `Ctrl+C`.

## Funcionamiento

- Una distancia valida de 1500 mm o menos inicia la deteccion.
- Debe mantenerse un segundo para confirmar presencia y descartar pasos breves o mascotas.
- Solo se envia una alerta por evento; al desaparecer el objeto se rearma el detector.
- Entre 22:00 y 08:00 el LiDAR sigue funcionando, pero Telegram queda silenciado.
- Si se desconecta el cable USB-C, el servicio registra el error y reintenta cada cinco segundos.

## Formatos aceptados

El lector funciona con una distancia por linea (`742`) y con filas 8x8 como:

```text
y0: 1200 1300 1400 1500 1600 1700 1800 1900
```

Si tu placa usa otro formato, comparte dos o tres lineas reales para ajustar solo `parse_distances`.
