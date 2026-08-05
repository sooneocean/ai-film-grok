"""Transactional planning mutations and their revision receipts."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from typing import Any

from drama_graph import GRAPH_NAME
from narrative_control import (
    NarrativeControlError,
    edit_node,
    lock_scope,
    mark_replan,
    unlock_scope,
    write_revision_receipt,
)
from util import read_json, write_json


class PlanMutationError(RuntimeError):
    """A user-correctable planning mutation failure."""

    def __init__(self, message: str, code: str = "PLAN_MUTATION_FAILED") -> None:
        super().__init__(message)
        self.code = code


def run(args: Namespace, root: Path) -> tuple[dict[str, Any], int]:
    action = str(args.plan_action)
    graph_path = root / GRAPH_NAME
    graph = read_json(graph_path)
    if not graph:
        raise PlanMutationError(
            f"missing {graph_path} — run: aifilm plan run --root …", "GRAPH_MISSING"
        )
    try:
        if action == "edit":
            changes: dict[str, Any] = {}
            for item in list(getattr(args, "set", None) or []):
                if "=" not in item:
                    raise PlanMutationError(f"--set requires field=value: {item}", "INVALID_FIELD")
                field, raw_value = item.split("=", 1)
                try:
                    value: Any = json.loads(raw_value)
                except json.JSONDecodeError:
                    value = raw_value
                if str(getattr(args, "node", "")) == "story" and field.startswith("story."):
                    field = field.split(".", 1)[1]
                changes[field] = value
            graph, affected = edit_node(graph, str(args.node), changes)
            write_json(graph_path, graph)
            receipt = write_revision_receipt(
                root, graph, action="edit", node_ref=str(args.node), affected=affected
            )
            return {
                "ok": True,
                "action": action,
                "revision": graph.get("revision"),
                "affected_nodes": affected,
                "receipt_path": str(receipt),
            }, 0
        if action == "lock":
            # Story lock: script-value-debrief soft by default; hard when
            # --strict or AIFILM_DEBRIEF_STRICT=1 (present structure + confirmed).
            debrief_gate: dict[str, Any] | None = None
            if str(args.scope) == "story":
                import os

                strict_deb = bool(getattr(args, "strict", False)) or os.environ.get(
                    "AIFILM_DEBRIEF_STRICT", ""
                ).lower() in {"1", "true", "yes", "on"}
                try:
                    from script_value_debrief import check_root

                    debrief_gate = check_root(
                        root,
                        strict=strict_deb,
                        require_confirmed=strict_deb,
                    )
                    if strict_deb and not debrief_gate.get("ok"):
                        raise PlanMutationError(
                            "script-value-debrief blocks story lock (strict): "
                            + ", ".join(
                                str(e.get("code") or e.get("message"))
                                for e in (debrief_gate.get("errors") or [])
                            ),
                            "DEBRIEF_LOCK_BLOCKED",
                        )
                except PlanMutationError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    debrief_gate = {"ok": True, "soft_error": str(exc)[:160]}
            graph = lock_scope(graph, str(args.scope), user_phrase=str(args.user_phrase))
            write_json(graph_path, graph)
            receipt = write_revision_receipt(
                root, graph, action="lock", reason=str(args.user_phrase)
            )
            out: dict[str, Any] = {
                "ok": True,
                "action": action,
                "scope": args.scope,
                "revision": graph.get("revision"),
                "receipt_path": str(receipt),
            }
            if debrief_gate is not None:
                out["script_value_debrief"] = debrief_gate
            return out, 0
        if action == "unlock":
            graph = unlock_scope(graph, str(args.scope), reason=str(args.reason))
            write_json(graph_path, graph)
            receipt = write_revision_receipt(root, graph, action="unlock", reason=str(args.reason))
            return {
                "ok": True,
                "action": action,
                "scope": args.scope,
                "revision": graph.get("revision"),
                "receipt_path": str(receipt),
            }, 0
        if not bool(getattr(args, "descendants", False)):
            raise PlanMutationError(
                "replan requires --descendants to confirm subtree invalidation",
                "DESCENDANTS_CONFIRM_REQUIRED",
            )
        affected = mark_replan(graph, str(args.node))
        write_json(graph_path, graph)
        receipt = write_revision_receipt(
            root, graph, action="replan", node_ref=str(args.node), affected=affected
        )
        return {
            "ok": True,
            "action": action,
            "revision": graph.get("revision"),
            "affected_nodes": affected,
            "receipt_path": str(receipt),
        }, 0
    except NarrativeControlError as exc:
        raise PlanMutationError(str(exc), exc.code) from exc
