"""Gate recomputation for film manifests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.film_io import director_notes_path, film_dirs, load_director_notes
from core.paths import record_file_matches
from director_review import (
    SCORECARD_DIMENSIONS,
    open_reshoot_items,
    reshoots_clear,
    scorecard_is_complete_and_passing,
)
from film_spec import FilmSpecError, validate_film_spec
from media_qa import approved_clip_record
from util import require_json as read_json


def recompute_gates(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    style = read_json(root / "style-bible.json") if (root / "style-bible.json").is_file() else {}
    spec = read_json(root / "film-spec.json") if (root / "film-spec.json").is_file() else {}
    spec_error = None
    try:
        shots = validate_film_spec(spec, assign_missing_ids=False)
    except FilmSpecError as exc:
        shots = []
        spec_error = str(exc)
    shot_ids = [shot["id"] for shot in shots]
    broll_ids = [
        str(entry.get("id"))
        for shot in shots
        for entry in (shot.get("dialogue_broll") or [])
        if isinstance(entry, dict) and str(entry.get("id") or "").strip()
    ]
    inventory_ids = shot_ids + broll_ids
    dirs = film_dirs(root)
    stills = manifest.get("stills") or {}
    clips = manifest.get("clips") or {}
    style_reference = (
        style.get("style_reference") if isinstance(style.get("style_reference"), dict) else {}
    )
    style_reference_ok = True
    if style_reference:
        try:
            from assets import style_lock as sl

            style_check = sl.validate_style_lock_bible(style)
            style_reference_ok = not any(
                str(code).startswith("STYLE_REFERENCE_") for code in style_check.get("hard") or []
            )
        except (ImportError, OSError, ValueError):
            style_reference_ok = False

    def _has_current_style_job(record: object) -> bool:
        if not style_reference:
            return True
        evidence = record.get("style_reference_job") if isinstance(record, dict) else None
        return isinstance(evidence, dict) and evidence.get(
            "style_reference_sha256"
        ) == style_reference.get("sha256")

    approved_stills = [
        sid
        for sid, record in stills.items()
        if isinstance(record, dict)
        and record.get("status") == "approved"
        and _has_current_style_job(record)
        and record_file_matches(dirs["keyframes"], record, field=f"still path for {sid}")
    ]
    review_contract = int(manifest.get("review_contract_version") or 1)
    approved_clips = [
        sid
        for sid, record in clips.items()
        if approved_clip_record(record)
        and _has_current_style_job(record)
        and (review_contract < 2 or isinstance(record.get("shot_review"), dict))
        and record_file_matches(dirs["clips"], record, field=f"clip path for {sid}")
    ]
    canonical = [
        path for path in dirs["canonical"].glob("*") if path.is_file() and not path.is_symlink()
    ]
    out_mp4 = [
        path for path in dirs["out"].glob("*.mp4") if path.is_file() and not path.is_symlink()
    ]
    outputs = manifest.get("outputs") or {}
    silent_record = outputs.get("silent_film")
    silent_qa = silent_record.get("technical_qa") if isinstance(silent_record, dict) else None
    assembled = bool(
        record_file_matches(dirs["out"], silent_record, field="silent film path")
        and isinstance(silent_qa, dict)
        and silent_qa.get("ok") is True
        and silent_qa.get("motion_ok") is True
    )
    final_record = outputs.get("final_film")
    final_qa = final_record.get("technical_qa") if isinstance(final_record, dict) else None
    final_file_ok = record_file_matches(dirs["out"], final_record, field="final film path")
    final_technical_ok = bool(
        final_file_ok
        and isinstance(final_qa, dict)
        and final_qa.get("ok") is True
        and final_qa.get("decode_ok") is True
        and final_qa.get("motion_ok") is True
        and final_qa.get("has_audio") is True
    )
    review = outputs.get("final_review")
    screening_evidence = review.get("screening_evidence") if isinstance(review, dict) else {}
    screening_evidence_ok = review_contract < 2 or (
        isinstance(screening_evidence, dict)
        and set(screening_evidence) == set(SCORECARD_DIMENSIONS)
    )
    review_ok = bool(
        isinstance(review, dict)
        and review.get("approved") is True
        and isinstance(final_record, dict)
        and review.get("output_sha256") == final_record.get("sha256")
        and isinstance(review.get("reviewer"), str)
        and review["reviewer"].strip()
        and isinstance(review.get("notes"), str)
        and review["notes"].strip()
        and isinstance(review.get("technical_qa"), dict)
        and review["technical_qa"].get("ok") is True
        and scorecard_is_complete_and_passing(review)
        and screening_evidence_ok
    )
    from delivery_artifact import desktop_delivery_is_current

    desktop_exported = desktop_delivery_is_current(outputs, final_record)
    dnotes = load_director_notes(root)
    open_items = open_reshoot_items(dnotes)
    from anatomy_safety import anatomy_safety_report, requires_anatomy_safety
    from clip_uniqueness import active_clip_reuse_report
    from still_uniqueness import active_still_reuse_report

    uniqueness = active_clip_reuse_report(manifest, required_shot_ids=shot_ids)
    still_uniqueness = active_still_reuse_report(
        manifest,
        required_shot_ids=shot_ids,
        keyframes_dir=dirs["keyframes"],
    )
    anatomy_required = requires_anatomy_safety(root)
    still_anatomy = anatomy_safety_report(manifest, required_shot_ids=shot_ids, kind="stills")
    clip_anatomy = anatomy_safety_report(manifest, required_shot_ids=shot_ids, kind="clips")
    from manifest_truth import preflight_manifest

    manifest_truth = preflight_manifest(root, manifest)
    clips_complete = (
        manifest_truth["ok"]
        and bool(shot_ids)
        and all(sid in approved_clips for sid in shot_ids)
        and uniqueness["ok"]
        and style_reference_ok
    )
    gates = {
        "manifest_current": manifest_truth["ok"],
        "brief": (root / "brief.json").is_file(),
        "style_locked": bool(style.get("locked")) and style_reference_ok,
        "spec": bool(shots) and spec_error is None,
        "canonical": len(canonical) > 0,
        "stills_complete": bool(shot_ids)
        and all(sid in approved_stills for sid in shot_ids)
        and still_uniqueness["ok"],
        "clips_complete": clips_complete,
        "assembled": assembled,
        "reshoots_clear": reshoots_clear(dnotes),
        "final_complete": bool(
            manifest_truth["ok"]
            and still_uniqueness["ok"]
            and clips_complete
            and final_technical_ok
            and review_ok
            and reshoots_clear(dnotes)
        ),
        "desktop_exported": desktop_exported,
    }
    if anatomy_required:
        gates["stills_complete"] = gates["stills_complete"] and still_anatomy["ok"]
        gates["clips_complete"] = gates["clips_complete"] and clip_anatomy["ok"]
        gates["final_complete"] = (
            gates["final_complete"] and still_anatomy["ok"] and clip_anatomy["ok"]
        )
    manifest["gates"] = gates
    manifest["style_locked"] = gates["style_locked"]
    return {
        "shot_ids": inventory_ids,
        "approved_stills": approved_stills,
        "approved_clips": approved_clips,
        "canonical_count": len(canonical),
        "outputs": [str(p) for p in out_mp4],
        "spec_error": spec_error,
        "final_technical_ok": final_technical_ok,
        "final_review_ok": review_ok,
        "style_reference_ok": style_reference_ok,
        "clip_uniqueness": uniqueness,
        "still_uniqueness": still_uniqueness,
        "anatomy_safety": {
            "required": anatomy_required,
            "stills": still_anatomy,
            "clips": clip_anatomy,
        },
        "manifest_truth": manifest_truth,
        "open_reshoots": open_items,
        "open_reshoot_count": len(open_items),
        "director_notes_path": str(director_notes_path(root))
        if director_notes_path(root).is_file()
        else None,
        "gates": gates,
    }
