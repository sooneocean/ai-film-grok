#!/usr/bin/env python3
"""Single stage projection model (R2 routing rewire).

Three taxonomies exist historically; this module is the only place that maps them:

- PUBLIC_CRAFT: agent → visual → voice → post → deliver  (SKILL / people)
- INTERNAL_PIPELINE: agent → visual → voice → design → post → deliver → done
- CRAFT_EIGHT: idea → … → verified  (craft_spine rings)
- WORKFLOW_11: professional book stages (workflow_spine)

`design` is an internal alias that projects to public `post`.
"""

from __future__ import annotations

from typing import Any

# Public / SKILL-facing craft (five segments + terminal done for status).
PUBLIC_CRAFT: tuple[str, ...] = (
    "agent",
    "visual",
    "voice",
    "post",
    "deliver",
)

# Internal next_actions / dispatch owner pipeline.
INTERNAL_PIPELINE: tuple[str, ...] = (
    "agent",
    "visual",
    "voice",
    "design",
    "post",
    "deliver",
    "done",
)

# Eight-ring craft spine (orthogonal artifact detector).
CRAFT_EIGHT: tuple[str, ...] = (
    "idea",
    "story",
    "beats",
    "shots",
    "media",
    "selects",
    "rough",
    "verified",
)

STAGE_OWNERS: dict[str, tuple[str, str | None]] = {
    "agent": ("director", None),
    "visual": ("visual", "visual"),
    "voice": ("audio", "audio"),
    "design": ("post", "post"),
    "post": ("post", "post"),
    "deliver": ("delivery", None),
    "done": ("delivery", None),
}

_CRAFT_EIGHT_TO_PUBLIC: dict[str, str] = {
    "idea": "agent",
    "story": "agent",
    "beats": "agent",
    "shots": "visual",
    "media": "visual",
    "selects": "visual",
    "rough": "post",
    "verified": "deliver",
}

_PIPELINE_TO_PUBLIC: dict[str, str] = {
    "agent": "agent",
    "visual": "visual",
    "voice": "voice",
    "design": "post",
    "post": "post",
    "deliver": "deliver",
    "done": "deliver",
}

PIPELINE_LABELS_ZH: dict[str, str] = {
    "agent": "0·Agent 规划（Lens / 定妆 / film-spec / pilot）",
    "visual": "1·视觉生成（Grok still + H3/Grok I2V）",
    "voice": "2·语音生成（Edge TTS + tts-rehearse / SRT）",
    "design": "3·设计合成（HyperFrames 优先 / Remotion）",
    "post": "4·后处理验收（FFmpeg plate · review-final）",
    "deliver": "交付导出（export-desktop）",
    "done": "完成",
}


def normalize_pipeline_stage(stage: str | None) -> str:
    s = str(stage or "agent").strip() or "agent"
    if s in INTERNAL_PIPELINE:
        return s
    if s in CRAFT_EIGHT:
        # project craft eight → nearest pipeline via public then expand
        pub = _CRAFT_EIGHT_TO_PUBLIC.get(s, "agent")
        return pub if pub in INTERNAL_PIPELINE else "agent"
    if s in PUBLIC_CRAFT:
        return s
    return "agent"


def to_public_craft(stage: str | None, *, source: str = "auto") -> str:
    """Project any stage name onto PUBLIC_CRAFT."""
    s = str(stage or "").strip()
    if not s:
        return "agent"
    if source == "craft_eight" or s in CRAFT_EIGHT:
        return _CRAFT_EIGHT_TO_PUBLIC.get(s, "agent")
    if s in _PIPELINE_TO_PUBLIC:
        return _PIPELINE_TO_PUBLIC[s]
    if s in PUBLIC_CRAFT:
        return s
    return "agent"


def to_pipeline_stage(stage: str | None) -> str:
    return normalize_pipeline_stage(stage)


def stage_owners(stage: str | None) -> tuple[str, str | None]:
    key = normalize_pipeline_stage(stage)
    return STAGE_OWNERS.get(key, ("director", None))


def responsibility_for_stage(stage: str | None) -> dict[str, str | None]:
    key = normalize_pipeline_stage(stage)
    owner, department = stage_owners(key)
    return {"owner": owner, "department": department, "stage": key}


def project_stages(
    *,
    craft_stage: str | None = None,
    pipeline_stage: str | None = None,
) -> dict[str, Any]:
    """Return a stable multi-key projection for dispatch / compact packets."""
    craft = str(craft_stage or "idea")
    pipe = normalize_pipeline_stage(pipeline_stage or to_public_craft(craft, source="craft_eight"))
    public = to_public_craft(pipe)
    if craft in CRAFT_EIGHT:
        public_from_craft = to_public_craft(craft, source="craft_eight")
    else:
        public_from_craft = public
    return {
        "craft_stage": craft if craft in CRAFT_EIGHT else craft,
        "pipeline_stage": pipe,
        "stage_public": public_from_craft if craft in CRAFT_EIGHT else public,
        "design_is_post_alias": pipe == "design",
    }
