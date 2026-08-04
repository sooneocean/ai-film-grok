"""Media-generation CLI routes and read-only motion evidence status."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import Any

from env_plate import EnvPlateError, run_env_plate
from motion_plan import MotionPlanError, build_motion_plan
from util import read_json


class MotionRouteError(RuntimeError):
    """Normalized route error suitable for the top-level CLI."""


def env_plate(args: Namespace) -> dict[str, Any]:
    prompt = str(getattr(args, "prompt", None) or "").strip()
    prompt_file = getattr(args, "prompt_file", None)
    if prompt_file:
        try:
            prompt = Path(prompt_file).expanduser().resolve().read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise MotionRouteError(f"cannot read env prompt file: {prompt_file}: {exc}") from exc
    if not prompt:
        raise MotionRouteError("env-plate requires --prompt or --prompt-file")
    try:
        return run_env_plate(
            prompt=prompt,
            root=Path(args.root).expanduser().resolve() if getattr(args, "root", None) else None,
            shot_id=getattr(args, "shot_id", None),
            wait=not bool(getattr(args, "no_wait", False)),
            width=str(getattr(args, "width", None) or "720"),
            height=str(getattr(args, "height", None) or "1280"),
            duration=str(getattr(args, "duration", None) or "5"),
            fps=str(getattr(args, "fps", None) or "24"),
            register=not bool(getattr(args, "no_register", False)),
            extract_keyframe=not bool(getattr(args, "no_keyframe", False)),
            out_dir=Path(args.out_dir) if getattr(args, "out_dir", None) else None,
            poll_timeout=float(getattr(args, "poll_timeout", None) or 240),
        )
    except EnvPlateError as exc:
        raise MotionRouteError(str(exc)) from exc


def motion_plan(args: Namespace) -> dict[str, Any]:
    try:
        return build_motion_plan(Path(args.root), str(args.shot_id))
    except MotionPlanError as exc:
        raise MotionRouteError(str(exc)) from exc


def motion_evidence_status(root: Path | str, shot_id: str) -> dict[str, Any]:
    base = Path(root).expanduser().resolve()
    receipt = read_json(base / "receipts" / "motion-evidence" / f"{shot_id}.json") or {}
    return {
        "kind": "motion-evidence-status",
        "shot_id": shot_id,
        "recorded": bool(receipt),
        "delivery_eligible": receipt.get("delivery_eligible") is True,
        "dry_run": receipt.get("dry_run") is True,
        "receipt": receipt,
    }


def i2v_motion_gate_from_rows(
    shots: list[dict[str, Any]],
    *,
    root: Path | str | None = None,
    write_receipts: bool = False,
    raw_complete: bool = True,
    kb_fallback: bool = False,
    style_ok: bool = True,
    auto_from_root: bool = False,
) -> dict[str, Any]:
    """Shipped entry: grade mean rows → high-motion audit + final gate.

    Each shot: id, heat_phase, mean|mean_absdiff, optional source,
    dramatic_function|df, wardrobe_state, motion_tier|spine_tier, tier.

    When ``auto_from_root`` and root is set with empty shots, rows are collected
    from film-spec + takes/audit (Phase B).
    """
    from i2v_motion_gate import (
        build_high_motion_audit,
        build_i2v_final_gate,
        collect_motion_gate_rows,
        write_motion_gate_receipts,
    )

    rows = list(shots or [])
    if auto_from_root and root is not None and not rows:
        rows = collect_motion_gate_rows(root)
    elif root is not None and rows:
        # Enrich sparse author rows with DF/wardrobe/mean from film root
        auto_map = {
            str(r.get("id") or ""): r
            for r in collect_motion_gate_rows(root)
            if r.get("id")
        }
        enriched: list[dict[str, Any]] = []
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            sid = str(raw.get("id") or raw.get("shot_id") or "")
            base = dict(auto_map.get(sid) or {})
            base.update({k: v for k, v in raw.items() if v is not None and v != ""})
            if sid:
                base["id"] = sid
            enriched.append(base)
        rows = enriched
    audit = build_high_motion_audit(rows)
    gate = build_i2v_final_gate(
        audit,
        raw_complete=raw_complete,
        kb_fallback=kb_fallback,
        style_ok=style_ok,
        shot_count=len(rows),
        raw_ok_count=len(rows) if raw_complete else 0,
    )
    out: dict[str, Any] = {
        "kind": "i2v-motion-gate",
        "ok": gate.get("ok") is True,
        "audit": audit,
        "gate": gate,
        "row_count": len(rows),
        "auto_from_root": bool(auto_from_root and root is not None),
    }
    if write_receipts and root is not None:
        out["receipts"] = write_motion_gate_receipts(root, audit, gate)
    return out
