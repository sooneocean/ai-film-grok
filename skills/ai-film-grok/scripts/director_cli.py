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
_BOOK_DEPARTMENT_KEYS = {
    "visual": ("visual", "style-bible"),
    "audio": ("sound", "audio", "audio-bible"),
    "post": ("post", "post-bible"),
}
_STAGE_INPUT_CANDIDATES: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "concept_lock": (("brief", ("brief.json",)), ("story", ("drama-graph.json",))),
    "script_lock": (("story", ("drama-graph.json",)), ("shots", ("film-spec.json",))),
    "department_look_lock": (("visual", ("style-bible.json",)),),
    "shot_animatic_lock": (
        ("story", ("drama-graph.json",)),
        ("shots", ("film-spec.json",)),
        ("timeline", ("timeline.json",)),
    ),
    "pilot_approval": (("pilot", ("receipts/pilot-approval.json",)),),
    "bulk": (("manifest", ("manifest.json",)),),
    "dailies_review": (("dailies", ("receipts/dailies.json",)),),
    "selects_rough_cut": (
        ("dailies", ("receipts/dailies.json",)),
        ("selects", ("receipts/selects-report.json",)),
        ("rough", ("receipts/rough-cut.json", "receipts/editor-cut.json")),
    ),
    "picture_lock": (("picture", ("receipts/picture-lock.json",)),),
    "post_locks": (
        ("post", ("post-plan.json",)),
        ("voice", ("receipts/tts-rehearsal.json", "audio/mix_report.json")),
        ("review", ("receipts/review-control.json", "receipts/review-actions.json")),
    ),
    "master_lock": (
        ("delivery", ("receipts/master-delivery.json",)),
        ("review", ("out/final-review.json", "receipts/final-review.json")),
        ("audit", ("receipts/post-audit.json",)),
    ),
}


def native_stage_input_refs(root: Path | str, stage: str) -> dict[str, str]:
    """Resolve exact native evidence files for one director lock."""
    from director_stage_gates import STAGE_ORDER, StageGateError

    if stage not in STAGE_ORDER:
        raise StageGateError(f"unknown stage: {stage}")
    base = Path(root).expanduser().resolve()
    refs: dict[str, str] = {}
    missing: list[str] = []
    for name, candidates in _STAGE_INPUT_CANDIDATES[stage]:
        selected = next((relative for relative in candidates if (base / relative).is_file()), None)
        if selected is None:
            missing.append(f"{name} ({' | '.join(candidates)})")
        else:
            refs[name] = selected
    if missing:
        raise StageGateError(f"native evidence missing for {stage}: " + ", ".join(missing))
    if stage in {"bulk", "dailies_review", "selects_rough_cut"}:
        if stage == "bulk":
            manifest = read_json(base / "manifest.json") or {}
            clips = manifest.get("clips") if isinstance(manifest.get("clips"), dict) else {}
            selected = [
                (str(shot_id), str(record.get("path") or ""))
                for shot_id, record in clips.items()
                if isinstance(record, dict) and record.get("status") == "approved"
            ]
        elif stage == "dailies_review":
            ledger = read_json(base / "receipts" / "dailies.json") or {}
            selected = [
                (str(shot_id), str(item.get("candidate") or ""))
                for shot_id, items in (ledger.get("shots") or {}).items()
                for item in (items if isinstance(items, list) else [])
                if isinstance(item, dict)
            ]
        else:
            from dailies import dailies_status

            selected = [
                (str(item.get("shot_id") or ""), str(item.get("candidate") or ""))
                for item in dailies_status(base).get("selections") or []
            ]
        for index, (shot_id, value) in enumerate(selected):
            candidate = Path(value).expanduser()
            if not candidate.is_absolute():
                candidate = base / candidate
            try:
                relative = candidate.resolve().relative_to(base)
            except ValueError as exc:
                raise StageGateError(
                    f"stage media must stay inside production root: {value}"
                ) from exc
            if not candidate.is_file():
                raise StageGateError(f"stage media is missing: {relative}")
            refs[f"media:{shot_id}:{index}"] = str(relative)
    return refs


