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


def speaker_frame_hard_enabled(spec: dict[str, Any]) -> bool:
    """I2.3 · when speaker-frame violations are hard (fail-closed).

    Hard when:
    - speaker_frame_strict / dialogue_window_strict is True, or
    - vo_mode=dialogue_drama AND heat max/hot/extreme OR adult_max_iron OR genre adult

    Explicit escape: ``speaker_frame_strict: false`` (takes precedence unless
    dialogue_window_strict is True).
    """
    if not isinstance(spec, dict):
        return False
    if spec.get("dialogue_window_strict") is True:
        return True
    if spec.get("speaker_frame_strict") is False:
        return False
    if spec.get("speaker_frame_strict") is True:
        return True
    vo = _norm(spec.get("vo_mode"))
    if vo != "dialogue_drama":
        return False
    heat = _norm(spec.get("heat_scale"))
    genre = _norm(spec.get("genre"))
    if heat in {"max", "hot", "extreme"}:
        return True
    if spec.get("adult_max_iron") is True:
        return True
    if genre in {"adult", "erotic", "nsfw", "ecchi"}:
        return True
    return False


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
    if hard is None:
        hard = speaker_frame_hard_enabled(data)

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
    # Honesty-rail R2: record pass/fail provenance when film root known
    if root is not None and not bad:
        try:
            from core.attestation_audit import write_attestation

            write_attestation(
                root,
                kind="speaker_frame",
                shot_id="_film",
                still_path=str(Path(root).expanduser().resolve() / "film-spec.json"),
                anatomy_safe=None,
                note=f"speaker_frame ok hard={bool(hard)} shots={report.get('shot_count')}",
                source="assert_dialogue_speaker_frame_contract",
            )
        except Exception:
            pass
    return report


# --- Wave 2 · dialogue still recipe (on_camera → speaker face/MCU, not fullbody meat) ---

_WIDE_SIZES = frozenset(
    {
        "ws",
        "wide",
        "wideshot",
        "wide_shot",
        "full",
        "fullbody",
        "full_body",
        "establishing",
        "els",
        "extreme_wide",
        "long",
        "long_shot",
        "ls",
    }
)
_CLOSE_OK = frozenset(
    {
        "cu",
        "ecu",
        "mcu",
        "close",
        "closeup",
        "close_up",
        "close-up",
        "medium_close",
        "medium_closeup",
        "ms",
        "medium",
        "medium_shot",
    }
)


def is_on_camera_dialogue_shot(shot: dict[str, Any] | None) -> bool:
    if not isinstance(shot, dict):
        return False
    screen = _screen_mode(shot)
    if screen not in _ON_CAMERA:
        return False
    if _spoken_cues(shot):
        return True
    return bool(
        str(
            shot.get("spoken_text")
            or shot.get("dialogue")
            or shot.get("dialogue_zh")
            or ""
        ).strip()
    )


def _shot_size_token(shot: dict[str, Any]) -> str:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    cam = dsl.get("camera") if isinstance(dsl.get("camera"), dict) else {}
    raw = (
        shot.get("shot_size")
        or dsl.get("shot_size")
        or cam.get("shot_size")
        or shot.get("framing")
        or ""
    )
    return str(raw).strip().lower().replace(" ", "_").replace("-", "_")


def lint_dialogue_still_recipe(shot: dict[str, Any] | None) -> dict[str, Any]:
    """Field-level still recipe for on_camera dialogue (no pixels).

    Hard codes (when speaker_frame hard):
      SPEAKER_MISSING_FOR_STILL — no speaker on on_camera dialogue
      DIALOGUE_STILL_WIDE_FRAME — WS/fullbody size on talking head
    Soft:
      DIALOGUE_STILL_SIZE_UNSPECIFIED — no shot_size (prefer MCU/CU)
    """
    issues: list[dict[str, Any]] = []
    if not is_on_camera_dialogue_shot(shot):
        return {
            "schema_version": 1,
            "kind": "dialogue-still-recipe",
            "ok": True,
            "applies": False,
            "issues": [],
        }
    sh = shot if isinstance(shot, dict) else {}
    sid = str(sh.get("id") or "")
    speaker = _norm(sh.get("speaker") or sh.get("dialogue_speaker"))
    if not speaker:
        issues.append(
            {
                "shot_id": sid,
                "code": "SPEAKER_MISSING_FOR_STILL",
                "severity": "hard",
                "msg": "on_camera dialogue still requires named speaker (face of speaker)",
            }
        )
    size = _shot_size_token(sh)
    if size in _WIDE_SIZES or "fullbody" in size or size.endswith("_ws"):
        issues.append(
            {
                "shot_id": sid,
                "code": "DIALOGUE_STILL_WIDE_FRAME",
                "severity": "hard",
                "msg": (
                    f"on_camera dialogue still uses wide/fullbody size={size!r}; "
                    "use face MCU/CU of speaker (禁全身办事 still 挂台词)"
                ),
            }
        )
    elif not size:
        issues.append(
            {
                "shot_id": sid,
                "code": "DIALOGUE_STILL_SIZE_UNSPECIFIED",
                "severity": "soft",
                "msg": "on_camera dialogue should set shot_size MCU/CU for still recipe",
            }
        )
    elif size not in _CLOSE_OK and "close" not in size and size not in {"ms", "medium"}:
        issues.append(
            {
                "shot_id": sid,
                "code": "DIALOGUE_STILL_SIZE_RISKY",
                "severity": "soft",
                "msg": f"dialogue still size={size!r} — prefer MCU/CU speaker face",
            }
        )
    hard_codes = [i for i in issues if i.get("severity") == "hard"]
    return {
        "schema_version": 1,
        "kind": "dialogue-still-recipe",
        "ok": not hard_codes,
        "applies": True,
        "shot_id": sid or None,
        "speaker": speaker or None,
        "shot_size": size or None,
        "issues": issues,
    }


