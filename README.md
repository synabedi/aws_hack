# JalMaapi

Delhi watches 179 CCTV cameras at 45 waterlogging hotspots by eye. JalMaapi turns each camera into a
depth gauge (centimetres with an error bar), a forecast (minutes until each vehicle class cannot pass)
and a dispatch desk (an officer-approved, bilingual advisory), with no new hardware.

Built for Environmental Hacks (WeMakeDevs x AWS), Oct 8 to 11, 2026. Track: Heat and Water.

Status: P1 (geometry and physics), P2 (perception) and P4 (field protocol, dashboard, story) are built and tested;
P3 (API, agents, Cedar, AWS deployment) is in progress on `p3-agents-aws`. Validation numbers are pending the
staged flood (`validation/report.md`). See `docs/architecture.png`, `docs/writeup.md`, `docs/video_script.md`.

## Run the dashboard now (mock data from the physics model)

    cd web && python3 -m http.server 8080     # open http://localhost:8080/?mock=1

Every synthetic site is labelled SIM; the one real site shows "no reading yet" until the staged flood is processed.
API contract the dashboard expects: `web/API.md`. Field protocol and ground-truth templates: `validation/`.

## Layout

```
contracts/   shared pydantic schemas and unit conventions (read first)
twin/        dry twin: MapAnything runner, calibration, basin tables
sense/       water segmentation, waterline, level fit, depth map, abstain checks
predict/     site model ODE, fitting, forecast, simulate, drain health
act/         Strands agents, pump bidding, Cedar policies, advisories
api/         FastAPI app, local/DynamoDB store, local/S3 storage
sim/         synthetic sites and replay
web/         dashboard (static, served by the API)
validation/  staged flood protocol, ground truth CSVs, error report
infra/       AWS setup and deploy scripts
```

## Perception (P2): how a frame becomes a trusted number, and when it refuses to

1. **Mask.** SAM 2.1 (Apache 2.0) segments standing water, prompted once with a box from Claude on Bedrock
   (`sense/prompts/water_box.txt`), else a manual click; the prompt is propagated through the clip. People and
   vehicles are masked too so their edges never count as waterline. Without a GPU the same code runs OpenCV
   GrabCut from the same prompt (`sense/segment.py`, backend `auto`).
2. **Waterline.** Boundary pixels minus the image border, person/vehicle masks and low-confidence twin points;
   pixels on kerbs and walls are preferred because one pixel of error there barely moves the height
   (`sense/waterline.py`).
3. **Cross-check.** Claude on Bedrock reads a depth range from visible cues only (kerb, tyre, legs, the 1 m
   stick: `sense/prompts/depth_cues.txt`). It never replaces the geometry; it can only lower confidence.
4. **Abstain.** A reading becomes `low_confidence` if the cue range disagrees by more than 15 cm, if fewer than
   50 waterline points survive or sigma exceeds 5 cm, or if the level jumps more than 10 cm in 30 s with no rain
   (`sense/checks.py`). Low-confidence readings are shown to the officer but never fit the model or trigger a verdict.

Known failure modes we expect and have not solved: wet asphalt read as water, specular reflections, night,
raindrops on the lens, murky moving water. Segmentation, not geometry, sets the error floor.

Simulated sites (`sim/`) replay depth curves from the same site model with different parameters and rain
scenarios. Every simulated record carries `simulated: true` and the UI labels them.

## Licences and credits

Apache 2.0. Uses MapAnything (Apache checkpoint), SAM 2.1 (Apache 2.0), Strands Agents SDK (Apache 2.0),
Cedar (Apache 2.0). Full credits and the AI coding tools used are listed in `docs/writeup.md`.
