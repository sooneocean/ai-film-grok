"""Hash-bound performance-state stills for dialogue shots."""

from __future__ import annotations

import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from util import canonical_json_sha256, read_json, sha256_file, utc_now, write_json

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$")


def _identifier(value: object, *, field: str) -> str:
    text = str(value or "").strip()
    if not _SAFE_ID.fullmatch(text):
        raise ValueError(f"{field} must be a safe identifier")
    return text


def _logical_identifier(value: object, *, field: str) -> str:
    text = str(value or "")
    if (
        not text
        or text != text.strip()
        or len(text) > 255
        or not all(char.isalnum() or char in "_-" for char in text)
    ):
        raise ValueError(f"{field} must be a safe logical identifier")
    return text


def _path_token(value: object, *, field: str) -> str:
    logical = _logical_identifier(value, field=field)
    if _SAFE_ID.fullmatch(logical):
        return logical
    return f"id-{sha256(logical.encode('utf-8')).hexdigest()[:20]}"


def performance_state_contract(shot: dict[str, Any]) -> dict[str, Any]:
    """Return only state-changing visual facts; dialogue text is intentionally excluded."""
    state = shot.get("performance_state") if isinstance(shot.get("performance_state"), dict) else {}
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    camera = dsl.get("camera") if isinstance(dsl.get("camera"), dict) else {}
    props = state.get("props")
    if not isinstance(props, list):
        props = dsl.get("props") if isinstance(dsl.get("props"), list) else []
    return {
        "speaker": str(shot.get("speaker") or "").strip(),
        "scene_id": str(shot.get("scene_id") or shot.get("scene_ref") or "").strip(),
        "wardrobe_state": str(
            shot.get("wardrobe_state") or dsl.get("wardrobe_state") or "full"
        ).strip(),
        "hair": str(state.get("hair") or shot.get("hair_state") or "").strip(),
        "makeup": str(state.get("makeup") or shot.get("makeup_state") or "").strip(),
        "emotion": str(state.get("emotion") or "neutral").strip(),
        "gaze_target": str(state.get("gaze_target") or shot.get("gaze_target") or "").strip(),
        "head_angle": str(state.get("head_angle") or "").strip(),
        "body_orientation": str(state.get("body_orientation") or "").strip(),
        "gesture": str(state.get("gesture") or shot.get("playable_action") or "").strip(),
        "props": sorted(str(item).strip() for item in props if str(item).strip()),
        "lighting": str(state.get("lighting") or dsl.get("lighting") or "").strip(),
        "space_position": str(
            state.get("space_position")
            or shot.get("space_position")
            or dsl.get("space_position")
            or ""
        ).strip(),
        "shot_size": str(state.get("shot_size") or camera.get("shot_size") or "").strip(),
        "continuity_parent": str(
            state.get("continuity_parent") or shot.get("continuity_parent") or ""
        ).strip(),
    }


def performance_state_id(shot: dict[str, Any]) -> str:
    contract = performance_state_contract(shot)
    speaker = _path_token(contract["speaker"] or "hero", field="speaker")
    digest = canonical_json_sha256(contract)
    return f"{speaker}-state-{digest[:12]}"


def _state_paths(root: Path, *, speaker: str, state_id: str) -> tuple[Path, Path]:
    speaker = _path_token(speaker, field="speaker")
    state_id = _path_token(state_id, field="state_id")
    image = root / "canonical" / "performance-states" / speaker / f"{state_id}.png"
    receipt = root / "receipts" / "performance-states" / speaker / f"{state_id}.json"
    return image, receipt


