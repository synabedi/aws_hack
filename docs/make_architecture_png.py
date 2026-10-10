"""Draw docs/architecture.png with Pillow (no graphviz needed): 3 inputs, 5 layers, 1 shared site model."""
from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

W, H = 1600, 900
BG, INK, BOX, ACC, SIM = (250, 250, 247), (30, 30, 30), (228, 236, 244), (0, 92, 160), (255, 239, 213)


def font(size: int, bold: bool = False):
    for name in (["Helvetica-Bold", "Arial Bold"] if bold else ["Helvetica", "Arial"]):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def box(d, xy, title, lines, fill=BOX, title_size=22):
    x0, y0, x1, y1 = xy
    d.rounded_rectangle(xy, radius=14, fill=fill, outline=ACC, width=2)
    d.text((x0 + 14, y0 + 10), title, fill=ACC, font=font(title_size, True))
    y = y0 + 44
    for ln in lines:
        d.text((x0 + 14, y), ln, fill=INK, font=font(17))
        y += 24


def arrow(d, a, b):
    d.line([a, b], fill=ACC, width=3)
    (x1, y1) = b
    d.polygon([(x1, y1), (x1 - 10, y1 - 6), (x1 - 10, y1 + 6)] if a[0] < b[0] else
              [(x1, y1), (x1 - 6, y1 - 10), (x1 + 6, y1 - 10)], fill=ACC)


def main(out="docs/architecture.png"):
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.text((40, 24), "JalMaapi: 3 inputs, 5 layers, 1 shared site model per hotspot", fill=INK, font=font(30, True))
    d.text((40, 64), "Delhi PWD CCTV frame -> depth in cm -> minutes to impassable -> officer-approved advisory", fill=INK, font=font(18))
    # inputs
    box(d, (40, 120, 360, 250), "Inputs", ["CCTV frame / staged clip", "Dry-day phone walk-through", "Rain: Open-Meteo / IMD / hose rate"])
    # layers
    box(d, (420, 120, 740, 290), "1  Sense", ["SAM 2.1 water mask (GPU worker)", "waterline -> twin lookup", "percentile level +/- sigma", "Claude on Bedrock cue cross-check", "abstain -> low_confidence"])
    box(d, (800, 120, 1120, 290), "2  Predict", ["A(h) dh/dt = R i - k sqrt(h-h0) - Qpump", "least-squares R, k + covariance", "100-sample band", "minutes to impassable per class"])
    box(d, (1180, 120, 1560, 290), "3  Act", ["Strands agents on Bedrock", "pump bidding (deterministic maths)", "Cedar policy: closure needs officer", "SNS approval -> Hindi + English advisory"])
    box(d, (420, 330, 740, 450), "0  Dry twin (offline)", ["MapAnything metric 3D model", "chalk-mark calibration (<= 2 cm)", "5 cm heightmap, A(h), V(h)"])
    box(d, (800, 330, 1120, 450), "Shared site model", ["params {R, k, h0} per site", "fitted on every confident reading", "queried by Predict, Act, Diagnose"], fill=(255, 250, 225))
    box(d, (1180, 330, 1560, 450), "4  Diagnose", ["k per event with interval", "health = k_latest / k_best", "flag < 60% twice", "validated: outlet open vs blocked"])
    box(d, (420, 490, 740, 610), "5  See (video only)", ["dashboard: map, site, approval", "4D twin / satellite layer (stretch)"])
    box(d, (800, 490, 1120, 610), "Simulated sites", ["5-8 synthetic hotspots from the", "same model; labelled simulated", "everywhere (EventBridge + Lambda)"], fill=SIM)
    box(d, (1180, 490, 1560, 610), "Officer (PWD nodal)", ["sees frame, heatmap, forecast", "approves / rejects: logged", "Flood Control Order 2026 record"])
    # arrows
    arrow(d, (360, 185), (420, 185))
    arrow(d, (740, 205), (800, 205))
    arrow(d, (1120, 205), (1180, 205))
    arrow(d, (580, 330), (580, 290))
    arrow(d, (960, 290), (960, 330))
    arrow(d, (1120, 390), (1180, 390))
    arrow(d, (1370, 450), (1370, 490))
    arrow(d, (960, 450), (960, 490))
    # AWS strip
    d.rounded_rectangle((40, 660, 1560, 860), radius=14, fill=(236, 243, 236), outline=(60, 120, 60), width=2)
    d.text((54, 672), "AWS", fill=(40, 100, 40), font=font(22, True))
    cols = [("App Runner", "FastAPI + Strands agents + Cedar"), ("Amazon Bedrock", "Claude: verifier, advisories, justifications"),
            ("EC2 g5 / local GPU", "MapAnything, SAM 2.1"), ("S3", "frames, masks, twins, basin tables"),
            ("DynamoDB", "sites, readings, forecasts, actions"), ("SNS", "officer approval link"),
            ("EventBridge + Lambda", "simulated site replay, 30 s"), ("Amplify / CloudWatch", "dashboard hosting, logs")]
    for i, (t, sline) in enumerate(cols):
        xx = 54 + (i % 4) * 375
        yy = 710 + (i // 4) * 70
        d.text((xx, yy), t, fill=INK, font=font(19, True))
        d.text((xx, yy + 26), sline, fill=INK, font=font(15))
    d.text((40, H - 28), "Open source used: MapAnything (Apache), SAM 2.1 (Apache), Strands Agents SDK (Apache), Cedar (Apache)", fill=INK, font=font(15))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    im.save(out)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
