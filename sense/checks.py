"""Abstain logic (architecture doc 8.5): four rules decide whether a reading can be trusted.

| rule            | fires when                                                    | flag               |
| vision cue      | geometry outside the VLM range by more than 15 cm             | vlm_disagreement   |
| fit quality     | fewer than 50 waterline points, or sigma above 5 cm           | few_points / high_sigma |
| temporal sanity | more than 10 cm change in 30 s with no rain input             | temporal_jump      |
| (monocular depth check is optional and cut per the plan's cut order)                      |

A reading's status can only go down here (confident -> low_confidence); never up. Low-confidence
readings are excluded from model fitting and never produce an automatic verdict.
"""
from __future__ import annotations

from contracts.schemas import Reading

VLM_TOLERANCE_CM = 15.0
MIN_POINTS = 50
MAX_SIGMA_CM = 5.0
TEMPORAL_JUMP_CM = 10.0
TEMPORAL_WINDOW_S = 30.0


def vlm_disagrees(depth_cm: float, vlm_range_cm: tuple[float, float] | None, tol: float = VLM_TOLERANCE_CM) -> bool:
    if vlm_range_cm is None:
        return False
    lo, hi = vlm_range_cm
    return depth_cm < lo - tol or depth_cm > hi + tol


def apply_checks(
    reading: Reading,
    prev_reading: Reading | None = None,
    vlm_range_cm: tuple[float, float] | None = None,
    rain_mm_h: float | None = None,
) -> Reading:
    """Return a copy of ``reading`` with checks_failed, vlm_range_cm and status updated."""
    if reading.status == "failed":
        return reading
    flags = list(reading.checks_failed)
    if vlm_range_cm is not None:
        if vlm_disagrees(reading.max_depth_cm, vlm_range_cm):
            flags.append("vlm_disagreement")
    if (reading.n_waterline_points or 0) < MIN_POINTS:
        flags.append("few_points")
    if reading.sigma_cm > MAX_SIGMA_CM:
        flags.append("high_sigma")
    if prev_reading is not None and prev_reading.status != "failed":
        dt = abs(reading.ts - prev_reading.ts)
        jump = abs(reading.level_m - prev_reading.level_m) * 100.0
        if dt <= TEMPORAL_WINDOW_S and jump > TEMPORAL_JUMP_CM and not (rain_mm_h and rain_mm_h > 0):
            flags.append("temporal_jump")
    flags = list(dict.fromkeys(flags))  # dedupe, keep order
    status = "low_confidence" if flags else reading.status
    return reading.model_copy(update={"checks_failed": flags, "status": status,
                                      "vlm_range_cm": vlm_range_cm if vlm_range_cm is not None else reading.vlm_range_cm})


def verify_reading(reading: Reading, prev_reading: Reading | None = None, rain_mm_h: float | None = None,
                   context: str = "") -> Reading:
    """Run the Bedrock cue check on the reading's frame (if enabled) and apply all rules."""
    from sense.verify import depth_range_cm

    rng = depth_range_cm(reading.frame_uri, context) if reading.frame_uri and not reading.simulated else None
    return apply_checks(reading, prev_reading, rng, rain_mm_h)
