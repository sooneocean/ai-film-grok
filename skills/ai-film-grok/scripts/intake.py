"""双模态项目接收：小说原文与角色定装图的证据化 staging。"""

from __future__ import annotations

import hashlib
import mimetypes
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from util import read_json, sha256_file, write_json

MANIFEST_NAME = "intake-manifest.json"
RECEIPT_NAME = "intake-report.json"
REVIEW_NAME = "intake-review.json"
SUPPORTED_STORY_SUFFIXES = {".md", ".markdown", ".txt"}
SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
_HEADING = re.compile(r"^#{1,6}\s*(.+?)\s*$")


class IntakeError(ValueError):
    """接收输入不满足可回溯契约。"""


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _safe_relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _image_dimensions(path: Path) -> tuple[int, int] | None:
    """Read common image dimensions without decoding or importing an image library."""
    data = path.read_bytes()[:64]
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data.startswith(b"\xff\xd8"):
        raw = path.read_bytes()
        i = 2
        sof_markers = (
            set(range(0xC0, 0xC4))
            | set(range(0xC5, 0xC8))
            | set(range(0xC9, 0xCC))
            | set(range(0xCD, 0xD0))
        )
        while i + 9 < len(raw):
            if raw[i] != 0xFF:
                i += 1
                continue
            marker = raw[i + 1]
            i += 2
            if marker in {0xD8, 0xD9}:
                continue
            if i + 2 > len(raw):
                break
            size = int.from_bytes(raw[i : i + 2], "big")
            if marker in sof_markers and i + 7 <= len(raw):
                return int.from_bytes(raw[i + 5 : i + 7], "big"), int.from_bytes(
                    raw[i + 3 : i + 5], "big"
                )
            if size < 2:
                break
            i += size
    return None


