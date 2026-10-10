import csv
import os

import numpy as np
import pytest

from contracts.schemas import BasinTable
from twin.basin import (
    area_at,
    build_basin_from_heightmap,
    build_twin_from_tape_grid,
    fill_small_holes,
    heightmap_from_points,
    load_basin,
    save_basin,
    to_datum,
    volume_at,
)
from twin.calibrate import apply_transform, check_stick, fit_scale_and_up, make_transform, umeyama

A_COEF = 0.1  # bowl z = A*(x^2+y^2)


def bowl(cell=0.02, half=1.5):
    g = np.arange(-half, half + 1e-9, cell)
    X, Y = np.meshgrid(g, g)
    return (A_COEF * (X**2 + Y**2)).astype(np.float32), X, Y


def test_basin_matches_paraboloid_analytics():
    hm, _, _ = bowl(cell=0.02)
    basin = build_basin_from_heightmap(hm, cell_m=0.02, max_h_m=0.2)
    assert basin.h_m[0] == 0.0 and abs(basin.h_m[-1] - 0.2) < 1e-6
    for h, a, v in zip(basin.h_m, basin.area_m2, basin.volume_m3):
        if h < 0.05:
            continue
        a_true = np.pi * h / A_COEF
        v_true = np.pi * h**2 / (2 * A_COEF)
        assert abs(a - a_true) / a_true < 0.05, (h, a, a_true)
        assert abs(v - v_true) / v_true < 0.05, (h, v, v_true)
    assert np.all(np.diff(basin.area_m2) >= 0) and np.all(np.diff(basin.volume_m3) >= 0)


def test_basin_excludes_disconnected_puddle():
    hm, X, Y = bowl(cell=0.05)
    # second, separate dip in the corner, lower than the main bowl's rim but not connected at h=0.1
    hm[(X > 1.0) & (Y > 1.0)] = 0.02
    hm, _ = to_datum(hm)
    basin = build_basin_from_heightmap(hm, cell_m=0.05, max_h_m=0.1)
    a_true = np.pi * 0.1 / A_COEF
    assert abs(basin.area_m2[-1] - a_true) / a_true < 0.1   # corner puddle not counted


def test_basin_requires_datum():
    hm, _, _ = bowl()
    with pytest.raises(ValueError):
        build_basin_from_heightmap(hm + 0.5, cell_m=0.02)


def test_heightmap_from_points_and_holes():
    rng = np.random.default_rng(0)
    pts = rng.uniform(-1, 1, size=(40000, 2))
    z = A_COEF * (pts**2).sum(1)
    # stray points above ground must not raise the floor
    z[:500] += 0.5
    hm, origin = heightmap_from_points(np.column_stack([pts, z]), cell_m=0.05)
    assert np.isfinite(hm).mean() > 0.95
    r, c = hm.shape[0] // 2, hm.shape[1] // 2
    assert hm[r, c] < 0.01
    hm[5:8, 5:8] = np.nan                # small hole -> filled
    hm[20:30, 20:30] = np.nan            # big hole -> stays unknown
    f = fill_small_holes(hm, max_hole_cells=25)
    assert np.isfinite(f[5:8, 5:8]).all()
    assert not np.isfinite(f[20:30, 20:30]).any()


def test_area_interp_clamps():
    b = BasinTable(h_m=[0, 0.1, 0.2], area_m2=[0, 1, 2], volume_m3=[0, 0.05, 0.2])
    assert area_at(b, 0.0) == pytest.approx(0.05)
    assert area_at(b, 0.15) == pytest.approx(1.5)
    assert area_at(b, 5.0) == pytest.approx(2.0)
    assert volume_at(b, 0.1) == pytest.approx(0.05)


def test_save_load_basin(tmp_path):
    b = BasinTable(h_m=[0, 0.01], area_m2=[0.1, 0.2], volume_m3=[0, 0.0015])
    save_basin(str(tmp_path), b)
    b2 = load_basin(str(tmp_path))
    assert b2.h_m == pytest.approx(b.h_m) and b2.area_m2 == pytest.approx(b.area_m2)


def test_tape_grid_fallback(tmp_path):
    rng = np.random.default_rng(1)
    p = tmp_path / "tape_grid.csv"
    with open(p, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["x_m", "y_m", "height_cm"])
        for x in np.linspace(-1.5, 1.5, 13):
            for y in np.linspace(-1.5, 1.5, 13):
                w.writerow([f"{x:.3f}", f"{y:.3f}", f"{100 * A_COEF * (x**2 + y**2) + rng.normal(0, 0.3):.1f}"])
    basin = build_twin_from_tape_grid(str(p), str(tmp_path / "twin"), cell_m=0.05)
    assert os.path.exists(tmp_path / "twin" / "basin.csv")
    h = 0.1
    i = int(round(h / 0.01))
    assert abs(basin.area_m2[i] - np.pi * h / A_COEF) / (np.pi * h / A_COEF) < 0.15


def _random_similarity(rng):
    q = rng.normal(size=4)
    q /= np.linalg.norm(q)
    w, x, y, z = q
    R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    return rng.uniform(0.5, 2.0), R, rng.normal(size=3)


def test_fit_scale_and_up_recovers_transform():
    rng = np.random.default_rng(2)
    metric = rng.uniform(-2, 2, size=(8, 3))
    metric[:, 2] = rng.uniform(0, 0.4, size=8)          # mark heights 0..40 cm
    s, R, t = _random_similarity(rng)
    recon = (metric - t) @ R / s                      # inverse: metric = s R recon + t
    cal = fit_scale_and_up(recon, metric[:, 2])
    assert cal.scale == pytest.approx(s, rel=1e-6)
    up_true = R.T @ np.array([0, 0, 1.0])              # metric z axis in recon coords
    assert abs(np.dot(cal.up, up_true)) > 0.99999
    assert cal.max_abs_m < 1e-6 and cal.ok
    z_out = apply_transform(np.asarray(cal.transform), recon)[:, 2]
    assert np.allclose(z_out, metric[:, 2], atol=1e-6)
    # with 1 cm noise the residual stays under the 2 cm recapture limit
    cal2 = fit_scale_and_up(recon, metric[:, 2] + rng.normal(0, 0.005, 8))
    assert cal2.ok and abs(cal2.scale - s) / s < 0.05


def test_fit_rejects_degenerate_marks():
    with pytest.raises(ValueError):
        fit_scale_and_up(np.zeros((3, 3)), np.array([0, 0.1, 0.2]))
    with pytest.raises(ValueError):
        fit_scale_and_up(np.random.default_rng(0).normal(size=(5, 3)), np.full(5, 0.1))


def test_umeyama_and_stick():
    rng = np.random.default_rng(3)
    src = rng.normal(size=(10, 3))
    s, R, t = _random_similarity(rng)
    dst = s * src @ R.T + t
    s2, R2, t2 = umeyama(src, dst)
    assert s2 == pytest.approx(s, rel=1e-9) and np.allclose(R2, R) and np.allclose(t2, t)
    chk = check_stick(np.zeros(3), np.array([1.0 / s, 0, 0]), s)
    assert chk["ok"] and chk["measured_m"] == pytest.approx(1.0)
    T = make_transform(2.0, [0, 0, 1], 0.5)
    assert apply_transform(T, np.array([[1, 1, 1.0]]))[0, 2] == pytest.approx(2.5)
