"""Story structure validation — weak scenes must not burn expensive media.

Film Production OS W1: validate narrative function before visual generation.
Does not replace story_quality scoring; adds structural flags + optional hard gate.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json

CODE_NO_PROTAGONIST_GOAL = "STORY_NO_PROTAGONIST_GOAL"
CODE_NO_OPPOSITION = "STORY_NO_OPPOSITION"
CODE_NO_STAKES = "STORY_NO_STAKES"
CODE_SCENE_NO_TURN = "SCENE_NO_NARRATIVE_TURN"
CODE_SCENE_REMOVABLE = "SCENE_POSSIBLY_REMOVABLE"
CODE_BEAT_MISSING = "BEAT_LAYER_MISSING"
CODE_SHOTS_WITHOUT_BEAT = "SHOTS_WITHOUT_BEAT"
CODE_ARC_TOO_SHORT = "EMOTIONAL_ARC_TOO_SHORT"


def _text(value: object) -> str:
    return str(value or "").strip()


def _is_blank(value: object) -> bool:
    t = _text(value).lower()
    return t in {"", "todo", "tbd", "n/a", "na", "needs_authoring", "待定", "待填写"}


def _story_blob(graph: dict[str, Any], spec: dict[str, Any] | None) -> dict[str, Any]:
    story = graph.get("story") if isinstance(graph.get("story"), dict) else {}
    if story:
        return story
    if isinstance(spec, dict):
        di = spec.get("director_intent") if isinstance(spec.get("director_intent"), dict) else {}
        return {
            "logline": di.get("logline") or spec.get("description"),
            "protagonist_goal": di.get("protagonist_want") or di.get("protagonist_goal"),
            "opposition": di.get("opposition") or story.get("opposition"),
            "stakes": di.get("stakes"),
            "climax_choice": di.get("climax_choice"),
            "ending_hook": di.get("ending_hook"),
            "emotional_arc": di.get("emotional_arc") or [],
        }
    return {}


def _iter_scenes(graph: dict[str, Any], spec: dict[str, Any] | None) -> list[dict[str, Any]]:
    scenes: list[dict[str, Any]] = []
    for ep in graph.get("episodes") or []:
        if not isinstance(ep, dict):
            continue
        for sc in ep.get("scenes") or []:
            if isinstance(sc, dict):
                scenes.append(sc)
    if scenes:
        return scenes
    if isinstance(spec, dict):
        for sc in spec.get("scenes") or []:
            if isinstance(sc, dict):
                scenes.append(sc)
    return scenes


def _scene_has_turn(scene: dict[str, Any]) -> bool:
    for key in (
        "scene_turn",
        "dramatic_goal",
        "conflict",
        "summary",
        "title",
    ):
        val = scene.get(key)
        if isinstance(val, dict):
            if any(not _is_blank(v) for v in val.values()):
                return True
        elif not _is_blank(val):
            return True
    board = scene.get("director_board")
    if isinstance(board, dict):
        for key in ("emotional_turn", "audience_question", "coverage_strategy"):
            if not _is_blank(board.get(key)):
                return True
    beats = scene.get("beats") if isinstance(scene.get("beats"), list) else []
    if beats:
        return True
    shots = scene.get("shots") if isinstance(scene.get("shots"), list) else []
    return len(shots) >= 2


def _beats_in_scene(scene: dict[str, Any]) -> list[dict[str, Any]]:
    raw = scene.get("beats")
    if isinstance(raw, list):
        return [b for b in raw if isinstance(b, dict)]
    return []


def _shots_in_scene(scene: dict[str, Any]) -> list[dict[str, Any]]:
    shots: list[dict[str, Any]] = []
    for beat in _beats_in_scene(scene):
        for sh in beat.get("shots") or []:
            if isinstance(sh, dict):
                shots.append(sh)
    if shots:
        return shots
    for sh in scene.get("shots") or []:
        if isinstance(sh, dict):
            shots.append(sh)
    return shots


def validate_story_structure(
    graph: dict[str, Any] | None = None,
    *,
    spec: dict[str, Any] | None = None,
    strict: bool = False,
    require_beats: bool = True,
) -> dict[str, Any]:
    """Validate story structure for production readiness.

    Returns ok/issues/flags. When strict=True, structural codes block (ok=False).
    Weak scenes are always flagged so expensive media can be skipped.
    """
    graph = graph if isinstance(graph, dict) else {}
    story = _story_blob(graph, spec)
    issues: list[dict[str, Any]] = []
    flags: list[dict[str, Any]] = []

    def add(code: str, message: str, *, severity: str = "error", ref: str = "") -> None:
        item = {"code": code, "severity": severity, "message": message}
        if ref:
            item["ref"] = ref
        if severity == "error":
            issues.append(item)
        else:
            flags.append(item)

    if _is_blank(story.get("protagonist_goal")) and _is_blank(story.get("protagonist_want")):
        add(
            CODE_NO_PROTAGONIST_GOAL,
            "protagonist has no clear goal (story.protagonist_goal / director_intent.protagonist_want)",
            severity="error" if strict else "warning",
            ref="story.protagonist_goal",
        )
    if _is_blank(story.get("opposition")):
        add(
            CODE_NO_OPPOSITION,
            "no meaningful resistance / opposition authored",
            severity="error" if strict else "warning",
            ref="story.opposition",
        )
    if _is_blank(story.get("stakes")):
        add(
            CODE_NO_STAKES,
            "stakes missing — what is lost if protagonist fails?",
            severity="warning",
            ref="story.stakes",
        )

    arc = story.get("emotional_arc") or []
    if not isinstance(arc, list) or len([a for a in arc if not _is_blank(a)]) < 3:
        add(
            CODE_ARC_TOO_SHORT,
            "emotional_arc needs ≥3 beats for progression",
            severity="error" if strict else "warning",
            ref="story.emotional_arc",
        )

    scenes = _iter_scenes(graph, spec)
    weak_scenes: list[str] = []
    beatless_with_shots: list[str] = []
    for i, scene in enumerate(scenes):
        sid = str(scene.get("id") or scene.get("title") or f"scene{i + 1}")
        if not _scene_has_turn(scene):
            weak_scenes.append(sid)
            add(
                CODE_SCENE_NO_TURN,
                f"{sid}: scene has no narrative turn/goal/conflict — flag before media spend",
                severity="warning",
                ref=f"scenes.{sid}",
            )
            add(
                CODE_SCENE_REMOVABLE,
                f"{sid}: candidate for cut — removing may not hurt story",
                severity="warning",
                ref=f"scenes.{sid}",
            )
        beats = _beats_in_scene(scene)
        shots = _shots_in_scene(scene)
        if require_beats and shots and not beats and scene.get("shots"):
            # Flat film-spec: shots under scene without beats
            if not any(isinstance(b, dict) for b in (scene.get("beats") or [])):
                beatless_with_shots.append(sid)
                add(
                    CODE_SHOTS_WITHOUT_BEAT,
                    f"{sid}: shots exist without beat layer — do not generate from screenplay paragraphs",
                    severity="error" if strict else "warning",
                    ref=f"scenes.{sid}.beats",
                )
        if require_beats and not beats and not shots:
            add(
                CODE_BEAT_MISSING,
                f"{sid}: no beats extracted yet",
                severity="warning",
                ref=f"scenes.{sid}.beats",
            )

    error_codes = sorted({str(i["code"]) for i in issues if i.get("severity") == "error"})
    warning_codes = sorted(
        {str(i["code"]) for i in issues + flags if i.get("severity") == "warning"}
    )
    # Non-strict: only real errors block; warnings always listed
    blocking = error_codes if strict else []
    ok = not blocking and (not error_codes if strict else True)
    # In non-strict mode, structural errors are demoted — reclassify
    if not strict:
        ok = True
        for item in issues:
            if item.get("severity") == "error":
                item["severity"] = "warning"
                flags.append(item)
        issues = []
        warning_codes = sorted({str(i["code"]) for i in flags})

    return {
        "ok": ok,
        "kind": "story-structure",
        "strict": strict,
        "issues": issues,
        "flags": flags,
        "codes": sorted(set(error_codes) | set(warning_codes)),
        "blocking": blocking,
        "weak_scene_ids": weak_scenes,
        "beatless_scene_ids": beatless_with_shots,
        "scene_count": len(scenes),
        "media_spend_allowed": ok and not (strict and weak_scenes),
    }


def assert_beats_before_shots(
    graph: dict[str, Any] | None = None,
    *,
    spec: dict[str, Any] | None = None,
    strict: bool = True,
) -> dict[str, Any]:
    """Fail-closed when shots appear without a beat intermediate layer."""
    report = validate_story_structure(
        graph, spec=spec, strict=strict, require_beats=True
    )
    beat_codes = {CODE_SHOTS_WITHOUT_BEAT, CODE_BEAT_MISSING}
    hit = [c for c in report.get("codes") or [] if c in beat_codes]
    if strict and report.get("beatless_scene_ids"):
        report = dict(report)
        report["ok"] = False
        report["blocking"] = sorted(set(report.get("blocking") or []) | {CODE_SHOTS_WITHOUT_BEAT})
        report["media_spend_allowed"] = False
    report["beat_gate"] = {"ok": not hit if strict else True, "codes": hit}
    return report


def validate_story_structure_at_root(
    root: Path | str,
    *,
    strict: bool = False,
    write_receipt: bool = True,
) -> dict[str, Any]:
    root_p = Path(root).expanduser().resolve()
    graph = read_json(root_p / "drama-graph.json") or {}
    spec = read_json(root_p / "film-spec.json") or {}
    if not isinstance(graph, dict):
        graph = {}
    if not isinstance(spec, dict):
        spec = {}
    report = validate_story_structure(graph, spec=spec or None, strict=strict)
    report["root"] = str(root_p)
    report["at"] = utc_now()
    if write_receipt:
        path = root_p / "receipts" / "story-structure.json"
        write_json(path, report)
        report["receipt"] = str(path)
    return report
