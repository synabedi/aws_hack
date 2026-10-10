"""Waterline extraction and filtering (architecture doc 8.3, steps 1-3).

Boundary pixels of the water mask, minus: the image border, pixels on or next to
person/vehicle masks, pixels whose twin point is missing or low confidence, and
pixels on flat ground where one pixel of mask error moves the height a lot. Pixels
on steep surfaces (kerbs, walls, stakes) are kept preferentially.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

MIN_POINTS = 50
MAX_SENSITIVITY_M_PER_PX = 0.02   # drop waterline pixels where 1 px moves height by > 2 cm


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
    """Heights (m) and the (N, 3) points of the kept waterline pixels."""
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
