#!/usr/bin/env python3
"""Director final-review scorecard + reshoot notes (closed production loop)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# All dimensions must be explicitly scored on --approve.
SCORECARD_DIMENSIONS: tuple[str, ...] = (
    "identity",
    "style",  # medium/palette/line language coherence across whole film
    "motion",
    "escalation",
    "audio",
    "subs",
    "dead_air",
)

# CLI flag stem: --score-identity, --score-dead-air, ...
SCORECARD_CLI_FLAGS: dict[str, str] = {
    dim: f"score_{dim}" for dim in SCORECARD_DIMENSIONS
}

RESHOOT_ACTIONS = frozenset({"keep", "reshoot", "recut"})
ITEM_STATUSES = frozenset({"open", "resolved"})
REASON_CODES = frozenset(SCORECARD_DIMENSIONS) | frozenset({"other", "continuity", "performance"})

# Fail dimension → default next action for the set
_DEFAULT_ACTION_FOR_DIM: dict[str, str] = {
    "identity": "reshoot",
    "style": "reshoot",
    "motion": "reshoot",
    "escalation": "recut",
    "audio": "recut",
    "subs": "recut",
    "dead_air": "recut",
}


class DirectorReviewError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def empty_scorecard() -> dict[str, bool | None]:
    return {dim: None for dim in SCORECARD_DIMENSIONS}


def normalize_score_value(value: object, *, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        token = value.strip().lower()
        if token in {"pass", "true", "yes", "1", "ok"}:
            return True
        if token in {"fail", "false", "no", "0"}:
            return False
    raise DirectorReviewError(
        f"{field} must be pass|fail (or true|false); got {value!r}"
    )


def build_scorecard_from_mapping(raw: dict[str, Any]) -> dict[str, bool]:
    """Build scorecard from a dict of dimension → pass/fail."""
    if not isinstance(raw, dict):
        raise DirectorReviewError("scorecard must be an object")
    card: dict[str, bool] = {}
    missing: list[str] = []
    for dim in SCORECARD_DIMENSIONS:
        if dim not in raw and dim.replace("_", "-") not in raw:
            missing.append(dim)
            continue
        value = raw.get(dim, raw.get(dim.replace("_", "-")))
        card[dim] = normalize_score_value(value, field=f"scorecard.{dim}")
    if missing:
        raise DirectorReviewError(
            "scorecard missing dimensions: "
            + ", ".join(missing)
            + f" (required: {', '.join(SCORECARD_DIMENSIONS)})"
        )
    return card


def build_scorecard_from_cli(args: Any) -> dict[str, bool]:
    """Read --score-* flags from argparse Namespace."""
    raw: dict[str, Any] = {}
    missing: list[str] = []
    for dim, attr in SCORECARD_CLI_FLAGS.items():
        value = getattr(args, attr, None)
        if value is None:
            missing.append(dim)
        else:
            raw[dim] = value
    if missing:
        flags = ", ".join(f"--score-{d.replace('_', '-')}" for d in missing)
        raise DirectorReviewError(
            f"review-final requires full scorecard; missing: {flags}"
        )
    return build_scorecard_from_mapping(raw)


def scorecard_all_pass(card: dict[str, bool]) -> bool:
    return all(card.get(dim) is True for dim in SCORECARD_DIMENSIONS)


def scorecard_failures(card: dict[str, bool]) -> list[str]:
    return [dim for dim in SCORECARD_DIMENSIONS if card.get(dim) is not True]


def scorecard_payload(card: dict[str, bool]) -> dict[str, Any]:
    return {
        "dimensions": {dim: bool(card.get(dim)) for dim in SCORECARD_DIMENSIONS},
        "all_pass": scorecard_all_pass(card),
        "failures": scorecard_failures(card),
        "version": 1,
    }


def validate_scorecard_for_approve(card: dict[str, bool]) -> dict[str, Any]:
    """Fail closed if any dimension is fail/missing."""
    fails = scorecard_failures(card)
    if fails:
        raise DirectorReviewError(
            "scorecard fail on: "
            + ", ".join(fails)
            + " — write director_notes / reshoot, then re-score before --approve can set final_complete"
        )
    payload = scorecard_payload(card)
    payload["all_pass"] = True
    return payload


def scorecard_is_complete_and_passing(review: object) -> bool:
    """Used by recompute_gates — old reviews without scorecard fail closed."""
    if not isinstance(review, dict):
        return False
    sc = review.get("scorecard")
    if not isinstance(sc, dict):
        return False
    dims = sc.get("dimensions")
    if not isinstance(dims, dict):
        return False
    return all(dims.get(dim) is True for dim in SCORECARD_DIMENSIONS)


def default_action_for_reason(reason_code: str) -> str:
    return _DEFAULT_ACTION_FOR_DIM.get(reason_code, "reshoot")


def _next_item_id(items: list[dict[str, Any]]) -> str:
    n = 1
    existing = {str(it.get("id") or "") for it in items}
    while f"rn_{n:03d}" in existing:
        n += 1
    return f"rn_{n:03d}"


def empty_director_notes() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "updated_at": utc_now(),
        "source": None,
        "output_sha256": None,
        "scorecard": None,
        "items": [],
        "closed_at": None,
    }


def open_reshoot_items(notes: object) -> list[dict[str, Any]]:
    if not isinstance(notes, dict):
        return []
    items = notes.get("items")
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for it in items:
        if isinstance(it, dict) and it.get("status") == "open" and it.get("action") != "keep":
            out.append(it)
    return out


def reshoots_clear(notes: object) -> bool:
    """True when no open reshoot/recut work remains (or no notes file)."""
    if notes is None:
        return True
    return len(open_reshoot_items(notes)) == 0


def add_reshoot_item(
    notes: dict[str, Any],
    *,
    action: str,
    reason_code: str,
    note: str = "",
    shot_id: str | None = None,
    source: str = "manual",
) -> dict[str, Any]:
    act = (action or "").strip().lower()
    if act not in RESHOOT_ACTIONS:
        raise DirectorReviewError(
            f"action must be one of {sorted(RESHOOT_ACTIONS)}; got {action!r}"
        )
    reason = (reason_code or "").strip().lower()
    if reason not in REASON_CODES:
        raise DirectorReviewError(
            f"reason_code must be one of {sorted(REASON_CODES)}; got {reason_code!r}"
        )
    items = notes.setdefault("items", [])
    if not isinstance(items, list):
        raise DirectorReviewError("director_notes.items must be an array")
    item = {
        "id": _next_item_id(items),
        "shot_id": shot_id,
        "action": act,
        "reason_code": reason,
        "status": "open" if act != "keep" else "resolved",
        "note": (note or "").strip(),
        "created_at": utc_now(),
        "resolved_at": None if act != "keep" else utc_now(),
        "source": source,
    }
    items.append(item)
    notes["updated_at"] = utc_now()
    notes["closed_at"] = None
    notes["source"] = source
    return item


def resolve_reshoot_item(
    notes: dict[str, Any],
    *,
    item_id: str | None = None,
    shot_id: str | None = None,
    resolve_note: str = "",
) -> list[dict[str, Any]]:
    """Resolve open items by id and/or shot_id. Returns list of resolved items."""
    items = notes.get("items")
    if not isinstance(items, list):
        raise DirectorReviewError("director_notes.items must be an array")
    if not item_id and not shot_id:
        raise DirectorReviewError("resolve requires --item-id and/or --shot-id")
    resolved: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict) or it.get("status") != "open":
            continue
        if item_id and it.get("id") != item_id:
            continue
        if shot_id and it.get("shot_id") != shot_id:
            continue
        it["status"] = "resolved"
        it["resolved_at"] = utc_now()
        if resolve_note:
            prev = it.get("note") or ""
            it["note"] = (prev + " | resolved: " + resolve_note).strip(" |")
        resolved.append(it)
    if not resolved:
        raise DirectorReviewError(
            f"no open reshoot items matched item_id={item_id!r} shot_id={shot_id!r}"
        )
    notes["updated_at"] = utc_now()
    if reshoots_clear(notes):
        notes["closed_at"] = utc_now()
    return resolved


def build_notes_from_scorecard_failures(
    card: dict[str, bool],
    *,
    notes_text: str,
    output_sha256: str | None,
    shot_ids: list[str] | None = None,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create/update director_notes from failing scorecard dimensions.

    If shot_ids provided, one reshoot/recut item per (shot × fail_dim) for
    identity/motion; otherwise one film-level item per fail dim.
    """
    package = existing if isinstance(existing, dict) else empty_director_notes()
    fails = scorecard_failures(card)
    package["scorecard"] = scorecard_payload(card)
    package["output_sha256"] = output_sha256
    package["source"] = "review-final"
    package["updated_at"] = utc_now()
    package["closed_at"] = None
    package.setdefault("items", [])

    shot_list = [s for s in (shot_ids or []) if s]
    for dim in fails:
        action = default_action_for_reason(dim)
        note = f"scorecard.{dim}=fail — {notes_text}".strip()
        if shot_list and dim in ("identity", "style", "motion", "escalation"):
            for sid in shot_list:
                add_reshoot_item(
                    package,
                    action=action,
                    reason_code=dim,
                    note=note,
                    shot_id=sid,
                    source="review-final",
                )
        else:
            add_reshoot_item(
                package,
                action=action,
                reason_code=dim,
                note=note,
                shot_id=None,
                source="review-final",
            )
    return package


def parse_shot_id_list(raw: object) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    text = str(raw).strip()
    if not text:
        return []
    parts = [p.strip() for p in text.replace(";", ",").split(",")]
    return [p for p in parts if p]
