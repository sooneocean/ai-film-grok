from __future__ import annotations

import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from adult_female_voice_pack import (
    PACK_ID,
    AdultFemaleVoicePackError,
    approve,
    initialize,
    list_candidates,
    render_pending,
)


def test_initialize_creates_fixed_16_item_pack(tmp_path: Path) -> None:
    pack = initialize(tmp_path)
    assert pack["pack_id"] == PACK_ID
    assert len(pack["items"]) == 16
    assert {item["kind"] for item in pack["items"]} == {"dialogue", "breath"}
    assert all(item["voice_profile"].startswith("qwen_zh_female_") for item in pack["items"])


@pytest.mark.parametrize("mutation", ("empty", "voice"))
def test_initialize_rejects_a_tampered_fixed_plan(tmp_path: Path, mutation: str) -> None:
    pack = copy.deepcopy(initialize(tmp_path))
    if mutation == "empty":
        pack["items"] = []
    else:
        pack["items"][0]["voice_profile"] = "qwen_zh_female_mature"
    path = tmp_path / "dialogue-packs" / f"{PACK_ID}.json"
    path.write_text(json.dumps(pack), encoding="utf-8")
    with pytest.raises(AdultFemaleVoicePackError, match="fixed v1 plan"):
        initialize(tmp_path)


def test_render_creates_pending_signed_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIFILM_AUDIO_RECEIPT_KEY", "x" * 24)

    def fake_render(_base: str, _token: str, _kind: str, payload: dict, out: Path) -> dict:
        out.write_bytes(b"RIFF" + payload["text"].encode())
        import hashlib

        return {"job_id": f"job-{out.stem}", "sha256": hashlib.sha256(out.read_bytes()).hexdigest()}

    with (
        patch(
            "adult_female_voice_pack.health", return_value={"tts_variants": {"voice_design": True}}
        ),
        patch("adult_female_voice_pack.render", side_effect=fake_render),
        patch("adult_female_voice_pack._validate_wav"),
    ):
        result = render_pending(tmp_path, base_url="http://192.168.1.2:8788", token="x" * 24)
    assert len(result["rendered"]) == 16
    candidates = list_candidates(tmp_path)
    assert len(candidates) == 16
    assert all(candidate["status"] == "pending_human_review" for candidate in candidates)


def test_approve_requires_all_hearing_confirmations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIFILM_AUDIO_RECEIPT_KEY", "x" * 24)

    def fake_render(_base: str, _token: str, _kind: str, payload: dict, out: Path) -> dict:
        out.write_bytes(b"RIFF" + payload["text"].encode())
        import hashlib

        return {"job_id": "job-1", "sha256": hashlib.sha256(out.read_bytes()).hexdigest()}

    with (
        patch(
            "adult_female_voice_pack.health", return_value={"tts_variants": {"voice_design": True}}
        ),
        patch("adult_female_voice_pack.render", side_effect=fake_render),
        patch("adult_female_voice_pack._validate_wav"),
    ):
        render_pending(tmp_path, base_url="http://192.168.1.2:8788", token="x" * 24)
        with pytest.raises(AdultFemaleVoicePackError, match="three human hearing"):
            approve(
                tmp_path,
                f"{PACK_ID}-breath-short-intake",
                reviewer="dex",
                female_voice_confirmed=True,
                breath_confirmed=False,
                artifact_free_confirmed=True,
            )
        result = approve(
            tmp_path,
            f"{PACK_ID}-breath-short-intake",
            reviewer="dex",
            female_voice_confirmed=True,
            breath_confirmed=True,
            artifact_free_confirmed=True,
        )
    assert result["status"] == "approved"
