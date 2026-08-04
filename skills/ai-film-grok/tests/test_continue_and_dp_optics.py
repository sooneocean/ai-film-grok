#!/usr/bin/env python3
"""go4 Grok continue-handoff + go5 DP focal inject (v2.37.2)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from continue_handoff import (  # noqa: E402
    resolve_continue_handoff,
    shot_wants_continue,
    write_continue_handoff,
)
from motion_prompt_spine import camera_clause, focal_clause, motion_core_clauses  # noqa: E402
from prompt_injector import PromptInjector  # noqa: E402


class FocalDpTests(unittest.TestCase):
    def test_cu_gets_85mm(self) -> None:
        shot = {"id": "s1", "shot_size": "cu", "dsl": {"action": "blinks"}}
        f = focal_clause(shot)
        self.assertIn("85mm", f)
        cam = camera_clause(shot)
        self.assertIn("85mm", cam)

    def test_wide_gets_35mm(self) -> None:
        shot = {"id": "s1", "dsl": {"camera": {"shot_size": "wide"}}}
        self.assertIn("35mm", focal_clause(shot))

    def test_insert_gets_105mm(self) -> None:
        shot = {"id": "s1", "shot_size": "insert"}
        self.assertIn("105mm", focal_clause(shot))

    def test_author_lens_wins(self) -> None:
        shot = {
            "id": "s1",
            "shot_size": "cu",
            "dsl": {"lens_mm": 40, "camera_prompt": "handheld"},
        }
        f = focal_clause(shot)
        self.assertIn("40mm", f)
        self.assertIn("author lock", f)

    def test_spine_includes_focal(self) -> None:
        shot = {
            "id": "s1",
            "dramatic_function": "reaction",
            "shot_size": "cu",
            "dsl": {"action": "eyes widen"},
        }
        clauses = motion_core_clauses({}, shot, include_audio=False)
        joined = " ".join(clauses)
        self.assertIn("85mm", joined)


class ContinueSharedTests(unittest.TestCase):
    def test_wants_continue(self) -> None:
        self.assertTrue(
            shot_wants_continue({"dsl": {"chain_mode": "continue"}})
        )
        self.assertTrue(shot_wants_continue({"parent_shot_id": "a1"}))
        self.assertFalse(shot_wants_continue({"dsl": {"chain_mode": "cut"}}))

    def test_write_missing_clip_ok_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta = write_continue_handoff(
                root,
                shot_id="a1",
                deliver=root / "missing.mp4",
                shot={"id": "a1", "dramatic_function": "action"},
                engine="grok",
            )
            self.assertFalse(meta["ok"])
            self.assertEqual(meta["engine"], "grok")
            self.assertTrue(
                (root / "receipts" / "continue-handoff" / "a1.json").is_file()
            )

    def test_resolve_uses_prev_endframe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "film-spec.json").write_text(
                json.dumps(
                    {
                        "scenes": [
                            {
                                "shots": [
                                    {"id": "a1"},
                                    {
                                        "id": "b1",
                                        "parent_shot_id": "a1",
                                        "dsl": {"chain_mode": "continue"},
                                    },
                                ]
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            handoff = root / "receipts" / "continue-handoff"
            handoff.mkdir(parents=True)
            end = handoff / "a1_end.png"
            end.write_bytes(b"PNG")
            (handoff / "a1.json").write_text(
                json.dumps(
                    {
                        "ok": True,
                        "shot_id": "a1",
                        "engine": "grok",
                        "end_frame": str(end),
                    }
                ),
                encoding="utf-8",
            )
            resolved = resolve_continue_handoff(root, "b1")
            self.assertTrue(resolved["ok"])
            self.assertTrue(resolved["wants_continue"])
            self.assertIn("CONTINUE", resolved.get("prompt_clause") or "")

    def test_injector_prepends_continue_clause(self) -> None:
        inj = PromptInjector(
            {
                "schema_version": 1,
                "state": "locked",
                "style_signature": "cel anime",
                "heat_scale": "soft",
            },
            template_version="I2V",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "film-spec.json").write_text(
                json.dumps(
                    {
                        "scenes": [
                            {
                                "shots": [
                                    {"id": "a1"},
                                    {
                                        "id": "b1",
                                        "parent_shot_id": "a1",
                                        "dsl": {
                                            "chain_mode": "continue",
                                            "action": "steps forward slowly",
                                        },
                                        "dramatic_function": "action",
                                    },
                                ]
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            handoff = root / "receipts" / "continue-handoff"
            handoff.mkdir(parents=True)
            end = handoff / "a1_end.png"
            end.write_bytes(b"PNG")
            (handoff / "a1.json").write_text(
                json.dumps({"ok": True, "end_frame": str(end), "shot_id": "a1"}),
                encoding="utf-8",
            )
            shot = {
                "id": "b1",
                "parent_shot_id": "a1",
                "dramatic_function": "action",
                "dsl": {"chain_mode": "continue", "action": "steps forward slowly"},
            }
            out = inj.assemble(shot, root)
            text = out.get("prompt_text") or ""
            self.assertIn("CONTINUE from previous end frame", text)


if __name__ == "__main__":
    unittest.main()
