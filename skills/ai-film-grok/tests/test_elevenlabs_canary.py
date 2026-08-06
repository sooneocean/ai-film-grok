from __future__ import annotations

import json

import elevenlabs_canary as canary
import pytest


def test_canary_requires_explicit_cost_cap(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    with pytest.raises(canary.ElevenLabsCanaryError, match="MAX_PAID_CALLS_2"):
        canary.run_canary(
            tmp_path,
            zh_voice="abcdefgh",
            ja_voice="ijklmnop",
            model="eleven_multilingual_v2",
            confirm_cost=True,
            max_paid_calls=1,
        )


def test_canary_blocks_without_key_and_never_calls_network(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.setattr(canary, "_request", lambda *args, **kwargs: pytest.fail("network called"))
    result = canary.run_canary(
        tmp_path,
        zh_voice="abcdefgh",
        ja_voice="ijklmnop",
        model="eleven_multilingual_v2",
        confirm_cost=True,
        max_paid_calls=2,
    )
    assert result["status"] == "blocked"
    receipt = json.loads((tmp_path / "receipts/elevenlabs-canary/receipt.json").read_text())
    assert receipt["paid_calls_attempted"] == 0
    assert "test-key" not in json.dumps(receipt)


def test_candidate_needs_human_review_before_ready(tmp_path) -> None:
    result = {
        "language": "zh",
        "voice_id": "abcdefgh",
        "model": "eleven_multilingual_v2",
        "sha256": "a" * 64,
        "verified_at": "2026-07-29T00:00:00Z",
    }
    canary._upsert_candidate(tmp_path, result)
    catalog = json.loads((tmp_path / "receipts/voice-armory/elevenlabs.json").read_text())
    entry = catalog["entries"][0]
    assert entry["status"] == "candidate"
    assert entry["forbidden_use"] == "zh_narration"
    approved = canary.review_candidate(tmp_path, language="zh", decision="approve")
    assert approved["status"] == "ready"
