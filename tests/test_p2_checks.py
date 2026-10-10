from contracts.schemas import Reading
from sense.checks import apply_checks, vlm_disagrees


def r(**kw):
    base = dict(site_id="s", ts=100.0, level_m=0.2, max_depth_cm=20.0, sigma_cm=1.0, status="confident",
                frame_uri="f.jpg", n_waterline_points=200)
    base.update(kw)
    return Reading(**base)


def test_clean_reading_stays_confident():
    out = apply_checks(r(), vlm_range_cm=(10, 30))
    assert out.status == "confident" and out.checks_failed == [] and out.vlm_range_cm == (10, 30)


def test_vlm_disagreement_rule():
    assert vlm_disagrees(50, (10, 30)) and not vlm_disagrees(44, (10, 30)) and not vlm_disagrees(20, None)
    out = apply_checks(r(max_depth_cm=50), vlm_range_cm=(10, 30))
    assert out.status == "low_confidence" and "vlm_disagreement" in out.checks_failed


def test_fit_quality_rules():
    assert "few_points" in apply_checks(r(n_waterline_points=20)).checks_failed
    assert "high_sigma" in apply_checks(r(sigma_cm=6.0)).checks_failed
    assert apply_checks(r(n_waterline_points=None)).status == "low_confidence"


def test_temporal_rule_respects_rain():
    prev = r(ts=80.0, level_m=0.05)
    assert "temporal_jump" in apply_checks(r(), prev_reading=prev).checks_failed
    assert "temporal_jump" not in apply_checks(r(), prev_reading=prev, rain_mm_h=40).checks_failed
    assert "temporal_jump" not in apply_checks(r(ts=200.0), prev_reading=prev).checks_failed   # outside 30 s window


def test_never_upgrades_and_dedupes():
    low = r(status="low_confidence", checks_failed=["few_points"], n_waterline_points=10)
    out = apply_checks(low)
    assert out.status == "low_confidence" and out.checks_failed == ["few_points"]
    failed = r(status="failed")
    assert apply_checks(failed, vlm_range_cm=(0, 1)).status == "failed"
