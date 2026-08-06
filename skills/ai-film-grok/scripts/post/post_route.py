#!/usr/bin/env python3
"""Post caption path router — one episode, one caption decision.

P0 · 2026-08-05 post optimize:

  master_hf      → plate ``subs=off``; HyperFrames/Remotion owns designed captions
  ship_hardburn  → plate PIL/ffmpeg burn; pixels must show Chinese; no double-burn

Writes ``receipts/post-route.json``. Agents must not invent a second path mid-final.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json

RECEIPT_REL = Path("receipts/post-route.json")
CAPTION_PATHS = frozenset({"master_hf", "ship_hardburn"})
DESIGNED_ENGINES = frozenset({"hyperframes", "remotion"})


class PostRouteError(ValueError):
    """Caption path / engine combination is unsafe."""


def post_route_path(root: Path | str) -> Path:
    return Path(root).expanduser().resolve() / RECEIPT_REL


def normalize_caption_path(value: str | None) -> str | None:
    text = str(value or "").strip().lower().replace("-", "_")
    if not text:
        return None
    aliases = {
        "hf": "master_hf",
        "master": "master_hf",
        "hyperframes": "master_hf",
        "designed": "master_hf",
        "ship": "ship_hardburn",
        "hardburn": "ship_hardburn",
        "hard_burn": "ship_hardburn",
        "pil": "ship_hardburn",
        "ffmpeg_burn": "ship_hardburn",
        "burn": "ship_hardburn",
    }
    text = aliases.get(text, text)
    if text not in CAPTION_PATHS:
        raise PostRouteError(f"caption_path must be one of {sorted(CAPTION_PATHS)} (got {value!r})")
    return text


def _spec_caption_path(root: Path) -> str | None:
    spec = read_json(root / "film-spec.json") or {}
    for key in ("caption_path", "caption_route"):
        raw = spec.get(key)
        if raw:
            return normalize_caption_path(str(raw))
    post = spec.get("post") if isinstance(spec.get("post"), dict) else {}
    if post.get("caption_path"):
        return normalize_caption_path(str(post["caption_path"]))
    # Explicit ship-mode flags on spec (honest PARTIAL path)
    if post.get("ship_hardburn") is True or spec.get("ship_hardburn") is True:
        return "ship_hardburn"
    return None


def _receipt_caption_path(root: Path) -> str | None:
    data = read_json(post_route_path(root)) or {}
    raw = data.get("caption_path")
    if raw:
        return normalize_caption_path(str(raw))
    return None


def _env_force_ship() -> bool:
    return str(os.environ.get("AIFILM_CAPTION_PATH") or "").strip().lower() in {
        "ship",
        "ship_hardburn",
        "hardburn",
        "burn",
    }


def default_caption_path(*, post_engine: str) -> str:
    engine = str(post_engine or "ffmpeg").strip().lower()
    if engine in DESIGNED_ENGINES:
        return "master_hf"
    return "ship_hardburn"


def resolve_caption_path(
    root: Path | str,
    *,
    post_engine: str = "hyperframes",
    explicit: str | None = None,
    prefer_ship: bool = False,
) -> dict[str, Any]:
    """Resolve single caption_path with source provenance.

    Priority: CLI explicit → env AIFILM_CAPTION_PATH → film-spec → existing receipt
    → prefer_ship → default from post_engine.
    """
    base = Path(root).expanduser().resolve()
    engine = str(post_engine or "ffmpeg").strip().lower()
    source = "default"
    path: str | None = None
    notes: list[str] = []

    if explicit:
        path = normalize_caption_path(explicit)
        source = "cli"
    elif _env_force_ship():
        path = "ship_hardburn"
        source = "env:AIFILM_CAPTION_PATH"
        notes.append("env forces ship_hardburn")
    else:
        path = _spec_caption_path(base)
        if path:
            source = "film-spec"
        else:
            path = _receipt_caption_path(base)
            if path:
                source = "receipts/post-route.json"
            elif prefer_ship:
                path = "ship_hardburn"
                source = "prefer_ship"
            else:
                path = default_caption_path(post_engine=engine)
                source = f"default:{engine}"

    assert path in CAPTION_PATHS
    # Conflicts: designed engine + forced burn via explicit ship is allowed (ship wins)
    # master_hf + ffmpeg engine is allowed (plate can still use off + external register)
    if path == "master_hf" and engine == "ffmpeg":
        notes.append(
            "master_hf with post_engine=ffmpeg: plate subs=off; you must attach designed captions later"
        )
    if path == "ship_hardburn" and engine in DESIGNED_ENGINES:
        notes.append(
            "ship_hardburn with designed engine: plate burns captions; "
            "designed-post may only grade/title with allow_burned_underlay (no second caption layer)"
        )

    return {
        "caption_path": path,
        "post_engine": engine,
        "source": source,
        "notes": notes,
        "plate_subs": "off" if path == "master_hf" else "burn",
        "plate_cards": "blank" if path == "master_hf" and engine in DESIGNED_ENGINES else "text",
        "designed_caption_owner": path == "master_hf" and engine in DESIGNED_ENGINES,
        "allow_burned_underlay": path == "ship_hardburn" and engine in DESIGNED_ENGINES,
        "skip_designed_post": False,  # keep engine; ship just changes caption ownership
    }


def apply_route_to_plate(
    route: dict[str, Any],
    *,
    subs_mode: str | None,
    plate_cards: str | None,
) -> dict[str, Any]:
    """Return resolved plate subs/cards; fail closed on double-burn conflicts."""
    path = str(route.get("caption_path") or "")
    engine = str(route.get("post_engine") or "")
    subs = str(subs_mode or "").strip().lower()
    cards = str(plate_cards or "auto").strip().lower()
    if cards in {"", "auto"}:
        cards = str(route.get("plate_cards") or "text")

    if path == "master_hf":
        if subs == "burn":
            raise PostRouteError(
                "caption_path=master_hf forbids plate --subs burn (would double-burn under HF/Remotion). "
                "Use caption_path=ship_hardburn or --subs off."
            )
        subs = "off"
        if cards == "text" and engine in DESIGNED_ENGINES:
            cards = "blank"
    elif path == "ship_hardburn":
        if subs == "off":
            # Explicit off on ship path is a foot-gun (no pixels). Force burn.
            subs = "burn"
        elif not subs:
            subs = "burn"
        if cards in {"", "auto"}:
            cards = "text"
    else:
        raise PostRouteError(f"unknown caption_path {path!r}")

    if cards not in {"text", "blank"}:
        raise PostRouteError("--plate-cards must be auto|text|blank")
    if subs not in {"burn", "off"}:
        raise PostRouteError("--subs must be burn|off")

    # Final double-burn invariant for designed engines
    if engine in DESIGNED_ENGINES and path == "master_hf" and subs == "burn":
        raise PostRouteError("master_hf + designed engine cannot burn plate subs")

    return {
        "subs": subs,
        "plate_cards": cards,
        "caption_path": path,
        "post_engine": engine,
        "designed_caption_owner": bool(route.get("designed_caption_owner")),
        "allow_burned_underlay": bool(route.get("allow_burned_underlay")),
    }


def write_post_route(root: Path | str, route: dict[str, Any]) -> dict[str, Any]:
    base = Path(root).expanduser().resolve()
    path = post_route_path(base)
    payload = {
        "schema_version": 1,
        "kind": "post-route",
        "at": utc_now(),
        "root": str(base),
        **route,
        "contract": [
            "one caption_path per episode",
            "master_hf: plate subs=off; designed engine owns captions",
            "ship_hardburn: plate burn; pixel ink required; no second caption layer",
        ],
    }
    write_json(path, payload)
    payload["path"] = str(path)
    return payload


def load_post_route(root: Path | str) -> dict[str, Any] | None:
    data = read_json(post_route_path(root)) or {}
    if data.get("kind") != "post-route":
        return None
    return data


def assert_no_double_caption_layers(
    *,
    caption_path: str,
    plate_subs: str,
    caption_owner: str | None,
) -> None:
    """Fail closed if plate already burned and owner is also designed."""
    path = normalize_caption_path(caption_path) or caption_path
    owner = str(caption_owner or "").strip().lower()
    if (
        path == "ship_hardburn"
        and plate_subs == "burn"
        and owner
        in {
            "hyperframes",
            "remotion",
            "hyperframes_export_only",
        }
    ):
        raise PostRouteError(
            "double caption risk: ship_hardburn plate burn + designed caption_owner="
            f"{owner}. Designed layer must not re-draw captions (title/grade only)."
        )
    if path == "master_hf" and plate_subs == "burn":
        raise PostRouteError(
            "double caption risk: master_hf requires plate subs=off before designed burn"
        )