def validate_native_stage_evidence(root: Path | str, stage: str) -> dict[str, str]:
    """Fail closed unless the stage's canonical evidence is semantically current."""
    base = Path(root).expanduser().resolve()
    refs = native_stage_input_refs(base, stage)
    if stage == "concept_lock":
        from narrative_control import control_status

        brief = read_json(base / refs["brief"]) or {}
        status = control_status(base)
        if (
            not isinstance(brief, dict)
            or not str(brief.get("title") or "").strip()
            or status.get("canonical") is not True
            or (status.get("semantic") or {}).get("ok") is not True
        ):
            raise ValueError(
                "concept lock requires a titled brief and canonical semantic drama graph"
            )
    elif stage == "script_lock":
        from narrative_control import control_status

        status = control_status(base)
        if (
            {"story", "beats", "shots", "panels"} - set(status.get("locked_scopes") or [])
            or status.get("ready_for_media") is not True
            or (status.get("projection") or {}).get("stale") is True
        ):
            raise ValueError("script lock requires current locked narrative scopes and projection")
    elif stage == "department_look_lock":
        style = read_json(base / refs["visual"]) or {}
        if style.get("locked") is not True:
            raise ValueError("department/look lock requires a locked visual bible")
    elif stage == "shot_animatic_lock":
        from film_spec import iter_film_spec_shots

        spec = read_json(base / refs["shots"]) or {}
        timeline = read_json(base / refs["timeline"]) or {}
        planned = iter_film_spec_shots(spec)
        timeline_shots = timeline.get("shots") if isinstance(timeline.get("shots"), list) else []
        planned_ids = [str(shot.get("id") or shot.get("shot_id") or "") for shot in planned]
        timeline_ids = [
            str(shot.get("id") or shot.get("shot_id") or "")
            for shot in timeline_shots
            if isinstance(shot, dict)
        ]
        durations_ok = all(
            isinstance(shot, dict)
            and float(shot.get("duration_sec") or shot.get("duration") or 0) > 0
            for shot in [*planned, *timeline_shots]
        )
        if not planned_ids or planned_ids != timeline_ids or not durations_ok:
            raise ValueError(
                "shot/animatic lock requires ordered shot ids and positive durations "
                "in film-spec and timeline"
            )
    elif stage == "pilot_approval":
        from production_gates import load_pilot_approval, pilot_is_user_approved

        if not pilot_is_user_approved(load_pilot_approval(base)):
            raise ValueError("pilot stage requires current explicit user approval")
    elif stage == "bulk":
        from dailies import _sha
        from film_spec import iter_film_spec_shots

        spec = read_json(base / "film-spec.json") or {}
        manifest = read_json(base / "manifest.json") or {}
        clips = manifest.get("clips") if isinstance(manifest.get("clips"), dict) else {}
        planned = [
            str(shot.get("id") or shot.get("shot_id") or "") for shot in iter_film_spec_shots(spec)
        ]
        for shot_id in planned:
            clip = clips.get(shot_id) if isinstance(clips.get(shot_id), dict) else {}
            path = Path(str(clip.get("path") or ""))
            if not path.is_absolute():
                path = base / path
            digest = str(clip.get("sha256") or clip.get("media_sha256") or "")
            if clip.get("status") != "approved" or not path.is_file() or digest != _sha(path):
                raise ValueError(f"bulk stage has no current approved clip for {shot_id}")
        if not planned:
            raise ValueError("bulk stage requires planned shots")
    elif stage == "dailies_review":
        from dailies import dailies_review_status

        if dailies_review_status(base).get("ok") is not True:
            raise ValueError("dailies stage requires complete canonical dailies evidence")
    elif stage == "selects_rough_cut":
        from selects_report import build_selects_report

        current_selects = build_selects_report(base, write_receipt=False)
        selects = read_json(base / "receipts" / "selects-report.json") or {}
        rough = read_json(base / refs["rough"]) or {}
        if (
            current_selects.get("complete") is not True
            or current_selects.get("ok") is not True
            or selects.get("complete") is not True
            or rough.get("ok") is not True
        ):
            raise ValueError("selects stage requires current selects and rough-cut receipts")
        current_hash = current_selects.get("selected_set_sha256")
        if (
            not current_hash
            or selects.get("selected_set_sha256") != current_hash
            or rough.get("selected_set_sha256") != current_hash
        ):
            raise ValueError("rough cut is not bound to the ordered selected take set")
    elif stage == "picture_lock":
        from picture_lock import picture_lock_status

        if picture_lock_status(base).get("ok") is not True:
            raise ValueError("picture lock receipt is missing or stale")
    elif stage == "post_locks":
        if (read_json(base / "receipts" / "post-lock-staleness.json") or {}).get("affected_locks"):
            raise ValueError("post locks are stale after picture changes")
    elif stage == "master_lock":
        from master_delivery import validate_master_delivery

        delivery = read_json(base / refs["delivery"]) or {}
        if validate_master_delivery(base, delivery=delivery).get("ok") is not True:
            raise ValueError("master lock requires successful checksum, ffprobe and full read-back")
    return refs


