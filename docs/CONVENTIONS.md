# JalMaapi build conventions (shared by P1 to P4)

Read `contracts/schemas.py` first; its docstring fixes units, datum, time, rain forcing and thresholds.
Read `/Users/synabedi/Downloads/JalMaapi Complete Idea, Impact and Architecture.md` sections for your layer.

## Rules for every owner
1. Edit ONLY the folders you own (see the work-split doc). Do not touch `contracts/`, `pyproject.toml`, or another owner's folder.
   If you need a contract change or a new dependency, say so in your final report; do not make it.
2. Everything must run WITHOUT AWS credentials, a GPU, or network: use local fallbacks
   (local JSON store, template advisories, synthetic twin). AWS paths switch on via env vars in `.env.example`.
3. Python 3.12, venv at `.venv` (use `.venv/bin/python`, `.venv/bin/pytest`). Project root on `sys.path`
   (pytest `pythonpath = ["."]`). Import across layers only via `from contracts.schemas import ...`
   and the public functions named in this brief.
4. Write tests under `tests/test_<yourlayer>_*.py` only. All your tests must pass with
   `.venv/bin/pytest tests/test_<yourlayer>_*.py -q` before you report.
5. No model weights, videos, point clouds or secrets in the repo. Keep prompts in `*/prompts/*.txt`.
6. Every record for a simulated site carries `simulated=True`. Low-confidence readings never produce
   an automatic "passable" verdict or an auto-published closure.
7. Label assumed thresholds (two_wheeler, bus_truck) as assumptions wherever they are shown.
8. Keep it honest: no fake accuracy numbers anywhere. Validation numbers come from `validation/` only.
9. Finish with a report: files written, public functions and their signatures, how you tested, what is
   stubbed or missing, and any contract/dependency change you need.

## Public cross-layer functions (signatures are fixed)
- `sense.segment.segment_water(frame_path: str, prompt_box=None, prompt_points=None) -> np.ndarray[bool] (H,W)`
- `sense.level.measure(site_id: str, frame_path: str, mask: np.ndarray, twin_dir: str, prev_reading: Reading|None=None) -> Reading`
- `twin.basin.load_basin(twin_dir: str) -> BasinTable` and `twin.basin.build_basin_from_heightmap(heightmap_m: np.ndarray, cell_m: float) -> BasinTable`
- `predict.forecast.fit_and_forecast(readings, forcing, basin, thresholds, pumps=0, horizon_min=60, prior=None) -> Forecast`
- `predict.simulate.simulate(readings, forcing, basin, thresholds, params: SiteParams, pumps: int, minutes: int) -> Forecast`
- `predict.site_model.integrate(params, basin, forcing, h_init, t_end_s, pumps=0, pump_rate_m3_s=0.02) -> (t_s, h_m)`
- `predict.fit.fit_params(readings, forcing, basin, prior=None, fix_k=None) -> SiteParams`
- `predict.drain_health.fit_k_from_recession(readings, basin) -> (k, (k_lo, k_hi))` and `score(k_latest, k_best) -> float`
- `sim.generate.make_sites(n: int, seed=0) -> list[tuple[Site, BasinTable, SiteParams, Forcing]]` and `sim.generate.synthetic_readings(site, basin, params, forcing, dt_s=30) -> list[Reading]`
- `act.authorize.authorize(action: Action, context: dict) -> Decision(allowed: bool, reason: str, policy_id: str|None)`
- `act.advisory.draft_advisory(site: Site, reading: Reading, forecast: Forecast|None, action_type: str) -> dict with keys en, hi`
- `act.bidding.run_round(sites_with_forecasts: list[tuple[Site, Forecast, callable simulate_fn]], inventory: dict) -> Allocation`
- `api.store.get_store() -> Store` with methods: put_site/get_site/list_sites, put_reading/list_readings(site_id, since_ts=None),
  put_forecast/get_latest_forecast, put_action/get_action/list_actions(status=None)/update_action, put_allocation/get_latest_allocation,
  put_drain_health/get_latest_drain_health. Backends: LocalJSONStore (data/local) and DynamoStore.
- `api.storage.get_storage() -> Storage` with put_file(local_path, key) -> uri, get_file(uri, local_path), url_for(uri). Backends: LocalStorage, S3Storage.

## Default thresholds (cm): closure 15, pedestrian 15, two_wheeler 15 (assumed), small_car 30, large_car 40, bus_truck 50 (assumed)
## Triggers: median t_impassable(closure) < 20 min -> propose closure + request pumps; depth above class threshold -> no-pass verdict now;
## level falling and below all thresholds for 10 min -> propose reopen; low_confidence -> manual review, no automatic verdict.
