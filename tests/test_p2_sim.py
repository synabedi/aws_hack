import numpy as np

from sim.generate import bowl_basin, make_sites, rain_scenario, synthetic_readings
from sim.replay_lambda import current_readings, handler


def test_bowl_basin_analytic():
    b = bowl_basin(0.004, half_m=15.0, max_h_m=0.5)
    i = b.h_m.index(0.2)
    assert abs(b.area_m2[i] - np.pi * 0.2 / 0.004) < 1e-6
    assert abs(b.volume_m3[i] - np.pi * 0.04 / 0.008) < 1e-6
    assert all(np.diff(b.area_m2) >= 0) and all(np.diff(b.volume_m3) >= 0)


def test_sites_are_labelled_and_realistic():
    sites = make_sites(6, seed=0)
    assert len(sites) == 6 and len({s.site_id for s, *_ in sites}) == 6
    peaks = []
    for site, basin, params, forcing in sites:
        assert site.simulated and params.source == "synthetic" and site.name_hi and site.diversion_hi
        rs = synthetic_readings(site, basin, params, forcing, t0=1e9)
        assert rs and all(r.simulated and r.source == "synthetic" and r.site_id == site.site_id for r in rs)
        peaks.append(max(r.max_depth_cm for r in rs))
    assert max(peaks) < 100.0 and max(peaks) > 15.0          # at least one site crosses the closure rule
    assert make_sites(50)[0][0].site_id == "sim_minto"         # capped at the hotspot list


def test_scenarios_and_replay(monkeypatch):
    for k in ("cloudburst", "steady", "two_bursts", "drizzle"):
        f = rain_scenario(k)
        assert len(f.t_s) == len(f.intensity_mm_h) and max(f.intensity_mm_h) > 0
    monkeypatch.setenv("JALMAAPI_BACKEND", "local")
    rows = current_readings(now=1_700_000_000.0 + 1800)
    assert len(rows) == 6 and all(r["simulated"] for r in rows)
    out = handler({}, None)
    assert "dry_run" in out and len(out["dry_run"]) == 6
