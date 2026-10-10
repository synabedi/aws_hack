"""Heightmap and basin curves A(h), V(h) for one site.

Datum convention (contracts/schemas.py): z = 0 at the lowest ground cell of the
heightmap. A(h) is the surface area of the connected pool that contains the
lowest cell when water stands at level h; V(h) is its volume. Separate puddles
that are not connected to the main pool are excluded, so the site model sees one basin.

Files written per site into ``twin_dir``:
    heightmap.npy        float32 (rows, cols) ground height in metres above datum, NaN = unknown
    heightmap_meta.json  {"cell_m": 0.05, "origin_xy": [x0, y0], "datum_offset_m": z_min_original}
    basin.csv            h_m,area_m2,volume_m3 in 1 cm steps from 0
"""
from __future__ import annotations

import json
import os

import numpy as np
from scipy import ndimage
from scipy.interpolate import griddata

from contracts.schemas import BasinTable

DEFAULT_CELL_M = 0.05
DEFAULT_STEP_M = 0.01
# A pool can never have zero area in the ODE (A dh/dt = ...). Below this we clamp.
MIN_AREA_M2 = 0.05


# ------------------------------------------------------------------ rasterising
def heightmap_from_points(
    points_xyz: np.ndarray,
    cell_m: float = DEFAULT_CELL_M,
    percentile: float = 25.0,
    min_points_per_cell: int = 2,
) -> tuple[np.ndarray, tuple[float, float]]:
    """Rasterise metric, up-aligned (z up) ground points to a grid.

    Each cell takes a low percentile of its points' z so that stray points above
    the ground (kerb tops seen at a cell edge, objects) do not raise the floor.
    Returns (heightmap_m, origin_xy). Heights are NOT yet shifted to datum.
    """
    pts = np.asarray(points_xyz, dtype=np.float64)
    pts = pts[np.isfinite(pts).all(axis=1)]
    if len(pts) == 0:
        raise ValueError("no finite points")
    x0, y0 = pts[:, 0].min(), pts[:, 1].min()
    cols = int(np.floor((pts[:, 0].max() - x0) / cell_m)) + 1
    rows = int(np.floor((pts[:, 1].max() - y0) / cell_m)) + 1
    ci = np.floor((pts[:, 0] - x0) / cell_m).astype(int)
    ri = np.floor((pts[:, 1] - y0) / cell_m).astype(int)
    flat = ri * cols + ci
    order = np.argsort(flat, kind="stable")
    flat_sorted, z_sorted = flat[order], pts[order, 2]
    uniq, start, counts = np.unique(flat_sorted, return_index=True, return_counts=True)
    hm = np.full(rows * cols, np.nan, dtype=np.float32)
    for u, s, c in zip(uniq, start, counts):
        if c >= min_points_per_cell:
            hm[u] = np.percentile(z_sorted[s:s + c], percentile)
        elif c == 1 and min_points_per_cell <= 1:
            hm[u] = z_sorted[s]
    return hm.reshape(rows, cols), (float(x0), float(y0))


def fill_small_holes(heightmap: np.ndarray, max_hole_cells: int = 25) -> np.ndarray:
    """Fill NaN holes of at most ``max_hole_cells`` cells by linear interpolation
    from surrounding cells (nearest for cells the linear hull does not cover).
    Larger holes stay NaN so unknown ground is never invented."""
    hm = np.array(heightmap, dtype=np.float32, copy=True)
    nan = ~np.isfinite(hm)
    if not nan.any():
        return hm
    labels, n = ndimage.label(nan)
    sizes = ndimage.sum(nan, labels, index=np.arange(1, n + 1))
    small = np.zeros_like(nan)
    for lab, sz in enumerate(sizes, start=1):
        if sz <= max_hole_cells:
            small |= labels == lab
    if not small.any():
        return hm
    rr, cc = np.nonzero(~nan)
    vals = hm[~nan]
    tr, tc = np.nonzero(small)
    lin = griddata((rr, cc), vals, (tr, tc), method="linear")
    near = griddata((rr, cc), vals, (tr, tc), method="nearest")
    lin = np.where(np.isfinite(lin), lin, near)
    hm[tr, tc] = lin
    return hm


