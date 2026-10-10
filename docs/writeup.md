# JalMaapi — submission writeup (draft; numbers pending the staged flood)

**Track:** Heat and Water · **Team:** up to 4 DTU students · **Repo:** https://github.com/synabedi/aws_hack · **Video:** see `docs/video_link.md`

## The problem in Delhi

Delhi mapped 448 waterlogging hotspots for 2026. PWD's monsoon control room watches 179 CCTV cameras at 45 of them,
24x7, and the Flood Control Order 2026 makes a named nodal officer accountable for each point. Yet the decision to
stop traffic still rests on field staff judging depth by eye at roughly six to eight inches and phoning it in; the
Minto Bridge SOP diverts at 6 inches. People died in underpasses at Siraspur, Okhla and Shalimar Bagh in 2024. The
cameras, officers, pumps and the 15 cm rule all exist. Missing: a number in centimetres, a countdown, and a record.

## Why existing approaches miss it

Physical gauges and LiDAR work but cost Rs 2.3 to 3.5 lakh per point at Mumbai prices and need upkeep at every spot.
Gauge-reading cameras need a surveyed board in view. Reference-object methods (Seoul, most papers) need a car or
person in frame and fail once it is submerged. Area forecasts give a probability for a neighbourhood, not centimetres
at one underpass now. Satellites cannot see under a flyover. Humans cannot watch 179 feeds in a cloudburst.

## What we built

**Sense.** A dry-day phone walk-through becomes a metric 3D "dry twin" (MapAnything, Apache checkpoint), calibrated to
tape-measured chalk marks. In a flood frame SAM 2.1 masks the water; the mask boundary looked up in the twin gives
the water level (90th–95th percentile of waterline heights, sigma from MAD and bootstrap), and depth everywhere below
it, including the hidden deepest point. Claude on Amazon Bedrock reads an independent depth range from visible cues;
disagreement, too few points, a large sigma or a physically impossible jump marks the reading low-confidence, and
low-confidence readings never produce a verdict.

**Predict.** A(h) dh/dt = R i(t) − k √(h−h0) − Q_pump, with A(h) from the twin, fitted by weighted least squares to the
depth curve. 100 parameter samples give a band; per vehicle class we report minutes to impassable (15 cm closure rule,
30/40/50 cm from ARR/WRL vehicle-stability tests; two-wheeler and bus values are labelled assumptions).

**Act.** Strands Agents on Bedrock: a site agent per hotspot, a coordinator that runs a contract-net pump round (the
arithmetic is deterministic Python, shown beside a "nearest pump to the worst depth" baseline), a dispatcher. Cedar
policies in the repo: informational advisories publish automatically; closures and reopenings are forbidden unless
`officer_approved`; nothing acts on a low-confidence reading. The officer approves on the dashboard; decision, id and
time are logged; a Hindi and English advisory publishes.

**Diagnose.** The fitted drain coefficient k per event gives a drain-health score (latest k ÷ best k). In the staged
test we block the outlet and k must drop.

## What fought back

Wet asphalt reads as water; the box prompt and the "waterline pixels on steep surfaces only" rule exist for that.
Images-only metric scale is off by up to about 13%, so chalk-mark calibration is mandatory. The up vector is not
given by the reconstruction; water being level gives it to us. Pumps that switch off at the floor make the ODE chatter;
we ramp them over the bottom centimetre. (Add what the field day taught us.)

## Validation (staged flood, DTU campus, 10 Oct 2026)

See `validation/report.md`. Targets: twin residual ≤ 2 cm; Sense MAE ≤ 3 cm vs ruler with ±2σ coverage ≥ 80%;
time-to-target from the first 40% of the fill within 20%; fitted inflow within 25% of the measured hose rate;
k blocked ÷ k open clearly below 1 with non-overlapping intervals. **Results: pending.** Whatever they are, they go
in the video unedited.

## Where AWS fits

App Runner hosts the FastAPI service with the agents, the physics model and the Cedar checks. Amazon Bedrock runs
Claude for the verifier, justifications and advisories. S3 holds frames, masks, depth maps, twins and basin tables;
DynamoDB holds sites, readings, forecasts, actions, allocations and drain health. SNS notifies the officer.
EventBridge Scheduler and Lambda replay the simulated sites every 30 s. Amplify hosts the dashboard; CloudWatch
holds logs. Two AWS open-source tools: Strands Agents SDK and Cedar. (GPU work: EC2 g5 if quota is granted, else a
local GPU with results uploaded to S3.)

## Limitations

One small staged test in daylight, not a monsoon underpass. Each site needs a fixed camera and a dry-day survey.
Night, rain on the lens, floating debris and murky moving water were not tested. Single-basin model. All sites except
one are simulated and labelled. No integration with real PWD feeds. That Delhi agencies judge depth by eye is inferred
from documented protocols, not confirmed.

## Open source and AI tools used

MapAnything (Apache 2.0 checkpoint), SAM 2.1 (Apache 2.0), Strands Agents SDK (Apache 2.0), Cedar (Apache 2.0),
Chart.js, Leaflet, OpenStreetMap and CARTO tiles. Public flood photos for the qualitative segmentation check are
CC BY-SA, attributed in `docs/public_flood_photos.md`. AI coding tools: Claude Code (Claude Fable 5.1) for code,
tests and documentation; ChatGPT/Claude for research notes. Sources for every Delhi fact are in the architecture doc.
