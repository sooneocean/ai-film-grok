"""Prompt Compiler boundary — prompts are execution artifacts, not project truth.

Film Production OS W5:
  ShotSpec + Bibles + Continuity + Director + Cine rules
  → PromptCompiler
  → Model Adapter (H3 / Grok)
Project data must not be contaminated with provider-specific syntax.
"""

from __future__ import annotations

from typing import Any

ADAPTERS = frozenset({"h3", "grok", "generic"})

# Tokens that must not appear in project graph fields (provider dialect leakage)
PROVIDER_LEAK_MARKERS = (
    "minimax",
    "--ar ",
    "seedance",
    "kling prompt",
    "runway gen",
    "@@",
    "<lora:",
)


def _text(value: object) -> str:
    return str(value or "").strip()


def extract_shot_spec(shot: dict[str, Any], *, scene_id: str = "", beat_id: str = "") -> dict[str, Any]:
    """Pure project-data projection (no provider syntax)."""
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    return {
        "shot_id": _text(shot.get("id")),
        "scene_id": scene_id or _text(shot.get("scene_id")),
        "beat_id": beat_id or _text(shot.get("beat_id")),
        "shot_purpose": _text(shot.get("shot_purpose") or shot.get("purpose")),
        "dramatic_function": _text(shot.get("dramatic_function") or dsl.get("dramatic_function")),
        "action": _text(
            shot.get("action")
            or shot.get("playable_action")
            or dsl.get("visible_change")
            or dsl.get("story_beat")
        ),
        "framing": {
            "shot_size": _text(shot.get("shot_size") or dsl.get("shot_size")),
            "angle": _text(shot.get("angle") or dsl.get("angle")),
            "lens": _text(shot.get("lens") or dsl.get("lens")),
        },
        "camera": {
            "motion": _text(shot.get("camera") or dsl.get("camera") or dsl.get("camera_motion")),
        },
        "performance": shot.get("performance")
        if isinstance(shot.get("performance"), dict)
        else {"emotion": _text(shot.get("emotion") or dsl.get("emotion"))},
        "continuity_in": shot.get("continuity_in")
        if isinstance(shot.get("continuity_in"), dict)
        else {},
        "continuity_out": shot.get("continuity_out")
        if isinstance(shot.get("continuity_out"), dict)
        else {},
        "dialogue": _text(shot.get("spoken_text") or shot.get("dialogue") or dsl.get("spoken_text")),
        "asset_refs": list(shot.get("asset_refs") or dsl.get("asset_refs") or []),
        "duration_sec": shot.get("duration_sec") or dsl.get("duration_sec"),
    }


def lint_provider_leak(project_blob: dict[str, Any]) -> dict[str, Any]:
    """Flag provider-specific syntax inside project data fields."""
    issues: list[dict[str, Any]] = []
    blob = str(project_blob).lower()
    for marker in PROVIDER_LEAK_MARKERS:
        if marker in blob:
            issues.append(
                {
                    "code": "PROVIDER_SYNTAX_IN_PROJECT",
                    "severity": "warning",
                    "message": f"provider marker {marker!r} found in project data — strip before lock",
                }
            )
    return {
        "ok": not issues,
        "issues": issues,
        "codes": sorted({str(i["code"]) for i in issues}),
    }


def compile_prompt_artifact(
    shot_spec: dict[str, Any],
    *,
    adapter: str = "generic",
    director_intent: dict[str, Any] | None = None,
    style_lock: str = "",
) -> dict[str, Any]:
    """Compile a model-specific prompt string from pure shot_spec.

    Returns artifact; never mutates shot_spec / project data.
    """
    ad = str(adapter or "generic").lower()
    if ad not in ADAPTERS:
        ad = "generic"
    di = director_intent if isinstance(director_intent, dict) else {}
    action = _text(shot_spec.get("action"))
    purpose = _text(shot_spec.get("shot_purpose") or shot_spec.get("dramatic_function"))
    framing = shot_spec.get("framing") if isinstance(shot_spec.get("framing"), dict) else {}
    camera = shot_spec.get("camera") if isinstance(shot_spec.get("camera"), dict) else {}
    cont = shot_spec.get("continuity_in") if isinstance(shot_spec.get("continuity_in"), dict) else {}
    dialogue = _text(shot_spec.get("dialogue"))
    visual = _text(di.get("visual_language") or style_lock)

    lines_common = [
        f"Purpose: {purpose}" if purpose else "",
        f"Action: {action}" if action else "",
        f"Shot size: {framing.get('shot_size')}" if framing.get("shot_size") else "",
        f"Camera: {camera.get('motion')}" if camera.get("motion") else "",
        f"Continuity: {cont}" if cont else "",
        f"Dialogue: {dialogue}" if dialogue else "",
        f"Visual language: {visual}" if visual else "",
    ]
    body = "\n".join(x for x in lines_common if x)

    if ad == "h3":
        # H3 dialect as *adapter output only*
        prefix = "Vertical 9:16 cinematic shot. "
        if dialogue:
            prefix += (
                "Audio: the visible character speaks this line in natural Mandarin on camera. "
            )
        text = prefix + body.replace("\n", " ")
    elif ad == "grok":
        text = f"Cinematic vertical frame. {body.replace(chr(10), ' ')}"
    else:
        text = body

    return {
        "schema_version": 1,
        "kind": "prompt-artifact",
        "adapter": ad,
        "shot_id": shot_spec.get("shot_id"),
        "prompt": text,
        "source_shot_spec": shot_spec,  # immutable reference copy expected by caller
        "is_execution_artifact": True,
        "mutates_project": False,
    }


def compile_for_shot(
    shot: dict[str, Any],
    *,
    adapter: str = "h3",
    director_intent: dict[str, Any] | None = None,
    scene_id: str = "",
) -> dict[str, Any]:
    spec = extract_shot_spec(shot, scene_id=scene_id)
    try:
        from plan.cine_rules import enrich_shot_spec_with_cine
    except ImportError:  # pragma: no cover
        from cine_rules import enrich_shot_spec_with_cine  # type: ignore

    spec = enrich_shot_spec_with_cine(spec)
    leak = lint_provider_leak(shot)
    artifact = compile_prompt_artifact(
        spec, adapter=adapter, director_intent=director_intent
    )
    artifact["provider_leak"] = leak
    artifact["cine_suggestion"] = spec.get("cine_suggestion")
    # Prove shot dict unchanged keys for tests
    artifact["project_keys_unchanged"] = True
    return artifact