def to_datum(heightmap: np.ndarray) -> tuple[np.ndarray, float]:
    """Shift so the lowest finite cell is z = 0. Returns (heightmap, datum_offset)."""
    zmin = float(np.nanmin(heightmap))
    return (heightmap - zmin).astype(np.float32), zmin


# ------------------------------------------------------------------ basin curves
def _pool_mask(heightmap: np.ndarray, level: float, seed_rc: tuple[int, int]) -> np.ndarray:
    below = np.isfinite(heightmap) & (heightmap <= level)
    if not below[seed_rc]:
        return np.zeros_like(below)
    labels, _ = ndimage.label(below)
    return labels == labels[seed_rc]


def build_basin_from_heightmap(
    heightmap_m: np.ndarray,
    cell_m: float = DEFAULT_CELL_M,
    step_m: float = DEFAULT_STEP_M,
    max_h_m: float | None = None,
) -> BasinTable:
    """Compute A(h) and V(h) in ``step_m`` steps from the datum upward.

    The heightmap must already be shifted to datum (min = 0). ``max_h_m`` defaults
    to the highest finite cell (the pool then covers the whole known ground).
    Connectivity is 4-neighbour via scipy.ndimage.label.
    """
    hm = np.asarray(heightmap_m, dtype=np.float64)
    if not np.isfinite(hm).any():
        raise ValueError("heightmap has no finite cells")
    zmin = float(np.nanmin(hm))
    if abs(zmin) > 1e-6:
        raise ValueError(f"heightmap is not at datum (min = {zmin:.4f} m); call to_datum first")
    seed = np.unravel_index(int(np.nanargmin(hm)), hm.shape)
    if max_h_m is None:
        max_h_m = float(np.nanmax(hm))
    n = int(np.floor(max_h_m / step_m + 1e-9)) + 1
    cell_area = cell_m * cell_m
    h_list, a_list, v_list = [], [], []
    for i in range(n):
        h = i * step_m
        pool = _pool_mask(hm, h, seed)
        area = pool.sum() * cell_area
        vol = float(np.sum(h - hm[pool]) * cell_area) if pool.any() else 0.0
        h_list.append(round(h, 6))
        a_list.append(float(area))
        v_list.append(vol)
    # enforce monotonic non-decreasing (numerical safety)
    a_list = np.maximum.accumulate(a_list).tolist()
    v_list = np.maximum.accumulate(v_list).tolist()
    return BasinTable(h_m=h_list, area_m2=a_list, volume_m3=v_list)


def area_at(basin: BasinTable, h: float | np.ndarray) -> np.ndarray | float:
    """Interpolated A(h), clamped below by MIN_AREA_M2 and held at the table ends."""
    a = np.interp(h, basin.h_m, basin.area_m2)
    return np.maximum(a, MIN_AREA_M2)


def volume_at(basin: BasinTable, h: float | np.ndarray) -> np.ndarray | float:
    return np.interp(h, basin.h_m, basin.volume_m3)


def level_from_volume(basin: BasinTable, v: float) -> float:
    return float(np.interp(v, basin.volume_m3, basin.h_m))


# ------------------------------------------------------------------ IO
def save_twin_grid(twin_dir: str, heightmap: np.ndarray, cell_m: float, origin_xy, datum_offset_m: float) -> None:
    os.makedirs(twin_dir, exist_ok=True)
    np.save(os.path.join(twin_dir, "heightmap.npy"), heightmap.astype(np.float32))
    with open(os.path.join(twin_dir, "heightmap_meta.json"), "w") as f:
        json.dump({"cell_m": cell_m, "origin_xy": [float(origin_xy[0]), float(origin_xy[1])],
                   "datum_offset_m": float(datum_offset_m)}, f, indent=2)


