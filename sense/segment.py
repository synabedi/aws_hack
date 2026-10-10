"""Water (and person/vehicle) segmentation.

Backends
  sam2     SAM 2.1 (Apache 2.0, facebook/sam2.1-hiera-*) image predictor, and the video
           predictor for prompt-once-propagate on a clip. Needs torch + sam2 (``pip install
           -e .[gpu]``). Runs on CUDA, falls back to CPU (MPS is unreliable for SAM 2).
  grabcut  OpenCV GrabCut seeded by the same box/points. No GPU, no weights. Used when
           sam2 is not installed, so the pipeline always produces a mask; weaker on wet
           asphalt and reflections, which is exactly where SAM 2 also struggles.

Prompt source (architecture doc 8.2): a box from the vision model (sense/verify.py), then a
manual click. With no prompt at all, a weak prior (lower 55% of the frame) is used and the
caller should expect low confidence.

Public API (signatures fixed in docs/CONVENTIONS.md):
  segment_water(frame_path, prompt_box=None, prompt_points=None, backend="auto") -> bool (H, W)
  segment_boxes(frame_path, boxes, backend="auto") -> bool (H, W)      union mask of people/vehicles
  segment_video(frame_paths, prompt_box=None, prompt_points=None, backend="auto") -> list[bool (H, W)]
Boxes are pixel [x0, y0, x1, y1]; points are pixel [[x, y], ...] (positive clicks).
"""
from __future__ import annotations

import os
from functools import lru_cache

import numpy as np
from PIL import Image

SAM2_CHECKPOINT = os.environ.get("SAM2_CHECKPOINT", "facebook/sam2.1-hiera-tiny")
Backend = str  # "auto" | "sam2" | "grabcut"


def _load_rgb(frame_path: str) -> np.ndarray:
    return np.asarray(Image.open(frame_path).convert("RGB"))


def sam2_available() -> bool:
    try:
        import sam2  # noqa: F401
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


def resolve_backend(backend: Backend) -> str:
    if backend == "auto":
        return "sam2" if sam2_available() else "grabcut"
    if backend == "sam2" and not sam2_available():
        raise RuntimeError("sam2 backend requested but torch/sam2 are not installed (pip install -e '.[gpu]')")
    return backend


def default_prior_box(h: int, w: int) -> list[int]:
    """Weak prior when no prompt is given: water collects in the lower part of a fixed CCTV view."""
    return [0, int(0.45 * h), w - 1, h - 1]


# ------------------------------------------------------------------ SAM 2.1
def _device():
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


@lru_cache(maxsize=1)
def _image_predictor():
    from sam2.sam2_image_predictor import SAM2ImagePredictor

    return SAM2ImagePredictor.from_pretrained(SAM2_CHECKPOINT, device=_device())


def _sam2_predict(rgb: np.ndarray, box, points) -> np.ndarray:
    import torch

    pred = _image_predictor()
    with torch.inference_mode():
        pred.set_image(rgb)
        kw = {"multimask_output": False}
        if box is not None:
            kw["box"] = np.asarray(box, dtype=np.float32)
        if points is not None and len(points):
            kw["point_coords"] = np.asarray(points, dtype=np.float32)
            kw["point_labels"] = np.ones(len(points), dtype=np.int32)
        masks, scores, _ = pred.predict(**kw)
    return np.asarray(masks[0]).astype(bool)


