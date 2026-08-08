#!/usr/bin/env python3
"""Fail-closed cinematic coherence audit for an ai-film-grok workspace.

This is deliberately a planning and evidence gate, not a taste-scoring model.
It turns already-authored shot metadata into concrete, repairable failures before
new media is bought or a cut is approved.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from continuity import (
    lint_frame_chain,
    lint_meaningful_motion,
    lint_production_consistency,
    lint_vo_motion_link,
)
from dramatic_meaning import lint_dramatic_meaning
from framing_lint import lint_composition_rules
from util import read_json, sha256_file, utc_now, write_json

AUDIT_VERSION = 1
RECEIPT_RELATIVE_PATH = Path("receipts/cinematic-audit.json")
_COVERAGE_MODES = frozenset({"reaction", "action_cover", "silence"})
_DIALOGUE_MODES = frozenset({"on_camera", "off_camera"})


def _shots(spec: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        shot
        for scene in spec.get("scenes") or []
        if isinstance(scene, dict)
        for shot in scene.get("shots") or []
        if isinstance(shot, dict)
    ]


def _issue(code: str, message: str, shot_ids: list[str] | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "severity": "error",
        "message": message,
        "shot_ids": shot_ids or [],
    }


def _coverage_issues(shots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    dialogue = [shot for shot in shots if str(shot.get("screen_mode") or "") in _DIALOGUE_MODES]
    if not dialogue:
        return issues
    coverage = [shot for shot in shots if str(shot.get("screen_mode") or "") in _COVERAGE_MODES]
    coverage_beats = {str(shot.get("beat_id") or "").strip() for shot in coverage}
    embedded: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for shot in dialogue:
        shot_id = str(shot.get("id") or "")
        try:
            from dialogue_broll import validate_dialogue_broll

            embedded.extend(
                (shot, entry) for entry in validate_dialogue_broll(shot, shot_id=shot_id)
            )
        except Exception:  # noqa: BLE001
            issues.append(
                _issue(
                    "DIALOGUE_BROLL_INVALID",
                    f"{shot_id} dialogue_broll cannot count as coverage until its full contract validates",
                    [shot_id],
                )
            )
    coverage_beats.update(
        str(shot.get("beat_id") or shot.get("dialogue_line_id") or shot.get("id") or "").strip()
        for shot, _ in embedded
    )
    for shot in dialogue:
        beat = str(
            shot.get("beat_id") or shot.get("dialogue_line_id") or shot.get("id") or ""
        ).strip()
        if beat and beat not in coverage_beats:
            issues.append(
                _issue(
                    "DIALOGUE_BEAT_COVERAGE_MISSING",
                    f"dialogue beat {beat} needs reaction, action_cover, or silence coverage",
                    [str(shot.get("id") or beat)],
                )
            )
    total = sum(float(shot.get("duration_sec") or 0) for shot in shots)
    covered = sum(float(shot.get("duration_sec") or 0) for shot in coverage) + sum(
        max(0.0, float(entry.get("end_sec") or 0) - float(entry.get("start_sec") or 0))
        for _, entry in embedded
    )
    if total > 0 and covered / total < 0.20:
        issues.append(
            _issue(
                "DIALOGUE_COVERAGE_RATIO_LOW",
                "dialogue scenes need at least 20% reaction/action/silence coverage",
                [str(shot.get("id") or "") for shot in dialogue],
            )
        )
    if total > 0 and covered / total > 0.40:
        issues.append(
            _issue(
                "DIALOGUE_COVERAGE_RATIO_HIGH",
                "dialogue coverage exceeds 40%; preserve at least 60% dramatic A-roll",
                [str(shot.get("id") or "") for shot in coverage],
            )
        )
    return issues


def _performance_issues(shots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for shot in shots:
        sid = str(shot.get("id") or "<unknown>")
        dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
        function = str(shot.get("dramatic_function") or "").strip().lower()
        if function in {"hook", "approach", "action"} and not (
            str(shot.get("performance_delta") or "").strip()
            or str(dsl.get("visible_change") or "").strip()
        ):
            issues.append(
                _issue(
                    "PERFORMANCE_DELTA_MISSING",
                    "story-driving shot needs a visible performance_delta or visible_change; story_beat alone is intent, not evidence",
                    [sid],
                )
            )
    return issues


def audit(
    root: Path | str,
    *,
    spec: dict[str, Any] | None = None,
    graph: dict[str, Any] | None = None,
    require_authored_contract: bool = False,
    require_clip_evidence: bool = False,
    require_media_evidence: bool = False,
) -> dict[str, Any]:
    base = Path(root).expanduser().resolve()
    source = spec if spec is not None else read_json(base / "film-spec.json")
    if not isinstance(source, dict):
        issues = [_issue("FILM_SPEC_MISSING", "film-spec.json is required")]
        return {
            "ok": False,
            "version": AUDIT_VERSION,
            "issues": issues,
            "blocking_codes": ["FILM_SPEC_MISSING"],
        }
    shots = _shots(source)
    if not shots:
        issues = [_issue("SHOTS_MISSING", "at least one authored shot is required")]
        return {
            "ok": False,
            "version": AUDIT_VERSION,
            "issues": issues,
            "blocking_codes": ["SHOTS_MISSING"],
        }
    intents = (
        source.get("transition_intents")
        if isinstance(source.get("transition_intents"), list)
        else None
    )
    reports = [
        lint_vo_motion_link(shots, transition_intents=intents),
        lint_meaningful_motion(shots),
        lint_frame_chain(shots, transition_intents=intents),
        lint_production_consistency(shots, bible=source, spec=source),
        lint_composition_rules(shots),
    ]
    issues: list[dict[str, Any]] = []
    for report in reports:
        for item in report.get("issues") or []:
            issues.append({**item, "severity": "error"})
    issues.extend(_coverage_issues(shots))
    issues.extend(_performance_issues(shots))
    # Temple-AV meaning stack: shot world-change, motion purpose, dialogue purpose, arc stack.
    # write-spec production path always fail-closes on meaning issues.
    meaning = lint_dramatic_meaning(source, shots=shots, graph=graph)
    for item in meaning.get("issues") or []:
        if isinstance(item, dict):
            issues.append({**item, "severity": "error"})
    if require_authored_contract:
        from creative_quality import validate_premium_vertical

        contract_graph = graph if graph is not None else read_json(base / "drama-graph.json") or {}
        creative = validate_premium_vertical(base, graph=contract_graph, spec=source)
        for item in creative.get("errors") or []:
            issues.append(
                _issue(
                    "CREATIVE_CONTRACT_" + str(item.get("code") or "INVALID"),
                    str(item.get("message") or "creative contract is incomplete"),
                )
            )
    manifest_hash = sha256_file(base / "manifest.json") if (base / "manifest.json").is_file() else None
    final_path = base / "out" / "film_final.mp4"
    final_hash = sha256_file(final_path) if final_path.is_file() else None
    if require_clip_evidence or require_media_evidence:
        manifest = read_json(base / "manifest.json") or {}
        clips = manifest.get("clips") if isinstance(manifest, dict) else None
        if not isinstance(clips, dict) or not clips:
            issues.append(
                _issue("CLIP_EVIDENCE_MISSING", "approved clip manifest evidence is required")
            )
        else:
            from media_qa import analyze_media, approved_clip_record

            invalid: list[str] = []
            for shot_id, record in clips.items():
                path = Path(str(record.get("path") or "")) if isinstance(record, dict) else Path()
                current = analyze_media(path, require_audio=False, require_motion=True)
                if (
                    not approved_clip_record(record)
                    or not path.is_file()
                    or sha256_file(path) != (record.get("sha256") if isinstance(record, dict) else None)
                    or not current.get("ok")
                ):
                    invalid.append(str(shot_id))
            if invalid:
                issues.append(
                    _issue(
                        "CLIP_EVIDENCE_INVALID",
                        "every clip must have current approved media evidence",
                        invalid,
                    )
                )
    if require_media_evidence:
        if final_hash is None:
            issues.append(
                _issue("FINAL_MEDIA_MISSING", "out/film_final.mp4 is required for final approval")
            )
        else:
            try:
                from media_qa import analyze_media

                technical = analyze_media(final_path, require_audio=True, require_motion=True)
                if not technical.get("ok"):
                    issues.append(
                        _issue(
                            "FINAL_MEDIA_QA_FAILED", "final MP4 did not pass decode/audio/motion QA"
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                issues.append(
                    _issue("FINAL_MEDIA_QA_FAILED", f"final MP4 cannot be verified: {exc}")
                )
    return {
        "ok": not issues,
        "kind": "cinematic-audit",
        "version": AUDIT_VERSION,
        "created_at": utc_now(),
        "inputs": {
            "film_spec_sha256": sha256_file(base / "film-spec.json") if spec is None else None,
            "manifest_sha256": manifest_hash,
            "final_mp4_sha256": final_hash,
        },
        "checked": {"shots": len(shots), "scenes": len(source.get("scenes") or [])},
        "issues": issues,
        "blocking_codes": sorted({str(item.get("code")) for item in issues}),
    }


def write_audit(
    root: Path | str,
    *,
    require_authored_contract: bool = False,
    require_clip_evidence: bool = False,
    require_media_evidence: bool = False,
) -> dict[str, Any]:
    base = Path(root).expanduser().resolve()
    report = audit(
        base,
        require_authored_contract=require_authored_contract,
        require_clip_evidence=require_clip_evidence,
        require_media_evidence=require_media_evidence,
    )
    destination = base / RECEIPT_RELATIVE_PATH
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_json(destination, report)
    report["path"] = str(destination)
    return report


def current_audit(root: Path | str) -> dict[str, Any]:
    base = Path(root).expanduser().resolve()
    report = read_json(base / RECEIPT_RELATIVE_PATH)
    if not isinstance(report, dict):
        return {"ok": False, "blocking_codes": ["CINEMATIC_AUDIT_MISSING"]}
    def _hash(name: Path) -> str | None:
        return sha256_file(name) if name.is_file() else None

    inputs = report.get("inputs", {})
    if (
        report.get("version") != AUDIT_VERSION
        or inputs.get("film_spec_sha256") != _hash(base / "film-spec.json")
        or inputs.get("manifest_sha256") != _hash(base / "manifest.json")
        or inputs.get("final_mp4_sha256") != _hash(base / "out" / "film_final.mp4")
    ):
        return {"ok": False, "blocking_codes": ["CINEMATIC_AUDIT_STALE"]}
    return report
