from __future__ import annotations

import json
import shlex
import sys
from argparse import Namespace
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aifilm_grok import _pipeline_bundle, build_parser, cmd_init  # noqa: E402
from approval_ledger import append_approval  # noqa: E402
from director_cli import lock_native_stage  # noqa: E402
from director_stage_gates import hash_input_refs, lock_stage  # noqa: E402
from dispatch import build_dispatch  # noqa: E402
from dispatch_compact import compact_dispatch  # noqa: E402
from production_book import init_production_book, read_production_book  # noqa: E402
from review_control import record_action, review_queue  # noqa: E402
from workflow_spine import (  # noqa: E402
    STAGE_ORDER,
    build_workflow_status,
    professional_stage_actions,
)

EXPECTED_PROFESSIONAL_STAGES = (
    "concept_lock",
    "script_lock",
    "department_look_lock",
    "shot_animatic_lock",
    "pilot_approval",
    "bulk",
    "dailies_review",
    "selects_rough_cut",
    "picture_lock",
    "post_locks",
    "master_lock",
)


def _write_concept_evidence(root: Path) -> None:
    (root / "brief.json").write_text('{"title":"t"}\n', encoding="utf-8")
    (root / "drama-graph.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "story": {
                    "premise": "p",
                    "logline": "l",
                    "protagonist_goal": "g",
                    "opposition": "o",
                    "stakes": "s",
                    "climax_choice": "c",
                    "ending_hook": "e",
                    "emotional_arc": ["a", "b", "c"],
                },
            }
        ),
        encoding="utf-8",
    )


def _lock(root: Path, stage: str) -> None:
    source = root / "stage-inputs" / f"{stage}.json"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(f'{{"stage":"{stage}"}}\n', encoding="utf-8")
    refs = {stage: str(source.relative_to(root))}
    hashes = hash_input_refs(root, refs)
    approval = append_approval(
        root,
        scope=f"stage:{stage}",
        approval_type="stage_lock",
        approver_type="human",
        approver="director",
        authorization_event=f"test:{stage}",
        input_hashes=hashes,
        evidence_refs=[str(source.relative_to(root))],
        transaction_id=f"tx-{stage}",
    )
    lock_stage(root, stage=stage, input_refs=refs, approval_id=approval["approval_id"])


def test_standard_init_absorbs_professional_control_book(tmp_path: Path, capsys) -> None:
    root = tmp_path / "film"

    assert (
        cmd_init(
            Namespace(
                title="雨夜",
                theme="陌生人必须在暴雨中完成一次交付",
                aspect="9:16",
                root=str(root),
                force=False,
            )
        )
        == 0
    )
    capsys.readouterr()

    book = read_production_book(root)
    assert book["rigor"] == "professional"
    assert book["quality_target"] == "standard"
    assert book["packs"]["format"] == "vertical-short"


def test_init_force_refuses_to_silently_upgrade_legacy_root(tmp_path: Path) -> None:
    root = tmp_path / "legacy"
    root.mkdir()
    legacy = root / "film-spec.json"
    legacy.write_text('{"title":"legacy","shots":[]}\n', encoding="utf-8")
    before = legacy.read_bytes()

    with pytest.raises(Exception, match="migrate-audit"):
        cmd_init(
            Namespace(
                title="覆盖",
                theme="不应写入",
                aspect="9:16",
                root=str(root),
                force=True,
            )
        )

    assert legacy.read_bytes() == before
    assert not (root / "production-book.json").exists()


def test_new_root_init_does_not_publish_partial_project_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "film"

    def fail_book(*_args, **_kwargs):
        raise RuntimeError("injected production-book failure")

    monkeypatch.setattr("production_book.init_production_book", fail_book)

    with pytest.raises(RuntimeError, match="injected production-book failure"):
        cmd_init(
            Namespace(
                title="雨夜",
                theme="原子初始化",
                aspect="9:16",
                root=str(root),
                force=False,
            )
        )

    assert not root.exists()
    assert not list(tmp_path.glob(".film.aifilm-init-*"))


