#!/usr/bin/env python3
"""One public ai-film-grok workflow distilled from the professional 11-stage model.

The professional model remains an internal ordering and evidence contract. It
does not create a second user-facing workflow: hash-bound director locks point
to evidence owned by narrative, pilot, clip, post, and final review systems.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from director_stage_gates import STAGE_ORDER
from production_book import RIGOR_LEVELS
from util import read_json

STAGE_LABELS_ZH: dict[str, str] = {
    "concept_lock": "概念锁",
    "script_lock": "剧本锁",
    "department_look_lock": "部门与视觉锁",
    "shot_animatic_lock": "镜头与动态分镜锁",
    "pilot_approval": "Pilot 批准",
    "bulk": "批量生成",
    "dailies_review": "每日样片审核",
    "selects_rough_cut": "选片与粗剪",
    "picture_lock": "画面锁定",
    "post_locks": "后期锁定",
    "master_lock": "母版锁定",
}

EVIDENCE_OWNERS: dict[str, str] = {
    "concept_lock": "drama-graph",
    "script_lock": "narrative locks",
    "department_look_lock": "style-bible",
    "shot_animatic_lock": "film-spec projection",
    "pilot_approval": "pilot approval",
    "bulk": "approved clip receipts",
    "dailies_review": "selects report",
    "selects_rough_cut": "editor cut",
    "picture_lock": "preview human review",
    "post_locks": "post plan + audio review",
    "master_lock": "review-final + post-audit; export read-back remains delivery evidence",
}

STAGE_TO_CRAFT: dict[str, str] = {
    "concept_lock": "idea",
    "script_lock": "story",
    "department_look_lock": "beats",
    "shot_animatic_lock": "shots",
    "pilot_approval": "shots",
    "bulk": "media",
    "dailies_review": "selects",
    "selects_rough_cut": "rough",
    "picture_lock": "rough",
    "post_locks": "rough",
    "master_lock": "verified",
}

_ACTION_PRIORITY: dict[str, tuple[str, ...]] = {
    "concept_lock": ("workflow-stage-lock", "workflow-concept"),
    "script_lock": (
        "workflow-stage-lock",
        "narrative-validate",
        "narrative-project",
        "narrative-lock",
    ),
    "department_look_lock": ("workflow-stage-lock", "lock-style"),
    "shot_animatic_lock": (
        "workflow-stage-lock",
        "narrative-validate",
        "narrative-project",
        "narrative-lock",
        "write-spec",
    ),
    "pilot_approval": (
        "workflow-stage-lock",
        "pilot-report",
        "pilot-reshoot",
        "pilot-score",
        "pilot-approve",
    ),
    "bulk": (
        "workflow-stage-lock",
        "production-evidence-gate",
        "state-index-plan",
        "queue-or-register",
        "pilot-window",
    ),
    "dailies_review": ("workflow-stage-lock", "selects-report"),
    "selects_rough_cut": ("workflow-stage-lock", "rough-cut-review"),
    "picture_lock": ("workflow-stage-lock", "compose-preview", "picture-lock-review"),
    "post_locks": (
        "workflow-stage-lock",
        "post-plan-init",
        "tts-rehearse",
        "post-lock-review",
        "audio-plan",
    ),
    "master_lock": (
        "workflow-stage-lock",
        "final-designed",
        "final",
        "review-final",
        "post-audit-gate",
        "post-audit",
        "master-lock-review",
    ),
    "complete": ("export-desktop", "done"),
}


def _present(path: Path, *, min_bytes: int = 2) -> bool:
    return path.is_file() and path.stat().st_size > min_bytes


def _mode(root: Path) -> tuple[str, str | None]:
    book = read_json(root / "production-book.json")
    if not isinstance(book, dict):
        return "legacy", None
    rigor = str(book.get("rigor") or "legacy")
    return rigor if rigor in RIGOR_LEVELS else "legacy", rigor


def _pilot_user_approved(root: Path) -> bool:
    try:
        from production_gates import load_pilot_approval, pilot_is_user_approved

        return pilot_is_user_approved(load_pilot_approval(root))
    except (OSError, ValueError):
        return False


def _selects_current(root: Path) -> bool:
    from selects_report import build_selects_report

    report = build_selects_report(root, write_receipt=False)
    return bool(report.get("complete") and report.get("ok"))


def _rough_current(root: Path, manifest: dict[str, Any], *, professional: bool) -> bool:
    if professional:
        from editor_cut import build_editor_cut_report
        from selects_report import build_selects_report

        selects = build_selects_report(root, write_receipt=False)
        rough = read_json(root / "receipts" / "rough-cut.json") or {}
        if rough.get("ok") is True:
            return bool(
                selects.get("complete")
                and rough.get("selected_set_sha256")
                and rough.get("selected_set_sha256") == selects.get("selected_set_sha256")
            )
        return bool(build_editor_cut_report(root, write=False).get("ok"))
    if _present(root / "receipts" / "rough-cut.json"):
        return True
    editor_cut = read_json(root / "receipts" / "editor-cut.json") or {}
    if editor_cut.get("ok") is True and int(editor_cut.get("shot_count") or 0) > 0:
        return True
    outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), dict) else {}
    silent = outputs.get("silent_film") if isinstance(outputs.get("silent_film"), dict) else {}
    return bool(silent.get("path") and silent.get("sha256"))


def _review_stage_approved(root: Path, stage: str) -> bool:
    try:
        from review_control import review_queue

        item = next(
            (entry for entry in review_queue(root).get("items") or [] if entry.get("id") == stage),
            None,
        )
        return bool(item and item.get("state") == "approved")
    except (OSError, ValueError):
        return False


def _post_plan_current(root: Path) -> bool:
    try:
        from post_plan import load_post_plan

        return load_post_plan(root) is not None
    except (OSError, ValueError):
        return False


def _post_audit_current(root: Path) -> bool:
    receipt = read_json(root / "receipts" / "post-audit.json") or {}
    if receipt.get("delivery_ready") is not True:
        return False
    try:
        from post_audit import audit_freshness

        return audit_freshness(root, receipt).get("stale") is False
    except (OSError, ValueError):
        return False


def build_workflow_status(
    root: Path | str,
    *,
    gates: dict[str, Any] | None = None,
    narrative: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Project existing ai-film-grok evidence onto the professional stage order."""
    base = Path(root).expanduser().resolve()
    gates = gates or {}
    if narrative is None:
        try:
            from narrative_control import control_status

            narrative = control_status(base)
        except (OSError, ValueError):
            narrative = {}
    narrative = narrative or {}
    mode, invalid_rigor = _mode(base)
    manifest = read_json(base / "manifest.json") or {}
    semantic = narrative.get("semantic") if isinstance(narrative.get("semantic"), dict) else {}
    projection = (
        narrative.get("projection") if isinstance(narrative.get("projection"), dict) else {}
    )
    locked_scopes = set(str(item) for item in narrative.get("locked_scopes") or [])

    concept_ok = bool(gates.get("brief") and narrative.get("canonical"))
    script_ok = bool(
        concept_ok and not semantic.get("errors") and {"story", "beats"}.issubset(locked_scopes)
    )
    look_ok = bool(script_ok and gates.get("style_locked"))
    shot_ok = bool(
        look_ok
        and gates.get("spec")
        and narrative.get("ready_for_media")
        and projection.get("stale") is not True
    )
    pilot_ok = bool(shot_ok and _pilot_user_approved(base))
    bulk_ok = bool(pilot_ok and gates.get("clips_complete"))
    from dailies import dailies_review_status

    dailies_ok = bool(bulk_ok and dailies_review_status(base).get("ok"))
    selects_ok = bool(dailies_ok and _selects_current(base))
    rough_ok = bool(
        selects_ok and _rough_current(base, manifest, professional=mode == "professional")
    )
    picture_ok = bool(rough_ok and _review_stage_approved(base, "preview"))
    post_ok = bool(
        picture_ok
        and _post_plan_current(base)
        and _review_stage_approved(base, "audio")
        and (
            _present(base / "receipts" / "tts-rehearsal.json")
            or _present(base / "audio" / "mix_report.json")
        )
    )
    master_ok = bool(post_ok and gates.get("final_complete") and _post_audit_current(base))

    readiness = {
        "concept_lock": concept_ok,
        "script_lock": script_ok,
        "department_look_lock": look_ok,
        "shot_animatic_lock": shot_ok,
        "pilot_approval": pilot_ok,
        "bulk": bulk_ok,
        "dailies_review": dailies_ok,
        "selects_rough_cut": rough_ok,
        "picture_lock": picture_ok,
        "post_locks": post_ok,
        "master_lock": master_ok,
    }
    try:
        from director_stage_gates import stage_status

        stage_gates = stage_status(base)
    except (OSError, ValueError):
        stage_gates = {
            "ok": mode == "legacy",
            "kind": "director-stage-status",
            "rigor": mode,
            "stages": [],
            "blocking": [],
            "warnings": [],
            "next_stage": None,
        }

    if mode != "professional":
        checks = dict(readiness)
        current = next((stage for stage in STAGE_ORDER if not checks[stage]), "complete")
        completed = [stage for stage in STAGE_ORDER if checks[stage]]
    else:
        gate_current = {
            str(item.get("stage")): bool(item.get("current"))
            for item in stage_gates.get("stages") or []
        }
        checks = {stage: gate_current.get(stage, False) for stage in STAGE_ORDER}
        next_stage = stage_gates.get("next_stage")
        current = str(next_stage) if next_stage in STAGE_ORDER else "complete"
        completed = []
        for stage in STAGE_ORDER:
            if not checks[stage]:
                break
            completed.append(stage)

    dependency_graph = {
        stage: ([] if index == 0 else [STAGE_ORDER[index - 1]])
        for index, stage in enumerate(STAGE_ORDER)
    }
    invalidated = [] if current == "complete" else list(STAGE_ORDER[STAGE_ORDER.index(current) :])
    return {
        "schema_version": 1,
        "kind": "ai-film-grok-workflow",
        "public_entry": "/ai-film-grok",
        "distilled_from": "professional-director-11",
        "mode": mode,
        "invalid_rigor": invalid_rigor,
        "blocking": mode == "professional",
        "current_stage": current,
        "current_label_zh": "完成" if current == "complete" else STAGE_LABELS_ZH[current],
        "stage_index": len(STAGE_ORDER) if current == "complete" else STAGE_ORDER.index(current),
        "stage_total": len(STAGE_ORDER),
        "stage_order": list(STAGE_ORDER),
        "completed": completed,
        "checks": checks,
        "readiness": readiness,
        "ready_for_lock": (
            current != "complete"
            and bool(readiness.get(current))
            and all(checks[stage] for stage in STAGE_ORDER[: STAGE_ORDER.index(current)])
        ),
        "stage_gates": stage_gates,
        "dependency_graph": dependency_graph,
        "evidence_owners": dict(EVIDENCE_OWNERS),
        "invalidated_downstream": invalidated,
        "delivery_pending": current == "complete" and not bool(gates.get("desktop_exported")),
        "craft_projection": (
            "verified" if current == "complete" else STAGE_TO_CRAFT.get(current, "idea")
        ),
        "compatibility": (
            "existing roots without production-book remain legacy; no silent upgrade"
            if mode == "legacy"
            else "professional ordering is enforced through native ai-film-grok evidence"
        ),
    }


