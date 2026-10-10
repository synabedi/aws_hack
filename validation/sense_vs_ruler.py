"""The 9 PM gate: Sense max depth vs the ruler, per 30 s sample.

predictions CSV: pass,t_s,max_depth_cm,sigma_cm,status   (from validation/measure_pass.py)
truth CSV:       pass,t_s,ruler_deep_cm,ruler_mid_cm       (validation/data/ruler_readings.csv)

Joins each prediction to the nearest truth sample in the same pass within ``tol_s``.
Reports MAE, worst case, bias, and the share of samples with |truth - pred| <= 2 sigma.
Numbers are printed and written as markdown, unedited.
"""
from __future__ import annotations

import argparse
import csv

import numpy as np

GATE_MAE_CM = 5.0        # go / no-go (doc 13.5)
TARGET_MAE_CM = 3.0      # stated goal (doc 13.4)
TARGET_COVERAGE = 0.80


def read_csv(path: str) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def join(pred: list[dict], truth: list[dict], tol_s: float = 5.0) -> list[dict]:
    out = []
    by_pass: dict[str, list[dict]] = {}
    for r in truth:
        by_pass.setdefault(r["pass"].strip(), []).append(r)
    for p in pred:
        cands = by_pass.get(p["pass"].strip(), [])
        if not cands:
            continue
        t = float(p["t_s"])
        best = min(cands, key=lambda r: abs(float(r["t_s"]) - t))
        if abs(float(best["t_s"]) - t) > tol_s:
            continue
        out.append({"pass": p["pass"].strip(), "t_s": t, "pred_cm": float(p["max_depth_cm"]),
                    "sigma_cm": float(p["sigma_cm"]), "status": p.get("status", "confident"),
                    "truth_cm": float(best["ruler_deep_cm"])})
    return out


def metrics(rows: list[dict], confident_only: bool = True) -> dict:
    rs = [r for r in rows if (r["status"] == "confident" or not confident_only)]
    if not rs:
        return {"n": 0}
    err = np.array([r["pred_cm"] - r["truth_cm"] for r in rs])
    sig = np.array([r["sigma_cm"] for r in rs])
    cov = np.mean(np.abs(err) <= 2.0 * sig)
    return {
        "n": len(rs), "mae_cm": float(np.mean(np.abs(err))), "bias_cm": float(np.mean(err)),
        "rmse_cm": float(np.sqrt(np.mean(err**2))), "worst_cm": float(np.max(np.abs(err))),
        "coverage_2sigma": float(cov),
        "gate_pass": bool(np.mean(np.abs(err)) <= GATE_MAE_CM),
        "target_pass": bool(np.mean(np.abs(err)) <= TARGET_MAE_CM and cov >= TARGET_COVERAGE),
    }


def to_markdown(rows: list[dict], overall: dict, per_pass: dict[str, dict]) -> str:
    lines = ["# Sense vs ruler", "", "Max depth from the camera vs the deep ruler, every 30 s sample, confident readings only.", ""]
    lines += ["| Scope | n | MAE cm | bias cm | RMSE cm | worst cm | within ±2σ | gate (≤5 cm) | target (≤3 cm, ≥80%) |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]

    def row(name, m):
        if m.get("n", 0) == 0:
            return f"| {name} | 0 | – | – | – | – | – | – | – |"
        return (f"| {name} | {m['n']} | {m['mae_cm']:.2f} | {m['bias_cm']:+.2f} | {m['rmse_cm']:.2f} | "
                f"{m['worst_cm']:.2f} | {100*m['coverage_2sigma']:.0f}% | {'PASS' if m['gate_pass'] else 'FAIL'} | "
                f"{'PASS' if m['target_pass'] else 'FAIL'} |")

    lines.append(row("all passes", overall))
    for k, m in per_pass.items():
        lines.append(row(f"pass {k}", m))
    lines += ["", "| pass | t_s | ruler cm | sense cm | σ cm | error cm | status |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        lines.append(f"| {r['pass']} | {r['t_s']:.0f} | {r['truth_cm']:.1f} | {r['pred_cm']:.1f} | {r['sigma_cm']:.1f} | "
                     f"{r['pred_cm']-r['truth_cm']:+.1f} | {r['status']} |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True)
    ap.add_argument("--truth", default="validation/data/ruler_readings.csv")
    ap.add_argument("--out", default="validation/sense_vs_ruler.md")
    ap.add_argument("--tol-s", type=float, default=5.0)
    a = ap.parse_args()
    rows = join(read_csv(a.pred), read_csv(a.truth), a.tol_s)
    overall = metrics(rows)
    per_pass = {p: metrics([r for r in rows if r["pass"] == p]) for p in sorted({r["pass"] for r in rows})}
    md = to_markdown(rows, overall, per_pass)
    with open(a.out, "w") as f:
        f.write(md)
    print(md)
    if overall.get("n", 0) == 0:
        print("NO MATCHED SAMPLES")
    else:
        print(f"GATE: {'GO' if overall['gate_pass'] else 'NO-GO -> fallback Sense (doc 13.5)'}")


if __name__ == "__main__":
    main()
