# Dashboard <-> API contract (what `web/app.js` calls; what P3's FastAPI must serve)

All bodies are the pydantic models in `contracts/schemas.py`, serialised with `model_dump()`. The dashboard
is served from the same origin as the API (FastAPI `StaticFiles` at `/`) or from Amplify with
`?api=https://<app-runner-url>`. When the API is unreachable, or with `?mock=1`, it loads `web/mock/*.json`
and shows a MOCK DATA banner.

| Method and path | Response | Mock file |
| --- | --- | --- |
| `GET /sites` | `SiteState[]` (site, latest_reading, latest_forecast, verdicts, drain_health, pending_actions) | `mock/sites.json` |
| `GET /sites/{id}/state` | `SiteState` | from `sites.json` |
| `GET /sites/{id}/history` | `{site_id, readings: Reading[]}` for the current event | `mock/history_{id}.json` |
| `GET /sites/{id}/forecast` | `Forecast` | from `sites.json` |
| `POST /sites/{id}/simulate` body `{pumps, minutes}` | `Forecast` | `mock/simulate_{id}.json[pumps]` |
| `GET /actions?status=proposed` | `Action[]` | `mock/actions.json` filtered |
| `POST /actions/{id}/approve` body `{officer_id}` | `Action` (status approved or published) | local state |
| `POST /actions/{id}/reject` body `{officer_id, reason?}` | `Action` | local state |
| `GET /allocations/latest` | `Allocation` | `mock/allocation.json` |
| `GET /feed` | `[{site_id, name, simulated, lat, lon, ts, max_depth_cm, sigma_cm, status, verdicts}]` | `mock/feed.json` |
| `GET /meta` (optional) | `{generated_ts, mock, aws?: {region, services[]}}` | `mock/meta.json` |

Rules the UI relies on: `simulated` is present on Site, Reading, Forecast, Action and DrainHealth;
`VerdictCard.passable` is `null` for low-confidence readings; `Forecast.t` is minutes and `depth/p10/p90` cm;
image URIs (`frame_uri`, `depthmap_uri`) are fetchable URLs or `null`.
