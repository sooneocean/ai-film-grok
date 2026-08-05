"""Strict, pixel-backed wardrobe-state ladders.

This module deliberately plans and registers state photos locally.  It never
calls an image provider: each I2I step needs an explicit human-approved output
before it can become the input for the following step.
"""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from util import utc_now


def _slug(value: object) -> str:
    text = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value or ""))
    return "-".join(part for part in text.split("-") if part) or "garment"


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stored_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _image_metadata(path: Path) -> dict[str, Any]:
    """Read pixels once, so an approval cannot point at a corrupt file."""
    try:
        from PIL import Image

        with Image.open(path) as image:
            image.load()
            return {
                "width": image.width,
                "height": image.height,
                "mode": image.mode,
                "format": image.format,
            }
    except Exception as exc:
        raise ValueError(f"state image is not a readable image: {path}") from exc


def needs_ladder(states: set[str]) -> bool:
    return any(state not in {"", "default", "full", "armored"} for state in states)


def exact_state_id(shot: dict[str, Any]) -> str | None:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    value = shot.get("wardrobe_state_id") or dsl.get("wardrobe_state_id")
    return str(value).strip() if value else None


def _states(ladder: dict[str, Any]) -> list[dict[str, Any]]:
    states = ladder.get("states") if isinstance(ladder.get("states"), list) else []
    return [state for state in states if isinstance(state, dict) and state.get("id")]


def state_for_id(bible: dict[str, Any], character_id: str, state_id: str) -> dict[str, Any] | None:
    ladders = (
        bible.get("wardrobe_ladders") if isinstance(bible.get("wardrobe_ladders"), dict) else {}
    )
    # Exact state IDs are character-owned pixel contracts.  Falling back to
    # hero would put another person's undress state on this character.
    for key in (character_id,):
        ladder = ladders.get(key)
        if not isinstance(ladder, dict):
            continue
        for state in _states(ladder):
            if str(state.get("id")) == state_id:
                return state
    return None


def resolve_exact_state_photo(
    bible: dict[str, Any], character_id: str, state_id: str, *, root: Path | None = None
) -> str | None:
    state = state_for_id(bible, character_id, state_id)
    if not state or state.get("status") != "approved" or not state.get("path"):
        return None
    path = Path(str(state["path"]))
    if root is not None and not path.is_absolute():
        path = root / path
    if root is not None and not path.is_file():
        return None
    return str(state["path"])


def resolve_state_photo_for_category(
    bible: dict[str, Any], character_id: str, wardrobe_state: str, *, root: Path | None = None
) -> str | None:
    """Return the deepest approved exact state tagged with a legacy category."""
    ladders = (
        bible.get("wardrobe_ladders") if isinstance(bible.get("wardrobe_ladders"), dict) else {}
    )
    wanted = str(wardrobe_state or "full").strip().lower()
    for key in (character_id,):
        ladder = ladders.get(key)
        if not isinstance(ladder, dict):
            continue
        matches = [
            state
            for state in _states(ladder)
            if str(state.get("wardrobe_state") or "").lower() == wanted
            and state.get("status") == "approved"
            and state.get("path")
        ]
        if matches:
            return resolve_exact_state_photo(bible, key, str(matches[-1]["id"]), root=root)
    return None


def ensure_ladder(
    bible: dict[str, Any], character_id: str, states_used: set[str], *, root: Path
) -> dict[str, Any] | None:
    """Create only an editable skeleton; never guess a garment inventory."""
    if not needs_ladder(states_used):
        return None
    ladders = bible.setdefault("wardrobe_ladders", {})
    if not isinstance(ladders, dict):
        ladders = {}
        bible["wardrobe_ladders"] = ladders
    ladder = ladders.get(character_id)
    if not isinstance(ladder, dict):
        ladder = {
            "status": "needs_wardrobe_breakdown",
            "garments": [],
            "states": [],
            "note": "List every removable garment outer-to-inner before state I2I generation.",
        }
        ladders[character_id] = ladder
    garments = ladder.get("garments") if isinstance(ladder.get("garments"), list) else []
    states = _states(ladder)
    if garments and not states:
        garment_ids = [
            str(item.get("id") or _slug(item.get("label")))
            if isinstance(item, dict)
            else _slug(item)
            for item in garments
        ]
        peak = (
            "bare"
            if "bare" in states_used
            else "undressed"
            if "undressed" in states_used
            else "partial"
        )
        cast_masters = (
            bible.get("cast_masters") if isinstance(bible.get("cast_masters"), dict) else {}
        )
        full_path = (
            cast_masters.get(character_id)
            or cast_masters.get("hero")
            or f"canonical/cast-states/{character_id}/full.png"
        )
        generated: list[dict[str, Any]] = [
            {
                "id": "full",
                "parent_state_id": None,
                "removed_garment_ids": [],
                "wardrobe_state": "full",
                "path": str(full_path),
                "status": "pending",
            }
        ]
        for index, garment_id in enumerate(garment_ids, start=1):
            state_id = f"remove-{_slug(garment_id)}"
            generated.append(
                {
                    "id": state_id,
                    "parent_state_id": generated[-1]["id"],
                    "removed_garment_ids": garment_ids[:index],
                    "wardrobe_state": peak if index == len(garment_ids) else "partial",
                    "path": f"canonical/cast-states/{character_id}/{state_id}.png",
                    "status": "pending",
                }
            )
        ladder["states"] = generated
        ladder["status"] = "pending_approval"
    return ladder


