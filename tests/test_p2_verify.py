import os
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from sense import verify


@pytest.fixture
def frame(tmp_path):
    p = str(tmp_path / "f.jpg")
    cv2.imwrite(p, np.full((120, 200, 3), 100, np.uint8))
    return p


def test_parse_json_tolerant():
    assert verify.parse_json('{"a": 1}') == {"a": 1}
    assert verify.parse_json('Sure, here it is:\n{"low_cm": 10, "high_cm": 25}\nthanks') == {"low_cm": 10, "high_cm": 25}
    assert verify.parse_json("no json here") is None


def test_norm_box_conversion():
    assert verify._norm_box_to_px([0.1, 0.5, 0.9, 1.0], 200, 120) == [20, 60, 180, 119]
    assert verify._norm_box_to_px([20, 60, 180, 119], 200, 120) == [20, 60, 180, 119]   # pixels pass through
    assert verify._norm_box_to_px([0.9, 0.5, 0.1, 1.0], 200, 120) is None             # inverted
    assert verify._norm_box_to_px(None, 200, 120) is None


def test_disabled_returns_none(frame, monkeypatch):
    monkeypatch.setenv("JALMAAPI_USE_BEDROCK", "false")
    assert verify.depth_range_cm(frame) is None and verify.locate_water(frame) is None and verify.locate_exclusions(frame) == []


def test_mocked_bedrock_calls(frame, monkeypatch):
    monkeypatch.setenv("JALMAAPI_USE_BEDROCK", "true")
    answers = iter([
        '{"water_present": true, "box": [0.1, 0.5, 0.9, 1.0], "confidence": 0.8}',
        '{"objects": [{"label": "person", "box": [0.0, 0.0, 0.2, 0.5]}, {"label": "car", "box": "bad"}]}',
        '{"low_cm": 30, "high_cm": 12, "cues": ["kerb"], "ruler_reading_cm": null}',
        '{"low_cm": null, "high_cm": null, "cues": []}',
    ])

    class FakeMessages:
        def create(self, **kw):
            assert kw["model"] == verify.model_id()
            assert kw["messages"][0]["content"][0]["type"] == "image"
            return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=next(answers))])

    monkeypatch.setattr(verify, "_client", lambda: SimpleNamespace(messages=FakeMessages()))
    assert verify.locate_water(frame) == [20, 60, 180, 119]
    assert verify.locate_exclusions(frame) == [[0, 0, 40, 60]]
    assert verify.depth_range_cm(frame, context="ruler at the deepest point") == (12.0, 30.0)   # swapped bounds fixed
    assert verify.depth_range_cm(frame) is None                                                  # null bounds -> abstain


def test_refusal_and_errors_abstain(frame, monkeypatch):
    monkeypatch.setenv("JALMAAPI_USE_BEDROCK", "true")

    class Refusing:
        def create(self, **kw):
            return SimpleNamespace(stop_reason="refusal", content=[])

    monkeypatch.setattr(verify, "_client", lambda: SimpleNamespace(messages=Refusing()))
    assert verify.depth_range_cm(frame) is None

    def boom():
        raise RuntimeError("no credentials")

    monkeypatch.setattr(verify, "_client", boom)
    assert verify.depth_range_cm(frame) is None


def test_prompts_exist_and_format():
    for name in ("water_box", "exclusions"):
        assert "JSON" in verify.load_prompt(name)
    assert "Context: x" in verify.load_prompt("depth_cues", context="Context: x")
    assert os.path.exists(os.path.join(verify.PROMPT_DIR, "depth_cues.txt"))
