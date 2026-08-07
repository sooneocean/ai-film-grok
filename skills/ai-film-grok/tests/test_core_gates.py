"""C6.4 base contracts for core.gates.recompute_gates (empty → partial film)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from core.constants import GATE_ORDER  # noqa: E402
from core.film_io import empty_manifest, ensure_tree  # noqa: E402
from core.gates import recompute_gates  # noqa: E402

# Expected gate keys written onto the summary / manifest.
_REQUIRED_GATE_KEYS = frozenset(GATE_ORDER) | {
    "manifest_current",
    "brief",
    "style_locked",
    "spec",
    "canonical",
    "stills_complete",
    "clips_complete",
    "assembled",
    "reshoots_clear",
    "final_complete",
    "desktop_exported",
}


def _minimal_spec(*shot_ids: str) -> dict:
    shots = [
        {
            "id": sid,
            "dramatic_function": "hook",
            "nar": "旁白。",
            "duration_sec": 6,
            "dsl": {"subject": "a", "action": "b", "motion": "slow push-in"},
        }
        for sid in shot_ids
    ]
    return {
        "title": "gate-test",
        "vo_mode": "storyteller",
        "tts_backend": "edge",
        "dramatic_meaning_strict": False,
        "director_intent": {
            "logline": "完整承诺句用于门禁测。",
            "tone": "色气",
            "emotional_arc": ["a", "b", "c"],
        },
        "sound_plan": {"mood": "rnb"},
        "scenes": [{"shots": shots}],
    }


def test_recompute_gates_empty_root_all_closed(tmp_path: Path) -> None:
    ensure_tree(tmp_path)
    man = empty_manifest(title="t", theme="x", aspect="9:16")
    summary = recompute_gates(tmp_path, man)
    gates = summary["gates"]
    assert _REQUIRED_GATE_KEYS.issubset(gates.keys())
    # empty film: no brief / no valid spec shots / no finals
    assert gates["brief"] is False
    assert gates["spec"] is False
    assert gates["stills_complete"] is False
    assert gates["clips_complete"] is False
    assert gates["assembled"] is False
    assert gates["final_complete"] is False
    assert gates["desktop_exported"] is False
    # side-effect: gates written onto manifest
    assert man["gates"] == gates
    assert summary["shot_ids"] == []
    assert summary["open_reshoot_count"] == 0


def test_recompute_gates_brief_and_spec_flip(tmp_path: Path) -> None:
    ensure_tree(tmp_path)
    man = empty_manifest(title="t", theme="x", aspect="9:16")
    (tmp_path / "brief.json").write_text("{}", encoding="utf-8")
    (tmp_path / "film-spec.json").write_text(
        json.dumps(_minimal_spec("shot01", "shot02"), ensure_ascii=False),
        encoding="utf-8",
    )
    summary = recompute_gates(tmp_path, man)
    gates = summary["gates"]
    assert gates["brief"] is True
    assert gates["spec"] is True
    assert set(summary["shot_ids"]) >= {"shot01", "shot02"}
    # stills/clips still incomplete without approved media
    assert gates["stills_complete"] is False
    assert gates["clips_complete"] is False
    assert gates["final_complete"] is False


def test_recompute_gates_invalid_spec_sets_error(tmp_path: Path) -> None:
    ensure_tree(tmp_path)
    man = empty_manifest(title="t", theme="x", aspect="9:16")
    (tmp_path / "film-spec.json").write_text(
        json.dumps({"title": "broken", "scenes": []}),
        encoding="utf-8",
    )
    summary = recompute_gates(tmp_path, man)
    # may fail validate_film_spec → empty shots + optional spec_error
    assert summary["gates"]["spec"] is False
    assert summary["shot_ids"] == [] or summary.get("spec_error")