def ladder_plan(
    bible: dict[str, Any], character_id: str, *, root: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (hard issues, serial I2I plan) for a character ladder."""
    ladders = (
        bible.get("wardrobe_ladders") if isinstance(bible.get("wardrobe_ladders"), dict) else {}
    )
    ladder = ladders.get(character_id)
    if not isinstance(ladder, dict):
        return ([{"code": "MISSING_WARDROBE_LADDER", "character_id": character_id}], [])
    garments = ladder.get("garments") if isinstance(ladder.get("garments"), list) else []
    garment_ids = [
        str(item.get("id") or _slug(item.get("label"))) if isinstance(item, dict) else _slug(item)
        for item in garments
    ]
    if not garment_ids:
        return ([{"code": "NEEDS_WARDROBE_BREAKDOWN", "character_id": character_id}], [])
    states = _states(ladder)
    if len(states) != len(garment_ids) + 1 or not states or str(states[0].get("id")) != "full":
        return ([{"code": "WARDROBE_LADDER_STATES_INCOMPLETE", "character_id": character_id}], [])
    hard: list[dict[str, Any]] = []
    plan: list[dict[str, Any]] = []
    for index, state in enumerate(states):
        sid = str(state["id"])
        expected_parent = None if index == 0 else str(states[index - 1]["id"])
        if state.get("parent_state_id") != expected_parent:
            hard.append(
                {
                    "code": "WARDROBE_LADDER_PARENT_MISMATCH",
                    "character_id": character_id,
                    "state_id": sid,
                }
            )
        expected_removed = garment_ids[:index]
        if list(state.get("removed_garment_ids") or []) != expected_removed:
            hard.append(
                {
                    "code": "WARDROBE_LADDER_STEP_INVALID",
                    "character_id": character_id,
                    "state_id": sid,
                }
            )
        path_value = state.get("path") or f"canonical/cast-states/{character_id}/{sid}.png"
        state.setdefault("path", path_value)
        path = Path(str(path_value))
        if not path.is_absolute():
            path = root / path
        approved = state.get("status") == "approved" and path.is_file()
        if approved and state.get("sha256") != _sha256(path):
            hard.append(
                {"code": "WARDROBE_STATE_HASH_DRIFT", "character_id": character_id, "state_id": sid}
            )
        if index == 0:
            if not approved:
                hard.append(
                    {
                        "code": "WARDROBE_FULL_STATE_UNAPPROVED",
                        "character_id": character_id,
                        "state_id": sid,
                    }
                )
        elif not approved:
            parent = states[index - 1]
            parent_path = Path(str(parent.get("path") or ""))
            if not parent_path.is_absolute():
                parent_path = root / parent_path
            parent_ready = (
                parent.get("status") == "approved"
                and parent_path.is_file()
                and parent.get("sha256") == _sha256(parent_path)
            )
            if not parent_ready:
                hard.append(
                    {
                        "code": "WARDROBE_LADDER_PARENT_UNAPPROVED",
                        "character_id": character_id,
                        "state_id": sid,
                        "parent_state_id": expected_parent,
                    }
                )
                continue
            plan.append(
                {
                    "action": "generate_wardrobe_state_photo",
                    "character_id": character_id,
                    "wardrobe_state_id": sid,
                    "parent_state_id": expected_parent,
                    "remove_garment_id": garment_ids[index - 1],
                    "out": str(path_value),
                    "requires": "previous state approved; image_edit only from parent state photo",
                    "agent_hint": f"image_edit the approved {expected_parent} state; remove only {garment_ids[index - 1]}; save {path_value}; then aifilm state-index approve-state",
                }
            )
    return hard, plan


def approve_state(
    bible: dict[str, Any],
    character_id: str,
    state_id: str,
    image: Path,
    *,
    root: Path,
    reviewer: str,
    review_note: str,
    generation_receipt: Path | None = None,
) -> dict[str, Any]:
    """Promote a reviewed state photo and preserve its I2I provenance."""
    state = state_for_id(bible, character_id, state_id)
    if not state:
        raise ValueError(f"unknown wardrobe state {character_id}:{state_id}")
    reviewer = str(reviewer or "").strip()
    review_note = str(review_note or "").strip()
    if not reviewer or not review_note:
        raise ValueError("reviewer and review_note are required to approve a wardrobe state")
    image = image.expanduser().resolve()
    if not image.is_file():
        raise ValueError(f"state image does not exist: {image}")
    image_meta = _image_metadata(image)
    image_sha = _sha256(image)
    parent_id = state.get("parent_state_id")
    parent: dict[str, Any] | None = None
    if parent_id:
        parent = state_for_id(bible, character_id, str(parent_id))
        if not parent or parent.get("status") != "approved":
            raise ValueError(f"parent state {parent_id} must be approved first")
        if not parent.get("sha256"):
            raise ValueError(f"parent state {parent_id} has no approved image hash")
        parent_path = Path(str(parent.get("path") or ""))
        if not parent_path.is_absolute():
            parent_path = root / parent_path
        if not parent_path.is_file() or _sha256(parent_path) != parent["sha256"]:
            raise ValueError(f"parent state {parent_id} image is missing or hash-drifted")
        if generation_receipt is None:
            raise ValueError("generation_receipt is required for a non-full I2I wardrobe state")
    receipt_record: dict[str, str] | None = None
    if generation_receipt is not None:
        generation_receipt = generation_receipt.expanduser().resolve()
        if not generation_receipt.is_file():
            raise ValueError(f"generation receipt does not exist: {generation_receipt}")
        try:
            parsed_receipt = json.loads(generation_receipt.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("generation_receipt must be a readable JSON receipt") from exc
        if not isinstance(parsed_receipt, dict):
            raise ValueError("generation_receipt must contain a JSON object")
        if parent:
            required_receipt = {
                "kind": "image_edit",
                "parent_state_id": str(parent_id),
                "parent_state_sha256": str(parent["sha256"]),
                "output_sha256": image_sha,
            }
            mismatched = [
                key
                for key, expected in required_receipt.items()
                if parsed_receipt.get(key) != expected
            ]
            if mismatched:
                raise ValueError(
                    "generation_receipt must bind image_edit parent and output hashes: "
                    + ", ".join(mismatched)
                )
        receipt_record = {
            "path": _stored_path(generation_receipt, root),
            "sha256": _sha256(generation_receipt),
        }
    approved_at = utc_now()
    parent_record = (
        {
            "state_id": str(parent_id),
            "path": str(parent["path"]),
            "sha256": str(parent["sha256"]),
        }
        if parent
        else None
    )
    state.update(
        {
            "path": _stored_path(image, root),
            "sha256": image_sha,
            "status": "approved",
            "approved_at": approved_at,
            "reviewer": reviewer,
            "review_note": review_note,
            "parent_state_sha256": parent_record["sha256"] if parent_record else None,
            "generation_receipt": receipt_record,
            "approval": {
                "reviewer": reviewer,
                "review_note": review_note,
                "approved_at": approved_at,
                "image": {"sha256": image_sha, **image_meta},
                "parent": parent_record,
                "generation_receipt": receipt_record,
            },
        }
    )
    return state


def render_contact_sheet(bible: dict[str, Any], character_id: str, *, root: Path) -> dict[str, Any]:
    """Render an offline visual review sheet of every canonical ladder state."""
    ladder = (
        bible.get("wardrobe_ladders", {}).get(character_id)
        if isinstance(bible.get("wardrobe_ladders"), dict)
        else None
    )
    if not isinstance(ladder, dict) or not _states(ladder):
        raise ValueError(f"no wardrobe ladder states for {character_id}")
    try:
        from PIL import Image, ImageDraw, ImageOps
    except ImportError as exc:
        raise ValueError("Pillow is required to render a wardrobe contact sheet") from exc

    states = _states(ladder)
    cell_w, cell_h, label_h, cols = 360, 330, 88, 2
    rows = (len(states) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell_w, 36 + rows * (cell_h + label_h)), "#171717")
    draw = ImageDraw.Draw(sheet)
    draw.text((12, 10), f"WARDROBE LADDER · {character_id}", fill="white")
    state_rows: list[dict[str, Any]] = []
    for index, state in enumerate(states):
        x, y = (index % cols) * cell_w, 36 + (index // cols) * (cell_h + label_h)
        tile = Image.new("RGB", (cell_w, cell_h), "#454545")
        state_path = Path(str(state.get("path") or ""))
        if not state_path.is_absolute():
            state_path = root / state_path
        exists = state_path.is_file()
        if exists:
            try:
                with Image.open(state_path) as source:
                    source.load()
                    tile.paste(ImageOps.contain(source.convert("RGB"), tile.size), (0, 0))
            except Exception:
                exists = False
        if not exists:
            ImageDraw.Draw(tile).text((12, 12), "MISSING / INVALID", fill="#ffb4b4")
        sheet.paste(tile, (x, y))
        removed = (
            ", ".join(str(value) for value in state.get("removed_garment_ids") or []) or "none"
        )
        label = f"{state['id']} · {state.get('status', 'pending')}\nremoved: {removed}"
        draw.multiline_text((x + 8, y + cell_h + 8), label, fill="white", spacing=3)
        state_rows.append(
            {
                "id": str(state["id"]),
                "status": str(state.get("status") or "pending"),
                "removed_garment_ids": list(state.get("removed_garment_ids") or []),
                "path": str(state.get("path") or ""),
                "exists": exists,
            }
        )
    out = root / "canonical" / "cast-states" / character_id / "contact-sheet.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    temp = out.with_suffix(".tmp.png")
    sheet.save(temp, format="PNG")
    temp.replace(out)
    return {"path": _stored_path(out, root), "sha256": _sha256(out), "states": state_rows}
