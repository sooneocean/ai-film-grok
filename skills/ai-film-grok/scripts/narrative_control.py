#!/usr/bin/env python3
"""Narrative control plane for the canonical vertical-drama graph.

The module is deliberately provider-free.  It owns narrative revisions,
node-level locks, semantic validation, stale propagation, and the hash that
binds a canonical graph to its executable film-spec projection.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
PLOT_POINT_STATUSES = frozenset({"planted", "carried", "paid_off", "season_hook"})
PLOT_POINT_TYPES = frozenset(
    {"character_secret", "prop_clue", "relationship_promise", "danger_omen", "world_info", "custom"}
)
PLACEHOLDER_RE = re.compile(
    r"^(?:todo|tbd|needs_authoring|待补|待定|待填写|冲突顶点|余韵与续集钩子|advance story)$",
    re.IGNORECASE,
)
GENERIC_HOOK_RE = re.compile(
    r"^(?:敬请期待|事情还没有结束|未完待续|to be continued|stay tuned)[。！! ]*$", re.I
)


class NarrativeControlError(ValueError):
    """A fail-closed narrative control error with a stable reason code."""

    def __init__(self, message: str, *, code: str = "NARRATIVE_CONTROL") -> None:
        super().__init__(message)
        self.code = code


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _nonempty(value: Any) -> bool:
    return (
        isinstance(value, str) and bool(value.strip()) and not PLACEHOLDER_RE.match(value.strip())
    )


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


def iter_nodes(
    graph: dict[str, Any], *, normalize: bool = True
) -> Iterable[tuple[str, str, dict[str, Any], str | None]]:
    """Yield (node_ref, node_type, node, parent_ref) in stable tree order.

    When ``normalize=True`` (default), a deep-copied normalized copy is
    traversed — safe for read-only consumers but writes to ``node`` are
    discarded. Pass ``normalize=False`` when you need to mutate nodes in place
    (e.g. ensure_graph_controls, node_index for descendants writes).
    """
    # Local import avoids the story_plan ↔ narrative_control module cycle.
    from story_plan import normalize_story_graph

    if normalize:
        graph = normalize_story_graph(graph)
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
    # normalize=False: keep original node refs so descendants() callers
    # (edit_node, mark_replan) mutate the real graph, not a deepcopy.
    for row in iter_nodes(graph, normalize=False):
        ref, node_type, node, parent = row
        out[ref] = row
        out.setdefault(f"{node_type}:{ref}", row)
    return out


def descendants(
    graph: dict[str, Any], node_ref: str
) -> list[tuple[str, str, dict[str, Any], str | None]]:
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
    # normalize=False: write control into the ORIGINAL graph nodes, not the
    # deepcopy that normalize_story_graph produces (writing to the copy
    # silently discards the control field, causing KeyError in callers).
    for _, _, node, _ in iter_nodes(graph, normalize=False):
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


def _issue(
    code: str, message: str, *, node_ref: str | None = None, severity: str = "hard"
) -> dict[str, Any]:
    return {"code": code, "message": message, "node_ref": node_ref, "severity": severity}


def draft_director_board() -> dict[str, str]:
    """Return an explicit authoring checklist; placeholders never pass a lock."""
    return {
        **{field: "needs_authoring" for field in DIRECTOR_BOARD_FIELDS},
        "approval_state": "draft",
    }


def validate_director_board(
    board: object, *, node_ref: str, require_approval: bool = False
) -> list[dict[str, Any]]:
    if not isinstance(board, dict):
        return [
            _issue("DIRECTOR_BOARD_MISSING", "beat.director_board is required", node_ref=node_ref)
        ]
    issues: list[dict[str, Any]] = []
    for field in DIRECTOR_BOARD_FIELDS:
        if not _nonempty(board.get(field)):
            issues.append(
                _issue(
                    "DIRECTOR_BOARD_FIELD_MISSING",
                    f"director_board.{field} is required",
                    node_ref=node_ref,
                )
            )
    approval = str(board.get("approval_state") or "draft").strip().lower()
    if approval not in DIRECTOR_BOARD_APPROVAL_STATES:
        issues.append(
            _issue(
                "DIRECTOR_BOARD_APPROVAL_INVALID",
                "director_board.approval_state must be draft|review|approved",
                node_ref=node_ref,
            )
        )
    elif require_approval and approval != "approved":
        issues.append(
            _issue(
                "DIRECTOR_BOARD_NOT_APPROVED",
                "director_board must be approved before beat lock",
                node_ref=node_ref,
            )
        )
    return issues


def _episode_tree(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(ep.get("id")): ep
        for ep in graph.get("episodes") or []
        if isinstance(ep, dict) and ep.get("id")
    }


def _episode_refs(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index episode-local beat and shot ids for hook/point evidence checks."""
    out: dict[str, dict[str, Any]] = {}
    for ep in graph.get("episodes") or []:
        if not isinstance(ep, dict) or not ep.get("id"):
            continue
        beats: set[str] = set()
        shots: set[str] = set()
        shot_to_beat: dict[str, str] = {}
        for scene in ep.get("scenes") or []:
            if not isinstance(scene, dict):
                continue
            for beat in scene.get("beats") or []:
                if not isinstance(beat, dict):
                    continue
                if beat.get("id"):
                    beats.add(str(beat["id"]))
                for shot in beat.get("shots") or []:
                    if isinstance(shot, dict) and shot.get("id"):
                        shot_id = str(shot["id"])
                        shots.add(shot_id)
                        shot_to_beat[shot_id] = str(beat["id"])
        out[str(ep["id"])] = {"beats": beats, "shots": shots, "shot_to_beat": shot_to_beat}
    return out


