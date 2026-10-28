"""Servicio ProxiSense: presencia por LiDAR con alertas de Telegram. Lanzador del paquete test_radar.

    python proxisense.py [--port COM3] [--no-privacy] [--replay data/habitacion_vacia.csv --once]

Las credenciales van en el archivo .env (ver .env.example). El codigo original se conserva en
legacy/proxisense.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from test_radar.cli import main  # noqa: E402

if __name__ == "__main__":
    main(["monitor", *sys.argv[1:]])