def approve_performance_state(
    root: Path,
    *,
    speaker: str,
    state_id: str,
    image: Path,
    generation_receipt: Path,
    reviewer: str,
    review_note: str,
) -> dict[str, Any]:
    """Register an already-generated state still; never calls an image provider."""
    root = Path(root).expanduser().resolve()
    expected_image, receipt_path = _state_paths(root, speaker=speaker, state_id=state_id)
    source = Path(image).expanduser().resolve()
    if source != expected_image.resolve():
        raise ValueError(f"performance state image must be {expected_image}")
    if not source.is_file():
        raise ValueError("performance state image is missing")
    try:
        from PIL import Image

        with Image.open(source) as decoded:
            decoded.verify()
    except Exception as exc:  # noqa: BLE001
        raise ValueError("performance state image is not readable") from exc
    generation = read_json(Path(generation_receipt).expanduser().resolve())
    if not isinstance(generation, dict):
        raise ValueError("generation receipt is missing or invalid")
    operation = str(generation.get("operation") or generation.get("kind") or "").lower()
    if "image_edit" not in operation and "image-edit" not in operation:
        raise ValueError("performance state requires an image_edit generation receipt")
    input_sha = str(generation.get("input_sha256") or "")
    output_sha = str(generation.get("output_sha256") or "")
    actual_sha = sha256_file(source)
    if not _SHA256.fullmatch(input_sha):
        raise ValueError("generation receipt requires input_sha256")
    if output_sha != actual_sha:
        raise ValueError("generation receipt output_sha256 does not match image")
    model = str(generation.get("model") or generation.get("model_id") or "").strip()
    if not model:
        raise ValueError("generation receipt requires model")
    if not str(reviewer or "").strip() or not str(review_note or "").strip():
        raise ValueError("reviewer and review_note are required")
    payload = {
        "schema_version": 1,
        "kind": "dialogue-performance-state-approval",
        "speaker": _logical_identifier(speaker, field="speaker"),
        "performance_state_id": _logical_identifier(state_id, field="state_id"),
        "image": {
            "path": str(source),
            "sha256": actual_sha,
        },
        "lineage": {
            "operation": "image_edit",
            "provider": str(generation.get("provider") or ""),
            "model": model,
            "input_sha256": input_sha,
            "output_sha256": output_sha,
            "generation_receipt_sha256": sha256_file(
                Path(generation_receipt).expanduser().resolve()
            ),
        },
        "approval": {
            "status": "approved",
            "reviewer": str(reviewer).strip(),
            "note": str(review_note).strip(),
            "approved_at": utc_now(),
        },
    }
    write_json(receipt_path, payload)
    return payload


def validate_performance_state(root: Path, *, speaker: str, state_id: str) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    image, receipt_path = _state_paths(root, speaker=speaker, state_id=state_id)
    receipt = read_json(receipt_path)
    codes: list[str] = []
    if not image.is_file():
        codes.append("STATE_IMAGE_MISSING")
    if not isinstance(receipt, dict):
        codes.append("STATE_APPROVAL_MISSING")
        receipt = {}
    expected = str((receipt.get("image") or {}).get("sha256") or "")
    actual = sha256_file(image) if image.is_file() else ""
    if image.is_file() and expected != actual:
        codes.append("OUTPUT_HASH_DRIFT")
    lineage = receipt.get("lineage") if isinstance(receipt.get("lineage"), dict) else {}
    if lineage.get("operation") != "image_edit":
        codes.append("I2I_LINEAGE_MISSING")
    if not _SHA256.fullmatch(str(lineage.get("input_sha256") or "")):
        codes.append("PARENT_HASH_MISSING")
    if not str(lineage.get("model") or "").strip():
        codes.append("MODEL_PROVENANCE_MISSING")
    approval = receipt.get("approval") if isinstance(receipt.get("approval"), dict) else {}
    if approval.get("status") != "approved" or not str(approval.get("reviewer") or "").strip():
        codes.append("HUMAN_APPROVAL_MISSING")
    return {
        "ok": not codes,
        "speaker": speaker,
        "performance_state_id": state_id,
        "image_path": str(image),
        "image_sha256": actual or None,
        "receipt_path": str(receipt_path),
        "codes": codes,
    }
