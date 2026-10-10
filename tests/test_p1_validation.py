from validation.sense_vs_ruler import join, metrics, to_markdown


def test_join_and_metrics():
    truth = [{"pass": "A", "t_s": str(t), "ruler_deep_cm": str(10 + t / 30), "ruler_mid_cm": "0"} for t in range(0, 300, 30)]
    pred = [{"pass": "A", "t_s": str(t + 1), "max_depth_cm": str(10 + t / 30 + (1 if t == 60 else 0)),
             "sigma_cm": "1.0", "status": "confident"} for t in range(0, 300, 30)]
    pred.append({"pass": "A", "t_s": "999", "max_depth_cm": "0", "sigma_cm": "1", "status": "confident"})  # unmatched
    rows = join(pred, truth, tol_s=5)
    assert len(rows) == 10
    m = metrics(rows)
    assert m["n"] == 10 and m["mae_cm"] == 0.1 and m["worst_cm"] == 1.0 and m["coverage_2sigma"] == 1.0
    assert m["gate_pass"] and m["target_pass"]
    md = to_markdown(rows, m, {"A": m})
    assert "PASS" in md and "| A |" in md
