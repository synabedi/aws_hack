"""STUB. Owner: sense agent replaces with SAM 2.1 segmentation.
Contract: segment_water(frame_path, prompt_box=None, prompt_points=None) -> np.ndarray bool (H, W)
"""
from __future__ import annotations

import numpy as np
from PIL import Image


def segment_water(frame_path: str, prompt_box=None, prompt_points=None) -> np.ndarray:
    im = Image.open(frame_path)
    h, w = im.height, im.width
    mask = np.zeros((h, w), dtype=bool)
    mask[int(h * 0.6):, :] = True
    return mask
