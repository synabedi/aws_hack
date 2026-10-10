"""Shared data contracts for JalMaapi.

Every layer (twin, sense, predict, act, api, sim, web) imports from here and
nothing else crosses layer boundaries. Change only by agreement.

UNITS AND CONVENTIONS (read before touching any layer)
------------------------------------------------------
* Datum: per site, z = 0 is the LOWEST ground point of the dry twin's heightmap
  (the basin floor). ``level_m`` is the water-surface height above that datum.
  ``max_depth_cm = (level_m - 0) * 100`` when water covers the lowest cell.
* Time: ``ts`` is Unix seconds (UTC) as float. ``t`` inside Forecast is MINUTES
  from the forecast issue time ``ts``.
* Rain / inflow forcing: ``Forcing.intensity_mm_h`` is rainfall intensity i(t) in
  mm/h on a time grid ``t_s`` (seconds since event start). The site model uses
  inflow Q_in [m^3/s] = R [m^2] * i [mm/h] / 3.6e6 (mm->m is /1000, h->s is /3600).
  For the staged hose test set i(t) = 1000 mm/h (= 1 m/h) constant, so the fitted
  R [m^2] equals the hose rate in m^3/h (e.g. 33 L/min = 2.0 m^3/h -> R = 2.0).
  State this in reports.
* Pumps: ``Site.pump_rate_m3_s`` is the discharge of ONE mobile pump. Q_pump =
  pumps * pump_rate_m3_s while a pump is running.
* Thresholds are centimetres of MAX depth. Keys of ``Thresholds`` are the
  vehicle classes used everywhere (t_impassable_min, verdict cards, advisories).
* Basin table: rows of (h_m, area_m2, volume_m3) in 1 cm steps from h=0 upward,
  area and volume monotonic non-decreasing. Stored as ``basin.csv`` with header
  ``h_m,area_m2,volume_m3``.
* Simulated sites carry ``simulated=True`` in every record and every API payload.
"""
from __future__ import annotations

import time
import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator

ReadingStatus = Literal["confident", "low_confidence", "failed"]
ActionStatus = Literal["proposed", "approved", "rejected", "published"]
ActionType = Literal["advisory", "closure", "reopen", "pump_move"]
VehicleClass = Literal[
    "closure", "pedestrian", "two_wheeler", "small_car", "large_car", "bus_truck"
]
VEHICLE_CLASSES: tuple[str, ...] = (
    "closure", "pedestrian", "two_wheeler", "small_car", "large_car", "bus_truck"
)


def now_ts() -> float:
    return time.time()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# --------------------------------------------------------------------------- sites
class Thresholds(BaseModel):
    """No-pass max-depth thresholds in cm. Defaults follow Architecture doc 9.3.
    ``closure`` is Delhi PWD's operational 6-inch rule. two_wheeler and bus_truck
    are assumptions and must be labelled as such in UI/video."""

    closure: float = 15.0
    pedestrian: float = 15.0
    two_wheeler: float = 15.0
    small_car: float = 30.0
    large_car: float = 40.0
    bus_truck: float = 50.0

    def as_dict(self) -> dict[str, float]:
        return {k: float(getattr(self, k)) for k in VEHICLE_CLASSES}


class SiteParams(BaseModel):
    """Fitted site-model parameters. R in m^2 (effective contributing area),
    k in m^2.5/s (orifice coefficient: Q_out = k*sqrt(h-h0)), h0 in m above datum."""

    R: float = Field(ge=0)
    k: float = Field(ge=0)
    h0: float = 0.0
    R_sigma: float | None = None
    k_sigma: float | None = None
    fitted_at: float | None = None
    source: Literal["fitted", "prior", "synthetic"] = "prior"


class Site(BaseModel):
    site_id: str
    name: str
    name_hi: str | None = None
    lat: float
    lon: float
    simulated: bool = False
    twin_uri: str | None = None          # s3://... or local path to twin folder
    basin_table_uri: str | None = None   # .../basin.csv
    up_vector: list[float] | None = None
    transform: list[list[float]] | None = None  # 4x4 similarity, twin -> metric
    thresholds: Thresholds = Field(default_factory=Thresholds)
    params: SiteParams | None = None
    traffic_weight: float = 1.0
    pump_rate_m3_s: float = 0.02
    officer_contact: str | None = None
    diversion_en: str | None = None
    diversion_hi: str | None = None
    rain_source: str = "scenario"        # open-meteo | scenario | hose


