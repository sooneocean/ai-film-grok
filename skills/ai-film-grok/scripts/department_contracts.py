#!/usr/bin/env python3
"""Versioned department bibles with stable, independently lockable nodes."""

from __future__ import annotations

import copy
import re
from collections.abc import Iterable, Mapping
from typing import Any

from util import canonical_json_sha256

NODE_STATES = {"draft", "review", "locked", "stale"}

VISUAL_NODE_KEYS = (
    "face",
    "geometry",
    "body",
    "hair",
    "makeup",
    "wardrobe",
    "art",
    "location",
    "prop",
    "cinematography",
)
AUDIO_NODE_KEYS = (
    "voice",
    "dialogue_delivery",
    "adr_lipsync",
    "ambience",
    "foley",
    "sfx",
    "bgm_motif_cue",
    "licensing",
)
POST_NODE_KEYS = (
    "coverage",
    "takes",
    "edl",
    "picture_lock",
    "vfx",
    "color",
    "captions",
    "mix",
    "master",
)

VISUAL_LEGACY_FIELDS: dict[str, tuple[str, ...]] = {
    "face": ("identity_lock", "characters", "cast_masters"),
    "geometry": ("geometry", "proportions", "character_geometry"),
    "body": ("body", "body_lock", "characters"),
    "hair": ("hair", "hair_swatches", "characters"),
    "makeup": ("makeup", "makeup_variants", "characters"),
    "wardrobe": ("wardrobe_variants", "cast_state_masters", "continuity_states"),
    "art": (
        "medium",
        "palette",
        "rendering",
        "signature_block",
        "negative_hints",
        "canonical_style_path",
    ),
    "location": ("locations",),
    "prop": ("props",),
    "cinematography": ("lens", "lighting", "cinematography"),
}
AUDIO_LEGACY_FIELDS: dict[str, tuple[str, ...]] = {
    "voice": ("voice", "voices", "voice_cast", "tts", "tts_backend", "vo_voice"),
    "dialogue_delivery": ("dialogue", "dialogue_delivery", "performance", "tone_tags"),
    "adr_lipsync": ("adr", "lipsync", "adr_lipsync", "lip_sync"),
    "ambience": ("ambience", "ambient", "room_tone"),
    "foley": ("foley",),
    "sfx": ("sfx", "sound_effects", "sound_cues"),
    "bgm_motif_cue": ("bgm", "music", "motifs", "music_cues", "bgm_motif_cue"),
    "licensing": ("licensing", "licenses", "rights", "provenance", "media"),
}
POST_LEGACY_FIELDS: dict[str, tuple[str, ...]] = {
    "coverage": ("coverage", "coverage_plan"),
    "takes": ("takes", "selects"),
    "edl": ("edl", "timeline"),
    "picture_lock": ("picture_lock", "pictureLock"),
    "vfx": ("vfx", "effects"),
    "color": ("color", "grade", "color_grade"),
    "captions": ("captions", "subtitles", "srt"),
    "mix": ("mix", "audio_mix", "mix_report"),
    "master": ("master", "delivery", "final", "media"),
}

VISUAL_DEPENDENCIES = {
    "geometry": ["visual.face.primary"],
    "body": ["visual.geometry.primary"],
    "hair": ["visual.face.primary"],
    "makeup": ["visual.face.primary"],
    "wardrobe": ["visual.body.primary", "visual.geometry.primary"],
    "cinematography": ["visual.art.primary", "visual.location.primary"],
}
AUDIO_DEPENDENCIES = {
    "dialogue_delivery": ["audio.voice.primary"],
    "adr_lipsync": ["audio.voice.primary", "audio.dialogue_delivery.primary"],
    "foley": ["audio.ambience.primary"],
    "bgm_motif_cue": ["audio.dialogue_delivery.primary"],
}
POST_DEPENDENCIES = {
    "takes": ["post.coverage.primary"],
    "edl": ["post.coverage.primary", "post.takes.primary"],
    "picture_lock": ["post.edl.primary"],
    "vfx": ["post.picture_lock.primary"],
    "color": ["post.picture_lock.primary", "post.vfx.primary"],
    "captions": ["post.picture_lock.primary"],
    "mix": ["post.picture_lock.primary", "post.captions.primary"],
    "master": [
        "post.picture_lock.primary",
        "post.color.primary",
        "post.captions.primary",
        "post.mix.primary",
    ],
}


def stable_hash(value: Any) -> str:
    return canonical_json_sha256(value)


