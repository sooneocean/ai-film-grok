from __future__ import annotations

import sys
from argparse import Namespace
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from quality_evidence import (  # noqa: E402
    QualityEvidenceError,
    build_shot_quality_evidence,
    quality_evidence_is_current,
)
from util import sha256_file  # noqa: E402


def test_quality_status_cli_exposes_new_contract(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from aifilm_grok import main

    assert main(["quality-status", "--root", str(tmp_path)]) == 0
    assert '"kind":"quality-contract-status"' in capsys.readouterr().out


def _qa(*, ok: bool = True) -> dict[str, object]:
    return {
        "ok": ok,
        "decode_ok": ok,
        "motion_ok": ok,
        "width": 720,
        "height": 1280,
        "duration_sec": 5.0,
        "motion_score": 4.0,
        "motion_continuity": 1.0,
    }


def _review(clip: Path, review: Path) -> dict[str, object]:
    review.write_text(
        '{"approved":true,"continuity_packet":{"ok":true,"neighbours":{},"reviewed_clip_sha256":"'
        + sha256_file(clip)
        + '"}}',
        encoding="utf-8",
    )
    return {"path": str(review), "sha256": None}


def _provider(clip: Path) -> dict[str, object]:
    return {"ok": True, "output_sha256": sha256_file(clip)}


def test_quality_evidence_binds_the_exact_clip_and_review(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"approved motion")
    review = tmp_path / "review.json"
    review_data = _review(clip, review)

    evidence = build_shot_quality_evidence(
        tmp_path,
        shot_id="s001",
        clip=clip,
        qa=_qa(),
        source_endpoint="image_to_video",
        identity_approved=True,
        motion_approved=True,
        review=review_data,
        uniqueness={"sha256": sha256_file(clip), "dhashes": ["a"]},
        continuity={"ok": True},
        provider=_provider(clip),
    )

    assert evidence["ok"] is True
    assert quality_evidence_is_current(evidence, clip=clip) is True
    clip.write_bytes(b"replaced media")
    assert quality_evidence_is_current(evidence, clip=clip) is False


def test_quality_evidence_fails_closed_for_missing_human_review(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"motion")

    with pytest.raises(QualityEvidenceError, match="human review"):
        build_shot_quality_evidence(
            tmp_path,
            shot_id="s001",
            clip=clip,
            qa=_qa(),
            source_endpoint="image_to_video",
            identity_approved=True,
            motion_approved=True,
            review=None,
            uniqueness={"sha256": sha256_file(clip), "dhashes": ["a"]},
            continuity={"ok": True},
            provider=_provider(clip),
        )


def test_quality_evidence_fails_closed_for_static_or_unfingerprinted_clip(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"motion")
    review = tmp_path / "review.json"
    review_data = _review(clip, review)

    with pytest.raises(QualityEvidenceError, match="motion QA"):
        build_shot_quality_evidence(
            tmp_path,
            shot_id="s001",
            clip=clip,
            qa=_qa(ok=False),
            source_endpoint="image_to_video",
            identity_approved=True,
            motion_approved=True,
            review=review_data,
            uniqueness={"sha256": "x", "dhashes": ["a"]},
            continuity={"ok": True},
            provider=_provider(clip),
        )
    with pytest.raises(QualityEvidenceError, match="fingerprint"):
        build_shot_quality_evidence(
            tmp_path,
            shot_id="s001",
            clip=clip,
            qa=_qa(),
            source_endpoint="image_to_video",
            identity_approved=True,
            motion_approved=True,
            review=review_data,
            uniqueness=None,
            continuity={"ok": True},
            provider=_provider(clip),
        )


def test_quality_evidence_becomes_stale_when_review_receipt_changes(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"motion")
    review = tmp_path / "review.json"
    evidence = build_shot_quality_evidence(
        tmp_path,
        shot_id="s001",
        clip=clip,
        qa=_qa(),
        source_endpoint="image_to_video",
        identity_approved=True,
        motion_approved=True,
        review=_review(clip, review),
        uniqueness={"sha256": sha256_file(clip), "dhashes": ["a"]},
        continuity={"ok": True},
        provider=_provider(clip),
    )
    review.write_text('{"approved":false}', encoding="utf-8")

    assert quality_evidence_is_current(evidence, clip=clip) is False


def test_register_final_rejects_current_contract_without_approved_shot_evidence(
    tmp_path: Path,
) -> None:
    from aifilm_grok import FilmError, cmd_register_final

    (tmp_path / "manifest.json").write_text(
        '{"quality_evidence_contract_version":1,"clips":{}}', encoding="utf-8"
    )
    with pytest.raises(FilmError, match="per-shot quality evidence"):
        cmd_register_final(
            Namespace(
                root=str(tmp_path),
                source=str(tmp_path / "final.mp4"),
                out_name=None,
                post_engine=None,
                allow_static=False,
            )
        )
