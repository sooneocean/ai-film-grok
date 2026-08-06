#!/usr/bin/env python3
"""Media auto-routing: pick 写实/漫剧 per character by cast-state stability.

P2 quality item "介质自动路由（按 cast_state 稳定性选写实/漫剧）".

The film has a global ``medium_key`` (photoreal / anime / manhua …) locked for the
whole movie. Some cast members are hard to keep coherent in photoreal — their
identity drifts shot-to-shot. For those, routing the character to anime/漫剧 at
*planning time* keeps identity stable without fighting the renderer.

This module is the pure, testable core of that routing:

  - ``route_character_medium(film_medium, char_stability)`` — the policy.
  - ``load_cast_stability(root)`` — data source (spec ``cast_stability`` map,
    defaulting every known character to "stable").
  - ``resolve_shot_medium(root, shot, intent)`` — orchestrates film medium +
    character stability into an effective medium for one shot.
  - ``media_routing_report(root)`` — observable per-character decisions.

The decision is made at planning time and baked into the shot spec; it never
switches medium mid-film at runtime, so the existing medium lock stays intact.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json
from util.film_spec import _root

# Medium values that imply photorealistic rendering (drift-prone for unstable cast).
_PHOTOREAL_MEDIA = frozenset({"photoreal", "semi_real", "real", "live_action", "realistic"})
_STABLE = "stable"
_UNSTABLE = "unstable"


def route_character_medium(
    film_medium: str,
    char_stability: str,
) -> tuple[str, str]:
    """Decide the effective medium for a character's shots (P2 media auto-routing).

    Pure policy. A film defaults to one medium, but an unstable cast member is
    downgraded to anime/漫剧 so identity stays coherent across shots instead of
    fighting photoreal drift. Returns ``(effective_medium, reason)``.

    - unstable + photoreal film -> "anime" (downgrade to keep identity)
    - anything else -> the film medium unchanged
    """
    fm = str(film_medium or "").strip().lower()
    stab = str(char_stability or "").strip().lower()
    if stab == _UNSTABLE and fm in _PHOTOREAL_MEDIA:
        return "anime", "unstable_cast_downgrade_to_anime"
    return fm, "film_medium_default"


def load_cast_stability(root: Path | str) -> dict[str, str]:
    """Load per-character stability from the film spec (default: all stable).

    Reads the optional ``cast_stability`` map (char_id -> "stable"|"unstable") and
    seeds every known character (from ``cast_ids`` / ``characters``) to "stable"
    so the routing has a complete, normalized view. Missing spec -> empty map.
    """
    base = _root(root)
    spec = read_json(base / "film-spec.json") or {}
    if not isinstance(spec, dict):
        return {}
    out: dict[str, str] = {}
    # Seed every known character so stability is defined for all of them.
    raw_cast = (
        spec.get("cast_ids")
        if isinstance(spec.get("cast_ids"), (list, dict))
        else spec.get("characters")
    )
    if isinstance(raw_cast, dict):
        char_ids = [str(k).strip() for k in raw_cast]
    elif isinstance(raw_cast, list):
        char_ids = [str(c).strip() for c in raw_cast if str(c).strip()]
    else:
        char_ids = []
    for cid in char_ids:
        if cid and cid not in out:
            out[cid] = _STABLE
    # Apply explicit overrides (any casing normalized to stable/unstable).
    overrides = spec.get("cast_stability") if isinstance(spec.get("cast_stability"), dict) else {}
    for cid, val in overrides.items():
        cid = str(cid).strip()
        if not cid:
            continue
        out[cid] = _UNSTABLE if str(val).strip().lower() == _UNSTABLE else _STABLE
    return out


def _film_medium_of(root: Path) -> str:
    """Resolve the film's global medium (style-bible wins, spec fallback)."""
    sb = read_json(root / "style-bible.json") or {}
    fp = sb.get("style_fingerprint") if isinstance(sb.get("style_fingerprint"), dict) else {}
    medium = fp.get("medium_key") if isinstance(fp, dict) else None
    if not medium:
        spec = read_json(root / "film-spec.json") or {}
        sfp = spec.get("style_fingerprint") if isinstance(spec.get("style_fingerprint"), dict) else {}
        medium = sfp.get("medium_key") if isinstance(sfp, dict) else None
    return str(medium or "photoreal").strip().lower()


def _shot_character(shot: dict[str, Any], intent: dict[str, Any] | None) -> str:
    sh = shot if isinstance(shot, dict) else {}
    intent = intent if isinstance(intent, dict) else {}
    for key in ("character", "char_id", "cast_id"):
        val = sh.get(key) or intent.get(key)
        if str(val or "").strip():
            return str(val).strip()
    return "hero"  # default character when unspecified


def resolve_shot_medium(
    root: Path | str,
    shot: dict[str, Any],
    intent: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Effective medium for one shot: film medium + this shot's character stability."""
    base = _root(root)
    film_medium = _film_medium_of(base)
    stability = load_cast_stability(base)
    char = _shot_character(shot, intent)
    stab = stability.get(char, _STABLE)
    return route_character_medium(film_medium, stab)


def media_routing_report(root: Path | str) -> dict[str, Any]:
    """Observable per-character media-routing decisions for the whole film."""
    base = _root(root)
    film_medium = _film_medium_of(base)
    stability = load_cast_stability(base)
    rows: list[dict[str, str]] = []
    for cid in sorted(stability.keys()):
        eff, reason = route_character_medium(film_medium, stability[cid])
        rows.append(
            {
                "character": cid,
                "film_medium": film_medium,
                "stability": stability[cid],
                "effective_medium": eff,
                "reason": reason,
            }
        )
    routed = [r for r in rows if r["effective_medium"] != r["film_medium"]]
    return {
        "ok": True,
        "film_medium": film_medium,
        "count": len(rows),
        "routed": len(routed),
        "rows": rows,
    }
