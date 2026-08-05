"""Native I2V audio helpers (peeled from render_final · W4 residual)."""

from __future__ import annotations

import argparse
from typing import Any

from final.errors import RenderError

DEFAULT_NATIVE_AUDIO_VOLUME = 0.72
NATIVE_AUDIO_TARGET_DB = -22.0
NATIVE_AUDIO_GAIN_MIN = 0.50
NATIVE_AUDIO_GAIN_MAX = 1.60


def resolve_native_audio_volume(
    args: argparse.Namespace,
    spec: dict[str, Any],
    voice_policy: dict[str, Any] | None = None,
) -> float:
    """Resolve native I2V audio gain without letting a policy override the CLI."""
    cli_value = getattr(args, "native_audio_volume", None)
    if cli_value is not None:
        raw_value = cli_value
    elif (voice_policy or {}).get("native_audio_volume") is not None:
        raw_value = (voice_policy or {})["native_audio_volume"]
    else:
        raw_value = spec.get("native_audio_volume", DEFAULT_NATIVE_AUDIO_VOLUME)
    try:
        value = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise RenderError("native_audio_volume must be between 0 and 1") from exc
    if value < 0 or value > 1:
        raise RenderError("native_audio_volume must be between 0 and 1")
    return value


def primary_native_shot_ids(shot_audio: list[dict[str, Any]]) -> list[str]:
    """Keep usable native ambience, never a stem replaced by rendered TTS."""
    return [
        str(item["id"])
        for item in shot_audio
        if item.get("native_audio")
        and item.get("native_audio_audible") is not False
        and not item.get("native_audio_suppressed_for_tts")
    ]


def native_dialogue_replaced_by_post_tts(shot: dict[str, Any]) -> bool:
    """True only when an approved dialogue contract explicitly selects post TTS."""
    contracts = shot.get("dialogue_contracts")
    if not isinstance(contracts, list):
        return False
    for contract in contracts:
        if not isinstance(contract, dict):
            continue
        for line in contract.get("lines") or []:
            if isinstance(line, dict) and str(line.get("audio_origin") or "") == "post_vo":
                return True
    return False


def resolve_native_audio_gain(native_record: dict[str, Any] | None) -> float:
    """Normalize audible I2V stems conservatively; never amplify known silence."""
    if not isinstance(native_record, dict):
        return 1.0
    if native_record.get("audible") is False:
        return 0.0
    mean_volume_db = native_record.get("mean_volume_db")
    if not isinstance(mean_volume_db, (int, float)) or isinstance(mean_volume_db, bool):
        return 1.0
    gain = 10 ** ((NATIVE_AUDIO_TARGET_DB - float(mean_volume_db)) / 20)
    return max(NATIVE_AUDIO_GAIN_MIN, min(NATIVE_AUDIO_GAIN_MAX, gain))
