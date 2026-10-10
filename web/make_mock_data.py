"""Generate web/mock/*.json from the real physics model so the dashboard runs before the API exists.

Shapes match contracts/schemas.py and web/API.md exactly, so switching the dashboard from mock to the
live API is a base-URL change. Every synthetic site is simulated=True; the one real site (DTU staged
flood) has no reading until the field data is processed, and the UI says so.

Usage: .venv/bin/python web/make_mock_data.py  [--minutes-in 40]
"""
from __future__ import annotations

import argparse
import json
import os

from contracts.schemas import (
    VEHICLE_CLASSES,
    Action,
    Allocation,
    Bid,
    DrainHealth,
    Site,
    SiteState,
    Thresholds,
    VerdictCard,
    now_ts,
)
from predict.forecast import fit_and_forecast
from predict.simulate import minutes_above_threshold, simulate
from predict.thresholds import assumed_classes
from sim.generate import make_sites, synthetic_readings

OUT = os.path.join(os.path.dirname(__file__), "mock")
ASSUMED = assumed_classes()


def verdicts(site: Site, reading, forecast) -> list[VerdictCard]:
    th = site.thresholds.as_dict()
    cards = []
    for c in VEHICLE_CLASSES:
        depth = reading.max_depth_cm if reading else 0.0
        low = reading is None or reading.status != "confident"
        cards.append(VerdictCard(vehicle_class=c, threshold_cm=th[c], current_depth_cm=depth,
                                 passable=None if low else depth < th[c],
                                 t_impassable_min=(forecast.t_impassable_min.get(c) if forecast else None),
                                 assumed=c in ASSUMED))
    return cards


def advisory(site: Site, reading, forecast, kind: str) -> dict:
    d = reading.max_depth_cm
    th = site.thresholds
    blocked = [c for c in ("two_wheeler", "small_car", "large_car", "bus_truck") if d >= getattr(th, c)]
    names_en = {"two_wheeler": "two-wheelers", "small_car": "cars", "large_car": "large cars", "bus_truck": "buses and trucks"}
    names_hi = {"two_wheeler": "दोपहिया", "small_car": "कारें", "large_car": "बड़ी कारें", "bus_truck": "बस और ट्रक"}
    tmin = forecast.t_impassable_min.get("closure") if forecast else None
    when_en = f" Expected to reach the 15 cm closure level in about {tmin:.0f} minutes." if tmin and tmin > 0 else ""
    when_hi = f" लगभग {tmin:.0f} मिनट में 15 सेमी बंद-स्तर तक पहुँचने की संभावना।" if tmin and tmin > 0 else ""
    if kind == "closure":
        en = (f"[SIMULATED] {site.name}: water depth {d:.0f} cm (±{reading.sigma_cm:.0f} cm). Underpass CLOSED to "
              f"{', '.join(names_en[c] for c in blocked) or 'all vehicles'}. {site.diversion_en}.{when_en}")
        hi = (f"[सिम्युलेटेड] {site.name_hi}: पानी की गहराई {d:.0f} सेमी (±{reading.sigma_cm:.0f} सेमी)। अंडरपास "
              f"{', '.join(names_hi[c] for c in blocked) or 'सभी वाहनों'} के लिए बंद। {site.diversion_hi}।{when_hi}")
    else:
        en = f"[SIMULATED] {site.name}: water rising, depth {d:.0f} cm. Drive slowly, avoid the underpass if possible.{when_en}"
        hi = f"[सिम्युलेटेड] {site.name_hi}: पानी बढ़ रहा है, गहराई {d:.0f} सेमी। धीरे चलें, संभव हो तो अंडरपास से बचें।{when_hi}"
    return {"en": en, "hi": hi}


