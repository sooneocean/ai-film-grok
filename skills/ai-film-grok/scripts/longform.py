"""Hash-bound 8–15 minute vertical longform production planning."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from media_probe import run_media_to_output
from util import canonical_json_sha256, read_json, sha256_file, utc_now, write_json

LONGFORM_PLAN_RELATIVE = Path("receipts/longform-production-plan.json")
MIN_DURATION_SEC = 480.0
MAX_DURATION_SEC = 900.0
DEFAULT_UNIT_MAX_SEC = 90.0
APPROVAL_POLICY = "three_gates"


class LongformError(ValueError):
    """A longform contract cannot be planned or resumed safely."""


def _number(value: object, *, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise LongformError(f"{field} must be numeric") from exc
    if not math.isfinite(result) or result <= 0:
        raise LongformError(f"{field} must be positive and finite")
    return result


def longform_profile(spec: dict[str, Any]) -> dict[str, Any]:
    mode = str(spec.get("production_mode") or "shortform")
    if mode != "longform":
        raise LongformError("film-spec production_mode is not longform")
    raw = spec.get("longform_profile")
    if not isinstance(raw, dict):
        raise LongformError("longform_profile is required for production_mode=longform")
    target = _number(raw.get("target_duration_sec"), field="longform_profile.target_duration_sec")
    if not MIN_DURATION_SEC <= target <= MAX_DURATION_SEC:
        raise LongformError("longform target duration must be within 480..900 seconds")
    act_count = int(raw.get("act_count") or 0)
    if act_count != 3:
        raise LongformError("longform_profile.act_count must be 3 in v1")
    unit_max = _number(
        raw.get("unit_max_duration_sec") or DEFAULT_UNIT_MAX_SEC,
        field="longform_profile.unit_max_duration_sec",
    )
    if unit_max > DEFAULT_UNIT_MAX_SEC:
        raise LongformError("longform production units must be <=90 seconds")
    approval = str(raw.get("approval_policy") or APPROVAL_POLICY)
    if approval != APPROVAL_POLICY:
        raise LongformError("longform approval_policy must be three_gates")
    if str(spec.get("aspect_ratio") or "9:16") != "9:16":
        raise LongformError("longform v1 requires aspect_ratio=9:16")
    return {
        "target_duration_sec": target,
        "act_count": act_count,
        "unit_max_duration_sec": unit_max,
        "approval_policy": approval,
    }


def _source_hashes(root: Path) -> dict[str, str]:
    paths = {
        "graph": root / "drama-graph.json",
        "spec": root / "film-spec.json",
        "timeline": root / "timeline.json",
    }
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise LongformError(f"longform sources missing: {', '.join(missing)}")
    return {name: sha256_file(path) for name, path in paths.items()}


def _scene_rows(spec: dict[str, Any], timeline: dict[str, Any]) -> list[dict[str, Any]]:
    duration_by_id = {
        str(item.get("id")): _number(item.get("duration_sec"), field="timeline.duration_sec")
        for item in timeline.get("shots") or []
        if isinstance(item, dict) and item.get("id")
    }
    scenes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for scene_index, raw_scene in enumerate(spec.get("scenes") or [], start=1):
        if not isinstance(raw_scene, dict):
            continue
        scene_id = str(raw_scene.get("id") or f"scene{scene_index:02d}")
        shots: list[dict[str, Any]] = []
        for raw_shot in raw_scene.get("shots") or []:
            if not isinstance(raw_shot, dict) or not raw_shot.get("id"):
                continue
            shot_id = str(raw_shot["id"])
            if shot_id in seen:
                raise LongformError(f"duplicate longform shot id: {shot_id}")
            seen.add(shot_id)
            duration = duration_by_id.get(shot_id)
            if duration is None:
                raise LongformError(f"timeline is missing longform shot: {shot_id}")
            shots.append(
                {
                    "id": shot_id,
                    "beat_id": str(raw_shot.get("beat_id") or shot_id),
                    "duration_sec": duration,
                }
            )
        if shots:
            scenes.append(
                {
                    "id": scene_id,
                    "title": str(raw_scene.get("title") or scene_id),
                    "shots": shots,
                    "duration_sec": sum(item["duration_sec"] for item in shots),
                }
            )
    timeline_ids = set(duration_by_id)
    if seen != timeline_ids:
        missing = sorted(timeline_ids - seen)
        extra = sorted(seen - timeline_ids)
        raise LongformError(
            f"spec/timeline shot inventory mismatch; missing={missing[:5]} extra={extra[:5]}"
        )
    if len(scenes) < 3:
        raise LongformError("longform v1 requires at least three scenes")
    return scenes


def _assign_acts(scenes: list[dict[str, Any]]) -> None:
    total = sum(float(scene["duration_sec"]) for scene in scenes)
    elapsed = 0.0
    for scene in scenes:
        midpoint = elapsed + float(scene["duration_sec"]) / 2
        ratio = midpoint / total
        scene["act_id"] = "act1" if ratio <= 0.25 else ("act2" if ratio <= 0.75 else "act3")
        elapsed += float(scene["duration_sec"])
    present = {str(scene["act_id"]) for scene in scenes}
    if present != {"act1", "act2", "act3"}:
        one_third = max(1, len(scenes) // 3)
        two_thirds = max(one_third + 1, math.ceil(len(scenes) * 2 / 3))
        for index, scene in enumerate(scenes):
            scene["act_id"] = (
                "act1" if index < one_third else ("act2" if index < two_thirds else "act3")
            )


def _beat_groups(scene: dict[str, Any]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for shot in scene["shots"]:
        if not groups or groups[-1]["beat_id"] != shot["beat_id"]:
            groups.append(
                {
                    "act_id": scene["act_id"],
                    "scene_id": scene["id"],
                    "beat_id": shot["beat_id"],
                    "shots": [],
                }
            )
        groups[-1]["shots"].append(shot)
    return groups


def _build_units(scenes: list[dict[str, Any]], *, unit_max_sec: float) -> list[dict[str, Any]]:
    groups = [group for scene in scenes for group in _beat_groups(scene)]
    units: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    current_duration = 0.0
    current_act: str | None = None

    def flush() -> None:
        nonlocal current, current_duration, current_act
        if not current:
            return
        shots = [shot for group in current for shot in group["shots"]]
        scene_ids = list(dict.fromkeys(str(group["scene_id"]) for group in current))
        beat_ids = list(dict.fromkeys(str(group["beat_id"]) for group in current))
        units.append(
            {
                "act_id": str(current_act),
                "scene_ids": scene_ids,
                "beat_ids": beat_ids,
                "shot_ids": [str(shot["id"]) for shot in shots],
                "duration_sec": round(sum(float(shot["duration_sec"]) for shot in shots), 6),
            }
        )
        current = []
        current_duration = 0.0
        current_act = None

    for group in groups:
        group_duration = sum(float(shot["duration_sec"]) for shot in group["shots"])
        if group_duration > unit_max_sec:
            flush()
            for shot in group["shots"]:
                duration = float(shot["duration_sec"])
                if duration > unit_max_sec:
                    raise LongformError(f"shot exceeds longform unit ceiling: {shot['id']}")
                units.append(
                    {
                        "act_id": group["act_id"],
                        "scene_ids": [group["scene_id"]],
                        "beat_ids": [group["beat_id"]],
                        "shot_ids": [shot["id"]],
                        "duration_sec": round(duration, 6),
                    }
                )
            continue
        if current and (
            current_act != group["act_id"] or current_duration + group_duration > unit_max_sec
        ):
            flush()
        current_act = str(group["act_id"])
        current.append(group)
        current_duration += group_duration
    flush()

    for index, unit in enumerate(units, start=1):
        unit_id = f"lf-unit-{index:03d}"
        unit["id"] = unit_id
        unit["depends_on"] = [] if index == 1 else [f"lf-unit-{index - 1:03d}"]
        unit["approval_gate"] = "pilot_scene" if index == 1 else None
    return units


def build_longform_plan(root: Path | str, *, write: bool = False) -> dict[str, Any]:
    base = Path(root).expanduser().resolve()
    spec = read_json(base / "film-spec.json") or {}
    graph = read_json(base / "drama-graph.json") or {}
    timeline = read_json(base / "timeline.json") or {}
    profile = longform_profile(spec)
    if str((graph.get("project") or {}).get("production_mode") or "shortform") != "longform":
        raise LongformError("drama-graph is not bound to production_mode=longform")
    scenes = _scene_rows(spec, timeline)
    _assign_acts(scenes)
    units = _build_units(scenes, unit_max_sec=float(profile["unit_max_duration_sec"]))
    production_book = read_json(base / "production-book.json") or {}
    packs = production_book.get("packs") if isinstance(production_book.get("packs"), dict) else {}
    actual_duration = round(sum(float(unit["duration_sec"]) for unit in units), 6)
    if not MIN_DURATION_SEC <= actual_duration <= MAX_DURATION_SEC:
        raise LongformError("longform actual timeline duration must be within 480..900 seconds")
    if abs(actual_duration - float(profile["target_duration_sec"])) > max(
        5.0, float(profile["target_duration_sec"]) * 0.05
    ):
        raise LongformError("longform timeline duration differs from target by more than 5 percent")
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "longform-production-plan",
        "ok": True,
        "production_mode": "longform",
        "aspect_ratio": "9:16",
        "target_duration_sec": float(profile["target_duration_sec"]),
        "actual_duration_sec": actual_duration,
        "unit_max_duration_sec": float(profile["unit_max_duration_sec"]),
        "approval_policy": profile["approval_policy"],
        "approval_gates": ["story_animatic_lock", "pilot_scene", "final_full_watch"],
        "workflow_core": {
            "version": 1,
            "stages": ["story", "editorial", "visual", "performance", "sound", "post", "delivery"],
            "evidence_policy": "hash-bound-fail-closed",
        },
        "packs": {
            "format": str(packs.get("format") or "vertical-longform"),
            "genre": str(packs.get("genre") or spec.get("genre") or "drama"),
        },
        "source_hashes": _source_hashes(base),
        "units": units,
    }
    payload["content_sha256"] = canonical_json_sha256(payload)
    payload["generated_at"] = utc_now()
    if write:
        write_json(base / LONGFORM_PLAN_RELATIVE, payload)
    return payload


def _plan_staleness(root: Path, plan: dict[str, Any]) -> list[str]:
    try:
        current = _source_hashes(root)
    except LongformError:
        return ["graph", "spec", "timeline"]
    recorded = plan.get("source_hashes") if isinstance(plan.get("source_hashes"), dict) else {}
    return [name for name, digest in current.items() if recorded.get(name) != digest]


def _plan_content_is_valid(plan: dict[str, Any]) -> bool:
    recorded = str(plan.get("content_sha256") or "")
    semantic = {
        key: value for key, value in plan.items() if key not in {"content_sha256", "generated_at"}
    }
    return bool(recorded and canonical_json_sha256(semantic) == recorded)


def unit_stage_signature(
    plan: dict[str, Any], unit: dict[str, Any], *, stage: str = "unit_master"
) -> str:
    return canonical_json_sha256(
        {
            "plan_sha256": plan.get("content_sha256"),
            "unit": unit,
            "stage": stage,
        }
    )


def longform_status(root: Path | str) -> dict[str, Any]:
    base = Path(root).expanduser().resolve()
    plan_path = base / LONGFORM_PLAN_RELATIVE
    plan = read_json(plan_path)
    if not plan:
        try:
            preview = build_longform_plan(base, write=False)
        except LongformError as exc:
            return {"ok": False, "root": str(base), "error": str(exc), "plan_present": False}
        return {
            "ok": False,
            "root": str(base),
            "plan_present": False,
            "stale": False,
            "next_action": f'aifilm write-spec --root "{base}"',
            "preview": preview,
        }
    if not _plan_content_is_valid(plan):
        return {
            "ok": False,
            "root": str(base),
            "plan_present": True,
            "plan": str(plan_path),
            "stale": True,
            "stale_sources": ["plan"],
            "error": "longform production plan content hash is stale or tampered",
        }
    stale_sources = _plan_staleness(base, plan)
    units = list(plan.get("units") or [])
    from checkpoint import CheckpointManager

    checkpoint = CheckpointManager(base, preserve_corrupt=False)
    unit_receipt = read_json(base / "receipts" / "longform-unit-masters.json")
    receipt_source = (
        Path(str(unit_receipt.get("source_final") or "")).expanduser()
        if isinstance(unit_receipt, dict)
        else Path()
    )
    receipt_current = bool(
        isinstance(unit_receipt, dict)
        and unit_receipt.get("plan_sha256") == plan.get("content_sha256")
        and receipt_source.is_file()
        and unit_receipt.get("source_final_sha256") == sha256_file(receipt_source)
    )
    completed: list[str] = []
    for unit in units:
        unit_id = str(unit.get("id") or "")
        signature = unit_stage_signature(plan, unit)
        if receipt_current and checkpoint.get_stage(unit_id, "unit_master", signature) is not None:
            completed.append(unit_id)
    next_unit = next(
        (unit for unit in units if str(unit.get("id") or "") not in set(completed)),
        None,
    )
    return {
        "ok": not stale_sources and not checkpoint.corrupt_detected,
        "root": str(base),
        "plan_present": True,
        "plan": str(plan_path),
        "stale": bool(stale_sources),
        "stale_sources": stale_sources,
        "unit_counts": {
            "total": len(units),
            "completed": len(completed),
            "pending": len(units) - len(completed),
        },
        "completed_units": completed,
        "next_unit": next_unit,
        "approval_policy": plan.get("approval_policy"),
        "checkpoint_corrupt": checkpoint.corrupt_detected,
    }


def materialize_unit_masters(
    root: Path | str,
    *,
    final_path: Path | str,
    film_timeline: dict[str, Any],
    shots: list[dict[str, Any]],
) -> dict[str, Any]:
    """Split a verified final into hash-bound review units and checkpoint each unit."""
    base = Path(root).expanduser().resolve()
    source = Path(final_path).expanduser().resolve()
    plan = read_json(base / LONGFORM_PLAN_RELATIVE)
    if not isinstance(plan, dict):
        raise LongformError("longform production plan is missing")
    if not _plan_content_is_valid(plan):
        raise LongformError("longform production plan content hash is stale or tampered")
    stale_sources = _plan_staleness(base, plan)
    if stale_sources:
        raise LongformError(f"longform production plan is stale: {', '.join(stale_sources)}")
    if not source.is_file():
        raise LongformError(f"longform final master is missing: {source}")

    starts = list(film_timeline.get("shot_starts") or [])
    if len(starts) != len(shots):
        raise LongformError("final film timeline does not match rendered shot inventory")
    shot_index: dict[str, int] = {}
    for index, shot in enumerate(shots):
        shot_id = str(shot.get("id") or "")
        if not shot_id or shot_id in shot_index:
            raise LongformError("rendered longform shots require unique ids")
        shot_index[shot_id] = index

    from checkpoint import CheckpointManager

    checkpoint = CheckpointManager(base)
    units = list(plan.get("units") or [])
    source_sha256 = sha256_file(source)
    outputs: list[dict[str, Any]] = []
    previous_end = 0.0
    for unit_number, raw_unit in enumerate(units, start=1):
        if not isinstance(raw_unit, dict):
            raise LongformError("longform production plan contains an invalid unit")
        unit_id = str(raw_unit.get("id") or "")
        unit_shot_ids = [str(value) for value in raw_unit.get("shot_ids") or []]
        try:
            indices = [shot_index[shot_id] for shot_id in unit_shot_ids]
        except KeyError as exc:
            raise LongformError(f"unit references unknown rendered shot: {exc.args[0]}") from exc
        if not indices or indices != list(range(indices[0], indices[-1] + 1)):
            raise LongformError(f"unit shots must be contiguous in the final timeline: {unit_id}")

        start = float(starts[indices[0]])
        if unit_number < len(units):
            next_ids = [str(value) for value in (units[unit_number].get("shot_ids") or [])]
            if not next_ids or next_ids[0] not in shot_index:
                raise LongformError(f"next unit has no rendered boundary after {unit_id}")
            end = float(starts[shot_index[next_ids[0]]])
        else:
            last_index = indices[-1]
            end = float(starts[last_index]) + float(shots[last_index].get("target") or 0)
        start = max(start, previous_end)
        duration = end - start
        if duration <= 0:
            raise LongformError(f"unit has an invalid final timeline range: {unit_id}")
        previous_end = end

        output = base / "out" / "units" / f"{unit_id}.mp4"
        signature = unit_stage_signature(plan, raw_unit)
        for dependency_id in [str(value) for value in raw_unit.get("depends_on") or []]:
            dependency = next(
                (
                    item
                    for item in units
                    if isinstance(item, dict) and str(item.get("id") or "") == dependency_id
                ),
                None,
            )
            if (
                not isinstance(dependency, dict)
                or checkpoint.get_stage(
                    dependency_id,
                    "unit_master",
                    unit_stage_signature(plan, dependency),
                )
                is None
            ):
                raise LongformError(
                    f"unit dependency is not verified: {unit_id} requires {dependency_id}"
                )
        existing = checkpoint.get_stage(unit_id, "unit_master", signature)
        reused = bool(
            existing is not None
            and (existing.get("metadata") or {}).get("source_final_sha256") == source_sha256
        )
        if not reused:
            run_media_to_output(
                [
                    "ffmpeg",
                    "-y",
                    "-ss",
                    f"{start:.6f}",
                    "-i",
                    str(source),
                    "-t",
                    f"{duration:.6f}",
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a:0",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "fast",
                    "-crf",
                    "20",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    str(output),
                ],
                output,
                timeout=max(180, math.ceil(duration * 5)),
            )
            checkpoint.mark_stage_done(
                unit_id,
                "unit_master",
                signature=signature,
                output=output,
                depends_on=[str(value) for value in raw_unit.get("depends_on") or []],
                metadata={
                    "start_sec": round(start, 6),
                    "end_sec": round(end, 6),
                    "source_final": str(source),
                    "source_final_sha256": source_sha256,
                },
            )
        outputs.append(
            {
                "unit_id": unit_id,
                "output": str(output),
                "sha256": sha256_file(output),
                "start_sec": round(start, 6),
                "end_sec": round(end, 6),
                "duration_sec": round(duration, 6),
                "reused": reused,
            }
        )

    receipt: dict[str, Any] = {
        "schema_version": 1,
        "kind": "longform-unit-masters",
        "plan_sha256": plan.get("content_sha256"),
        "source_final": str(source),
        "source_final_sha256": source_sha256,
        "units": outputs,
        "generated_at": utc_now(),
    }
    receipt["content_sha256"] = canonical_json_sha256(receipt)
    receipt_path = base / "receipts" / "longform-unit-masters.json"
    write_json(receipt_path, receipt)
    return {
        "ok": True,
        "receipt": str(receipt_path),
        "unit_count": len(outputs),
        "units": outputs,
    }


def prepare_longform_resume(root: Path | str, *, unit_id: str) -> dict[str, Any]:
    status = longform_status(root)
    if not status.get("ok"):
        raise LongformError(
            "longform plan is missing or stale; rebuild it with write-spec before resume"
        )
    plan = read_json(Path(root).expanduser().resolve() / LONGFORM_PLAN_RELATIVE) or {}
    unit = next(
        (item for item in plan.get("units") or [] if str(item.get("id") or "") == unit_id),
        None,
    )
    if not isinstance(unit, dict):
        raise LongformError(f"unknown longform unit: {unit_id}")
    from checkpoint import CheckpointManager

    checkpoint = CheckpointManager(Path(root).expanduser().resolve(), preserve_corrupt=False)
    signature = unit_stage_signature(plan, unit)
    if checkpoint.get_stage(unit_id, "unit_master", signature) is not None:
        return {
            "ok": True,
            "root": str(Path(root).expanduser().resolve()),
            "unit": unit,
            "resume_from": None,
            "completed": True,
            "next_action": None,
            "note": "unit master is already verified",
        }
    incomplete_dependencies: list[str] = []
    for dependency_id in [str(value) for value in unit.get("depends_on") or []]:
        dependency = next(
            (
                item
                for item in plan.get("units") or []
                if isinstance(item, dict) and str(item.get("id") or "") == dependency_id
            ),
            None,
        )
        if (
            not isinstance(dependency, dict)
            or checkpoint.get_stage(
                dependency_id,
                "unit_master",
                unit_stage_signature(plan, dependency),
            )
            is None
        ):
            incomplete_dependencies.append(dependency_id)
    if incomplete_dependencies:
        raise LongformError(
            "longform unit dependencies are incomplete: " + ", ".join(incomplete_dependencies)
        )
    return {
        "ok": True,
        "root": str(Path(root).expanduser().resolve()),
        "unit": unit,
        "resume_from": "first_invalid_stage",
        "next_action": (f'aifilm final --root "{Path(root).expanduser().resolve()}" --resume'),
        "note": "final resumes hash-valid shot checkpoints, then rebuilds verified unit masters",
    }


def estimate_plate_timeout(
    root: Path | str,
    *,
    duration_sec: float | None = None,
    shot_count: int | None = None,
    lipsync: str = "off",
) -> int:
    """Dynamic plate wall-clock for ``aifilm final`` → render_final subprocess.

    Floors (Wave D · 2026-08-03):
    - short / default: **1200s**
    - longform clock (≥480s picture) or ``production_mode=longform``: **1800s**
    Cap 21600s. Override with ``--plate-timeout``. Stuck sidechain is handled
    inside render_final (amix PARTIAL), not by this estimate alone.
    """
    base = Path(root).expanduser().resolve()
    timeline = read_json(base / "timeline.json") or {}
    shots = [item for item in timeline.get("shots") or [] if isinstance(item, dict)]
    duration = float(
        duration_sec
        if duration_sec is not None
        else sum(float(item.get("duration_sec") or 0) for item in shots)
    )
    count = int(shot_count if shot_count is not None else len(shots))
    lipsync_factor = 18 if str(lipsync or "off") != "off" else 0
    estimate = math.ceil(600 + duration * 3 + count * (20 + lipsync_factor))
    floor = 1200
    if duration + 1e-9 >= MIN_DURATION_SEC:
        floor = 1800
    else:
        spec = read_json(base / "film-spec.json") or {}
        if str(spec.get("production_mode") or "").strip().lower() == "longform":
            floor = 1800
    return min(21600, max(floor, estimate))
