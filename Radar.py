"""Radar tactico del sensor LiDAR (v1.0). Lanzador del paquete test_radar.

    python Radar.py [--port COM3] [--no-heatmap] [--replay data/habitacion_vacia.csv]

El codigo original de esta version se conserva intacto en legacy/Radar.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from test_radar.cli import main  # noqa: E402

if __name__ == "__main__":
    main(["radar", *sys.argv[1:]])
