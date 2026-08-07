"""Scene dramatic model hardening (Film Production OS W4).

Required when scene_strict=true: dramatic_goal, conflict, scene_turn,
emotional_arc{start,mid,end}, continuity_in/out.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json

CODE_SCENE_FIELD = "SCENE_DRAMA_FIELD_MISSING"
CODE_SCENE_ARC = "SCENE_EMOTIONAL_ARC_INCOMPLETE"
CODE_SCENE_CONTINUITY = "SCENE_CONTINUITY_MISSING"

_PLACEHOLDERS = frozenset(
    {"", "todo", "tbd", "n/a", "na", "needs_authoring", "待定", "待填写", "placeholder"}
)


def _text(value: object) -> str:
    return str(value or "").strip()


def _blank(value: object) -> bool:
    if isinstance(value, dict):
        return not any(not _blank(v) for v in value.values())
    return _text(value).lower() in _PLACEHOLDERS


def lint_scene_drama(scene: dict[str, Any], *, scene_id: str = "", strict: bool = False) -> dict[str, Any]:
    sid = scene_id or _text(scene.get("id") or scene.get("title") or "scene")
    issues: list[dict[str, Any]] = []
    sev = "error" if strict else "warning"

    for field in ("dramatic_goal", "scene_turn"):
        if _blank(scene.get(field)):
            # Accept director_board.emotional_turn as soft scene_turn
            board = scene.get("director_board") if isinstance(scene.get("director_board"), dict) else {}
            if field == "scene_turn" and not _blank(board.get("emotional_turn")):
                continue
            if field == "dramatic_goal" and not _blank(scene.get("summary")):
                continue
            issues.append(
                {
                    "code": CODE_SCENE_FIELD,
                    "severity": sev,
                    "message": f"{sid}: missing {field}",
                    "ref": f"{sid}.{field}",
                }
            )

    conflict = scene.get("conflict")
    if _blank(conflict):
        issues.append(
            {
                "code": CODE_SCENE_FIELD,
                "severity": sev,
                "message": f"{sid}: missing conflict (external/internal or string)",
                "ref": f"{sid}.conflict",
            }
        )

    arc = scene.get("emotional_arc")
    if isinstance(arc, dict):
        for k in ("start", "middle", "end"):
            # accept mid alias
            val = arc.get(k) if k != "middle" else (arc.get("middle") or arc.get("mid"))
            if _blank(val):
                issues.append(
                    {
                        "code": CODE_SCENE_ARC,
                        "severity": sev,
                        "message": f"{sid}: emotional_arc.{k} missing",
                        "ref": f"{sid}.emotional_arc.{k}",
                    }
                )
    elif isinstance(arc, list) and len([x for x in arc if not _blank(x)]) >= 2:
        pass
    else:
        board = scene.get("director_board") if isinstance(scene.get("director_board"), dict) else {}
        if _blank(board.get("emotional_turn")):
            issues.append(
                {
                    "code": CODE_SCENE_ARC,
                    "severity": sev,
                    "message": f"{sid}: emotional_arc object or board.emotional_turn required",
                    "ref": f"{sid}.emotional_arc",
                }
            )

    for ckey in ("continuity_in", "continuity_out"):
        if _blank(scene.get(ckey)):
            issues.append(
                {
                    "code": CODE_SCENE_CONTINUITY,
                    "severity": "warning",  # always soft unless scene_continuity_strict
                    "message": f"{sid}: {ckey} empty — continuity agent cannot chain",
                    "ref": f"{sid}.{ckey}",
                }
            )

    errors = [i for i in issues if i.get("severity") == "error"]
    return {
        "ok": not errors,
        "scene_id": sid,
        "issues": issues,
        "codes": sorted({str(i["code"]) for i in issues}),
        "blocking": sorted({str(i["code"]) for i in errors}),
    }


def lint_spec_scene_drama(spec: dict[str, Any], *, strict: bool | None = None) -> dict[str, Any]:
    if strict is None:
        strict = bool(spec.get("scene_strict"))
    scenes = [s for s in (spec.get("scenes") or []) if isinstance(s, dict)]
    reports = []
    all_issues: list[dict[str, Any]] = []
    for i, sc in enumerate(scenes):
        sid = _text(sc.get("id") or sc.get("title") or f"sc{i + 1:02d}")
        r = lint_scene_drama(sc, scene_id=sid, strict=strict)
        reports.append(r)
        all_issues.extend(r.get("issues") or [])
    errors = [i for i in all_issues if i.get("severity") == "error"]
    return {
        "ok": not errors,
        "kind": "scene-drama",
        "strict": strict,
        "scenes": reports,
        "issues": all_issues,
        "codes": sorted({str(i["code"]) for i in all_issues}),
        "blocking": sorted({str(i["code"]) for i in errors}),
    }


def scene_drama_at_root(root: Path | str, *, strict: bool | None = None, write_receipt: bool = True) -> dict[str, Any]:
    root_p = Path(root).expanduser().resolve()
    spec = read_json(root_p / "film-spec.json") or {}
    if not isinstance(spec, dict):
        return {"ok": False, "error": "film-spec missing"}
    report = lint_spec_scene_drama(spec, strict=strict)
    report["root"] = str(root_p)
    report["at"] = utc_now()
    if write_receipt:
        path = root_p / "receipts" / "scene-drama.json"
        write_json(path, report)
        report["receipt"] = str(path)
    return report
