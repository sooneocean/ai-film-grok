"""Validate agent-authored T2T story reception packages.

The text transformation itself is intentionally performed by the ai-film-grok
agent.  This module keeps that creative step provider-free while ensuring the
result remains traceable and safe to hand to the deterministic planner.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
KIND = "story-reception"
PROVENANCE_VALUES = frozenset({"source_supported", "creative_suggestion"})
TREATMENT_FIELDS = (
    "title",
    "logline",
    "theme",
    "protagonist_goal",
    "opposition",
    "stakes",
    "climax_choice",
    "ending_hook",
    "emotional_arc",
    "act_structure",
    "pace_chart",
    "visual_motifs",
    "scene_beats",
    "sound_intent",
    "camera_intent",
    "planning_text",
    "mature_intimacy",
)
_MINOR_MARKERS = ("未成年", "未滿18", "未满18", "underage", "minor")
_INTIMACY_MARKERS = ("成人", "亲密", "性愛", "性爱", "性行为", "sexual", "sex", "r18")


class ReceptionError(ValueError):
    """A story reception package is malformed or cannot be trusted."""


def _nonempty(value: object) -> bool:
    return bool(value and str(value).strip()) if isinstance(value, str) else bool(value)


def source_sha256(raw_text: str) -> str:
    return hashlib.sha256(raw_text.encode("utf-8")).hexdigest()


def _contains_marker(text: str, markers: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in markers)


def validate_story_reception(payload: object) -> dict[str, Any]:
    """Validate and return a reception package without changing its content."""
    if not isinstance(payload, dict):
        raise ReceptionError("story reception must be a JSON object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ReceptionError(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("kind") != KIND:
        raise ReceptionError(f"kind must be {KIND!r}")

    source = payload.get("source")
    if not isinstance(source, dict):
        raise ReceptionError("source must be an object")
    raw_text = source.get("raw_text")
    if not isinstance(raw_text, str) or not raw_text.strip():
        raise ReceptionError("source.raw_text is required")
    expected = source.get("sha256")
    actual = source_sha256(raw_text)
    if not isinstance(expected, str) or expected != actual:
        raise ReceptionError("source.sha256 does not match source.raw_text")
    if not _nonempty(source.get("language")) or not _nonempty(source.get("source_ref")):
        raise ReceptionError("source.language and source.source_ref are required")

    fidelity = payload.get("fidelity")
    if not isinstance(fidelity, dict):
        raise ReceptionError("fidelity must be an object")
    for field in ("immutable_facts", "protected_dialogue", "explicit_constraints", "unknowns"):
        if not isinstance(fidelity.get(field), list):
            raise ReceptionError(f"fidelity.{field} must be an array")

    treatment = payload.get("treatment")
    if not isinstance(treatment, dict):
        raise ReceptionError("treatment must be an object")
    if (
        not isinstance(treatment.get("planning_text"), str)
        or not treatment["planning_text"].strip()
    ):
        raise ReceptionError("treatment.planning_text is required")
    provenance = treatment.get("provenance")
    if not isinstance(provenance, dict):
        raise ReceptionError("treatment.provenance must be an object")
    for field in TREATMENT_FIELDS:
        if _nonempty(treatment.get(field)) and provenance.get(field) not in PROVENANCE_VALUES:
            raise ReceptionError(
                f"treatment.provenance.{field} must be source_supported or creative_suggestion"
            )

    mature = treatment.get("mature_intimacy")
    safety_text = f"{raw_text}\n{treatment['planning_text']}"
    has_minor_signal = _contains_marker(safety_text, _MINOR_MARKERS)
    has_intimacy_signal = _contains_marker(safety_text, _INTIMACY_MARKERS)
    if has_minor_signal and has_intimacy_signal:
        raise ReceptionError("story reception cannot combine minor and intimacy signals")
    if has_intimacy_signal and not isinstance(mature, dict):
        raise ReceptionError("adult intimacy signals require treatment.mature_intimacy")
    if has_intimacy_signal and mature.get("enabled") is not True:
        raise ReceptionError("adult intimacy signals require mature_intimacy.enabled=true")
    if mature is not None:
        if not isinstance(mature, dict):
            raise ReceptionError("treatment.mature_intimacy must be an object")
        if mature.get("enabled"):
            if mature.get("adult_only") is not True:
                raise ReceptionError("treatment.mature_intimacy.adult_only must be true")
            if mature.get("participants_confirmed_adult") is not True:
                raise ReceptionError(
                    "treatment.mature_intimacy.participants_confirmed_adult must be true"
                )
            if mature.get("consent") != "explicit":
                raise ReceptionError("treatment.mature_intimacy.consent must be explicit")
            if not isinstance(mature.get("visual_focus"), list) or not mature["visual_focus"]:
                raise ReceptionError("treatment.mature_intimacy.visual_focus is required")
    return payload


def load_story_reception(path: Path) -> dict[str, Any]:
    """Load and validate a package written by the agent T2T receiver."""
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise ReceptionError(f"story reception file not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReceptionError(f"story reception is not valid JSON: {path}") from exc
    return validate_story_reception(payload)


def reception_summary(payload: dict[str, Any], *, path: Path | None = None) -> dict[str, Any]:
    """Return the minimal provenance safe to copy into downstream receipts."""
    source = payload["source"]
    treatment = payload["treatment"]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "path": str(path) if path else None,
        "source_ref": source["source_ref"],
        "source_sha256": source["sha256"],
        "language": source["language"],
        "fidelity": {
            "immutable_facts": list(payload["fidelity"]["immutable_facts"]),
            "protected_dialogue": list(payload["fidelity"]["protected_dialogue"]),
            "explicit_constraints": list(payload["fidelity"]["explicit_constraints"]),
            "unknowns": list(payload["fidelity"]["unknowns"]),
        },
        "mature_intimacy": dict(treatment.get("mature_intimacy") or {}),
        "provenance": dict(treatment.get("provenance") or {}),
    }


def story_contract_seed(payload: dict[str, Any]) -> dict[str, Any]:
    """Map the agent's treatment into existing canonical story fields."""
    treatment = payload["treatment"]
    return {
        key: treatment[key]
        for key in (
            "theme",
            "protagonist_goal",
            "opposition",
            "stakes",
            "climax_choice",
            "ending_hook",
            "emotional_arc",
            "act_structure",
            "pace_chart",
        )
        if _nonempty(treatment.get(key))
    }
