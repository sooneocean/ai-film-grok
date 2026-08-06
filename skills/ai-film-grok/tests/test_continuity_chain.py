#!/usr/bin/env python3
"""Long-form continuity_chain.md + byte-identical join gates."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from continuity_chain import (  # noqa: E402
    CODE_BYTE_MISMATCH,
    CODE_MISSING_CHAIN_DOC,
    check_continuity_chain,
    init_chain_doc,
    is_long_form,
    upsert_join,
)


def _spec(n: int = 6) -> dict:
    shots = []
    for i in range(1, n + 1):
        shots.append(
            {
                "id": f"shot{i:02d}",
                "dramatic_function": "action" if i < n else "afterglow",
                "nar": "测",
                "duration_sec": 6,
                "dsl": {
                    "action": "steps",
                    "motion": "steps forward, idle not speaking",
                    "start_pose": "a",
                    "end_pose": "b",
                    "chain_mode": "continue",
                },
            }
        )
    return {
        "title": "test-chain",
        "director_intent": {
            "logline": "测试长片动作链",
            "tone": "test",
            "emotional_arc": ["a", "b", "c"],
        },
        "scenes": [{"shots": shots}],
    }


def test_is_long_form_by_shot_count():
    assert is_long_form(_spec(6)) is True
    assert is_long_form(_spec(3)) is False


def test_is_long_form_flag():
    s = _spec(2)
    s["long_form"] = True
    assert is_long_form(s) is True


def test_missing_doc_hard_for_long():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        report = check_continuity_chain(root, _spec(6), require_doc_if_long=True)
        assert CODE_MISSING_CHAIN_DOC in report["codes"]
        assert report["ok"] is False


def test_init_creates_doc():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        path = init_chain_doc(root, _spec(6))
        assert path.is_file()
        text = path.read_text(encoding="utf-8")
        assert "Join: shot01 → shot02" in text
        assert "姿势 pose" in text
        report = check_continuity_chain(root, _spec(6))
        assert CODE_MISSING_CHAIN_DOC not in report["codes"]


def test_byte_mismatch_hard():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        init_chain_doc(root, _spec(6))
        upsert_join(
            root,
            from_id="shot01",
            to_id="shot02",
            mode="continue",
            last_sha="aaa",
            first_sha="bbb",
        )
        report = check_continuity_chain(root, _spec(6))
        assert CODE_BYTE_MISMATCH in report["codes"]
        assert report["ok"] is False


def test_byte_identical_ok():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        init_chain_doc(root, _spec(6))
        upsert_join(
            root,
            from_id="shot01",
            to_id="shot02",
            mode="continue",
            last_sha="same",
            first_sha="same",
        )
        report = check_continuity_chain(root, _spec(6))
        assert CODE_BYTE_MISMATCH not in report["codes"]
        assert report["ok"] is True
