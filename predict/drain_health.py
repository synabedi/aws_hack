"""Drain health from the fitted drain coefficient k.

k is fitted on a recession (no inflow, pumps off) with R fixed at 0. The confidence
interval is the Jacobian sigma; if a bootstrap is requested it resamples the readings.
Health score = latest k / best recorded k (percent). Flag when below 60% on two
consecutive events. One coefficient says the site drains slowly, not why.
"""
from __future__ import annotations

import numpy as np

from contracts.schemas import BasinTable, DrainHealth, Forcing, Reading, SiteParams, now_ts
from predict.fit import fit_params
from predict.site_model import DrainLaw

FLAG_BELOW_PCT = 60.0


def fit_k_from_recession(
    readings: list[Reading],
    basin: BasinTable,
    h0: float = 0.0,
    pump_rate_m3_s: float = 0.02,
    drain: DrainLaw = "orifice",
    n_bootstrap: int = 0,
    seed: int = 0,
) -> tuple[float, tuple[float, float]]:
    """Returns (k, (k_lo, k_hi)) as a 95% interval (1.96 sigma or bootstrap 2.5/97.5)."""
    rs = sorted([r for r in readings if r.status == "confident"], key=lambda r: r.ts)
    if len(rs) < 3:
        raise ValueError("need at least 3 confident recession readings")
    zero = Forcing(t_s=[0.0], intensity_mm_h=[0.0], source="recession")
    prior = SiteParams(R=0.0, k=0.01, h0=h0, source="prior")

    def _fit(sub: list[Reading]) -> float:
        # R is irrelevant with zero forcing; fit_params still fits R (stays ~0) and k.
        p = fit_params(sub, zero, basin, prior=prior, h0=h0, t0=rs[0].ts,
                       pump_rate_m3_s=pump_rate_m3_s, drain=drain)
        return p.k, p.k_sigma

    k, k_sig = _fit(rs)
    if n_bootstrap > 0:
        rng = np.random.default_rng(seed)
        ks = []
        for _ in range(n_bootstrap):
            idx = np.sort(rng.choice(len(rs), len(rs), replace=True))
            sub = [rs[i] for i in idx]
            # keep first/last to anchor the window
            sub[0], sub[-1] = rs[0], rs[-1]
            try:
                ks.append(_fit(sub)[0])
            except Exception:
                continue
        if len(ks) >= 10:
            lo, hi = np.percentile(ks, [2.5, 97.5])
            return float(k), (float(lo), float(hi))
    s = k_sig if k_sig is not None else 0.25 * k
    return float(k), (max(float(k - 1.96 * s), 0.0), float(k + 1.96 * s))


def score(k_latest: float, k_best: float) -> float:
    if k_best <= 0:
        return 100.0
    return float(100.0 * k_latest / k_best)


def assess(site_id: str, event_id: str, k: float, k_ci: tuple[float, float],
           history: list[DrainHealth], simulated: bool = False) -> DrainHealth:
    """Build the DrainHealth record for a new event given the site's history."""
    k_best = max([h.k for h in history] + [k])
    sc = score(k, k_best)
    prev_low = bool(history) and history[-1].score_pct < FLAG_BELOW_PCT
    flagged = sc < FLAG_BELOW_PCT and prev_low
    note = f"draining at {sc:.0f}% of its best observed rate"
    if flagged:
        note += "; flagged: below 60% on two consecutive events"
    return DrainHealth(site_id=site_id, event_id=event_id, ts=now_ts(), k=k, k_ci=k_ci,
                       score_pct=sc, flagged=flagged, note=note, simulated=simulated)


def compare_passes(k_open: tuple[float, tuple[float, float]], k_blocked: tuple[float, tuple[float, float]]) -> dict:
    """Staged-flood validation: pass C (blocked) vs pass B (open)."""
    kb, (kb_lo, kb_hi) = k_open
    kc, (kc_lo, kc_hi) = k_blocked
    return {
        "k_open": kb, "k_open_ci": [kb_lo, kb_hi],
        "k_blocked": kc, "k_blocked_ci": [kc_lo, kc_hi],
        "ratio": kc / kb if kb > 0 else None,
        "intervals_overlap": not (kc_hi < kb_lo or kb_hi < kc_lo),
        "score_pct_blocked": score(kc, kb),
    }
