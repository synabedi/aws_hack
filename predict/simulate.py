"""What-if simulation for the agents: same site model, given parameters, N pumps.

No fitting here; ``params`` come from the site record (fitted or prior). Returns a
Forecast whose band reflects the parameter sigmas if present, else a 25% spread.
"""
from __future__ import annotations

from contracts.schemas import BasinTable, Forcing, Forecast, Reading, SiteParams, Thresholds
from predict.forecast import forecast_from_params


def simulate(
    readings: list[Reading],
    forcing: Forcing,
    basin: BasinTable,
    thresholds: Thresholds,
    params: SiteParams,
    pumps: int,
    minutes: int,
    pump_rate_m3_s: float = 0.02,
    t0: float | None = None,
    n_samples: int = 50,
) -> Forecast:
    rs = sorted(readings, key=lambda r: r.ts)
    if not rs:
        raise ValueError("simulate needs at least one reading for the starting level")
    t0 = rs[0].ts if t0 is None else t0
    last = rs[-1]
    conf = "confident" if (last.status == "confident" and params.source == "fitted") else "low_confidence"
    return forecast_from_params(
        params, last.level_m, last.ts - t0, last.site_id, last.ts, forcing, basin, thresholds,
        pumps=pumps, horizon_min=minutes, pump_rate_m3_s=pump_rate_m3_s, n_samples=n_samples,
        confidence=conf, simulated=last.simulated, note=f"what-if with {pumps} pump(s)",
        rain_source=forcing.source,
    )


def minutes_above_threshold(forecast: Forecast, threshold_cm: float) -> float:
    """Minutes within the horizon where the median depth is at or above the threshold."""
    if len(forecast.t) < 2:
        return 0.0
    dt = forecast.t[1] - forecast.t[0]
    return float(sum(dt for d in forecast.depth if d >= threshold_cm))
