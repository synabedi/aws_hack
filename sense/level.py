"""Waterline -> water level -> depth, with an error bar and abstain checks.

Steps (architecture doc 8.3, 8.4, 8.5):
 1. boundary pixels of the water mask
 2. drop pixels on the image border, on person/vehicle masks, or with a low-confidence
    twin point; prefer pixels on steep surfaces (kerbs, walls) where a 1 px error
    barely changes height
 3. look up each pixel's metric 3D point in ref_pointmap_metric.npy
 4. first flood frame: RANSAC plane, check its normal within 5 deg of the twin's up
 5. level = 90th-95th percentile of waterline heights (resists occlusion; Dale et al. 2026)
 6. sigma = max(scaled MAD, bootstrap spread over 200 resamples)

Fit-quality and temporal rules set ``status`` here; the vision-model cross-check in
sense/checks.py (P2) can downgrade a reading further, never upgrade it.

twin_dir must contain ref_pointmap_metric.npy (H, W, 3) and, for max depth,
heightmap.npy + heightmap_meta.json (see twin/basin.py). ref_conf.npy is optional.
"""
from __future__ import annotations

import json
import os

import numpy as np
from scipy import ndimage

from contracts.schemas import Reading, now_ts
from sense.depthmap import depth_map_cm, max_depth_cm, render_heatmap

LEVEL_PERCENTILE = 92.5
MIN_POINTS = 50
MAX_SIGMA_CM = 5.0
TEMPORAL_JUMP_CM = 10.0
TEMPORAL_WINDOW_S = 30.0
UP_ANGLE_LIMIT_DEG = 5.0
MAX_SENSITIVITY_M_PER_PX = 0.02   # drop waterline pixels where 1 px moves height by more than 2 cm
N_BOOTSTRAP = 200


# ------------------------------------------------------------------ twin loading
def load_twin(twin_dir: str) -> dict:
    pm_path = os.path.join(twin_dir, "ref_pointmap_metric.npy")
    if not os.path.exists(pm_path):
        raise FileNotFoundError(f"{pm_path} missing: run twin/calibrate.py first")
    tw = {"pointmap": np.load(pm_path).astype(np.float32), "conf": None, "heightmap": None,
          "meta": {"datum_offset_m": 0.0}}
    cp = os.path.join(twin_dir, "ref_conf.npy")
    if os.path.exists(cp):
        tw["conf"] = np.load(cp)
    hp = os.path.join(twin_dir, "heightmap.npy")
    mp = os.path.join(twin_dir, "heightmap_meta.json")
    if os.path.exists(hp) and os.path.exists(mp):
        tw["heightmap"] = np.load(hp)
        with open(mp) as f:
            tw["meta"] = json.load(f)
    return tw


# ------------------------------------------------------------------ waterline
def extract_waterline(mask: np.ndarray, exclude_mask: np.ndarray | None = None,
                      border_px: int = 2, exclude_dilate_px: int = 5) -> np.ndarray:
    """(N, 2) row/col of mask boundary pixels after border and exclusion filtering."""
    m = np.asarray(mask).astype(bool)
    inner = ndimage.binary_erosion(m, iterations=1, border_value=0)
    boundary = m & ~inner
    boundary[:border_px, :] = False
    boundary[-border_px:, :] = False
    boundary[:, :border_px] = False
    boundary[:, -border_px:] = False
    if exclude_mask is not None:
        ex = ndimage.binary_dilation(np.asarray(exclude_mask).astype(bool), iterations=exclude_dilate_px)
        boundary &= ~ex
    return np.argwhere(boundary)


def height_sensitivity(pointmap: np.ndarray) -> np.ndarray:
    """Metres of height change per pixel step (max over row/col directions)."""
    z = pointmap[..., 2].astype(np.float64)
    gy, gx = np.gradient(z)
    s = np.maximum(np.abs(gx), np.abs(gy))
    s[~np.isfinite(s)] = np.inf
    return s


def waterline_heights(boundary_rc: np.ndarray, pointmap: np.ndarray, conf: np.ndarray | None = None,
                      conf_percentile: float = 10.0, max_sens: float = MAX_SENSITIVITY_M_PER_PX
                      ) -> tuple[np.ndarray, np.ndarray]:
    """Heights (m, uncalibrated for datum) and the (N,3) points of the kept waterline pixels."""
    if len(boundary_rc) == 0:
        return np.array([]), np.zeros((0, 3))
    pts = pointmap[boundary_rc[:, 0], boundary_rc[:, 1]].astype(np.float64)
    keep = np.isfinite(pts).all(axis=1)
    if conf is not None:
        finite = conf[np.isfinite(conf)]
        if finite.size:
            keep &= conf[boundary_rc[:, 0], boundary_rc[:, 1]] >= np.percentile(finite, conf_percentile)
    sens = height_sensitivity(pointmap)[boundary_rc[:, 0], boundary_rc[:, 1]]
    steep_ok = keep & (sens <= max_sens)
    if steep_ok.sum() >= MIN_POINTS:
        keep = steep_ok
    pts = pts[keep]
    return pts[:, 2], pts


def robust_level(z: np.ndarray, pct: float = LEVEL_PERCENTILE, n_boot: int = N_BOOTSTRAP,
                 seed: int = 0) -> tuple[float, float]:
    """(level_m, sigma_m): percentile level; sigma = max(1.4826*MAD, bootstrap std of the percentile)."""
    z = np.asarray(z, dtype=np.float64)
    if z.size == 0:
        return float("nan"), float("nan")
    level = float(np.percentile(z, pct))
    mad = 1.4826 * float(np.median(np.abs(z - np.median(z))))
    rng = np.random.default_rng(seed)
    boots = [np.percentile(rng.choice(z, z.size, replace=True), pct) for _ in range(n_boot)]
    sig = max(mad, float(np.std(boots)))
    return level, sig


