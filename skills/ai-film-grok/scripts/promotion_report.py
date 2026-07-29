"""Read-only candidate-to-promotion report for a film workspace.

This report deliberately has no approval or rendering side effects.  It turns
existing receipts into an explicit explanation of why a candidate is, or is
not, ready to be promoted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dailies import _current_items
from quality_evidence import quality_evidence_is_current
from util import read_json, sha256_file, utc_now, write_json

SCHEMA_VERSION = 1


def _root(root: Path | str) -> Path:
    return Path(root).expanduser().resolve()


def _path(root: Path, raw: object) -> Path | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    path = Path(raw).expanduser()
    return path if path.is_absolute() else root / path


def _source_hashes(root: Path) -> dict[str, str | None]:
    paths = {
        "manifest": root / "manifest.json",
        "dailies": root / "receipts" / "dailies.json",
        "final_review": root / "out" / "final-review.json",
        "audio_provenance": root / "receipts" / "audio-provenance.json",
        "subtitle_alignment": root / "receipts" / "subtitle-dialogue-alignment.json",
        "audio_delivery": root / "receipts" / "audio-delivery-report.json",
    }
    return {name: sha256_file(path) if path.is_file() else None for name, path in paths.items()}


def _issue(code: str, layer: str, message: str) -> dict[str, str]:
    return {"code": code, "layer": layer, "message": message}


def _current_dailies(root: Path) -> dict[str, list[dict[str, Any]]]:
    receipt = read_json(root / "receipts" / "dailies.json") or {}
    shots = receipt.get("shots") if isinstance(receipt.get("shots"), dict) else {}
    return {
        str(shot_id): _current_items(items)
        for shot_id, items in shots.items()
        if isinstance(items, list)
    }


def _asset(
    root: Path, shot_id: str, clip: dict[str, Any], dailies: list[dict[str, Any]]
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    media = _path(root, clip.get("path"))
    media_hash = sha256_file(media) if media and media.is_file() else None
    expected_hash = str(clip.get("sha256") or "") or None
    selected = [item for item in dailies if item.get("status") == "select"]
    if not media:
        issues.append(
            _issue("CANDIDATE_MEDIA_MISSING", "candidate", "manifest clip path is missing")
        )
    elif not media.is_file():
        issues.append(
            _issue("CANDIDATE_MEDIA_MISSING", "candidate", "manifest clip file is missing")
        )
    if len(selected) > 1:
        issues.append(
            _issue(
                "DAILIES_SELECT_COUNT", "candidate", "more than one current candidate is selected"
            )
        )
    if selected and media_hash and selected[0].get("media_sha256") != media_hash:
        issues.append(
            _issue(
                "SELECT_MANIFEST_HASH_MISMATCH",
                "candidate",
                "selected candidate differs from current manifest clip",
            )
        )

    qa = clip.get("qa") if isinstance(clip.get("qa"), dict) else {}
    quality = clip.get("quality_gate") if isinstance(clip.get("quality_gate"), dict) else {}
    technical_ok = bool(
        media_hash
        and expected_hash == media_hash
        and qa.get("ok") is True
        and qa.get("decode_ok") is True
        and qa.get("motion_ok") is True
        and quality.get("ok") is True
    )
    if expected_hash and expected_hash != media_hash:
        issues.append(
            _issue(
                "TECHNICAL_EVIDENCE_STALE", "technical", "manifest hash differs from current media"
            )
        )
    elif not technical_ok:
        issues.append(
            _issue(
                "TECHNICAL_QA_MISSING",
                "technical",
                "current media lacks passing decode, motion, or quality QA",
            )
        )

    technical_state = (
        "technical_failed"
        if expected_hash
        and expected_hash != media_hash
        or qa.get("ok") is False
        or quality.get("ok") is False
        else "technical_pending"
        if not technical_ok
        else "passed"
    )

    review = clip.get("shot_review") if isinstance(clip.get("shot_review"), dict) else {}
    visual_ok = bool(
        review.get("approved") is True
        and clip.get("identity_approved") is True
        and clip.get("motion_approved") is True
    )
    if not visual_ok:
        issues.append(
            _issue(
                "VISUAL_REVIEW_MISSING",
                "visual",
                "current clip lacks approved identity, motion, or shot review",
            )
        )
    visual_state = (
        "visual_failed"
        if review.get("approved") is False
        or clip.get("identity_approved") is False
        or clip.get("motion_approved") is False
        else "visual_pending"
        if not visual_ok
        else "passed"
    )

    evidence = clip.get("quality_evidence")
    semantic_ok = bool(
        media and media.is_file() and quality_evidence_is_current(evidence, clip=media)
    )
    if not semantic_ok:
        issues.append(
            _issue(
                "SEMANTIC_EVIDENCE_STALE",
                "semantic",
                "current clip lacks hash-bound continuity and human review evidence",
            )
        )
    semantic_state = (
        "semantic_pending"
        if not isinstance(evidence, dict)
        else "semantic_failed"
        if not semantic_ok
        else "passed"
    )

    integration_ok = bool(
        clip.get("status") == "approved"
        and selected
        and media_hash
        and selected[0].get("media_sha256") == media_hash
    )
    if not integration_ok:
        issues.append(
            _issue(
                "INTEGRATION_BINDING_MISSING",
                "integration",
                "approved manifest clip is not the selected current dailies candidate",
            )
        )
    integration_state = (
        "integration_failed"
        if selected and media_hash and selected[0].get("media_sha256") != media_hash
        else "integration_pending"
        if not integration_ok
        else "passed"
    )

    if not media_hash:
        state = "candidate"
    elif technical_state != "passed":
        state = technical_state
    elif visual_state != "passed":
        state = visual_state
    elif semantic_state != "passed":
        state = semantic_state
    elif integration_state != "passed":
        state = integration_state
    else:
        state = "promotion_eligible"
    return {
        "shot_id": shot_id,
        "kind": "clip",
        "path": str(media) if media else None,
        "sha256": media_hash,
        "state": state,
        "layers": {
            "candidate": bool(media_hash),
            "technical": technical_state,
            "visual": visual_state,
            "semantic": semantic_state,
            "integration": integration_state,
        },
        "issues": issues,
    }


def _experiments(root: Path, known_by_shot: dict[str, set[str]]) -> list[dict[str, Any]]:
    """Report only declared A/B evidence; absence is never treated as approval."""
    path = root / "receipts" / "experiment-a-b.json"
    receipt = read_json(path) if path.is_file() else {}
    rows = receipt.get("experiments") if isinstance(receipt, dict) else []
    if not isinstance(rows, list):
        rows = []
    reported: list[dict[str, Any]] = []
    for index, raw in enumerate(rows):
        row = raw if isinstance(raw, dict) else {}
        category = str(row.get("category") or "unknown")
        shot_id = str(row.get("shot_id") or "")
        baseline = row.get("baseline_sha256")
        candidate = row.get("candidate_sha256")
        conclusion = row.get("human_conclusion")
        valid = (
            shot_id in known_by_shot
            and isinstance(baseline, str)
            and isinstance(candidate, str)
            and baseline != candidate
            and baseline in known_by_shot.get(shot_id, set())
            and candidate in known_by_shot.get(shot_id, set())
            and isinstance(conclusion, str)
            and conclusion.strip()
        )
        reported.append(
            {
                "id": str(row.get("id") or f"experiment-{index + 1}"),
                "category": category,
                "shot_id": shot_id or None,
                "state": "experiment_reviewed" if valid else "experiment_evidence_missing",
                "issues": [
                    _issue(
                        "EXPERIMENT_EVIDENCE_MISSING",
                        "experiment",
                        "A/B baseline, candidate, and human conclusion are required",
                    )
                ]
                if not valid
                else [],
            }
        )
    return reported


def _final(root: Path, manifest: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), dict) else {}
    record = outputs.get("final_film") if isinstance(outputs.get("final_film"), dict) else {}
    path = _path(root, record.get("path"))
    actual_hash = sha256_file(path) if path and path.is_file() else None
    expected_hash = str(record.get("sha256") or "") or None
    issues: list[dict[str, str]] = []
    technical = bool(
        actual_hash
        and actual_hash == expected_hash
        and isinstance(record.get("technical_qa"), dict)
        and record["technical_qa"].get("ok") is True
        and record["technical_qa"].get("decode_ok") is True
        and record["technical_qa"].get("has_audio") is True
    )
    if not actual_hash or actual_hash != expected_hash:
        issues.append(
            _issue(
                "FINAL_HASH_STALE", "technical", "registered final does not match the current file"
            )
        )
    elif not technical:
        issues.append(
            _issue(
                "FINAL_TECHNICAL_QA_MISSING", "technical", "final lacks passing decode and audio QA"
            )
        )

    review = outputs.get("final_review") if isinstance(outputs.get("final_review"), dict) else {}
    review_path = _path(root, review.get("path")) or root / "out" / "final-review.json"
    review_on_disk = read_json(review_path) if review_path.is_file() else {}
    if not isinstance(review_on_disk, dict):
        review_on_disk = {}
    visual = bool(
        review.get("approved") is True
        and review.get("output_sha256") == actual_hash
        and review_on_disk.get("approved") is True
        and review_on_disk.get("output_sha256") == actual_hash
    )
    if not visual:
        issues.append(
            _issue(
                "FINAL_REVIEW_STALE",
                "visual",
                "final review is missing, failed, or bound to another export",
            )
        )
    semantic_sources = (
        "audio_provenance",
        "subtitle_dialogue_alignment",
        "subtitle_cut_boundaries",
    )
    semantic = all(
        isinstance(review_on_disk.get(name), dict) and review_on_disk[name].get("ok") is True
        for name in semantic_sources
    )
    if not semantic:
        issues.append(
            _issue(
                "AUDIO_DUPLICATION_RISK",
                "semantic",
                "final review lacks current audio and subtitle alignment evidence",
            )
        )

    delivery_dir = outputs.get("desktop_dir")
    delivery_copy = None
    delivery_hash = None
    if isinstance(delivery_dir, str) and delivery_dir.strip() and path:
        delivery_copy = Path(delivery_dir).expanduser() / path.name
        delivery_hash = sha256_file(delivery_copy) if delivery_copy.is_file() else None
    delivery_ok = delivery_copy is None or delivery_hash == actual_hash
    if delivery_copy is not None and not delivery_ok:
        issues.append(
            _issue(
                "DELIVERY_HASH_MISMATCH",
                "integration",
                "delivery copy differs from the reviewed final",
            )
        )
    state = (
        "promotion_eligible"
        if technical and visual and semantic and delivery_ok
        else "integration_pending"
    )
    return (
        {
            "path": str(path) if path else None,
            "sha256": actual_hash,
            "state": state,
            "layers": {
                "technical": technical,
                "visual": visual,
                "semantic": semantic,
                "integration": delivery_ok,
            },
            "issues": issues,
        },
        {
            "path": str(delivery_copy) if delivery_copy else None,
            "sha256": delivery_hash,
            "matches_final": delivery_ok,
        },
    )


def build_promotion_report(root: Path | str) -> dict[str, Any]:
    """Build a report from current bytes and receipts without changing project state."""
    base = _root(root)
    manifest = read_json(base / "manifest.json") or {}
    clips = manifest.get("clips") if isinstance(manifest.get("clips"), dict) else {}
    dailies = _current_dailies(base)
    assets = [
        _asset(
            base,
            str(shot_id),
            clip if isinstance(clip, dict) else {},
            dailies.get(str(shot_id), []),
        )
        for shot_id, clip in sorted(clips.items())
    ]
    for shot_id, entries in sorted(dailies.items()):
        if shot_id not in clips:
            assets.append(_asset(base, shot_id, {}, entries))
    final, delivery = _final(base, manifest)
    known_by_shot: dict[str, set[str]] = {}
    for asset in assets:
        if isinstance(asset.get("sha256"), str):
            known_by_shot.setdefault(str(asset["shot_id"]), set()).add(asset["sha256"])
    for shot_id, entries in dailies.items():
        for entry in entries:
            candidate_hash = entry.get("media_sha256")
            if isinstance(candidate_hash, str):
                known_by_shot.setdefault(shot_id, set()).add(candidate_hash)
    experiments = _experiments(base, known_by_shot)
    all_issues = [issue for asset in assets for issue in asset["issues"]] + final["issues"]
    for experiment in experiments:
        all_issues.extend(experiment["issues"])
    priority = (
        "FINAL_HASH_STALE",
        "AUDIO_DUPLICATION_RISK",
        "TECHNICAL_EVIDENCE_STALE",
        "VISUAL_REVIEW_MISSING",
        "SEMANTIC_EVIDENCE_STALE",
    )
    highest = [issue for code in priority for issue in all_issues if issue["code"] == code][:5]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "promotion-report",
        "generated_at": utc_now(),
        "source_hashes": _source_hashes(base),
        "assets": assets,
        "final": final,
        "delivery": delivery,
        "experiments": experiments,
        "summary": {
            "asset_count": len(assets),
            "promotion_eligible_count": sum(
                item["state"] == "promotion_eligible" for item in assets
            ),
            "issue_count": len(all_issues),
            "report_only": True,
        },
        "highest_roi_actions": highest,
    }


def write_promotion_report(root: Path | str, out: Path | str) -> dict[str, Any]:
    """Persist only an explicitly requested report inside the film workspace."""
    base = _root(root)
    destination = Path(out).expanduser()
    if not destination.is_absolute():
        destination = base / destination
    destination = destination.resolve()
    try:
        destination.relative_to(base)
    except ValueError as exc:
        raise ValueError("--out must stay inside the film root") from exc
    report = build_promotion_report(base)
    write_json(destination, report)
    report["report_path"] = str(destination)
    return report
