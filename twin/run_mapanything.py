"""Run MapAnything (facebook/map-anything-apache, Apache 2.0) on sampled walk-through
frames plus the fixed-camera reference still, and save what Sense needs.

Writes into ``twin_dir``:
    frames/                sampled JPEGs (frame_000.jpg ...) plus ref.jpg (the reference still, index 0)
    ref_pointmap.npy       (H, W, 3) float32 3D point of every reference-still pixel, reconstruction coords
    ref_conf.npy           (H, W) float32 confidence for the reference still
    points.npy             (N, 3) float32 all confident points from all views
    poses.npy              (V, 4, 4) camera-to-world poses
    intrinsics.npy         (V, 3, 3)

Then run twin/calibrate.py (control marks) and twin/basin.py (heightmap + basin.csv).

Needs a GPU box with ``pip install mapanything`` (see the MapAnything README). On a
machine without it, this script exits with a clear message; the tape-grid fallback in
twin/basin.py builds the heightmap by hand.

Supplying intrinsics is strongly recommended: the paper reports scale error falling
from ~13% (images only) to ~6% with intrinsics (arXiv 2509.13414). Calibration against
the chalk marks is mandatory either way.
"""
from __future__ import annotations

import argparse
import os

import numpy as np


def sample_frames(video_path: str, out_dir: str, n_frames: int = 60) -> list[str]:
    import cv2

    os.makedirs(out_dir, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        raise RuntimeError(f"cannot read {video_path}")
    idx = np.linspace(0, total - 1, min(n_frames, total)).astype(int)
    paths = []
    for i, fi in enumerate(idx):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(fi))
        ok, frame = cap.read()
        if not ok:
            continue
        p = os.path.join(out_dir, f"frame_{i:03d}.jpg")
        cv2.imwrite(p, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
        paths.append(p)
    cap.release()
    return paths


def run(twin_dir: str, reference_still: str, video: str | None, frames_dir: str | None,
        n_frames: int = 60, device: str = "cuda", intrinsics_json: str | None = None) -> None:
    import shutil

    fdir = os.path.join(twin_dir, "frames")
    os.makedirs(fdir, exist_ok=True)
    ref_path = os.path.join(fdir, "ref.jpg")
    shutil.copy(reference_still, ref_path)
    if video:
        sample_frames(video, fdir, n_frames)
    elif frames_dir:
        for i, f in enumerate(sorted(os.listdir(frames_dir))):
            if f.lower().endswith((".jpg", ".jpeg", ".png")):
                shutil.copy(os.path.join(frames_dir, f), os.path.join(fdir, f"frame_{i:03d}.jpg"))
    else:
        raise SystemExit("give --video or --frames-dir")

    try:
        import torch
        from mapanything.models import MapAnything
        from mapanything.utils.image import load_images
    except ImportError as e:  # pragma: no cover
        raise SystemExit(
            f"MapAnything not installed ({e}). Install on the GPU box per "
            "https://github.com/facebookresearch/map-anything, or use the tape-grid fallback: "
            "python -m twin.basin --twin-dir <dir> --tape-grid validation/data/tape_grid.csv"
        )

    model = MapAnything.from_pretrained("facebook/map-anything-apache").to(device)
    model.eval()
    # ref.jpg sorts first, so view 0 is the reference still
    views = load_images(fdir)
    if intrinsics_json:
        import json

        with open(intrinsics_json) as f:
            K = np.asarray(json.load(f)["K"], dtype=np.float32)
        for v in views:
            v["intrinsics"] = torch.from_numpy(K)[None]
    with torch.no_grad():
        preds = model.infer(
            views, memory_efficient_inference=False, use_amp=True, amp_dtype="bf16",
            apply_mask=True, mask_edges=True, apply_confidence_mask=False, confidence_percentile=10,
        )

    def to_np(x):
        return x.detach().float().cpu().numpy() if hasattr(x, "detach") else np.asarray(x)

    ref = preds[0]
    pm = to_np(ref["pts3d"])[0]
    conf = to_np(ref["conf"])[0] if "conf" in ref else np.ones(pm.shape[:2], np.float32)
    mask = to_np(ref["mask"])[0].astype(bool) if "mask" in ref else np.ones(pm.shape[:2], bool)
    pm = pm.astype(np.float32)
    pm[~mask] = np.nan
    np.save(os.path.join(twin_dir, "ref_pointmap.npy"), pm)
    np.save(os.path.join(twin_dir, "ref_conf.npy"), conf.astype(np.float32))

    pts, poses, Ks = [], [], []
    for p in preds:
        x = to_np(p["pts3d"])[0].reshape(-1, 3)
        m = to_np(p["mask"])[0].reshape(-1).astype(bool) if "mask" in p else np.ones(len(x), bool)
        pts.append(x[m])
        poses.append(to_np(p["camera_poses"])[0])
        Ks.append(to_np(p["intrinsics"])[0])
    np.save(os.path.join(twin_dir, "points.npy"), np.concatenate(pts).astype(np.float32))
    np.save(os.path.join(twin_dir, "poses.npy"), np.stack(poses).astype(np.float32))
    np.save(os.path.join(twin_dir, "intrinsics.npy"), np.stack(Ks).astype(np.float32))
    print(f"saved twin to {twin_dir}: ref_pointmap {pm.shape}, {sum(len(p) for p in pts)} points, {len(preds)} views")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--twin-dir", required=True)
    ap.add_argument("--reference-still", required=True, help="the fixed camera's dry frame")
    ap.add_argument("--video", help="walk-through clip from the second phone")
    ap.add_argument("--frames-dir", help="already-sampled frames instead of --video")
    ap.add_argument("--n-frames", type=int, default=60)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--intrinsics-json", help='{"K": [[fx,0,cx],[0,fy,cy],[0,0,1]]} for the walk-through phone')
    a = ap.parse_args()
    run(a.twin_dir, a.reference_still, a.video, a.frames_dir, a.n_frames, a.device, a.intrinsics_json)
