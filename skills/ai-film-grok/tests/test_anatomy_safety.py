from __future__ import annotations

import json
from pathlib import Path

import pytest
from anatomy_safety import AnatomySafetyError, anatomy_safety_report, require_anatomy_safe
from media_queue import MediaQueue, QueueError
from runtime_policy import sha256


def _adult_root(tmp_path: Path) -> Path:
    (tmp_path / "film-spec.json").write_text(
        json.dumps({"heat_scale": "max", "adult_max_iron": True}), encoding="utf-8"
    )
    return tmp_path


def test_adult_max_approval_requires_explicit_human_anatomy_attestation(tmp_path: Path) -> None:
    with pytest.raises(AnatomySafetyError, match="--anatomy-safe"):
        require_anatomy_safe(
            root=_adult_root(tmp_path), anatomy_safe=False, kind="still", shot_id="s1"
        )


def test_non_adult_project_does_not_require_anatomy_attestation(tmp_path: Path) -> None:
    require_anatomy_safe(root=tmp_path, anatomy_safe=False, kind="clip", shot_id="s1")


def test_report_rejects_missing_and_explicitly_poisoned_media() -> None:
    report = anatomy_safety_report(
        {
            "stills": {
                "s1": {"status": "approved", "anatomy_safe": True},
                "s2": {"status": "approved"},
                "s3": {"status": "approved", "anatomy_safe": False},
            }
        },
        required_shot_ids=["s1", "s2", "s3"],
        kind="stills",
    )
    assert report["ok"] is False
    assert report["missing_attestation_shots"] == ["s2"]
    assert report["poisoned_shots"] == ["s3"]


def test_adult_max_i2v_queue_rejects_unattested_keyframe(tmp_path: Path) -> None:
    import os
    from unittest import mock

    root = _adult_root(tmp_path)
    (root / "manifest.json").write_text(json.dumps({"stills": {}}), encoding="utf-8")
    prompt = root / "shot01.txt"
    image = root / "shot01.png"
    prompt.write_text("prompt", encoding="utf-8")
    image.write_bytes(b"png")
    # Isolate anatomy gate from I2.4 generation_request hard path
    with mock.patch.dict(os.environ, {"AIFILM_SKIP_GENERATION_REQUEST": "1"}, clear=False):
        with pytest.raises(QueueError, match="approved keyframe|anatomy_safe|I2V blocked"):
            MediaQueue(root).add_job(
                shot_id="shot01",
                operation="image_to_video",
                prompt_file=prompt,
                inputs=[image],
            )


def test_adult_max_i2v_queue_binds_input_bytes_to_the_safe_keyframe(tmp_path: Path) -> None:
    import os
    from unittest import mock

    root = _adult_root(tmp_path)
    safe = root / "safe.png"
    poison = root / "unreviewed-poison.png"
    prompt = root / "shot01.txt"
    safe.write_bytes(b"safe-png")
    poison.write_bytes(b"other-png")
    prompt.write_text("prompt", encoding="utf-8")
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "stills": {
                    "shot01": {
                        "status": "approved",
                        "anatomy_safe": True,
                        "path": str(safe),
                        "sha256": sha256(safe),
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    with mock.patch.dict(os.environ, {"AIFILM_SKIP_GENERATION_REQUEST": "1"}, clear=False):
        with pytest.raises(QueueError, match="does not match the approved anatomy-safe"):
            MediaQueue(root).add_job(
                shot_id="shot01",
                operation="image_to_video",
                prompt_file=prompt,
                inputs=[poison],
            )


def test_adult_max_reference_i2v_rejects_extra_unreviewed_image(tmp_path: Path) -> None:
    import os
    from unittest import mock

    root = _adult_root(tmp_path)
    safe = root / "safe.png"
    poison = root / "unreviewed-poison.png"
    prompt = root / "shot01.txt"
    safe.write_bytes(b"safe-png")
    poison.write_bytes(b"other-png")
    prompt.write_text("prompt", encoding="utf-8")
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "stills": {
                    "shot01": {
                        "status": "approved",
                        "anatomy_safe": True,
                        "path": str(safe),
                        "sha256": sha256(safe),
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    with mock.patch.dict(os.environ, {"AIFILM_SKIP_GENERATION_REQUEST": "1"}, clear=False):
        with pytest.raises(QueueError, match="every input must be"):
            MediaQueue(root).add_job(
                shot_id="shot01",
                operation="reference_to_video",
                prompt_file=prompt,
                inputs=[safe, poison],
            )
