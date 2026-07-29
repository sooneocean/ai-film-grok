from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from promotion_report import build_promotion_report  # noqa: E402
from quality_evidence import build_shot_quality_evidence  # noqa: E402
from util import sha256_file  # noqa: E402


def _qa() -> dict[str, object]:
    return {"ok": True, "decode_ok": True, "motion_ok": True, "has_audio": True}


def _approved_asset(root: Path) -> dict[str, object]:
    clip = root / "clips" / "s001.mp4"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"current approved motion")
    review = root / "review-s001.json"
    review.write_text(
        json.dumps(
            {
                "approved": True,
                "continuity_packet": {
                    "ok": True,
                    "neighbours": {},
                    "reviewed_clip_sha256": sha256_file(clip),
                },
            }
        ),
        encoding="utf-8",
    )
    evidence = build_shot_quality_evidence(
        root,
        shot_id="s001",
        clip=clip,
        qa=_qa(),
        source_endpoint="image_to_video",
        identity_approved=True,
        motion_approved=True,
        review={"path": str(review)},
        uniqueness={"sha256": sha256_file(clip), "dhashes": ["1"]},
        continuity={"ok": True},
        provider={"ok": True, "output_sha256": sha256_file(clip)},
    )
    return {
        "path": "clips/s001.mp4",
        "sha256": sha256_file(clip),
        "status": "approved",
        "qa": _qa(),
        "quality_gate": {"ok": True},
        "identity_approved": True,
        "motion_approved": True,
        "shot_review": {"approved": True},
        "quality_evidence": evidence,
    }


def _write_manifest(root: Path, *, clip: dict[str, object], final_bytes: bytes = b"final") -> None:
    out = root / "out"
    out.mkdir(exist_ok=True)
    final = out / "film_final.mp4"
    final.write_bytes(final_bytes)
    final_hash = sha256_file(final)
    final_review = {
        "approved": True,
        "output_sha256": final_hash,
        "audio_provenance": {"ok": True},
        "subtitle_dialogue_alignment": {"ok": True},
        "subtitle_cut_boundaries": {"ok": True},
    }
    (out / "final-review.json").write_text(json.dumps(final_review), encoding="utf-8")
    manifest = {
        "clips": {"s001": clip},
        "outputs": {
            "final_film": {
                "path": "out/film_final.mp4",
                "sha256": final_hash,
                "technical_qa": _qa(),
            },
            "final_review": {**final_review, "path": "out/final-review.json"},
        },
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "receipts").mkdir(exist_ok=True)
    (root / "receipts" / "dailies.json").write_text(
        json.dumps(
            {
                "shots": {
                    "s001": [
                        {
                            "candidate": str(root / "clips" / "s001.mp4"),
                            "media_sha256": clip["sha256"],
                            "status": "select",
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )


def test_report_is_read_only_and_identifies_an_eligible_asset(tmp_path: Path) -> None:
    clip = _approved_asset(tmp_path)
    _write_manifest(tmp_path, clip=clip)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}

    report = build_promotion_report(tmp_path)

    after = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert before == after
    assert report["summary"]["report_only"] is True
    assert report["assets"][0]["state"] == "promotion_eligible"
    assert report["final"]["state"] == "promotion_eligible"


def test_report_rejects_stale_asset_evidence_after_media_replacement(tmp_path: Path) -> None:
    clip = _approved_asset(tmp_path)
    _write_manifest(tmp_path, clip=clip)
    (tmp_path / "clips" / "s001.mp4").write_bytes(b"replacement")

    asset = build_promotion_report(tmp_path)["assets"][0]

    assert asset["state"] == "technical_failed"
    assert {issue["code"] for issue in asset["issues"]} >= {
        "TECHNICAL_EVIDENCE_STALE",
        "SEMANTIC_EVIDENCE_STALE",
    }


def test_report_detects_final_delivery_hash_mismatch(tmp_path: Path) -> None:
    clip = _approved_asset(tmp_path)
    _write_manifest(tmp_path, clip=clip)
    delivered = tmp_path / "delivery"
    delivered.mkdir()
    (delivered / "film_final.mp4").write_bytes(b"wrong export")
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    manifest["outputs"]["desktop_dir"] = str(delivered)
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    report = build_promotion_report(tmp_path)

    assert report["delivery"]["matches_final"] is False
    assert "DELIVERY_HASH_MISMATCH" in {issue["code"] for issue in report["final"]["issues"]}


def test_cli_only_writes_when_out_is_explicit_and_keeps_it_in_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from aifilm_grok import main

    clip = _approved_asset(tmp_path)
    _write_manifest(tmp_path, clip=clip)
    assert main(["promotion-report", "--root", str(tmp_path)]) == 0
    assert not list(tmp_path.glob("**/promotion-report.json"))
    assert json.loads(capsys.readouterr().out)["kind"] == "promotion-report"

    target = tmp_path / "reports" / "promotion-report.json"
    assert main(["promotion-report", "--root", str(tmp_path), "--out", str(target)]) == 0
    assert target.is_file()
    assert (
        main(
            [
                "promotion-report",
                "--root",
                str(tmp_path),
                "--out",
                str(tmp_path.parent / "nope.json"),
            ]
        )
        == 2
    )
    assert "inside the film root" in capsys.readouterr().out


def test_status_surfaces_report_only_promotion_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from aifilm_grok import main

    clip = _approved_asset(tmp_path)
    _write_manifest(tmp_path, clip=clip)

    assert main(["status", "--root", str(tmp_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["promotion_report"]["report_only"] is True
    assert payload["promotion_report"]["final_state"] == "promotion_eligible"
