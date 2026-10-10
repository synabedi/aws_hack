"""Run Sense over one staged-flood pass: frames + masks -> predictions CSV for sense_vs_ruler.py.

frames dir: <stem>.jpg sampled every 30 s, named so that sorting gives time order;
masks dir:  <stem>_mask.png (white = water) from sense/segment.py (P2), optionally
            <stem>_exclude.png for people and vehicles.
Frame time t_s = index * dt_s unless a ``times.csv`` (stem,t_s) sits in the frames dir.
"""
from __future__ import annotations

import argparse
import csv
import os

import cv2

from sense.level import measure


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-id", required=True)
    ap.add_argument("--pass-name", required=True, help="A, B or C")
    ap.add_argument("--frames", required=True)
    ap.add_argument("--masks", required=True)
    ap.add_argument("--twin-dir", required=True)
    ap.add_argument("--out", required=True, help="predictions CSV (append-safe per pass)")
    ap.add_argument("--dt-s", type=float, default=30.0)
    ap.add_argument("--heatmaps", help="optional dir for mask/depth PNGs")
    a = ap.parse_args()

    stems = sorted(os.path.splitext(f)[0] for f in os.listdir(a.frames) if f.lower().endswith((".jpg", ".png", ".jpeg")))
    times = {}
    tpath = os.path.join(a.frames, "times.csv")
    if os.path.exists(tpath):
        with open(tpath, newline="") as f:
            times = {r["stem"]: float(r["t_s"]) for r in csv.DictReader(f)}
    rows, prev = [], None
    for i, stem in enumerate(stems):
        fp = next(os.path.join(a.frames, f) for f in os.listdir(a.frames) if os.path.splitext(f)[0] == stem)
        mp = os.path.join(a.masks, f"{stem}_mask.png")
        if not os.path.exists(mp):
            print(f"skip {stem}: no mask")
            continue
        mask = cv2.imread(mp, cv2.IMREAD_GRAYSCALE) > 127
        ex_p = os.path.join(a.masks, f"{stem}_exclude.png")
        ex = (cv2.imread(ex_p, cv2.IMREAD_GRAYSCALE) > 127) if os.path.exists(ex_p) else None
        t_s = times.get(stem, i * a.dt_s)
        r = measure(a.site_id, fp, mask, a.twin_dir, prev_reading=prev, exclude_mask=ex, ts=t_s,
                    out_dir=a.heatmaps, check_up=(i == 0))
        prev = r
        rows.append({"pass": a.pass_name, "t_s": t_s, "max_depth_cm": f"{r.max_depth_cm:.2f}",
                     "sigma_cm": f"{r.sigma_cm:.2f}", "status": r.status, "level_m": f"{r.level_m:.4f}",
                     "n_points": r.n_waterline_points, "checks": ";".join(r.checks_failed)})
        print(f"{stem}: t={t_s:.0f}s depth={r.max_depth_cm:.1f}±{r.sigma_cm:.1f} cm n={r.n_waterline_points} {r.status}")
    exists = os.path.exists(a.out)
    with open(a.out, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["pass"])
        if not exists:
            w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {a.out}")


if __name__ == "__main__":
    main()
