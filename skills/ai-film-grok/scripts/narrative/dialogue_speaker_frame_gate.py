#!/usr/bin/env python3
"""Dialogue speaker ↔ on-camera picture contract (huangdao v3 §H).

on_camera dialogue shots: speaker must be the visual subject (dsl.subject/cast),
match audio_cues speaker, and stay stable within a beat in heat windows.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from production_gates import ProductionGateError
from util import read_json

DIALOGUE_WINDOW_HEAT = frozenset({"foreplay", "act", "climax"})
_ON_CAMERA = frozenset({"on_camera", "on-camera", "on cam"})


def _norm(s: Any) -> str:
    return " ".join(str(s or "").strip().lower().split())


def _cast_ids(spec: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for key in ("cast", "characters", "cast_voices"):
        block = spec.get(key)
        if isinstance(block, dict):
            for k, v in block.items():
                out.add(_norm(k))
                if isinstance(v, dict):
                    for idk in ("id", "name", "speaker", "character"):
                        if v.get(idk):
                            out.add(_norm(v.get(idk)))
        elif isinstance(block, list):
            for item in block:
                if isinstance(item, str):
                    out.add(_norm(item))
                elif isinstance(item, dict):
                    for idk in ("id", "name", "speaker", "character"):
                        if item.get(idk):
                            out.add(_norm(item.get(idk)))
    return {x for x in out if x}


def _iter_shots(spec: dict[str, Any]) -> list[dict[str, Any]]:
    shots: list[dict[str, Any]] = []
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for sh in scene.get("shots") or []:
            if isinstance(sh, dict) and sh.get("id"):
                shots.append(sh)
    return shots


def _screen_mode(shot: dict[str, Any]) -> str:
    sm = _norm(shot.get("screen_mode"))
    if sm:
        return sm
    cues = shot.get("audio_cues") if isinstance(shot.get("audio_cues"), list) else []
    for cue in cues:
        if isinstance(cue, dict) and str(cue.get("spoken_text") or "").strip():
            return _norm(cue.get("screen_mode") or "on_camera")
    if shot.get("speaker_on_camera") is True or shot.get("lipsync") is True:
        return "on_camera"
    return sm


def _spoken_cues(shot: dict[str, Any]) -> list[dict[str, Any]]:
    cues = shot.get("audio_cues") if isinstance(shot.get("audio_cues"), list) else []
    out: list[dict[str, Any]] = []
    for cue in cues:
        if not isinstance(cue, dict):
            continue
        if not str(cue.get("spoken_text") or cue.get("text") or "").strip():
            continue
        lt = _norm(cue.get("line_type") or "dialogue")
        if lt in {"sfx", "ambience", "music", "bed", "foley"}:
            continue
        out.append(cue)
    return out


def _subject_blob(shot: dict[str, Any]) -> str:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    parts: list[str] = []
    for key in ("subject", "cast", "focal_character", "characters"):
        val = dsl.get(key) if key in dsl else shot.get(key)
        if isinstance(val, list):
            parts.extend(str(x) for x in val)
        elif val:
            parts.append(str(val))
    return _norm(" ".join(parts))


def lint_dialogue_speaker_frame(
    spec: dict[str, Any],
    *,
    window_strict: bool | None = None,
) -> dict[str, Any]:
    """Return audit report; does not raise."""
    vo = _norm(spec.get("vo_mode"))
    if window_strict is None:
        window_strict = spec.get("dialogue_window_strict") is True or (
            spec.get("dialogue_window_strict") is not False and vo == "dialogue_drama"
        )
    cast_ids = _cast_ids(spec)
    violations: list[dict[str, Any]] = []
    window_violations: list[dict[str, Any]] = []
    shots = _iter_shots(spec)
    prev_on: dict[str, Any] | None = None

    for shot in shots:
        sid = str(shot.get("id"))
        screen = _screen_mode(shot)
        cues = _spoken_cues(shot)
        has_dialogue = bool(cues) or bool(
            str(
                shot.get("dialogue") or shot.get("dialogue_zh") or shot.get("dialogue_ja") or ""
            ).strip()
        )
        if screen not in _ON_CAMERA or not has_dialogue:
            prev_on = None if screen not in _ON_CAMERA else prev_on
            continue

        speaker = _norm(shot.get("speaker") or shot.get("dialogue_speaker"))
        if not speaker:
            violations.append(
                {
                    "shot_id": sid,
                    "code": "SPEAKER_MISSING",
                    "msg": "on_camera dialogue shot missing speaker",
                }
            )
        elif cast_ids and speaker not in cast_ids:
            # soft warn style if cast registry exists and speaker not listed
            violations.append(
                {
                    "shot_id": sid,
                    "code": "SPEAKER_NOT_IN_CAST",
                    "msg": f"speaker {speaker!r} not in cast registry",
                }
            )

        for cue in cues:
            cue_sp = _norm(cue.get("speaker") or cue.get("character"))
            if speaker and cue_sp and cue_sp != speaker:
                violations.append(
                    {
                        "shot_id": sid,
                        "code": "SPEAKER_CUE_MISMATCH",
                        "msg": f"shot speaker {speaker!r} != cue speaker {cue_sp!r}",
                    }
                )

        if speaker:
            blob = _subject_blob(shot)
            if blob and speaker not in blob and speaker.split("_")[0] not in blob:
                # also accept bare name tokens
                token_ok = any(tok and tok in blob for tok in speaker.replace("-", " ").split())
                if not token_ok:
                    violations.append(
                        {
                            "shot_id": sid,
                            "code": "SPEAKER_NOT_IN_SUBJECT",
                            "msg": (
                                f"on_camera speaker {speaker!r} not reflected in "
                                "dsl.subject/cast (risk: A lines / B body)"
                            ),
                        }
                    )

        heat = _norm(shot.get("heat_phase"))
        beat = str(shot.get("beat_id") or shot.get("story_beat") or "").strip()
        if window_strict and heat in DIALOGUE_WINDOW_HEAT and prev_on:
            prev_sp = _norm(prev_on.get("speaker"))
            prev_beat = str(prev_on.get("beat_id") or prev_on.get("story_beat") or "").strip()
            prev_heat = _norm(prev_on.get("heat_phase"))
            if (
                prev_heat in DIALOGUE_WINDOW_HEAT
                and beat
                and beat == prev_beat
                and speaker
                and prev_sp
                and speaker != prev_sp
            ):
                window_violations.append(
                    {
                        "shot_id": sid,
                        "prev_shot_id": prev_on.get("id"),
                        "code": "DIALOGUE_WINDOW_SPEAKER_FLIP",
                        "msg": (
                            f"adjacent on_camera speakers flip {prev_sp!r}→{speaker!r} "
                            f"on same beat_id={beat!r} inside heat window"
                        ),
                    }
                )

        prev_on = {
            "id": sid,
            "speaker": speaker,
            "beat_id": beat,
            "story_beat": shot.get("story_beat"),
            "heat_phase": heat,
        }

    return {
        "schema_version": 1,
        "kind": "dialogue-speaker-frame",
        "ok": not violations and not window_violations,
        "vo_mode": vo or None,
        "window_strict": bool(window_strict),
        "checked_shots": len(shots),
        "violations": violations,
        "window_violations": window_violations,
    }


def assert_dialogue_speaker_frame_contract(
    root: Path | str | None = None,
    *,
    spec: dict[str, Any] | None = None,
    hard: bool | None = None,
) -> dict[str, Any]:
    """Lint + optional hard raise for dialogue_drama / explicit strict."""
    data = spec
    if data is None:
        if root is None:
            raise ProductionGateError("speaker-frame gate needs root or spec")
        path = Path(root).expanduser().resolve() / "film-spec.json"
        data = read_json(path) or {}
        if not isinstance(data, dict) or not data:
            raise ProductionGateError(f"speaker-frame gate: missing film-spec at {path}")

    report = lint_dialogue_speaker_frame(data)
    vo = _norm(data.get("vo_mode"))
    if hard is None:
        hard = (
            data.get("dialogue_window_strict") is True
            or data.get("speaker_frame_strict") is True
            or (
                vo == "dialogue_drama"
                and data.get("speaker_frame_strict") is not False
                and (
                    _norm(data.get("heat_scale")) in {"max", "hot", "extreme"}
                    or data.get("adult_max_iron") is True
                )
            )
        )

    bad = list(report.get("violations") or []) + list(report.get("window_violations") or [])
    report["hard"] = bool(hard)
    if hard and bad:
        codes = sorted({str(v.get("code")) for v in bad})
        raise ProductionGateError(
            "dialogue speaker-frame gate failed: "
            + ", ".join(codes)
            + f" ({len(bad)} issue(s)); fix speaker/subject alignment or set "
            "speaker_frame_strict:false / dialogue_window_strict:false"
        )
    return report


__all__ = [
    "DIALOGUE_WINDOW_HEAT",
    "assert_dialogue_speaker_frame_contract",
    "lint_dialogue_speaker_frame",
]