def _file_record(path: Path, root: Path, *, role: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise IntakeError(f"{role} must be a regular file: {path}")
    record: dict[str, Any] = {
        "path": _safe_relative(path, root),
        "name": path.name,
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "mime": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
    }
    dims = _image_dimensions(path) if path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES else None
    if dims:
        record["width"], record["height"] = dims
        record["aspect_ratio"] = round(dims[0] / dims[1], 5) if dims[1] else None
    return record


def _copy_into(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _paragraph_evidence(text: str, *, source_ref: str) -> list[dict[str, Any]]:
    """Create stable paragraph refs while retaining exact source offsets."""
    evidence: list[dict[str, Any]] = []
    chapter = "chapter_01"
    paragraph_index = 0
    for block in re.finditer(r"\S[\s\S]*?(?=\n\s*\n|\Z)", text):
        raw = block.group(0)
        body = raw.strip()
        if not body:
            continue
        if _HEADING.match(body.splitlines()[0].strip()):
            chapter = f"chapter_{len({item['chapter_id'] for item in evidence}) + 1:02d}"
        paragraph_index += 1
        start = block.start() + len(raw) - len(raw.lstrip())
        end = start + len(body)
        evidence.append(
            {
                "id": f"{chapter}:paragraph_{paragraph_index:04d}",
                "source_ref": f"{source_ref}:{chapter}:paragraph_{paragraph_index:04d}",
                "chapter_id": chapter,
                "paragraph_index": paragraph_index,
                "char_start": start,
                "char_end": end,
                "text": body,
                "text_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            }
        )
    return evidence


def create_intake(
    root: Path,
    *,
    story: Path,
    characters: list[tuple[str, Path]],
    language: str = "zh-CN",
    character_names: dict[str, str] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    story = Path(story).expanduser().resolve()
    if story.suffix.lower() not in SUPPORTED_STORY_SUFFIXES:
        raise IntakeError(f"unsupported story type: {story.suffix or '<none>'}")
    if not story.is_file() or story.is_symlink():
        raise IntakeError(f"story must be a regular file: {story}")
    if not characters:
        raise IntakeError("at least one --character id=path is required")
    ids = [cid.strip() for cid, _ in characters]
    if any(not cid or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", cid) for cid in ids):
        raise IntakeError("character ids must match [A-Za-z][A-Za-z0-9_-]{0,63}")
    if len(set(ids)) != len(ids):
        raise IntakeError("duplicate character id")
    manifest_path = root / MANIFEST_NAME
    if manifest_path.exists() and not force:
        raise IntakeError(f"{manifest_path} exists; pass --force to replace intake")

    story_dest = root / "intake" / "story" / story.name
    _copy_into(story, story_dest)
    story_record = _file_record(story_dest, root, role="staged story")
    source_ref = f"novel:{story_record['sha256'][:16]}"
    characters_out: list[dict[str, Any]] = []
    character_names = character_names or {}
    for cid, image in characters:
        image = Path(image).expanduser().resolve()
        if image.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
            raise IntakeError(f"unsupported character image type: {image.suffix or '<none>'}")
        if not image.is_file() or image.is_symlink():
            raise IntakeError(f"character image must be a regular file: {image}")
        dest = root / "intake" / "characters" / cid / image.name
        _copy_into(image, dest)
        record = _file_record(dest, root, role=f"character image {cid}")
        characters_out.append(
            {
                "id": cid,
                "name": character_names.get(cid, cid),
                "aliases": [],
                "reference_role": "costume_identity",
                "reference_image": record,
                "visual_features": {
                    "status": "needs_visual_review",
                    "identity": [],
                    "wardrobe": [],
                    "signature_features": [],
                },
                "review_status": "needs_review",
            }
        )

    manifest = {
        "schema_version": 1,
        "kind": "ai-film-intake",
        "created_at": _utc_now(),
        "language": language,
        "story": {"kind": "novel", "source_ref": source_ref, "file": story_record},
        "characters": characters_out,
        "status": "staged",
    }
    write_json(manifest_path, manifest)
    return validate_intake(root, write_receipt=True)


def validate_intake(root: Path, *, write_receipt: bool = True) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    manifest = read_json(root / MANIFEST_NAME)
    errors: list[str] = []
    warnings: list[str] = []
    if not manifest:
        return {"ok": False, "errors": [f"missing {MANIFEST_NAME}"], "warnings": []}
    story = (manifest.get("story") or {}).get("file") or {}
    records = [("story", story)]
    for char in manifest.get("characters") or []:
        records.append((f"character:{char.get('id')}", char.get("reference_image") or {}))
    for role, record in records:
        path = root / str(record.get("path") or "")
        try:
            actual = _file_record(path, root, role=role)
            if actual["sha256"] != record.get("sha256"):
                errors.append(f"{role}: sha256 changed")
            if role.startswith("character:"):
                dims = actual.get("width"), actual.get("height")
                if not dims or not all(isinstance(x, int) and x > 0 for x in dims):
                    errors.append(f"{role}: image dimensions unavailable")
                elif dims[0] < 512 or dims[1] < 512:
                    warnings.append(f"{role}: reference image is below 512px on one axis")
        except (OSError, IntakeError) as exc:
            errors.append(f"{role}: {exc}")
    evidence: list[dict[str, Any]] = []
    story_path = root / str(story.get("path") or "")
    if not errors and story_path.is_file():
        text = story_path.read_text(encoding="utf-8")
        evidence = _paragraph_evidence(
            text, source_ref=str((manifest.get("story") or {}).get("source_ref"))
        )
        if not evidence:
            errors.append("story: no non-empty paragraphs found")
    bindings = _character_bindings(manifest, evidence)
    score = _score_intake(manifest, errors, warnings, bindings)
    report = {
        "schema_version": 1,
        "kind": "intake-report",
        "at": _utc_now(),
        "ok": not errors,
        "root": str(root),
        "errors": errors,
        "warnings": warnings,
        "story": {"paragraph_count": len(evidence), "evidence": evidence},
        "characters": [
            {
                "id": c.get("id"),
                "name": c.get("name"),
                "reference": c.get("reference_image"),
                "review_status": c.get("review_status", "needs_review"),
            }
            for c in manifest.get("characters") or []
        ],
        "character_bindings": bindings,
        "quality": score,
    }
    if write_receipt:
        write_json(root / "receipts" / RECEIPT_NAME, report)
    return report


def _character_bindings(
    manifest: dict[str, Any], evidence: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Deterministic first pass; visual identity is never auto-approved."""
    joined = "\n".join(str(item.get("text") or "") for item in evidence)
    bindings: list[dict[str, Any]] = []
    for char in manifest.get("characters") or []:
        cid = str(char.get("id") or "")
        names = [str(char.get("name") or cid)] + [str(x) for x in char.get("aliases") or []]
        hits = [name for name in names if name and name in joined]
        confidence = (
            "confirmed"
            if hits and char.get("review_status") == "approved"
            else ("probable" if hits else "unmatched")
        )
        bindings.append(
            {
                "character_id": cid,
                "matched_names": hits,
                "confidence": confidence,
                "evidence_refs": [
                    item["source_ref"]
                    for item in evidence
                    if any(name and name in str(item.get("text") or "") for name in names)
                ],
                "review_required": confidence != "confirmed",
            }
        )
    return bindings


def _score_intake(
    manifest: dict[str, Any],
    errors: list[str],
    warnings: list[str],
    bindings: list[dict[str, Any]],
) -> dict[str, Any]:
    characters = manifest.get("characters") or []
    story_score = 0 if errors and any(item.startswith("story:") for item in errors) else 1
    reference_score = sum(
        1 for char in characters if (char.get("reference_image") or {}).get("width", 0) >= 512
    )
    reference_score = round(reference_score / len(characters), 2) if characters else 0
    binding_score = sum(item["confidence"] != "unmatched" for item in bindings)
    binding_score = round(binding_score / len(bindings), 2) if bindings else 0
    review_score = sum(char.get("review_status") == "approved" for char in characters)
    review_score = round(review_score / len(characters), 2) if characters else 0
    overall = round(
        100
        * (
            0.25 * story_score + 0.30 * reference_score + 0.25 * binding_score + 0.20 * review_score
        ),
        1,
    )
    return {
        "overall": overall,
        "story_parse": story_score,
        "reference_quality": reference_score,
        "character_binding": binding_score,
        "human_review": review_score,
        "warnings": len(warnings),
        "ready_for_planning": not errors and story_score == 1,
        "ready_for_generation": not errors and review_score == 1 and binding_score == 1,
    }


def approve_character(
    root: Path, *, character_id: str, user_phrase: str, notes: str = ""
) -> dict[str, Any]:
    if not str(user_phrase).strip():
        raise IntakeError("user_phrase is required for character approval")
    root = Path(root).expanduser().resolve()
    manifest = read_json(root / MANIFEST_NAME)
    if not manifest:
        raise IntakeError(f"missing {MANIFEST_NAME}")
    found = False
    for char in manifest.get("characters") or []:
        if char.get("id") == character_id:
            char["review_status"] = "approved"
            char["visual_features"]["status"] = "reviewed"
            char["approval_ref"] = f"user:{user_phrase.strip()}"
            if notes:
                char["review_notes"] = notes
            found = True
            break
    if not found:
        raise IntakeError(f"unknown character id: {character_id}")
    manifest["status"] = "review"
    write_json(root / MANIFEST_NAME, manifest)
    report = validate_intake(root, write_receipt=True)
    review = {
        "schema_version": 1,
        "kind": "intake-review",
        "at": _utc_now(),
        "user_phrase": user_phrase.strip(),
        "character_id": character_id,
        "notes": notes,
        "quality": report.get("quality"),
    }
    write_json(root / "receipts" / REVIEW_NAME, review)
    return {"ok": True, "report": report, "review": review}


def inspect_intake(root: Path) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    report = validate_intake(root, write_receipt=True)
    manifest = read_json(root / MANIFEST_NAME) or {}
    return {
        "ok": report.get("ok"),
        "manifest": manifest,
        "receipt": str(root / "receipts" / RECEIPT_NAME),
        "summary": {
            "characters": len(manifest.get("characters") or []),
            "story_paragraphs": (report.get("story") or {}).get("paragraph_count", 0),
            "errors": len(report.get("errors") or []),
            "warnings": len(report.get("warnings") or []),
        },
    }