def test_professional_spine_never_advances_from_native_evidence_without_stage_lock(
    tmp_path: Path,
) -> None:
    init_production_book(tmp_path, rigor="professional")
    narrative = {
        "canonical": True,
        "semantic": {"errors": []},
        "locked_scopes": ["story", "beats", "shots", "panels"],
        "projection": {"ok": True, "stale": False},
        "ready_for_media": True,
    }

    status = build_workflow_status(
        tmp_path,
        gates={"brief": True, "style_locked": True, "spec": True},
        narrative=narrative,
    )

    assert STAGE_ORDER == EXPECTED_PROFESSIONAL_STAGES
    assert status["stage_order"] == list(EXPECTED_PROFESSIONAL_STAGES)
    assert status["stage_total"] == 11
    assert status["current_stage"] == "concept_lock"
    assert status["completed"] == []
    assert status["readiness"]["shot_animatic_lock"] is True
    assert status["distilled_from"] == "professional-director-11"
    assert status["public_entry"] == "/ai-film-grok"


def test_professional_spine_uses_director_stage_gate_next_stage(tmp_path: Path) -> None:
    init_production_book(tmp_path, rigor="professional")
    _write_concept_evidence(tmp_path)
    lock_native_stage(
        tmp_path,
        stage="concept_lock",
        approver="dex",
        user_phrase="批准概念锁",
    )

    status = build_workflow_status(tmp_path, gates={})

    assert status["current_stage"] == "script_lock"
    assert status["completed"] == ["concept_lock"]
    assert status["stage_gates"]["next_stage"] == "script_lock"


def test_native_stage_lock_routes_professional_workflow_forward(tmp_path: Path) -> None:
    init_production_book(tmp_path, rigor="professional")
    _write_concept_evidence(tmp_path)

    report = lock_native_stage(
        tmp_path,
        stage="concept_lock",
        approver="dex",
        user_phrase="批准概念锁",
    )

    assert report["ok"] is True
    assert report["input_refs"] == {
        "brief": "brief.json",
        "story": "drama-graph.json",
    }
    assert report["stage_gates"]["next_stage"] == "script_lock"


def test_review_ui_approval_writes_professional_stage_lock(tmp_path: Path) -> None:
    init_production_book(tmp_path, rigor="professional")
    _write_concept_evidence(tmp_path)
    queue = review_queue(tmp_path)

    assert queue["items"][0]["id"] == "director:concept_lock"
    assert queue["items"][0]["state"] == "pending_review"

    result = record_action(
        tmp_path,
        stage="director:concept_lock",
        action="approve",
        issue="story",
        note="批准当前概念锁",
        timestamp_sec=None,
        expected_ledger_revision=queue["ledger_revision"],
    )

    assert result["event"]["stage_lock"]["stage"] == "concept_lock"
    assert build_workflow_status(tmp_path, gates={})["current_stage"] == "script_lock"


def test_legacy_root_remains_compatible_without_silent_upgrade(tmp_path: Path) -> None:
    status = build_workflow_status(tmp_path, gates={})

    assert status["mode"] == "legacy"
    assert status["blocking"] is False
    assert status["current_stage"] == "concept_lock"


def test_master_lock_completes_spine_before_desktop_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_production_book(tmp_path, rigor="professional")
    monkeypatch.setattr(
        "director_cli.validate_native_stage_evidence",
        lambda _root, _stage: {},
    )
    for stage in STAGE_ORDER:
        _lock(tmp_path, stage)

    status = build_workflow_status(
        tmp_path,
        gates={"desktop_exported": False},
    )

    assert status["current_stage"] == "complete"
    assert status["completed"] == list(STAGE_ORDER)
    assert status["delivery_pending"] is True


def test_complete_professional_workflow_is_done_after_desktop_export(
    tmp_path: Path,
) -> None:
    actions = professional_stage_actions(
        tmp_path,
        {
            "mode": "professional",
            "current_stage": "complete",
            "ready_for_lock": False,
            "delivery_pending": False,
        },
        [],
    )

    assert actions == [
        {
            "id": "done",
            "cmd": f'aifilm status --root "{tmp_path.resolve()}"',
            "why": "母版与 Desktop 交付副本均已验证；流程已收敛",
            "stage": "deliver",
            "stage_label": "deliver",
            "source": "professional_workflow",
        }
    ]


