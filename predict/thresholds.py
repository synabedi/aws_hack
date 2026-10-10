"""Load default thresholds and their provenance from predict/thresholds.yaml."""
from __future__ import annotations

import os

import yaml

from contracts.schemas import VEHICLE_CLASSES, Thresholds

_PATH = os.path.join(os.path.dirname(__file__), "thresholds.yaml")


def load_threshold_table() -> dict[str, dict]:
    with open(_PATH) as f:
        return yaml.safe_load(f)


def default_thresholds() -> Thresholds:
    tab = load_threshold_table()
    return Thresholds(**{c: float(tab[c]["cm"]) for c in VEHICLE_CLASSES})


def assumed_classes() -> set[str]:
    return {c for c, v in load_threshold_table().items() if v.get("assumed")}
