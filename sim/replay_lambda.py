"""AWS Lambda handler: emit one synthetic reading per simulated site every 30 s.

Wire it to an EventBridge Scheduler rule (rate(1 minute) with two invocations, or a 30 s
schedule expression). Each invocation computes where every scenario is at ``now - scenario_start``
and writes a Reading row to DynamoDB (table ``${JALMAAPI_TABLE_PREFIX}_readings``) or, when
JALMAAPI_API_URL is set, POSTs it to the API so the same ingest path runs. The scenario loops every
``SCENARIO_LOOP_MIN`` minutes so the demo never runs dry.

Local dry run:  python -m sim.replay_lambda
"""
from __future__ import annotations

import json
import os
import time
from decimal import Decimal

from sim.generate import make_sites, reading_at

LOOP_MIN = int(os.environ.get("SCENARIO_LOOP_MIN", "150"))
N_SITES = int(os.environ.get("JALMAAPI_SIM_SITES", "6"))
TABLE_PREFIX = os.environ.get("JALMAAPI_TABLE_PREFIX", "jalmaapi")


def _scenario_offset_s(now: float) -> tuple[float, float]:
    loop = LOOP_MIN * 60
    t0 = (int(now) // loop) * loop
    return now - t0, float(t0)


def current_readings(now: float | None = None) -> list[dict]:
    now = time.time() if now is None else now
    off, t0 = _scenario_offset_s(now)
    out = []
    for site, basin, params, forcing in make_sites(N_SITES):
        r = reading_at(site, basin, params, forcing, off, t0)
        out.append(r.model_dump())
    return out


def _to_dynamo(item: dict) -> dict:
    return json.loads(json.dumps(item), parse_float=Decimal)


def handler(event, context):  # noqa: ARG001 - Lambda signature
    rows = current_readings()
    api = os.environ.get("JALMAAPI_API_URL")
    if api:
        import urllib.request

        for r in rows:
            req = urllib.request.Request(f"{api.rstrip('/')}/sites/{r['site_id']}/readings",
                                         data=json.dumps(r).encode(), headers={"Content-Type": "application/json"},
                                         method="POST")
            urllib.request.urlopen(req, timeout=10).read()
        return {"posted": len(rows)}
    if os.environ.get("JALMAAPI_BACKEND", "aws") == "aws":
        import boto3

        table = boto3.resource("dynamodb").Table(f"{TABLE_PREFIX}_readings")
        with table.batch_writer() as bw:
            for r in rows:
                bw.put_item(Item=_to_dynamo(r))
        return {"written": len(rows)}
    return {"dry_run": rows}


if __name__ == "__main__":
    os.environ.setdefault("JALMAAPI_BACKEND", "local")
    for r in current_readings():
        print(f"{r['site_id']:<16} t+{int(r['ts'] % (LOOP_MIN * 60)):>5}s  depth {r['max_depth_cm']:6.1f} cm  simulated={r['simulated']}")
