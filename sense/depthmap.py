"""Depth map and max depth from a water level and the dry twin.

depth(pixel) = level - ground height at that pixel, inside the water mask.
max depth = level - lowest heightmap cell that is below the level AND connected to
the visible water, so the deepest point counts even when murky water hides it.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage


def depth_map_cm(level_m: float, pointmap_metric: np.ndarray, water_mask: np.ndarray,
                 datum_offset_m: float = 0.0) -> np.ndarray:
    """(H, W) float32 depth in cm; NaN outside the mask or where the ground is above the level."""
    z = pointmap_metric[..., 2].astype(np.float64) - datum_offset_m
    d = (level_m - z) * 100.0
    d[~water_mask] = np.nan
    d[d < 0] = np.nan
    return d.astype(np.float32)


def _cells_for_xy(xy: np.ndarray, meta: dict, shape: tuple[int, int]) -> np.ndarray:
    cell = float(meta["cell_m"])
    x0, y0 = meta["origin_xy"]
    ci = np.floor((xy[:, 0] - x0) / cell).astype(int)
    ri = np.floor((xy[:, 1] - y0) / cell).astype(int)
    ok = (ri >= 0) & (ri < shape[0]) & (ci >= 0) & (ci < shape[1])
    return np.stack([ri[ok], ci[ok]], axis=1)


def max_depth_cm(level_m: float, heightmap: np.ndarray, meta: dict | None = None,
                 visible_xy: np.ndarray | None = None) -> tuple[float, tuple[int, int] | None]:
    """Max depth (cm) over the pool connected to the visible water. ``heightmap`` is at
    datum; ``level_m`` is above datum. Returns (max_depth_cm, (row, col) of the deepest cell)."""
    hm = np.asarray(heightmap, dtype=np.float64)
    below = np.isfinite(hm) & (hm <= level_m)
    if not below.any():
        return 0.0, None
    labels, _n = ndimage.label(below)
    seeds = None
    if visible_xy is not None and meta is not None and len(visible_xy):
        rc = _cells_for_xy(np.asarray(visible_xy, dtype=float), meta, hm.shape)
        if len(rc):
            labs = labels[rc[:, 0], rc[:, 1]]
            seeds = {int(v) for v in labs[labs > 0]}
    if not seeds:
        # no visible-water seed: use the global minimum's component
        seeds = {int(labels[np.unravel_index(int(np.nanargmin(np.where(np.isfinite(hm), hm, np.inf))), hm.shape)])}
        seeds.discard(0)
        if not seeds:
            return 0.0, None
    pool = np.isin(labels, list(seeds))
    zmin_idx = np.argmin(np.where(pool, hm, np.inf))
    rc = np.unravel_index(int(zmin_idx), hm.shape)
    return float((level_m - hm[rc]) * 100.0), (int(rc[0]), int(rc[1]))


def render_heatmap(frame_path: str, depth_cm: np.ndarray, out_path: str, vmax_cm: float | None = None,
                   alpha: float = 0.55) -> str:
    """Overlay a colour depth map on the frame and write a PNG (for the dashboard)."""
    import cv2

    frame = cv2.imread(frame_path)
    if frame is None:
        raise FileNotFoundError(frame_path)
    H, W = depth_cm.shape
    if frame.shape[:2] != (H, W):
        frame = cv2.resize(frame, (W, H))
    valid = np.isfinite(depth_cm)
    vmax = vmax_cm or (float(np.nanmax(depth_cm)) if valid.any() else 1.0)
    vmax = max(vmax, 1.0)
    norm = np.zeros((H, W), np.uint8)
    norm[valid] = np.clip(depth_cm[valid] / vmax * 255.0, 0, 255).astype(np.uint8)
    colour = cv2.applyColorMap(norm, cv2.COLORMAP_JET)
    out = frame.copy()
    out[valid] = (alpha * colour[valid] + (1 - alpha) * frame[valid]).astype(np.uint8)
    cv2.imwrite(out_path, out)
    return out_path
