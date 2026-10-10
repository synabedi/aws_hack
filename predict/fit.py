"""Fit R and k of the site model to a measured depth curve.

Sigma-weighted nonlinear least squares (scipy.optimize.least_squares, bounds >= 0).
R is pinned by the rising limb while it rains; k by the recession after inflow stops.
With rise-only data, k is fixed (``fix_k`` or the prior) and R alone is fitted.
Parameter uncertainty comes from the Jacobian: cov = (J^T J)^-1 * s^2 with s^2 the
reduced chi-square (floored at 1 so sigmas are never optimistic).

Time convention: model time t_s = reading.ts - t0 where t0 = ``t0`` kwarg or the
first reading's ts. The Forcing must use the same origin.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares

from contracts.schemas import BasinTable, Forcing, Reading, SiteParams, now_ts
from predict.site_model import DrainLaw, integrate, make_forcing_fn
from twin.basin import area_at

DEFAULT_PRIOR = SiteParams(R=50.0, k=0.01, h0=0.0, source="prior")


def _pump_schedule(readings: list[Reading]):
    ts = np.array([r.ts for r in readings])
    pumps = np.array([r.pumps_on for r in readings])

    def fn(t_abs: float) -> int:
        j = int(np.searchsorted(ts, t_abs, side="right") - 1)
        return int(pumps[max(j, 0)])

    return fn


def _has_recession(readings: list[Reading], forcing: Forcing, t0: float) -> bool:
    """True if at least 3 confident readings fall where inflow is ~0 (k identifiable)."""
    ffn = make_forcing_fn(forcing)
    n = sum(1 for r in readings if ffn(r.ts - t0) < 0.5)
    return n >= 3


def _has_inflow(readings: list[Reading], forcing: Forcing, t0: float) -> bool:
    """True if at least 2 readings fall where inflow is > 0 (R identifiable)."""
    ffn = make_forcing_fn(forcing)
    n = sum(1 for r in readings if ffn(r.ts - t0) >= 0.5)
    return n >= 2


def initial_guess(readings: list[Reading], forcing: Forcing, basin: BasinTable, t0: float,
                  prior: SiteParams) -> tuple[float, float]:
    """Rough R from the steepest rise, k from the recession slope; fall back to prior."""
    ffn = make_forcing_fn(forcing)
    t = np.array([r.ts - t0 for r in readings])
    h = np.array([r.level_m for r in readings])
    R0, k0 = prior.R, prior.k
    if len(t) >= 2:
        dh = np.diff(h) / np.maximum(np.diff(t), 1e-6)
        hm = 0.5 * (h[1:] + h[:-1])
        im = np.array([ffn(0.5 * (a + b)) for a, b in zip(t[1:], t[:-1])])
        rise = (im > 0.5) & (dh > 0)
        if rise.any():
            A = np.asarray(area_at(basin, hm[rise]))
            R0 = float(np.median(A * dh[rise] / (im[rise] / 3.6e6)))
        rec = (im <= 0.5) & (dh < 0) & (hm > prior.h0 + 0.005)
        if rec.any():
            A = np.asarray(area_at(basin, hm[rec]))
            k0 = float(np.median(-A * dh[rec] / np.sqrt(hm[rec] - prior.h0)))
    return max(R0, 1e-3), max(k0, 1e-5)


def fit_params(
    readings: list[Reading],
    forcing: Forcing,
    basin: BasinTable,
    prior: SiteParams | None = None,
    fix_k: float | None = None,
    h0: float | None = None,
    t0: float | None = None,
    pump_rate_m3_s: float = 0.02,
    drain: DrainLaw = "orifice",
    confident_only: bool = True,
) -> SiteParams:
    prior = prior or DEFAULT_PRIOR
    rs = [r for r in readings if (r.status == "confident" or not confident_only)]
    rs = sorted(rs, key=lambda r: r.ts)
    if len(rs) < 3:
        return SiteParams(R=prior.R, k=prior.k, h0=prior.h0, source="prior", fitted_at=now_ts())
    t0 = rs[0].ts if t0 is None else t0
    h0 = prior.h0 if h0 is None else h0
    t = np.array([r.ts - t0 for r in rs])
    h_obs = np.array([r.level_m for r in rs])
    sig = np.array([max(r.sigma_cm, 0.3) / 100.0 for r in rs])
    pump_fn_abs = _pump_schedule(rs)
    pump_fn = lambda tt: pump_fn_abs(tt + t0)  # noqa: E731

    fit_k = fix_k is None and _has_recession(rs, forcing, t0)
    fit_R = _has_inflow(rs, forcing, t0)
    k_fixed = fix_k if fix_k is not None else prior.k
    R_fixed = prior.R if fit_R else 0.0
    R0, k0 = initial_guess(rs, forcing, basin, t0, prior)
    if not fit_k and not fit_R:
        return SiteParams(R=R_fixed, k=k_fixed, h0=h0, source="prior", fitted_at=now_ts())

    def model_h(R, k):
        p = SiteParams(R=R, k=k, h0=h0)
        _, hh = integrate(p, basin, forcing, h_obs[0], float(t[-1]), pumps=pump_fn,
                          pump_rate_m3_s=pump_rate_m3_s, t_eval=t, t_start_s=float(t[0]), drain=drain)
        return hh

    def unpack(x):
        i = 0
        if fit_R:
            R = x[i]
            i += 1
        else:
            R = R_fixed
        k = x[i] if fit_k else k_fixed
        return R, k

    def resid(x):
        R, k = unpack(x)
        return (model_h(R, k) - h_obs) / sig

    x0 = np.array(([R0] if fit_R else []) + ([k0] if fit_k else []))
    lb = np.zeros_like(x0)
    res = least_squares(resid, x0, bounds=(lb, np.inf), x_scale="jac", diff_step=1e-3, max_nfev=200)
    J = res.jac
    dof = max(len(h_obs) - len(res.x), 1)
    s2 = max(float(np.sum(res.fun**2) / dof), 1.0)
    try:
        cov = np.linalg.inv(J.T @ J) * s2
        sigmas = np.sqrt(np.clip(np.diag(cov), 0, None))
    except np.linalg.LinAlgError:
        sigmas = np.full(len(res.x), np.nan)
    R_hat, k_hat = unpack(res.x)
    R_sig = float(sigmas[0]) if fit_R and np.isfinite(sigmas[0]) else None
    k_idx = 1 if fit_R else 0
    k_sig = float(sigmas[k_idx]) if fit_k and np.isfinite(sigmas[k_idx]) else None
    return SiteParams(R=float(R_hat), k=float(k_hat), h0=h0, R_sigma=R_sig, k_sigma=k_sig,
                      fitted_at=now_ts(), source="fitted")
