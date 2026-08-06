#!/usr/bin/env python3
"""Persistent single-concurrency queue and capability receipts for Grok media tools."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from cache import ContentCache
from media_qa import ALLOWED_VIDEO_ENDPOINTS, MediaQAError, analyze_media
from production_chain import (
    ProductionChainError,
    build_shot_contract,
    canonical_contract_required,
    require_current_queue_contract,
)
from production_gates import (
    ProductionGateError,
    assert_heat_allows_media,
    assert_pilot_allows_add,
)
from runtime_policy import sha256
from security_policy import (
    SecurityPolicyError,
    safe_output_path,
    safe_workspace_directory,
    validate_identifier,
)
from util import read_json, utc_now, write_json

OPERATIONS = frozenset({"image_gen", "image_edit", "image_to_video", "reference_to_video"})
COMPLETION_ENDPOINTS = frozenset({*ALLOWED_VIDEO_ENDPOINTS, "image_gen", "image_edit"})
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
TERMINAL_STATUSES = frozenset({STATUS_SUCCEEDED, STATUS_FAILED})
QUEUE_PARTIAL_REL = Path("receipts/media-queue-partial.json")


def note_queue_partial(
    root: Path | str,
    *,
    stage: str,
    error: str,
    shot_id: str = "",
    job_id: str = "",
    honest_limits: list[str] | None = None,
) -> Path:
    """AF2 · durable honesty when post-complete side effects fail (handoff/sidecar)."""
    base = Path(root).expanduser().resolve()
    path = base / QUEUE_PARTIAL_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    prior = read_json(path) if path.is_file() else None
    events: list[dict[str, Any]] = []
    if isinstance(prior, dict) and isinstance(prior.get("events"), list):
        events = list(prior["events"])  # type: ignore[arg-type]
    events.append(
        {
            "at": utc_now(),
            "stage": str(stage),
            "shot_id": str(shot_id or "") or None,
            "job_id": str(job_id or "") or None,
            "error": str(error)[:300],
        }
    )
    events = events[-40:]
    limits = list(
        honest_limits
        or [
            "take media may be ok — side effect (handoff/sidecar) failed",
            "do not claim continue-chain is complete without re-check",
        ]
    )
    write_json(
        path,
        {
            "kind": "media-queue-partial",
            "schema_version": 1,
            "at": utc_now(),
            "ok": True,
            "partial": True,
            "root": str(base),
            "honest_limits": limits,
            "events": events,
            "last_stage": str(stage),
            "last_error": str(error)[:300],
        },
    )
    return path


# Typed fail reasons — agents must use these instead of hand-editing queue JSON
FAIL_REASONS = frozenset({"moderation", "motion", "rate_limit", "decode", "other"})
# Default backoff seconds by reason when retryable (job-level next_attempt_at,
# not process sleep — media_queue requeues; see util.retry for process loops).
REASON_BACKOFF_SEC = {
    "moderation": 0,  # do not auto-spin; requeue after soft still
    "motion": 5,
    "rate_limit": 90,  # Kei 2026-07-16: 45s still hit 503; give Imagine more room
    "decode": 10,
    "other": 15,
}


def scheduled_backoff_sec(reason: str) -> float:
    """Single lookup for job-level retry delay (seconds until next_attempt_at)."""
    key = str(reason or "other").strip().lower() or "other"
    if key not in REASON_BACKOFF_SEC:
        key = "other"
    return float(REASON_BACKOFF_SEC[key])


class QueueError(RuntimeError):
    pass


def _inventory_weapon_tags() -> str:
    """Documented primary weapons for agent recovery (weapon-inventory SSoT)."""
    try:
        from weapon_inventory import primary_for

        still = (primary_for("text-to-image") or {}).get("id") or "qwen-image-2512-quality"
        edit = (primary_for("local-image-edit") or {}).get("id") or "qwen-image-edit-2511-local"
        motion = (primary_for("image-to-video") or {}).get("id") or "minimax-h3-i2v-pilot"
        tts = (primary_for("tts_zh_ship") or {}).get("id") or "edge_tts_zh"
        return f"weapons: still={still} edit={edit} motion={motion} tts={tts}"
    except Exception:
        return (
            "weapons: still=qwen-image-2512-quality "
            "edit=qwen-image-edit-2511-local motion=minimax-h3-i2v-pilot tts=edge_tts_zh"
        )


def _queue_error(msg: str) -> QueueError:
    """QueueError with inventory primary tags when not already present."""
    text = str(msg or "").strip()
    tags = _inventory_weapon_tags()
    if "weapons:" in text or "motion=" in text:
        return QueueError(text)
    return QueueError(f"{text} — {tags}")


def style_reference_output_evidence(
    root: Path | str,
    *,
    job_id: str,
    source: Path,
    shot_id: str,
    allowed_operations: frozenset[str],
) -> dict[str, Any]:
    """Verify a registered asset came from a completed job carrying the current style input."""
    queue = MediaQueue(root)
    state = queue.state()
    job = next((item for item in state.get("jobs") or [] if item.get("id") == job_id), None)
    if not isinstance(job, dict):
        raise QueueError(f"style-reference queue job not found: {job_id}")
    if job.get("status") != STATUS_SUCCEEDED:
        raise QueueError(f"style-reference queue job is not succeeded: {job_id}")
    if str(job.get("shot_id") or "") != str(shot_id):
        raise QueueError("style-reference queue job belongs to another shot")
    operation = str(job.get("operation") or "")
    if operation not in allowed_operations:
        raise QueueError(
            f"style-reference queue job operation {operation!r} is not one of {sorted(allowed_operations)}"
        )
    receipt = job.get("receipt") if isinstance(job.get("receipt"), dict) else {}
    source_sha = sha256(Path(source).expanduser().resolve())
    if receipt.get("output_sha256") != source_sha:
        raise QueueError("style-reference queue job output SHA-256 does not match registered asset")
    from util import read_json

    style = read_json(Path(root).expanduser().resolve() / "style-bible.json") or {}
    reference = (
        style.get("style_reference") if isinstance(style.get("style_reference"), dict) else {}
    )
    try:
        from style_lock import validate_style_lock_bible

        check = validate_style_lock_bible(style)
    except (ImportError, OSError, ValueError) as exc:
        raise QueueError(f"cannot validate current uploaded style reference: {exc}") from exc
    reference_errors = [
        str(code) for code in check.get("hard") or [] if str(code).startswith("STYLE_REFERENCE_")
    ]
    if reference_errors:
        raise QueueError(
            "current uploaded style reference failed integrity validation: "
            + ", ".join(reference_errors)
        )
    job_reference = (
        job.get("style_reference_input")
        if isinstance(job.get("style_reference_input"), dict)
        else {}
    )
    if not reference or job_reference.get("sha256") != reference.get("sha256"):
        raise QueueError(
            "style-reference queue job is not bound to the current uploaded style SHA-256"
        )
    return {
        "job_id": job_id,
        "operation": operation,
        "output_sha256": source_sha,
        "style_reference_sha256": job_reference["sha256"],
    }


def _usage_binding(
    root: Path,
    generation_id: str,
    job_id: str,
    *,
    expected_cache_key: str | None = None,
) -> dict[str, Any]:
    """Require a completed usage record before binding provider media to a job."""
    try:
        from generation_usage import usage_list

        records = usage_list(root, generation_id=generation_id).get("records") or []
    except (OSError, ValueError) as exc:
        raise QueueError(f"cannot read generation usage for {generation_id}: {exc}") from exc
    if len(records) != 1 or not isinstance(records[0], dict):
        raise QueueError(f"generation usage receipt missing for {generation_id}")
    record = records[0]
    recorded_job = record.get("job_id")
    if recorded_job not in {None, "", job_id}:
        raise QueueError(
            f"generation {generation_id} belongs to job {recorded_job!r}, not {job_id!r}"
        )
    if record.get("status") not in {"succeeded", "failed", "moderated"}:
        raise QueueError(f"generation {generation_id} is not terminal in usage receipt")
    recorded_cache_key = record.get("cache_key")
    if expected_cache_key and recorded_cache_key != expected_cache_key:
        raise QueueError(f"generation {generation_id} contract does not match queue cache key")
    usage = record.get("usage") if isinstance(record.get("usage"), dict) else {}
    return {
        "generation_id": generation_id,
        "status": record.get("status"),
        "measurement": record.get("measurement", "unknown"),
        "provider_request_id": record.get("provider_request_id"),
        "input_hash": record.get("input_hash"),
        "cache_key": recorded_cache_key,
        "contract_version": record.get("contract_version"),
        "usage": usage,
        "cost_in_usd_ticks": usage.get("cost_in_usd_ticks"),
    }


def normalize_fail_reason(value: object) -> str:
    """Map free-text or enum to a FAIL_REASONS member."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return "other"
    text = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if text in FAIL_REASONS:
        return text
    # Aliases from provider / QA messages
    if "moderat" in text or "content_moderat" in text or "nsfw" in text:
        return "moderation"
    if "motion" in text or "static" in text:
        return "motion"
    if "rate" in text or "429" in text or "resource_exhausted" in text or "too_many" in text:
        return "rate_limit"
    if "decode" in text or "ffprobe" in text or "corrupt" in text:
        return "decode"
    return "other"


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class MediaQueue:
    def __init__(self, root: Path | str, *, budget_units: int = 20):
        if budget_units < 1 or budget_units > 10_000:
            raise QueueError("budget_units must be between 1 and 10000")
        self.budget_units = budget_units
        self.root = Path(root).expanduser().resolve()
        try:
            self.receipts = safe_workspace_directory(
                self.root, "receipts", field="film receipts directory"
            )
        except SecurityPolicyError as exc:
            raise QueueError(str(exc)) from exc
        self.receipts.mkdir(parents=True, exist_ok=True)
        try:
            self.path = safe_output_path(
                self.receipts, "media-queue.json", suffixes={".json"}, field="media queue"
            )
            self.lock_path = safe_output_path(
                self.receipts, ".media-queue.lock", suffixes={".lock"}, field="media queue lock"
            )
        except SecurityPolicyError as exc:
            raise QueueError(str(exc)) from exc

    @contextmanager
    def _locked(self) -> Iterator[None]:
        with self.lock_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _read(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {
                "schema_version": 1,
                "updated_at": utc_now(),
                "policy": {"max_concurrency": 1, "budget_units": self.budget_units},
                "jobs": [],
            }
        from util import require_json
        from util.errors import FilmError

        try:
            value = require_json(self.path)
        except FilmError as exc:
            raise QueueError(f"media queue is corrupt: {exc}") from exc
        if not isinstance(value.get("jobs"), list):
            raise QueueError("media queue has invalid shape")
        return value

    def _write(self, state: dict[str, Any]) -> None:
        from util import write_json

        state["updated_at"] = utc_now()
        write_json(self.path, state)

    def state(self) -> dict[str, Any]:
        with self._locked():
            return self._read()

    def set_budget(self, units: int) -> dict[str, Any]:
        if units < 1 or units > 10_000:
            raise QueueError("budget units must be between 1 and 10000")
        with self._locked():
            state = self._read()
            state.setdefault("policy", {})["budget_units"] = units
            self._write(state)
            return state

    def metrics(self, state: dict[str, Any] | None = None) -> dict[str, Any]:
        state = self.state() if state is None else state
        counts: dict[str, int] = {}
        attempts = 0
        durations: list[float] = []
        for job in state["jobs"]:
            status = str(job.get("status") or "unknown")
            counts[status] = counts.get(status, 0) + 1
            attempts += int(job.get("attempts") or 0)
            if job.get("claimed_at") and job.get("completed_at"):
                durations.append(
                    max(
                        0.0,
                        (
                            _parse_time(job["completed_at"]) - _parse_time(job["claimed_at"])
                        ).total_seconds(),
                    )
                )
        terminal = sum(counts.get(status, 0) for status in TERMINAL_STATUSES)
        result = {
            "counts": counts,
            "jobs": len(state["jobs"]),
            "attempts": attempts,
            "success_rate": round(counts.get(STATUS_SUCCEEDED, 0) / terminal, 4)
            if terminal
            else None,
            "mean_run_seconds": round(sum(durations) / len(durations), 3) if durations else None,
            "budget_units": int(
                (state.get("policy") or {}).get("budget_units") or self.budget_units
            ),
            "budget_remaining": max(
                0,
                int((state.get("policy") or {}).get("budget_units") or self.budget_units)
                - len(state["jobs"]),
            ),
        }
        try:
            from generation_usage import usage_status

            usage = usage_status(self.root)
            result["actual_generation_requests"] = usage.get("requests_total", 0)
            result["actual_generation_status_counts"] = usage.get("status_counts", {})
            result["actual_generation_unknown_cost_requests"] = usage.get(
                "unknown_cost_requests", 0
            )
        except (OSError, ValueError):
            result["actual_generation_requests"] = 0
            result["actual_generation_status_counts"] = {}
            result["actual_generation_unknown_cost_requests"] = 0
        return result

    def add_job(
        self,
        *,
        shot_id: str,
        operation: str,
        prompt_file: Path,
        inputs: list[Path],
        max_attempts: int = 3,
        allow_without_pilot: bool = False,
        assembly_receipt: Path | None = None,
        is_canary: bool = False,
        canary_group_id: str | None = None,
        seed_offset: int = 0,
        generation_contract: dict[str, Any] | None = None,
        require_preflight: bool = False,
    ) -> dict[str, Any]:
        try:
            shot_id = validate_identifier(shot_id, field="shot id")
        except SecurityPolicyError as exc:
            raise QueueError(str(exc)) from exc
        if operation not in OPERATIONS:
            raise QueueError(f"unknown media operation {operation!r}")
        prompt = prompt_file.expanduser().resolve()
        if not prompt.is_file():
            raise QueueError(f"prompt file is missing: {prompt}")
        resolved_inputs = [path.expanduser().resolve() for path in inputs]
        if any(not path.is_file() for path in resolved_inputs):
            raise QueueError("every media input must be an existing file")
        # Material fidelity: if a GenerationRequest receipt exists, pixel sha must match
        if operation in {"image_to_video", "reference_to_video"} and resolved_inputs:
            try:
                from generation_request import GenerationRequestError, assert_pixel_pack_current

                assert_pixel_pack_current(self.root, shot_id, inputs=resolved_inputs)
            except GenerationRequestError as exc:
                raise QueueError(str(exc)) from exc
            except Exception as exc:  # noqa: BLE001 — optional fidelity; never silent
                note_queue_partial(
                    self.root,
                    stage="generation_request_optional",
                    error=str(exc),
                    shot_id=str(shot_id),
                    honest_limits=[
                        "generation_request check skipped (module/legacy)",
                        "material fidelity not guaranteed for this enqueue",
                    ],
                )
        if operation in {"image_to_video", "reference_to_video"}:
            from anatomy_safety import requires_anatomy_safety

            if requires_anatomy_safety(self.root):
                manifest = read_json(self.root / "manifest.json") or {}
                stills = manifest.get("stills") if isinstance(manifest, dict) else {}
                still = stills.get(shot_id) if isinstance(stills, dict) else None
                if not isinstance(still, dict) or still.get("status") != "approved":
                    raise QueueError(
                        "adult-max I2V requires an approved keyframe for this shot; "
                        "do not animate an unreviewed still"
                    )
                if still.get("anatomy_safe") is not True:
                    raise QueueError(
                        "adult-max I2V blocked: keyframe lacks anatomy_safe=true or was marked "
                        "poisoned; repair the still and register it with --anatomy-safe first"
                    )
                approved_sha = str(still.get("sha256") or "").strip()
                if not approved_sha:
                    raise QueueError(
                        "adult-max I2V blocked: approved keyframe has no SHA-256 binding"
                    )
                input_hashes = [sha256(path) for path in resolved_inputs]
                if not input_hashes or input_hashes[0] != approved_sha:
                    raise QueueError(
                        "adult-max I2V blocked: first input does not match the approved anatomy-safe "
                        "keyframe bytes for this shot"
                    )
                style = read_json(self.root / "style-bible.json") or {}
                reference = style.get("style_reference") if isinstance(style, dict) else None
                reference_sha = (
                    str(reference.get("sha256") or "").strip()
                    if isinstance(reference, dict)
                    else ""
                )
                allowed_hashes = {approved_sha, *([reference_sha] if reference_sha else [])}
                if any(input_sha not in allowed_hashes for input_sha in input_hashes):
                    raise QueueError(
                        "adult-max I2V blocked: every input must be the approved anatomy-safe "
                        "keyframe or the locked style reference"
                    )
                if operation == "image_to_video" and len(input_hashes) != 1:
                    raise QueueError(
                        "adult-max image_to_video accepts exactly the one approved anatomy-safe "
                        "keyframe; use reference_to_video for an explicit secondary style reference"
                    )
        # Reference-first productions must carry the uploaded style image as an
        # actual provider input, not merely a sentence in a prompt receipt.
        # Frame-1-only I2V cannot consume that second image, so it is forbidden
        # here; use reference_to_video to keep the visual language attached.
        style_path = self._require_style_reference_input(
            operation=operation,
            inputs=resolved_inputs,
            assembly_receipt=assembly_receipt,
        )
        if max_attempts < 1 or max_attempts > 10:
            raise QueueError("max_attempts must be between 1 and 10")
        # Shot must exist in film-spec when present (no ghost queue after write-spec)
        spec_path = self.root / "film-spec.json"
        if spec_path.is_file():
            try:
                from narrative_control import NarrativeControlError, assert_projection_ready

                assert_projection_ready(self.root, require_locked=True)
            except NarrativeControlError as exc:
                raise QueueError(f"{exc.code}: {exc}") from exc
            try:
                from util import require_json
                from util.errors import FilmError

                raw_spec = require_json(spec_path)
            except FilmError as exc:
                raise QueueError(f"cannot read film-spec.json: {exc}") from exc
            known_ids: set[str] = set()
            if isinstance(raw_spec, dict):
                try:
                    from dialogue_broll import iter_dialogue_broll
                    from film_spec import validate_film_spec

                    validated = validate_film_spec(raw_spec, assign_missing_ids=False)
                    for s in validated:
                        known_ids.add(str(s["id"]))
                    known_ids.update(str(s.get("id")) for s in iter_dialogue_broll(raw_spec))
                except Exception:
                    for scene in raw_spec.get("scenes") or []:
                        if not isinstance(scene, dict):
                            continue
                        for sh in scene.get("shots") or []:
                            if isinstance(sh, dict) and sh.get("id"):
                                known_ids.add(str(sh["id"]))
            if known_ids and shot_id not in known_ids:
                raise QueueError(
                    f"shot_id {shot_id!r} is not in film-spec "
                    f"(known={sorted(known_ids)}). write-spec first; do not queue ghost shots."
                )
            # Hybrid dual-lane: restricted/meat soft-lock must not enter Grok cloud bulk.
            if operation in {"image_to_video", "reference_to_video"} and isinstance(raw_spec, dict):
                try:
                    from production_router import build_shot_intent

                    shot_row: dict[str, Any] | None = None
                    for scene in raw_spec.get("scenes") or []:
                        if not isinstance(scene, dict):
                            continue
                        for sh in scene.get("shots") or []:
                            if isinstance(sh, dict) and str(sh.get("id") or "") == shot_id:
                                shot_row = sh
                                break
                        if shot_row is not None:
                            break
                    if shot_row is None:
                        for sh in raw_spec.get("shots") or []:
                            if isinstance(sh, dict) and str(sh.get("id") or "") == shot_id:
                                shot_row = sh
                                break
                    if shot_row is not None:
                        intent = build_shot_intent(raw_spec, shot_row)
                        locked = str(intent.get("provider_lock") or "").strip().lower()
                        rec = str(intent.get("recommended_provider") or "").strip().lower()
                        h3_on = bool(intent.get("h3_enabled"))
                        film_profile = str(raw_spec.get("_i2v_profile") or "").strip().lower()
                        is_h3_primary = film_profile == "h3_primary"
                        # hybrid: block restricted meat; h3_primary: all H3-locked shots
                        wants_h3 = locked == "comfy-h3" or (
                            h3_on
                            and rec == "comfy-h3"
                            and (intent.get("content_class") == "restricted_local" or is_h3_primary)
                        )
                        contract_provider = (
                            str((generation_contract or {}).get("provider") or "").strip().lower()
                        )
                        allow_cloud = os.environ.get(
                            "AIFILM_ALLOW_CLOUD_RESTRICTED", ""
                        ).strip().lower() in {"1", "true", "yes", "on"}
                        if wants_h3 and contract_provider not in {
                            "comfy-h3",
                            "comfy_h3",
                            "local_h3",
                            "minimax-h3",
                        }:
                            if not allow_cloud:
                                lane_why = (
                                    "h3_primary film-wide local primary"
                                    if is_h3_primary
                                    else "restricted_local"
                                )
                                motion_p = "minimax-h3-i2v-pilot"
                                try:
                                    from weapon_inventory import primary_for

                                    motion_p = (
                                        (primary_for("image-to-video") or {}).get("id")
                                        or motion_p
                                    )
                                except Exception:
                                    pass
                                raise _queue_error(
                                    f"shot {shot_id!r} is {lane_why} → local motion primary "
                                    f"{motion_p} (provider_lock={locked or rec}). "
                                    f'Use: aifilm h3 plan --root "{self.root}" --shot-id {shot_id} '
                                    f'&& aifilm h3 run --root "{self.root}" --shot-id {shot_id} '
                                    f"--register (inventory motion={motion_p}). "
                                    f"Escape: AIFILM_ALLOW_CLOUD_RESTRICTED=1 "
                                    f"(not recommended for bare/meat / h3_primary)."
                                )
                        # Motion Prompt Spine: enrich + fail-closed empty core (P0/A).
                        from motion_prompt_spine import (
                            MotionCoreError,
                            assert_motion_prompt_core,
                            ensure_motion_core_in_prompt,
                            motion_core_skip_enabled,
                        )

                        if not motion_core_skip_enabled():
                            try:
                                raw_prompt = prompt.read_text(encoding="utf-8")
                                enriched = ensure_motion_core_in_prompt(
                                    raw_prompt, raw_spec, shot_row
                                )
                                if enriched.strip() != raw_prompt.strip():
                                    prompt.write_text(enriched.rstrip() + "\n", encoding="utf-8")
                                assert_motion_prompt_core(
                                    enriched,
                                    shot_row,
                                    mode=operation,
                                    role=str(shot_row.get("shot_role") or "hero"),
                                )
                            except MotionCoreError as exc:
                                raise _queue_error(str(exc)) from exc
                            except QueueError:
                                raise
                            except Exception as exc:
                                raise _queue_error(
                                    f"motion core enrich failed for {shot_id}: {exc}"
                                ) from exc
                except QueueError:
                    raise
                except Exception as exc:
                    # Restricted / H3 routing must not silent-pass into cloud bulk
                    raise _queue_error(
                        f"restricted/local motion routing failed for {shot_id}: {exc}"
                    ) from exc
        try:
            source_contract = build_shot_contract(self.root, shot_id)
            if not source_contract["ok"]:
                raise ProductionChainError(
                    ", ".join(str(code) for code in source_contract.get("errors") or [])
                )
        except ProductionChainError as exc:
            raise _queue_error(f"queue source contract is not ready: {exc}") from exc
        prompt_hash = sha256(prompt)
        input_records = [{"path": str(path), "sha256": sha256(path)} for path in resolved_inputs]
        legacy_identity = {
            "shot_id": shot_id,
            "operation": operation,
            "prompt": prompt_hash,
            "inputs": input_records,
            "is_canary": is_canary,
            "seed_offset": seed_offset,
        }
        cache_key = None
        if generation_contract:
            input_hash = ContentCache.key(
                json.dumps(input_records, sort_keys=True, separators=(",", ":"))
            )
            extra_parameters = generation_contract.get("parameters")
            cache_key = ContentCache.contract_key(
                input_hash=input_hash,
                provider=str(generation_contract.get("provider") or "unspecified"),
                model=str(generation_contract.get("model") or "unspecified"),
                parameters={
                    "shot_id": shot_id,
                    "operation": operation,
                    "prompt_sha256": prompt_hash,
                    "is_canary": is_canary,
                    "seed_offset": seed_offset,
                    **(extra_parameters if isinstance(extra_parameters, dict) else {}),
                },
                version=str(generation_contract.get("version") or "1"),
            )
        identity = (
            cache_key or ContentCache.key(json.dumps(legacy_identity, sort_keys=True))
        ).encode("utf-8")
        canary_suffix = f"-canary{seed_offset}" if is_canary else ""
        job_id = f"{shot_id}-{hashlib.sha256(identity).hexdigest()[:16]}{canary_suffix}"
        with self._locked():
            state = self._read()
            existing = next((job for job in state["jobs"] if job.get("id") == job_id), None)
            if existing:
                return existing
            existing_shot_ids = {
                str(job.get("shot_id")) for job in state["jobs"] if job.get("shot_id")
            }
            try:
                assert_pilot_allows_add(
                    self.root,
                    shot_id=shot_id,
                    existing_shot_ids=existing_shot_ids,
                    force=allow_without_pilot,
                )
            except ProductionGateError as exc:
                raise _queue_error(str(exc)) from exc
            # Wave 5: adult-max heat hard_fail blocks all queue adds (not pilot-skippable)
            try:
                assert_heat_allows_media(self.root)
            except ProductionGateError as exc:
                raise _queue_error(str(exc)) from exc
            # Wave G: pilot-approved bulk defaults to bulk-preflight hard gate
            # (pilot window ≤3 shots without approval stays open; canary/skip env opt-out).
            skip_pf = os.environ.get("AIFILM_SKIP_BULK_PREFLIGHT", "").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
            force_pf = require_preflight or os.environ.get(
                "AIFILM_REQUIRE_BULK_PREFLIGHT", ""
            ).strip().lower() in {"1", "true", "yes", "on"}
            pilot_bulk = False
            try:
                from production_gates import load_pilot_approval, pilot_is_user_approved

                pilot_bulk = pilot_is_user_approved(load_pilot_approval(self.root))
            except Exception:
                pilot_bulk = False
            want_pf = (force_pf or (pilot_bulk and not is_canary and not skip_pf)) and (
                not allow_without_pilot
            )
            if want_pf:
                try:
                    from workflow_pack import WorkflowPackError, assert_bulk_preflight

                    # queue path: no tunnel/lease — those are bulk-time capacity, not job-enqueue
                    assert_bulk_preflight(
                        self.root,
                        require=True,
                        probe_tunnel=False,
                        check_lease=False,
                    )
                except WorkflowPackError as exc:
                    raise _queue_error(str(exc)) from exc
                except Exception as exc:  # noqa: BLE001
                    raise _queue_error(f"bulk preflight unavailable: {exc}") from exc
            effective_budget = int(
                (state.get("policy") or {}).get("budget_units") or self.budget_units
            )
            if len(state["jobs"]) >= effective_budget:
                raise _queue_error(
                    f"generation-unit budget exhausted ({len(state['jobs'])}/{effective_budget}); "
                    "use the budget command to raise it explicitly before adding work"
                )
            job = {
                "id": job_id,
                "shot_id": shot_id,
                "operation": operation,
                "prompt_file": str(prompt),
                "prompt_sha256": prompt_hash,
                "inputs": input_records,
                "status": STATUS_PENDING,
                "attempts": 0,
                "max_attempts": max_attempts,
                "next_attempt_at": utc_now(),
                "created_at": utc_now(),
                "is_canary": is_canary,
                "seed_offset": seed_offset,
                "source_contract": source_contract,
            }
            if cache_key:
                job["cache_key"] = cache_key
                job["generation_contract"] = generation_contract
            if canary_group_id:
                job["canary_group_id"] = canary_group_id
            if assembly_receipt:
                job["assembly_receipt"] = str(assembly_receipt.expanduser().resolve())
            if style_path:
                job["style_reference_input"] = {
                    "path": str(style_path),
                    "sha256": sha256(style_path),
                }
            state["jobs"].append(job)
            self._write(state)
            return job

    def _require_style_reference_input(
        self,
        *,
        operation: str,
        inputs: list[Path],
        assembly_receipt: Path | None,
    ) -> Path | None:
        """Fail closed when a reference-first film omits its uploaded style anchor."""
        from util import read_json

        style = read_json(self.root / "style-bible.json") or {}
        reference = (
            style.get("style_reference") if isinstance(style.get("style_reference"), dict) else {}
        )
        if not reference:
            return None
        try:
            from style_lock import validate_style_lock_bible

            check = validate_style_lock_bible(style)
        except (ImportError, OSError, ValueError) as exc:
            raise QueueError(f"cannot validate uploaded style reference: {exc}") from exc
        hard = [
            str(code)
            for code in check.get("hard") or []
            if str(code).startswith("STYLE_REFERENCE_")
        ]
        if hard:
            raise QueueError("uploaded style reference is invalid: " + ", ".join(hard))
        staged = Path(str(reference.get("staged_path") or "")).expanduser().resolve()
        if operation == "image_to_video":
            raise QueueError(
                "reference-first film forbids image_to_video: use reference_to_video with the uploaded "
                "style image so I2V cannot drift from frame-1 alone"
            )
        if staged not in inputs:
            raise QueueError(
                "reference-first media job must include the uploaded style reference as --input: "
                + str(staged)
            )
        if assembly_receipt is None or not assembly_receipt.is_file():
            raise QueueError("reference-first media job requires a prompt_assembly receipt")
        receipt = read_json(assembly_receipt) or {}
        recorded = (
            receipt.get("style_reference")
            if isinstance(receipt.get("style_reference"), dict)
            else {}
        )
        if recorded.get("sha256") != reference.get("sha256"):
            raise QueueError(
                "prompt assembly receipt is not bound to the current uploaded style reference"
            )
        return staged

    def add_canary_pair(
        self,
        *,
        shot_id: str,
        operation: str,
        prompt_file: Path,
        inputs: list[Path],
        max_attempts: int = 3,
        allow_without_pilot: bool = False,
        seed_offset: int = 101,
        generation_contract: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Enqueue primary job and canary speculative mutation job in parallel."""
        group_id = f"canary_grp_{shot_id}_{secrets.token_hex(4)}"
        primary = self.add_job(
            shot_id=shot_id,
            operation=operation,
            prompt_file=prompt_file,
            inputs=inputs,
            max_attempts=max_attempts,
            allow_without_pilot=allow_without_pilot,
            is_canary=False,
            canary_group_id=group_id,
            generation_contract=generation_contract,
        )
        canary = self.add_job(
            shot_id=shot_id,
            operation=operation,
            prompt_file=prompt_file,
            inputs=inputs,
            max_attempts=max_attempts,
            allow_without_pilot=allow_without_pilot,
            is_canary=True,
            canary_group_id=group_id,
            seed_offset=seed_offset,
            generation_contract=generation_contract,
        )
        return primary, canary

    def claim(self, *, now: str | None = None) -> dict[str, Any]:
        current = _parse_time(now or utc_now())
        with self._locked():
            state = self._read()
            if any(job.get("status") == STATUS_RUNNING for job in state["jobs"]):
                raise QueueError("single-concurrency policy: another media job is already running")
            eligible = [
                job
                for job in state["jobs"]
                if job.get("status") == STATUS_PENDING
                and _parse_time(job.get("next_attempt_at") or utc_now()) <= current
            ]
            if not eligible:
                raise QueueError("no media job is eligible to run")
            job = eligible[0]
            job["status"] = STATUS_RUNNING
            job["attempts"] = int(job.get("attempts") or 0) + 1
            job["claimed_at"] = current.replace(microsecond=0).isoformat()
            job["claim_token"] = secrets.token_hex(16)
            self._write(state)
        try:
            from pipeline_events import append_event

            append_event(
                self.root,
                stage="i2v",
                phase="claimed",
                shot_id=str(job.get("shot_id") or ""),
                retry_of=str(job.get("id") or "") if int(job.get("attempts") or 0) > 1 else None,
            )
        except OSError:
            pass
        return job

    def _running_job(self, state: dict[str, Any], job_id: str, claim_token: str) -> dict[str, Any]:
        job = next((item for item in state["jobs"] if item.get("id") == job_id), None)
        if not job or job.get("status") != STATUS_RUNNING or job.get("claim_token") != claim_token:
            raise QueueError("job is not running under this claim token")
        return job

    def fail(
        self,
        job_id: str,
        *,
        claim_token: str,
        error: str,
        retryable: bool,
        reason: str | None = None,
        now: str | None = None,
    ) -> dict[str, Any]:
        current = _parse_time(now or utc_now())
        reason_norm = normalize_fail_reason(reason if reason is not None else error)
        with self._locked():
            state = self._read()
            job = self._running_job(state, job_id, claim_token)
            attempts = int(job["attempts"])
            job["fail_reason"] = reason_norm
            job["last_error"] = str(error)[:1000]
            # moderation: do not auto-retry spinning the same still; mark failed unless
            # caller forces retryable and still has attempts (soft still then requeue)
            auto_retry = retryable and attempts < int(job["max_attempts"])
            if reason_norm == "moderation" and retryable:
                # stay failed until agent requeues after soft still / new inputs
                auto_retry = False
            if auto_retry:
                base = scheduled_backoff_sec(reason_norm)
                if reason_norm == "rate_limit":
                    delay = max(base, min(60 * (2 ** (attempts - 1)), 1800))
                else:
                    delay = min(max(base, 5 * (2 ** (attempts - 1))), 1800)
                job["status"] = STATUS_PENDING
                job["next_attempt_at"] = (
                    (current + timedelta(seconds=delay)).replace(microsecond=0).isoformat()
                )
            else:
                job["status"] = STATUS_FAILED
            job.setdefault("retry_history", []).append(
                {
                    "attempt": attempts,
                    "reason": reason_norm,
                    "retryable": bool(retryable),
                    "status_after": job["status"],
                    "next_attempt_at": job.get("next_attempt_at"),
                    "error": str(error)[:1000],
                    "recorded_at": utc_now(),
                }
            )
            job.pop("claim_token", None)
            self._write(state)
        try:
            from pipeline_events import append_event

            append_event(
                self.root,
                stage="i2v",
                phase="failed",
                shot_id=str(job.get("shot_id") or ""),
                error_code=reason_norm,
            )
        except OSError:
            pass
        # B · 2026-08-06: moderation/poison streaks → scale-fallback stop-hard-on honesty
        err_l = str(error).lower()
        if reason_norm == "moderation" or any(
            k in err_l for k in ("poison", "anatomy", "futa", "畸形", "崩坏")
        ):
            try:
                self._maybe_write_scale_fallback_on_fail(
                    reason_norm=reason_norm,
                    error=str(error),
                    shot_id=str(job.get("shot_id") or ""),
                )
            except Exception:  # noqa: BLE001
                pass
        return job

    def _maybe_write_scale_fallback_on_fail(
        self,
        *,
        reason_norm: str,
        error: str,
        shot_id: str,
    ) -> None:
        """Count recent moderation/poison fails; emit SCALE_HARD_ON_BAN when streak high."""
        state = self._read()
        poison_n = 0
        mod_n = 0
        for j in state.get("jobs") or []:
            if not isinstance(j, dict):
                continue
            fr = str(j.get("fail_reason") or "")
            err = str(j.get("last_error") or "").lower()
            if fr == "moderation":
                mod_n += 1
            if "poison" in err or "anatomy" in err or "futa" in err or "畸形" in err or "崩坏" in err:
                poison_n += 1
        if mod_n < 2 and poison_n < 2 and reason_norm != "moderation":
            return
        from narrative.scale_fallback import (
            decide_scale_fallback,
            write_scale_fallback_receipt,
        )

        decision = decide_scale_fallback(
            target_tier="bare",
            consecutive_poison=max(poison_n, 2 if "poison" in error.lower() else 0),
            consecutive_moderation=max(mod_n, 1 if reason_norm == "moderation" else 0),
            consecutive_anatomy_fail=poison_n,
        )
        if not decision.get("codes"):
            return
        write_scale_fallback_receipt(
            self.root,
            {
                "kind": "scale-fallback",
                "schema_version": 1,
                "source": "media_queue.fail",
                "shot_id": shot_id or None,
                "fail_reason": reason_norm,
                "error": str(error)[:300],
                "moderation_fail_jobs": mod_n,
                "poison_like_jobs": poison_n,
                "decision": decision,
                "codes": decision.get("codes"),
                "partial": True,
                "honest_limits": decision.get("honest_limits"),
                "promote_ban": decision.get("promote_ban"),
                "note": decision.get("note"),
            },
        )

    def requeue(
        self,
        job_id: str,
        *,
        reason: str | None = None,
        reset_attempts: bool = False,
        now: str | None = None,
    ) -> dict[str, Any]:
        """Return a failed/pending/running-stale job to pending without hand-editing JSON.

        Clears claim_token. Optionally records fail_reason for agent playbooks.
        Does not require claim_token (explicit operator action after soft still / rate wait).
        """
        current = _parse_time(now or utc_now())
        with self._locked():
            state = self._read()
            job = next((item for item in state["jobs"] if item.get("id") == job_id), None)
            if not job:
                raise QueueError(f"unknown job id: {job_id}")
            status = str(job.get("status") or "")
            if status == STATUS_SUCCEEDED:
                raise QueueError("cannot requeue a succeeded job")
            if status == STATUS_RUNNING:
                raise QueueError(
                    "job is running under a claim; fail it first or wait for reconcile"
                )
            if reason is not None:
                job["fail_reason"] = normalize_fail_reason(reason)
            job["status"] = STATUS_PENDING
            job["next_attempt_at"] = current.replace(microsecond=0).isoformat()
            job.pop("claim_token", None)
            if reset_attempts:
                job["attempts"] = 0
            job["requeued_at"] = current.replace(microsecond=0).isoformat()
            job.setdefault("retry_history", []).append(
                {
                    "attempt": int(job.get("attempts") or 0),
                    "reason": normalize_fail_reason(reason) if reason is not None else None,
                    "retryable": True,
                    "status_after": STATUS_PENDING,
                    "next_attempt_at": job["next_attempt_at"],
                    "manual": True,
                    "recorded_at": utc_now(),
                }
            )
            self._write(state)
            return job

    def complete(
        self,
        job_id: str,
        *,
        claim_token: str,
        output: Path,
        endpoint: str,
        provider_request_id: str | None = None,
        generation_id: str | None = None,
    ) -> dict[str, Any]:
        media = output.expanduser().resolve()
        if endpoint not in COMPLETION_ENDPOINTS:
            raise QueueError(f"completion endpoint must be one of {sorted(COMPLETION_ENDPOINTS)}")
        if endpoint in {"image_gen", "image_edit"}:
            if not media.is_file():
                raise QueueError("still output file is missing")
            qa = {"ok": True, "kind": "still", "bytes": media.stat().st_size}
        else:
            qa = analyze_media(media, require_audio=False, require_motion=True)
            if not qa.get("ok"):
                raise QueueError(
                    f"media output failed decode/duration/motion QA: {qa.get('errors')}"
                )
        with self._locked():
            state = self._read()
            job = self._running_job(state, job_id, claim_token)
            if job.get("operation") != endpoint:
                raise QueueError(
                    f"job operation {job.get('operation')} does not match endpoint {endpoint}"
                )
            source_contract = job.get("source_contract")
            if isinstance(source_contract, dict):
                try:
                    require_current_queue_contract(self.root, source_contract)
                except ProductionChainError as exc:
                    raise QueueError(str(exc)) from exc
            elif canonical_contract_required(self.root):
                raise QueueError("queue job source contract is missing for a canonical project")
            usage_binding = None
            if generation_id:
                usage_binding = _usage_binding(
                    self.root,
                    generation_id,
                    job_id,
                    expected_cache_key=job.get("cache_key"),
                )
                if usage_binding["status"] != STATUS_SUCCEEDED:
                    raise QueueError(
                        f"generation {generation_id} ended as {usage_binding['status']}, not succeeded"
                    )
            job["status"] = STATUS_SUCCEEDED
            job["completed_at"] = utc_now()
            job["receipt"] = {
                "endpoint": endpoint,
                "provider_request_id": provider_request_id,
                "generation_id": generation_id,
                "output": str(media),
                "output_sha256": sha256(media),
                "qa": qa,
            }
            if usage_binding is not None:
                job["receipt"]["generation_usage"] = usage_binding
            job["attempts_completed"] = int(job.get("attempts") or 0)
            job.pop("claim_token", None)
            self._write(state)
        try:
            from pipeline_events import append_event

            append_event(
                self.root, stage="i2v", phase="completed", shot_id=str(job.get("shot_id") or "")
            )
        except OSError:
            pass
        # γ4 · tag Grok I2V outputs into takes/<sid>/grok_* for Fill-Idle lane detect
        if endpoint in {"image_to_video", "reference_to_video"} and media.is_file():
            try:
                sid = str(job.get("shot_id") or "")
                contract = (
                    job.get("generation_contract")
                    if isinstance(job.get("generation_contract"), dict)
                    else {}
                )
                provider = str(
                    (contract or {}).get("provider") or job.get("provider") or ""
                ).lower()
                params = (
                    contract.get("parameters")
                    if isinstance(contract, dict) and isinstance(contract.get("parameters"), dict)
                    else {}
                )
                endpoint_name = str(
                    (params or {}).get("source_endpoint") or job.get("endpoint") or ""
                ).lower()
                is_grok = (
                    "grok" in provider
                    or "xai" in provider
                    or "grok" in endpoint_name
                    or "imagine" in endpoint_name
                )
                # Prefer explicit grok markers; avoid re-tagging H3
                if (
                    sid
                    and is_grok
                    and "h3" not in media.name.lower()
                    and "minimax" not in media.name.lower()
                ):
                    takes_dir = self.root / "takes" / sid
                    takes_dir.mkdir(parents=True, exist_ok=True)
                    dest = takes_dir / f"grok_{media.name}"
                    if not dest.exists() and media.resolve() != dest.resolve():
                        import shutil

                        try:
                            dest.hardlink_to(media)
                        except OSError:
                            shutil.copy2(media, dest)
                        # provider sidecar for lane detect
                        side = Path(str(dest) + ".json")
                        if not side.is_file():
                            write_json(
                                side,
                                {
                                    "provider": "grok",
                                    "lane": "grok",
                                    "source_output": str(media),
                                    "from": "media_queue.complete",
                                },
                            )
            except Exception as exc:  # noqa: BLE001 — AF2 honesty
                note_queue_partial(
                    self.root,
                    stage="grok_take_sidecar",
                    error=str(exc),
                    shot_id=str(job.get("shot_id") or ""),
                    job_id=str(job.get("id") or job_id),
                )
                warnings = list(job.get("warnings") or [])
                warnings.append(f"grok_take_sidecar_partial: {str(exc)[:160]}")
                job["warnings"] = warnings[-12:]
                job["partial_side_effects"] = True
        # go4 · Grok bulk continue handoff write (parity H3)
        if endpoint in {"image_to_video", "reference_to_video"}:
            try:
                from continue_handoff import maybe_write_for_clip

                sid = str(job.get("shot_id") or "")
                if sid and media.is_file():
                    mode = "r2v" if endpoint == "reference_to_video" else "i2v"
                    maybe_write_for_clip(self.root, sid, media, engine="grok", mode=mode)
            except Exception as exc:  # noqa: BLE001 — AF2 honesty
                note_queue_partial(
                    self.root,
                    stage="continue_handoff",
                    error=str(exc),
                    shot_id=str(job.get("shot_id") or ""),
                    job_id=str(job.get("id") or job_id),
                )
                warnings = list(job.get("warnings") or [])
                warnings.append(f"continue_handoff_partial: {str(exc)[:160]}")
                job["warnings"] = warnings[-12:]
                job["partial_side_effects"] = True
        return job

    def reconcile(self, *, stale_after_seconds: int = 1800, now: str | None = None) -> list[str]:
        current = _parse_time(now or utc_now())
        reset: list[str] = []
        with self._locked():
            state = self._read()
            for job in state["jobs"]:
                if job.get("status") != STATUS_RUNNING or not job.get("claimed_at"):
                    continue
                if current - _parse_time(job["claimed_at"]) > timedelta(
                    seconds=stale_after_seconds
                ):
                    job["status"] = STATUS_PENDING
                    job["next_attempt_at"] = current.replace(microsecond=0).isoformat()
                    job.pop("claim_token", None)
                    reset.append(job["id"])
            if reset:
                self._write(state)
        return reset


def record_capability(root: Path | str, *, endpoint: str, media: Path) -> dict[str, Any]:
    if endpoint not in ALLOWED_VIDEO_ENDPOINTS:
        raise QueueError(f"unknown video endpoint {endpoint}")
    film_root = Path(root).expanduser().resolve()
    receipts = safe_workspace_directory(film_root, "receipts", field="film receipts directory")
    receipts.mkdir(parents=True, exist_ok=True)
    path = safe_output_path(
        receipts, "capabilities.json", suffixes={".json"}, field="capability receipt"
    )
    qa = analyze_media(media, require_audio=False, require_motion=True)
    result = {
        "endpoint": endpoint,
        "checked_at": utc_now(),
        "media_sha256": sha256(media),
        "qa": qa,
    }
    from util import soft_json, write_json

    state = soft_json(path) if path.is_file() else {"schema_version": 1, "checks": []}
    if not state:
        state = {"schema_version": 1, "checks": []}
    state.setdefault("checks", []).append(result)
    state["latest"] = result
    write_json(path, state)
    if not qa.get("ok"):
        raise QueueError(f"capability canary failed decode/duration/motion QA: {qa.get('errors')}")
    return result


def _generation_contract_from_args(args: argparse.Namespace) -> dict[str, Any] | None:
    values = {
        "provider": getattr(args, "provider", None),
        "model": getattr(args, "model", None),
        "parameters_json": getattr(args, "parameters_json", None),
        "version": getattr(args, "contract_version", None),
    }
    if not any(values.values()):
        return None
    parameters: dict[str, Any] = {}
    raw = values["parameters_json"]
    if raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise QueueError(f"--parameters-json must be valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise QueueError("--parameters-json must be a JSON object")
        parameters = parsed
    return {
        "provider": values["provider"] or "unspecified",
        "model": values["model"] or "unspecified",
        "parameters": parameters,
        "version": values["version"] or "1",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ai-film-grok persistent media queue")
    parser.add_argument("--budget-units", type=int, default=20)
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add")
    add.add_argument("--root", required=True)
    add.add_argument("--shot-id", required=True)
    add.add_argument("--operation", required=True, choices=sorted(OPERATIONS))
    add.add_argument("--prompt-file", required=True)
    add.add_argument("--input", action="append", default=[])
    add.add_argument("--max-attempts", type=int, default=3)
    add.add_argument(
        "--allow-without-pilot",
        action="store_true",
        help="Skip pilot user-approval gate (emergency / unit tests only)",
    )
    add.add_argument(
        "--require-preflight",
        action="store_true",
        help=(
            "Force bulk-preflight even outside pilot-approved bulk. "
            "Default: already hard when pilot user-approved (skip: AIFILM_SKIP_BULK_PREFLIGHT=1)"
        ),
    )
    add.add_argument(
        "--assembly-receipt", help="Path to prompt_assembly_shot.json receipt for traceability"
    )
    add.add_argument("--provider", help="Generation provider for contract-bound job identity")
    add.add_argument("--model", help="Generation model for contract-bound job identity")
    add.add_argument(
        "--parameters-json", help="JSON object of generation parameters for job identity"
    )
    add.add_argument("--contract-version", default="1")
    claim = sub.add_parser("claim")
    claim.add_argument("--root", required=True)
    status = sub.add_parser("status")
    status.add_argument("--root", required=True)
    budget = sub.add_parser("budget")
    budget.add_argument("--root", required=True)
    budget.add_argument("--units", required=True, type=int)
    complete = sub.add_parser("complete")
    complete.add_argument("--root", required=True)
    complete.add_argument("--job-id", required=True)
    complete.add_argument("--claim-token", required=True)
    complete.add_argument("--output", required=True)
    complete.add_argument("--endpoint", required=True, choices=sorted(COMPLETION_ENDPOINTS))
    complete.add_argument("--provider-request-id")
    complete.add_argument("--generation-id")
    fail = sub.add_parser("fail")
    fail.add_argument("--root", required=True)
    fail.add_argument("--job-id", required=True)
    fail.add_argument("--claim-token", required=True)
    fail.add_argument("--error", required=True)
    fail.add_argument(
        "--reason",
        choices=sorted(FAIL_REASONS),
        default=None,
        help="typed fail reason: moderation|motion|rate_limit|decode|other",
    )
    fail.add_argument("--terminal", action="store_true")
    requeue = sub.add_parser(
        "requeue", help="Return failed/pending job to pending (no hand-edit JSON)"
    )
    requeue.add_argument("--root", required=True)
    requeue.add_argument("--job-id", required=True)
    requeue.add_argument(
        "--reason",
        choices=sorted(FAIL_REASONS),
        default=None,
        help="optional reason stamp on requeue",
    )
    requeue.add_argument(
        "--reset-attempts",
        action="store_true",
        help="reset attempts counter (e.g. after soft still + new prompt)",
    )
    reconcile = sub.add_parser("reconcile")
    reconcile.add_argument("--root", required=True)
    reconcile.add_argument("--stale-after", type=int, default=1800)
    canary = sub.add_parser("capability")
    canary.add_argument("--root", required=True)
    canary.add_argument("--endpoint", required=True, choices=sorted(ALLOWED_VIDEO_ENDPOINTS))
    canary.add_argument("--media", required=True)
    args = parser.parse_args(argv)
    try:
        queue = MediaQueue(args.root, budget_units=args.budget_units)
        if args.command == "add":
            result = queue.add_job(
                shot_id=args.shot_id,
                operation=args.operation,
                prompt_file=Path(args.prompt_file),
                inputs=[Path(value) for value in args.input],
                max_attempts=args.max_attempts,
                allow_without_pilot=bool(getattr(args, "allow_without_pilot", False)),
                assembly_receipt=Path(args.assembly_receipt) if args.assembly_receipt else None,
                generation_contract=_generation_contract_from_args(args),
                require_preflight=bool(getattr(args, "require_preflight", False)),
            )
        elif args.command == "claim":
            result = queue.claim()
        elif args.command == "status":
            state = queue.state()
            result = {"state": state, "metrics": queue.metrics(state)}
        elif args.command == "budget":
            state = queue.set_budget(args.units)
            result = {"policy": state["policy"], "metrics": queue.metrics(state)}
        elif args.command == "complete":
            result = queue.complete(
                args.job_id,
                claim_token=args.claim_token,
                output=Path(args.output),
                endpoint=args.endpoint,
                provider_request_id=args.provider_request_id,
                generation_id=args.generation_id,
            )
        elif args.command == "fail":
            result = queue.fail(
                args.job_id,
                claim_token=args.claim_token,
                error=args.error,
                reason=args.reason,
                retryable=not args.terminal,
            )
        elif args.command == "requeue":
            result = queue.requeue(
                args.job_id,
                reason=args.reason,
                reset_attempts=args.reset_attempts,
            )
        elif args.command == "reconcile":
            result = {"reset": queue.reconcile(stale_after_seconds=args.stale_after)}
        else:
            result = record_capability(args.root, endpoint=args.endpoint, media=Path(args.media))
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2))
        return 0
    except (MediaQAError, QueueError, SecurityPolicyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