def lock_native_stage(
    root: Path | str,
    *,
    stage: str,
    approver: str,
    user_phrase: str | None = None,
    authorization_event: str | None = None,
    input_refs: dict[str, str] | None = None,
    transaction_id: str | None = None,
    expected_ledger_revision: int | None = None,
) -> dict[str, Any]:
    """Create one human approval and hash-bound lock over native evidence."""
    from approval_ledger import append_approval
    from director_stage_gates import hash_input_refs, lock_stage, stage_status

    base = Path(root).expanduser().resolve()
    native_refs = validate_native_stage_evidence(base, stage)
    team_gate: dict[str, Any] | None = None
    team_plan = base / "production-team.json"
    if team_plan.is_file():
        from production_team import validate_team

        snapshot = base / "receipts" / "capability-snapshot.json"
        if not snapshot.is_file():
            raise ValueError("production-team exists but capability snapshot is missing")
        team_gate = validate_team(team_plan, capabilities_path=snapshot, stage=stage)
        if team_gate.get("ok") is not True:
            raise ValueError("production-team stage gate is not ready")
    refs = dict(native_refs)
    for name, relative in (input_refs or {}).items():
        if name in refs and refs[name] != relative:
            raise ValueError(f"custom input ref cannot replace native stage evidence: {name}")
        refs[name] = relative
    hashes = hash_input_refs(root, refs)
    tx = transaction_id or f"tx-stage-{stage}-{stable_content_hash(hashes)[:16]}"
    approval = append_approval(
        root,
        expected_revision=expected_ledger_revision,
        scope=f"stage:{stage}",
        approval_type="stage_lock",
        approver_type="user",
        approver=approver,
        user_phrase=user_phrase,
        authorization_event=authorization_event,
        input_hashes=hashes,
        evidence_refs=list(refs.values()),
        transaction_id=tx,
    )
    locked = lock_stage(
        root,
        stage=stage,
        input_refs=refs,
        approval_id=approval["approval_id"],
    )
    return {
        "ok": True,
        "action": "lock-stage",
        "stage": stage,
        "input_refs": refs,
        "approval_id": approval["approval_id"],
        "lock": locked,
        "stage_gates": stage_status(root),
        "production_team": team_gate,
    }


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
    book = read_json(base / "production-book.json") or {}
    records = book.get("departments") if isinstance(book, dict) else {}
    records = records if isinstance(records, dict) else {}
    items = []
    for department, filename in DEPARTMENT_FILES.items():
        if department == "sound":
            continue
        source_file = None
        for key in _BOOK_DEPARTMENT_KEYS[department]:
            record = records.get(key)
            candidate_source = record.get("source_file") if isinstance(record, dict) else None
            if isinstance(candidate_source, str) and candidate_source.strip():
                source_file = candidate_source
                break
        path = base / filename
        source = "default"
        if isinstance(source_file, str) and source_file.strip():
            candidate = Path(source_file).expanduser()
            candidate = candidate if candidate.is_absolute() else base / candidate
            candidate = candidate.resolve()
            if candidate.is_relative_to(base):
                path = candidate
                source = "production_book"
        value = read_json(path) if path.is_file() else None
        current_version = value.get("schema_version") if isinstance(value, dict) else None
        target_version = _DEPARTMENT_SCHEMA_TARGETS[department]
        items.append(
            {
                "department": department,
                "path": str(path),
                "path_source": source,
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
