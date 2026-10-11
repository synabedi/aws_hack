"""Demo snapshot for the web/desk dashboard.

Reuses web/make_mock_data.py unchanged (same physics model, same contract shapes) but writes to
web/desk/public/mock, so the original web/mock snapshot is untouched. Adds one file per simulated site,
lab_<site_id>.json, holding what FloodLab needs to run the site equation in the browser: basin area
table, rain for the next 60 minutes, the fitted parameters and one pump's rate.

Usage (from the repo root):  PYTHONPATH=. python3 web/desk/make_demo_data.py --minutes-in 8
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os

from predict.site_model import make_forcing_fn
from sim.generate import make_sites

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "public", "mock")


def main(minutes_in: int) -> None:
    spec = importlib.util.spec_from_file_location("make_mock_data", os.path.join(HERE, "..", "make_mock_data.py"))
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)
    base.OUT = OUT
    base.main(minutes_in)

    with open(os.path.join(OUT, "sites.json")) as f:
        states = {s["site"]["site_id"]: s for s in json.load(f)}
    for site, basin, _params, forcing in make_sites(6, seed=0):
        st = states[site.site_id]
        fc = st["latest_forecast"]
        rain = make_forcing_fn(forcing)
        lab = {
            "site_id": site.site_id,
            "simulated": True,
            "h_now_m": fc["depth"][0] / 100.0,
            "params": fc["params"],
            "pump_rate_m3_s": site.pump_rate_m3_s,
            "rain_mm_h": [rain(minutes_in * 60 + m * 60) for m in range(61)],   # one value per minute from now
            "rain_source": forcing.source,
            "basin": {"h_m": basin.h_m, "area_m2": [round(a, 3) for a in basin.area_m2]},
        }
        with open(os.path.join(OUT, f"lab_{site.site_id}.json"), "w") as f:
            json.dump(lab, f)
    # compact the big files; the browser does not need indentation
    for name in os.listdir(OUT):
        p = os.path.join(OUT, name)
        with open(p) as f:
            obj = json.load(f)
        with open(p, "w") as f:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes-in", type=int, default=8)
    main(ap.parse_args().minutes_in)
