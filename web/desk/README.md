# JalMaapi desk (`web/desk/`)

A second dashboard that sits next to the static one in `web/`. Same API contract (`web/API.md`,
`contracts/schemas.py`); nothing in `web/` is changed or removed.

What it adds:

- **Intervention Clock**: time left to decide, not time until the water arrives. Earliest plausible
  crossing of the closure rule (10th percentile of crossing time) minus set-up time and a safety buffer.
  The 8 min and 3 min values are assumptions and are labelled as such on screen.
- **FloodLab**: rainfall, drain performance, pump count and pump arrival delay, run through the same
  site equation as `predict/site_model.py`. Checked against the forecast median: within 0.7 cm on all six demo sites.
- **Evidence** for any reading: frame, mask, depth map, waterline points, cue range, checks that fired.
- Pump plan against the baseline, drain health, approvals with the Hindi and English advisory.

## Run

    cd web/desk
    npm install
    npm run dev            # http://localhost:5173/?mock=1 for the demo snapshot

Against the API: `?api=https://<app-runner-url>` or `VITE_API_BASE` at build time. If the API cannot be
reached it falls back to the demo snapshot and says so in the header.

## Build and host

`npm run build` writes a static site to `web/desk/dist` (relative paths, so it works under any prefix).
Amplify: app root `web/desk`, build command `npm run build`, output `dist`.

## Demo snapshot

`public/mock/` is generated from the real physics model by reusing `web/make_mock_data.py` unchanged:

    PYTHONPATH=. python3 web/desk/make_demo_data.py --minutes-in 2

It also writes `lab_<site_id>.json` (basin area table, rain for the next hour, fitted parameters, pump rate),
which is what FloodLab needs.

## One optional endpoint for P3

`GET /sites/{id}/lab` returning the same shape as `public/mock/lab_<site_id>.json`. Without it FloodLab
still works in live mode, but only for the pump count (via `POST /sites/{id}/simulate`).

## Known gap

In the synthetic sites, water reaches 15 cm within 3 to 5 minutes of rain starting, which is less than the
11 minutes a closure is assumed to need. So the clock reads "Close now" at every rising simulated site and
never shows a live countdown in the demo snapshot. That is the data, not a display bug.