def _hook_issues(
    hook: object,
    *,
    code: str,
    episode_id: str,
    refs: dict[str, Any],
    points: dict[str, dict[str, Any]],
    require_unresolved: bool = False,
) -> list[dict[str, Any]]:
    if not isinstance(hook, dict) or not _nonempty(hook.get("question")):
        return [
            _issue(
                code,
                f"episode {episode_id} hook requires a non-empty question",
                node_ref=episode_id,
            )
        ]
    issues: list[dict[str, Any]] = []
    if GENERIC_HOOK_RE.match(str(hook.get("question") or "").strip()):
        issues = [
            _issue(
                "HOOK_QUESTION_GENERIC",
                f"hook question must name a concrete unresolved question: {episode_id}",
                node_ref=episode_id,
            )
        ]
    if not hook.get("source_refs") or not _nonempty(hook.get("visible_evidence")):
        issues.append(
            _issue(
                "PLOT_POINT_NO_EVIDENCE",
                f"hook requires source_refs and visible_evidence: {episode_id}",
                node_ref=episode_id,
            )
        )
    point_id = str(hook.get("point_id") or "")
    beat_id = str(hook.get("beat_id") or "")
    shot_ids = {str(x) for x in hook.get("shot_ids") or [] if str(x).strip()}
    if not point_id or point_id not in points:
        issues.append(
            _issue(
                "PLOT_POINT_ORPHAN",
                f"hook references unknown point: {point_id}",
                node_ref=episode_id,
            )
        )
    local_shots = shot_ids.intersection(refs["shots"])
    if beat_id not in refs["beats"] or not local_shots:
        issues.append(
            _issue(
                "PLOT_POINT_NO_EVIDENCE",
                f"hook has no local beat/shot evidence: {episode_id}",
                node_ref=episode_id,
            )
        )
    elif not any(refs.get("shot_to_beat", {}).get(shot_id) == beat_id for shot_id in local_shots):
        issues.append(
            _issue(
                "PLOT_POINT_NO_EVIDENCE",
                f"hook shot evidence is not bound to hook beat: {episode_id}",
                node_ref=episode_id,
            )
        )
    if point_id in points and str(points[point_id].get("introduced_episode") or "") != episode_id:
        issues.append(
            _issue(
                "PLOT_POINT_ORPHAN",
                f"hook point is not introduced in episode: {point_id}",
                node_ref=episode_id,
            )
        )
    if require_unresolved and point_id in points and points[point_id].get("status") == "paid_off":
        payoff = points[point_id].get("payoff_evidence") or {}
        try:
            paid_in = int(str(payoff.get("episode") or "").removeprefix("ep"))
            current = int(str(episode_id).removeprefix("ep"))
        except (TypeError, ValueError):
            paid_in = current = 0
        if not paid_in or paid_in <= current:
            issues.append(
                _issue(
                    "ENDING_HOOK_ALREADY_PAID",
                    f"ending hook point is already paid off: {point_id}",
                    node_ref=episode_id,
                )
            )
    return issues


