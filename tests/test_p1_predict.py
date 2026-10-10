import numpy as np
import pytest

from contracts.schemas import Forcing, Reading, SiteParams, Thresholds
from predict.drain_health import assess, compare_passes, fit_k_from_recession, score
from predict.fit import fit_params
from predict.forecast import fit_and_forecast
from predict.simulate import minutes_above_threshold, simulate
from predict.site_model import integrate
from predict.thresholds import assumed_classes, default_thresholds
from twin.basin import build_basin_from_heightmap

A_COEF = 0.1
R_TRUE, K_TRUE = 2.0, 0.0008        # hose 2 m^3/h (33 L/min) at i = 1000 mm/h (1 m/h); orifice k
HOSE = 1000.0   # mm/h == 1 m/h, so R [m^2] reads as m^3/h


@pytest.fixture(scope="module")
def basin():
    g = np.arange(-1.6, 1.6 + 1e-9, 0.04)
    X, Y = np.meshgrid(g, g)
    return build_basin_from_heightmap((A_COEF * (X**2 + Y**2)).astype(np.float32), 0.04, max_h_m=0.25)


def fill_then_drain(t_on=600.0, t_end=1800.0):
    return Forcing(t_s=[0.0, t_on], intensity_mm_h=[HOSE, 0.0], source="hose")


def make_readings(basin, params, forcing, t_end, dt=30.0, noise_cm=0.5, seed=0, t0=1_700_000_000.0):
    rng = np.random.default_rng(seed)
    t_eval = np.arange(0, t_end + 1e-9, dt)
    t, h = integrate(params, basin, forcing, 0.0, t_end, t_eval=t_eval)
    out = []
    for ti, hi in zip(t, h):
        lvl = max(hi + rng.normal(0, noise_cm / 100), 0.0)
        out.append(Reading(site_id="s1", ts=t0 + ti, level_m=lvl, max_depth_cm=lvl * 100, sigma_cm=noise_cm,
                           status="confident", frame_uri="synthetic", source="synthetic"))
    return out, t, h


def test_integrate_fills_and_drains(basin):
    p = SiteParams(R=R_TRUE, k=K_TRUE)
    t, h = integrate(p, basin, fill_then_drain(), 0.0, 1800.0)
    i_peak = int(np.argmax(h))
    assert 0.1 < h[i_peak] < 0.3, h[i_peak]
    assert abs(t[i_peak] - 600) <= 10
    assert h[-1] < h[i_peak] * 0.6 and h.min() >= 0
    # pumps lower the peak
    _, hp = integrate(p, basin, fill_then_drain(), 0.0, 1800.0, pumps=1, pump_rate_m3_s=0.0002)
    assert hp.max() < h.max()


def test_fit_recovers_R_and_k(basin):
    p = SiteParams(R=R_TRUE, k=K_TRUE)
    rs, _, _ = make_readings(basin, p, fill_then_drain(), 1800.0)
    fit = fit_params(rs, fill_then_drain(), basin, prior=SiteParams(R=2.0, k=0.003))
    assert fit.source == "fitted"
    assert abs(fit.R - R_TRUE) / R_TRUE < 0.15, fit
    assert abs(fit.k - K_TRUE) / K_TRUE < 0.25, fit
    assert fit.R_sigma is not None and fit.k_sigma is not None and fit.R_sigma < 0.2 * R_TRUE


def test_fit_rise_only_fixes_k(basin):
    p = SiteParams(R=R_TRUE, k=K_TRUE)
    rs, _, _ = make_readings(basin, p, fill_then_drain(), 420.0)   # rising limb only
    fit = fit_params(rs, fill_then_drain(), basin, prior=SiteParams(R=2.0, k=K_TRUE))
    assert fit.k == pytest.approx(K_TRUE)          # not identifiable -> fixed to prior
    assert abs(fit.R - R_TRUE) / R_TRUE < 0.15


def test_fit_falls_back_to_prior_with_few_readings(basin):
    p = SiteParams(R=R_TRUE, k=K_TRUE)
    rs, _, _ = make_readings(basin, p, fill_then_drain(), 60.0)
    rs = rs[:2]
    fit = fit_params(rs, fill_then_drain(), basin, prior=SiteParams(R=3.0, k=0.01))
    assert fit.source == "prior" and fit.R == 3.0


