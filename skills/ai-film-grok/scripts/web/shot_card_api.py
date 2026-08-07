"""Read-only Shot Card projection for director-center console (Phase E4).

Single film-root truth: builds from ``film-spec.json`` via ``plan.shot_card``.
No second director system — UI only displays what the plan already owns.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json
from web_core import WebConsoleError


def _root(root: Path | str) -> Path:
    value = Path(root).expanduser().resolve()
    if not value.is_dir():
        raise WebConsoleError("film root must be an existing directory")
    return value


def _load_spec(base: Path) -> dict[str, Any] | None:
    raw = read_json(base / "film-spec.json")
    return raw if isinstance(raw, dict) else None


def _summary(card: dict[str, Any]) -> dict[str, Any]:
    """Compact fields for console panel (full card still returned)."""
    framing = card.get("framing") if isinstance(card.get("framing"), dict) else {}
    camera = card.get("camera") if isinstance(card.get("camera"), dict) else {}
    subject = card.get("subject") if isinstance(card.get("subject"), dict) else {}
    duration = card.get("duration") if isinstance(card.get("duration"), dict) else {}
    return {
        "id": card.get("id"),
        "title": card.get("title"),
        "shot_purpose": card.get("shot_purpose") or card.get("dramatic_function"),
        "narrative_function": card.get("narrative_function"),
        "action": card.get("action"),
        "dialogue": card.get("dialogue"),
        "subject": subject.get("primary"),
        "shot_size": framing.get("shot_size"),
        "camera_motion": camera.get("motion"),
        "duration_sec": duration.get("target_seconds"),
        "asset_refs": list(card.get("asset_refs") or [])[:12],
        "status": card.get("status"),
        "scene_id": card.get("scene_id"),
        "beat_id": card.get("beat_id"),
    }


def _iter_spec_shots(spec: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    """Scene/beat tree first; flat top-level shots as fallback (common film-spec shape)."""
    from plan.shot_card import collect_shots_from_spec

    rows = list(collect_shots_from_spec(spec))
    if rows:
        return rows
    out: list[tuple[str, str, dict[str, Any]]] = []
    for shot in spec.get("shots") or []:
        if isinstance(shot, dict):
            out.append(
                (
                    str(shot.get("scene_id") or ""),
                    str(shot.get("beat_id") or ""),
                    shot,
                )
            )
    return out


def get_shot_card(root: Path | str, shot_id: str) -> dict[str, Any]:
    """Return one shot card or a soft-empty payload when unknown."""
    base = _root(root)
    sid = str(shot_id or "").strip()
    if not sid:
        raise WebConsoleError("shot query required")
    from plan.shot_card import build_shot_card

    spec = _load_spec(base)
    if not spec:
        return {
            "kind": "shot-card",
            "ok": False,
            "shot_id": sid,
            "found": False,
            "reason": "no film-spec.json",
            "summary": None,
            "card": None,
        }
    for scene_id, beat_id, shot in _iter_spec_shots(spec):
        if not isinstance(shot, dict):
            continue
        cur = str(shot.get("id") or "").strip()
        if cur != sid:
            continue
        card = build_shot_card(shot, scene_id=scene_id, beat_id=beat_id)
        return {
            "kind": "shot-card",
            "ok": True,
            "shot_id": sid,
            "found": True,
            "summary": _summary(card),
            "card": card,
        }
    return {
        "kind": "shot-card",
        "ok": True,
        "shot_id": sid,
        "found": False,
        "reason": "shot not in film-spec",
        "summary": None,
        "card": None,
    }


def list_shot_cards(root: Path | str, *, limit: int = 80) -> dict[str, Any]:
    """Index of shot-card summaries for the film (read-only)."""
    base = _root(root)
    limit = max(1, min(int(limit), 200))
    from plan.shot_card import build_shot_card

    spec = _load_spec(base)
    items: list[dict[str, Any]] = []
    if spec:
        for i, (scene_id, beat_id, shot) in enumerate(_iter_spec_shots(spec), start=1):
            if not isinstance(shot, dict):
                continue
            card = build_shot_card(shot, scene_id=scene_id, beat_id=beat_id, index=i)
            items.append(_summary(card))
            if len(items) >= limit:
                break
    return {
        "kind": "shot-card-index",
        "ok": True,
        "count": len(items),
        "items": items,
        "has_film_spec": bool(spec),
    }
