#!/usr/bin/env python3
"""Narrative control plane for the canonical vertical-drama graph.

The module is deliberately provider-free.  It owns narrative revisions,
node-level locks, semantic validation, stale propagation, and the hash that
binds a canonical graph to its executable film-spec projection.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from util import read_json, write_json


GRAPH_SCHEMA_VERSION = 2
GRAPH_NAME = "drama-graph.json"
PROJECTION_KEY = "_projection"
CONTROL_STATES = frozenset({"draft", "review", "locked", "stale"})
LOCK_SCOPES = ("story", "beats", "shots", "panels")
DIRECTOR_BOARD_FIELDS = (
    "emotional_turn",
    "audience_question",
    "image_priority",
    "sound_priority",
    "coverage_strategy",
    "cut_intent",
)
DIRECTOR_BOARD_APPROVAL_STATES = frozenset({"draft", "review", "approved"})
STABLE_SHOT_RE = re.compile(r"^ep\d+_sc\d+_bt\d+_sh\d+$")
PLACEHOLDER_RE = re.compile(
    r"^(?:todo|tbd|needs_authoring|待补|待定|待填写|冲突顶点|余韵与续集钩子|advance story)$",
    re.IGNORECASE,
)


class NarrativeControlError(ValueError):
    """A fail-closed narrative control error with a stable reason code."""

    def __init__(self, message: str, *, code: str = "NARRATIVE_CONTROL") -> None:
        super().__init__(message)
        self.code = code


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and not PLACEHOLDER_RE.match(value.strip())


def _canonical_content(value: Any) -> Any:
    """Strip volatile bookkeeping before hashing narrative content."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key in sorted(value):
            if key in {"content_sha256", "revision", "updated_at", "at", "control", "state"}:
                continue
            if key == "derived_from":
                # Paths/timestamps describe provenance, not creative content.
                out[key] = {
                    k: _canonical_content(v)
                    for k, v in value[key].items()
                    if k not in {"at", "film_spec", "style_bible", "root"}
                }
            else:
                out[key] = _canonical_content(value[key])
        return out
    if isinstance(value, list):
        return [_canonical_content(item) for item in value]
    return value


