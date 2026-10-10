"""Synthetic sites for the city view and the pump bidding (architecture doc 10.6).

Every site made here is labelled ``simulated=True`` in the Site, in every Reading and in
every Forecast; the UI and the video must show the label. The depth curves come from the
same site model as the real site (predict/site_model.py) with different R, k, basin
shape and rain, so the agents allocate pumps across sites that behave like the real one.

Public API (docs/CONVENTIONS.md):
  make_sites(n, seed=0) -> list[(Site, BasinTable, SiteParams, Forcing)]
  synthetic_readings(site, basin, params, forcing, dt_s=30, t0=None, noise_cm=0.5, seed=0) -> list[Reading]
"""
from __future__ import annotations

import numpy as np

from contracts.schemas import (
    BasinTable,
    Forcing,
    Reading,
    Site,
    SiteParams,
    Thresholds,
    now_ts,
)
from predict.site_model import integrate

# Delhi PWD hotspots named in the architecture doc (sections 2, 14.3). Coordinates approximate.
HOTSPOTS = [
    ("sim_minto", "Minto Bridge underpass", "मिंटो ब्रिज अंडरपास", 28.6318, 77.2235, "Divert via Barakhamba Road and Connaught Place outer circle", "बाराखंभा रोड और कनॉट प्लेस बाहरी सर्कल से होकर जाएँ"),
    ("sim_moolchand", "Moolchand underpass", "मूलचंद अंडरपास", 28.5660, 77.2340, "Divert via Lala Lajpat Rai Path and Ring Road", "लाला लाजपत राय पथ और रिंग रोड से होकर जाएँ"),
    ("sim_prahladpur", "Pul Prahladpur underpass", "पुल प्रह्लादपुर अंडरपास", 28.4999, 77.2898, "Divert via MB Road and Badarpur flyover", "एमबी रोड और बदरपुर फ्लाईओवर से होकर जाएँ"),
    ("sim_zakhira", "Zakhira underpass", "ज़खीरा अंडरपास", 28.6690, 77.1530, "Divert via Rohtak Road and Shastri Nagar", "रोहतक रोड और शास्त्री नगर से होकर जाएँ"),
    ("sim_igi_t3", "IGI T3 approach underpass", "आईजीआई टी3 अंडरपास", 28.5562, 77.0999, "Divert via NH48 service road and Dwarka link", "एनएच48 सर्विस रोड और द्वारका लिंक से होकर जाएँ"),
    ("sim_vasantkunj", "Airport to Vasant Kunj underpass", "वसंत कुंज अंडरपास", 28.5245, 77.1360, "Divert via Mehrauli-Mahipalpur Road", "महरौली-महिपालपुर रोड से होकर जाएँ"),
    ("sim_siraspur", "Siraspur underpass", "सिरसपुर अंडरपास", 28.7620, 77.1050, "Divert via GT Karnal Road", "जीटी करनाल रोड से होकर जाएँ"),
    ("sim_okhla", "Okhla underpass", "ओखला अंडरपास", 28.5380, 77.2860, "Divert via Mathura Road and Kalindi Kunj", "मथुरा रोड और कालिंदी कुंज से होकर जाएँ"),
]


def bowl_basin(a_coef: float, half_m: float = 15.0, max_h_m: float = 1.0) -> BasinTable:
    """Analytic paraboloid basin z = a (x^2 + y^2): A(h) = pi h / a, V(h) = pi h^2 / (2a), capped at the rim."""
    h = np.round(np.arange(0.0, max_h_m + 1e-9, 0.01), 4)
    rim_area = (2 * half_m) ** 2
    area = np.minimum(np.pi * h / a_coef, rim_area)
    # once the rim is reached the pool grows like a box
    vol = np.array([np.pi * hh**2 / (2 * a_coef) if aa < rim_area else
                    np.pi * (rim_area * a_coef / np.pi) ** 2 / (2 * a_coef) + rim_area * (hh - rim_area * a_coef / np.pi)
                    for hh, aa in zip(h, area)])
    return BasinTable(h_m=h.tolist(), area_m2=area.tolist(), volume_m3=vol.tolist())