def _unique_strings(value: Any, default: list[str]) -> list[str]:
    if not isinstance(value, list):
        return list(default)
    result = list(dict.fromkeys(text for item in value if (text := str(item).strip())))
    return result or list(default)


def _legacy_state(value: Any, *, locked: bool) -> str:
    state = str(value or "").strip().lower()
    if state in NODE_STATES:
        return state
    if state == "approved" or locked:
        return "locked"
    if state == "candidate":
        return "review"
    return "draft"


def _valid_approval(
    approval_ref: Any,
    valid_approval_refs: set[str],
) -> bool:
    return isinstance(approval_ref, str) and approval_ref in valid_approval_refs


def _legacy_approval_reason() -> dict[str, str]:
    return {
        "code": "LEGACY_APPROVAL_UNVERIFIED",
        "reason": "historic Approved/locked state has no current hash-bound approval",
    }


def _extract_data(raw: Mapping[str, Any], fields: Iterable[str]) -> dict[str, Any]:
    return {field: copy.deepcopy(raw[field]) for field in fields if field in raw}


def _normalize_node(
    existing: Any,
    *,
    department: str,
    key: str,
    fallback_data: Any,
    fallback_state: str,
    fallback_approval_ref: str | None,
    dependencies: list[str],
    valid_approval_refs: set[str],
    historic_approval: bool,
) -> dict[str, Any]:
    node = copy.deepcopy(existing) if isinstance(existing, dict) else {}
    node_id = f"{department}.{key}.primary"
    data = copy.deepcopy(node.get("data", fallback_data))
    approval_ref = node.get("approval_ref", fallback_approval_ref)
    state = _legacy_state(node.get("state", fallback_state), locked=False)
    is_current = _valid_approval(approval_ref, valid_approval_refs)
    if state == "locked" and not is_current:
        state = "review"

    stale_reasons = copy.deepcopy(node.get("stale_reasons") or [])
    if (historic_approval or str(node.get("state") or "").lower() == "locked") and not is_current:
        reason = _legacy_approval_reason()
        if reason not in stale_reasons:
            stale_reasons.append(reason)

    node.update(
        {
            "id": node_id,
            "revision": max(1, int(node.get("revision") or 1)),
            "source_refs": _unique_strings(
                node.get("source_refs"), [f"legacy://{department}/{key}"]
            ),
            "dependency_refs": _unique_strings(node.get("dependency_refs"), dependencies)
            if dependencies
            else _unique_strings(node.get("dependency_refs"), []),
            "state": state,
            "approval_ref": approval_ref if isinstance(approval_ref, str) else None,
            "stale_reasons": stale_reasons,
            "data": data,
        }
    )
    node["hash"] = stable_hash(
        {
            "id": node["id"],
            "revision": node["revision"],
            "source_refs": node["source_refs"],
            "dependency_refs": node["dependency_refs"],
            "data": node["data"],
        }
    )
    return node