def graph_content_sha256(graph: dict[str, Any]) -> str:
    payload = json.dumps(
        _canonical_content(graph), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _control(node: dict[str, Any], *, default_state: str = "draft") -> dict[str, Any]:
    raw = node.get("control") if isinstance(node.get("control"), dict) else {}
    state = str(raw.get("state") or default_state)
    if state not in CONTROL_STATES:
        state = default_state
    return {
        "state": state,
        "revision": int(raw.get("revision") or 1),
        "locked_fields": list(raw.get("locked_fields") or []),
        "locked_at": raw.get("locked_at"),
        "lock_reason": raw.get("lock_reason"),
    }


def _set_control(node: dict[str, Any], **updates: Any) -> None:
    current = _control(node)
    current.update({k: v for k, v in updates.items() if v is not None})
    node["control"] = current


def iter_nodes(graph: dict[str, Any]) -> Iterable[tuple[str, str, dict[str, Any], str | None]]:
    """Yield (node_ref, node_type, node, parent_ref) in stable tree order."""
    story = graph.get("story")
    if isinstance(story, dict):
        yield "story", "story", story, None
    for ep in graph.get("episodes") or []:
        if not isinstance(ep, dict):
            continue
        ep_ref = str(ep.get("id") or "episode")
        yield ep_ref, "episode", ep, "story" if isinstance(graph.get("story"), dict) else None
        for sc in ep.get("scenes") or []:
            if not isinstance(sc, dict):
                continue
            sc_ref = str(sc.get("id") or "scene")
            yield sc_ref, "scene", sc, ep_ref
            for bt in sc.get("beats") or []:
                if not isinstance(bt, dict):
                    continue
                bt_ref = str(bt.get("id") or "beat")
                yield bt_ref, "beat", bt, sc_ref
                for sh in bt.get("shots") or []:
                    if not isinstance(sh, dict):
                        continue
                    sh_ref = str(sh.get("id") or "shot")
                    yield sh_ref, "shot", sh, bt_ref
                    for panel in sh.get("panels") or []:
                        if not isinstance(panel, dict):
                            continue
                        panel_ref = str(panel.get("id") or "panel")
                        yield panel_ref, "panel", panel, sh_ref


def node_index(graph: dict[str, Any]) -> dict[str, tuple[str, str, dict[str, Any], str | None]]:
    out: dict[str, tuple[str, str, dict[str, Any], str | None]] = {}
    for row in iter_nodes(graph):
        ref, node_type, node, parent = row
        out[ref] = row
        out.setdefault(f"{node_type}:{ref}", row)
    return out


def descendants(graph: dict[str, Any], node_ref: str) -> list[tuple[str, str, dict[str, Any], str | None]]:
    idx = node_index(graph)
    row = idx.get(node_ref)
    if not row:
        raise NarrativeControlError(f"unknown narrative node: {node_ref}", code="NODE_NOT_FOUND")
    children: list[tuple[str, str, dict[str, Any], str | None]] = []
    pending = [row[0]]
    while pending:
        parent = pending.pop(0)
        for candidate in idx.values():
            if candidate[3] == parent and candidate not in children:
                children.append(candidate)
                pending.append(candidate[0])
    return children


def ensure_graph_controls(graph: dict[str, Any]) -> dict[str, Any]:
    """Add v2 bookkeeping without changing creative fields."""
    graph.setdefault("schema_version", GRAPH_SCHEMA_VERSION)
    graph.setdefault("kind", "vertical-drama-graph")
    graph.setdefault("state", "draft")
    graph.setdefault("revision", 1)
    graph.setdefault("updated_at", utc_now())
    graph.setdefault("lock_scopes", [])
    if graph.get("state") not in CONTROL_STATES:
        graph["state"] = "draft"
    for _, _, node, _ in iter_nodes(graph):
        node["control"] = _control(node)
    graph["content_sha256"] = graph_content_sha256(graph)
    return graph


def bump_graph_revision(graph: dict[str, Any], *, reason: str = "edit") -> dict[str, Any]:
    ensure_graph_controls(graph)
    graph["revision"] = int(graph.get("revision") or 0) + 1
    graph["updated_at"] = utc_now()
    graph["revision_reason"] = reason
    graph["content_sha256"] = graph_content_sha256(graph)
    return graph


def _issue(code: str, message: str, *, node_ref: str | None = None, severity: str = "hard") -> dict[str, Any]:
    return {"code": code, "message": message, "node_ref": node_ref, "severity": severity}


def draft_director_board() -> dict[str, str]:
    """Return an explicit authoring checklist; placeholders never pass a lock."""
    return {**{field: "needs_authoring" for field in DIRECTOR_BOARD_FIELDS}, "approval_state": "draft"}


def validate_director_board(board: object, *, node_ref: str, require_approval: bool = False) -> list[dict[str, Any]]:
    if not isinstance(board, dict):
        return [_issue("DIRECTOR_BOARD_MISSING", "beat.director_board is required", node_ref=node_ref)]
    issues: list[dict[str, Any]] = []
    for field in DIRECTOR_BOARD_FIELDS:
        if not _nonempty(board.get(field)):
            issues.append(_issue("DIRECTOR_BOARD_FIELD_MISSING", f"director_board.{field} is required", node_ref=node_ref))
    approval = str(board.get("approval_state") or "draft").strip().lower()
    if approval not in DIRECTOR_BOARD_APPROVAL_STATES:
        issues.append(_issue("DIRECTOR_BOARD_APPROVAL_INVALID", "director_board.approval_state must be draft|review|approved", node_ref=node_ref))
    elif require_approval and approval != "approved":
        issues.append(_issue("DIRECTOR_BOARD_NOT_APPROVED", "director_board must be approved before beat lock", node_ref=node_ref))
    return issues


def validate_narrative_graph(graph: dict[str, Any], *, strict: bool = False) -> dict[str, Any]:
    """Validate narrative meaning in addition to graph shape."""
    issues: list[dict[str, Any]] = []
    canonical = int(graph.get("schema_version") or 0) >= GRAPH_SCHEMA_VERSION
    story = graph.get("story") if isinstance(graph.get("story"), dict) else {}

    if canonical:
        required_story = (
            "premise",
            "logline",
            "protagonist_goal",
            "opposition",
            "stakes",
            "climax_choice",
            "ending_hook",
        )
        for field in required_story:
            if not _nonempty(story.get(field)):
                issues.append(_issue("STORY_GOAL_MISSING" if field == "protagonist_goal" else "STORY_STAKES_MISSING" if field == "stakes" else "STORY_FIELD_MISSING", f"story.{field} is required", node_ref="story"))
        if not isinstance(story.get("emotional_arc"), list) or len(story.get("emotional_arc") or []) < 3:
            issues.append(_issue("STORY_ARC_MISSING", "story.emotional_arc requires at least 3 beats", node_ref="story"))

    seen_shots: set[str] = set()
    for ref, node_type, node, _ in iter_nodes(graph):
        if node_type == "shot":
            sid = str(node.get("id") or ref)
            if sid in seen_shots:
                issues.append(_issue("DUPLICATE_SHOT_ID", f"duplicate shot id: {sid}", node_ref=ref))
            seen_shots.add(sid)
            if canonical and not STABLE_SHOT_RE.match(sid):
                issues.append(_issue("UNSTABLE_NODE_ID", f"shot id must be stable hierarchy id: {sid}", node_ref=ref))
            if canonical:
                if not _nonempty(node.get("beat_id") or node.get("beatId")):
                    issues.append(_issue("SHOT_ORPHAN_BEAT", "shot must reference beat_id", node_ref=ref))
                for field in ("coverage_role", "must_show", "visible_change", "start_state", "end_state"):
                    if not _nonempty(node.get(field)):
                        code = "SHOT_MUST_SHOW_MISSING" if field == "must_show" else "SHOT_VISIBLE_CHANGE_MISSING" if field == "visible_change" else "SHOT_FIELD_MISSING"
                        issues.append(_issue(code, f"shot.{field} is required", node_ref=ref))
        elif canonical and node_type == "beat":
            for field, code in (
                ("objective", "BEAT_OBJECTIVE_MISSING"),
                ("obstacle", "BEAT_OBSTACLE_MISSING"),
                ("tactic", "BEAT_TACTIC_MISSING"),
                ("turn", "BEAT_NO_TURN"),
                ("outcome", "BEAT_OUTCOME_MISSING"),
                ("state_delta", "BEAT_STATE_DELTA_MISSING"),
            ):
                if not _nonempty(node.get(field)):
                    issues.append(_issue(code, f"beat.{field} is required", node_ref=ref))
            issues.extend(validate_director_board(node.get("director_board"), node_ref=ref, require_approval=strict))
        elif canonical and node_type == "scene":
            for field in ("purpose", "entry_state", "exit_state", "conflict"):
                if not _nonempty(node.get(field)):
                    issues.append(_issue("SCENE_FIELD_MISSING", f"scene.{field} is required", node_ref=ref))

    for _, _, scene, _ in iter_nodes(graph):
        if not isinstance(scene, dict) or not scene.get("beats"):
            continue
        for beat in scene.get("beats") or []:
            if not isinstance(beat, dict):
                continue
            shots = [s for s in beat.get("shots") or [] if isinstance(s, dict)]
            previous: str | None = None
            for shot in shots:
                action = str(shot.get("must_show") or shot.get("visible_change") or shot.get("action") or "").strip().lower()
                role = str(shot.get("coverage_role") or "")
                if action and previous == re.sub(r"\s+", " ", action) and role not in {"reaction", "hold"}:
                    issues.append(_issue("SHOT_DUPLICATE_ACTION", "adjacent shots repeat the same visual evidence", node_ref=str(shot.get("id"))))
                if action:
                    previous = re.sub(r"\s+", " ", action)

    hard = [item for item in issues if item.get("severity") == "hard"]
    return {
        "ok": not hard,
        "canonical": canonical,
        "strict": strict,
        "issues": issues,
        "errors": [item for item in issues if item.get("severity") == "hard"],
        "warnings": [item for item in issues if item.get("severity") != "hard"],
        "issue_codes": sorted({str(item.get("code")) for item in issues}),
    }


def projection_status(root: Path, graph: dict[str, Any] | None = None) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    graph = graph or (read_json(root / GRAPH_NAME) or {})
    if int(graph.get("schema_version") or 0) < GRAPH_SCHEMA_VERSION:
        return {"ok": True, "canonical": False, "stale": False, "reason": "legacy graph"}
    spec = read_json(root / "film-spec.json") or {}
    projection = spec.get(PROJECTION_KEY) if isinstance(spec.get(PROJECTION_KEY), dict) else {}
    expected = graph_content_sha256(graph)
    actual = str(projection.get("source_sha256") or "")
    return {
        "ok": bool(spec) and bool(actual) and actual == expected,
        "canonical": True,
        "stale": bool(spec) and actual != expected,
        "missing": not bool(spec),
        "expected_sha256": expected,
        "actual_sha256": actual or None,
        "source_revision": projection.get("source_revision"),
        "graph_revision": graph.get("revision"),
    }


def control_status(root: Path) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    graph = read_json(root / GRAPH_NAME) or {}
    if not graph:
        return {"ok": True, "exists": False, "canonical": False, "locked_scopes": [], "semantic": {"ok": True, "issues": []}, "projection": {"ok": True, "stale": False}}
    ensure_graph_controls(graph)
    semantic = validate_narrative_graph(graph)
    locked = list(graph.get("lock_scopes") or [])
    projection = projection_status(root, graph)
    ready = bool(semantic.get("ok")) and all(scope in locked for scope in LOCK_SCOPES) and bool(projection.get("ok"))
    return {
        "ok": ready,
        "exists": True,
        "canonical": int(graph.get("schema_version") or 0) >= GRAPH_SCHEMA_VERSION,
        "revision": graph.get("revision"),
        "content_sha256": graph.get("content_sha256") or graph_content_sha256(graph),
        "state": graph.get("state"),
        "locked_scopes": locked,
        "semantic": semantic,
        "projection": projection,
        "ready_for_media": ready,
    }


def assert_projection_ready(root: Path, *, require_locked: bool = True) -> dict[str, Any]:
    status = control_status(root)
    if not status.get("exists") or not status.get("canonical"):
        return status
    if require_locked and not status.get("ready_for_media"):
        projection = status.get("projection") or {}
        semantic = status.get("semantic") or {}
        if projection.get("stale"):
            raise NarrativeControlError("film-spec projection is stale; run aifilm graph project after locking", code="GRAPH_PROJECTION_STALE")
        if semantic.get("errors"):
            raise NarrativeControlError("narrative graph has semantic errors; run aifilm plan validate --strict", code="NARRATIVE_NOT_VALID")
        missing = [s for s in LOCK_SCOPES if s not in (status.get("locked_scopes") or [])]
        raise NarrativeControlError(f"narrative scopes not locked: {', '.join(missing)}", code="NARRATIVE_NOT_LOCKED")
    return status


def _scope_nodes(graph: dict[str, Any], scope: str) -> list[tuple[str, str, dict[str, Any], str | None]]:
    if scope not in LOCK_SCOPES:
        raise NarrativeControlError(f"unknown lock scope: {scope}", code="UNKNOWN_LOCK_SCOPE")
    wanted = {"story": {"story"}, "beats": {"beat"}, "shots": {"shot"}, "panels": {"panel"}}[scope]
    return [row for row in iter_nodes(graph) if row[1] in wanted]


def lock_scope(graph: dict[str, Any], scope: str, *, user_phrase: str) -> dict[str, Any]:
    if not str(user_phrase or "").strip():
        raise NarrativeControlError("lock requires a non-empty user phrase", code="USER_APPROVAL_REQUIRED")
    validation = validate_narrative_graph(graph, strict=True)
    scope_prefixes = {
        "story": ("STORY_",),
        "beats": ("BEAT_", "SCENE_", "DIRECTOR_BOARD_"),
        "shots": ("SHOT_", "UNSTABLE_NODE_ID", "DUPLICATE_SHOT_ID"),
        "panels": (),
    }
    scope_errors = [
        item for item in validation.get("errors") or []
        if any(str(item.get("code") or "").startswith(prefix) for prefix in scope_prefixes[scope])
    ]
    if scope_errors:
        raise NarrativeControlError("cannot lock graph with semantic errors", code="NARRATIVE_NOT_VALID")
    ensure_graph_controls(graph)
    for _, _, node, _ in _scope_nodes(graph, scope):
        c = _control(node)
        c["state"] = "locked"
        c["locked_fields"] = sorted(k for k in node if k not in {"control", "_film"})
        c["locked_at"] = utc_now()
        c["lock_reason"] = user_phrase.strip()
        node["control"] = c
    scopes = set(graph.get("lock_scopes") or [])
    scopes.add(scope)
    graph["lock_scopes"] = [s for s in LOCK_SCOPES if s in scopes]
    graph["state"] = "locked" if len(graph["lock_scopes"]) == len(LOCK_SCOPES) else "review"
    bump_graph_revision(graph, reason=f"lock:{scope}")
    return graph


def unlock_scope(graph: dict[str, Any], scope: str, *, reason: str) -> dict[str, Any]:
    if not str(reason or "").strip():
        raise NarrativeControlError("unlock requires a reason", code="UNLOCK_REASON_REQUIRED")
    ensure_graph_controls(graph)
    for _, _, node, _ in _scope_nodes(graph, scope):
        c = _control(node)
        c["state"] = "review"
        c["locked_fields"] = []
        c["lock_reason"] = reason.strip()
        node["control"] = c
    graph["lock_scopes"] = [s for s in graph.get("lock_scopes") or [] if s != scope]
    graph["state"] = "review"
    bump_graph_revision(graph, reason=f"unlock:{scope}")
    return graph


def _set_path(target: dict[str, Any], path: str, value: Any) -> None:
    parts = [p for p in str(path).split(".") if p]
    if not parts:
        raise NarrativeControlError("empty field path", code="INVALID_FIELD")
    cursor: dict[str, Any] = target
    for part in parts[:-1]:
        existing = cursor.get(part)
        if not isinstance(existing, dict):
            existing = {}
            cursor[part] = existing
        cursor = existing
    cursor[parts[-1]] = value


def edit_node(graph: dict[str, Any], node_ref: str, changes: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    row = node_index(graph).get(node_ref)
    if not row:
        raise NarrativeControlError(f"unknown narrative node: {node_ref}", code="NODE_NOT_FOUND")
    ref, _, node, _ = row
    c = _control(node)
    locked = set(c.get("locked_fields") or [])
    for field in changes:
        root_field = str(field).split(".", 1)[0]
        if c.get("state") == "locked" and (field in locked or root_field in locked):
            raise NarrativeControlError(f"node {ref} field {field} is locked", code="LOCKED_NODE_MUTATION")
        if field in {"id", "control"} or field.startswith("_"):
            raise NarrativeControlError(f"field cannot be edited: {field}", code="INVALID_FIELD")
    for field, value in changes.items():
        _set_path(node, field, value)
    _set_control(node, state="review", revision=int(c.get("revision") or 1) + 1)
    affected = [r[0] for r in descendants(graph, ref)]
    for child_ref, _, child, _ in descendants(graph, ref):
        _set_control(child, state="stale")
    graph["state"] = "review"
    bump_graph_revision(graph, reason=f"edit:{ref}")
    return graph, affected


def mark_replan(graph: dict[str, Any], node_ref: str) -> list[str]:
    """Invalidate a node subtree without deleting any generated media."""
    row = node_index(graph).get(node_ref)
    if not row:
        raise NarrativeControlError(f"unknown narrative node: {node_ref}", code="NODE_NOT_FOUND")
    affected_rows = [row] + descendants(graph, row[0])
    if any(_control(r[2]).get("state") == "locked" for r in affected_rows):
        raise NarrativeControlError("cannot replan locked node/subtree; unlock the scope first", code="LOCKED_NODE_MUTATION")
    affected = [r[0] for r in affected_rows]
    for _, _, node, _ in affected_rows:
        _set_control(node, state="stale")
    graph["state"] = "stale"
    bump_graph_revision(graph, reason=f"replan:{row[0]}")
    return affected


def graph_locked_for_projection(graph: dict[str, Any]) -> dict[str, Any]:
    ensure_graph_controls(graph)
    semantic = validate_narrative_graph(graph, strict=True)
    missing = [scope for scope in LOCK_SCOPES if scope not in (graph.get("lock_scopes") or [])]
    return {
        "ok": bool(semantic.get("ok")) and not missing,
        "semantic": semantic,
        "missing_scopes": missing,
    }


def write_revision_receipt(root: Path, graph: dict[str, Any], *, action: str, node_ref: str | None = None, affected: list[str] | None = None, reason: str | None = None) -> Path:
    root = Path(root).expanduser().resolve()
    path = root / "receipts" / "narrative" / f"revision-{int(graph.get('revision') or 1):04d}.json"
    write_json(path, {
        "ok": True,
        "action": action,
        "node_ref": node_ref,
        "affected_nodes": affected or [],
        "reason": reason,
        "revision": graph.get("revision"),
        "content_sha256": graph.get("content_sha256"),
        "at": utc_now(),
    })
    return path
