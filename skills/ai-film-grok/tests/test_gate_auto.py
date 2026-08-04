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