def assert_dialogue_still_for_register(
    root: Path | str,
    shot_id: str,
    *,
    hard: bool | None = None,
) -> dict[str, Any]:
    """Fail-closed still recipe for on_camera dialogue when speaker-frame hard."""
    base = Path(root).expanduser().resolve()
    spec = read_json(base / "film-spec.json") or {}
    if not isinstance(spec, dict):
        return {"ok": True, "skipped": True, "reason": "no_spec"}
    shot = None
    for sh in _iter_shots(spec):
        if str(sh.get("id") or "") == str(shot_id):
            shot = sh
            break
    if shot is None:
        return {"ok": True, "skipped": True, "reason": "shot_not_in_spec"}
    report = lint_dialogue_still_recipe(shot)
    if hard is None:
        hard = speaker_frame_hard_enabled(spec)
    report["hard"] = bool(hard)
    hard_issues = [
        i for i in (report.get("issues") or []) if i.get("severity") == "hard"
    ]
    if hard and hard_issues:
        codes = sorted({str(i.get("code")) for i in hard_issues})
        raise ProductionGateError(
            "dialogue still recipe failed for "
            f"{shot_id}: {', '.join(codes)}; use speaker face MCU/CU still "
            "(escape speaker_frame_strict:false)"
        )
    return report


# --- Wave 2 · prompt must not ban speech when shot has spoken_text ---

_NO_SPEECH_PATTERNS = (
    "no speech",
    "no talking",
    "without speech",
    "silent mouth",
    "mouth closed no",
    "do not speak",
    "doesn't speak",
    "does not speak",
    "mute character",
    "no dialogue",
    "禁说话",
    "不要开口",
    "闭嘴不语",
    "无对白",
    "不说话",
)


def lint_dialogue_prompt_speech(
    prompt: str,
    shot: dict[str, Any] | None,
) -> dict[str, Any]:
    """If shot has spoken dialogue, custom/I2V prompt must not say no-speech."""
    spoken = False
    if isinstance(shot, dict):
        spoken = is_on_camera_dialogue_shot(shot) or bool(
            str(shot.get("spoken_text") or "").strip()
        )
        if not spoken:
            for cue in shot.get("audio_cues") or []:
                if isinstance(cue, dict) and str(
                    cue.get("spoken_text") or cue.get("text") or ""
                ).strip():
                    spoken = True
                    break
    if not spoken:
        return {"ok": True, "applies": False, "hits": []}
    low = str(prompt or "").lower()
    hits = [p for p in _NO_SPEECH_PATTERNS if p in low]
    return {
        "ok": not hits,
        "applies": True,
        "hits": hits,
        "code": "DIALOGUE_PROMPT_NO_SPEECH" if hits else None,
        "msg": (
            f"dialogue shot prompt forbids speech ({hits}); remove no-speech lines "
            "and keep Mandarin spoken delivery"
            if hits
            else None
        ),
    }


def assert_dialogue_prompt_allows_speech(
    prompt: str,
    shot: dict[str, Any] | None,
) -> dict[str, Any]:
    rep = lint_dialogue_prompt_speech(prompt, shot)
    if not rep.get("ok"):
        raise ProductionGateError(
            str(rep.get("msg") or "DIALOGUE_PROMPT_NO_SPEECH")
        )
    return rep


__all__ = [
    "DIALOGUE_WINDOW_HEAT",
    "assert_dialogue_prompt_allows_speech",
    "assert_dialogue_speaker_frame_contract",
    "assert_dialogue_still_for_register",
    "is_on_camera_dialogue_shot",
    "lint_dialogue_prompt_speech",
    "lint_dialogue_speaker_frame",
    "lint_dialogue_still_recipe",
    "speaker_frame_hard_enabled",
]
