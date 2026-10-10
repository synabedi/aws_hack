import json
import os

import cv2
import numpy as np
import pytest

from contracts.schemas import Reading
from sense.depthmap import depth_map_cm, max_depth_cm, render_heatmap
from sense.level import (
    angle_deg, extract_waterline, fit_plane_ransac, measure, robust_level, waterline_heights,
)
from twin.basin import build_basin_from_heightmap, save_basin, save_twin_grid

A_COEF = 0.2
CELL = 0.01
N = 200


@pytest.fixture(scope="module")
def twin(tmp_path_factory):
    """Orthographic 'camera' over a bowl: pixel (i, j) sees (x_j, y_i, z)."""
    d = tmp_path_factory.mktemp("twin")
    g = -1.0 + np.arange(N) * CELL
    X, Y = np.meshgrid(g, g)
    Z = A_COEF * (X**2 + Y**2)
    # a kerb: vertical wall at x > 0.9 raises ground by 30 cm (steep edge -> preferred waterline pixels)
    Z = Z + np.where(X > 0.9, 0.3, 0.0)
    pm = np.stack([X, Y, Z], axis=-1).astype(np.float32)
    np.save(d / "ref_pointmap_metric.npy", pm)
    save_twin_grid(str(d), Z.astype(np.float32), CELL, (-1.0, -1.0), datum_offset_m=0.0)
    save_basin(str(d), build_basin_from_heightmap(Z.astype(np.float32), CELL, max_h_m=0.3))
    frame = np.full((N, N, 3), 120, np.uint8)
    cv2.imwrite(str(d / "frame.jpg"), frame)
    return {"dir": str(d), "pm": pm, "Z": Z, "frame": str(d / "frame.jpg")}


def test_measure_recovers_level_and_max_depth(twin):
    L = 0.10
    mask = twin["Z"] < L
    r = measure("s1", twin["frame"], mask, twin["dir"], ts=100.0, check_up=True)
    assert r.status == "confident", r.checks_failed
    assert abs(r.level_m - L) < 0.005, r.level_m
    assert abs(r.max_depth_cm - 10.0) < 0.6, r.max_depth_cm
    assert r.sigma_cm < 1.0 and r.n_waterline_points >= 50


def test_measure_resists_occluded_boundary(twin):
    """A wedge of the pool is masked out (occluder): boundary pixels now include deep
    points. The high-percentile level must still read the true level within 1 cm."""
    L = 0.10
    mask = twin["Z"] < L
    X = twin["pm"][..., 0]
    Y = twin["pm"][..., 1]
    mask &= ~((X < 0) & (np.abs(Y) < 0.15))      # occluded strip through the middle
    r = measure("s1", twin["frame"], mask, twin["dir"], ts=100.0)
    assert abs(r.level_m - L) < 0.01, r.level_m


def test_measure_uses_exclude_mask_and_temporal_check(twin):
    L = 0.10
    mask = twin["Z"] < L
    ex = np.zeros_like(mask)
    ex[80:120, 80:120] = True                       # a "vehicle" in the middle
    prev = Reading(site_id="s1", ts=90.0, level_m=0.30, max_depth_cm=30, sigma_cm=1, status="confident", frame_uri="x")
    r = measure("s1", twin["frame"], mask, twin["dir"], prev_reading=prev, exclude_mask=ex, ts=100.0)
    assert "temporal_jump" in r.checks_failed and r.status == "low_confidence"
    assert abs(r.level_m - L) < 0.005
    r2 = measure("s1", twin["frame"], mask, twin["dir"], prev_reading=prev, ts=100.0, rain_mm_h=50.0)
    assert "temporal_jump" not in r2.checks_failed


def test_measure_fails_cleanly_on_empty_mask(twin):
    r = measure("s1", twin["frame"], np.zeros((N, N), bool), twin["dir"], ts=1.0)
    assert r.status == "failed" and r.n_waterline_points == 0


def test_measure_few_points_is_low_confidence(twin):
    mask = twin["Z"] < 0.0004       # a few pixels around the centre
    r = measure("s1", twin["frame"], mask, twin["dir"], ts=1.0)
    assert r.status in ("low_confidence", "failed")
    if r.status == "low_confidence":
        assert "few_points" in r.checks_failed


def test_measure_writes_outputs(twin, tmp_path):
    mask = twin["Z"] < 0.1
    r = measure("s1", twin["frame"], mask, twin["dir"], ts=1.0, out_dir=str(tmp_path))
    assert r.mask_uri and os.path.exists(r.mask_uri)
    assert r.depthmap_uri and os.path.exists(r.depthmap_uri)
    assert r.model_dump()["status"] == "confident"


def test_max_depth_hidden_deepest_point(twin):
    """Deepest cell is counted even when the visible water does not cover it."""
    Z = twin["Z"].astype(np.float32)
    meta = json.load(open(os.path.join(twin["dir"], "heightmap_meta.json")))
    vis = np.array([[0.5, 0.0]])             # visible water only at x=0.5 (z=0.05)
    mx, rc = max_depth_cm(0.10, Z, meta, vis)
    assert abs(mx - 10.0) < 0.1 and rc == (100, 100)
    mx2, _ = max_depth_cm(0.10, Z, meta, np.array([[0.95, 0.0]]))   # seed on the kerb top (above level)
    assert mx2 == pytest.approx(10.0, abs=0.1)                       # falls back to global pool


def test_depth_map_and_heatmap(twin, tmp_path):
    mask = twin["Z"] < 0.1
    d = depth_map_cm(0.1, twin["pm"], mask)
    assert np.nanmax(d) == pytest.approx(10.0, abs=0.05)
    assert np.isnan(d[~mask]).all()
    out = render_heatmap(twin["frame"], d, str(tmp_path / "h.png"))
    assert os.path.exists(out)


def test_waterline_and_percentile():
    m = np.zeros((50, 50), bool)
    m[10:40, 10:40] = True
    rc = extract_waterline(m)
    assert len(rc) == 4 * 30 - 4
    z = np.concatenate([np.full(900, 0.1), np.full(100, 0.0)])   # 10% occluded low points
    lvl, sig = robust_level(z)
    assert lvl == pytest.approx(0.1) and sig < 0.01


def test_waterline_prefers_steep_pixels():
    H = W = 120
    z = np.tile(np.linspace(0, 1.2, W), (H, 1))          # 1 cm/px slope (too flat: 0.01 <= 0.02 ok)
    z[:, 60:] += 5.0                                      # 5 m step at col 60 -> huge sensitivity there
    pm = np.stack([np.zeros((H, W)), np.zeros((H, W)), z], -1)
    m = np.zeros((H, W), bool)
    m[20:100, 20:100] = True
    rc = extract_waterline(m)
    heights, _ = waterline_heights(rc, pm)
    assert len(heights) >= 50 and not np.any(np.isin(heights, z[0, 59:61]))   # step pixels dropped


def test_ransac_plane():
    rng = np.random.default_rng(0)
    P = rng.uniform(-1, 1, (300, 3))
    P[:, 2] = 0.2 + rng.normal(0, 0.002, 300)
    P[:40, 2] += rng.uniform(0.1, 0.5, 40)           # outliers
    n, d, inl = fit_plane_ransac(P)
    assert angle_deg(n, [0, 0, 1]) < 1.0 and abs(d - 0.2) < 0.01 and inl.sum() >= 250