def test_forecast_time_to_threshold_from_first_40pct(basin):
    """Doc 13.4: using only the first 40% of pass A, predicted time to target depth within 20%."""
    p = SiteParams(R=R_TRUE, k=K_TRUE)
    forcing = Forcing(t_s=[0.0], intensity_mm_h=[HOSE], source="hose")
    rs, t, h = make_readings(basin, p, forcing, 600.0)
    target_cm = 10.0
    t_true = float(t[np.argmax(h * 100 >= target_cm)])
    assert t_true > 0
    cut = rs[: int(0.4 * len(rs))]
    th = Thresholds(closure=target_cm)
    fc = fit_and_forecast(cut, forcing, basin, th, horizon_min=30, prior=SiteParams(R=2.0, k=K_TRUE))
    assert fc.confidence == "confident"
    t_pred = (cut[-1].ts - rs[0].ts) + fc.t_impassable_min["closure"] * 60
    assert abs(t_pred - t_true) / t_true < 0.2, (t_pred, t_true)
    assert fc.t_impassable_p10["closure"] <= fc.t_impassable_min["closure"] <= fc.t_impassable_p90["closure"]
    assert len(fc.t) == len(fc.depth) == len(fc.p10) == len(fc.p90) == 31
    assert all(a <= b <= c for a, b, c in zip(fc.p10, fc.depth, fc.p90))


def test_forecast_low_confidence_without_confident_readings(basin):
    rs = [Reading(site_id="s1", ts=1e9 + i * 30, level_m=0.05, max_depth_cm=5, sigma_cm=8, status="low_confidence",
                  frame_uri="x") for i in range(4)]
    fc = fit_and_forecast(rs, fill_then_drain(), basin, Thresholds(), horizon_min=20)
    assert fc.confidence == "low_confidence" and "prior" in (fc.note or "")


def test_simulate_pumps_reduce_minutes_above_threshold(basin):
    p = SiteParams(R=R_TRUE, k=K_TRUE, source="fitted")
    forcing = Forcing(t_s=[0.0], intensity_mm_h=[HOSE], source="hose")
    rs, _, _ = make_readings(basin, p, forcing, 300.0)
    th = Thresholds()
    f0 = simulate(rs, forcing, basin, th, p, pumps=0, minutes=60, pump_rate_m3_s=0.0002)
    f2 = simulate(rs, forcing, basin, th, p, pumps=2, minutes=60, pump_rate_m3_s=0.0002)
    m0, m2 = minutes_above_threshold(f0, th.closure), minutes_above_threshold(f2, th.closure)
    assert m2 < m0 and f2.pumps == 2 and f0.confidence == "confident"


def test_drain_health_blocked_outlet_has_lower_k(basin):
    rec = Forcing(t_s=[0.0], intensity_mm_h=[0.0], source="recession")
    rs_open, _, _ = make_readings(basin, SiteParams(R=0, k=K_TRUE), rec, 900.0, seed=1)
    rs_block, _, _ = make_readings(basin, SiteParams(R=0, k=K_TRUE * 0.4), rec, 900.0, seed=2)
    # start both from the same filled level
    for rs in (rs_open, rs_block):
        for r in rs:
            r.level_m += 0.0
    start = 0.2
    rs_open = _from_level(basin, K_TRUE, start, rec, 1)
    rs_block = _from_level(basin, K_TRUE * 0.4, start, rec, 2)
    kb = fit_k_from_recession(rs_open, basin)
    kc = fit_k_from_recession(rs_block, basin)
    cmp = compare_passes(kb, kc)
    assert abs(kb[0] - K_TRUE) / K_TRUE < 0.2
    assert cmp["ratio"] < 0.7 and not cmp["intervals_overlap"], cmp
    hist = []
    d1 = assess("s1", "e1", kb[0], kb[1], hist)
    assert d1.score_pct == pytest.approx(100.0) and not d1.flagged
    hist.append(d1)
    d2 = assess("s1", "e2", kc[0], kc[1], hist)
    assert d2.score_pct < 60 and not d2.flagged          # first low event: not yet flagged
    hist.append(d2)
    d3 = assess("s1", "e3", kc[0], kc[1], hist)
    assert d3.flagged                                      # second consecutive low event
    assert score(0.5, 1.0) == 50.0


def _from_level(basin, k, h_start, forcing, seed):
    rng = np.random.default_rng(seed)
    t_eval = np.arange(0, 900 + 1e-9, 30.0)
    t, h = integrate(SiteParams(R=0, k=k), basin, forcing, h_start, 900.0, t_eval=t_eval)
    return [Reading(site_id="s1", ts=1e9 + ti, level_m=max(hi + rng.normal(0, 0.005), 0), max_depth_cm=hi * 100,
                    sigma_cm=0.5, status="confident", frame_uri="x") for ti, hi in zip(t, h)]


def test_thresholds_yaml():
    th = default_thresholds()
    assert th == Thresholds()
    assert assumed_classes() == {"two_wheeler", "bus_truck"}