def validate_narrative_contract(
    graph: dict[str, Any], *, strict: bool = False
) -> list[dict[str, Any]]:
    """Validate cross-episode promises, hooks, and their shot-level evidence."""
    if not strict:
        return []
    episodes = _episode_tree(graph)
    refs_by_ep = _episode_refs(graph)
    raw_points = graph.get("plot_points")
    points_list = raw_points if isinstance(raw_points, list) else []
    points: dict[str, dict[str, Any]] = {
        str(item.get("point_id")): item
        for item in points_list
        if isinstance(item, dict) and item.get("point_id")
    }
    issues: list[dict[str, Any]] = []
    if not points:
        issues.append(
            _issue(
                "PLOT_POINT_ORPHAN",
                "graph.plot_points must contain at least one tracked point",
                node_ref="graph",
            )
        )

    for point_id, point in points.items():
        intro_ep = str(point.get("introduced_episode") or "")
        refs = refs_by_ep.get(intro_ep, {"beats": set(), "shots": set()})
        intro_beat = str(point.get("introduced_beat_id") or "")
        intro_shots = {str(x) for x in point.get("introduced_shot_ids") or [] if str(x).strip()}
        if (
            intro_ep not in episodes
            or intro_beat not in refs["beats"]
            or not intro_shots.intersection(refs["shots"])
            or not any(
                refs.get("shot_to_beat", {}).get(shot_id) == intro_beat
                for shot_id in intro_shots.intersection(refs["shots"])
            )
        ):
            issues.append(
                _issue(
                    "PLOT_POINT_ORPHAN",
                    f"point has invalid introduction evidence: {point_id}",
                    node_ref=point_id,
                )
            )
        if not point.get("source_refs"):
            issues.append(
                _issue(
                    "PLOT_POINT_NO_SOURCE",
                    f"point has no source_refs: {point_id}",
                    node_ref=point_id,
                )
            )
        point_type = str(point.get("point_type") or "")
        if point_type not in PLOT_POINT_TYPES:
            issues.append(
                _issue(
                    "PLOT_POINT_TYPE_INVALID", f"invalid point type: {point_id}", node_ref=point_id
                )
            )
        if "authoring_status" in point and point.get("authoring_status") != "confirmed":
            issues.append(
                _issue(
                    "PLOT_POINT_NOT_CONFIRMED",
                    f"point requires author confirmation: {point_id}",
                    node_ref=point_id,
                )
            )
        if "confidence" in point:
            try:
                confidence = float(point.get("confidence"))
                if not 0 <= confidence <= 1:
                    raise ValueError
            except (TypeError, ValueError):
                issues.append(
                    _issue(
                        "PLOT_POINT_CONFIDENCE_INVALID",
                        f"invalid confidence: {point_id}",
                        node_ref=point_id,
                    )
                )
        if not _nonempty(point.get("source_excerpt")):
            issues.append(
                _issue(
                    "PLOT_POINT_SOURCE_EXCERPT_MISSING",
                    f"point.source_excerpt is required: {point_id}",
                    node_ref=point_id,
                )
            )
        for field in ("visible_evidence", "audience_question"):
            if not _nonempty(point.get(field)):
                issues.append(
                    _issue(
                        "PLOT_POINT_NO_EVIDENCE"
                        if field == "visible_evidence"
                        else "PLOT_POINT_FIELD_MISSING",
                        f"point.{field} is required: {point_id}",
                        node_ref=point_id,
                    )
                )
        status = str(point.get("status") or "")
        if status not in PLOT_POINT_STATUSES:
            issues.append(
                _issue(
                    "PLOT_POINT_STATUS_INVALID",
                    f"invalid point status: {point_id}",
                    node_ref=point_id,
                )
            )
        try:
            intro_no = int(str(intro_ep).removeprefix("ep"))
            payoff_no = int(point.get("planned_payoff_episode"))
        except (TypeError, ValueError):
            intro_no = payoff_no = 0
            issues.append(
                _issue(
                    "PLOT_POINT_NO_PAYOFF_PLAN",
                    f"point has no valid payoff episode: {point_id}",
                    node_ref=point_id,
                )
            )
        if payoff_no and payoff_no < intro_no:
            issues.append(
                _issue(
                    "PAYOFF_BEFORE_SETUP",
                    f"payoff precedes introduction: {point_id}",
                    node_ref=point_id,
                )
            )
        if payoff_no and payoff_no > intro_no + 3 and status != "season_hook":
            issues.append(
                _issue(
                    "PAYOFF_WINDOW_EXCEEDED",
                    f"payoff exceeds three-episode window: {point_id}",
                    node_ref=point_id,
                )
            )
        if status == "paid_off":
            payoff = (
                point.get("payoff_evidence")
                if isinstance(point.get("payoff_evidence"), dict)
                else {}
            )
            if (
                not payoff.get("episode")
                or not payoff.get("beat_id")
                or not payoff.get("shot_ids")
                or not _nonempty(payoff.get("visible_change"))
            ):
                issues.append(
                    _issue(
                        "PAYOFF_EVIDENCE_MISSING",
                        f"paid_off point needs payoff evidence: {point_id}",
                        node_ref=point_id,
                    )
                )
            else:
                payoff_refs = refs_by_ep.get(
                    str(payoff.get("episode")), {"beats": set(), "shots": set()}
                )
                if str(payoff.get("beat_id")) not in payoff_refs["beats"] or not set(
                    map(str, payoff.get("shot_ids") or [])
                ).intersection(payoff_refs["shots"]):
                    issues.append(
                        _issue(
                            "PAYOFF_EVIDENCE_ORPHAN",
                            f"payoff evidence is not bound to a real shot: {point_id}",
                            node_ref=point_id,
                        )
                    )

    for index, (episode_id, episode) in enumerate(episodes.items()):
        refs = refs_by_ep.get(episode_id, {"beats": set(), "shots": set()})
        contract = episode
        issues.extend(
            _hook_issues(
                contract.get("opening_hook"),
                code="EPISODE_OPENING_HOOK_MISSING",
                episode_id=episode_id,
                refs=refs,
                points=points,
            )
        )
        issues.extend(
            _hook_issues(
                contract.get("ending_hook"),
                code="EPISODE_ENDING_HOOK_MISSING",
                episode_id=episode_id,
                refs=refs,
                points=points,
                require_unresolved=True,
            )
        )
        if not isinstance(contract.get("mid_episode_points"), list) or not contract.get(
            "mid_episode_points"
        ):
            issues.append(
                _issue(
                    "EPISODE_MIDPOINT_POINT_MISSING",
                    f"episode has no midpoint plot point: {episode_id}",
                    node_ref=episode_id,
                )
            )
        for point_id in contract.get("mid_episode_points") or []:
            point = points.get(str(point_id))
            if not point or str(point.get("introduced_episode")) != episode_id:
                issues.append(
                    _issue(
                        "PLOT_POINT_ORPHAN",
                        f"midpoint point is not introduced in episode: {point_id}",
                        node_ref=episode_id,
                    )
                )
        if not _nonempty(contract.get("new_audience_question")):
            issues.append(
                _issue(
                    "ENDING_HOOK_EMPTY_QUESTION",
                    f"episode has no new audience question: {episode_id}",
                    node_ref=episode_id,
                )
            )
        elif GENERIC_HOOK_RE.match(str(contract.get("new_audience_question") or "").strip()):
            issues.append(
                _issue(
                    "HOOK_QUESTION_GENERIC",
                    f"episode question must be concrete: {episode_id}",
                    node_ref=episode_id,
                )
            )
        for relation_name in ("carry_in_points", "payoff_points"):
            for point_id in contract.get(relation_name) or []:
                if str(point_id) not in points:
                    issues.append(
                        _issue(
                            "PLOT_POINT_ORPHAN",
                            f"{relation_name} references unknown point: {point_id}",
                            node_ref=episode_id,
                        )
                    )
        if index > 0:
            previous_id = list(episodes)[index - 1]
            previous = episodes[previous_id]
            previous_hook = previous.get("ending_hook") if isinstance(previous, dict) else {}
            carry = {str(x) for x in contract.get("carry_in_points") or []}
            payoff = {str(x) for x in contract.get("payoff_points") or []}
            previous_point = str((previous_hook or {}).get("point_id") or "")
            if previous_point and previous_point not in carry:
                issues.append(
                    _issue(
                        "HOOK_NOT_CARRIED_FORWARD",
                        f"episode does not carry prior ending hook: {episode_id}",
                        node_ref=episode_id,
                    )
                )
            if previous_point and previous_point not in payoff:
                issues.append(
                    _issue(
                        "HOOK_NOT_PAID_OFF",
                        f"episode does not respond to prior ending hook: {episode_id}",
                        node_ref=episode_id,
                    )
                )
        for point_id in contract.get("payoff_points") or []:
            point = points.get(str(point_id))
            if not point:
                issues.append(
                    _issue(
                        "PLOT_POINT_ORPHAN",
                        f"payoff references unknown point: {point_id}",
                        node_ref=episode_id,
                    )
                )
                continue
            if point.get("status") not in {"paid_off", "season_hook"}:
                issues.append(
                    _issue(
                        "PAYOFF_STATUS_INVALID",
                        f"payoff point is not marked paid_off: {point_id}",
                        node_ref=episode_id,
                    )
                )
            payoff_evidence = (
                point.get("payoff_evidence")
                if isinstance(point.get("payoff_evidence"), dict)
                else {}
            )
            if str(payoff_evidence.get("episode") or "") != episode_id:
                issues.append(
                    _issue(
                        "PAYOFF_EVIDENCE_MISMATCH",
                        f"payoff evidence does not match episode: {point_id}",
                        node_ref=episode_id,
                    )
                )
            payoff_refs = refs_by_ep.get(
                episode_id, {"beats": set(), "shots": set(), "shot_to_beat": {}}
            )
            payoff_shots = {str(x) for x in payoff_evidence.get("shot_ids") or []}
            if str(payoff_evidence.get("beat_id") or "") not in payoff_refs["beats"] or not any(
                payoff_refs.get("shot_to_beat", {}).get(shot_id)
                == str(payoff_evidence.get("beat_id"))
                for shot_id in payoff_shots
            ):
                issues.append(
                    _issue(
                        "PAYOFF_EVIDENCE_ORPHAN",
                        f"payoff evidence is not bound to its beat: {point_id}",
                        node_ref=episode_id,
                    )
                )
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
                issues.append(
                    _issue(
                        "STORY_GOAL_MISSING"
                        if field == "protagonist_goal"
                        else "STORY_STAKES_MISSING"
                        if field == "stakes"
                        else "STORY_FIELD_MISSING",
                        f"story.{field} is required",
                        node_ref="story",
                    )
                )
        if (
            not isinstance(story.get("emotional_arc"), list)
            or len(story.get("emotional_arc") or []) < 3
        ):
            issues.append(
                _issue(
                    "STORY_ARC_MISSING",
                    "story.emotional_arc requires at least 3 beats",
                    node_ref="story",
                )
            )

    seen_shots: set[str] = set()
    for ref, node_type, node, _ in iter_nodes(graph):
        if node_type == "shot":
            sid = str(node.get("id") or ref)
            if sid in seen_shots:
                issues.append(
                    _issue("DUPLICATE_SHOT_ID", f"duplicate shot id: {sid}", node_ref=ref)
                )
            seen_shots.add(sid)
            if canonical and not STABLE_SHOT_RE.match(sid):
                issues.append(
                    _issue(
                        "UNSTABLE_NODE_ID",
                        f"shot id must be stable hierarchy id: {sid}",
                        node_ref=ref,
                    )
                )
            if canonical:
                if not _nonempty(node.get("beat_id") or node.get("beatId")):
                    issues.append(
                        _issue("SHOT_ORPHAN_BEAT", "shot must reference beat_id", node_ref=ref)
                    )
                for field in (
                    "coverage_role",
                    "must_show",
                    "visible_change",
                    "start_state",
                    "end_state",
                    "playable_action",
                    "expectation",
                    "subtext",
                    "gaze_target",
                    "reaction_trigger",
                    "body_state",
                ):
                    if not _nonempty(node.get(field)):
                        code = (
                            "SHOT_MUST_SHOW_MISSING"
                            if field == "must_show"
                            else "SHOT_VISIBLE_CHANGE_MISSING"
                            if field == "visible_change"
                            else "SHOT_PERFORMANCE_MISSING"
                            if field
                            in {
                                "playable_action",
                                "expectation",
                                "subtext",
                                "gaze_target",
                                "reaction_trigger",
                                "body_state",
                            }
                            else "SHOT_FIELD_MISSING"
                        )
                        issues.append(_issue(code, f"shot.{field} is required", node_ref=ref))
        elif canonical and node_type == "beat":
            for field, code in (
                ("objective", "BEAT_OBJECTIVE_MISSING"),
                ("obstacle", "BEAT_OBSTACLE_MISSING"),
                ("tactic", "BEAT_TACTIC_MISSING"),
                ("turn", "BEAT_NO_TURN"),
                ("outcome", "BEAT_OUTCOME_MISSING"),
                ("state_delta", "BEAT_STATE_DELTA_MISSING"),
                ("audience_question", "BEAT_AUDIENCE_QUESTION_MISSING"),
                ("emotional_turn", "BEAT_EMOTIONAL_TURN_MISSING"),
            ):
                if not _nonempty(node.get(field)):
                    issues.append(_issue(code, f"beat.{field} is required", node_ref=ref))
            issues.extend(
                validate_director_board(
                    node.get("director_board"), node_ref=ref, require_approval=strict
                )
            )
        elif canonical and node_type == "scene":
            for field in ("purpose", "entry_state", "exit_state", "conflict"):
                if not _nonempty(node.get(field)):
                    issues.append(
                        _issue("SCENE_FIELD_MISSING", f"scene.{field} is required", node_ref=ref)
                    )

    for _, _, scene, _ in iter_nodes(graph):
        if not isinstance(scene, dict) or not scene.get("beats"):
            continue
        for beat in scene.get("beats") or []:
            if not isinstance(beat, dict):
                continue
            shots = [s for s in beat.get("shots") or [] if isinstance(s, dict)]
            previous: str | None = None
            for shot in shots:
                action = (
                    str(
                        shot.get("must_show")
                        or shot.get("visible_change")
                        or shot.get("action")
                        or ""
                    )
                    .strip()
                    .lower()
                )
                role = str(shot.get("coverage_role") or "")
                if (
                    action
                    and previous == re.sub(r"\s+", " ", action)
                    and role not in {"reaction", "hold"}
                ):
                    issues.append(
                        _issue(
                            "SHOT_DUPLICATE_ACTION",
                            "adjacent shots repeat the same visual evidence",
                            node_ref=str(shot.get("id")),
                        )
                    )
                if action:
                    previous = re.sub(r"\s+", " ", action)

    issues.extend(validate_narrative_contract(graph, strict=strict))

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
        return {
            "ok": True,
            "exists": False,
            "canonical": False,
            "locked_scopes": [],
            "semantic": {"ok": True, "issues": []},
            "projection": {"ok": True, "stale": False},
        }
    ensure_graph_controls(graph)
    semantic = validate_narrative_graph(graph)
    locked = list(graph.get("lock_scopes") or [])
    projection = projection_status(root, graph)
    ready = (
        bool(semantic.get("ok"))
        and all(scope in locked for scope in LOCK_SCOPES)
        and bool(projection.get("ok"))
    )
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
            raise NarrativeControlError(
                "film-spec projection is stale; run aifilm graph project after locking",
                code="GRAPH_PROJECTION_STALE",
            )
        if semantic.get("errors"):
            raise NarrativeControlError(
                "narrative graph has semantic errors; run aifilm plan validate --strict",
                code="NARRATIVE_NOT_VALID",
            )
        missing = [s for s in LOCK_SCOPES if s not in (status.get("locked_scopes") or [])]
        raise NarrativeControlError(
            f"narrative scopes not locked: {', '.join(missing)}", code="NARRATIVE_NOT_LOCKED"
        )
    return status


