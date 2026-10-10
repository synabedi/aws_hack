"""Vision-model cross-checks with Claude on Amazon Bedrock (architecture doc 8.5).

Three calls, each returning None when Bedrock is off, unreachable, or the model declines:
  locate_water(frame_path)        -> pixel box for the SAM 2 prompt
  locate_exclusions(frame_path)   -> pixel boxes for people and vehicles
  depth_range_cm(frame_path, ...) -> (low_cm, high_cm) independent depth estimate from visible cues

Enabled by JALMAAPI_USE_BEDROCK=true. Model: BEDROCK_MODEL_ID (default anthropic.claude-opus-5-5),
region AWS_REGION. Uses the Anthropic SDK's Bedrock (Mantle) client, so AWS credentials come from
the usual boto chain. Prompts are plain text files in sense/prompts/ so the writeup can quote them.
The vision model never replaces the geometry; it can only lower a reading's confidence.
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
from functools import lru_cache

from PIL import Image

PROMPT_DIR = os.path.join(os.path.dirname(__file__), "prompts")
DEFAULT_MODEL = "anthropic.claude-opus-5-5"
MAX_SIDE_PX = 1568


def bedrock_enabled() -> bool:
    return os.environ.get("JALMAAPI_USE_BEDROCK", "false").strip().lower() in ("1", "true", "yes")


def model_id() -> str:
    return os.environ.get("BEDROCK_MODEL_ID", DEFAULT_MODEL)


def load_prompt(name: str, **fmt) -> str:
    with open(os.path.join(PROMPT_DIR, f"{name}.txt")) as f:
        text = f.read()
    for k, v in fmt.items():          # plain replace: prompts contain literal JSON braces
        text = text.replace("{" + k + "}", str(v))
    return text


@lru_cache(maxsize=1)
def _client():
    from anthropic import AnthropicBedrockMantle

    return AnthropicBedrockMantle(aws_region=os.environ.get("AWS_REGION", "ap-south-1"))


def _image_block(frame_path: str) -> dict:
    im = Image.open(frame_path).convert("RGB")
    im.thumbnail((MAX_SIDE_PX, MAX_SIDE_PX))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=90)
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.standard_b64encode(buf.getvalue()).decode()}}


def parse_json(text: str) -> dict | None:
    """Tolerant JSON extraction: the whole text, else the first {...} block."""
    text = text.strip()
    for cand in (text, *re.findall(r"\{.*\}", text, flags=re.S)):
        try:
            v = json.loads(cand)
            if isinstance(v, dict):
                return v
        except json.JSONDecodeError:
            continue
    return None


def ask_json(frame_path: str, prompt: str, max_tokens: int = 1024) -> dict | None:
    """One vision call -> parsed JSON dict, or None on any failure (the caller abstains)."""
    if not bedrock_enabled():
        return None
    try:
        import anthropic
    except ImportError:
        print("[verify] anthropic SDK not installed (pip install 'anthropic[bedrock]'); abstaining")
        return None
    try:
        resp = _client().messages.create(
            model=model_id(), max_tokens=max_tokens,
            messages=[{"role": "user", "content": [_image_block(frame_path), {"type": "text", "text": prompt}]}],
        )
        if resp.stop_reason == "refusal":
            return None
        text = "".join(b.text for b in resp.content if b.type == "text")
        return parse_json(text)
    except anthropic.APIError as e:  # auth, region, model access, rate limit, server
        print(f"[verify] Bedrock call failed: {type(e).__name__}: {e}")
        return None
    except Exception as e:  # pragma: no cover - credentials chain, network
        print(f"[verify] Bedrock unavailable: {type(e).__name__}: {e}")
        return None


def _norm_box_to_px(box, w: int, h: int) -> list[int] | None:
    try:
        x0, y0, x1, y1 = [float(v) for v in box]
    except (TypeError, ValueError):
        return None
    if max(x0, y0, x1, y1) > 1.5:          # model answered in pixels already
        px = [x0, y0, x1, y1]
    else:
        px = [x0 * w, y0 * h, x1 * w, y1 * h]
    px = [int(round(v)) for v in px]
    px = [min(max(px[0], 0), w - 1), min(max(px[1], 0), h - 1), min(max(px[2], 0), w - 1), min(max(px[3], 0), h - 1)]
    if px[2] <= px[0] or px[3] <= px[1]:
        return None
    return px


def locate_water(frame_path: str) -> list[int] | None:
    out = ask_json(frame_path, load_prompt("water_box"))
    if not out or not out.get("water_present") or not out.get("box"):
        return None
    w, h = Image.open(frame_path).size
    return _norm_box_to_px(out["box"], w, h)


def locate_exclusions(frame_path: str) -> list[list[int]]:
    out = ask_json(frame_path, load_prompt("exclusions"))
    if not out:
        return []
    w, h = Image.open(frame_path).size
    boxes = []
    for obj in out.get("objects", []) or []:
        b = _norm_box_to_px(obj.get("box"), w, h) if isinstance(obj, dict) else None
        if b:
            boxes.append(b)
    return boxes


def depth_range_cm(frame_path: str, context: str = "") -> tuple[float, float] | None:
    """Independent depth range from visible cues. None = no usable cue or Bedrock off."""
    ctx = f"Context: {context}" if context else ""
    out = ask_json(frame_path, load_prompt("depth_cues", context=ctx))
    if not out:
        return None
    lo, hi = out.get("low_cm"), out.get("high_cm")
    try:
        lo, hi = float(lo), float(hi)
    except (TypeError, ValueError):
        return None
    if hi < lo:
        lo, hi = hi, lo
    return (max(lo, 0.0), max(hi, 0.0))
