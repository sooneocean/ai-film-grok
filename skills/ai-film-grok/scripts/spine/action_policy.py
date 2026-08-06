#!/usr/bin/env python3
"""Action spend/approval/skill maps (R4). Defaults live here; catalog may overlay."""

from __future__ import annotations

from typing import Any

# action id → skill_id
ACTION_SKILLS: dict[str, str] = {
    "narrative-validate": "story.validate",
    "narrative-project": "graph.project",
    "narrative-lock": "story.validate",
    "grok-i2v-bulk": "image.animate",
    "state-index-plan": "character.state.update",
    "dialogue-candidate-review": "quality.inspect",
    "audio-plan": "sound.design",
    "selects-report": "projection.verify",
    "post-audit-gate": "projection.verify",
    "closeout-run": "projection.verify",
    "production-evidence-gate": "projection.verify",
    "bulk-preflight": "image.animate",
    "h3-run-next": "image.animate",
    "h3-until-empty": "image.animate",
    "h3-capacity-plan": "projection.verify",
    "h3-fill-idle": "image.animate",
    "h3-lane": "image.animate",
    "pilot-pack": "quality.inspect",
    "variety-precheck": "story.validate",
    "i2v-motion-gate": "projection.verify",
    "film-core-closeout": "projection.verify",
    "select-shortlist": "projection.verify",
    "ship-prep": "projection.verify",
    "gate-auto": "projection.verify",
    "cinematic-gate": "projection.verify",
    "export-desktop": "export.package",
    "dailies_review-evidence": "dispatch.orchestrate",
    "agent-review-final": "quality.inspect",
}

SKILL_POLICIES: dict[str, tuple[str, str]] = {
    "keyframe.generate": ("external", "human_required"),
    "image.animate": ("paid", "human_required"),
    "voice.synthesize": ("external", "human_required"),
    "video.render": ("external", "human_required"),
    "quality.inspect": ("local", "human_required"),
    "export.package": ("local", "none"),
}

COMMAND_POLICIES: dict[str, tuple[str, str]] = {
    "dailies": ("local", "none"),
    "export-desktop": ("local", "none"),
    "final": ("external", "human_required"),
    "closeout": ("local", "none"),
    "grok-oauth": ("external", "human_required"),
    "media-queue": ("external", "human_required"),
    "pilot": ("local", "human_required"),
    "pilot-pack": ("local", "none"),
    "bulk-preflight": ("local", "none"),
    "variety-precheck": ("local", "none"),
    "i2v-motion-gate": ("local", "none"),
    "film-core-closeout": ("local", "none"),
    "select-shortlist": ("local", "none"),
    "ship-prep": ("local", "none"),
    "gate-auto": ("local", "none"),
    "cinematic-gate": ("local", "none"),
    "queue-progress": ("local", "none"),
    "tunnel-probe": ("local", "none"),
    "gpu-lease": ("local", "none"),
    "h3": ("local", "none"),
    "agent-review-final": ("local", "none"),
    "queue-run-oauth": ("paid", "human_required"),
    "review-ui": ("local", "human_required"),
    "review-final": ("local", "human_required"),
    "tts-rehearse": ("external", "human_required"),
}

# Hard-compat aliases used by dispatch.py historical names
_ACTION_SKILLS = ACTION_SKILLS
_SKILL_POLICIES = SKILL_POLICIES
_COMMAND_POLICIES = COMMAND_POLICIES


def _catalog_overlay() -> dict[str, dict[str, Any]]:
    """Optional overlay from route-catalog (action rows only). Fail soft."""
    try:
        from route_catalog import list_routes

        out: dict[str, dict[str, Any]] = {}
        for route in list_routes(kind="action"):
            rid = str(route.get("id") or "")
            if not rid:
                continue
            out[rid] = route
        return out
    except Exception:
        return {}


def resolve_skill_id(action_id: str) -> str:
    overlay = _catalog_overlay().get(action_id) or {}
    if overlay.get("skill_id"):
        return str(overlay["skill_id"])
    return ACTION_SKILLS.get(action_id, "dispatch.orchestrate")


def resolve_policy(
    *,
    action_id: str,
    operation: str,
    skill_id: str | None = None,
) -> tuple[str, str]:
    """Return (spend_class, approval_class). Command policy beats skill default."""
    sid = skill_id or resolve_skill_id(action_id)
    spend, approval = SKILL_POLICIES.get(sid, ("local", "none"))
    cmd = COMMAND_POLICIES.get(operation)
    if cmd is not None:
        spend, approval = cmd
    # Catalog may refine spend/approval for known actions (never loosen pilot human).
    overlay = _catalog_overlay().get(action_id) or {}
    if overlay.get("spend_class"):
        spend = str(overlay["spend_class"])
    if overlay.get("approval_class"):
        approval = str(overlay["approval_class"])
    if operation == "plan":
        # lock stays human even if catalog says none
        pass
    if operation == "pilot" and operation != "pilot-pack":
        approval = "human_required"
    return spend, approval


def catalog_advance_ids() -> frozenset[str]:
    """Action ids marked advance_eligible in route-catalog (empty if missing)."""
    try:
        from route_catalog import list_routes

        return frozenset(
            str(r.get("id"))
            for r in list_routes(advance_only=True)
            if r.get("id")
        )
    except Exception:
        return frozenset()
