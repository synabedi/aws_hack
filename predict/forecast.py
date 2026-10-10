"""Fit the site model to the measured depth curve and forecast minutes to impassable.

Forecast band: 100 parameter sets sampled from the fit covariance (truncated at 0),
each integrated forward over the horizon with the given rain forcing and pump count.
Per vehicle class, the crossing time is the first minute at which max depth reaches
the threshold; the median and 10th/90th percentiles of per-sample crossing times are
reported, ``None`` meaning "not within the horizon".

The depth curve starts from the last confident reading. ``forcing`` must cover the
future: its t_s runs from event start (first reading) through t_last + horizon.
"""
from __future__ import annotations

import numpy as np

from contracts.schemas import (
    VEHICLE_CLASSES,
    BasinTable,
    Forcing,
    Forecast,
    Reading,
    SiteParams,
    Thresholds,
)
from predict.fit import DEFAULT_PRIOR, fit_params
from predict.site_model import DrainLaw, integrate

MIN_CONFIDENT_READINGS = 3


def _crossing_minutes(t_min: np.ndarray, depth_cm: np.ndarray, threshold_cm: float) -> float | None:
    idx = np.nonzero(depth_cm >= threshold_cm)[0]
    return float(t_min[idx[0]]) if len(idx) else None


def _percentile_or_none(values: list[float | None], q: float) -> float | None:
    """Percentile of crossing times where None means "never within the horizon".
    Uses the nearest-rank method so infinities are never interpolated."""
    arr = np.array([np.inf if v is None else v for v in values], dtype=float)
    p = float(np.percentile(arr, q, method="nearest"))
    return None if not np.isfinite(p) else p


def sample_params(params: SiteParams, n: int, rng: np.random.Generator) -> list[SiteParams]:
    R_s = params.R_sigma if params.R_sigma is not None else 0.25 * params.R
    k_s = params.k_sigma if params.k_sigma is not None else 0.25 * params.k
    R = np.clip(rng.normal(params.R, R_s, n), 0.0, None)
    k = np.clip(rng.normal(params.k, k_s, n), 0.0, None)
    return [SiteParams(R=float(a), k=float(b), h0=params.h0) for a, b in zip(R, k)]


def forecast_from_params(
    params: SiteParams,
    h_start_m: float,
    t_start_s: float,
    site_id: str,
    ts: float,
    forcing: Forcing,
    basin: BasinTable,
    thresholds: Thresholds,
    pumps: int = 0,
    horizon_min: int = 60,
    pump_rate_m3_s: float = 0.02,
    n_samples: int = 100,
    seed: int = 0,
    drain: DrainLaw = "orifice",
    confidence: str = "confident",
    simulated: bool = False,
    note: str | None = None,
    rain_source: str = "scenario",
) -> Forecast:
    rng = np.random.default_rng(seed)
    t_eval = t_start_s + np.arange(0, horizon_min * 60 + 1, 60.0)
    t_min = (t_eval - t_start_s) / 60.0
    sets = [params] + (sample_params(params, n_samples - 1, rng) if n_samples > 1 else [])
    curves = []
    for p in sets:
        _, h = integrate(p, basin, forcing, h_start_m, float(t_eval[-1]), pumps=pumps,
                         pump_rate_m3_s=pump_rate_m3_s, t_eval=t_eval, t_start_s=t_start_s, drain=drain)
        curves.append(h * 100.0)
    C = np.stack(curves)                       # (samples, T) max depth cm
    med = np.median(C, axis=0)
    p10 = np.percentile(C, 10, axis=0)
    p90 = np.percentile(C, 90, axis=0)
    th = thresholds.as_dict()
    t_imp, t_p10, t_p90 = {}, {}, {}
    for c in VEHICLE_CLASSES:
        per_sample = [_crossing_minutes(t_min, row, th[c]) for row in C]
        t_imp[c] = _crossing_minutes(t_min, med, th[c])
        t_p10[c] = _percentile_or_none(per_sample, 10)
        t_p90[c] = _percentile_or_none(per_sample, 90)
    return Forecast(
        site_id=site_id, ts=ts, t=t_min.tolist(), depth=med.tolist(), p10=p10.tolist(), p90=p90.tolist(),
        t_impassable_min=t_imp, t_impassable_p10=t_p10, t_impassable_p90=t_p90,
        params={"R": params.R, "k": params.k, "h0": params.h0}, rain_source=rain_source,
        pumps=pumps, confidence=confidence, simulated=simulated, note=note,
    )


def fit_and_forecast(
    readings: list[Reading],
    forcing: Forcing,
    basin: BasinTable,
    thresholds: Thresholds,
    pumps: int = 0,
    horizon_min: int = 60,
    prior: SiteParams | None = None,
    pump_rate_m3_s: float = 0.02,
    n_samples: int = 100,
    seed: int = 0,
    drain: DrainLaw = "orifice",
    t0: float | None = None,
) -> Forecast:
    prior = prior or DEFAULT_PRIOR
    rs = sorted([r for r in readings if r.status == "confident"], key=lambda r: r.ts)
    if not rs:
        if not readings:
            raise ValueError("no readings")
        last = sorted(readings, key=lambda r: r.ts)[-1]
        rs_all = sorted(readings, key=lambda r: r.ts)
        t_start = last.ts - (rs_all[0].ts if t0 is None else t0)
        return forecast_from_params(
            prior, last.level_m, t_start, last.site_id, last.ts, forcing, basin, thresholds, pumps,
            horizon_min, pump_rate_m3_s, n_samples, seed, drain, confidence="low_confidence",
            simulated=last.simulated, note="no confident readings; forecast from prior parameters",
            rain_source=forcing.source,
        )
    t0 = rs[0].ts if t0 is None else t0
    params = fit_params(rs, forcing, basin, prior=prior, t0=t0, pump_rate_m3_s=pump_rate_m3_s, drain=drain)
    conf = "confident" if (params.source == "fitted" and len(rs) >= MIN_CONFIDENT_READINGS) else "low_confidence"
    note = None if conf == "confident" else f"only {len(rs)} confident readings; parameters from prior"
    last = rs[-1]
    return forecast_from_params(
        params, last.level_m, last.ts - t0, last.site_id, last.ts, forcing, basin, thresholds, pumps,
        horizon_min, pump_rate_m3_s, n_samples, seed, drain, confidence=conf, simulated=last.simulated,
        note=note, rain_source=forcing.source,
    )
