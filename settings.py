import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
SENSORS = ("temperature", "humidity", "distance_cm")
BOUNDS = {"temperature": (-40, 80), "humidity": (0, 100), "distance_cm": (2, 400)}
