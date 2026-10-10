# Ground-truth data files (P4)

These are **templates with headers only**. Nothing here is measured yet; fill them on site. Never type a
number you did not measure. Raw videos go to S3 or Drive, not Git. Stills under 1 MB may be committed.

| File | Columns | Filled when |
| --- | --- | --- |
| `control_marks.csv` | `mark_id,height_cm` | before water, step 3 |
| `tape_grid.csv` | `x_m,y_m,height_cm` (x, y from a chalked origin; height above the lowest point) | before water, step 4 |
| `hose_rate.csv` | `trial,litres,seconds,l_min,mean_l_min` (mean repeated on each row) | before water, step 6 |
| `ruler_readings.csv` | `pass,t_s,ruler_deep_cm,ruler_mid_cm` every 30 s | during every pass |
| `chalk_times.csv` | `pass,mark_id,t_s` when the water reaches a mark | during every pass |
| `events.csv` | `pass,t_s,event` with `hose_on`, `hose_off`, `outlet_blocked`, `outlet_open`, `pump_on`, `pump_off` | during every pass |
| `marks_pixels.json` | `{"<mark_id>": [u, v]}` pixel position of each mark on the reference still | after step 7 |
| `stick_pixels.json` | `[[u, v], [u, v]]` stick ends on the reference still | after step 7 |

`t_s` is seconds since the start of that pass's recording.
