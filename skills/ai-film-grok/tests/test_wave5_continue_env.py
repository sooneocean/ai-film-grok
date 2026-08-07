"""Wave 5 · continue handoff poison/redress block + env heuristic."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


class ContinueHandoffSafetyTests(unittest.TestCase):
    def test_resolve_blocks_poison_parent(self) -> None:
        from continue_handoff import resolve_continue_handoff

        root = Path(tempfile.mkdtemp())
        (root / "film-spec.json").write_text(
            json.dumps(
                {
                    "scenes": [
                        {
                            "shots": [
                                {
                                    "id": "a",
                                    "heat_phase": "act",
                                    "wardrobe_state": "bare",
                                },
                                {
                                    "id": "b",
                                    "parent_shot_id": "a",
                                    "dsl": {"chain_mode": "continue"},
                                    "heat_phase": "act",
                                    "wardrobe_state": "bare",
                                },
                            ]
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (root / "manifest.json").write_text(
            json.dumps(
                {
                    "stills": {
                        "a": {
                            "status": "approved",
                            "anatomy_safe": False,
                            "path": "x.png",
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        handoff = root / "receipts" / "continue-handoff"
        handoff.mkdir(parents=True)
        end = handoff / "a_end.png"
        end.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
        (handoff / "a.json").write_text(
            json.dumps(
                {
                    "ok": True,
                    "safe_for_continue": True,
                    "end_frame": str(end),
                    "shot_id": "a",
                }
            ),
            encoding="utf-8",
        )
        rep = resolve_continue_handoff(root, "b")
        self.assertFalse(rep.get("ok"))
        self.assertIn("POISON_SOURCE_STILL", rep.get("block_codes") or [])

    def test_resolve_blocks_meta_unsafe(self) -> None:
        from continue_handoff import resolve_continue_handoff

        root = Path(tempfile.mkdtemp())
        (root / "film-spec.json").write_text(
            json.dumps(
                {
                    "scenes": [
                        {
                            "shots": [
                                {"id": "p1"},
                                {
                                    "id": "p2",
                                    "dsl": {"chain_mode": "continue"},
                                    "parent_shot_id": "p1",
                                },
                            ]
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (root / "manifest.json").write_text("{}", encoding="utf-8")
        handoff = root / "receipts" / "continue-handoff"
        handoff.mkdir(parents=True)
        end = handoff / "p1_end.png"
        end.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
        (handoff / "p1.json").write_text(
            json.dumps(
                {
                    "ok": False,
                    "safe_for_continue": False,
                    "end_frame": str(end),
                    "block_codes": ["ENDFRAME_REDRESS_RISK"],
                    "shot_id": "p1",
                }
            ),
            encoding="utf-8",
        )
        rep = resolve_continue_handoff(root, "p2")
        self.assertFalse(rep.get("ok"))
        self.assertIn("ENDFRAME_REDRESS_RISK", rep.get("block_codes") or [])

    def test_write_marks_poison_source(self) -> None:
        from continue_handoff import write_continue_handoff

        root = Path(tempfile.mkdtemp())
        (root / "film-spec.json").write_text("{}", encoding="utf-8")
        (root / "manifest.json").write_text(
            json.dumps(
                {
                    "stills": {
                        "s1": {"status": "approved", "anatomy_safe": False}
                    }
                }
            ),
            encoding="utf-8",
        )
        # fake clip (write will fail extract but we mock)
        clip = root / "takes" / "s1.mp4"
        clip.parent.mkdir(parents=True)
        clip.write_bytes(b"\x00" * 64)
        with mock.patch(
            "spine.continue_handoff.subprocess.run"
        ) as run_mock:
            # force extract "success" by creating end png in side effect
            def _run(cmd, **kwargs):
                out = Path(cmd[-1])
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)

                class R:
                    returncode = 0

                return R()

            run_mock.side_effect = _run
            meta = write_continue_handoff(
                root,
                shot_id="s1",
                deliver=clip,
                shot={"id": "s1", "heat_phase": "act", "wardrobe_state": "bare"},
            )
        self.assertFalse(meta.get("safe_for_continue"))
        self.assertIn("POISON_SOURCE_STILL", meta.get("block_codes") or [])


class EnvHeuristicTests(unittest.TestCase):
    def test_df_env_without_role_is_t2v(self) -> None:
        from h3_mode import resolve_h3_mode

        r = resolve_h3_mode(
            {
                "id": "e1",
                "dramatic_function": "establishing",
                "heat_phase": "setup",
            },
            has_still=False,
        )
        self.assertEqual(r["mode"], "t2v")

    def test_shot_lane_env_heuristic(self) -> None:
        from shot_lane import resolve_shot_lane

        r = resolve_shot_lane(
            {
                "id": "e2",
                "dramatic_function": "bridge",
                "heat_phase": "setup",
            },
            has_still=False,
        )
        self.assertEqual(r["lane"], "env")
        self.assertEqual(r["h3_mode"], "t2v")


if __name__ == "__main__":
    unittest.main()
