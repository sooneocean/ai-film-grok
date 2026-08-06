from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import final_editorial_review as editorial  # noqa: E402


def test_post_tts_dialogue_contract_requires_suppression() -> None:
    spec = {
        "scenes": [
            {
                "shots": [
                    {
                        "id": "shot01",
                        "dialogue_contracts": [
                            {
                                "lines": [
                                    {
                                        "audio_origin": "post_vo",
                                    }
                                ]
                            }
                        ],
                    }
                ]
            }
        ]
    }
    assert editorial._post_tts_dialogue_shots(spec) == {"shot01"}


def test_editorial_gate_duplicate_dialogue_audio(tmp_path: Path) -> None:
    """Native lane + audible TTS must fail closed (no double-speak ship)."""
    (tmp_path / "out").mkdir()
    (tmp_path / "audio").mkdir()
    (tmp_path / "receipts").mkdir()
    (tmp_path / "out" / "film_final.mp4").write_bytes(b"fake-mp4")
    (tmp_path / "film-spec.json").write_text("{}", encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps({"outputs": {"final_film": {"path": "film_final.mp4"}}}), encoding="utf-8"
    )
    (tmp_path / "audio" / "mix_report.json").write_text(
        json.dumps(
            {
                "native_audio": {
                    "preserved_shots": ["shot01"],
                    "suppressed_for_tts_shots": [],
                    "native_dialogue_shots": ["shot01"],
                    "xor_violations": [],
                    "shot_lanes": {
                        "shot01": {
                            "lane": "native",
                            "tts_mix_gain": 1.0,
                            "caption_clock_only": False,
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    # Avoid full media QA hard-fail on fake bytes — patch analyze path lightly
    import media_qa

    orig = media_qa.analyze_media

    def _ok_media(*_a, **_k):
        return {"ok": True}

    media_qa.analyze_media = _ok_media  # type: ignore[assignment]
    try:
        # cinematic_audit may also fail on empty root — patch
        import cinematic_audit

        def _ok_cine(*_a, **_k):
            return {"ok": True, "issues": []}

        cinematic_audit.audit = _ok_cine  # type: ignore[assignment]
        report = editorial.audit(tmp_path, write=False)
    finally:
        media_qa.analyze_media = orig  # type: ignore[assignment]

    codes = {item.get("code") for item in report.get("issues") or []}
    assert "DUPLICATE_DIALOGUE_AUDIO" in codes
    assert report.get("ok") is False


def test_currentness_detects_final_or_mix_change(tmp_path: Path) -> None:
    (tmp_path / "out").mkdir()
    (tmp_path / "audio").mkdir()
    (tmp_path / "out" / "film_final.mp4").write_bytes(b"one")
    (tmp_path / "audio" / "mix_report.json").write_text("{}", encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps({"outputs": {"final_film": {"path": "film_final.mp4"}}}), encoding="utf-8"
    )
    receipt = {
        "inputs": editorial._inputs(tmp_path, json.loads((tmp_path / "manifest.json").read_text()))
    }
    assert editorial.is_current(tmp_path, receipt)["ok"] is True
    (tmp_path / "audio" / "mix_report.json").write_text('{"changed": true}', encoding="utf-8")
    stale = editorial.is_current(tmp_path, receipt)
    assert stale["stale"] is True
    assert stale["mismatches"] == ["mix_report"]