def main(minutes_in: int = 40, pumps_available: int = 4):
    os.makedirs(OUT, exist_ok=True)
    now = now_ts()
    t0 = now - minutes_in * 60
    states, histories, actions, bids, sim_fns, current_depth = [], {}, [], [], {}, {}
    sites = make_sites(6, seed=0)
    for site, basin, params, forcing in sites:
        rs = synthetic_readings(site, basin, params, forcing, t0=t0, duration_s=minutes_in * 60)
        fc = fit_and_forecast(rs, forcing, basin, site.thresholds, horizon_min=60, prior=params,
                              pump_rate_m3_s=site.pump_rate_m3_s, n_samples=60)
        site.params = params
        last = rs[-1]
        # drain health: one site shows a degraded drain so the card has something to say
        degraded = site.site_id == "sim_zakhira"
        k_now = params.k * (0.45 if degraded else 1.0)
        dh = DrainHealth(site_id=site.site_id, event_id=f"{site.site_id}_prev", k=k_now,
                         k_ci=(k_now * 0.8, k_now * 1.2), score_pct=45.0 if degraded else 100.0, flagged=degraded,
                         note=("draining at 45% of its best observed rate; flagged: below 60% on two consecutive events"
                               if degraded else "draining at 100% of its best observed rate"), simulated=True)
        pending = []
        tclose = fc.t_impassable_min.get("closure")
        if last.max_depth_cm >= site.thresholds.closure or (tclose is not None and tclose < 20):
            adv = advisory(site, last, fc, "closure")
            pending.append(Action(site_id=site.site_id, type="closure", status="proposed", proposed_by="site_agent",
                                  justification=(f"Depth {last.max_depth_cm:.0f} cm with sigma {last.sigma_cm:.1f} cm; "
                                                 f"median time to the 15 cm closure level {('now' if last.max_depth_cm >= 15 else f'{tclose:.0f} min')}; "
                                                 f"forecast band p10-p90 at +30 min {fc.p10[30]:.0f}-{fc.p90[30]:.0f} cm. "
                                                 "Policy: closures need officer approval."),
                                  payload={"advisory_en": adv["en"], "advisory_hi": adv["hi"], "reading_ts": last.ts,
                                           "frame_uri": last.frame_uri}, simulated=True, reading_status=last.status))
        elif last.max_depth_cm >= 5:
            adv = advisory(site, last, fc, "advisory")
            a = Action(site_id=site.site_id, type="advisory", status="published", proposed_by="dispatcher",
                       justification="Informational advisory: permitted automatically by policy.", published_at=now - 120,
                       payload={"advisory_en": adv["en"], "advisory_hi": adv["hi"]}, simulated=True)
            actions.append(a)
        actions += pending
        states.append(SiteState(site=site, latest_reading=last, latest_forecast=fc, verdicts=verdicts(site, last, fc),
                                drain_health=dh, pending_actions=pending))
        histories[site.site_id] = {"site_id": site.site_id, "readings": [r.model_dump() for r in rs]}
        sim_fns[site.site_id] = {str(p): simulate(rs, forcing, basin, site.thresholds, params, p, 60, site.pump_rate_m3_s, n_samples=30).model_dump()
                                 for p in (0, 1, 2, 3)}
        current_depth[site.site_id] = last.max_depth_cm
        # bids: marginal minutes above closure avoided per extra pump, times traffic weight
        base = minutes_above_threshold(simulate(rs, forcing, basin, site.thresholds, params, 0, 60, site.pump_rate_m3_s, n_samples=1), site.thresholds.closure)
        prev = base
        for p in (1, 2, 3):
            m = minutes_above_threshold(simulate(rs, forcing, basin, site.thresholds, params, p, 60, site.pump_rate_m3_s, n_samples=1), site.thresholds.closure)
            bids.append(Bid(site_id=site.site_id, pumps=p, minutes_avoided=prev - m, marginal_benefit=(prev - m) * site.traffic_weight, simulated=True))
            prev = m
    # the real site: no reading yet
    real = Site(site_id="dtu_staged", name="DTU campus staged flood (real site)", name_hi="डीटीयू परिसर स्टेज्ड फ्लड", lat=28.7501, lon=77.1177,
                simulated=False, thresholds=Thresholds(), traffic_weight=0.2, diversion_en="Campus test site: no traffic diversion", diversion_hi="परिसर परीक्षण स्थल",
                rain_source="hose")
    states.insert(0, SiteState(site=real, latest_reading=None, latest_forecast=None, verdicts=verdicts(real, None, None), drain_health=None, pending_actions=[]))
    histories["dtu_staged"] = {"site_id": "dtu_staged", "readings": []}
    # greedy allocation by marginal benefit, in pump order per site
    awards = {s.site.site_id: 0 for s in states}
    pool = pumps_available
    ranked = sorted(bids, key=lambda b: -b.marginal_benefit)
    for b in ranked:
        if pool == 0:
            break
        if b.marginal_benefit <= 0 or awards[b.site_id] != b.pumps - 1:
            continue
        awards[b.site_id] += 1
        pool -= 1
    # second pass for sites whose lower-order bids were skipped
    for b in ranked:
        if pool == 0:
            break
        if b.marginal_benefit > 0 and awards[b.site_id] == b.pumps - 1:
            awards[b.site_id] += 1
            pool -= 1
    baseline = {k: 0 for k in awards}
    worst = sorted(current_depth, key=lambda k: -current_depth[k])[:pumps_available]
    for i in range(pumps_available):
        baseline[worst[i % len(worst)]] += 1
    benefit = sum(b.minutes_avoided for b in bids if b.pumps <= awards[b.site_id])
    base_benefit = sum(b.minutes_avoided for b in bids if b.pumps <= baseline[b.site_id])
    alloc = Allocation(inventory={"pumps": pumps_available, "crews": pumps_available}, bids=bids, awards=awards, baseline_awards=baseline,
                       justification=(f"{pumps_available} mobile pumps allocated by marginal minutes-above-closure avoided over the next 60 min, "
                                      f"weighted by traffic. Forecast-based plan avoids {benefit:.0f} site-minutes above 15 cm vs {base_benefit:.0f} "
                                      "for 'nearest pump to the worst current depth'. All sites simulated."),
                       benefit_minutes=benefit, baseline_benefit_minutes=base_benefit)
    feed = [{"site_id": s.site.site_id, "name": s.site.name, "simulated": s.site.simulated, "lat": s.site.lat, "lon": s.site.lon,
             "ts": s.latest_reading.ts if s.latest_reading else None,
             "max_depth_cm": s.latest_reading.max_depth_cm if s.latest_reading else None,
             "sigma_cm": s.latest_reading.sigma_cm if s.latest_reading else None,
             "status": s.latest_reading.status if s.latest_reading else "no_reading",
             "verdicts": {v.vehicle_class: v.passable for v in s.verdicts}} for s in states]

    def dump(name, obj):
        with open(os.path.join(OUT, name), "w") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)

    dump("sites.json", [s.model_dump() for s in states])
    for sid, h in histories.items():
        dump(f"history_{sid}.json", h)
    for sid, w in sim_fns.items():
        dump(f"simulate_{sid}.json", w)
    dump("actions.json", [a.model_dump() for a in actions])
    dump("allocation.json", alloc.model_dump())
    dump("feed.json", feed)
    dump("meta.json", {"generated_ts": now, "mock": True, "minutes_into_scenario": minutes_in,
                       "note": "Mock data from sim/generate.py + predict/. All sites except dtu_staged are simulated."})
    print(f"wrote {len(states)} sites, {len(actions)} actions, {len(bids)} bids to {OUT}")
    for s in states:
        d = s.latest_reading.max_depth_cm if s.latest_reading else None
        tc = s.latest_forecast.t_impassable_min.get("closure") if s.latest_forecast else None
        print(f"  {s.site.site_id:<14} depth {d if d is None else round(d, 1)!s:>6}  t_close {tc}  pending {len(s.pending_actions)}  pumps {awards[s.site.site_id]} (baseline {baseline[s.site.site_id]})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes-in", type=int, default=40)
    a = ap.parse_args()
    main(a.minutes_in)