def test_complete_professional_workflow_never_routes_back_to_heat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_production_book(tmp_path, rigor="professional")
    monkeypatch.setattr(
        "director_cli.validate_native_stage_evidence",
        lambda _root, _stage: {},
    )
    for stage in STAGE_ORDER:
        _lock(tmp_path, stage)
    monkeypatch.setattr(
        "heat_check.heat_agent_status",
        lambda _root: {
            "active": True,
            "hard_fail": True,
            "needs_boost": True,
            "next_cmd": f'aifilm heat boost --root "{tmp_path}" --apply',
        },
    )

    packet = build_dispatch(
        tmp_path,
        gates={"desktop_exported": True},
        include_capability=False,
        write_receipt=False,
        use_state_cache=False,
    )

    assert packet["workflow"]["current_stage"] == "complete"
    assert packet["next_id"] == "done"
    assert packet["next_action"]["argv"][:1] == ["status"]
    assert all(action["id"] != "heat-boost" for action in packet["next_actions"])


def test_dispatch_compact_and_full_share_unified_workflow(tmp_path: Path) -> None:
    (tmp_path / "brief.json").write_text('{"title":"t"}\n', encoding="utf-8")
    (tmp_path / "film-spec.json").write_text('{"title":"t","shots":[]}\n', encoding="utf-8")
    init_production_book(tmp_path, rigor="professional")

    full = build_dispatch(
        tmp_path,
        gates={"brief": True},
        include_capability=False,
        write_receipt=False,
        use_state_cache=False,
    )
    compact = compact_dispatch(full)

    assert full["workflow"]["public_entry"] == "/ai-film-grok"
    assert full["next_id"] == "concept_lock-evidence"
    assert full["next_action"] is not None
    assert full["next_action"]["argv"][:2] == ["plan", "status"]
    assert compact["next_action"] == full["next_action"]
    assert compact["workflow"]["mode"] == "professional"
    assert compact["workflow"]["current_stage"] == full["workflow"]["current_stage"]

    actions, pipeline, next_cmd, next_id = _pipeline_bundle(
        tmp_path,
        gates={"brief": True},
        persist=False,
    )
    assert next_id == full["next_id"]
    assert next_cmd == full["next_cmd"]
    assert pipeline["bound_next_action"] == full["next_action"]
    assert pipeline["workflow_stage"] == full["workflow"]["current_stage"]
    assert actions[0]["id"] == full["next_actions"][0]["id"]


def test_dispatch_routes_ready_stage_to_human_hash_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_production_book(tmp_path, rigor="professional")
    original = build_workflow_status

    def ready_status(root: Path, **kwargs):
        status = original(root, **kwargs)
        status["readiness"]["concept_lock"] = True
        status["ready_for_lock"] = True
        return status

    monkeypatch.setattr("workflow_spine.build_workflow_status", ready_status)

    full = build_dispatch(
        tmp_path,
        gates={"brief": True},
        include_capability=False,
        write_receipt=False,
        use_state_cache=False,
    )

    assert full["next_id"] == "concept_lock-review"
    assert "review-ui serve" in full["next_cmd"]
    assert full["next_action"]["approval_class"] == "human_required"


@pytest.mark.parametrize(
    ("stage", "ready_for_lock"),
    [*((stage, ready) for stage in STAGE_ORDER for ready in (False, True)), ("complete", False)],
)
def test_every_professional_primary_action_parses_without_placeholders(
    tmp_path: Path, stage: str, ready_for_lock: bool
) -> None:
    workflow = {
        "mode": "professional",
        "current_stage": stage,
        "ready_for_lock": ready_for_lock,
    }

    actions = professional_stage_actions(tmp_path, workflow, [])

    command = actions[0]["cmd"]
    assert not any(token in command for token in ("<", ">", "…"))
    build_parser().parse_args(shlex.split(command)[1:])
