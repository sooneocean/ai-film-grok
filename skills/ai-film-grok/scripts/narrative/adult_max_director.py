"""Evidence-bearing sensory direction for ``heat_scale=max`` projects.

This module deliberately separates authored intent from verified media.  The
specification can be projected before generation, while the receipt can only
pass after reviewed, hash-bound clips and the final audio/timeline exist.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json, sha256_file, utc_now, write_json


class AdultMaxDirectorError(ValueError):
    pass


_PHASE_DEFAULTS: dict[str, dict[str, Any]] = {
    "setup": {"coverage": "establish", "motion": "approach", "energy": 0.35},
    "foreplay": {"coverage": "escalation", "motion": "reveal", "energy": 0.55},
    "act": {"coverage": "action_progress", "motion": "rhythm", "energy": 0.82},
    "climax": {"coverage": "climax_reaction", "motion": "peak_release", "energy": 1.0},
    "afterglow": {"coverage": "afterglow", "motion": "release", "energy": 0.4},
}


def _shots(spec: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        shot
        for scene in spec.get("scenes") or []
        if isinstance(scene, dict)
        for shot in scene.get("shots") or []
        if isinstance(shot, dict)
    ]


def active(spec: dict[str, Any]) -> bool:
    return str(spec.get("heat_scale") or "").strip().lower() == "max"


def apply_contract(spec: dict[str, Any], shots: list[dict[str, Any]]) -> dict[str, Any]:
    """Project minimum sensory direction into a max spec without touching others."""
    if not active(spec):
        return {"active": False, "projected": []}
    director = spec.get("adult_max_director")
    if not isinstance(director, dict):
        director = {}
        spec["adult_max_director"] = director
    director.setdefault("schema_version", 1)
    director.setdefault("strict", True)
    director.setdefault("require_media_evidence", True)
    director.setdefault("require_human_final_review", True)
    director.setdefault("minimum_av_alignment_score", 90)
    projected: list[str] = []
    for shot in shots:
        phase = str(shot.get("heat_phase") or "setup").strip().lower()
        defaults = _PHASE_DEFAULTS.get(phase)
        if not defaults:
            continue
        cues = shot.get("sensory_cues")
        if not isinstance(cues, dict):
            cues = {}
            shot["sensory_cues"] = cues
        cues.setdefault("visual_coverage", defaults["coverage"])
        cues.setdefault("motion_beat", defaults["motion"])
        cues.setdefault("music_energy", defaults["energy"])
        cues.setdefault("cut_trigger", "visible_change")
        if phase in {"act", "climax"}:
            cues.setdefault("sound_events", ["body_foley", "performance", "music_pulse"])
            cues.setdefault("require_timestamp_evidence", True)
        else:
            cues.setdefault("sound_events", ["ambience", "music_pulse"])
        projected.append(str(shot.get("id") or "?"))
    # A detail insert is a separate coverage need, never a substitute for action progression.
    act_shots = [s for s in shots if str(s.get("heat_phase") or "").lower() == "act"]
    if act_shots and not any(
        (s.get("sensory_cues") or {}).get("visual_coverage") == "detail" for s in act_shots
    ):
        detail = next((s for s in act_shots if s.get("coverage_role") == "detail"), None)
        # A detail may be projected only onto a shot explicitly authored as an
        # insert.  Re-labelling an action beat would hide missing progression.
        if detail is not None:
            detail["sensory_cues"]["visual_coverage"] = "detail"
    return {"active": True, "projected": projected}


def validate_contract(spec: dict[str, Any], shots: list[dict[str, Any]]) -> dict[str, Any]:
    if not active(spec):
        return {"ok": True, "active": False, "codes": []}
    codes: list[str] = []
    act = [s for s in shots if str(s.get("heat_phase") or "").lower() == "act"]
    climax = [s for s in shots if str(s.get("heat_phase") or "").lower() == "climax"]
    for shot in act + climax:
        cues = shot.get("sensory_cues") if isinstance(shot.get("sensory_cues"), dict) else {}
        missing = [
            key
            for key in ("visual_coverage", "motion_beat", "sound_events", "cut_trigger")
            if not cues.get(key)
        ]
        if missing:
            codes.append(
                f"ADULT_MAX_SENSORY_CUES_MISSING:{shot.get('id') or '?'}:{','.join(missing)}"
            )
    if act and not any(
        (s.get("sensory_cues") or {}).get("visual_coverage") == "detail" for s in act
    ):
        codes.append("ADULT_MAX_DETAIL_COVERAGE_MISSING")
    if climax and not any(
        (s.get("sensory_cues") or {}).get("visual_coverage") == "climax_reaction" for s in climax
    ):
        codes.append("ADULT_MAX_CLIMAX_REACTION_MISSING")
    return {"ok": not codes, "active": True, "codes": codes}


def receipt_path(root: Path | str) -> Path:
    return Path(root).expanduser().resolve() / "receipts" / "adult-max" / "sensory-evidence.json"


def build_evidence(root: Path | str, *, write: bool = True) -> dict[str, Any]:
    """Build a current-media receipt.  It never manufactures review approval."""
    base = Path(root).expanduser().resolve()
    spec = read_json(base / "film-spec.json") or {}
    if not active(spec):
        return {"ok": True, "active": False, "codes": [], "root": str(base)}
    shots = _shots(spec)
    contract = validate_contract(spec, shots)
    manifest = read_json(base / "manifest.json") or {}
    clips = manifest.get("clips") if isinstance(manifest.get("clips"), dict) else {}
    sound_plan = spec.get("sound_plan") if isinstance(spec.get("sound_plan"), dict) else {}
    sound_events = sound_plan.get("events") if isinstance(sound_plan.get("events"), list) else []
    codes = list(contract["codes"])
    evidence_shots: list[dict[str, Any]] = []
    for shot in shots:
        if str(shot.get("heat_phase") or "").lower() not in {"act", "climax"}:
            continue
        sid = str(shot.get("id") or "")
        clip = clips.get(sid) if isinstance(clips.get(sid), dict) else {}
        source = Path(str(clip.get("path") or "")).expanduser()
        review = clip.get("shot_review") if isinstance(clip.get("shot_review"), dict) else {}
        review_path = Path(str(review.get("path") or "")).expanduser()
        item: dict[str, Any] = {"shot_id": sid, "ok": False}
        if not source.is_file():
            codes.append(f"ADULT_MAX_MEDIA_MISSING:{sid}")
        elif not _current_quality_evidence(base, clip, source):
            codes.append(f"ADULT_MAX_QUALITY_EVIDENCE_MISSING:{sid}")
        elif not review_path.is_file():
            codes.append(f"ADULT_MAX_REVIEW_MISSING:{sid}")
        else:
            packet = read_json(review_path) or {}
            source_rec = packet.get("source") if isinstance(packet.get("source"), dict) else {}
            coitus = (
                (packet.get("evidence") or {}).get("coitus")
                if isinstance(packet.get("evidence"), dict)
                else None
            )
            performance = (
                packet.get("adult_performance_evidence")
                if isinstance(packet.get("adult_performance_evidence"), dict)
                else None
            )
            valid = True
            source_sha = sha256_file(source)
            if packet.get("approved") is not True or source_rec.get("sha256") != source_sha:
                codes.append(f"ADULT_MAX_REVIEW_STALE:{sid}")
                valid = False
            if not isinstance(coitus, dict) or coitus.get("timestamp_sec") is None:
                codes.append(f"ADULT_MAX_TIMESTAMP_EVIDENCE_MISSING:{sid}")
                valid = False
            if not performance:
                codes.append(f"ADULT_MAX_PERFORMANCE_EVIDENCE_MISSING:{sid}")
                valid = False
            elif (
                performance.get("clip_sha256") != source_sha
                or performance.get("coitus_timestamp_sec") != coitus.get("timestamp_sec")
                or performance.get("human_review_required") is not True
            ):
                codes.append(f"ADULT_MAX_PERFORMANCE_EVIDENCE_STALE:{sid}")
                valid = False
            if not isinstance(packet.get("reviewer"), str) or not packet["reviewer"].strip():
                codes.append(f"ADULT_MAX_HUMAN_REVIEW_MISSING:{sid}")
                valid = False
            if valid:
                item.update(
                    {
                        "ok": True,
                        "clip_sha256": source_sha,
                        "review_sha256": sha256_file(review_path),
                        "timestamp_sec": coitus["timestamp_sec"],
                    }
                )
        evidence_shots.append(item)
        if not any(
            isinstance(event, dict)
            and event.get("type") == "sfx_accent"
            and event.get("sex_sfx") is True
            and str(event.get("shot_id") or "") == sid
            for event in sound_events
        ):
            codes.append(f"ADULT_MAX_FOLEY_MISSING:{sid}")
    alignment_path = base / "receipts" / "audio-visual-alignment.json"
    alignment = read_json(alignment_path) or {}
    minimum = int((spec.get("adult_max_director") or {}).get("minimum_av_alignment_score") or 90)
    if not alignment_path.is_file():
        codes.append("ADULT_MAX_AV_ALIGNMENT_MISSING")
    elif int(alignment.get("av_alignment_score") or 0) < minimum:
        codes.append("ADULT_MAX_AV_ALIGNMENT_LOW")
    mix_path, mix_ok = _verified_mix(base)
    if not mix_ok:
        codes.append("ADULT_MAX_MIX_EVIDENCE_MISSING")
    result = {
        "schema_version": 1,
        "kind": "adult-max-sensory-evidence",
        "created_at": utc_now(),
        "root": str(base),
        "active": True,
        "ok": not codes,
        "codes": codes,
        "contract": contract,
        "shots": evidence_shots,
        "audio_visual": {
            "path": str(alignment_path),
            "score": alignment.get("av_alignment_score"),
            "minimum": minimum,
        },
        "mix": {"path": str(mix_path) if mix_path else None, "ok": mix_ok},
    }
    if write:
        path = receipt_path(base)
        write_json(path, result)
        result["path"] = str(path)
        result["sha256"] = sha256_file(path)
    return result


def _current_quality_evidence(root: Path, record: dict[str, Any], source: Path) -> bool:
    """Reuse the delivery contract; a sensory approval cannot bypass clip QA."""
    evidence = record.get("quality_evidence") if isinstance(record, dict) else None
    if not isinstance(evidence, dict):
        return False
    try:
        from quality_evidence import quality_evidence_is_current

        return quality_evidence_is_current(evidence, clip=source)
    except (OSError, ValueError):
        return False


def _verified_mix(root: Path) -> tuple[Path | None, bool]:
    """Accept only the renderer's hash-bound mix report and local artifacts."""
    root = root.expanduser().resolve()
    report_path = root / "audio" / "mix_report.json"
    if not report_path.is_file():
        return None, False
    report = read_json(report_path) or {}
    artifacts = report.get("artifacts") if isinstance(report.get("artifacts"), dict) else {}
    for name in ("bgm", "sfx", "mixed"):
        item = artifacts.get(name) if isinstance(artifacts, dict) else None
        path = Path(str((item or {}).get("path") or "")).expanduser()
        if not path.is_file() or not str((item or {}).get("sha256") or ""):
            return report_path, False
        try:
            path.resolve().relative_to(root)
        except ValueError:
            return report_path, False
        if sha256_file(path) != item["sha256"]:
            return report_path, False
    return report_path, True
