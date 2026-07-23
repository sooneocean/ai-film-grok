#!/usr/bin/env python3
"""Pure validation for music, stems, captions, mix, and master approval."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_STEM_KINDS = {"dialogue", "vo", "native", "ambience", "foley", "sfx", "bgm"}


def _issue(code: str, message: str, **context: str) -> dict[str, str]:
    return {"code": code, "message": message, **context}


def _data(bible: Mapping[str, Any], node: str) -> Mapping[str, Any]:
    nodes = bible.get("nodes")
    value = nodes.get(node) if isinstance(nodes, Mapping) else None
    data = value.get("data") if isinstance(value, Mapping) else None
    return data if isinstance(data, Mapping) else {}


def _window(value: Mapping[str, Any]) -> tuple[float, float] | None:
    try:
        start = float(value["start_sec"])
        end = float(value["end_sec"])
    except (KeyError, TypeError, ValueError):
        return None
    return (start, end) if 0 <= start < end else None


def _validate_captions(data: Mapping[str, Any], errors: list[dict[str, str]]) -> None:
    owner = str(data.get("render_owner") or "")
    active = data.get("active_renderers")
    if not owner or not isinstance(active, list) or active != [owner]:
        errors.append(
            _issue(
                "CAPTION_RENDER_OWNER_CONFLICT",
                "captions must have exactly one active rendering owner",
            )
        )
    for index, cue in enumerate(data.get("cues") or []):
        cue_id = str(cue.get("cue_id") or index) if isinstance(cue, Mapping) else str(index)
        if not isinstance(cue, Mapping):
            errors.append(_issue("CAPTION_WINDOW_INVALID", "caption cue is invalid", cue_id=cue_id))
            continue
        cue_window = _window(cue)
        shot_window = _window(cue.get("shot_window") or {})
        dialogue_window = _window(cue.get("dialogue_window") or {})
        if cue_window is None or shot_window is None or dialogue_window is None:
            errors.append(
                _issue("CAPTION_WINDOW_INVALID", "caption windows are invalid", cue_id=cue_id)
            )
            continue
        if cue_window[0] < shot_window[0] or cue_window[1] > shot_window[1]:
            errors.append(
                _issue(
                    "CAPTION_OUTSIDE_SHOT_WINDOW",
                    "caption must remain inside its shot",
                    cue_id=cue_id,
                )
            )
        if cue_window[0] < dialogue_window[0] or cue_window[1] > dialogue_window[1]:
            errors.append(
                _issue(
                    "CAPTION_OUTSIDE_DIALOGUE_WINDOW",
                    "dialogue caption must remain inside its dialogue window",
                    cue_id=cue_id,
                )
            )


def _validate_music(data: Mapping[str, Any], errors: list[dict[str, str]]) -> None:
    license_data = data.get("license")
    if not str(data.get("motif") or "").strip():
        errors.append(_issue("BGM_MOTIF_MISSING", "BGM needs a named dramatic motif"))
    if not (
        isinstance(license_data, Mapping)
        and str(license_data.get("source") or "").strip()
        and str(license_data.get("license_id") or "").strip()
    ):
        errors.append(_issue("BGM_LICENSE_MISSING", "BGM needs source and license provenance"))
    cues = data.get("cues")
    if not isinstance(cues, list) or not cues:
        errors.append(_issue("BGM_CUES_MISSING", "BGM needs explicit cue in/out"))
        return
    for index, cue in enumerate(cues):
        cue_id = str(cue.get("cue_id") or index) if isinstance(cue, Mapping) else str(index)
        try:
            valid = (
                isinstance(cue, Mapping)
                and float(cue["in_sec"]) >= 0
                and float(cue["out_sec"]) > float(cue["in_sec"])
                and float(cue["silence_before_sec"]) >= 0
                and float(cue["silence_after_sec"]) >= 0
                and float(cue["ducking_db"]) <= 0
            )
        except (KeyError, TypeError, ValueError):
            valid = False
        if not valid:
            errors.append(
                _issue(
                    "BGM_CUE_INVALID",
                    "BGM cue needs in/out, silence handles, and non-positive ducking",
                    cue_id=cue_id,
                )
            )


def _validate_mix(data: Mapping[str, Any], errors: list[dict[str, str]]) -> None:
    stems = data.get("stems")
    kinds = {
        str(stem.get("kind"))
        for stem in stems or []
        if isinstance(stem, Mapping) and _SHA256.fullmatch(str(stem.get("sha256") or ""))
    }
    if not isinstance(stems, list) or kinds != _STEM_KINDS:
        errors.append(
            _issue(
                "MIX_STEM_PROVENANCE_INCOMPLETE",
                "mix needs hash-bound dialogue, VO, native, ambience, foley, SFX, and BGM stems",
            )
        )
    try:
        lufs = float(data["integrated_lufs"])
        peak = float(data["true_peak_dbtp"])
    except (KeyError, TypeError, ValueError):
        lufs, peak = 0.0, 1.0
    if not -24.0 <= lufs <= -14.0:
        errors.append(
            _issue("MIX_LUFS_OUT_OF_RANGE", "integrated loudness must be -24 to -14 LUFS")
        )
    if peak > -1.0:
        errors.append(_issue("MIX_TRUE_PEAK_TOO_HIGH", "true peak must not exceed -1.0 dBTP"))
    if "degraded_from" not in data:
        errors.append(
            _issue(
                "MIX_DEGRADATION_UNDECLARED",
                "mix must explicitly declare degraded_from, including null when not degraded",
            )
        )
    elif data.get("degraded_from") is not None and not bool(
        str(data.get("degraded_from") or "").strip()
    ):
        errors.append(
            _issue("MIX_DEGRADATION_INVALID", "degraded_from cannot be empty when present")
        )


def _validate_master(data: Mapping[str, Any], errors: list[dict[str, str]]) -> None:
    current = {
        "final": str(data.get("final_sha256") or ""),
        "mix": str(data.get("mix_sha256") or ""),
        "srt": str(data.get("srt_sha256") or ""),
    }
    approval = data.get("approval")
    approved = approval.get("input_hashes") if isinstance(approval, Mapping) else None
    if not isinstance(approval, Mapping) or approval.get("approver_type") not in {"human", "user"}:
        errors.append(
            _issue(
                "MASTER_HUMAN_APPROVAL_REQUIRED",
                "master pass requires current hash-bound human/user approval",
            )
        )
    if (
        not all(_SHA256.fullmatch(value) for value in current.values())
        or not isinstance(approved, Mapping)
        or dict(approved) != current
    ):
        errors.append(
            _issue(
                "MASTER_APPROVAL_STALE",
                "final, mix, or SRT hash changed after master approval",
            )
        )
    automated = data.get("automated_score")
    if isinstance(automated, Mapping) and automated.get("decision") != "advisory":
        errors.append(
            _issue(
                "AUTOMATED_SCORE_MUST_BE_ADVISORY",
                "automated scores cannot write or imply a human pass",
            )
        )


def validate_post_bible(bible: Mapping[str, Any]) -> dict[str, Any]:
    """Validate post closure without mutating approvals or node state."""
    errors: list[dict[str, str]] = []
    captions = _data(bible, "captions")
    mix = _data(bible, "mix")
    music = _data(bible, "bgm_motif_cue")
    master = _data(bible, "master")
    _validate_captions(captions, errors)
    _validate_mix(mix, errors)
    if music:
        _validate_music(music, errors)
    _validate_master(master, errors)
    return {
        "ok": not errors,
        "kind": "post-bible-validation",
        "errors": errors,
        "advisory_only": True,
    }
