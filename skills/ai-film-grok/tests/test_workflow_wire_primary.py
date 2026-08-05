"""Workflow wire: primary next + seven-step public phase stay same family.

Real path: disk fixtures → ``recompute_gates`` → ``build_dispatch`` (same as
``aifilm dispatch``). Synthetic gates= dict injection is intentionally avoided.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from core.gates import recompute_gates  # noqa: E402
from dispatch import build_dispatch, structured_next_action  # noqa: E402
from dispatch_compact import compact_dispatch  # noqa: E402
from next_actions import _STAGE_LABELS_ZH  # noqa: E402
from production_gates import ProductionGateError, assert_pilot_allows_add  # noqa: E402
from workflow_spine import PUBLIC_FLOW  # noqa: E402

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


def _valid_film_spec(**extra: object) -> dict:
    base: dict = {
        "title": "色气测试",
        "vo_mode": "storyteller",
        "tts_backend": "edge",
        "dramatic_meaning_strict": False,
        "director_intent": {
            "logline": "雨夜后座升温的完整承诺句。",
            "tone": "色气·诱惑",
            "emotional_arc": ["a", "b", "c"],
        },
        "sound_plan": {"mood": "rnb"},
        "scenes": [
            {
                "shots": [
                    {
                        "id": "shot01",
                        "dramatic_function": "hook",
                        "nar": "话说她眨眼。",
                        "duration_sec": 6,
                        "dsl": {"subject": "a", "action": "b", "motion": "slow push-in, soft blink"},
                    },
                    {
                        "id": "shot02",
                        "dramatic_function": "action",
                        "nar": "她靠近他。",
                        "duration_sec": 6,
                        "dsl": {"subject": "a", "action": "lean", "motion": "push-in"},
                    },
                    {
                        "id": "shot03",
                        "dramatic_function": "reaction",
                        "nar": "他回头。",
                        "duration_sec": 6,
                        "dsl": {"subject": "b", "action": "turn", "motion": "pan"},
                    },
                ]
            }
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


def _empty_manifest() -> dict:
    return {"schema_version": 2, "clips": {}, "outputs": {}, "gates": {}}


def _dispatch_via_recompute(root: Path) -> tuple[dict, dict, dict]:
    man_path = root / "manifest.json"
    if man_path.is_file():
        man = json.loads(man_path.read_text(encoding="utf-8"))
    else:
        man = _empty_manifest()
        _write(man_path, man)
    summary = recompute_gates(root, man)
    gates = summary.get("gates") or {}
    full = build_dispatch(
        root,
        gates=gates,
        open_reshoot_count=int(summary.get("open_reshoot_count") or 0),
        include_capability=False,
        write_receipt=False,
        use_state_cache=False,
    )
    return full, compact_dispatch(full), gates


def _assert_primary_wire(full, compact, *, expected_ids, expected_phase):
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
        {"id": next_id, "cmd": next_cmd, "why": full.get("next_why"), "stage": "agent"}
    )
    assert structured is not None, f"primary not structured: {next_id} {next_cmd}"
    labels = " ".join(str(a.get("stage_label") or "") for a in (full.get("next_actions") or []))
    assert "Seedance" not in labels


def test_public_flow_is_seven_steps() -> None:
    assert len(PUBLIC_FLOW) == 7


def test_missing_spec_primary_is_write_spec_in_design_phase(tmp_path: Path) -> None:
    _write(tmp_path / "brief.json", {"title": "t", "theme": "x"})
    _write(tmp_path / "style-bible.json", {"locked": True})
    _write(tmp_path / "manifest.json", _empty_manifest())
    full, compact, gates = _dispatch_via_recompute(tmp_path)
    assert gates.get("spec") is False
    _assert_primary_wire(full, compact, expected_ids={"write-spec"}, expected_phase="design_performance")


def test_partial_invalid_spec_with_pilot_stays_design_not_production(tmp_path: Path) -> None:
    _write(tmp_path / "brief.json", {"title": "t", "theme": "x"})
    _write(tmp_path / "style-bible.json", {"locked": True})
    _write(
        tmp_path / "film-spec.json",
        {
            "title": "t",
            "tts_backend": "edge",
            "shots": [
                {"id": "shot01", "nar": "a", "dramatic_function": "hook"},
                {"id": "shot02", "nar": "b", "dramatic_function": "action"},
                {"id": "shot03", "nar": "c", "dramatic_function": "reaction"},
            ],
            "_i2v_profile": "h3_primary",
            "h3": {"enabled": True},
        },
    )
    _write(tmp_path / "receipts" / "pilot-approval.json", _pilot_approval())
    _write(tmp_path / "manifest.json", _empty_manifest())
    full, compact, gates = _dispatch_via_recompute(tmp_path)
    assert gates.get("spec") is False
    assert compact["phase"]["id"] == "design_performance"
    assert full.get("next_id") == "write-spec"
    assert full.get("next_id") not in {"h3-fill-idle", "h3-until-empty", "bulk-preflight", "queue-or-register"}


def test_pilot_pending_primary_stays_in_pilot_family(tmp_path: Path) -> None:
    _write(tmp_path / "brief.json", {"title": "t", "theme": "x"})
    _write(tmp_path / "style-bible.json", {"locked": True})
    _write(tmp_path / "film-spec.json", _valid_film_spec())
    _write(tmp_path / "manifest.json", _empty_manifest())
    full, compact, gates = _dispatch_via_recompute(tmp_path)
    assert gates.get("spec") is True
    _assert_primary_wire(
        full, compact,
        expected_ids={"variety-precheck", "pilot-pack", "pilot-report", "pilot-score", "pilot-approve"},
        expected_phase="pilot",
    )


def test_bulk_ready_primary_is_bulk_preflight_in_production(tmp_path: Path) -> None:
    _write(tmp_path / "brief.json", {"title": "t", "theme": "x"})
    _write(tmp_path / "style-bible.json", {"locked": True})
    _write(tmp_path / "film-spec.json", _valid_film_spec(_i2v_profile="h3_primary", h3={"enabled": True}))
    _write(tmp_path / "receipts" / "pilot-approval.json", _pilot_approval())
    _write(tmp_path / "manifest.json", _empty_manifest())
    full, compact, gates = _dispatch_via_recompute(tmp_path)
    assert gates.get("spec") is True
    _assert_primary_wire(full, compact, expected_ids={"bulk-preflight"}, expected_phase="production")


def test_bulk_preflight_ok_primary_is_h3_production(tmp_path: Path) -> None:
    _write(tmp_path / "brief.json", {"title": "t", "theme": "x"})
    _write(tmp_path / "style-bible.json", {"locked": True})
    _write(tmp_path / "film-spec.json", _valid_film_spec(_i2v_profile="h3_primary", h3={"enabled": True}))
    _write(tmp_path / "receipts" / "pilot-approval.json", _pilot_approval())
    _write(tmp_path / "receipts" / "bulk-preflight.json", {"ok": True, "kind": "bulk-preflight"})
    _write(tmp_path / "manifest.json", _empty_manifest())
    full, compact, gates = _dispatch_via_recompute(tmp_path)
    _assert_primary_wire(
        full, compact,
        expected_ids={"h3-until-empty", "h3-run-next", "h3-fill-idle", "h3-lane"},
        expected_phase="production",
    )


def test_plate_primary_is_closeout_family_in_post_master(tmp_path: Path) -> None:
    _write(tmp_path / "brief.json", {"title": "t", "theme": "x"})
    _write(tmp_path / "style-bible.json", {"locked": True})
    _write(tmp_path / "film-spec.json", _valid_film_spec())
    _write(tmp_path / "receipts" / "pilot-approval.json", _pilot_approval())
    plate = tmp_path / "out" / "film_final.mp4"
    plate.parent.mkdir(parents=True, exist_ok=True)
    plate.write_bytes(b"\x00" * 128)
    _write(
        tmp_path / "manifest.json",
        {
            "schema_version": 2,
            "clips": {},
            "outputs": {"final_film": {"path": str(plate), "sha256": "abc123", "post_engine": "hyperframes"}},
            "gates": {},
        },
    )
    full, compact, gates = _dispatch_via_recompute(tmp_path)
    assert gates.get("clips_complete") is False
    _assert_primary_wire(
        full, compact,
        expected_ids={"closeout-run", "agent-review-final", "review-final"},
        expected_phase="post_master",
    )


def test_visual_stage_label_does_not_advertise_seedance_default() -> None:
    assert "Seedance" not in _STAGE_LABELS_ZH["visual"]


def test_pilot_gate_still_fail_closed_without_user_approval(tmp_path: Path) -> None:
    _write(tmp_path / "brief.json", {"title": "t"})
    _write(tmp_path / "film-spec.json", _valid_film_spec())
    with pytest.raises(ProductionGateError):
        assert_pilot_allows_add(tmp_path, shot_id="shot04", existing_shot_ids={"shot01", "shot02", "shot03"})
