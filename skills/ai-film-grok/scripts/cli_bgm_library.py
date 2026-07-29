"""CLI surface for the shared ACE-Step BGM library."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import Any

from bgm_library import (
    BGMLibraryError,
    approve_candidate,
    audit_library,
    baseline_recipes,
    default_library_root,
    generate_candidates,
    library_status,
    record_gaps,
    reject_candidate,
    select_timeline,
    series_recipes,
    write_review_pack,
)
from music_cue import build_music_timeline
from util import read_json, write_json

_NODE_MODEL_FIELDS = ("model", "music_model", "music_checkpoint_fingerprint", "performance_model")
_NODE_GPU_FIELDS = ("available", "name", "cuda", "driver", "free_vram_mib", "total_vram_mib")
_NODE_MODEL_KINDS = ("tts", "music", "sfx", "performance")


def _public_node_health(raw: Any, *, token: str) -> dict[str, Any]:
    """Project an untrusted health response to the node's public capability schema."""
    if not isinstance(raw, dict):
        return {"ok": False}
    public: dict[str, Any] = {"ok": raw.get("ok") is True}
    if raw.get("node") == "private-lan":
        public["node"] = "private-lan"
    models = raw.get("models")
    if isinstance(models, dict):
        public_models = {
            kind: models[kind] for kind in _NODE_MODEL_KINDS if isinstance(models.get(kind), bool)
        }
        if public_models:
            public["models"] = public_models
    if isinstance(raw.get("music_batch"), bool):
        public["music_batch"] = raw["music_batch"]
    for field in _NODE_MODEL_FIELDS:
        value = raw.get(field)
        if isinstance(value, str) and len(value) <= 256 and token not in value:
            public[field] = value
    gpu = raw.get("gpu")
    if isinstance(gpu, dict):
        public_gpu: dict[str, Any] = {}
        for field in _NODE_GPU_FIELDS:
            value = gpu.get(field)
            if (
                field == "available"
                and isinstance(value, bool)
                or field in {"name", "cuda"}
                and isinstance(value, str)
                and len(value) <= 128
                and token not in value
                or field == "driver"
                and isinstance(value, str)
                and bool(re.fullmatch(r"[0-9][0-9.]{0,30}", value))
                or field.endswith("_mib")
                and isinstance(value, int)
                and value >= 0
            ):
                public_gpu[field] = value
        if public_gpu:
            public["gpu"] = public_gpu
    return public


