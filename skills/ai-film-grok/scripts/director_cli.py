#!/usr/bin/env python3
"""Director-facing production-book lifecycle operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from department_cli import (
    DEPARTMENT_FILES,
    mark_department_stale,
    migrate_department,
    show_department,
    sync_department_book,
    validate_department,
)
from production_book import (
    apply_stale_propagation,
    impact_dry_run,
    init_production_book,
    read_production_book,
    stable_content_hash,
    write_production_book,
)
from util import read_json

_DEPARTMENT_SCHEMA_TARGETS = {"visual": 3, "audio": 1, "post": 1}


def director_init(
    root: Path | str,
    *,
    title: str = "Untitled",
    rigor: str = "professional",
    format_pack: str = "vertical-short",
    genre_pack: str = "drama",
) -> dict[str, Any]:
    book = init_production_book(
        root, title=title, rigor=rigor, format_pack=format_pack, genre_pack=genre_pack
    )
    return {"ok": True, "action": "init", "book": book}


def migrate_audit(root: Path | str) -> dict[str, Any]:
    base = Path(root).expanduser().resolve()
    items = []
    for department, filename in DEPARTMENT_FILES.items():
        if department == "sound":
            continue
        path = base / filename
        value = read_json(path) if path.is_file() else None
        current_version = value.get("schema_version") if isinstance(value, dict) else None
        target_version = _DEPARTMENT_SCHEMA_TARGETS[department]
        items.append(
            {
                "department": department,
                "path": str(path),
                "exists": path.is_file(),
                "from_version": current_version,
                "to_version": target_version,
                "needs_migration": path.is_file() and current_version != target_version,
                "status": "missing"
                if not path.is_file()
                else "current"
                if current_version == target_version
                else "migratable",
            }
        )
    return {
        "ok": True,
        "action": "migrate-audit",
        "dry_run": True,
        "production_book_exists": (base / "production-book.json").is_file(),
        "departments": items,
    }


def migrate(root: Path | str, *, title: str = "Untitled") -> dict[str, Any]:
    base = Path(root).expanduser().resolve()
    init_production_book(base, title=title, rigor="legacy")
    migrated = []
    for item in migrate_audit(base)["departments"]:
        if item["needs_migration"]:
            migrated.append(migrate_department(base, item["department"]))
        elif item["exists"]:
            value = show_department(base, item["department"])["department"]
            sync_department_book(base, item["department"], value)
    return {
        "ok": True,
        "action": "migrate",
        "book": read_production_book(base),
        "migrated": migrated,
    }


def status(root: Path | str) -> dict[str, Any]:
    from director_stage_gates import stage_status

    book = read_production_book(root)
    departments = book.get("departments") or {}
    return {
        "ok": True,
        "action": "status",
        "rigor": book.get("rigor"),
        "revision": book.get("revision"),
        "state": book.get("state"),
        "department_locks": {
            key: value.get("state") == "locked" for key, value in departments.items()
        },
        "stale_reasons": book.get("stale_reasons") or [],
        "asset_versions": [
            {"id": item.get("id"), "version": item.get("version"), "hash": item.get("hash")}
            for item in book.get("assets") or []
            if isinstance(item, dict)
        ],
        "stage_gates": stage_status(root),
    }


def check(root: Path | str) -> dict[str, Any]:
    from director_stage_gates import stage_status

    book = read_production_book(root)
    errors: list[str] = []
    if book.get("content_sha256") != stable_content_hash(book):
        errors.append("production-book content hash is stale")
    departments = []
    required_departments = {"visual", "audio", "post"}
    if book.get("rigor") == "professional":
        for required in ("drama-graph.json", "film-spec.json"):
            if not (Path(root) / required).is_file():
                errors.append(f"story: required canonical file is missing: {required}")
    for department, filename in DEPARTMENT_FILES.items():
        if department == "sound":
            continue
        if (Path(root) / filename).is_file():
            report = validate_department(root, department)
            departments.append(report)
            errors.extend(f"{department}: {item}" for item in report["errors"])
            bible = read_json(Path(root) / filename) or {}
            if department == "audio":
                from audio_bible import validate_audio_bible

                errors.extend(
                    f"audio: {item['message']}" for item in validate_audio_bible(bible)["errors"]
                )
            elif department == "post":
                from post_bible import validate_post_bible

                errors.extend(
                    f"post: {item['message']}" for item in validate_post_bible(bible)["errors"]
                )
        elif book.get("rigor") == "professional" and department in required_departments:
            errors.append(f"{department}: required department bible is missing")
    stage_gates = stage_status(root)
    errors.extend(f"stage {item['stage']}: {item['message']}" for item in stage_gates["blocking"])
    if book.get("rigor") == "professional" and stage_gates.get("next_stage") is None:
        from master_delivery import validate_master_delivery

        sidecar = read_json(Path(root) / "receipts" / "master-delivery.json")
        if not isinstance(sidecar, dict):
            errors.append("master: receipts/master-delivery.json is missing")
        else:
            master = validate_master_delivery(root, delivery=sidecar)
            errors.extend(f"master: {item['message']}" for item in master["issues"])
    return {
        "ok": not errors,
        "action": "check",
        "errors": errors,
        "departments": departments,
        "stage_gates": stage_gates,
    }


def impact(root: Path | str, *, changed_refs: list[str], reason: str) -> dict[str, Any]:
    return impact_dry_run(read_production_book(root), changed_refs, reason=reason)


def rebuild(
    root: Path | str,
    *,
    changed_refs: list[str],
    reason: str,
    expected_revision: int,
    transaction_id: str | None = None,
) -> dict[str, Any]:
    book = read_production_book(root)
    preview = impact_dry_run(book, changed_refs, reason=reason)
    changed = apply_stale_propagation(
        book,
        preview,
        expected_revision=expected_revision,
        transaction_id=transaction_id or preview["transaction_id"],
    )
    for department, dependency_ref in (("visual", "visual"), ("audio", "sound"), ("post", "post")):
        path = Path(root).expanduser().resolve() / DEPARTMENT_FILES[department]
        if dependency_ref not in preview["affected"] or not path.is_file():
            continue
        bible = mark_department_stale(
            root,
            department,
            reason=reason,
            transaction_id=preview["transaction_id"],
        )
        book_ref = "sound" if department == "audio" else department
        changed["departments"][book_ref].update(
            {
                "revision": bible["revision"],
                "content_sha256": bible["hash"],
                "state": "stale",
            }
        )
    written = write_production_book(root, changed, expected_revision=expected_revision)
    return {
        "ok": True,
        "action": "rebuild",
        "transaction_id": preview["transaction_id"],
        "impact": preview,
        "book": written,
    }
