"""Phase D · review_mode policy (async_dailies | gate_each).

Kept as a dedicated module so advance/final/picture_lock can depend on it
without large edits to review_control.py (which is easy to thrash in multi-agent trees).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import exclusive_file_lock, read_json, utc_now, write_json

REVIEW_MODES = frozenset({"async_dailies", "gate_each"})
DEFAULT_REVIEW_MODE = "async_dailies"
SETTINGS_NAME = "review-control.json"
HARD_CLEAR_BOUNDARIES = frozenset(
    {
        "picture_lock",
        "final",
        "master",
        "master_lock",
        "review-final",
        "export",
        "export-desktop",
        "post_locks",
        "selects_rough_cut",
    }
)


class ReviewModeError(ValueError):
    """Review mode / pending human backlog blocks progress."""


def _root(root: Path | str) -> Path:
    value = Path(root).expanduser().resolve()
    if not value.is_dir():
        raise ReviewModeError("film root must be an existing directory")
    return value


def _settings_path(root: Path) -> Path:
    return root / "receipts" / SETTINGS_NAME


def normalize_review_mode(value: Any) -> str:
    mode = str(value or DEFAULT_REVIEW_MODE).strip().lower()
    if mode not in REVIEW_MODES:
        raise ReviewModeError(f"review_mode must be one of {sorted(REVIEW_MODES)} (got {value!r})")
    return mode


def get_review_mode(root: Path | str) -> str:
    base = _root(root)
    raw = read_json(_settings_path(base))
    if not isinstance(raw, dict):
        return DEFAULT_REVIEW_MODE
    try:
        return normalize_review_mode(raw.get("review_mode", DEFAULT_REVIEW_MODE))
    except ReviewModeError:
        return DEFAULT_REVIEW_MODE


def set_review_mode(root: Path | str, mode: str, *, expected_revision: int | None = None) -> dict[str, Any]:
    """Write review_mode into review-control.json (creates file if missing)."""
    base = _root(root)
    path = _settings_path(base)
    mode = normalize_review_mode(mode)
    path.parent.mkdir(parents=True, exist_ok=True)
    with exclusive_file_lock(path):
        current = read_json(path)
        if not isinstance(current, dict):
            current = {
                "schema_version": 1,
                "kind": "review-control-settings",
                "revision": 0,
                "reviewer": "owner",
                "budget_envelopes": {"still": 0, "motion": 0, "audio": 0, "post": 0},
                "advance_mode": "next_review_gate",
                "autopilot": {
                    "enabled": False,
                    "sample_every": 5,
                    "allowed_providers": [],
                    "telegram_notify": True,
                },
            }
        rev = int(current.get("revision") or 0)
        if expected_revision is not None and rev != int(expected_revision):
            raise ReviewModeError(f"review settings revision is stale (have {rev}, expected {expected_revision})")
        current["review_mode"] = mode
        current["revision"] = rev + 1
        current["updated_at"] = utc_now()
        if "kind" not in current:
            current["kind"] = "review-control-settings"
        write_json(path, current)
        return current


def _is_major_stage(stage_id: str) -> bool:
    sid = str(stage_id or "")
    if sid.startswith("director:"):
        return True
    if sid.startswith("shot:"):
        return False
    return sid in {
        "story",
        "design",
        "budget",
        "pilot",
        "audio",
        "preview",
        "final",
    }


def collect_pending_review_blockers(
    root: Path | str,
    *,
    include_take_picks: bool = True,
    include_stages: bool = True,
    include_shot_stages: bool = False,
) -> list[dict[str, Any]]:
    """Collect human backlog.

    - major stages (story/pilot/final/director:*) always when include_stages
    - shot:* stages only when include_shot_stages (gate_each)
    - multi-take needs_pick when include_take_picks
    """
    base = _root(root)
    blockers: list[dict[str, Any]] = []
    if include_stages:
        try:
            from review_control import review_queue

            items = review_queue(base).get("items") or []
        except Exception:  # noqa: BLE001
            items = []
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                state = str(item.get("state") or "")
                if state not in {"pending_review", "stale"}:
                    continue
                sid = str(item.get("id") or "")
                if sid.startswith("shot:") and not include_shot_stages:
                    continue
                if not sid.startswith("shot:") and not _is_major_stage(sid):
                    continue
                blockers.append(
                    {
                        "id": item.get("id"),
                        "kind": "stage",
                        "state": state,
                        "title": item.get("title"),
                    }
                )
    if include_take_picks:
        try:
            from web.takes_api import list_take_shots

            for shot in list_take_shots(base).get("shots") or []:
                if not isinstance(shot, dict) or not shot.get("needs_pick"):
                    continue
                blockers.append(
                    {
                        "id": f"take:{shot.get('shot_id')}",
                        "kind": "take_pick",
                        "state": "pending_review",
                        "title": f"选 Take · {shot.get('shot_id')}",
                        "shot_id": shot.get("shot_id"),
                        "candidates": shot.get("candidate_count"),
                    }
                )
        except Exception:  # noqa: BLE001
            pass
    return blockers


def assert_review_advance_allowed(
    root: Path | str,
    *,
    boundary: str | None = None,
    next_id: str | None = None,
) -> dict[str, Any]:
    base = _root(root)
    mode = get_review_mode(base)
    boundary_key = str(boundary or next_id or "").strip().lower()
    boundary_token = boundary_key.split(":")[-1].replace("_", "-")
    hard = any(
        token in boundary_key or token.replace("_", "-") == boundary_token
        for token in HARD_CLEAR_BOUNDARIES
    ) or boundary_token in {t.replace("_", "-") for t in HARD_CLEAR_BOUNDARIES}

    if mode == "gate_each":
        blockers = collect_pending_review_blockers(
            base,
            include_take_picks=True,
            include_stages=True,
            include_shot_stages=True,
        )
    elif hard:
        # picture_lock / final: major stages + multi-take picks (not every shot: row)
        blockers = collect_pending_review_blockers(
            base,
            include_take_picks=True,
            include_stages=True,
            include_shot_stages=False,
        )
    else:
        # async_dailies bulk: major stage pending only
        blockers = collect_pending_review_blockers(
            base,
            include_take_picks=False,
            include_stages=True,
            include_shot_stages=False,
        )

    # Don't treat the destination stage itself as a blocker (e.g. final is always
    # pending_review until review-final exists — that must not hard-lock `final`).
    def _self_stage(bid: str) -> bool:
        b = str(bid or "").lower()
        if not boundary_key:
            return False
        if b in (boundary_key, boundary_token) or b.endswith(":" + boundary_token):
            return True
        if boundary_token in {"final", "review-final", "export", "export-desktop"} and b == "final":
            return True
        if boundary_token in {"picture-lock", "picture_lock"} and "picture" in b:
            return True
        return False

    blockers = [b for b in blockers if not _self_stage(str(b.get("id") or ""))]

    report = {
        "ok": not blockers,
        "review_mode": mode,
        "boundary": boundary_key or None,
        "hard_clear": hard,
        "blockers": blockers,
        "blocker_count": len(blockers),
    }
    if blockers:
        kinds = sorted({str(b.get("kind")) for b in blockers})
        ids = ", ".join(str(b.get("id")) for b in blockers[:8])
        more = "" if len(blockers) <= 8 else f" (+{len(blockers) - 8})"
        where = "hard boundary" if hard else f"review_mode={mode}"
        raise ReviewModeError(
            f"pending human review blocks advance ({where}; kinds={kinds}): {ids}{more}"
        )
    return report