# ------------------------------------------------------------------ GrabCut
def _grabcut(rgb: np.ndarray, box, points, iters: int = 5) -> np.ndarray:
    import cv2

    h, w = rgb.shape[:2]
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    mask = np.full((h, w), cv2.GC_BGD, np.uint8)
    if box is None:
        box = default_prior_box(h, w)
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    x0, y0 = max(x0, 0), max(y0, 0)
    x1, y1 = min(x1, w - 1), min(y1, h - 1)
    if x1 <= x0 + 1 or y1 <= y0 + 1:
        return np.zeros((h, w), bool)
    mask[y0:y1 + 1, x0:x1 + 1] = cv2.GC_PR_FGD
    # a thin band inside the box edge is "probably background" so GrabCut can carve the shape
    band = max(2, min(x1 - x0, y1 - y0) // 20)
    mask[y0:y0 + band, x0:x1 + 1] = cv2.GC_PR_BGD
    mask[y1 - band + 1:y1 + 1, x0:x1 + 1] = cv2.GC_PR_BGD
    mask[y0:y1 + 1, x0:x0 + band] = cv2.GC_PR_BGD
    mask[y0:y1 + 1, x1 - band + 1:x1 + 1] = cv2.GC_PR_BGD
    if points is not None:
        for x, y in points:
            cv2.circle(mask, (int(x), int(y)), 4, int(cv2.GC_FGD), -1)
    bgd = np.zeros((1, 65), np.float64)
    fgd = np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(bgr, mask, None, bgd, fgd, iters, cv2.GC_INIT_WITH_MASK)
    except cv2.error:
        return np.zeros((h, w), bool)
    out = (mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD)
    return _largest_component(out)


def _largest_component(mask: np.ndarray) -> np.ndarray:
    from scipy import ndimage

    labels, n = ndimage.label(mask)
    if n <= 1:
        return mask
    sizes = ndimage.sum(mask, labels, index=np.arange(1, n + 1))
    return labels == (int(np.argmax(sizes)) + 1)


# ------------------------------------------------------------------ public API
def segment_water(frame_path: str, prompt_box=None, prompt_points=None, backend: Backend = "auto") -> np.ndarray:
    rgb = _load_rgb(frame_path)
    be = resolve_backend(backend)
    if prompt_box is None and prompt_points is None:
        prompt_box = default_prior_box(*rgb.shape[:2])
    if be == "sam2":
        return _sam2_predict(rgb, prompt_box, prompt_points)
    return _grabcut(rgb, prompt_box, prompt_points)


def segment_boxes(frame_path: str, boxes: list[list[float]], backend: Backend = "auto") -> np.ndarray:
    """Union mask for people/vehicle boxes, used to drop their edges from the waterline."""
    rgb = _load_rgb(frame_path)
    h, w = rgb.shape[:2]
    out = np.zeros((h, w), bool)
    if not boxes:
        return out
    be = resolve_backend(backend)
    for b in boxes:
        if be == "sam2":
            out |= _sam2_predict(rgb, b, None)
        else:
            x0, y0, x1, y1 = [int(round(v)) for v in b]
            out[max(y0, 0):min(y1, h - 1) + 1, max(x0, 0):min(x1, w - 1) + 1] = True  # box fill is good enough for exclusion
    return out


def segment_video(frame_paths: list[str], prompt_box=None, prompt_points=None, backend: Backend = "auto") -> list[np.ndarray]:
    """Prompt once on the first frame, propagate through the clip (doc 8.2)."""
    if not frame_paths:
        return []
    be = resolve_backend(backend)
    if be == "sam2":
        try:
            return _sam2_video(frame_paths, prompt_box, prompt_points)
        except Exception as e:  # pragma: no cover - depends on the sam2 build
            print(f"sam2 video propagation failed ({e}); falling back to per-frame prediction")
    masks = []
    prev = None
    for p in frame_paths:
        if prev is not None and prompt_points is None:
            # seed each frame from the previous mask's centroid so the prompt tracks the pool
            ys, xs = np.nonzero(prev)
            pts = [[float(xs.mean()), float(ys.mean())]] if len(xs) else None
            m = segment_water(p, prompt_box, pts, be)
        else:
            m = segment_water(p, prompt_box, prompt_points, be)
        masks.append(m)
        prev = m
    return masks


def _sam2_video(frame_paths, box, points):
    import shutil
    import tempfile

    import torch
    from sam2.sam2_video_predictor import SAM2VideoPredictor

    pred = SAM2VideoPredictor.from_pretrained(SAM2_CHECKPOINT, device=_device())
    tmp = tempfile.mkdtemp(prefix="sam2frames_")
    try:
        for i, p in enumerate(frame_paths):
            Image.open(p).convert("RGB").save(os.path.join(tmp, f"{i:05d}.jpg"), quality=95)
        with torch.inference_mode():
            state = pred.init_state(video_path=tmp)
            kw = {}
            if box is not None:
                kw["box"] = np.asarray(box, dtype=np.float32)
            if points is not None and len(points):
                kw["points"] = np.asarray(points, dtype=np.float32)
                kw["labels"] = np.ones(len(points), dtype=np.int32)
            pred.add_new_points_or_box(state, frame_idx=0, obj_id=1, **kw)
            out = [None] * len(frame_paths)
            for fi, _ids, logits in pred.propagate_in_video(state):
                out[fi] = (logits[0, 0] > 0).cpu().numpy().astype(bool)
        h, w = Image.open(frame_paths[0]).size[::-1]
        return [m if m is not None else np.zeros((h, w), bool) for m in out]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
