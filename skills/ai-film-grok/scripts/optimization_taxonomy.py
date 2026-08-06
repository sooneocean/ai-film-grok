"""Versioned error taxonomy for optimisation receipts.

This module deliberately classifies only stable, structured evidence.  It never
tries to turn arbitrary provider prose into a confident root cause.
"""

from __future__ import annotations

from typing import Any

TAXONOMY_VERSION = 1
UNCLASSIFIED = "UNCLASSIFIED"

_CODES: dict[str, dict[str, Any]] = {
    "DECODE_FAILED": {
        "layer": "l0",
        "stage": "media",
        "retryable": True,
        "repair": "reencode-or-regenerate",
    },
    "DURATION_INVALID": {
        "layer": "l0",
        "stage": "media",
        "retryable": False,
        "repair": "repair-duration",
    },
    "AUDIO_MISSING": {"layer": "l0", "stage": "post", "retryable": False, "repair": "repair-audio"},
    "MOTION_LOW": {"layer": "l1", "stage": "media", "retryable": True, "repair": "reshoot-motion"},
    "IDENTITY_DRIFT": {
        "layer": "l1",
        "stage": "media",
        "retryable": True,
        "repair": "rebuild-still",
    },
    "CONTINUITY_CHAIN_BROKEN": {
        "layer": "l0",
        "stage": "media",
        "retryable": False,
        "repair": "repair-continuity",
    },
    "PILOT_REJECTED": {
        "layer": "l2",
        "stage": "pilot",
        "retryable": False,
        "repair": "repair-pilot",
    },
    "INVENTORY_INCOMPLETE": {
        "layer": "l0",
        "stage": "deliver",
        "retryable": False,
        "repair": "complete-inventory",
    },
    "SUBTITLE_DOUBLE_BURN": {
        "layer": "l0",
        "stage": "post",
        "retryable": False,
        "repair": "rerender-captions",
    },
    "PROVIDER_RATE_LIMIT": {
        "layer": "l3",
        "stage": "media",
        "retryable": True,
        "repair": "retry-backoff",
    },
    "PROVIDER_MODERATION": {
        "layer": "l3",
        "stage": "media",
        "retryable": False,
        "repair": "repair-input",
    },
    "COST_UNKNOWN": {
        "layer": "l3",
        "stage": "generation",
        "retryable": False,
        "repair": "record-provider-usage",
    },
}

_ALIASES = {
    "decode": "DECODE_FAILED",
    "ffprobe": "DECODE_FAILED",
    "duration": "DURATION_INVALID",
    "audio": "AUDIO_MISSING",
    "motion": "MOTION_LOW",
    "identity": "IDENTITY_DRIFT",
    "face": "IDENTITY_DRIFT",
    "continuity": "CONTINUITY_CHAIN_BROKEN",
    "rate_limit": "PROVIDER_RATE_LIMIT",
    "moderation": "PROVIDER_MODERATION",
}


def catalog() -> dict[str, Any]:
    return {
        "schema_version": TAXONOMY_VERSION,
        "codes": {key: dict(value) for key, value in _CODES.items()},
    }


def normalize_code(value: object) -> str:
    text = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    if text in _CODES:
        return text
    lowered = str(value or "").strip().lower()
    for token, code in _ALIASES.items():
        if token in lowered:
            return code
    return UNCLASSIFIED


def details(code: object) -> dict[str, Any]:
    normalized = normalize_code(code)
    if normalized == UNCLASSIFIED:
        return {
            "code": UNCLASSIFIED,
            "layer": "unknown",
            "stage": "unknown",
            "retryable": False,
            "repair": "classify-error",
        }
    return {"code": normalized, **_CODES[normalized]}
