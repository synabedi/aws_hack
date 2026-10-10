"""Predict and Diagnose metrics on the staged flood (architecture doc 13.4).

Inputs
  --pred  predictions CSV from validation/measure_pass.py for passes A, B, C
          (pass,t_s,max_depth_cm,sigma_cm,status,level_m,...)
  --truth validation/data/ruler_readings.csv (pass,t_s,ruler_deep_cm,ruler_mid_cm)
  --hose  validation/data/hose_rate.csv with a column mean_l_min (three bucket timings)
  --twin-dir  the site twin (basin.csv)
Outputs a markdown table: time-to-target from the first 40% of pass A, fitted R vs hose, k_C / k_B.
"""
from __future__ import annotations

import argparse
import csv

from contracts.schemas import Forcing, Reading, Thresholds
from predict.drain_health import compare_passes, fit_k_from_recession
from predict.fit import fit_params
from predict.forecast import fit_and_forecast
from twin.basin import load_basin

HOSE_I = 1000.0  # mm/h == 1 m/h so R [m^2] == m^3/h


def readings_for(rows: list[dict], pass_name: str, site_id: str = "site") -> list[Reading]:
    out = []
    for r in rows:
        if r["pass"].strip() != pass_name:
            continue
        out.append(Reading(site_id=site_id, ts=float(r["t_s"]), level_m=float(r["level_m"]),
                           max_depth_cm=float(r["max_depth_cm"]), sigma_cm=float(r["sigma_cm"]),
                           status=r.get("status", "confident"), frame_uri="staged"))
    return sorted(out, key=lambda x: x.ts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True)
    ap.add_argument("--truth", default="validation/data/ruler_readings.csv")
    ap.add_argument("--hose", default="validation/data/hose_rate.csv")
    ap.add_argument("--twin-dir", required=True)
    ap.add_argument("--target-cm", type=float, default=15.0)
    ap.add_argument("--out", default="validation/predict_vs_truth.md")
    a = ap.parse_args()
    with open(a.pred, newline="") as f:
        pred = list(csv.DictReader(f))
    with open(a.truth, newline="") as f:
        truth = list(csv.DictReader(f))
    basin = load_basin(a.twin_dir)
    lines = ["# Predict and Diagnose vs truth", ""]

    # --- pass A: time to target from first 40% ---
    A = readings_for(pred, "A")
    truthA = sorted([r for r in truth if r["pass"].strip() == "A"], key=lambda r: float(r["t_s"]))
    t_true = next((float(r["t_s"]) for r in truthA if float(r["ruler_deep_cm"]) >= a.target_cm), None)
    hose = Forcing(t_s=[0.0], intensity_mm_h=[HOSE_I], source="hose")
    if A and t_true is not None:
        cut = A[: max(3, int(0.4 * len(A)))]
        fc = fit_and_forecast(cut, hose, basin, Thresholds(closure=a.target_cm), horizon_min=60)
        tm = fc.t_impassable_min["closure"]
        t_pred = (cut[-1].ts - A[0].ts) + tm * 60 if tm is not None else None
        err = abs(t_pred - t_true) / t_true * 100 if t_pred is not None else None
        lines.append(f"| time to {a.target_cm:.0f} cm (first 40% of pass A, {len(cut)} readings) | predicted {t_pred:.0f} s | actual {t_true:.0f} s | error {err:.0f}% | {'PASS' if err is not None and err <= 20 else 'FAIL'} |")
    else:
        lines.append("| time to target | no pass A data or ruler never reached target | | | |")

    # --- fitted inflow vs hose ---
    try:
        with open(a.hose, newline="") as f:
            hose_lmin = float(list(csv.DictReader(f))[0]["mean_l_min"])
        hose_m3h = hose_lmin * 60 / 1000
        if A:
            p = fit_params(A, hose, basin)
            err = abs(p.R - hose_m3h) / hose_m3h * 100
            lines.append(f"| fitted inflow | {p.R:.3f} m³/h (±{(p.R_sigma or 0):.3f}) | hose {hose_m3h:.3f} m³/h | error {err:.0f}% | {'PASS' if err <= 25 else 'FAIL'} |")
    except (FileNotFoundError, KeyError, IndexError):
        lines.append("| fitted inflow | no hose_rate.csv | | | |")

    # --- k open vs blocked ---
    B, C = readings_for(pred, "B"), readings_for(pred, "C")
    if len(B) >= 3 and len(C) >= 3:
        cmp = compare_passes(fit_k_from_recession(B, basin), fit_k_from_recession(C, basin))
        lines.append(f"| k open (B) | {cmp['k_open']:.5f} [{cmp['k_open_ci'][0]:.5f}, {cmp['k_open_ci'][1]:.5f}] | "
                     f"k blocked (C) {cmp['k_blocked']:.5f} [{cmp['k_blocked_ci'][0]:.5f}, {cmp['k_blocked_ci'][1]:.5f}] | "
                     f"ratio {cmp['ratio']:.2f} | {'PASS' if cmp['ratio'] < 1 and not cmp['intervals_overlap'] else 'FAIL'} |")
    else:
        lines.append("| drain k | need ≥3 confident readings in both pass B and pass C | | | |")
    md = "\n".join(lines) + "\n"
    with open(a.out, "w") as f:
        f.write(md)
    print(md)


if __name__ == "__main__":
    main()
