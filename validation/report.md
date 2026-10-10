# Validation report (P1)

All numbers here come from the staged flood (architecture doc section 13) and are reported unedited.
Until the passes are filmed and processed, every cell reads "pending". Nothing in this file is estimated.

How each number is produced:

| Layer | Metric | Target | Script |
| --- | --- | --- | --- |
| Twin | Residual on tape-measured control marks | ≤ 2 cm per mark | `python -m twin.calibrate --twin-dir ... --marks-csv validation/data/control_marks.csv --marks-pixels ...` |
| Sense | MAE of max depth vs deep ruler, all 30 s samples (confident readings) | ≤ 3 cm (gate: ≤ 5 cm) | `python validation/measure_pass.py ...` then `python validation/sense_vs_ruler.py --pred validation/predictions.csv` |
| Sense | Share of readings with truth inside ±2σ | ≥ 80% | same |
| Predict | Time to target depth predicted from the first 40% of pass A | within 20% | `python validation/predict_vs_truth.py` (writes the table below) |
| Predict | Fitted inflow R (m³/h at i = 1000 mm/h) vs measured hose rate | within 25% | same, against `validation/data/hose_rate.csv` |
| Diagnose | k (pass C, blocked) ÷ k (pass B, open) | clearly < 1, intervals not overlapping | same |

## Results

| Layer | Metric | Target | Result |
| --- | --- | --- | --- |
| Twin | control-mark residual (rms / max) | ≤ 2 cm | pending |
| Sense | MAE vs ruler (n = ?) | ≤ 3 cm | pending |
| Sense | worst-case error | report | pending |
| Sense | ±2σ coverage | ≥ 80% | pending |
| Predict | time-to-target error, first 40% of pass A | ≤ 20% | pending |
| Predict | fitted inflow vs hose rate | ≤ 25% | pending |
| Diagnose | k_C / k_B with 95% intervals | < 1, non-overlapping | pending |

## Synthetic self-checks (not validation, only proof the maths is wired correctly)

These run in `tests/test_p1_*.py` on analytic cases and say nothing about real-world accuracy:

- paraboloid bowl: A(h) and V(h) within 5% of the closed form
- known-parameter ODE run: R recovered within 15%, k within 25%, from 0.5 cm noisy samples
- rise-only data: k correctly held at the prior, R still recovered
- first 40% of a synthetic fill: time to target within 20%
- blocked outlet (k × 0.4): ratio < 0.7 and non-overlapping intervals
- synthetic flooded bowl seen by an orthographic camera: level within 0.5 cm, max depth within 0.6 cm,
  level within 1 cm when a strip of the pool is occluded

## Limitations to carry into the README and video

- One small staged test in daylight, not a monsoon underpass.
- The model is a single basin with an orifice drain; street inflow, drain backflow and wind are ignored.
- Night, rain on the lens and murky moving water were not tested.
