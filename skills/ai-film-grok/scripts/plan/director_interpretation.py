"""Director Interpretation receipt — scene-level analysis before shot list.

Film Production OS W2 / §41. Does not generate images; writes production instructions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json


def _text(value: object) -> str:
    return str(value or "").strip()


def _scene_from_spec(spec: dict[str, Any], scene_id: str | None) -> tuple[str, dict[str, Any]]:
    scenes = [s for s in (spec.get("scenes") or []) if isinstance(s, dict)]
    if not scenes:
        return "sc01", {}
    if scene_id:
        for i, sc in enumerate(scenes):
            sid = str(sc.get("id") or sc.get("title") or f"sc{i + 1:02d}")
            if sid == scene_id or str(sc.get("id")) == scene_id:
                return sid, sc
    sc0 = scenes[0]
    sid = str(sc0.get("id") or sc0.get("title") or "sc01")
    return sid, sc0


def build_director_interpretation(
    spec: dict[str, Any],
    *,
    scene_id: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile a director analysis object for one scene."""
    sid, scene = _scene_from_spec(spec, scene_id)
    di = spec.get("director_intent") if isinstance(spec.get("director_intent"), dict) else {}
    board = scene.get("director_board") if isinstance(scene.get("director_board"), dict) else {}
    ovr = overrides if isinstance(overrides, dict) else {}

    dramatic = _text(
        ovr.get("dramatic_function")
        or board.get("emotional_turn")
        or scene.get("scene_turn")
        or scene.get("summary")
        or scene.get("title")
        or "what changes in this scene must be authored"
    )
    pov = _text(
        ovr.get("pov")
        or board.get("pov")
        or di.get("protagonist_pov")
        or di.get("protagonist_want")
        or "protagonist"
    )
    arc_parts = di.get("emotional_arc") if isinstance(di.get("emotional_arc"), list) else []
    arc_str = " → ".join(_text(x) for x in arc_parts if _text(x))
    emotional = _text(
        ovr.get("emotional_arc")
        or board.get("emotional_turn")
        or arc_str
        or "start → turn → end"
    )
    info = _text(
        ovr.get("information_strategy")
        or board.get("audience_question")
        or "audience vs character knowledge must be authored"
    )
    visual = _text(
        ovr.get("visual_strategy")
        or board.get("coverage_strategy")
        or board.get("image_priority")
        or di.get("visual_language")
        or "camera language progression"
    )
    performance = _text(
        ovr.get("performance_strategy")
        or board.get("performance")
        or "objectives and intensity"
    )
    sound = _text(
        ovr.get("sound_strategy")
        or board.get("sound_priority")
        or "ambience / dialogue / silence"
    )
    editorial = _text(
        ovr.get("editorial_strategy")
        or board.get("cut_intent")
        or "how the scene should cut"
    )
    risk = _text(
        ovr.get("risk")
        or board.get("risk")
        or "continuity and generation risks"
    )

    return {
        "schema_version": 1,
        "kind": "director-interpretation",
        "scene_id": sid,
        "title": _text(scene.get("title")) or sid,
        "dramatic_function": dramatic,
        "pov": pov,
        "emotional_arc": emotional,
        "information_strategy": info,
        "visual_strategy": visual,
        "performance_strategy": performance,
        "sound_strategy": sound,
        "editorial_strategy": editorial,
        "risk": risk,
        "creative_intent_refs": {
            "theme": _text(di.get("theme")),
            "audience_emotion": _text(di.get("audience_emotion")),
            "visual_language": _text(di.get("visual_language")),
            "pacing": _text(di.get("pacing") or di.get("tone")),
        },
        "status": "draft",
        "at": utc_now(),
    }


def format_director_interpretation_md(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            "## Director Interpretation",
            "",
            f"Scene: {payload.get('scene_id')} — {payload.get('title')}",
            "",
            "### Dramatic Function",
            str(payload.get("dramatic_function") or ""),
            "",
            "### POV",
            str(payload.get("pov") or ""),
            "",
            "### Emotional Arc",
            str(payload.get("emotional_arc") or ""),
            "",
            "### Information Strategy",
            str(payload.get("information_strategy") or ""),
            "",
            "### Visual Strategy",
            str(payload.get("visual_strategy") or ""),
            "",
            "### Performance Strategy",
            str(payload.get("performance_strategy") or ""),
            "",
            "### Sound Strategy",
            str(payload.get("sound_strategy") or ""),
            "",
            "### Editorial Strategy",
            str(payload.get("editorial_strategy") or ""),
            "",
            "### Risk",
            str(payload.get("risk") or ""),
            "",
        ]
    )


def interpret_scene_at_root(
    root: Path | str,
    *,
    scene_id: str | None = None,
    write_receipt: bool = True,
) -> dict[str, Any]:
    root_p = Path(root).expanduser().resolve()
    spec = read_json(root_p / "film-spec.json") or {}
    if not isinstance(spec, dict) or not spec:
        return {"ok": False, "error": "film-spec.json missing", "root": str(root_p)}

    payload = build_director_interpretation(spec, scene_id=scene_id)
    payload["ok"] = True
    payload["root"] = str(root_p)
    if write_receipt:
        out_dir = root_p / "receipts" / "director-interpretation"
        out_dir.mkdir(parents=True, exist_ok=True)
        sid = str(payload.get("scene_id") or "scene")
        json_path = out_dir / f"{sid}.json"
        md_path = out_dir / f"{sid}.md"
        write_json(json_path, payload)
        md_path.write_text(format_director_interpretation_md(payload), encoding="utf-8")
        payload["receipt"] = str(json_path)
        payload["markdown"] = str(md_path)
    return payload