# -------------------------------------------------------------------------- readings
class Reading(BaseModel):
    site_id: str
    ts: float
    level_m: float
    max_depth_cm: float
    sigma_cm: float
    status: ReadingStatus
    frame_uri: str
    mask_uri: str | None = None
    depthmap_uri: str | None = None
    vlm_range_cm: tuple[float, float] | None = None
    n_waterline_points: int | None = None
    source: Literal["camera", "synthetic", "replay"] = "camera"
    simulated: bool = False
    checks_failed: list[str] = Field(default_factory=list)
    event_id: str | None = None
    pumps_on: int = 0


# -------------------------------------------------------------------------- forcing
class Forcing(BaseModel):
    """Rain or hose intensity on a time grid. t_s in seconds since event start."""

    t_s: list[float]
    intensity_mm_h: list[float]
    source: str = "scenario"

    @field_validator("intensity_mm_h")
    @classmethod
    def _same_len(cls, v, info):
        t = info.data.get("t_s")
        if t is not None and len(t) != len(v):
            raise ValueError("t_s and intensity_mm_h must have the same length")
        return v


class BasinTable(BaseModel):
    h_m: list[float]
    area_m2: list[float]
    volume_m3: list[float]

    @classmethod
    def from_csv(cls, path: str) -> "BasinTable":
        import csv

        h, a, v = [], [], []
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                h.append(float(row["h_m"]))
                a.append(float(row["area_m2"]))
                v.append(float(row["volume_m3"]))
        return cls(h_m=h, area_m2=a, volume_m3=v)

    def to_csv(self, path: str) -> None:
        import csv

        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["h_m", "area_m2", "volume_m3"])
            for row in zip(self.h_m, self.area_m2, self.volume_m3):
                w.writerow([f"{row[0]:.4f}", f"{row[1]:.4f}", f"{row[2]:.5f}"])


# -------------------------------------------------------------------------- forecast
class Forecast(BaseModel):
    site_id: str
    ts: float
    t: list[float]            # minutes from ts
    depth: list[float]        # median max-depth cm
    p10: list[float]
    p90: list[float]
    t_impassable_min: dict[str, float | None]        # class -> median minutes, None = not within horizon
    t_impassable_p10: dict[str, float | None] = Field(default_factory=dict)
    t_impassable_p90: dict[str, float | None] = Field(default_factory=dict)
    params: dict[str, float]  # R, k, h0 used
    rain_source: str = "scenario"
    pumps: int = 0
    confidence: Literal["confident", "low_confidence"] = "confident"
    simulated: bool = False
    note: str | None = None


# -------------------------------------------------------------------------- actions
class Action(BaseModel):
    action_id: str = Field(default_factory=lambda: new_id("act"))
    site_id: str
    type: ActionType
    status: ActionStatus = "proposed"
    proposed_by: str                     # agent name
    justification: str
    created_ts: float = Field(default_factory=now_ts)
    approved_by: str | None = None
    decided_at: float | None = None
    published_at: float | None = None
    payload: dict = Field(default_factory=dict)   # advisory_en, advisory_hi, pumps, reading_ts ...
    simulated: bool = False
    reading_status: ReadingStatus = "confident"


# ----------------------------------------------------------------------- allocations
class Bid(BaseModel):
    site_id: str
    pumps: int                       # marginal pump number (1, 2, 3)
    marginal_benefit: float          # minutes above closure threshold avoided * traffic_weight
    minutes_avoided: float
    simulated: bool = False


class Allocation(BaseModel):
    round_id: str = Field(default_factory=lambda: new_id("round"))
    ts: float = Field(default_factory=now_ts)
    inventory: dict[str, int]        # {"pumps": n, "crews": m}
    bids: list[Bid]
    awards: dict[str, int]           # site_id -> pumps awarded (forecast-based)
    baseline_awards: dict[str, int]  # site_id -> pumps (nearest pump to worst current depth)
    justification: str
    benefit_minutes: float = 0.0
    baseline_benefit_minutes: float = 0.0


class DrainHealth(BaseModel):
    site_id: str
    event_id: str
    ts: float = Field(default_factory=now_ts)
    k: float
    k_ci: tuple[float, float]
    score_pct: float
    flagged: bool = False
    note: str | None = None
    simulated: bool = False


# -------------------------------------------------------------------- api responses
class VerdictCard(BaseModel):
    vehicle_class: str
    threshold_cm: float
    current_depth_cm: float
    passable: bool | None            # None when reading is low confidence
    t_impassable_min: float | None
    assumed: bool = False            # threshold is an assumption, not a standard


class SiteState(BaseModel):
    site: Site
    latest_reading: Reading | None
    latest_forecast: Forecast | None
    verdicts: list[VerdictCard]
    drain_health: DrainHealth | None
    pending_actions: list[Action]
