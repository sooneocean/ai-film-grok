#!/usr/bin/env python3
"""True-video-only hero policy (P0 · 2026-08-04).

Still images are input assets only. Camera motion must be model-generated
(Grok I2V / H3 I2V|FLF|R2V / LTX dialogue|env). Ken Burns / panel zoompan
must never enter the hero timeline.

Class analogy: still = wardrobe polaroid; only generated film stock goes on the edit bench.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from i2v_motion_gate import source_is_forbidden
from util import read_json

# Extensions that are never hero clips (input stills only)
STILL_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"})
VIDEO_SUFFIXES = frozenset({".mp4", ".webm", ".mov", ".m4v", ".mkv"})

# Endpoints that prove generative video (not post still-motion)
HERO_VIDEO_ENDPOINTS = frozenset(
    {
        "image_to_video",
        "reference_to_video",
        "frw_seedance_i2v",
        "frw_seedance_flf",
        "frw_ltx_i2v",
        "frw_ltx23_img2video_audio",
        "frw_ltx_t2v",
        "frw_ltx_flf",
        "frw_ltx_lipsync",
        "frw_wan_lipsync",
        "frw_wan_i2v",
        "frw_seedance_lipsync",
        "frw_newvideo",
        "frw_img2video",
        "frw_text2video",
        "frw_first_last_frame",
        "frw_video_continue",
        "local_infinite_talk",
        "local_fantasy_talking",
        "local_latentsync",
        "local_minimax_h3_t2v",
        "local_minimax_h3_i2v",
        "local_minimax_h3_r2v",
        # external only when tags prove real generative origin (see assert)
        "external",
    }
)

# Never valid as hero source_endpoint (still animation / fake camera)
FORBIDDEN_HERO_ENDPOINTS = frozenset(
    {
        "ken_burns",
        "kenburns",
        "still_motion",
        "still-motion",
        "panel_animation",
        "panel-animation",
        "shortform_motion",
        "shortform-motion",
        "zoompan",
        "slideshow",
        "static_hold",
        "image_hold",
    }
)

# Tags / provider tokens that mark still-as-motion smuggling
_EXTRA_FORBIDDEN_TOKENS = frozenset(
    {
        "panel_animation",
        "panelanimation",
        "shortform_motion",
        "shortformmotion",
        "shortform_panel",
        "zoompan",
        "still_motion",
        "stillmotion",
        "image_hold",
        "imagehold",
        "post_push_in",
        "postpushin",
    }
)

PANEL_PRODUCTION_MODES = frozenset(
    {
        "panel",
        "panel-animation",
        "panel_animation",
        "shortform",
        "shortform-package",
        "manga_panel",
    }
)

# Drama / film modes where panel still-motion is illegal on hero track
DRAMA_PRODUCTION_MODES = frozenset(
    {
        "dialogue_drama",
        "adult",
        "longform",
        "premium_vertical",
        "hybrid_h3",
        "grok_primary",
        "standard",
        "",  # default = drama
    }
)

CODE_STILL_AS_CLIP = "TRUE_VIDEO_STILL_AS_CLIP"
CODE_FORBIDDEN_SOURCE = "TRUE_VIDEO_FORBIDDEN_SOURCE"
CODE_FORBIDDEN_ENDPOINT = "TRUE_VIDEO_FORBIDDEN_ENDPOINT"
CODE_PANEL_NOT_HERO = "PANEL_MOTION_NOT_HERO"
CODE_NOT_VIDEO = "TRUE_VIDEO_NOT_VIDEO"
CODE_EXTERNAL_UNPROVEN = "TRUE_VIDEO_EXTERNAL_UNPROVEN"


class TrueVideoPolicyError(ValueError):
    """Hero clip violates true-video-only policy."""


def policy_skip_enabled() -> bool:
    return os.environ.get("AIFILM_SKIP_TRUE_VIDEO_POLICY", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def production_mode_of(root: Path | str | None = None, spec: dict[str, Any] | None = None) -> str:
    """Resolve production_mode / content channel for panel vs drama."""
    if spec is None and root is not None:
        base = Path(root).expanduser().resolve()
        spec = read_json(base / "film-spec.json") or {}
    spec = spec if isinstance(spec, dict) else {}
    timeline = spec.get("timeline") if isinstance(spec.get("timeline"), dict) else {}
    mode = (
        str(
            spec.get("production_mode")
            or timeline.get("production_mode")
            or spec.get("content_channel")
            or ""
        )
        .strip()
        .lower()
    )
    if root is not None and not mode:
        book = read_json(Path(root).expanduser().resolve() / "production-book.json") or {}
        if isinstance(book, dict):
            mode = (
                str(book.get("production_mode") or book.get("content_channel") or "")
                .strip()
                .lower()
            )
    return mode


def is_panel_project(root: Path | str | None = None, spec: dict[str, Any] | None = None) -> bool:
    mode = production_mode_of(root, spec)
    if mode in PANEL_PRODUCTION_MODES:
        return True
    if mode in DRAMA_PRODUCTION_MODES or not mode:
        # Explicit allow flag for hybrid experiments
        if isinstance(spec, dict) and spec.get("allow_panel_hero_motion") is True:
            return True
        if root is not None:
            book = read_json(Path(root).expanduser().resolve() / "production-book.json") or {}
            if isinstance(book, dict) and book.get("allow_panel_hero_motion") is True:
                return True
        return False
    # unknown modes: treat as drama (fail closed for still-motion)
    return False


def path_looks_like_still(path: Path | str) -> bool:
    p = Path(path)
    return p.suffix.lower() in STILL_SUFFIXES


def path_looks_like_video(path: Path | str) -> bool:
    p = Path(path)
    return p.suffix.lower() in VIDEO_SUFFIXES


def source_blob_forbidden(
    source: str | None = None,
    *,
    tags: list[str] | None = None,
    provider: str | None = None,
    endpoint: str | None = None,
    review_note: str | None = None,
) -> bool:
    """True if any channel marks Ken Burns / panel / still-motion."""
    if source_is_forbidden(source, tags=tags):
        return True
    parts: list[str] = []
    for raw in (source, provider, endpoint, review_note):
        if raw:
            parts.append(str(raw).strip().lower())
    for t in tags or []:
        parts.append(str(t).strip().lower())
    if not parts:
        return False
    blob = " ".join(parts)
    if "ken burns" in blob or "ken_burns" in blob or "ken-burns" in blob:
        return True
    if "panel animation" in blob or "shortform motion" in blob:
        return True
    if "zoompan" in blob or "still-motion" in blob or "still motion" in blob:
        return True
    # Underscore compounds kept as tokens (panel_animation) + split alnum words
    norm = blob.replace("-", "_")
    compound_tokens = set(re.findall(r"[a-z0-9_]+", norm))
    word_tokens = set(re.findall(r"[a-z0-9]+", norm))
    if (compound_tokens | word_tokens) & _EXTRA_FORBIDDEN_TOKENS:
        return True
    # whole-token already covered by source_is_forbidden for core set
    return False


def assert_hero_clip_source(
    path: Path | str,
    *,
    endpoint: str | None,
    status: str = "candidate",
    tags: list[str] | None = None,
    provider: str | None = None,
    review_note: str | None = None,
    root: Path | str | None = None,
    role: str = "hero",
) -> dict[str, Any]:
    """Fail closed when registering/promoting a still-motion or non-video hero.

    Environment/bridge role is lighter but still must be real video (not png).
    """
    if policy_skip_enabled():
        return {
            "ok": True,
            "skipped": True,
            "escape": "AIFILM_SKIP_TRUE_VIDEO_POLICY=1",
        }

    source = Path(path).expanduser().resolve()
    ep = str(endpoint or "").strip().lower()
    codes: list[str] = []
    issues: list[dict[str, Any]] = []

    if path_looks_like_still(source):
        codes.append(CODE_STILL_AS_CLIP)
        issues.append(
            {
                "code": CODE_STILL_AS_CLIP,
                "message": (
                    f"{source.name} is a still image — stills are I2V inputs only; "
                    "hero timeline accepts generated video (Grok I2V / H3 I2V|R2V|FLF)"
                ),
            }
        )

    if not source.is_file():
        codes.append(CODE_NOT_VIDEO)
        issues.append({"code": CODE_NOT_VIDEO, "message": f"clip path missing: {source}"})
    elif not path_looks_like_video(source) and not path_looks_like_still(source):
        # Unknown suffix: still require video-like via endpoint later; warn as not_video
        if status == "approved":
            codes.append(CODE_NOT_VIDEO)
            issues.append(
                {
                    "code": CODE_NOT_VIDEO,
                    "message": f"approved hero clip must be video file, got suffix {source.suffix!r}",
                }
            )

    if ep in FORBIDDEN_HERO_ENDPOINTS:
        codes.append(CODE_FORBIDDEN_ENDPOINT)
        issues.append(
            {
                "code": CODE_FORBIDDEN_ENDPOINT,
                "message": (
                    f"source_endpoint={ep!r} is still-motion / panel animation — "
                    "forbidden on hero track (use Grok/H3 generative video)"
                ),
            }
        )

    if source_blob_forbidden(
        str(source),
        tags=tags,
        provider=provider,
        endpoint=ep,
        review_note=review_note,
    ):
        codes.append(CODE_FORBIDDEN_SOURCE)
        issues.append(
            {
                "code": CODE_FORBIDDEN_SOURCE,
                "message": (
                    "Ken Burns / panel / still-motion tags forbidden for hero clips; "
                    "camera motion must be model-generated"
                ),
            }
        )

    # Panel project isolation: shortform motion only if explicitly panel mode
    if role != "environment" and root is not None and not is_panel_project(root):
        tag_blob = " ".join(str(t).lower() for t in (tags or []))
        if any(
            k in tag_blob or k in ep
            for k in ("panel", "shortform", "ken_burns", "zoompan", "still_motion")
        ):
            codes.append(CODE_PANEL_NOT_HERO)
            issues.append(
                {
                    "code": CODE_PANEL_NOT_HERO,
                    "message": (
                        "panel/shortform still-motion cannot enter drama hero track; "
                        "set production_mode=panel only for pure panel packages"
                    ),
                }
            )

    # external endpoint needs generative provenance tags for approved hero
    if status == "approved" and ep == "external" and role != "environment":
        tag_set = {str(t).strip().lower() for t in (tags or [])}
        proven = bool(
            tag_set
            & {
                "grok",
                "image_to_video",
                "h3",
                "minimax_h3",
                "local_minimax_h3_i2v",
                "local_minimax_h3_r2v",
                "local_minimax_h3_t2v",
                "ltx",
                "frw",
                "generated_i2v",
                "generated_r2v",
            }
        )
        if not proven:
            codes.append(CODE_EXTERNAL_UNPROVEN)
            issues.append(
                {
                    "code": CODE_EXTERNAL_UNPROVEN,
                    "message": (
                        "external approved hero requires tags proving generative origin "
                        "(e.g. generated_i2v / h3 / grok) — blocks smuggled Ken Burns mp4"
                    ),
                }
            )

    if (
        status == "approved"
        and ep
        and ep not in HERO_VIDEO_ENDPOINTS
        and ep not in FORBIDDEN_HERO_ENDPOINTS
    ):
        # Unknown endpoint: allow only if not still-like; soft for candidate, hard for approved
        codes.append(CODE_FORBIDDEN_ENDPOINT)
        issues.append(
            {
                "code": CODE_FORBIDDEN_ENDPOINT,
                "message": f"unknown source_endpoint={ep!r} for approved hero clip",
            }
        )

    ok = not codes
    report = {
        "ok": ok,
        "codes": codes,
        "issues": issues,
        "path": str(source),
        "endpoint": ep or None,
        "role": role,
        "status": status,
        "policy": "true_video_only_v1",
    }
    if not ok:
        msg = "; ".join(i.get("message", c) for c, i in zip(codes, issues, strict=False))
        raise TrueVideoPolicyError(msg)
    return report


def scan_manifest_true_video(
    root: Path | str,
    *,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Audit all approved clips for still-motion / non-video smuggling."""
    base = Path(root).expanduser().resolve()
    if policy_skip_enabled():
        return {
            "ok": True,
            "skipped": True,
            "escape": "AIFILM_SKIP_TRUE_VIDEO_POLICY=1",
            "violations": [],
            "checked": 0,
        }
    man = manifest if isinstance(manifest, dict) else (read_json(base / "manifest.json") or {})
    clips = man.get("clips") if isinstance(man.get("clips"), dict) else {}
    violations: list[dict[str, Any]] = []
    checked = 0
    for shot_id, rec in clips.items():
        if not isinstance(rec, dict):
            continue
        if str(rec.get("status") or "") != "approved":
            continue
        checked += 1
        path = rec.get("path") or rec.get("rel_path") or ""
        tags = rec.get("tags") if isinstance(rec.get("tags"), list) else []
        try:
            from quality_gates import shot_role

            role = shot_role(base, str(shot_id))
        except Exception:
            role = "hero"
        try:
            assert_hero_clip_source(
                path,
                endpoint=str(rec.get("source_endpoint") or "") or None,
                status="approved",
                tags=[str(t) for t in tags],
                provider=str(rec.get("provider") or "") or None,
                review_note=str(rec.get("review_note") or "") or None,
                root=base,
                role=role,
            )
        except TrueVideoPolicyError as exc:
            violations.append(
                {
                    "shot_id": str(shot_id),
                    "path": str(path),
                    "error": str(exc),
                    "endpoint": rec.get("source_endpoint"),
                }
            )
        # Also flag forbidden source on path/provider even if assert path empty
        if source_blob_forbidden(
            str(path),
            tags=[str(t) for t in tags],
            provider=str(rec.get("provider") or ""),
            endpoint=str(rec.get("source_endpoint") or ""),
        ):
            if not any(v.get("shot_id") == str(shot_id) for v in violations):
                violations.append(
                    {
                        "shot_id": str(shot_id),
                        "path": str(path),
                        "error": "forbidden still-motion source tags",
                        "endpoint": rec.get("source_endpoint"),
                    }
                )

    return {
        "ok": not violations,
        "checked": checked,
        "violations": violations,
        "codes": [CODE_FORBIDDEN_SOURCE] if violations else [],
        "policy": "true_video_only_v1",
        "note": "hero track = generated video only; stills never enter timeline",
    }


def assert_manifest_true_video(
    root: Path | str, *, manifest: dict[str, Any] | None = None
) -> dict[str, Any]:
    report = scan_manifest_true_video(root, manifest=manifest)
    if not report.get("ok"):
        vids = report.get("violations") or []
        sample = "; ".join(f"{v.get('shot_id')}: {v.get('error')}" for v in vids[:5])
        raise TrueVideoPolicyError(
            f"True-video policy failed on {len(vids)} approved clip(s): {sample}. "
            "Re-I2V with Grok/H3; ban Ken Burns / panel still-motion on hero track."
        )
    return report
