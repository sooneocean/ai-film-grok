"""No-spend planning autopilot: automates drafts, never human approvals."""

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from util import read_json, write_json


def authoring_questionnaire(graph: dict[str, Any]) -> list[dict[str, Any]]:
    """Prioritize causal story gaps before decorative shot detail."""
    from story_plan import _authoring_questions

    priorities = {
        "protagonist_goal": 1,
        "opposition": 1,
        "stakes": 1,
        "climax_choice": 1,
        "ending_hook": 1,
        "turn": 2,
        "outcome": 2,
        "state_delta": 2,
        "obstacle": 3,
        "tactic": 3,
    }
    rows = [
        dict(item, priority=priorities.get(str(item.get("field")), 4))
        for item in _authoring_questions(graph)
    ]
    return sorted(rows, key=lambda item: (item["priority"], item["node_ref"], item["field"]))


def minimal_authoring_batch(
    questionnaire: list[dict[str, Any]], *, limit: int = 5
) -> list[dict[str, Any]]:
    """Ask causality first; defer lower-risk beat tactics to later passes."""
    if not questionnaire:
        return []
    top_priority = min(int(item["priority"]) for item in questionnaire)
    first = [item for item in questionnaire if int(item["priority"]) == top_priority]
    return first[:limit]


def draft_readiness(questionnaire: list[dict[str, Any]]) -> dict[str, Any]:
    """A transparent draft-completeness score, not approval or quality judgment."""
    weights = {1: 5, 2: 3, 3: 1, 4: 1}
    missing_weight = sum(weights.get(int(item["priority"]), 1) for item in questionnaire)
    baseline = 25
    score = max(0, round(100 * (1 - missing_weight / baseline)))
    return {
        "score": score,
        "missing_weight": missing_weight,
        "ready_for_human_lock_review": not questionnaire,
        "note": "Measures unresolved authoring fields only; it does not approve story quality or production readiness.",
    }


