"""gate-auto: machine verification without human click-loop."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from gate_auto import (  # noqa: E402
    HUMAN_ONLY,
    auto_inject_sex_sfx,
    run_gate_auto,
)


def test_human_only_list_stable() -> None:
    assert "pilot_user_approval" in HUMAN_ONLY
    assert "review_final_scorecard" in HUMAN_ONLY


def test_sex_sfx_auto_inject(tmp_path: Path) -> None:
    spec = {
        "heat_scale": "max",
        "vo_mode": "dialogue_drama",
        "sound_plan": {"events": []},
        "scenes": [
            {
                "shots": [
                    {
                        "id": "m1",
                        "heat_phase": "act",
                        "dsl": {"motion": "thrust", "action": "thrust"},
                    }
                ]
            }
        ],
    }
    (tmp_path / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
    rep = auto_inject_sex_sfx(tmp_path)
    assert rep.get("ok") is True
    data = json.loads((tmp_path / "film-spec.json").read_text(encoding="utf-8"))
    events = (data.get("sound_plan") or {}).get("events") or []
    assert any(isinstance(e, dict) and e.get("sex_sfx") for e in events)


def test_gate_auto_writes_receipt(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(
        json.dumps({"clips": {}, "gates": {}}), encoding="utf-8"
    )
    (tmp_path / "film-spec.json").write_text(
        json.dumps(
            {
                "vo_mode": "storyteller",
                "dramatic_meaning_strict": False,
                "scenes": [{"shots": []}],
            }
        ),
        encoding="utf-8",
    )
    rep = run_gate_auto(
        tmp_path,
        write=True,
        measure_i2v=False,  # no clips — skip ffmpeg mean
        run_variety=False,
        promote_single=False,
    )
    assert (tmp_path / "receipts" / "gate-auto.json").is_file()
    assert "steps" in rep
    assert "human_only_forever" in rep


def test_gate_auto_skip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFILM_SKIP_GATE_AUTO", "1")
    rep = run_gate_auto(tmp_path, write=True)
    assert rep.get("skipped") is True
    assert rep.get("ok") is True
    monkeypatch.delenv("AIFILM_SKIP_GATE_AUTO", raising=False)


def test_gate_auto_on_advance_and_w8_allowlist() -> None:
    from advance import ADVANCE_ACTIONS
    from autopilot import LOCAL_THROUGHPUT_NEXT_IDS
    from dispatch import _ACTION_SKILLS, _COMMAND_POLICIES

    assert "gate-auto" in ADVANCE_ACTIONS
    assert "gate-auto" in LOCAL_THROUGHPUT_NEXT_IDS
    assert "cinematic-gate" in ADVANCE_ACTIONS
    assert "cinematic-gate" in LOCAL_THROUGHPUT_NEXT_IDS
    assert _ACTION_SKILLS.get("gate-auto") == "projection.verify"
    assert _COMMAND_POLICIES.get("gate-auto") == ("local", "none")
    assert _COMMAND_POLICIES.get("cinematic-gate") == ("local", "none")


def test_gate_auto_advance_argv(tmp_path: Path) -> None:
    from advance import _validate_argv

    root = tmp_path.resolve()
    _validate_argv(
        root=root,
        action_id="gate-auto",
        action={
            "spend_class": "local",
            "approval_class": "none",
            "skill_id": "projection.verify",
            "argv": ["gate-auto", "--root", str(root)],
        },
    )


def test_machine_receipts_green_and_fast_path(tmp_path: Path) -> None:
    from gate_auto import machine_receipts_green, run_gate_auto

    rec = tmp_path / "receipts"
    rec.mkdir(parents=True)
    (rec / "gate-auto.json").write_text(
        json.dumps({"ok": True, "kind": "gate-auto", "steps": []}), encoding="utf-8"
    )
    (rec / "i2v-final-gate.json").write_text(
        json.dumps({"ok": True, "kind": "i2v-final-gate"}), encoding="utf-8"
    )
    (rec / "cinematic-gate.json").write_text(
        json.dumps({"ok": True, "kind": "cinematic-gate"}), encoding="utf-8"
    )
    st = machine_receipts_green(tmp_path)
    assert st["ok"] is True
    rep = run_gate_auto(tmp_path, write=True, force=False)
    assert rep.get("fast_path") is True
    assert rep.get("ok") is True
    # force re-runs ladder (may soft-pass empty film)
    rep2 = run_gate_auto(
        tmp_path,
        write=True,
        force=True,
        measure_i2v=False,
        run_variety=False,
        promote_single=False,
    )
    assert rep2.get("fast_path") is not True


def test_i2v_soft_when_no_clips(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(
        json.dumps({"clips": {}, "gates": {}}), encoding="utf-8"
    )
    (tmp_path / "film-spec.json").write_text(
        json.dumps(
            {
                "vo_mode": "storyteller",
                "dramatic_meaning_strict": False,
                "scenes": [{"shots": []}],
            }
        ),
        encoding="utf-8",
    )
    rep = run_gate_auto(
        tmp_path,
        write=True,
        force=True,
        promote_single=False,
        run_variety=False,
        run_cinematic=False,
    )
    i2v = next(s for s in rep["steps"] if s["id"] == "i2v_motion")
    assert i2v["ok"] is True
    assert i2v["hard"] is False