def add_bgm_library_parsers(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser(
        "bgm-library",
        help="Manage the shared, approved ACE-Step BGM library and anti-repeat routing",
    )
    actions = parser.add_subparsers(dest="bgm_library_action", required=True)
    for name in ("doctor", "status", "audit"):
        command = actions.add_parser(name)
        command.add_argument("--library-root", default="")

    generate = actions.add_parser("generate", help="Generate pending candidates offline on 5090")
    generate.add_argument("--library-root", default="")
    generate.add_argument("--recipe-pack", choices=("baseline-v1",), default="baseline-v1")
    generate.add_argument("--slot", action="append", default=[])
    generate.add_argument("--batch-size", type=int, choices=range(1, 9), default=4)
    generate.add_argument("--seed-base", type=int, default=5100)

    canary = actions.add_parser(
        "canary",
        help="Generate one bounded 30-second batch for real-node acceptance",
    )
    canary.add_argument("--library-root", default="")
    canary.add_argument(
        "--slot",
        choices=tuple(recipe["recipe_id"] for recipe in baseline_recipes()),
        default="baseline-v1-rnb-pad",
    )
    canary.add_argument("--duration", type=float, default=30.0)
    canary.add_argument("--batch-size", type=int, choices=range(1, 9), default=4)
    canary.add_argument("--seed-base", type=int, default=5900)

    review = actions.add_parser("review-pack", help="Write a local HTML listening pack")
    review.add_argument("--library-root", default="")

    approve = actions.add_parser("approve", help="Approve a fully heard instrumental candidate")
    approve.add_argument("--library-root", default="")
    approve.add_argument("--asset-id", required=True)
    approve.add_argument("--reviewer", required=True)
    approve.add_argument("--license-note", required=True)
    approve.add_argument("--instrumental-confirmed", action="store_true")

    reject = actions.add_parser("reject", help="Reject a candidate without deleting its receipt")
    reject.add_argument("--library-root", default="")
    reject.add_argument("--asset-id", required=True)
    reject.add_argument("--reviewer", required=True)
    reject.add_argument("--reason", required=True)

    for name in ("plan", "select"):
        route = actions.add_parser(name, help=f"{name.title()} approved BGM for a film timeline")
        route.add_argument("--library-root", default="")
        route.add_argument("--root", required=True)
        route.add_argument("--series-id", default="")
        route.add_argument("--allow-gaps", action="store_true")

    series = actions.add_parser("series-pack", help="Generate nine lineage-bound series candidates")
    series.add_argument("--library-root", default="")
    series.add_argument("--root", required=True)
    series.add_argument("--series-id", required=True)
    series.add_argument("--seed-base", type=int, default=9100)


def _root(args: argparse.Namespace) -> Path:
    raw = str(getattr(args, "library_root", "") or "").strip()
    return Path(raw).expanduser().resolve() if raw else default_library_root()


def _flatten_shots(value: Any) -> list[dict[str, Any]]:
    shots: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if value.get("id") and any(
            key in value for key in ("duration", "duration_sec", "nar", "music_cue")
        ):
            shots.append(value)
        for key in ("episodes", "scenes", "beats", "shots"):
            child = value.get(key)
            if isinstance(child, list):
                for item in child:
                    shots.extend(_flatten_shots(item))
    elif isinstance(value, list):
        for item in value:
            shots.extend(_flatten_shots(item))
    seen: set[str] = set()
    unique = []
    for shot in shots:
        shot_id = str(shot.get("id") or "")
        if shot_id and shot_id not in seen:
            seen.add(shot_id)
            unique.append(shot)
    return unique


def _film_timeline(film_root: Path) -> tuple[str, str, list[dict[str, Any]]]:
    spec = read_json(film_root / "film-spec.json")
    if not isinstance(spec, dict):
        raise BGMLibraryError("film-spec.json is required for BGM routing")
    shots = _flatten_shots(spec)
    if not shots:
        raise BGMLibraryError("film-spec.json has no routable shots")
    starts: dict[str, float] = {}
    ends: dict[str, float] = {}
    cursor = 0.0
    for shot in shots:
        shot_id = str(shot["id"])
        try:
            duration = float(shot.get("duration_sec") or shot.get("duration") or 5.0)
        except (TypeError, ValueError) as exc:
            raise BGMLibraryError(f"invalid shot duration: {shot_id}") from exc
        starts[shot_id] = cursor
        cursor += max(0.1, duration)
        ends[shot_id] = cursor
    sound_plan = spec.get("sound_plan") if isinstance(spec.get("sound_plan"), dict) else {}
    mood = str(sound_plan.get("mood") or "rnb")
    timeline = build_music_timeline(
        shots,
        shot_starts=starts,
        shot_ends=ends,
        default_mood=mood,
    )
    film_id = str(spec.get("id") or spec.get("title") or film_root.name)
    series_id = str(spec.get("series_id") or "")
    return film_id, series_id, timeline


def _node_credentials() -> tuple[str, str]:
    # ``config.env`` is deliberately loaded by the central config loader so
    # credentials remain out of command arguments and shell history.  Direct
    # environment values still take precedence there.
    from config_loader import get_config

    get_config()
    base = os.environ.get("AIFILM_AUDIO_NODE_URL", "").strip()
    token = os.environ.get("AIFILM_AUDIO_NODE_TOKEN", "").strip()
    if not base or not token:
        raise BGMLibraryError("AIFILM_AUDIO_NODE_URL/TOKEN are required for ACE-Step generation")
    return base, token


def cmd_bgm_library(args: argparse.Namespace, *, emit) -> int:
    action = str(args.bgm_library_action)
    library = _root(args)
    if action == "doctor":
        from audio_node_client import health

        node: dict[str, Any]
        try:
            base, token = _node_credentials()
        except BGMLibraryError:
            node = {"ok": False, "error": "AIFILM_AUDIO_NODE_URL/TOKEN not configured"}
        else:
            try:
                node = _public_node_health(health(base, token), token=token)
            except Exception:
                node = {"ok": False, "error": "audio node health check failed"}
        report = {"ok": bool(node.get("ok")), "node": node, "library": library_status(library)}
    elif action == "status":
        report = library_status(library)
    elif action == "audit":
        report = audit_library(library)
    elif action == "review-pack":
        report = write_review_pack(library)
    elif action == "approve":
        report = approve_candidate(
            library,
            args.asset_id,
            reviewer=args.reviewer,
            license_note=args.license_note,
            instrumental_confirmed=bool(args.instrumental_confirmed),
        )
    elif action == "reject":
        report = reject_candidate(
            library,
            args.asset_id,
            reviewer=args.reviewer,
            reason=args.reason,
        )
    elif action == "generate":
        base, token = _node_credentials()
        recipes = baseline_recipes()
        slots = {str(slot) for slot in args.slot}
        if slots:
            recipes = [recipe for recipe in recipes if recipe["recipe_id"] in slots]
            missing = slots - {str(recipe["recipe_id"]) for recipe in recipes}
            if missing:
                raise BGMLibraryError(
                    "unknown baseline recipe slots: " + ", ".join(sorted(missing))
                )
        batches = []
        for index, recipe in enumerate(recipes):
            seed_start = int(args.seed_base) + index * int(args.batch_size)
            seeds = list(range(seed_start, seed_start + int(args.batch_size)))
            batches.append(
                generate_candidates(
                    library,
                    base_url=base,
                    token=token,
                    recipe=recipe,
                    batch_size=int(args.batch_size),
                    seeds=seeds,
                )
            )
        report = {"ok": True, "recipe_pack": args.recipe_pack, "batches": batches}
    elif action == "canary":
        duration = float(args.duration)
        if not 10.0 <= duration <= 600.0:
            raise BGMLibraryError("canary duration must be between 10 and 600 seconds")
        base, token = _node_credentials()
        recipe = next(item for item in baseline_recipes() if item["recipe_id"] == str(args.slot))
        recipe = {**recipe, "duration": duration}
        seeds = list(range(int(args.seed_base), int(args.seed_base) + int(args.batch_size)))
        batch = generate_candidates(
            library,
            base_url=base,
            token=token,
            recipe=recipe,
            batch_size=int(args.batch_size),
            seeds=seeds,
        )
        candidates = batch["candidates"]
        checksums = [str(item["sha256"]) for item in candidates]
        fingerprints = [
            tuple((item.get("technical") or {}).get("fingerprint") or []) for item in candidates
        ]
        durations = [
            float((item.get("technical") or {}).get("duration_sec") or 0.0) for item in candidates
        ]
        duration_tolerance = max(1.0, duration * 0.05)
        checks = {
            "candidate_count": len(candidates) == int(args.batch_size),
            "unique_checksums": len(set(checksums)) == len(checksums),
            "unique_fingerprints": len(set(fingerprints)) == len(fingerprints),
            "duration_ok": all(abs(value - duration) <= duration_tolerance for value in durations),
            "technical_pass": all(
                bool((item.get("technical") or {}).get("ok")) for item in candidates
            ),
            "pending_only": all(
                item.get("status") == "pending_human_review" for item in candidates
            ),
        }
        report = {
            **batch,
            "ok": all(checks.values()),
            "status": "pending_human_review",
            "slot": args.slot,
            "requested_duration_sec": duration,
            "checks": checks,
        }
    elif action in {"plan", "select"}:
        film_root = Path(args.root).expanduser().resolve()
        film_id, spec_series_id, timeline = _film_timeline(film_root)
        report = select_timeline(
            library,
            film_id=film_id,
            series_id=str(args.series_id or spec_series_id),
            timeline=timeline,
            require_complete=not bool(args.allow_gaps),
        )
        if report["gaps"]:
            report["gap_queue"] = record_gaps(library, report)
        if action == "select":
            receipt = film_root / "receipts" / "bgm-selection.json"
            write_json(receipt, report)
            report = {**report, "receipt": str(receipt)}
    elif action == "series-pack":
        base, token = _node_credentials()
        recipes = series_recipes(library, series_id=args.series_id)
        candidates = []
        for index, recipe in enumerate(recipes):
            result = generate_candidates(
                library,
                base_url=base,
                token=token,
                recipe=recipe,
                batch_size=1,
                seeds=[int(args.seed_base) + index],
            )
            candidates.extend(result["candidates"])
        receipt = Path(args.root).expanduser().resolve() / "receipts" / "bgm-series-pack.json"
        report = {
            "ok": True,
            "series_id": args.series_id,
            "status": "pending_human_review",
            "candidate_count": len(candidates),
            "candidates": candidates,
        }
        write_json(receipt, report)
        report["receipt"] = str(receipt)
    else:  # pragma: no cover
        raise BGMLibraryError(f"unknown BGM library action: {action}")
    emit(report)
    return 2 if action == "canary" and report.get("ok") is not True else 0
