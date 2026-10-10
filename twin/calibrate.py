"""Calibrate a MapAnything reconstruction to metric, gravity-aligned coordinates.

Inputs: 3D positions of the chalk control marks in reconstruction coordinates
(clicked on the reference still, looked up in its point map) and their
tape-measured heights above the lowest point (``validation/data/control_marks.csv``,
columns ``mark_id,height_cm``).

Heights alone cannot fix a full rigid transform (rotation about the vertical and
in-plane translation stay free), but they fix everything Sense needs: the metric
scale ``s``, the up vector ``u`` and the vertical offset ``c``, through

    height_i = s * (p_i . u) + c

which is linear in w = s*u and c. Needs >= 4 marks not all on one line, at
different heights. If x,y positions were also surveyed, ``umeyama`` fits the
full similarity instead.

The 1 m stick is an independent scale check: ``check_stick``.
Recapture if the per-mark residual exceeds 2 cm (architecture doc 8.1).
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass

import numpy as np

RESIDUAL_LIMIT_M = 0.02


@dataclass
class Calibration:
    scale: float
    up: list[float]            # unit vector in reconstruction coords
    offset_m: float            # c, so that height = scale*(p.up) + offset
    transform: list[list[float]]  # 4x4: reconstruction -> metric, z up, datum at lowest mark reference
    residuals_m: list[float]
    rms_m: float
    max_abs_m: float
    ok: bool

    def to_json(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def from_json(cls, path: str) -> "Calibration":
        with open(path) as f:
            return cls(**json.load(f))


def fit_scale_and_up(points_xyz: np.ndarray, heights_m: np.ndarray) -> Calibration:
    """Fit s, u, c from control-mark positions and their measured heights."""
    P = np.asarray(points_xyz, dtype=np.float64)
    h = np.asarray(heights_m, dtype=np.float64)
    if P.shape[0] < 4:
        raise ValueError("need at least 4 control marks")
    if np.ptp(h) < 0.05:
        raise ValueError("control marks need a spread of heights (>= 5 cm)")
    A = np.hstack([P, np.ones((len(P), 1))])
    sol, *_ = np.linalg.lstsq(A, h, rcond=None)
    w, c = sol[:3], float(sol[3])
    s = float(np.linalg.norm(w))
    if s <= 0:
        raise ValueError("degenerate fit")
    u = w / s
    pred = A @ sol
    res = pred - h
    rms = float(np.sqrt(np.mean(res**2)))
    mx = float(np.max(np.abs(res)))
    T = make_transform(s, u, c)
    return Calibration(scale=s, up=u.tolist(), offset_m=c, transform=T.tolist(),
                       residuals_m=res.tolist(), rms_m=rms, max_abs_m=mx, ok=mx <= RESIDUAL_LIMIT_M)


def rotation_to_z(u: np.ndarray) -> np.ndarray:
    """Rotation matrix that maps unit vector u onto +z."""
    u = np.asarray(u, dtype=np.float64)
    u = u / np.linalg.norm(u)
    z = np.array([0.0, 0.0, 1.0])
    v = np.cross(u, z)
    sn = np.linalg.norm(v)
    cs = float(np.dot(u, z))
    if sn < 1e-12:
        return np.eye(3) if cs > 0 else np.diag([1.0, -1.0, -1.0])
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * ((1 - cs) / sn**2)


def make_transform(scale: float, up, offset_m: float) -> np.ndarray:
    """4x4 so that for p in reconstruction coords, (T @ [p,1])[2] = scale*(p.up)+offset."""
    R = rotation_to_z(np.asarray(up))
    T = np.eye(4)
    T[:3, :3] = scale * R
    T[2, 3] = offset_m
    return T


def apply_transform(T: np.ndarray, points: np.ndarray) -> np.ndarray:
    """Apply a 4x4 transform to (..., 3) points; NaNs pass through."""
    T = np.asarray(T, dtype=np.float64)
    P = np.asarray(points, dtype=np.float64)
    shp = P.shape
    flat = P.reshape(-1, 3)
    out = flat @ T[:3, :3].T + T[:3, 3]
    return out.reshape(shp)


def umeyama(src: np.ndarray, dst: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
    """Full similarity (s, R, t) with dst ~ s*R@src + t. Umeyama 1991."""
    src = np.asarray(src, dtype=np.float64)
    dst = np.asarray(dst, dtype=np.float64)
    n = src.shape[0]
    mu_s, mu_d = src.mean(0), dst.mean(0)
    S, D = src - mu_s, dst - mu_d
    cov = D.T @ S / n
    U, sig, Vt = np.linalg.svd(cov)
    Sgn = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        Sgn[2, 2] = -1
    R = U @ Sgn @ Vt
    var_s = (S**2).sum() / n
    s = float(np.trace(np.diag(sig) @ Sgn) / var_s)
    t = mu_d - s * R @ mu_s
    return s, R, t


def check_stick(p_a: np.ndarray, p_b: np.ndarray, scale: float, true_len_m: float = 1.0) -> dict:
    """Independent scale check with the 1 m stick: endpoints in reconstruction coords."""
    measured = float(np.linalg.norm(np.asarray(p_b) - np.asarray(p_a)) * scale)
    err = measured - true_len_m
    return {"measured_m": measured, "error_m": err, "error_pct": 100.0 * err / true_len_m,
            "ok": abs(err) <= 0.03}


def read_control_marks_csv(path: str) -> dict[str, float]:
    import csv

    out = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            out[str(row["mark_id"])] = float(row["height_cm"]) / 100.0
    return out


def calibrate_twin(twin_dir: str, marks_xyz: dict[str, np.ndarray], marks_csv: str,
                   stick_xyz: tuple[np.ndarray, np.ndarray] | None = None) -> Calibration:
    """Fit the calibration, save calibration.json, transform ref_pointmap.npy and
    points.npy into ref_pointmap_metric.npy and points_metric.npy (z = height above
    the lowest control mark reference; twin.basin.to_datum then re-zeroes to the floor)."""
    heights = read_control_marks_csv(marks_csv)
    ids = [m for m in heights if m in marks_xyz]
    if len(ids) < 4:
        raise ValueError(f"only {len(ids)} control marks have both a 3D position and a height")
    P = np.stack([np.asarray(marks_xyz[m], dtype=float) for m in ids])
    h = np.array([heights[m] for m in ids])
    cal = fit_scale_and_up(P, h)
    print("per-mark residuals (cm):")
    for m, r in zip(ids, cal.residuals_m):
        print(f"  {m}: {100 * r:+.2f}")
    print(f"scale {cal.scale:.4f}  rms {100 * cal.rms_m:.2f} cm  max {100 * cal.max_abs_m:.2f} cm  "
          f"{'OK' if cal.ok else 'RECAPTURE (residual > 2 cm)'}")
    if stick_xyz is not None:
        print("stick check:", check_stick(stick_xyz[0], stick_xyz[1], cal.scale))
    cal.to_json(os.path.join(twin_dir, "calibration.json"))
    T = np.asarray(cal.transform)
    for name in ("ref_pointmap", "points"):
        src = os.path.join(twin_dir, f"{name}.npy")
        if os.path.exists(src):
            np.save(os.path.join(twin_dir, f"{name}_metric.npy"), apply_transform(T, np.load(src)).astype(np.float32))
    return cal


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Calibrate twin scale and up vector from control marks")
    ap.add_argument("--twin-dir", required=True)
    ap.add_argument("--marks-csv", required=True, help="mark_id,height_cm")
    ap.add_argument("--marks-pixels", required=True,
                    help="JSON {mark_id: [u, v]} pixel positions of each mark on the reference still")
    ap.add_argument("--stick-pixels", help="JSON [[u,v],[u,v]] stick endpoints on the reference still")
    a = ap.parse_args()
    pm = np.load(os.path.join(a.twin_dir, "ref_pointmap.npy"))
    with open(a.marks_pixels) as f:
        px = json.load(f)
    marks = {k: pm[int(v[1]), int(v[0])] for k, v in px.items()}
    stick = None
    if a.stick_pixels:
        with open(a.stick_pixels) as f:
            sp = json.load(f)
        stick = (pm[int(sp[0][1]), int(sp[0][0])], pm[int(sp[1][1]), int(sp[1][0])])
    calibrate_twin(a.twin_dir, marks, a.marks_csv, stick)
