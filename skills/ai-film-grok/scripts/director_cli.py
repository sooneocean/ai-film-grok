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
    quality_target: str | None = None,
) -> dict[str, Any]:
    existing = Path(root).expanduser().resolve() / "production-book.json"
    if existing.is_file() and quality_target is not None:
        current = read_production_book(root).get("quality_target", "standard")
        if quality_target != current:
            raise ValueError(
                f"existing production book already uses quality_target={current}; "
                "create a migration/change record before switching profiles"
            )
    book = init_production_book(
        root,
        title=title,
        rigor=rigor,
        format_pack=format_pack,
        genre_pack=genre_pack,
        quality_target=quality_target or "standard",
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
        "quality_target": book.get("quality_target", "standard"),
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
    quality_target = str(book.get("quality_target") or "standard")
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
    quality = None
    if quality_target == "premium_vertical":
        from creative_quality import validate_premium_vertical

        quality = validate_premium_vertical(root)
        errors.extend(f"creative: {item['message']}" for item in quality["errors"])
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
        "quality": quality,
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


def verify(root: Path | str) -> dict[str, Any]:
    """Run director methodology verification: pace_chart, act_structure, music_spotting.

    Loads film-spec + drama-graph, extracts shots/beats, and runs the three
    verification functions from rhythm.py. Returns a combined report.
    """
    root = Path(root)
    spec = read_json(root / "film-spec.json") or {}
    graph = read_json(root / "drama-graph.json") or {}

    # Collect all shots from film-spec scenes
    shots: list[dict[str, Any]] = []
    for sc in spec.get("scenes") or []:
        if isinstance(sc, dict):
            for sh in sc.get("shots") or []:
                if isinstance(sh, dict):
                    shots.append(sh)

    # Collect beats from drama-graph episodes
    beats: list[dict[str, Any]] = []
    for ep in graph.get("episodes") or []:
        if isinstance(ep, dict):
            for sc in ep.get("scenes") or []:
                if isinstance(sc, dict):
                    for bt in sc.get("beats") or []:
                        if isinstance(bt, dict):
                            beats.append(bt)

    di = spec.get("director_intent") if isinstance(spec.get("director_intent"), dict) else {}
    pace_chart = di.get("pace_chart") or []
    act_structure = di.get("act_structure") or {}
    sound_plan = spec.get("sound_plan") if isinstance(spec.get("sound_plan"), dict) else {}
    music_spotting = sound_plan.get("music_spotting") or []

    total_duration = (
        sum(float(s.get("duration_sec") or s.get("targetDuration") or 0) for s in shots) or None
    )

    results: dict[str, Any] = {"ok": True, "action": "verify"}

    # 1. Pace chart verification
    if pace_chart and shots:
        from rhythm import verify_pace_chart

        pace_result = verify_pace_chart(shots, pace_chart, total_duration=total_duration)
        results["pace_chart"] = pace_result
        if not pace_result["ok"]:
            results["ok"] = False

    # 2. Act structure verification
    if act_structure and shots:
        from rhythm import verify_act_structure

        act_result = verify_act_structure(shots, act_structure, total_duration=total_duration)
        results["act_structure"] = act_result
        if not act_result["ok"]:
            results["ok"] = False

    # 3. Music spotting verification
    if music_spotting:
        from rhythm import verify_music_spotting

        music_result = verify_music_spotting(
            music_spotting, beats=beats, total_duration=total_duration
        )
        results["music_spotting"] = music_result
        if not music_result["ok"]:
            results["ok"] = False

    results["shots_checked"] = len(shots)
    results["beats_checked"] = len(beats)
    results["note"] = (
        "Director methodology verification: pace_chart + act_structure + music_spotting. "
        "Soft warnings only — does not block delivery."
    )
    return results
