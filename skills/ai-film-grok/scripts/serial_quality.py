#!/usr/bin/env python3
"""Auditable narrative and safety contract for optional serial productions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json, write_json

RECEIPT = Path("receipts/serial-quality.json")
_PLACEHOLDERS = {"", "todo", "tbd", "needs_authoring", "placeholder", "待填写", "待补"}
_MINOR_MARKERS = ("未成年", "未满18", "未滿18", "underage", "minor")
_INTIMACY_MARKERS = ("成人", "亲密", "性愛", "性爱", "性行为", "sexual", "sex")


def _authored(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().casefold() not in _PLACEHOLDERS
    if isinstance(value, list):
        return bool(value) and all(_authored(item) for item in value)
    return value is not None


def _issue(code: str, message: str, ref: str) -> dict[str, str]:
    return {"code": code, "message": message, "ref": ref}


def serial_enabled(spec: dict[str, Any]) -> bool:
    serial = spec.get("serial")
    return serial is True or (isinstance(serial, dict) and serial.get("enabled") is True)


def _beats(graph: dict[str, Any]) -> list[dict[str, Any]]:
    flat = graph.get("beats") or graph.get("beat_nodes") or []
    if isinstance(flat, list) and flat:
        return [item for item in flat if isinstance(item, dict)]
    return [
        beat
        for episode in graph.get("episodes") or []
        if isinstance(episode, dict)
        for scene in episode.get("scenes") or []
        if isinstance(scene, dict)
        for beat in scene.get("beats") or []
        if isinstance(beat, dict)
    ]


def _shots(spec: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        shot
        for scene in spec.get("scenes") or []
        if isinstance(scene, dict)
        for shot in scene.get("shots") or []
        if isinstance(shot, dict)
    ]


def _contains(text: str, markers: tuple[str, ...]) -> bool:
    value = text.casefold()
    return any(marker.casefold() in value for marker in markers)


def validate_serial(root: Path | str, *, write_receipt: bool = False) -> dict[str, Any]:
    """Validate serial mode without inferring creative intent or rights."""
    base = Path(root).expanduser().resolve()
    spec = read_json(base / "film-spec.json") or {}
    if not isinstance(spec, dict) or not serial_enabled(spec):
        return {"ok": True, "enabled": False, "action": "serial-validate", "errors": [], "warnings": []}

    graph = read_json(base / "drama-graph.json") or {}
    bible = read_json(base / "series-bible.json") or {}
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    if not isinstance(bible, dict):
        bible = {}
    contract = spec.get("episode_contract") if isinstance(spec.get("episode_contract"), dict) else {}
    serial = spec.get("serial") if isinstance(spec.get("serial"), dict) else {}

    for field in ("series_id", "title", "season_arc", "release_cadence"):
        if not _authored(bible.get(field)):
            errors.append(_issue("SERIES_BIBLE_FIELD_MISSING", f"series-bible.{field} must be authored", f"series-bible.{field}"))
    if serial.get("series_id") and bible.get("series_id") != serial.get("series_id"):
        errors.append(_issue("SERIES_ID_MISMATCH", "film-spec serial.series_id must match series-bible", "serial.series_id"))

    mature = bible.get("mature_content") if isinstance(bible.get("mature_content"), dict) else {}
    if mature.get("adult_only") is not True or mature.get("explicit_consent") is not True:
        errors.append(_issue("SERIES_ADULT_CONSENT_MISSING", "serial mature content requires adult_only and explicit_consent", "series-bible.mature_content"))
    participants = bible.get("characters") if isinstance(bible.get("characters"), list) else []
    if not participants:
        errors.append(_issue("SERIES_CHARACTERS_MISSING", "series-bible.characters is required", "series-bible.characters"))
    for index, character in enumerate(participants):
        ref = f"series-bible.characters[{index}]"
        if not isinstance(character, dict):
            errors.append(_issue("SERIES_CHARACTER_INVALID", "character must be an object", ref))
            continue
        for field in ("id", "relationship", "motivation", "contrast"):
            if not _authored(character.get(field)):
                errors.append(_issue("SERIES_CHARACTER_FIELD_MISSING", f"{field} must be authored", f"{ref}.{field}"))
        rights = character.get("rights") if isinstance(character.get("rights"), dict) else {}
        if character.get("adult_confirmed") is not True:
            errors.append(_issue("SERIES_CHARACTER_ADULT_UNCONFIRMED", "every character must be confirmed adult", ref))
        source_type = rights.get("source_type")
        if source_type not in {"original", "licensed"}:
            errors.append(_issue("SERIES_CHARACTER_RIGHTS_MISSING", "rights.source_type must be original or licensed", f"{ref}.rights"))
        elif source_type == "licensed" and not _authored(rights.get("source_ref")):
            errors.append(_issue("SERIES_LICENSE_EVIDENCE_MISSING", "licensed character requires rights.source_ref", f"{ref}.rights.source_ref"))

    for field in ("episode_id", "primary_event", "event_turn", "visible_outcome", "opening_hook", "ending_question", "expected_next_payoff", "title", "synopsis", "conflict_basis", "relationship_basis"):
        if not _authored(contract.get(field)):
            errors.append(_issue("EPISODE_CONTRACT_FIELD_MISSING", f"episode_contract.{field} must be authored", f"episode_contract.{field}"))
    opening = contract.get("opening_promise") if isinstance(contract.get("opening_promise"), dict) else {}
    for field in ("characters", "setting", "conflict", "evidence_shot_ids"):
        if not _authored(opening.get(field)):
            errors.append(_issue("OPENING_PROMISE_MISSING", f"opening_promise.{field} must be authored", f"episode_contract.opening_promise.{field}"))

    shots = _shots(spec)
    shot_ids = {str(shot.get("id") or shot.get("shot_id") or "") for shot in shots}
    evidence_ids = {str(item) for item in opening.get("evidence_shot_ids") or []}
    if evidence_ids and not evidence_ids <= shot_ids:
        errors.append(_issue("OPENING_EVIDENCE_UNKNOWN", "opening evidence shot ids must exist in film-spec", "episode_contract.opening_promise.evidence_shot_ids"))
    total = sum(float(shot.get("duration_sec") or shot.get("duration") or 0) for shot in shots)
    window = min(30.0, total)
    elapsed = 0.0
    opening_ids: set[str] = set()
    for shot in shots:
        elapsed += float(shot.get("duration_sec") or shot.get("duration") or 0)
        opening_ids.add(str(shot.get("id") or shot.get("shot_id") or ""))
        if elapsed >= window:
            break
    if evidence_ids and not evidence_ids <= opening_ids:
        errors.append(_issue("OPENING_EVIDENCE_LATE", "opening promise evidence must appear in first min(30 seconds, episode duration)", "episode_contract.opening_promise.evidence_shot_ids"))

    beats = _beats(graph if isinstance(graph, dict) else {})
    if not beats:
        errors.append(_issue("SERIAL_BEATS_MISSING", "serial episode requires beats", "drama-graph.beats"))
    for index, beat in enumerate(beats):
        if not _authored(beat.get("event_relation")):
            errors.append(_issue("BEAT_EVENT_RELATION_MISSING", "every beat must state how it serves the primary event", f"beat[{index}].event_relation"))

    episodes = bible.get("episodes") if isinstance(bible.get("episodes"), list) else []
    current = next((item for item in episodes if isinstance(item, dict) and item.get("episode_id") == contract.get("episode_id")), None)
    if current is None:
        errors.append(_issue("SERIES_EPISODE_LEDGER_MISSING", "current episode must be registered in series-bible.episodes", "series-bible.episodes"))
    elif int(current.get("episode_number") or 1) > 1 and not _authored(current.get("responds_to_hook_id")):
        errors.append(_issue("PREVIOUS_HOOK_UNRESOLVED", "later episodes must declare the prior hook they answer", "series-bible.episodes"))
    novelty = contract.get("novelty") if isinstance(contract.get("novelty"), dict) else {}
    for field in ("genre_tags", "setting", "differentiator", "signature"):
        if not _authored(novelty.get(field)):
            errors.append(_issue("NOVELTY_DECLARATION_MISSING", f"novelty.{field} must be authored", f"episode_contract.novelty.{field}"))
    signature = str(novelty.get("signature") or "").strip().casefold()
    if signature:
        for episode in episodes:
            if isinstance(episode, dict) and episode.get("episode_id") != contract.get("episode_id") and str(episode.get("novelty_signature") or "").strip().casefold() == signature:
                warnings.append(_issue("NOVELTY_SIGNATURE_COLLISION", "same novelty signature as another registered episode; human originality review required", "episode_contract.novelty.signature"))

    safety_text = "\n".join(str(value) for value in (bible, contract))
    if _contains(safety_text, _MINOR_MARKERS) and _contains(safety_text, _INTIMACY_MARKERS):
        errors.append(_issue("SERIAL_MINOR_INTIMACY_CONFLICT", "minor and intimacy signals cannot coexist", "series-bible/episode-contract"))
    report = {"ok": not errors, "enabled": True, "action": "serial-validate", "errors": errors, "warnings": warnings, "human_review_required": True, "opening_window_sec": window, "episodes_registered": len(episodes)}
    if write_receipt:
        write_json(base / RECEIPT, report)
    return report