def prioritize_actions(
    workflow: dict[str, Any], actions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Keep one next action aligned with the internal professional stage."""
    if workflow.get("mode") != "professional":
        return list(actions)
    priorities = _ACTION_PRIORITY.get(str(workflow.get("current_stage") or ""), ())
    if not priorities:
        return list(actions)
    rank = {action_id: index for index, action_id in enumerate(priorities)}
    indexed = list(enumerate(actions))
    indexed.sort(
        key=lambda item: (
            0 if str(item[1].get("id") or "") in rank else 1,
            rank.get(str(item[1].get("id") or ""), len(rank)),
            item[0],
        )
    )
    return [action for _, action in indexed]


def professional_stage_actions(
    root: Path | str,
    workflow: dict[str, Any],
    actions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return a closed, executable action set for the current Professional stage."""
    if workflow.get("mode") != "professional":
        return list(actions)
    base = Path(root).expanduser().resolve()
    stage = str(workflow.get("current_stage") or "")
    if stage == "complete":
        if not workflow.get("delivery_pending", True):
            return [
                {
                    "id": "done",
                    "cmd": f'aifilm status --root "{base}"',
                    "why": "母版与 Desktop 交付副本均已验证；流程已收敛",
                    "stage": "deliver",
                    "stage_label": "deliver",
                    "source": "professional_workflow",
                }
            ]
        return [
            {
                "id": "export-desktop",
                "cmd": f'aifilm export-desktop --root "{base}" --name "{base.name}"',
                "why": "Master Lock 已是当前版本；执行锁后导出并进行 checksum/解码回读",
                "stage": "deliver",
                "stage_label": "deliver",
                "source": "professional_workflow",
            }
        ]
    if workflow.get("ready_for_lock"):
        return [
            {
                "id": f"{stage}-review",
                "cmd": f'aifilm review-ui serve --root "{base}"',
                "why": (
                    f"{STAGE_LABELS_ZH[stage]}证据已齐；审核后由界面提交原文批准并写入 "
                    "hash-bound stage lock"
                ),
                "stage": "agent",
                "stage_label": "agent",
                "source": "professional_workflow",
            }
        ]

    allowed = set(_ACTION_PRIORITY.get(stage, ()))
    selected = []
    for action in actions:
        command = str(action.get("cmd") or "").strip()
        if (
            str(action.get("id") or "") in allowed
            and command.startswith("aifilm ")
            and not any(token in command for token in ("<", ">", "…"))
        ):
            selected.append(action)
    fallbacks: dict[str, tuple[str, str]] = {
        "concept_lock": (
            f'aifilm plan status --root "{base}"',
            "检查故事接收与 canonical drama graph；概念证据未齐时不得进入视觉",
        ),
        "script_lock": (
            f'aifilm plan validate --root "{base}" --strict',
            "检查故事、beats、shots 与 panels 的语义和锁定状态",
        ),
        "department_look_lock": (
            f'aifilm director status --root "{base}"',
            "检查 Visual Bible、资产与部门交接证据",
        ),
        "shot_animatic_lock": (
            f'aifilm write-spec --root "{base}"',
            "生成当前 drama graph 的镜头、时长与 animatic 投影",
        ),
        "pilot_approval": (
            f'aifilm pilot report --root "{base}"',
            "检查 Pilot 评分与用户批准；不得直接进入付费 Bulk",
        ),
        "bulk": (
            f'aifilm production-evidence --root "{base}"',
            "检查已锁 Pilot 与逐镜媒体生成前置证据",
        ),
        "dailies_review": (
            f'aifilm dailies status --root "{base}"',
            "检查每个计划镜头的 take、选择与重拍分类",
        ),
        "selects_rough_cut": (
            f'aifilm selects --root "{base}" --no-write',
            "只读投影 canonical dailies ledger 并检查粗剪绑定",
        ),
        "picture_lock": (
            f'aifilm review-ui serve --root "{base}"',
            "检查 EDL、timeline 与 ordered selected take set 后等待 Picture Lock",
        ),
        "post_locks": (
            f'aifilm post-plan --root "{base}" show',
            "检查唯一后期 owner、声音、音乐、字幕与混音锁",
        ),
        "master_lock": (
            f'aifilm post-audit --root "{base}"',
            "检查 final candidate、review-final 与 master read-back",
        ),
    }
    if selected:
        return selected
    command, why = fallbacks[stage]
    return [
        {
            "id": f"{stage}-evidence",
            "cmd": command,
            "why": why,
            "stage": "agent",
            "stage_label": "agent",
            "source": "professional_workflow",
        }
    ]
