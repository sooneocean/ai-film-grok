"""Shot Card — director-facing production unit (not an image prompt).

Film Production OS W2: every shot carries purpose, audience info, continuity,
and asset refs. Prompts are compiled downstream; cards are source of planning truth.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json

# Cinematic purpose taxonomy (director language). Coexists with dramatic_function spine.
SHOT_PURPOSES = frozenset(
    {
        "establish_location",
        "introduce_character",
        "reveal_information",
        "show_reaction",
        "show_relationship",
        "create_tension",
        "release_tension",
        "transition",
        "insert_detail",
        "establish_geography",
        "subjective_pov",
        "emotional_closeup",
        "action_coverage",
        "dialogue_coverage",
        "story_reveal",
        "visual_motif",
    }
)

# Aesthetic-only labels that must not be the sole purpose.
BANNED_SOLE_PURPOSES = frozenset(
    {
        "looks cool",
        "looks_cool",
        "cinematic",
        "beautiful",
        "beautiful shot",
        "aesthetic",
        "好看",
        "帅",
        "电影感",
    }
)

CODE_PURPOSE_EMPTY = "SHOT_PURPOSE_EMPTY"
CODE_PURPOSE_AESTHETIC_ONLY = "SHOT_PURPOSE_AESTHETIC_ONLY"
CODE_PURPOSE_UNKNOWN = "SHOT_PURPOSE_UNKNOWN"

_DRAMATIC_TO_PURPOSE: dict[str, str] = {
    "hook": "establish_location",
    "approach": "create_tension",
    "sensory": "insert_detail",
    "reaction": "show_reaction",
    "action": "action_coverage",
    "afterglow": "release_tension",
    "bridge": "transition",
}


def _text(value: object) -> str:
    return str(value or "").strip()


def _norm(value: object) -> str:
    return _text(value).lower().replace("-", "_").replace(" ", "_")


def _dsl(shot: dict[str, Any]) -> dict[str, Any]:
    raw = shot.get("dsl")
    return raw if isinstance(raw, dict) else {}


def resolve_shot_purpose(shot: dict[str, Any]) -> str:
    """Return normalized purpose or empty string."""
    for key in ("shot_purpose", "purpose", "narrative_function"):
        val = shot.get(key)
        if _text(val):
            return _norm(val)
    dsl = _dsl(shot)
    for key in ("shot_purpose", "purpose", "narrative_function"):
        val = dsl.get(key)
        if _text(val):
            return _norm(val)
    fn = _norm(shot.get("dramatic_function") or dsl.get("dramatic_function"))
    if fn in _DRAMATIC_TO_PURPOSE:
        return _DRAMATIC_TO_PURPOSE[fn]
    return ""


def lint_shot_purpose(shots: list[dict[str, Any]], *, strict: bool = False) -> dict[str, Any]:
    """Flag empty or aesthetic-only purposes.

    When strict, unknown non-empty purposes that are not in SHOT_PURPOSES also error
    unless they map from dramatic_function (already resolved).
    """
    issues: list[dict[str, Any]] = []
    for i, shot in enumerate(shots):
        if not isinstance(shot, dict):
            continue
        sid = str(shot.get("id") or f"shot{i + 1}")
        role = _norm(shot.get("shot_role") or "hero")
        raw_purpose = _text(shot.get("shot_purpose") or shot.get("purpose") or "")
        purpose = resolve_shot_purpose(shot)

        if raw_purpose and _norm(raw_purpose) in BANNED_SOLE_PURPOSES:
            issues.append(
                {
                    "code": CODE_PURPOSE_AESTHETIC_ONLY,
                    "severity": "error",
                    "message": (
                        f"{sid}: purpose {raw_purpose!r} is aesthetic-only — "
                        "author a narrative purpose from SHOT_PURPOSES"
                    ),
                    "shot_ids": [sid],
                    "ref": f"{sid}.shot_purpose",
                }
            )
            continue

        if not purpose:
            if role in {"env", "insert"}:
                continue
            issues.append(
                {
                    "code": CODE_PURPOSE_EMPTY,
                    "severity": "error",
                    "message": (
                        f"{sid}: missing shot_purpose — every shot needs a reason to exist "
                        f"(one of {sorted(SHOT_PURPOSES)[:6]}…)"
                    ),
                    "shot_ids": [sid],
                    "ref": f"{sid}.shot_purpose",
                }
            )
            continue

        if purpose in BANNED_SOLE_PURPOSES:
            issues.append(
                {
                    "code": CODE_PURPOSE_AESTHETIC_ONLY,
                    "severity": "error",
                    "message": f"{sid}: purpose {purpose!r} banned as sole justification",
                    "shot_ids": [sid],
                    "ref": f"{sid}.shot_purpose",
                }
            )
        elif (
            strict
            and purpose not in SHOT_PURPOSES
            and purpose not in _DRAMATIC_TO_PURPOSE.values()
        ):
            issues.append(
                {
                    "code": CODE_PURPOSE_UNKNOWN,
                    "severity": "warning",
                    "message": f"{sid}: purpose {purpose!r} not in SHOT_PURPOSES enum",
                    "shot_ids": [sid],
                    "ref": f"{sid}.shot_purpose",
                }
            )

    errors = [i for i in issues if i.get("severity") == "error"]
    codes = sorted({str(i["code"]) for i in issues})
    return {
        "ok": not errors,
        "kind": "shot-purpose",
        "issues": issues,
        "codes": codes,
        "error_count": len(errors),
        "warning_count": len(issues) - len(errors),
        "blocking": sorted({str(i["code"]) for i in errors}),
    }


def build_shot_card(
    shot: dict[str, Any],
    *,
    scene_id: str = "",
    beat_id: str = "",
    index: int = 1,
) -> dict[str, Any]:
    """Build a machine+human Shot Card from a film-spec / graph shot dict."""
    dsl = _dsl(shot)
    sid = str(shot.get("id") or f"shot{index:02d}")
    purpose = resolve_shot_purpose(shot)
    narrative = _text(
        shot.get("narrative_function")
        or shot.get("story_beat")
        or dsl.get("story_beat")
        or dsl.get("visible_change")
        or shot.get("title")
    )
    cont_in = shot.get("continuity_in") if isinstance(shot.get("continuity_in"), dict) else {}
    cont_out = shot.get("continuity_out") if isinstance(shot.get("continuity_out"), dict) else {}
    if not cont_in and isinstance(dsl.get("continuity_in"), dict):
        cont_in = dsl["continuity_in"]
    if not cont_out and isinstance(dsl.get("continuity_out"), dict):
        cont_out = dsl["continuity_out"]

    asset_refs: list[str] = []
    for key in ("asset_refs", "character_ids", "location_ids", "prop_ids"):
        raw = shot.get(key) or dsl.get(key)
        if isinstance(raw, list):
            asset_refs.extend(str(x) for x in raw if str(x).strip())
        elif _text(raw):
            asset_refs.append(_text(raw))
    for key in ("cast", "location", "prop"):
        val = shot.get(key) or dsl.get(key)
        if _text(val):
            asset_refs.append(_text(val))
    # de-dupe preserve order
    seen: set[str] = set()
    assets_unique: list[str] = []
    for a in asset_refs:
        if a not in seen:
            seen.add(a)
            assets_unique.append(a)

    framing = {
        "shot_size": _text(shot.get("shot_size") or dsl.get("shot_size") or shot.get("size")),
        "angle": _text(shot.get("angle") or dsl.get("angle")),
        "lens": _text(shot.get("lens") or dsl.get("lens")),
    }
    camera = {
        "motion": _text(
            shot.get("camera") or dsl.get("camera") or shot.get("camera_motion") or dsl.get("camera_motion")
        ),
        "height": _text(shot.get("camera_height") or dsl.get("camera_height")),
    }
    performance = shot.get("performance") if isinstance(shot.get("performance"), dict) else {}
    if not performance:
        performance = {
            "emotion": _text(shot.get("emotion") or dsl.get("emotion")),
            "intensity": shot.get("intensity") or dsl.get("intensity"),
        }

    card: dict[str, Any] = {
        "schema_version": 1,
        "kind": "ai-film-shot-card",
        "id": sid,
        "scene_id": scene_id or _text(shot.get("scene_id")),
        "beat_id": beat_id or _text(shot.get("beat_id")),
        "title": _text(shot.get("title")) or sid,
        "shot_purpose": purpose or None,
        "narrative_function": narrative or None,
        "audience_information": shot.get("audience_information")
        if isinstance(shot.get("audience_information"), dict)
        else {
            "before": _text(shot.get("audience_before") or dsl.get("audience_before")),
            "after": _text(shot.get("audience_after") or dsl.get("audience_after") or narrative),
        },
        "emotional_function": shot.get("emotional_function")
        if isinstance(shot.get("emotional_function"), dict)
        else {
            "start": _text(shot.get("emotion_start") or dsl.get("emotion_start")),
            "end": _text(shot.get("emotion_end") or dsl.get("emotion_end")),
        },
        "pov": shot.get("pov")
        if isinstance(shot.get("pov"), dict)
        else {"character_id": _text(shot.get("pov") or dsl.get("pov")), "mode": _text(shot.get("pov_mode"))},
        "framing": framing,
        "camera": camera,
        "subject": {
            "primary": _text(shot.get("subject") or dsl.get("subject") or shot.get("primary_subject")),
        },
        "action": _text(
            shot.get("action")
            or shot.get("playable_action")
            or dsl.get("action")
            or dsl.get("visible_change")
        ),
        "performance": performance,
        "duration": {
            "target_seconds": shot.get("duration_sec")
            or shot.get("duration")
            or dsl.get("duration_sec")
            or None
        },
        "lighting": shot.get("lighting")
        if isinstance(shot.get("lighting"), dict)
        else {"source": _text(shot.get("lighting") or dsl.get("lighting"))},
        "continuity_in": cont_in,
        "continuity_out": cont_out,
        "dialogue": shot.get("spoken_text") or shot.get("dialogue") or dsl.get("spoken_text"),
        "sound": shot.get("sound")
        if isinstance(shot.get("sound"), dict)
        else {
            "ambience": shot.get("ambience") or [],
            "effects": shot.get("sfx") or [],
        },
        "asset_refs": assets_unique,
        "dramatic_function": _text(shot.get("dramatic_function") or dsl.get("dramatic_function")),
        "status": _text(shot.get("status") or "ready_for_storyboard") or "ready_for_storyboard",
    }
    return card


def format_shot_card_markdown(card: dict[str, Any], *, index: int = 1) -> str:
    """Human-readable shot list line (§42 style)."""
    purpose = card.get("shot_purpose") or card.get("dramatic_function") or "shot"
    title = card.get("title") or card.get("id")
    lines = [
        f"## Shot {index:02d} — {purpose}",
        "",
        f"Id: {card.get('id')}",
        f"Title: {title}",
        "",
        "Purpose:",
        f"{card.get('narrative_function') or card.get('shot_purpose') or '(unset)'}",
        "",
        "Story Information:",
        f"{(card.get('audience_information') or {}).get('after') or '(unset)'}",
        "",
        "Framing:",
        f"{(card.get('framing') or {}).get('shot_size') or '(unset)'}",
        "",
        "Camera:",
        f"{(card.get('camera') or {}).get('motion') or '(unset)'}",
        "",
        "Duration:",
        f"{(card.get('duration') or {}).get('target_seconds') or '(unset)'}s",
        "",
        "Performance / Action:",
        f"{card.get('action') or (card.get('performance') or {}).get('emotion') or '(unset)'}",
        "",
        "Dialogue:",
        f"{card.get('dialogue') or 'null'}",
        "",
        "Continuity In:",
        f"{card.get('continuity_in') or '{}'}",
        "",
        "Continuity Out:",
        f"{card.get('continuity_out') or '{}'}",
        "",
        "Assets:",
        f"{', '.join(card.get('asset_refs') or []) or '(none)'}",
        "",
    ]
    return "\n".join(lines)


def collect_shots_from_spec(spec: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    """Yield (scene_id, beat_id, shot) from film-spec nested or flat shapes."""
    out: list[tuple[str, str, dict[str, Any]]] = []
    for si, scene in enumerate(spec.get("scenes") or []):
        if not isinstance(scene, dict):
            continue
        sc_id = str(scene.get("id") or scene.get("title") or f"sc{si + 1:02d}")
        beats = scene.get("beats") if isinstance(scene.get("beats"), list) else None
        if beats:
            for bi, beat in enumerate(beats):
                if not isinstance(beat, dict):
                    continue
                bt_id = str(beat.get("id") or f"{sc_id}_bt{bi + 1:02d}")
                for shot in beat.get("shots") or []:
                    if isinstance(shot, dict):
                        out.append((sc_id, bt_id, shot))
        else:
            for shot in scene.get("shots") or []:
                if isinstance(shot, dict):
                    beat_id = _text(shot.get("beat_id"))
                    out.append((sc_id, beat_id, shot))
    return out


def export_shot_cards(
    root: Path | str,
    *,
    write_files: bool = True,
    strict_purpose: bool = False,
) -> dict[str, Any]:
    """Build shot cards from film-spec; optionally write shot-cards/ + receipt."""
    root_p = Path(root).expanduser().resolve()
    spec = read_json(root_p / "film-spec.json") or {}
    if not isinstance(spec, dict):
        return {"ok": False, "error": "film-spec.json missing or invalid", "cards": []}

    triples = collect_shots_from_spec(spec)
    cards: list[dict[str, Any]] = []
    md_parts: list[str] = [f"# Shot List — {spec.get('title') or root_p.name}", ""]
    for i, (sc_id, bt_id, shot) in enumerate(triples, start=1):
        card = build_shot_card(shot, scene_id=sc_id, beat_id=bt_id, index=i)
        cards.append(card)
        md_parts.append(format_shot_card_markdown(card, index=i))

    purpose_report = lint_shot_purpose([t[2] for t in triples], strict=strict_purpose)
    report: dict[str, Any] = {
        "ok": purpose_report.get("ok", True),
        "kind": "shot-card-export",
        "root": str(root_p),
        "count": len(cards),
        "cards": cards,
        "purpose_lint": purpose_report,
        "at": utc_now(),
    }

    if write_files:
        out_dir = root_p / "shot-cards"
        out_dir.mkdir(parents=True, exist_ok=True)
        write_json(out_dir / "index.json", {"cards": cards, "count": len(cards)})
        md_path = out_dir / "SHOT_LIST.md"
        md_path.write_text("\n".join(md_parts), encoding="utf-8")
        for card in cards:
            write_json(out_dir / f"{card['id']}.json", card)
        receipt = root_p / "receipts" / "shot-cards.json"
        write_json(
            receipt,
            {
                "ok": report["ok"],
                "count": len(cards),
                "purpose_lint": purpose_report,
                "shot_list_md": str(md_path),
                "at": utc_now(),
            },
        )
        report["shot_list_md"] = str(md_path)
        report["receipt"] = str(receipt)
        report["dir"] = str(out_dir)
    return report
