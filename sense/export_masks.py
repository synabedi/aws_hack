"""Masks for a staged-flood pass: frames dir -> <stem>_mask.png (+ <stem>_exclude.png), optional S3 upload.

Prompt order (doc 8.2): --box, else the vision model's water box on the first frame
(needs JALMAAPI_USE_BEDROCK=true), else a manual click (--point), else the weak lower-frame prior.
--video propagates one prompt through the clip (SAM 2 video predictor; per-frame tracking
with the GrabCut fallback). --vlm-exclude asks the vision model for people/vehicle boxes.

Example:
  python -m sense.export_masks --frames validation/frames/A --out validation/masks/A --video \
      --box 120,400,1800,1070 --s3-prefix s3://jalmaapi-<acct>/site_dtu/masks/A
"""
from __future__ import annotations

import argparse
import json
import os

import cv2
import numpy as np

from sense import segment, verify


def list_frames(frames_dir: str) -> list[str]:
    return sorted(os.path.join(frames_dir, f) for f in os.listdir(frames_dir)
                  if f.lower().endswith((".jpg", ".jpeg", ".png")))


def upload_dir(local_dir: str, s3_prefix: str) -> int:
    import boto3

    assert s3_prefix.startswith("s3://")
    bucket, _, prefix = s3_prefix[5:].partition("/")
    s3 = boto3.client("s3")
    n = 0
    for f in sorted(os.listdir(local_dir)):
        s3.upload_file(os.path.join(local_dir, f), bucket, f"{prefix.rstrip('/')}/{f}")
        n += 1
    return n


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--backend", default="auto", choices=["auto", "sam2", "grabcut"])
    ap.add_argument("--box", help="x0,y0,x1,y1 pixel prompt box for the water")
    ap.add_argument("--point", action="append", help="x,y positive click (repeatable)")
    ap.add_argument("--video", action="store_true", help="prompt once, propagate through the clip")
    ap.add_argument("--exclude-boxes", help='JSON [[x0,y0,x1,y1], ...] people/vehicle boxes (all frames)')
    ap.add_argument("--vlm-exclude", action="store_true", help="ask the vision model for people/vehicle boxes per frame")
    ap.add_argument("--s3-prefix", help="upload the out dir to s3://bucket/prefix")
    a = ap.parse_args(argv)

    frames = list_frames(a.frames)
    if not frames:
        raise SystemExit(f"no frames in {a.frames}")
    os.makedirs(a.out, exist_ok=True)

    box = [float(v) for v in a.box.split(",")] if a.box else None
    points = [[float(v) for v in p.split(",")] for p in a.point] if a.point else None
    source = "manual box" if box else ("manual click" if points else None)
    if box is None and points is None and verify.bedrock_enabled():
        box = verify.locate_water(frames[0])
        source = "vision model box" if box else None
    if source is None:
        source = "lower-frame prior (weak)"
    print(f"prompt: {source} box={box} points={points} backend={segment.resolve_backend(a.backend)}")

    masks = segment.segment_video(frames, box, points, a.backend) if a.video else \
        [segment.segment_water(f, box, points, a.backend) for f in frames]

    static_ex = json.loads(a.exclude_boxes) if a.exclude_boxes else []
    meta = {"prompt_source": source, "box": box, "points": points, "backend": segment.resolve_backend(a.backend),
            "video": a.video, "frames": []}
    for f, m in zip(frames, masks):
        stem = os.path.splitext(os.path.basename(f))[0]
        cv2.imwrite(os.path.join(a.out, f"{stem}_mask.png"), m.astype(np.uint8) * 255)
        boxes = list(static_ex)
        if a.vlm_exclude:
            boxes += verify.locate_exclusions(f)
        if boxes:
            ex = segment.segment_boxes(f, boxes, a.backend)
            cv2.imwrite(os.path.join(a.out, f"{stem}_exclude.png"), ex.astype(np.uint8) * 255)
        meta["frames"].append({"stem": stem, "water_px": int(m.sum()), "exclusions": len(boxes)})
        print(f"{stem}: water {100 * m.mean():.1f}% of frame, {len(boxes)} exclusion boxes")
    with open(os.path.join(a.out, "masks_meta.json"), "w") as fh:
        json.dump(meta, fh, indent=2)
    if a.s3_prefix:
        n = upload_dir(a.out, a.s3_prefix)
        print(f"uploaded {n} files to {a.s3_prefix}")


if __name__ == "__main__":
    main()
