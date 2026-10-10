"""The site model: one basin, orifice-style drain, optional pumps.

    A(h) dh/dt = R * i(t) / 3.6e6  -  k * sqrt(max(h - h0, 0))  -  Q_pump(t)

h in m above datum, A in m^2 (from the basin table), i in mm/h, R in m^2,
k in m^2.5/s, Q_pump in m^3/s. The water cannot go below the floor (h >= 0) and a
pump cannot draw below h0. See contracts/schemas.py for unit conventions.

Linear-reservoir fallback (``drain="linear"``): Q_out = k * max(h - h0, 0), k in m^2/s.
"""
from __future__ import annotations

from typing import Callable, Literal

import numpy as np
from scipy.integrate import solve_ivp

from contracts.schemas import BasinTable, Forcing, SiteParams
from twin.basin import area_at

MM_H_TO_M_S = 1.0 / 3.6e6
DrainLaw = Literal["orifice", "linear"]


def inflow_m3_s(R: float, intensity_mm_h: float) -> float:
    return R * intensity_mm_h * MM_H_TO_M_S


HEAD_EPS_M = 1e-4   # regularises sqrt(head) at the outlet so the ODE is not stiff at the floor
PUMP_RAMP_M = 0.01  # a pump draws nothing at the floor and full rate from 1 cm of water up (no on/off chatter)


def outflow_m3_s(k: float, h: float, h0: float, drain: DrainLaw = "orifice") -> float:
    head = max(h - h0, 0.0)
    if drain == "orifice":
        # == k*sqrt(head) for head >> HEAD_EPS_M, linear (finite slope) below it
        return k * head / np.sqrt(head + HEAD_EPS_M)
    return k * head


def make_forcing_fn(forcing: Forcing) -> Callable[[float], float]:
    t = np.asarray(forcing.t_s, dtype=float)
    i = np.asarray(forcing.intensity_mm_h, dtype=float)
    if len(t) == 0:
        return lambda _t: 0.0
    if len(t) == 1:
        return lambda _t: float(i[0])
    # step-hold: intensity applies from its timestamp until the next one; last value held
    def fn(tt: float) -> float:
        j = int(np.searchsorted(t, tt, side="right") - 1)
        return float(i[max(j, 0)])
    return fn


def make_pump_fn(pumps: int | Callable[[float], int], pump_rate_m3_s: float) -> Callable[[float], float]:
    if callable(pumps):
        return lambda t: float(pumps(t)) * pump_rate_m3_s
    return lambda _t: float(pumps) * pump_rate_m3_s


def rhs_factory(params: SiteParams, basin: BasinTable, forcing_fn, pump_fn, drain: DrainLaw = "orifice"):
    R, k, h0 = float(params.R), float(params.k), float(params.h0)

    def rhs(t, y):
        h = float(y[0])
        q_in = inflow_m3_s(R, forcing_fn(t))
        q_out = outflow_m3_s(k, h, h0, drain)
        q_pump = pump_fn(t) * min(max((h - max(h0, 0.0)) / PUMP_RAMP_M, 0.0), 1.0)
        net = q_in - q_out - q_pump
        if h <= 0.0 and net < 0.0:
            return [0.0]
        return [net / float(area_at(basin, max(h, 0.0)))]

    return rhs


def integrate(
    params: SiteParams,
    basin: BasinTable,
    forcing: Forcing,
    h_init: float,
    t_end_s: float,
    pumps: int | Callable[[float], int] = 0,
    pump_rate_m3_s: float = 0.02,
    t_eval: np.ndarray | None = None,
    t_start_s: float = 0.0,
    drain: DrainLaw = "orifice",
    max_step_s: float = 5.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Integrate the site model from (t_start_s, h_init) to t_end_s.

    Returns (t_s, h_m). h is clamped at >= 0. ``t_eval`` defaults to 1 s spacing.
    """
    if t_eval is None:
        t_eval = np.arange(t_start_s, t_end_s + 1e-9, 1.0)
    t_eval = np.asarray(t_eval, dtype=float)
    if t_end_s <= t_start_s or len(t_eval) == 0:
        return np.array([t_start_s]), np.array([max(h_init, 0.0)])
    f = rhs_factory(params, basin, make_forcing_fn(forcing), make_pump_fn(pumps, pump_rate_m3_s), drain)
    sol = solve_ivp(f, (t_start_s, t_end_s), [max(h_init, 0.0)], t_eval=t_eval, method="LSODA",
                    max_step=max_step_s, rtol=1e-5, atol=1e-6)
    if not sol.success:
        raise RuntimeError(f"ODE integration failed: {sol.message}")
    return sol.t, np.clip(sol.y[0], 0.0, None)