def answer_transaction(answers: list[dict[str, Any]]) -> dict[str, str]:
    """Create a stable identity for one exact director-answer batch."""
    payload = json.dumps(answers, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    answer_sha256 = hashlib.sha256(payload).hexdigest()
    return {
        "answer_sha256": answer_sha256,
        "transaction_id": f"planning-answer-{answer_sha256[:16]}",
    }


def apply_authoring_answers(
    root: Path,
    answers: list[dict[str, Any]],
    *,
    dry_run: bool = False,
    expected_transaction_id: str | None = None,
) -> dict[str, Any]:
    """Apply only questionnaire fields through canonical graph edit semantics."""
    from narrative_control import edit_node, validate_narrative_graph

    transaction = answer_transaction(answers)
    if (
        expected_transaction_id is not None
        and expected_transaction_id != transaction["transaction_id"]
    ):
        raise ValueError("planning-answer transaction id does not match this answer batch")
    root = Path(root).expanduser().resolve()
    path = root / "drama-graph.json"
    graph = read_json(path)
    if not isinstance(graph, dict):
        raise ValueError("missing canonical drama-graph.json")
    before_questions = authoring_questionnaire(graph)
    before_readiness = draft_readiness(before_questions)
    allowed = {(row["node_ref"], row["field"]) for row in before_questions}
    original_revision = graph.get("revision")
    graph = deepcopy(graph)
    changed = []
    for answer in answers:
        ref, field, value = (
            str(answer.get("node_ref") or ""),
            str(answer.get("field") or ""),
            str(answer.get("value") or "").strip(),
        )
        if (ref, field) not in allowed or not value:
            raise ValueError(f"answer is not an open authoring field: {ref}.{field}")
        graph, _affected = edit_node(graph, ref, {field: value})
        changed.append({"node_ref": ref, "field": field})
    validation = validate_narrative_graph(graph)
    if not validation.get("ok") and not dry_run:
        raise ValueError(
            "planning-answer transaction rejected: batch leaves narrative graph invalid"
        )
    if not dry_run:
        write_json(path, graph)
    remaining_questions = authoring_questionnaire(graph)
    remaining_readiness = draft_readiness(remaining_questions)
    result = {
        "ok": bool(validation.get("ok")),
        "changed": changed,
        "dry_run": dry_run,
        "atomic": True,
        **transaction,
        "expected_transaction_id": expected_transaction_id,
        "transaction_verified": expected_transaction_id is not None,
        "would_mark_stale": bool(changed),
        "original_revision": original_revision,
        "readiness_before": before_readiness,
        "readiness_after": remaining_readiness,
        "readiness_delta": remaining_readiness["score"] - before_readiness["score"],
        "remaining_high_priority": minimal_authoring_batch(remaining_questions),
        "state": graph.get("state"),
        "revision": graph.get("revision"),
        "validate": validation,
        "note": "Answers update draft/review graph only; projection and locks remain invalid until explicit human review.",
    }
    if not dry_run:
        history_path = root / "receipts" / "planning-history.json"
        history = read_json(history_path) or {
            "schema_version": 1,
            "kind": "planning-history",
            "entries": [],
        }
        history.setdefault("entries", []).append(
            {
                "at": datetime.now(UTC).replace(microsecond=0).isoformat(),
                "action": "planning-answer",
                **transaction,
                "transaction_verified": expected_transaction_id is not None,
                "changed": changed,
                "revision": result["revision"],
                "readiness_before": before_readiness,
                "readiness_after": remaining_readiness,
                "readiness_delta": result["readiness_delta"],
            }
        )
        write_json(history_path, history)
        result["planning_history_path"] = str(history_path)
    return result


def planning_history_summary(root: Path) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    history = read_json(root / "receipts" / "planning-history.json") or {}
    entries = [item for item in history.get("entries") or [] if isinstance(item, dict)]
    scores = [int((item.get("readiness_after") or {}).get("score") or 0) for item in entries]
    stalled = 0
    for item in reversed(entries):
        if int(item.get("readiness_delta") or 0) > 0:
            break
        stalled += 1
    graph = read_json(root / "drama-graph.json") or {}
    questions = authoring_questionnaire(graph) if graph else []
    if not entries:
        diagnosis = "NO_FORMAL_ANSWERS"
    elif stalled and questions and int(questions[0]["priority"]) == 1:
        diagnosis = "CORE_CAUSALITY_STILL_MISSING"
    elif stalled:
        diagnosis = "ANSWERS_DID_NOT_REDUCE_OPEN_FIELDS"
    else:
        diagnosis = "PROGRESSING"
    core_fields = {"protagonist_goal", "opposition", "stakes", "climax_choice", "ending_hook"}
    template_rows = (
        [item for item in questions if item["field"] in core_fields]
        if diagnosis == "CORE_CAUSALITY_STILL_MISSING"
        else minimal_authoring_batch(questions)
    )
    answer_template = [
        {"node_ref": item["node_ref"], "field": item["field"], "value": "<director answer>"}
        for item in template_rows
    ]
    return {
        "ok": True,
        "entry_count": len(entries),
        "readiness_curve": scores,
        "stalled_rounds": stalled,
        "stalled_diagnosis": diagnosis,
        "current_high_priority": minimal_authoring_batch(questions),
        "recommended_answer_template": answer_template,
        "recommended_dry_run": (
            f'aifilm planning-answer --root "{root}" --dry-run --answers-json '
            + json.dumps(answer_template, ensure_ascii=False)
            if answer_template
            else None
        ),
        "history_path": str(root / "receipts" / "planning-history.json"),
    }


def build_planning_autopilot(root: Path, *, write: bool = True) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    graph = read_json(root / "drama-graph.json") or {}
    has_graph = bool(graph)
    status = (graph.get("story") or {}).get("status") if has_graph else "missing"
    automatic = (
        [f'aifilm plan run --root "{root}" --text <premise>']
        if not has_graph
        else [f'aifilm graph validate --root "{root}"', f'aifilm graph status --root "{root}"']
    )
    checkpoints = [
        "导演补写主角目标、阻力、代价、选择与结尾问题",
        "人工锁定 narrative graph / film-spec",
        "人工批准关键帧、Pilot 与最终成片",
    ]
    questionnaire = authoring_questionnaire(graph) if has_graph else []
    batch = minimal_authoring_batch(questionnaire)
    readiness = draft_readiness(questionnaire)
    answer_template = [
        {"node_ref": item["node_ref"], "field": item["field"], "value": "<director answer>"}
        for item in batch
    ]
    report = {
        "schema_version": 1,
        "kind": "planning-autopilot",
        "mode": "draft_automation_only",
        "graph_present": has_graph,
        "story_status": status,
        "automatic_steps": automatic,
        "human_checkpoints": checkpoints,
        "authoring_questionnaire": questionnaire,
        "needs_authoring_count": len(questionnaire),
        "minimal_authoring_batch": batch,
        "deferred_authoring_count": max(0, len(questionnaire) - len(batch)),
        "draft_readiness": readiness,
        "planning_answer_template": answer_template,
        "planning_answer_dry_run": (
            f'aifilm planning-answer --root "{root}" --dry-run --answers-json '
            + json.dumps(answer_template, ensure_ascii=False)
            if answer_template
            else None
        ),
        "blocked_actions": [
            "no automatic graph lock",
            "no automatic pilot approval",
            "no paid media generation",
        ],
        "ready_for_projection": status == "locked",
    }
    if write:
        path = root / "receipts" / "planning-autopilot.json"
        write_json(path, report)
        report["path"] = str(path)
    return report
