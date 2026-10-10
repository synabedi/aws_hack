import os

import cv2
import numpy as np
import pytest

from sense import segment


@pytest.fixture(scope="module")
def pool_frame(tmp_path_factory):
    """Grey asphalt with a dark brown pool in the lower middle, mild noise."""
    d = tmp_path_factory.mktemp("frames")
    rng = np.random.default_rng(0)
    H, W = 240, 320
    img = np.full((H, W, 3), 150, np.uint8)
    img = (img + rng.normal(0, 6, img.shape)).clip(0, 255).astype(np.uint8)
    truth = np.zeros((H, W), bool)
    cv2.ellipse(truth.view(np.uint8), (160, 170), (110, 45), 0, 0, 360, 1, -1)
    img[truth] = (rng.normal(0, 4, (truth.sum(), 3)) + np.array([40, 60, 90])).clip(0, 255).astype(np.uint8)
    p = str(d / "f0.jpg")
    cv2.imwrite(p, img)
    p1 = str(d / "f1.jpg")
    cv2.imwrite(p1, img)
    return {"path": p, "path2": p1, "truth": truth, "dir": str(d)}


def iou(a, b):
    return (a & b).sum() / max((a | b).sum(), 1)


def test_grabcut_with_box_prompt(pool_frame):
    m = segment.segment_water(pool_frame["path"], prompt_box=[40, 115, 280, 225], backend="grabcut")
    assert m.shape == pool_frame["truth"].shape and m.dtype == bool
    assert iou(m, pool_frame["truth"]) > 0.8, iou(m, pool_frame["truth"])


def test_grabcut_with_point_prompt(pool_frame):
    m = segment.segment_water(pool_frame["path"], prompt_box=[20, 100, 300, 235], prompt_points=[[160, 170]], backend="grabcut")
    assert iou(m, pool_frame["truth"]) > 0.8


def test_default_prior_runs(pool_frame):
    m = segment.segment_water(pool_frame["path"], backend="grabcut")
    assert m.shape == pool_frame["truth"].shape and 0 < m.sum() < m.size


def test_segment_boxes_union(pool_frame):
    ex = segment.segment_boxes(pool_frame["path"], [[10, 10, 50, 50], [100, 20, 120, 40]], backend="grabcut")
    assert ex[10:51, 10:51].all() and ex[20:41, 100:121].all() and not ex[200, 200]
    assert not segment.segment_boxes(pool_frame["path"], [], backend="grabcut").any()


def test_segment_video_per_frame_tracking(pool_frame):
    masks = segment.segment_video([pool_frame["path"], pool_frame["path2"]], prompt_box=[40, 115, 280, 225], backend="grabcut")
    assert len(masks) == 2 and all(iou(m, pool_frame["truth"]) > 0.8 for m in masks)
    assert segment.segment_video([], backend="grabcut") == []


def test_backend_resolution():
    assert segment.resolve_backend("grabcut") == "grabcut"
    assert segment.resolve_backend("auto") in ("sam2", "grabcut")
    if not segment.sam2_available():
        with pytest.raises(RuntimeError):
            segment.resolve_backend("sam2")


def test_export_masks_cli(pool_frame, tmp_path):
    from sense.export_masks import main

    out = tmp_path / "masks"
    main(["--frames", pool_frame["dir"], "--out", str(out), "--backend", "grabcut", "--box", "40,115,280,225",
          "--exclude-boxes", "[[10,10,50,50]]"])
    assert os.path.exists(out / "f0_mask.png") and os.path.exists(out / "f0_exclude.png") and os.path.exists(out / "masks_meta.json")
    m = cv2.imread(str(out / "f0_mask.png"), cv2.IMREAD_GRAYSCALE) > 127
    assert iou(m, pool_frame["truth"]) > 0.8