def fit_plane_ransac(points: np.ndarray, n_iter: int = 300, thresh_m: float = 0.01, seed: int = 0
                     ) -> tuple[np.ndarray, float, np.ndarray]:
    """Plane n.x = d through (N,3) points. Returns (unit normal with n_z >= 0, d, inlier mask)."""
    P = np.asarray(points, dtype=np.float64)
    if len(P) < 3:
        raise ValueError("need 3 points")
    rng = np.random.default_rng(seed)
    best_n, best_in = None, np.zeros(len(P), bool)
    for _ in range(n_iter):
        idx = rng.choice(len(P), 3, replace=False)
        a, b, c = P[idx]
        n = np.cross(b - a, c - a)
        nn = np.linalg.norm(n)
        if nn < 1e-12:
            continue
        n /= nn
        inl = np.abs(P @ n - float(n @ a)) <= thresh_m
        if inl.sum() > best_in.sum():
            best_n, best_in = n, inl
    if best_n is None:
        raise ValueError("RANSAC failed")
    # refine on inliers by SVD
    Q = P[best_in]
    cen = Q.mean(0)
    _, _, vt = np.linalg.svd(Q - cen)
    n = vt[-1]
    if n[2] < 0:
        n = -n
    return n, float(n @ cen), best_in


def angle_deg(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    c = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
    return float(np.degrees(np.arccos(np.clip(c, -1.0, 1.0))))


# ------------------------------------------------------------------ measure
def measure(
    site_id: str,
    frame_path: str,
    mask: np.ndarray,
    twin_dir: str,
    prev_reading: Reading | None = None,
    exclude_mask: np.ndarray | None = None,
    ts: float | None = None,
    out_dir: str | None = None,
    rain_mm_h: float | None = None,
    check_up: bool = False,
    pumps_on: int = 0,
    event_id: str | None = None,
    simulated: bool = False,
) -> Reading:
    """One flooded frame + its water mask -> Reading (see contracts.schemas.Reading)."""
    ts = now_ts() if ts is None else ts
    tw = load_twin(twin_dir)
    pm, conf = tw["pointmap"], tw["conf"]
    if mask.shape != pm.shape[:2]:
        raise ValueError(f"mask {mask.shape} does not match twin pointmap {pm.shape[:2]}")
    datum = float(tw["meta"].get("datum_offset_m", 0.0))
    checks: list[str] = []

    rc = extract_waterline(mask, exclude_mask)
    z, pts = waterline_heights(rc, pm, conf)
    n = int(z.size)
    if n == 0:
        return Reading(site_id=site_id, ts=ts, level_m=0.0, max_depth_cm=0.0, sigma_cm=float("inf"),
                       status="failed", frame_uri=frame_path, n_waterline_points=0,
                       checks_failed=["no_waterline_points"], pumps_on=pumps_on, event_id=event_id,
                       simulated=simulated)

    level_raw, sigma_m = robust_level(z)
    level = level_raw - datum
    sigma_cm = sigma_m * 100.0

    if check_up and n >= 3:
        try:
            normal, _, _ = fit_plane_ransac(pts)
            if angle_deg(normal, [0, 0, 1]) > UP_ANGLE_LIMIT_DEG:
                checks.append("up_vector_mismatch")
        except ValueError:
            checks.append("plane_fit_failed")
    if n < MIN_POINTS:
        checks.append("few_points")
    if sigma_cm > MAX_SIGMA_CM:
        checks.append("high_sigma")
    if prev_reading is not None and prev_reading.status != "failed":
        dt = abs(ts - prev_reading.ts)
        jump = abs(level - prev_reading.level_m) * 100.0
        if dt <= TEMPORAL_WINDOW_S and jump > TEMPORAL_JUMP_CM and not (rain_mm_h and rain_mm_h > 0):
            checks.append("temporal_jump")

    # depth everywhere, and the deepest point even if hidden
    dmap = depth_map_cm(level, pm, mask, datum)
    if tw["heightmap"] is not None:
        wet = pm[mask]
        wet = wet[np.isfinite(wet).all(axis=1)]
        xy = wet[:, :2] if len(wet) else None
        mx, _ = max_depth_cm(level, tw["heightmap"], tw["meta"], xy)
    else:
        zmin = float(np.nanmin(pm[..., 2])) - datum
        mx = max((level - zmin) * 100.0, 0.0)
    mx = max(mx, float(np.nanmax(dmap)) if np.isfinite(dmap).any() else 0.0)

    mask_uri = depth_uri = None
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        stem = os.path.splitext(os.path.basename(frame_path))[0]
        import cv2

        mask_uri = os.path.join(out_dir, f"{stem}_mask.png")
        cv2.imwrite(mask_uri, (mask.astype(np.uint8) * 255))
        depth_uri = render_heatmap(frame_path, dmap, os.path.join(out_dir, f"{stem}_depth.png"))

    status = "confident" if not checks else "low_confidence"
    return Reading(
        site_id=site_id, ts=ts, level_m=float(level), max_depth_cm=float(mx), sigma_cm=float(sigma_cm),
        status=status, frame_uri=frame_path, mask_uri=mask_uri, depthmap_uri=depth_uri,
        n_waterline_points=n, checks_failed=checks, pumps_on=pumps_on, event_id=event_id,
        simulated=simulated,
    )
