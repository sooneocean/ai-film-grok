#!/usr/bin/env python3
"""Offline, hash-bound creative contracts for the production control plane."""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

from music_cue import normalize_music_cue
from story_plan import normalize_story_graph
from util import (
    canonical_json_sha256,
    exclusive_file_lock,
    read_json,
    sha256_file,
    utc_now,
    write_json,
)

BRIEF_NAME = "creative-brief.json"
RECEIPT_DIR = ("receipts", "workshop")
RHYTHM_PROFILES = {
    "cinematic_medium",
    "short_video_medium_high",
    "high_density_hook",
    "slow_high_information",
}
REFERENCE_TYPES = {"character", "scene", "prop", "first_frame", "blocking", "video"}
INTERNAL_ID_RE = re.compile(
    r"(?:\basset[_-][a-z0-9_-]*\b|\b(?:CH\d+|SC\d+|PR\d+|MAP\d+|FF\d+)\b)", re.I
)


class WorkshopError(ValueError):
    """A workshop contract is invalid or cannot be compiled."""


class WorkshopConflict(WorkshopError):
    """A creative brief update did not use the current revision."""


def _path(root: Path, *parts: str) -> Path:
    return Path(root).expanduser().resolve().joinpath(*parts)


def _receipt_path(root: Path, name: str) -> Path:
    return _path(root, *RECEIPT_DIR, name)


def _source_ref(path: Path, *, kind: str) -> dict[str, str]:
    return {"kind": kind, "path": str(path), "sha256": sha256_file(path)}


def _content_hash(value: dict[str, Any]) -> str:
    return canonical_json_sha256(
        {key: item for key, item in value.items() if key != "content_sha256"}
    )


def _require_brief(root: Path) -> dict[str, Any]:
    brief = read_json(_path(root, BRIEF_NAME))
    if brief is None:
        raise WorkshopError("creative brief missing; run workshop intake first")
    return brief