def migrate_department_bible(
    raw: Mapping[str, Any] | str | None,
    *,
    department: str,
    node_fields: Mapping[str, tuple[str, ...]],
    dependencies: Mapping[str, list[str]] | None = None,
    schema_version: int = 1,
    valid_approval_refs: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Add the current contract around legacy data without removing any field."""
    valid_refs = {str(item) for item in (valid_approval_refs or [])}
    if isinstance(raw, Mapping):
        output: dict[str, Any] = copy.deepcopy(dict(raw))
        legacy_text = None
    else:
        output = {}
        legacy_text = copy.deepcopy(raw)
        if raw is not None:
            output["legacy_payload"] = legacy_text

    locked = bool(output.get("locked"))
    old_state = output.get("state")
    historic_approval = locked or str(old_state or "").strip().lower() in {
        "approved",
        "locked",
    }
    approval_ref = output.get("approval_ref")
    approval_current = _valid_approval(approval_ref, valid_refs)
    state = _legacy_state(old_state, locked=locked)
    if historic_approval and not approval_current:
        state = "review"

    stale_reasons = copy.deepcopy(output.get("stale_reasons") or [])
    if historic_approval and not approval_current:
        reason = _legacy_approval_reason()
        if reason not in stale_reasons:
            stale_reasons.append(reason)

    existing_nodes = output.get("nodes") if isinstance(output.get("nodes"), dict) else {}
    nodes: dict[str, dict[str, Any]] = {}
    for key, fields in node_fields.items():
        data: Any = _extract_data(output, fields)
        if not data and legacy_text is not None:
            data = {"legacy_text": legacy_text}
        nodes[key] = _normalize_node(
            existing_nodes.get(key),
            department=department,
            key=key,
            fallback_data=data,
            fallback_state=state,
            fallback_approval_ref=approval_ref if isinstance(approval_ref, str) else None,
            dependencies=list((dependencies or {}).get(key, [])),
            valid_approval_refs=valid_refs,
            historic_approval=historic_approval,
        )

    output.update(
        {
            "schema_version": schema_version,
            "kind": f"{department}-bible",
            "revision": max(1, int(output.get("revision") or 1)),
            "state": state,
            "approval_ref": approval_ref if isinstance(approval_ref, str) else None,
            "stale_reasons": stale_reasons,
            "nodes": nodes,
        }
    )
    output["hash"] = stable_hash(
        {
            "kind": output["kind"],
            "revision": output["revision"],
            "nodes": output["nodes"],
        }
    )
    return output


def migrate_style_bible(
    raw: Mapping[str, Any] | str | None,
    *,
    valid_approval_refs: Iterable[str] | None = None,
) -> dict[str, Any]:
    return migrate_department_bible(
        raw,
        department="visual",
        node_fields=VISUAL_LEGACY_FIELDS,
        dependencies=VISUAL_DEPENDENCIES,
        schema_version=3,
        valid_approval_refs=valid_approval_refs,
    )


def migrate_audio_bible(
    raw: Mapping[str, Any] | str | None,
    *,
    valid_approval_refs: Iterable[str] | None = None,
) -> dict[str, Any]:
    return migrate_department_bible(
        raw,
        department="audio",
        node_fields=AUDIO_LEGACY_FIELDS,
        dependencies=AUDIO_DEPENDENCIES,
        valid_approval_refs=valid_approval_refs,
    )


def migrate_post_bible(
    raw: Mapping[str, Any] | str | None,
    *,
    valid_approval_refs: Iterable[str] | None = None,
) -> dict[str, Any]:
    return migrate_department_bible(
        raw,
        department="post",
        node_fields=POST_LEGACY_FIELDS,
        dependencies=POST_DEPENDENCIES,
        valid_approval_refs=valid_approval_refs,
    )


def _asset_id(value: Any, prefix: str, index: int) -> str:
    if isinstance(value, dict) and value.get("id"):
        return str(value["id"])
    raw = value.strip() if isinstance(value, str) and value.strip() else f"legacy-{index + 1}"
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_")[:64]
    return slug or f"{prefix}-{index + 1}"


def _asset_items(value: Any, kind: str) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        source = [
            ({"id": key, **item} if isinstance(item, dict) else {"id": key, "description": item})
            for key, item in value.items()
        ]
    elif isinstance(value, list):
        source = value
    else:
        source = []
    result: list[dict[str, Any]] = []
    for index, item in enumerate(source):
        normalized = copy.deepcopy(item) if isinstance(item, dict) else {"description": str(item)}
        asset_id = _asset_id(normalized if isinstance(item, dict) else item, kind, index)
        normalized["id"] = asset_id
        normalized.setdefault("ref", f"asset.{kind}.{asset_id}")
        normalized.setdefault("sourceRefs", [])
        normalized.setdefault("dependencyRefs", [])
        result.append(normalized)
    return result


def migrate_asset_registry(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """Normalize loose v1 registry items to typed v2 shapes without deleting metadata."""
    output = copy.deepcopy(dict(raw or {}))
    output["schema_version"] = 2
    output["kind"] = "asset-registry"
    output["characters"] = _asset_items(output.get("characters"), "character")
    output["locations"] = _asset_items(output.get("locations"), "location")
    output["props"] = _asset_items(output.get("props"), "prop")
    timeline = output.get("characterStatesTimeline")
    normalized_timeline: list[dict[str, Any]] = []
    for index, item in enumerate(timeline if isinstance(timeline, list) else []):
        event = copy.deepcopy(item) if isinstance(item, dict) else {"legacy_value": item}
        shot_id = str(event.get("shotId") or f"legacy-shot-{index + 1}")
        character_id = str(event.get("characterId") or "unknown")
        event.setdefault("id", f"asset.state.{character_id}.{shot_id}")
        event["shotId"] = shot_id
        event["characterId"] = character_id
        event.setdefault("characterRef", f"asset.character.{character_id}")
        event.setdefault("shotRef", shot_id)
        event.setdefault("wardrobeState", "full")
        normalized_timeline.append(event)
    output["characterStatesTimeline"] = normalized_timeline
    output.setdefault("counts", {})
    output.setdefault("consistency", {})
    return output
