from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from performance_state import (  # noqa: E402
    approve_performance_state,
    performance_state_id,
    validate_performance_state,
)


def _image(path: Path, color: str = "navy") -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 112), color).save(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _generation_receipt(path: Path, *, output_sha256: str) -> Path:
    payload = {
        "kind": "image-edit-generation",
        "operation": "image_edit",
        "provider": "comfy_lan",
        "model": "qwen-image-edit-2511-local",
        "input_sha256": "a" * 64,
        "output_sha256": output_sha256,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_state_id_reuses_identical_performance_and_splits_real_change() -> None:
    base = {
        "speaker": "hero",
        "wardrobe_state": "full",
        "performance_state": {
            "emotion": "guarded",
            "gaze_target": "partner",
            "head_angle": "three-quarter",
            "body_orientation": "toward partner",
            "gesture": "holds the letter",
            "props": ["letter"],
            "lighting": "cool window key",
        },
        "dsl": {"camera": {"shot_size": "medium close-up"}},
    }
    same = {**base, "dialogue_line_id": "dlg_02"}
    changed = {
        **base,
        "performance_state": {**base["performance_state"], "emotion": "furious"},
    }

    assert performance_state_id(base) == performance_state_id(same)
    assert performance_state_id(base) != performance_state_id(changed)


def test_approved_state_requires_hash_bound_i2i_and_human_review(tmp_path: Path) -> None:
    state_id = "hero-state-deadbeef"
    image = tmp_path / "canonical" / "performance-states" / "hero" / f"{state_id}.png"
    output_sha = _image(image)
    generation = _generation_receipt(
        tmp_path / "generation.json",
        output_sha256=output_sha,
    )

    receipt = approve_performance_state(
        tmp_path,
        speaker="hero",
        state_id=state_id,
        image=image,
        generation_receipt=generation,
        reviewer="dex",
        review_note="identity, wardrobe, gaze and pose approved",
    )

    assert receipt["approval"]["status"] == "approved"
    assert receipt["lineage"]["input_sha256"] == "a" * 64
    report = validate_performance_state(tmp_path, speaker="hero", state_id=state_id)
    assert report["ok"] is True
    assert report["image_sha256"] == output_sha


def test_state_rejects_tampered_image_and_non_i2i_receipt(tmp_path: Path) -> None:
    state_id = "hero-state-deadbeef"
    image = tmp_path / "canonical" / "performance-states" / "hero" / f"{state_id}.png"
    output_sha = _image(image)
    generation = _generation_receipt(
        tmp_path / "generation.json",
        output_sha256=output_sha,
    )
    generation.write_text(
        json.dumps(
            {
                "operation": "image_gen",
                "model": "qwen",
                "input_sha256": "a" * 64,
                "output_sha256": output_sha,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="image_edit"):
        approve_performance_state(
            tmp_path,
            speaker="hero",
            state_id=state_id,
            image=image,
            generation_receipt=generation,
            reviewer="dex",
            review_note="reviewed",
        )

    generation = _generation_receipt(
        tmp_path / "generation.json",
        output_sha256=output_sha,
    )
    approve_performance_state(
        tmp_path,
        speaker="hero",
        state_id=state_id,
        image=image,
        generation_receipt=generation,
        reviewer="dex",
        review_note="reviewed",
    )
    _image(image, "red")
    assert validate_performance_state(tmp_path, speaker="hero", state_id=state_id)["ok"] is False
    assert (
        "OUTPUT_HASH_DRIFT"
        in validate_performance_state(tmp_path, speaker="hero", state_id=state_id)["codes"]
    )