def _validate_brief(payload: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(payload)
    required = ("platform", "rhythm_profile", "audience", "target_duration_sec", "genre")
    missing = [key for key in required if not str(result.get(key) or "").strip()]
    if missing:
        raise WorkshopError("creative brief missing: " + ", ".join(missing))
    rhythm = str(result["rhythm_profile"]).strip()
    if rhythm not in RHYTHM_PROFILES:
        raise WorkshopError(f"rhythm_profile must be one of {sorted(RHYTHM_PROFILES)}")
    duration = result["target_duration_sec"]
    if not isinstance(duration, (int, float)) or not 1 <= float(duration) <= 7200:
        raise WorkshopError("target_duration_sec must be between 1 and 7200")
    constraints = result.get("constraints", [])
    if not isinstance(constraints, list) or not all(isinstance(item, str) for item in constraints):
        raise WorkshopError("constraints must be a list of strings")
    result["constraints"] = [item.strip() for item in constraints if item.strip()]
    return result


def intake_workshop(
    root: Path, payload: dict[str, Any], *, expected_revision: int
) -> dict[str, Any]:
    """Persist the only workshop-authored source with optimistic revision control."""
    root = Path(root).expanduser().resolve()
    path = _path(root, BRIEF_NAME)
    with exclusive_file_lock(path):
        current = read_json(path)
        actual = int((current or {}).get("revision") or 0)
        if actual != expected_revision:
            raise WorkshopConflict(
                f"expected revision {expected_revision}, current revision is {actual}"
            )
        brief = _validate_brief(payload)
        now = utc_now()
        brief.update(
            {
                "schema_version": 1,
                "kind": "creative-brief",
                "revision": actual + 1,
                "created_at": (current or {}).get("created_at") or now,
                "updated_at": now,
            }
        )
        brief["content_sha256"] = canonical_json_sha256(
            {
                key: value
                for key, value in brief.items()
                if key not in {"content_sha256", "updated_at"}
            }
        )
        write_json(path, brief)
    return brief


def _load_graph(root: Path) -> tuple[dict[str, Any], dict[str, str]]:
    path = _path(root, "drama-graph.json")
    graph = read_json(path)
    if graph is None:
        raise WorkshopError(
            "drama-graph.json missing; workshop compile requires canonical story truth"
        )
    return normalize_story_graph(graph), _source_ref(path, kind="drama-graph")


def _shots(graph: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for episode in graph.get("episodes") or []:
        for scene in episode.get("scenes") or []:
            for beat in scene.get("beats") or []:
                for shot in beat.get("shots") or []:
                    if isinstance(shot, dict):
                        result.append(shot)
    return result


def _text(value: Any) -> str:
    return str(value or "").strip()


def _assets(shot: dict[str, Any]) -> list[dict[str, Any]]:
    raw = shot.get("reference_assets") or []
    if not isinstance(raw, list):
        return []
    output: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        output.append(
            {
                "asset_type": _text(item.get("asset_type")),
                "label": _text(item.get("label")),
                "use_only": _text(item.get("use_only")),
                "do_not_reference": _text(item.get("do_not_reference")),
                "single_instance": bool(item.get("single_instance")),
            }
        )
    return output


def _director_prompt(shot: dict[str, Any]) -> dict[str, Any]:
    film = shot.get("_film") if isinstance(shot.get("_film"), dict) else {}
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    if not dsl:
        dsl = film.get("dsl") if isinstance(film.get("dsl"), dict) else {}
    camera = dsl.get("camera")
    if isinstance(camera, dict):
        camera_text = ", ".join(
            f"{key}: {_text(value)}" for key, value in camera.items() if _text(value)
        )
    else:
        camera_text = _text(camera)
    return {
        "function": _text(
            shot.get("shot_function")
            or shot.get("narrativePurpose")
            or shot.get("dramaticFunction")
            or shot.get("dramatic_function")
        ),
        "subject": _text(dsl.get("subject") or shot.get("subject")),
        "camera": camera_text,
        "action": _text(dsl.get("action") or shot.get("action")),
        "lighting": _text(dsl.get("lighting") or shot.get("lighting")),
        "sound": _text(
            shot.get("sound_design") or shot.get("dialogue") or shot.get("nar") or film.get("nar")
        ),
        "end_state": _text(shot.get("end_state") or shot.get("state_delta")),
        "references": _assets(shot),
    }


def diagnose_workshop(root: Path) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    brief = _require_brief(root)
    graph, source = _load_graph(root)
    findings: list[dict[str, Any]] = []
    for shot in _shots(graph):
        dialogue = _text(shot.get("dialogue"))
        purpose = _text(shot.get("narrativePurpose") or shot.get("dramatic_function"))
        if dialogue and not purpose:
            findings.append(
                {
                    "shot_id": shot.get("id"),
                    "dimension": "conflict_drive",
                    "code": "PURPOSE_MISSING",
                }
            )
        if dialogue and len(dialogue) > 35 and not any(mark in dialogue for mark in "，。！？；…"):
            findings.append(
                {
                    "shot_id": shot.get("id"),
                    "dimension": "readability",
                    "code": "LONG_UNBROKEN_DIALOGUE",
                }
            )
        if dialogue and not _text((shot.get("performance") or {}).get("intent")):
            findings.append(
                {"shot_id": shot.get("id"), "dimension": "voice_print", "code": "DELIVERY_MISSING"}
            )
    report = {
        "schema_version": 1,
        "kind": "workshop-diagnosis",
        "created_at": utc_now(),
        "brief_sha256": brief["content_sha256"],
        "source": source,
        "seven_dimensions": [
            "voice_print",
            "subtext",
            "conflict_drive",
            "genre_voice",
            "information_efficiency",
            "readability",
            "memorable_line",
        ],
        "findings": findings,
        "mutated_story": False,
    }
    report["content_sha256"] = _content_hash(report)
    write_json(_receipt_path(root, "diagnose.json"), report)
    return report


def compile_workshop(root: Path) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    brief = _require_brief(root)
    graph, graph_ref = _load_graph(root)
    compiled_shots: list[dict[str, Any]] = []
    cues: list[dict[str, Any]] = []
    for shot in _shots(graph):
        prompt = _director_prompt(shot)
        compiled_shots.append(
            {
                "shot_id": _text(shot.get("id")),
                "duration_sec": shot.get("duration_sec")
                or shot.get("targetDuration")
                or film_duration(shot),
                "director_prompt": prompt,
            }
        )
        cue = normalize_music_cue(
            shot.get("music_cue") if isinstance(shot.get("music_cue"), dict) else {}, shot=shot
        )
        cues.append(
            {
                "shot_id": _text(shot.get("id")),
                "music": cue,
                "dialogue_priority": bool(prompt["sound"]),
                "silence_allowed": bool(shot.get("silence_beat")),
            }
        )
    book_path = _path(root, "production-book.json")
    sources = [graph_ref, _source_ref(_path(root, BRIEF_NAME), kind="creative-brief")]
    if book_path.is_file():
        sources.append(_source_ref(book_path, kind="production-book"))
    packet = {
        "schema_version": 1,
        "kind": "workshop-director-packet",
        "created_at": utc_now(),
        "provider_policy": "provider_neutral",
        "provider_default_changed": False,
        "sources": sources,
        "brief": {
            key: brief[key]
            for key in (
                "platform",
                "rhythm_profile",
                "audience",
                "target_duration_sec",
                "genre",
                "constraints",
            )
        },
        "asset_handoff": [
            {"shot_id": item["shot_id"], "references": item["director_prompt"]["references"]}
            for item in compiled_shots
        ],
        "shots": compiled_shots,
        "sound_cue_sheet": cues,
    }
    packet["content_sha256"] = _content_hash(packet)
    write_json(_receipt_path(root, "compile.json"), packet)
    return packet


def _issue(code: str, shot_id: str, message: str) -> dict[str, str]:
    return {"code": code, "shot_id": shot_id, "message": message}


def film_duration(shot: dict[str, Any]) -> Any:
    film = shot.get("_film") if isinstance(shot.get("_film"), dict) else {}
    return film.get("duration_sec")


def validate_workshop(root: Path, *, strict: bool = False) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    packet = read_json(_receipt_path(root, "compile.json")) or compile_workshop(root)
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    if _text(packet.get("content_sha256")) != _content_hash(packet):
        errors.append(
            _issue(
                "WORKSHOP_PACKET_TAMPERED",
                "",
                "compiled workshop packet content hash does not match its payload",
            )
        )
    for source in packet.get("sources") or []:
        path = Path(_text(source.get("path")))
        expected = _text(source.get("sha256"))
        if not path.is_file() or not expected or sha256_file(path) != expected:
            errors.append(
                _issue(
                    "WORKSHOP_SOURCE_STALE",
                    "",
                    f"compiled packet source is missing or changed: {path}",
                )
            )
    for item in packet.get("shots") or []:
        shot_id = _text(item.get("shot_id"))
        duration = item.get("duration_sec")
        prompt = (
            item.get("director_prompt") if isinstance(item.get("director_prompt"), dict) else {}
        )
        problems: list[tuple[str, str]] = []
        if not isinstance(duration, (int, float)) or float(duration) <= 0:
            problems.append(("SHOT_DURATION_INVALID", "shot duration must be positive"))
        elif float(duration) > 15:
            problems.append(("UNIT_DURATION_EXCEEDED", "a platform unit may not exceed 15 seconds"))
        for field in (
            "function",
            "subject",
            "camera",
            "action",
            "lighting",
            "sound",
            "end_state",
        ):
            if not _text(prompt.get(field)):
                problems.append(
                    ("DIRECTOR_PROMPT_FIELD_MISSING", f"director prompt missing {field}")
                )
        combined = " ".join(
            _text(prompt.get(field))
            for field in (
                "function",
                "subject",
                "camera",
                "action",
                "lighting",
                "sound",
                "end_state",
            )
        )
        if INTERNAL_ID_RE.search(combined):
            problems.append(
                ("PROMPT_INTERNAL_ID", "director prompt contains an internal asset identifier")
            )
        references = prompt.get("references") if isinstance(prompt.get("references"), list) else []
        if len(references) > 9:
            problems.append(("REFERENCE_IMAGE_LIMIT", "a prompt unit may use at most 9 references"))
        for reference in references:
            if reference.get("asset_type") not in REFERENCE_TYPES or not _text(
                reference.get("use_only")
            ):
                problems.append(
                    (
                        "REFERENCE_ROLE_INVALID",
                        "reference needs a known type and use_only responsibility",
                    )
                )
            if (
                reference.get("asset_type") == "prop"
                and reference.get("single_instance")
                and not _text(reference.get("do_not_reference"))
            ):
                problems.append(
                    (
                        "PROP_SINGLE_INSTANCE_UNCLEAR",
                        "single-instance prop needs a do_not_reference rule",
                    )
                )
        if isinstance(duration, (int, float)) and float(duration) > 0 and prompt["sound"]:
            rate = len(prompt["sound"]) / float(duration)
            if rate > 6:
                problems.append(
                    (
                        "DIALOGUE_RATE_HIGH",
                        f"dialogue rate {rate:.1f} characters/sec exceeds the 6 character/sec risk limit",
                    )
                )
        if (
            isinstance(duration, (int, float))
            and float(duration) > 10
            and not _text(prompt.get("function"))
        ):
            problems.append(
                (
                    "SLOW_SHOT_FUNCTION_MISSING",
                    "a shot longer than 10 seconds needs a concrete dramatic function",
                )
            )
        target = errors if strict else warnings
        target.extend(_issue(code, shot_id, message) for code, message in problems)
    report = {
        "schema_version": 1,
        "kind": "workshop-validation",
        "created_at": utc_now(),
        "packet_sha256": packet.get("content_sha256"),
        "strict": strict,
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
    }
    report["content_sha256"] = _content_hash(report)
    write_json(_receipt_path(root, "validate.json"), report)
    return report


def _render_prompt(prompt: dict[str, Any], *, target: str) -> str:
    label = {
        "grok": "Grok Imagine director prompt",
        "frw-seedance": "FRW/Seedance director prompt",
        "generic": "Director prompt",
    }[target]
    fields = [
        ("Function", prompt.get("function")),
        ("Subject", prompt.get("subject")),
        ("Camera", prompt.get("camera")),
        ("Action", prompt.get("action")),
        ("Lighting", prompt.get("lighting")),
        ("Sound", prompt.get("sound")),
        ("End state", prompt.get("end_state")),
    ]
    parts = [label + "."] + [f"{name}: {_text(value)}." for name, value in fields if _text(value)]
    for ref in prompt.get("references") or []:
        parts.append(
            f"Reference {ref['asset_type']}: use only {_text(ref.get('use_only'))}; do not inherit {_text(ref.get('do_not_reference')) or 'unlisted details'}."
        )
    return " ".join(parts)


def export_workshop(root: Path, *, target: str) -> dict[str, Any]:
    if target not in {"grok", "frw-seedance", "generic"}:
        raise WorkshopError("target must be grok|frw-seedance|generic")
    root = Path(root).expanduser().resolve()
    packet = read_json(_receipt_path(root, "compile.json")) or compile_workshop(root)
    validation = validate_workshop(root, strict=True)
    if not validation["ok"]:
        codes = ", ".join(item["code"] for item in validation["errors"])
        raise WorkshopError(f"workshop export blocked by validation: {codes}")
    prompts = [
        {"shot_id": item["shot_id"], "text": _render_prompt(item["director_prompt"], target=target)}
        for item in packet.get("shots") or []
    ]
    report = {
        "schema_version": 1,
        "kind": "workshop-prompt-export",
        "created_at": utc_now(),
        "target": target,
        "packet_sha256": packet.get("content_sha256"),
        "external_action": False,
        "provider_default_changed": False,
        "prompts": prompts,
    }
    report["content_sha256"] = _content_hash(report)
    write_json(_receipt_path(root, f"export-{target}.json"), report)
    return report