def load_twin_grid(twin_dir: str) -> tuple[np.ndarray, dict]:
    hm = np.load(os.path.join(twin_dir, "heightmap.npy"))
    with open(os.path.join(twin_dir, "heightmap_meta.json")) as f:
        meta = json.load(f)
    return hm, meta


def save_basin(twin_dir: str, basin: BasinTable) -> str:
    os.makedirs(twin_dir, exist_ok=True)
    path = os.path.join(twin_dir, "basin.csv")
    basin.to_csv(path)
    return path


def load_basin(twin_dir: str) -> BasinTable:
    return BasinTable.from_csv(os.path.join(twin_dir, "basin.csv"))


# ------------------------------------------------------------------ tape-grid fallback
def load_tape_grid(csv_path: str, cell_m: float = DEFAULT_CELL_M) -> tuple[np.ndarray, tuple[float, float]]:
    """Fallback heightmap from a hand survey CSV ``x_m,y_m,height_cm``.

    Linear interpolation inside the surveyed hull; outside stays NaN (unknown).
    Returned heights are in metres, shifted to datum.
    """
    import csv

    xs, ys, zs = [], [], []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            xs.append(float(row["x_m"]))
            ys.append(float(row["y_m"]))
            zs.append(float(row["height_cm"]) / 100.0)
    if len(xs) < 3:
        raise ValueError("tape grid needs at least 3 points")
    xs, ys, zs = map(np.asarray, (xs, ys, zs))
    x0, y0 = xs.min(), ys.min()
    cols = int(np.ceil((xs.max() - x0) / cell_m)) + 1
    rows = int(np.ceil((ys.max() - y0) / cell_m)) + 1
    gx = x0 + np.arange(cols) * cell_m
    gy = y0 + np.arange(rows) * cell_m
    GX, GY = np.meshgrid(gx, gy)
    hm = griddata((xs, ys), zs, (GX, GY), method="linear").astype(np.float32)
    hm, _ = to_datum(hm)
    return hm, (float(x0), float(y0))


def build_twin_from_tape_grid(csv_path: str, twin_dir: str, cell_m: float = DEFAULT_CELL_M) -> BasinTable:
    hm, origin = load_tape_grid(csv_path, cell_m)
    save_twin_grid(twin_dir, hm, cell_m, origin, datum_offset_m=0.0)
    basin = build_basin_from_heightmap(hm, cell_m)
    save_basin(twin_dir, basin)
    return basin


def build_twin_from_points(
    points_xyz: np.ndarray, twin_dir: str, cell_m: float = DEFAULT_CELL_M
) -> tuple[np.ndarray, BasinTable, float]:
    """points must already be metric and up-aligned (see twin.calibrate)."""
    hm, origin = heightmap_from_points(points_xyz, cell_m)
    hm = fill_small_holes(hm)
    hm, datum = to_datum(hm)
    save_twin_grid(twin_dir, hm, cell_m, origin, datum_offset_m=datum)
    basin = build_basin_from_heightmap(hm, cell_m)
    save_basin(twin_dir, basin)
    return hm, basin, datum


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Build heightmap and basin.csv for a site")
    ap.add_argument("--twin-dir", required=True)
    ap.add_argument("--points", help="points_metric.npy (N,3), already calibrated and up-aligned")
    ap.add_argument("--tape-grid", help="validation/data/tape_grid.csv fallback")
    ap.add_argument("--cell", type=float, default=DEFAULT_CELL_M)
    a = ap.parse_args()
    if a.tape_grid:
        b = build_twin_from_tape_grid(a.tape_grid, a.twin_dir, a.cell)
    elif a.points:
        _, b, _ = build_twin_from_points(np.load(a.points), a.twin_dir, a.cell)
    else:
        ap.error("give --points or --tape-grid")
    print(f"basin.csv written: {len(b.h_m)} levels, max h {b.h_m[-1]:.2f} m, "
          f"max area {b.area_m2[-1]:.2f} m2, max volume {b.volume_m3[-1]:.3f} m3")
