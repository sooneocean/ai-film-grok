"""Read-only production projections for the localhost workbench.

Browser never invents pipeline state.  These helpers only *read* existing
receipts / soft queue probes and return fail-soft dicts for
``GET /api/console-state``.

Default path: ``receipts/dispatch.json`` (last ``aifilm dispatch`` write).
Never runs full ``build_dispatch`` on GET — too slow and side-effecty.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from util import read_json


def _clip_text(value: Any, *, max_len: int = 480) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


def project_dispatch_for_console(root: Path | str) -> dict[str, Any]:
    """Project last dispatch receipt into a small workbench-safe view.

    Returns always-present keys so the UI can render without null checks.
    ``available`` is False when no receipt exists or it is unreadable.
    """
    base = Path(root).expanduser().resolve()
    empty: dict[str, Any] = {
        "available": False,
        "source": None,
        "at": None,
        "stage_public": None,
        "craft_stage": None,
        "pipeline_stage": None,
        "next_id": None,
        "next_cmd": None,
        "next_why": None,
        "route_catalog_id": None,
        "blocked_by": [],
        "required_proof": None,
        "weapon_line": None,
        "weapon_layer": None,
        "copy_cmd": f'aifilm dispatch --root "{base}"',
        "hint": "尚无 dispatch 回执。在终端跑一次 aifilm dispatch --root <film> 后刷新。",
    }
    path = base / "receipts" / "dispatch.json"
    raw = read_json(path)
    if not isinstance(raw, dict) or not raw:
        return empty

    action = raw.get("next_action") if isinstance(raw.get("next_action"), dict) else {}
    weapon = raw.get("weapon_route") if isinstance(raw.get("weapon_route"), dict) else {}

    next_cmd = _clip_text(raw.get("next_cmd") or action.get("cmd"), max_len=1536)
    next_why = _clip_text(raw.get("next_why") or action.get("why"), max_len=768)
    next_id = raw.get("next_id") or action.get("id")
    if next_id is not None:
        next_id = str(next_id)

    blocked: list[Any] = []
    for key in ("blocked_by",):
        val = action.get(key) if action.get(key) is not None else raw.get(key)
        if isinstance(val, list):
            blocked = val[:12]
            break
    handoff = raw.get("department_handoff") if isinstance(raw.get("department_handoff"), dict) else {}
    if not blocked and isinstance(handoff.get("blocked_by"), list):
        blocked = handoff.get("blocked_by")[:12]

    required_proof = action.get("required_proof") or raw.get("required_proof")
    if required_proof is not None and not isinstance(required_proof, (str, list, dict)):
        required_proof = str(required_proof)

    weapon_line = _clip_text(
        raw.get("weapon_inventory_line")
        or weapon.get("inventory_line")
        or weapon.get("line")
        or weapon.get("primary"),
        max_len=240,
    )

    # Prefer the bound next_cmd for copy; otherwise a fresh dispatch probe.
    copy_cmd = next_cmd or f'aifilm dispatch --root "{base}"'

    return {
        "available": True,
        "source": "receipts/dispatch.json",
        "at": raw.get("at") or raw.get("generated_at"),
        "stage_public": raw.get("stage_public"),
        "craft_stage": raw.get("craft_stage"),
        "pipeline_stage": raw.get("pipeline_stage"),
        "next_id": next_id,
        "next_cmd": next_cmd,
        "next_why": next_why,
        "route_catalog_id": raw.get("route_catalog_id") or next_id,
        "blocked_by": blocked,
        "required_proof": required_proof,
        "weapon_line": weapon_line,
        "weapon_layer": weapon.get("layer") or ("weapon" if weapon else None),
        "copy_cmd": copy_cmd,
        "hint": None,
    }


def project_queue_snapshot(root: Path | str) -> dict[str, Any]:
    """Soft media-queue + takes-count snapshot (never raises)."""
    base = Path(root).expanduser().resolve()
    out: dict[str, Any] = {
        "available": False,
        "job_counts": {},
        "running": 0,
        "unknown": 0,
        "takes_count": None,
    }
    try:
        from review_control import runtime_status

        rt = runtime_status(base)
        if isinstance(rt, dict):
            out["available"] = True
            out["job_counts"] = rt.get("job_counts") or {}
            out["running"] = int(rt.get("running") or 0)
            out["unknown"] = int(rt.get("unknown") or 0)
    except Exception:  # noqa: BLE001 — fail-soft for console GET
        pass

    # Takes progress: count files under takes/ (common H3 progress signal).
    takes_dir = base / "takes"
    if takes_dir.is_dir():
        try:
            n = sum(1 for p in takes_dir.rglob("*") if p.is_file() and not p.is_symlink())
            out["takes_count"] = n
            out["available"] = True
        except OSError:
            pass
    return out


def enrich_console_state(root: Path | str, state: dict[str, Any]) -> dict[str, Any]:
    """Attach dispatch + queue projections onto an existing console-state dict."""
    base = Path(root).expanduser().resolve()
    state = dict(state)
    state["dispatch_projection"] = project_dispatch_for_console(base)
    state["queue_snapshot"] = project_queue_snapshot(base)
    try:
        from web.director_live_ext import project_director_live
        state["director_live"] = project_director_live(base)
    except Exception:
        state["director_live"] = {"kind": "director-center-live", "available": False}
    return state


def safe_project_live(root: Path | str, **kw: Any) -> dict[str, Any]:
    """Fail-soft wrapper around :func:`project_director_live`.

    On success returns the live projection unchanged. On *any* exception
    returns a deterministic degraded shape whose key set is **identical** to
    ``project_director_live``'s (values empty/zero, ``available=False``) so
    downstream UI never needs null checks and shape-parity CI stays green.

    This is the shared guard for single-film serve mode, SSE, and any other
    caller that must never 500 on a malformed film root. (Studio aggregation
    keeps its own top-level guard in ``studio.build_studio_live`` because it
    needs a studio-scoped ``degraded`` flag.)
    """
    try:
        return project_director_live(root, **kw)
    except Exception as exc:  # noqa: BLE001 — top-level fail-soft guard
        logging.getLogger("web.projection").warning(
            "safe_project_live degraded for %s: %s: %s", root, type(exc).__name__, exc
        )
        return {
            "kind": "director-center-live",
            "available": False,
            "revision": 0,
            "review_mode": None,
            "dispatch": {
                "available": False,
                "stage_public": None,
                "craft_stage": None,
                "pipeline_stage": None,
                "next_id": None,
                "next_cmd": None,
                "next_why": None,
                "approval_class": None,
                "console_url": None,
                "copy_cmd": None,
                "blocked_by": [],
            },
            "queue": {
                "available": False,
                "pending": 0,
                "running": 0,
                "reviewable": 0,
                "failed": 0,
                "takes_count": None,
                "multi_take_shots": 0,
                "job_counts": {},
                "unknown": 0,
            },
            "human_inbox": [],
            "inbox_count": 0,
            "activity": [],
            "gates": {"blocking": False, "hard_fail": []},
            "session": {"active": False, "port": None, "pid": None, "url": None},
        }


# Re-export director-live API (implementation in director_live_ext)
from web.director_live_ext import (  # noqa: E402
    attach_console_url_to_dispatch,
    project_director_live,
    project_events_tail,
    project_human_inbox,
    session_meta,
)
