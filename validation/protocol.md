# Staged flood protocol (P4 field) — Saturday 10 Oct 2026

October has no monsoon. One afternoon flooding a campus dip with a hose is the only ground truth this
project will have. It validates Sense, Predict and Diagnose at once. Film in daylight: Delhi sunset is
about 17:50 in mid-October, so finish passes A and B by 17:15; pass C may move to Sunday morning.

## Site

A paved dip, ramp foot or kerb-bounded corner on campus that holds water and has one identifiable drain
point or outflow edge. Target 15 to 25 cm at the deepest point. Get permission from the estate office first
and tell security what you are doing. Keep people and vehicles out of frame during the passes.

## Kit

| Item | Why |
| --- | --- |
| 2 phones, 1 tripod | Fixed camera (stands in for CCTV) and the walk-through camera |
| Hose, or buckets | Inflow. A hose gives a steady, measurable rate |
| Measuring bucket (known litres) and stopwatch | Hose rate = litres / seconds, three times |
| 1 m stick | Scale check for the twin |
| 2 rulers or marked stakes | Ground truth at the deepest point and a mid-depth point, readable from the tripod |
| Tape measure, chalk | Control marks and the hand-surveyed height grid |
| Cloth or brick | Partly block the outlet for pass C |
| A few bricks or stakes | Extra vertical edges in the basin so the waterline has steep surfaces to sit on |

## Before any water (about 40 minutes)

1. Fix the tripod and take the reference still (`validation/frames/ref.jpg`). Do not move it again until all passes are done.
2. Lay the 1 m stick flat in view. Stand the two rulers upright at the deepest point and at a mid-depth point, zero at the ground, readable from the tripod.
3. Chalk five or more numbered control marks at different heights around the basin (on kerbs, walls, stakes). Tape-measure each one's height above the lowest point of the basin. Record in `validation/data/control_marks.csv`.
4. Tape-measure a coarse height grid across the basin (every 0.5 m, more where it curves). Record in `validation/data/tape_grid.csv`. This is the twin's ground truth and the fallback heightmap.
5. Walk the site with the second phone for 30 to 60 seconds, slowly, covering ground, kerbs and walls, with plenty of overlap. Save as `walkthrough.mp4` (goes to S3 or Drive, never Git).
6. Time the hose filling the measuring bucket three times. Record in `validation/data/hose_rate.csv`.
7. Note the pixel position of each chalk mark and of the stick ends on the reference still (`validation/data/marks_pixels.json`, `stick_pixels.json`) for `twin/calibrate.py`.

## Three passes

| Pass | Steps | Validates |
| --- | --- | --- |
| A. Slow fill | Hose on at the measured rate, outlet open, until the deep ruler reads the target. Record continuously. | Sense accuracy; Predict (fit R, forecast time to threshold) |
| B. Drain-down, outlet open | Hose off. Record until nearly empty. | Predict and Diagnose (fit k) |
| C. Drain-down, outlet partly blocked | Refill to the same level, partly block the outlet, hose off, record. | Diagnose (k must drop) |

During every pass a second person reads both rulers aloud on camera every 30 seconds and notes when each
chalk mark is reached. Record in `validation/data/ruler_readings.csv` and `chalk_times.csv`. Also log every
hose on/off time (`events.csv`) so pumping and inflow are never confused with drainage in the fit.

## After filming

1. Sample each pass at 30 s into `validation/frames/<pass>/` (`ffmpeg -i passA.mp4 -vf fps=1/30 validation/frames/A/%03d.jpg`) with a `times.csv`.
2. Masks: `python -m sense.export_masks --frames validation/frames/A --out validation/masks/A --video --box ...`
3. Twin: `twin/run_mapanything.py` on the GPU box, then `twin/calibrate.py`, then `twin/basin.py` (or the tape-grid fallback).
4. Depth: `python validation/measure_pass.py --site-id dtu_staged --pass-name A ...` for A, B, C.
5. Gate (by 21:00): `python validation/sense_vs_ruler.py --pred validation/predictions.csv`.
6. Predict and Diagnose: `python validation/predict_vs_truth.py --pred validation/predictions.csv --twin-dir ...`.
7. Paste the numbers, unedited, into `validation/report.md`.
