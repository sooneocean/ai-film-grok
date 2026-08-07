"""Coverage Checker — can this scene be edited coherently?

Film Production OS W3: fail-closed when coverage predicts an uncuttable scene.
Does not generate media; blocks SHOT_READY / bulk when strict.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json

# Roles inferred from shot purpose / dramatic_function / coverage_role / shot_size
COVERAGE_ROLES = frozenset(
    {
        "establish",
        "master",
        "medium",
        "close_up",
        "reaction",
        "pov",
        "insert",
        "cutaway",
        "transition",
        "entry_exit",
        "environment",
        "action_detail",
        "dialogue",
        "reverse",
    }
)

# Minimum coverage for a scene with ≥2 hero shots (shortform subset)
SHORTFORM_MIN = frozenset({"establish", "close_up", "medium", "action_detail", "reaction"})
# Dialogue scenes need extra
DIALOGUE_MIN = frozenset({"dialogue", "reaction", "reverse", "close_up"})
# Longform / professional full set soft-check
LONGFORM_RECOMMENDED = frozenset(
    {
        "establish",
        "master",
        "medium",
        "close_up",
        "reaction",
        "insert",
        "transition",
    }
)

CODE_COVERAGE_INCOMPLETE = "COVERAGE_INCOMPLETE"
CODE_DIALOGUE_COVERAGE = "DIALOGUE_COVERAGE_INCOMPLETE"
CODE_UNEDITABLE_PREDICTED = "SCENE_UNEDITABLE_PREDICTED"
CODE_NO_SHOTS = "COVERAGE_NO_SHOTS"


def _text(value: object) -> str:
    return str(value or "").strip()


def _norm(value: object) -> str:
    return _text(value).lower().replace("-", "_").replace(" ", "_")


def _shots_from_scene(scene: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    beats = scene.get("beats") if isinstance(scene.get("beats"), list) else None
    if beats:
        for beat in beats:
            if not isinstance(beat, dict):
                continue
            for sh in beat.get("shots") or []:
                if isinstance(sh, dict):
                    out.append(sh)
    for sh in scene.get("shots") or []:
        if isinstance(sh, dict):
            out.append(sh)
    return out


def infer_coverage_role(shot: dict[str, Any]) -> str:
    """Map shot fields to a coverage role bucket."""
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    explicit = _norm(shot.get("coverage_role") or dsl.get("coverage_role"))
    if explicit in COVERAGE_ROLES:
        return explicit

    purpose = _norm(
        shot.get("shot_purpose") or shot.get("purpose") or dsl.get("shot_purpose")
    )
    purpose_map = {
        "establish_location": "establish",
        "establish_geography": "establish",
        "introduce_character": "medium",
        "reveal_information": "insert",
        "show_reaction": "reaction",
        "show_relationship": "medium",
        "create_tension": "medium",
        "release_tension": "medium",
        "transition": "transition",
        "insert_detail": "insert",
        "subjective_pov": "pov",
        "emotional_closeup": "close_up",
        "action_coverage": "action_detail",
        "dialogue_coverage": "dialogue",
        "story_reveal": "insert",
        "visual_motif": "cutaway",
    }
    if purpose in purpose_map:
        return purpose_map[purpose]

    fn = _norm(shot.get("dramatic_function") or dsl.get("dramatic_function"))
    fn_map = {
        "hook": "establish",
        "approach": "medium",
        "sensory": "insert",
        "reaction": "reaction",
        "action": "action_detail",
        "afterglow": "medium",
        "bridge": "transition",
    }
    if fn in fn_map:
        return fn_map[fn]

    size = _norm(shot.get("shot_size") or dsl.get("shot_size") or shot.get("size"))
    if size in {"ecu", "cu", "close_up", "closeup", "extreme_close_up"}:
        return "close_up"
    if size in {"ms", "medium", "mcu"}:
        return "medium"
    if size in {"ws", "wide", "establishing", "long"}:
        return "establish"
    if size in {"insert", "detail"}:
        return "insert"

    role = _norm(shot.get("shot_role") or "hero")
    if role == "env":
        return "environment"
    if role == "insert":
        return "insert"
    if role == "bridge":
        return "transition"
    return "medium"


def _is_dialogue_shot(shot: dict[str, Any]) -> bool:
    spoken = shot.get("spoken_text") or shot.get("dialogue")
    if _text(spoken):
        return True
    screen = _norm(shot.get("screen_mode") or "")
    return screen in {"on_camera", "off_camera", "dialogue"}


def _scene_is_dialogue(shots: list[dict[str, Any]]) -> bool:
    return sum(1 for s in shots if _is_dialogue_shot(s)) >= 1


def check_scene_coverage(
    scene: dict[str, Any],
    *,
    scene_id: str = "",
    production_mode: str = "shortform",
    strict: bool = False,
) -> dict[str, Any]:
    """Return coverage report for one scene."""
    sid = scene_id or _text(scene.get("id") or scene.get("title") or "scene")
    shots = _shots_from_scene(scene)
    issues: list[dict[str, Any]] = []
    roles_present: set[str] = set()
    for sh in shots:
        roles_present.add(infer_coverage_role(sh))

    if not shots:
        issues.append(
            {
                "code": CODE_NO_SHOTS,
                "severity": "error",
                "message": f"{sid}: no shots to cover",
                "ref": sid,
            }
        )
        return _pack(sid, roles_present, issues, shots, production_mode, strict)

    # Board strategy is advisory evidence, not a substitute for roles
    board = scene.get("director_board") if isinstance(scene.get("director_board"), dict) else {}
    strategy = _text(board.get("coverage_strategy"))

    required = set(SHORTFORM_MIN)
    if production_mode == "longform":
        required |= set(LONGFORM_RECOMMENDED)

    # Soft: single-shot micro scenes only need establish OR medium
    if len(shots) == 1:
        required = {"establish", "medium", "close_up", "action_detail"}
        if not roles_present.intersection(required):
            issues.append(
                {
                    "code": CODE_COVERAGE_INCOMPLETE,
                    "severity": "error" if strict else "warning",
                    "message": f"{sid}: single shot lacks readable coverage role",
                    "ref": sid,
                }
            )
    else:
        missing = sorted(required - roles_present)
        # shortform: need at least 2 of the min set for ≥2 shots
        if production_mode != "longform":
            hit = len(roles_present & SHORTFORM_MIN)
            if hit < 2:
                issues.append(
                    {
                        "code": CODE_COVERAGE_INCOMPLETE,
                        "severity": "error" if strict else "warning",
                        "message": (
                            f"{sid}: weak coverage (roles={sorted(roles_present)}); "
                            f"need variety among {sorted(SHORTFORM_MIN)}"
                        ),
                        "ref": sid,
                        "missing": missing,
                    }
                )
        else:
            if missing:
                issues.append(
                    {
                        "code": CODE_COVERAGE_INCOMPLETE,
                        "severity": "error" if strict else "warning",
                        "message": f"{sid}: missing coverage roles: {missing}",
                        "ref": sid,
                        "missing": missing,
                    }
                )

    if _scene_is_dialogue(shots):
        dlg_hit = roles_present & DIALOGUE_MIN
        if len(dlg_hit) < 2 and len(shots) >= 2:
            issues.append(
                {
                    "code": CODE_DIALOGUE_COVERAGE,
                    "severity": "error" if strict else "warning",
                    "message": (
                        f"{sid}: dialogue scene needs ≥2 of {sorted(DIALOGUE_MIN)} "
                        f"(have {sorted(dlg_hit)})"
                    ),
                    "ref": sid,
                }
            )

    # Uneditable prediction: only same role repeated with no insert/reaction
    if len(shots) >= 3 and len(roles_present) == 1:
        issues.append(
            {
                "code": CODE_UNEDITABLE_PREDICTED,
                "severity": "error" if strict else "warning",
                "message": (
                    f"{sid}: all shots map to single role {next(iter(roles_present))!r} — "
                    "editor cannot cut coherently"
                ),
                "ref": sid,
            }
        )

    return _pack(sid, roles_present, issues, shots, production_mode, strict, strategy)


def _pack(
    sid: str,
    roles: set[str],
    issues: list[dict[str, Any]],
    shots: list[dict[str, Any]],
    production_mode: str,
    strict: bool,
    strategy: str = "",
) -> dict[str, Any]:
    errors = [i for i in issues if i.get("severity") == "error"]
    ok = not errors
    return {
        "ok": ok,
        "scene_id": sid,
        "shot_count": len(shots),
        "roles_present": sorted(roles),
        "coverage_strategy": strategy or None,
        "production_mode": production_mode,
        "strict": strict,
        "issues": issues,
        "codes": sorted({str(i["code"]) for i in issues}),
        "blocking": sorted({str(i["code"]) for i in errors}),
        "production_allowed": ok,
    }


def check_spec_coverage(
    spec: dict[str, Any],
    *,
    strict: bool = False,
) -> dict[str, Any]:
    mode = str(spec.get("production_mode") or "shortform")
    scenes = [s for s in (spec.get("scenes") or []) if isinstance(s, dict)]
    reports: list[dict[str, Any]] = []
    for i, sc in enumerate(scenes):
        sid = _text(sc.get("id") or sc.get("title") or f"sc{i + 1:02d}")
        reports.append(
            check_scene_coverage(sc, scene_id=sid, production_mode=mode, strict=strict)
        )
    all_issues: list[dict[str, Any]] = []
    for r in reports:
        all_issues.extend(r.get("issues") or [])
    errors = [i for i in all_issues if i.get("severity") == "error"]
    return {
        "ok": not errors,
        "kind": "coverage-check",
        "strict": strict,
        "scene_count": len(reports),
        "scenes": reports,
        "issues": all_issues,
        "codes": sorted({str(i["code"]) for i in all_issues}),
        "blocking": sorted({str(i["code"]) for i in errors}),
        "production_allowed": not errors,
    }


def coverage_check_at_root(
    root: Path | str,
    *,
    strict: bool = False,
    write_receipt: bool = True,
) -> dict[str, Any]:
    root_p = Path(root).expanduser().resolve()
    spec = read_json(root_p / "film-spec.json") or {}
    if not isinstance(spec, dict) or not spec:
        return {"ok": False, "error": "film-spec.json missing", "root": str(root_p)}
    report = check_spec_coverage(spec, strict=strict)
    report["root"] = str(root_p)
    report["at"] = utc_now()
    if write_receipt:
        path = root_p / "receipts" / "coverage-check.json"
        write_json(path, report)
        report["receipt"] = str(path)
    return report
