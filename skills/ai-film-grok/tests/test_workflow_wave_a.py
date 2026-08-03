"""Wave A workflow: closeout run + pilot pack + next prefers closeout."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from closeout import closeout_run, closeout_status  # noqa: E402
from next_actions import build_next_actions  # noqa: E402
from pilot_pack import assert_pilot_go_allows_bulk, pilot_pack  # noqa: E402
from production_gates import ProductionGateError  # noqa: E402
from util import write_json  # noqa: E402


def _min_spec(*, heat: str = "max") -> dict:
    return {
        "title": "wave-a",
        "heat_scale": heat,
        "scenes": [
            {
                "title": "s1",
                "shots": [
                    {
                        "id": "shot01",
                        "dramatic_function": "hook",
                        "coitus_beat": "undress",
                        "heat_phase": "foreplay",
                        "nar": "旁白一",
                        "dsl": {"subject": "a", "action": "walk", "motion": "walk"},
                    },
                    {
                        "id": "shot02",
                        "dramatic_function": "action",
                        "coitus_beat": "union",
                        "heat_phase": "act",
                        "nar": "旁白二",
                        "dsl": {"subject": "a", "action": "hold", "motion": "thrust"},
                    },
                    {
                        "id": "shot03",
                        "dramatic_function": "action",
                        "coitus_beat": "rhythm",
                        "heat_phase": "climax",
                        "nar": "旁白三",
                        "dsl": {"subject": "a", "action": "finish", "motion": "finish"},
                    },
                ],
            }
        ],
    }


class CloseoutTests(unittest.TestCase):
    def test_status_blocks_without_plate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(root / "manifest.json", {"gates": {}, "outputs": {}})
            write_json(root / "film-spec.json", _min_spec(heat="soft"))
            st = closeout_status(root)
            self.assertFalse(st["ok"])
            self.assertEqual(st["blocked_by"], "plate_or_final")
            self.assertIn("final", st["next_cmd"] or "")

    def test_run_stops_at_review_when_plate_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "out"
            out.mkdir()
            plate = out / "film_final.mp4"
            plate.write_bytes(b"fake")
            write_json(
                root / "manifest.json",
                {
                    "gates": {"final_complete": False, "clips_complete": True},
                    "outputs": {"final_film": {"path": str(plate)}},
                },
            )
            write_json(root / "film-spec.json", _min_spec(heat="soft"))
            report = closeout_run(root, execute=True)
            self.assertFalse(report["ok"])
            self.assertEqual(report["stopped_at"], "final_complete")
            self.assertIn("review-final", report["next_cmd"] or "")
            self.assertTrue((root / "receipts" / "closeout.json").is_file())

    def test_next_actions_prefers_closeout_when_final_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plate = root / "out" / "film_final.mp4"
            plate.parent.mkdir(parents=True)
            plate.write_bytes(b"x")
            write_json(root / "brief.json", {"title": "wave-a", "theme": "test"})
            write_json(
                root / "manifest.json",
                {
                    "gates": {
                        "brief": True,
                        "style_locked": True,
                        "spec": True,
                        "clips_complete": True,
                        "final_complete": False,
                        "desktop_exported": False,
                    },
                    "outputs": {"final_film": {"path": str(plate)}},
                    "clips": {"shot01": {"status": "approved", "path": str(plate)}},
                },
            )
            write_json(root / "film-spec.json", _min_spec(heat="soft"))
            write_json(root / "post-plan.json", {"owner": "hyperframes"})
            write_json(
                root / "receipts" / "pilot-approval.json",
                {"approved": True, "approved_by": "user", "user_phrase": "pilot 过", "shots": ["shot01"]},
            )
            gates = {
                "brief": True,
                "style_locked": True,
                "spec": True,
                "clips_complete": True,
                "final_complete": False,
                "desktop_exported": False,
            }
            actions = build_next_actions(root, gates=gates)
            ids = [a.get("id") for a in actions]
            self.assertIn("closeout-run", ids)
            self.assertIn("review-final", ids)
            self.assertLess(ids.index("closeout-run"), ids.index("review-final"))


class PilotPackTests(unittest.TestCase):
    def test_pack_fails_closed_without_media(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(root / "film-spec.json", _min_spec())
            write_json(root / "manifest.json", {"stills": {}, "clips": {}, "gates": {}})
            pack = pilot_pack(root)
            self.assertFalse(pack["ok"])
            self.assertIn("PILOT_MEDIA_NOT_READY", pack["pilot_go"]["blockers"])
            self.assertTrue(Path(pack["receipt_path"]).is_file())

    def test_pack_three_beat_detects_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(root / "film-spec.json", _min_spec())
            write_json(root / "manifest.json", {"stills": {}, "clips": {}, "gates": {}})
            pack = pilot_pack(root, shots=["shot01", "shot02", "shot03"])
            self.assertTrue(pack["adult_three_beat"]["three_beat_ok"])
            self.assertTrue(pack["adult_three_beat"]["has_undress"])
            self.assertTrue(pack["adult_three_beat"]["has_union"])
            self.assertTrue(pack["adult_three_beat"]["has_rhythm"])

    def test_pilot_go_gate_blocks_when_ok_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(
                root / "receipts" / "pilot-go.json",
                {"ok": False, "pilot_go": {"ok": False, "blockers": ["PILOT_NOT_USER_APPROVED"]}},
            )
            with self.assertRaises(ProductionGateError):
                assert_pilot_go_allows_bulk(root)


if __name__ == "__main__":
    unittest.main()
