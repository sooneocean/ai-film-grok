"""CLI surface for the shared ACE-Step BGM library."""

from __future__ import annotations

import argparse
import os
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
    base = os.environ.get("AIFILM_AUDIO_NODE_URL", "").strip()
    token = os.environ.get("AIFILM_AUDIO_NODE_TOKEN", "").strip()
    if not base or not token:
        raise BGMLibraryError("AIFILM_AUDIO_NODE_URL/TOKEN are required for ACE-Step generation")
    return base, token


def cmd_bgm_library(args: argparse.Namespace, *, emit) -> int:
    action = str(args.bgm_library_action)
    library = _root(args)
    if action == "doctor":
        from audio_node_client import AudioNodeError, health

        base = os.environ.get("AIFILM_AUDIO_NODE_URL", "").strip()
        token = os.environ.get("AIFILM_AUDIO_NODE_TOKEN", "").strip()
        node: dict[str, Any]
        if not base or not token:
            node = {"ok": False, "error": "AIFILM_AUDIO_NODE_URL/TOKEN not configured"}
        else:
            try:
                node = health(base, token)
            except AudioNodeError as exc:
                node = {"ok": False, "error": str(exc)}
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
    return 0