def _scope_nodes(
    graph: dict[str, Any], scope: str
) -> list[tuple[str, str, dict[str, Any], str | None]]:
    if scope not in LOCK_SCOPES:
        raise NarrativeControlError(f"unknown lock scope: {scope}", code="UNKNOWN_LOCK_SCOPE")
    wanted = {"story": {"story"}, "beats": {"beat"}, "shots": {"shot"}, "panels": {"panel"}}[scope]
    # normalize=False: lock_scope writes locked state into the real nodes.
    return [row for row in iter_nodes(graph, normalize=False) if row[1] in wanted]


def lock_scope(graph: dict[str, Any], scope: str, *, user_phrase: str) -> dict[str, Any]:
    if not str(user_phrase or "").strip():
        raise NarrativeControlError(
            "lock requires a non-empty user phrase", code="USER_APPROVAL_REQUIRED"
        )
    validation = validate_narrative_graph(graph, strict=True)
    scope_prefixes = {
        "story": ("STORY_",),
        "beats": ("BEAT_", "SCENE_", "DIRECTOR_BOARD_"),
        "shots": ("SHOT_", "UNSTABLE_NODE_ID", "DUPLICATE_SHOT_ID"),
        "panels": (),
    }
    scope_errors = [
        item
        for item in validation.get("errors") or []
        if any(str(item.get("code") or "").startswith(prefix) for prefix in scope_prefixes[scope])
    ]
    if scope_errors:
        raise NarrativeControlError(
            "cannot lock graph with semantic errors", code="NARRATIVE_NOT_VALID"
        )
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