def rain_scenario(kind: str, minutes: int = 120) -> Forcing:
    """Rain intensity scenarios in mm/h on a 60 s grid."""
    t = np.arange(0, minutes * 60 + 1, 60.0)
    m = t / 60.0
    if kind == "cloudburst":      # 30 min at 80 mm/h then tailing off
        i = np.where(m < 30, 80.0, np.where(m < 60, 25.0, 0.0))
    elif kind == "steady":        # 90 min at 35 mm/h
        i = np.where(m < 90, 35.0, 0.0)
    elif kind == "two_bursts":
        i = np.where(m < 20, 60.0, np.where(m < 50, 5.0, np.where(m < 75, 70.0, 0.0)))
    elif kind == "drizzle":
        i = np.where(m < 100, 8.0, 0.0)
    else:
        raise ValueError(kind)
    return Forcing(t_s=t.tolist(), intensity_mm_h=i.tolist(), source=f"scenario:{kind}")


def make_sites(n: int = 6, seed: int = 0) -> list[tuple[Site, BasinTable, SiteParams, Forcing]]:
    rng = np.random.default_rng(seed)
    n = max(1, min(n, len(HOTSPOTS)))
    kinds = ["cloudburst", "steady", "two_bursts", "drizzle"]
    out = []
    for i in range(n):
        sid, name, name_hi, lat, lon, div_en, div_hi = HOTSPOTS[i]
        a_coef = float(rng.uniform(0.002, 0.005))        # bowl steepness: ~30 m x 10 m pool at 30 cm
        basin = bowl_basin(a_coef)
        R = float(rng.uniform(1000, 5000))                # m^2 effective catchment of an underpass approach
        k = float(rng.uniform(0.02, 0.08))                # m^2.5/s drain coefficient (peaks 15-60 cm in a cloudburst)
        params = SiteParams(R=R, k=k, h0=0.0, R_sigma=0.15 * R, k_sigma=0.2 * k, source="synthetic")
        site = Site(site_id=sid, name=name, name_hi=name_hi, lat=lat, lon=lon, simulated=True,
                    thresholds=Thresholds(), params=params, traffic_weight=float(rng.uniform(0.6, 2.0)),
                    pump_rate_m3_s=0.02, diversion_en=div_en, diversion_hi=div_hi, rain_source="scenario")
        out.append((site, basin, params, rain_scenario(kinds[i % len(kinds)])))
    return out


def synthetic_readings(site: Site, basin: BasinTable, params: SiteParams, forcing: Forcing, dt_s: float = 30.0,
                       t0: float | None = None, noise_cm: float = 0.5, seed: int = 0,
                       duration_s: float | None = None) -> list[Reading]:
    """Depth curve from the site model, sampled every dt_s with Gaussian noise. All simulated."""
    rng = np.random.default_rng(seed)
    t0 = now_ts() if t0 is None else t0
    t_end = float(forcing.t_s[-1]) if duration_s is None else float(duration_s)
    t_eval = np.arange(0, t_end + 1e-9, dt_s)
    t, h = integrate(params, basin, forcing, 0.0, t_end, t_eval=t_eval, pump_rate_m3_s=site.pump_rate_m3_s)
    event_id = f"{site.site_id}_{int(t0)}"
    out = []
    for ti, hi in zip(t, h):
        lvl = max(float(hi + rng.normal(0, noise_cm / 100.0)), 0.0)
        out.append(Reading(site_id=site.site_id, ts=t0 + float(ti), level_m=lvl, max_depth_cm=lvl * 100.0,
                           sigma_cm=noise_cm, status="confident", frame_uri=f"synthetic://{site.site_id}/{int(ti)}",
                           source="synthetic", simulated=True, event_id=event_id))
    return out


def reading_at(site: Site, basin: BasinTable, params: SiteParams, forcing: Forcing, t_since_start_s: float,
               t0: float, noise_cm: float = 0.5) -> Reading:
    """One reading at a given offset into the scenario (used by the replay Lambda)."""
    rng = np.random.default_rng(int(t_since_start_s))
    _, h = integrate(params, basin, forcing, 0.0, max(t_since_start_s, 1.0), t_eval=np.array([max(t_since_start_s, 1.0)]),
                     pump_rate_m3_s=site.pump_rate_m3_s)
    lvl = max(float(h[-1] + rng.normal(0, noise_cm / 100.0)), 0.0)
    return Reading(site_id=site.site_id, ts=t0 + t_since_start_s, level_m=lvl, max_depth_cm=lvl * 100.0,
                   sigma_cm=noise_cm, status="confident", frame_uri=f"synthetic://{site.site_id}/{int(t_since_start_s)}",
                   source="synthetic", simulated=True, event_id=f"{site.site_id}_{int(t0)}")
