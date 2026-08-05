"""Workflow wire: primary next + seven-step public phase stay same family.

Locks thrash modes found in 2026-08-05 audit:
- legacy phase frozen at define_story while bulk/plate advanced
- audio-plan / gate-auto / post-plan stealing closeout or export primary
- Seedance-as-default visual stage label
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from dispatch import build_dispatch, structured_next_action  # noqa: E402
from dispatch_compact import compact_dispatch  # noqa: E402
from next_actions import _STAGE_LABELS_ZH, build_next_actions  # noqa: E402
from production_gates import ProductionGateError, assert_pilot_allows_add  # noqa: E402
from workflow_spine import PUBLIC_FLOW, public_flow_phase  # noqa: E402

# Primary action id → seven-step public phase family (must match compact.phase.id).
_ACTION_PHASE: dict[str, str] = {
    "write-spec": "design_performance",
    "lock-style": "design_performance",
    "variety-precheck": "pilot",
    "pilot-pack": "pilot",
    "pilot-report": "pilot",
    "pilot-score": "pilot",
    "pilot-approve": "pilot",
    "bulk-preflight": "production",
    "h3-until-empty": "production",
    "h3-run-next": "production",
    "h3-fill-idle": "production",
    "queue-or-register": "production",
    "gate-auto": "selects_rough",
    "ship-prep": "selects_rough",
    "closeout-run": "post_master",
    "agent-review-final": "post_master",
    "review-final": "post_master",
    "post-audit": "post_master",
    "export-desktop": "delivery",
    "done": "delivery",
}

_PUBLIC_IDS = {item["id"] for item in PUBLIC_FLOW}


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, (dict, list)):
        path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    else:
        path.write_text(str(payload), encoding="utf-8")


def _spec(**extra: object) -> dict:
    base: dict = {
        "title": "wire-primary",
        "tts_backend": "edge",
        "shots": [
            {"id": "shot01", "nar": "开场", "dramatic_function": "hook"},
            {"id": "shot02", "nar": "发展", "dramatic_function": "develop"},
            {"id": "shot03", "nar": "高潮", "dramatic_function": "climax"},
        ],
    }
    base.update(extra)
    return base


def _pilot_approval() -> dict:
    return {
        "kind": "pilot-approval",
        "approved": True,
        "approved_by": "user",
        "user_phrase": "pilot 过",
        "approved_at": "2026-08-04T00:00:00+00:00",
    }


def _dispatch(root: Path, gates: dict) -> tuple[dict, dict]:
    full = build_dispatch(
        root,
        gates=gates,
        include_capability=False,
        write_receipt=False,
        use_state_cache=False,
    )
    return full, compact_dispatch(full)


def _assert_primary_wire(
    full: dict,
    compact: dict,
    *,
    expected_ids: set[str],
    expected_phase: str,
) -> None:
    next_id = str(full.get("next_id") or "")
    next_cmd = str(full.get("next_cmd") or "")
    phase_id = str((compact.get("phase") or {}).get("id") or "")
    assert next_id in expected_ids, f"unexpected primary {next_id!r}; want {expected_ids}"
    assert phase_id == expected_phase, f"phase {phase_id!r} != {expected_phase!r}"
    assert phase_id in _PUBLIC_IDS
    family = _ACTION_PHASE.get(next_id)
    assert family == phase_id, f"primary {next_id} family {family} != phase {phase_id}"
    assert next_cmd.strip().startswith("aifilm "), f"non-executable cmd: {next_cmd!r}"
    assert "…" not in next_cmd and "<" not in next_cmd and ">" not in next_cmd
    structured = structured_next_action(
        {
            "id": next_id,
            "cmd": next_cmd,
            "why": full.get("next_why"),
            "stage": "agent",
        }
    )
    assert structured is not None, f"primary not structured: {next_id} {next_cmd}"
    labels = " ".join(
        str(a.get("stage_label") or "") for a in (full.get("next_actions") or [])
    )
    assert "Seedance" not in labels


def test_public_flow_is_seven_steps() -> None:
    assert len(PUBLIC_FLOW) == 7
    assert [p["id"] for p in PUBLIC_FLOW] == [
        "define_story",
        "design_performance",
        "pilot",
        "production",
        "selects_rough",
        "post_master",
        "delivery",
    ]


def test_missing_spec_primary_is_write_spec_in_design_phase(tmp_path: Path) -> None:
    _write(tmp_path / "brief.json", {"title": "t", "theme": "x"})
    gates = {
        "brief": True,
        "style_locked": True,
        "spec": False,
        "clips_complete": False,
        "final_complete": False,
        "desktop_exported": False,
    }
    full, compact = _dispatch(tmp_path, gates)
    _assert_primary_wire(
        full,
        compact,
        expected_ids={"write-spec"},
        expected_phase="design_performance",
    )


def test_pilot_pending_primary_stays_in_pilot_family(tmp_path: Path) -> None:
    _write(tmp_path / "brief.json", {"title": "t", "theme": "x"})
    _write(tmp_path / "film-spec.json", _spec())
    gates = {
        "brief": True,
        "style_locked": True,
        "spec": True,
        "clips_complete": False,
        "final_complete": False,
        "desktop_exported": False,
    }
    full, compact = _dispatch(tmp_path, gates)
    _assert_primary_wire(
        full,
        compact,
        expected_ids={
            "variety-precheck",
            "pilot-pack",
            "pilot-report",
            "pilot-score",
            "pilot-approve",
        },
        expected_phase="pilot",
    )


def test_bulk_ready_primary_is_bulk_preflight_in_production(tmp_path: Path) -> None:
    _write(tmp_path / "brief.json", {"title": "t", "theme": "x"})
    _write(
        tmp_path / "film-spec.json",
        _spec(_i2v_profile="h3_primary", h3={"enabled": True}),
    )
    _write(tmp_path / "receipts" / "pilot-approval.json", _pilot_approval())
    gates = {
        "brief": True,
        "style_locked": True,
        "spec": True,
        "clips_complete": False,
        "final_complete": False,
        "desktop_exported": False,
    }
    full, compact = _dispatch(tmp_path, gates)
    _assert_primary_wire(
        full,
        compact,
        expected_ids={"bulk-preflight"},
        expected_phase="production",
    )


def test_bulk_preflight_ok_primary_is_h3_production(tmp_path: Path) -> None:
    _write(tmp_path / "brief.json", {"title": "t", "theme": "x"})
    _write(
        tmp_path / "film-spec.json",
        _spec(_i2v_profile="h3_primary", h3={"enabled": True}),
    )
    _write(tmp_path / "receipts" / "pilot-approval.json", _pilot_approval())
    _write(
        tmp_path / "receipts" / "bulk-preflight.json",
        {"ok": True, "kind": "bulk-preflight"},
    )
    gates = {
        "brief": True,
        "style_locked": True,
        "spec": True,
        "clips_complete": False,
        "final_complete": False,
        "desktop_exported": False,
    }
    full, compact = _dispatch(tmp_path, gates)
    _assert_primary_wire(
        full,
        compact,
        expected_ids={"h3-until-empty", "h3-run-next", "h3-fill-idle", "h3-lane"},
        expected_phase="production",
    )


def test_plate_primary_is_closeout_not_audio_or_gate(tmp_path: Path) -> None:
    _write(tmp_path / "brief.json", {"title": "t", "theme": "x"})
    _write(tmp_path / "film-spec.json", _spec())
    _write(tmp_path / "receipts" / "pilot-approval.json", _pilot_approval())
    plate = tmp_path / "out" / "film_final.mp4"
    plate.parent.mkdir(parents=True, exist_ok=True)
    plate.write_bytes(b"\x00" * 64)
    _write(
        tmp_path / "manifest.json",
        {
            "clips": {
                "shot01": {"status": "approved"},
                "shot02": {"status": "approved"},
                "shot03": {"status": "approved"},
            },
            "outputs": {
                "final_film": {
                    "path": str(plate),
                    "sha256": "abc123",
                    "post_engine": "hyperframes",
                }
            },
        },
    )
    gates = {
        "brief": True,
        "style_locked": True,
        "spec": True,
        "clips_complete": True,
        "final_complete": False,
        "desktop_exported": False,
    }
    full, compact = _dispatch(tmp_path, gates)
    _assert_primary_wire(
        full,
        compact,
        expected_ids={"closeout-run"},
        expected_phase="post_master",
    )
    ids = [a.get("id") for a in (full.get("next_actions") or [])]
    assert ids[0] == "closeout-run"
    assert "audio-plan" not in ids[:3]
    assert "gate-auto" not in ids[:3]
    assert "post-plan-init" not in ids[:3]


def test_final_complete_primary_is_export_in_delivery(tmp_path: Path) -> None:
    _write(tmp_path / "brief.json", {"title": "t", "theme": "x"})
    _write(tmp_path / "film-spec.json", _spec())
    _write(tmp_path / "receipts" / "pilot-approval.json", _pilot_approval())
    plate = tmp_path / "out" / "film_final.mp4"
    plate.parent.mkdir(parents=True, exist_ok=True)
    plate.write_bytes(b"\x00" * 64)
    _write(
        tmp_path / "manifest.json",
        {
            "clips": {
                "shot01": {"status": "approved"},
                "shot02": {"status": "approved"},
                "shot03": {"status": "approved"},
            },
            "outputs": {
                "final_film": {
                    "path": str(plate),
                    "sha256": "abc123",
                    "post_engine": "hyperframes",
                }
            },
        },
    )
    _write(
        tmp_path / "receipts" / "post-audit.json",
        {
            "kind": "post-audit",
            "delivery_ready": True,
            "ok": True,
            "final_sha256": "abc123",
        },
    )
    gates = {
        "brief": True,
        "style_locked": True,
        "spec": True,
        "clips_complete": True,
        "final_complete": True,
        "desktop_exported": False,
    }
    full, compact = _dispatch(tmp_path, gates)
    next_id = str(full.get("next_id") or "")
    phase = str((compact.get("phase") or {}).get("id") or "")
    assert next_id in {"export-desktop", "post-audit"}
    assert phase == "delivery"
    assert next_id != "audio-plan"
    structured = structured_next_action(
        {
            "id": next_id,
            "cmd": full.get("next_cmd"),
            "why": full.get("next_why"),
            "stage": "agent",
        }
    )
    assert structured is not None


def test_done_primary_does_not_reopen_audio_plan(tmp_path: Path) -> None:
    _write(tmp_path / "brief.json", {"title": "t", "theme": "x"})
    _write(tmp_path / "film-spec.json", _spec())
    _write(tmp_path / "receipts" / "pilot-approval.json", _pilot_approval())
    plate = tmp_path / "out" / "film_final.mp4"
    plate.parent.mkdir(parents=True, exist_ok=True)
    plate.write_bytes(b"\x00" * 64)
    _write(
        tmp_path / "manifest.json",
        {
            "outputs": {
                "final_film": {
                    "path": str(plate),
                    "sha256": "abc123",
                    "post_engine": "hyperframes",
                }
            }
        },
    )
    _write(
        tmp_path / "receipts" / "post-audit.json",
        {"kind": "post-audit", "delivery_ready": True, "ok": True, "final_sha256": "abc123"},
    )
    gates = {
        "brief": True,
        "style_locked": True,
        "spec": True,
        "clips_complete": True,
        "final_complete": True,
        "desktop_exported": True,
    }
    full, compact = _dispatch(tmp_path, gates)
    _assert_primary_wire(
        full,
        compact,
        expected_ids={"done"},
        expected_phase="delivery",
    )
    assert full.get("next_id") != "audio-plan"


def test_visual_stage_label_does_not_advertise_seedance_default() -> None:
    assert "Seedance" not in _STAGE_LABELS_ZH["visual"]
    assert "H3" in _STAGE_LABELS_ZH["visual"] or "Grok" in _STAGE_LABELS_ZH["visual"]


def test_pilot_gate_still_fail_closed_without_user_approval(tmp_path: Path) -> None:
    _write(tmp_path / "brief.json", {"title": "t"})
    _write(tmp_path / "film-spec.json", _spec())
    with pytest.raises(ProductionGateError):
        assert_pilot_allows_add(
            tmp_path,
            shot_id="shot04",
            existing_shot_ids={"shot01", "shot02", "shot03"},
        )


def test_legacy_phase_advances_with_production_evidence(tmp_path: Path) -> None:
    empty = public_flow_phase({"current_stage": "concept_lock"})
    assert empty["id"] == "define_story"

    _write(tmp_path / "brief.json", {"title": "t", "theme": "x"})
    _write(
        tmp_path / "film-spec.json",
        _spec(_i2v_profile="h3_primary", h3={"enabled": True}),
    )
    _write(tmp_path / "receipts" / "pilot-approval.json", _pilot_approval())
    gates = {
        "brief": True,
        "style_locked": True,
        "spec": True,
        "clips_complete": False,
        "final_complete": False,
        "desktop_exported": False,
    }
    full, compact = _dispatch(tmp_path, gates)
    assert compact["phase"]["id"] == "production"
    assert (full.get("workflow") or {}).get("current_stage") == "bulk"


def test_build_next_actions_plate_prefers_closeout_over_post_plan(tmp_path: Path) -> None:
    _write(tmp_path / "brief.json", {"title": "t"})
    _write(tmp_path / "film-spec.json", _spec())
    _write(tmp_path / "receipts" / "pilot-approval.json", _pilot_approval())
    plate = tmp_path / "out" / "film_final.mp4"
    plate.parent.mkdir(parents=True, exist_ok=True)
    plate.write_bytes(b"\x00" * 32)
    _write(
        tmp_path / "manifest.json",
        {"outputs": {"final_film": {"path": str(plate), "sha256": "x"}}},
    )
    actions = build_next_actions(
        tmp_path,
        gates={
            "brief": True,
            "style_locked": True,
            "spec": True,
            "clips_complete": True,
            "final_complete": False,
        },
    )
    ids = [a["id"] for a in actions]
    assert "closeout-run" in ids
    assert ids[0] == "closeout-run"
    assert "post-plan-init" not in ids
    assert "gate-auto" not in ids
    assert "audio-plan" not in ids