def edit_node(
    graph: dict[str, Any], node_ref: str, changes: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    row = node_index(graph).get(node_ref)
    if not row:
        raise NarrativeControlError(f"unknown narrative node: {node_ref}", code="NODE_NOT_FOUND")
    ref, _, node, _ = row
    c = _control(node)
    locked = set(c.get("locked_fields") or [])
    for field in changes:
        root_field = str(field).split(".", 1)[0]
        if c.get("state") == "locked" and (field in locked or root_field in locked):
            raise NarrativeControlError(
                f"node {ref} field {field} is locked", code="LOCKED_NODE_MUTATION"
            )
        if field in {"id", "control"} or field.startswith("_"):
            raise NarrativeControlError(f"field cannot be edited: {field}", code="INVALID_FIELD")
    for field, value in changes.items():
        _set_path(node, field, value)
    _set_control(node, state="review", revision=int(c.get("revision") or 1) + 1)
    affected = [r[0] for r in descendants(graph, ref)]
    for _child_ref, _, child, _ in descendants(graph, ref):
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
        raise NarrativeControlError(
            "cannot replan locked node/subtree; unlock the scope first", code="LOCKED_NODE_MUTATION"
        )
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


def write_revision_receipt(
    root: Path,
    graph: dict[str, Any],
    *,
    action: str,
    node_ref: str | None = None,
    affected: list[str] | None = None,
    reason: str | None = None,
) -> Path:
    root = Path(root).expanduser().resolve()
    path = root / "receipts" / "narrative" / f"revision-{int(graph.get('revision') or 1):04d}.json"
    write_json(
        path,
        {
            "ok": True,
            "action": action,
            "node_ref": node_ref,
            "affected_nodes": affected or [],
            "reason": reason,
            "revision": graph.get("revision"),
            "content_sha256": graph.get("content_sha256"),
            "at": utc_now(),
        },
    )
    return path
