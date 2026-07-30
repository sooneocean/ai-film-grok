"""Production gates: pilot user-approval + loop-risk hard blocks."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from dialogue_benchmark import WEAPONS  # noqa: E402
from film_spec import RECOMMENDED_NAR_CHARS  # noqa: E402
from performance_candidates import sign_receipt  # noqa: E402
from production_gates import (  # noqa: E402
    ProductionGateError,
    assert_dialogue_drama_production_evidence,
    assert_no_loop_risk,
    assert_pilot_user_approved,
    loop_risk_shots_from_spec,
    pilot_is_user_approved,
)

_TEST_RECEIPT_KEY = "test-only-dialogue-receipt-key-32"


class PilotGateTests(unittest.TestCase):
    def test_agent_self_approve_rejected(self) -> None:
        self.assertFalse(
            pilot_is_user_approved({"approved": True, "approved_by": "agent", "notes": "self"})
        )

    def test_user_approve_ok(self) -> None:
        self.assertTrue(
            pilot_is_user_approved(
                {"approved": True, "approved_by": "user", "user_phrase": "pilot 过"}
            )
        )

    def test_assert_requires_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            with self.assertRaisesRegex(ProductionGateError, "missing|pilot"):
                assert_pilot_user_approved(root, env_skip=False)

    def test_allows_three_then_blocks_fourth(self) -> None:
        from production_gates import assert_pilot_allows_add

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            known: set[str] = set()
            for i in range(1, 4):
                sid = f"shot0{i}"
                assert_pilot_allows_add(root, shot_id=sid, existing_shot_ids=known, env_skip=False)
                known.add(sid)
            with self.assertRaisesRegex(ProductionGateError, "pilot"):
                assert_pilot_allows_add(
                    root, shot_id="shot04", existing_shot_ids=known, env_skip=False
                )

    def test_assert_accepts_user_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rec = root / "receipts"
            rec.mkdir()
            (rec / "pilot-approval.json").write_text(
                json.dumps(
                    {
                        "approved": True,
                        "approved_by": "user",
                        "user_phrase": "pilot 过",
                        "shots": ["shot01", "shot02", "shot03"],
                    }
                ),
                encoding="utf-8",
            )
            out = assert_pilot_user_approved(root, env_skip=False)
            self.assertTrue(out.get("ok"))


class DialogueEvidenceGateTests(unittest.TestCase):
    def _write_benchmark_fixture(self, root: Path) -> dict[str, object]:
        (root / "film-spec.json").write_text(
            json.dumps(
                {
                    "vo_mode": "dialogue_drama",
                    "dialogue_benchmark_required": True,
                }
            ),
            encoding="utf-8",
        )
        package = {
            "scenes": [
                {
                    "lines": [
                        {"line_id": "line-01"},
                        {"line_id": "line-02"},
                    ]
                }
            ]
        }
        (root / "dialogue-scene-package.json").write_text(
            json.dumps(package),
            encoding="utf-8",
        )
        arms = []
        artifact_dir = root / "benchmark-artifacts"
        artifact_dir.mkdir()
        for index, weapon in enumerate(WEAPONS):
            relative_artifact = Path("benchmark-artifacts") / f"arm-{index}.bin"
            artifact_bytes = f"reviewed-{weapon}".encode()
            (root / relative_artifact).write_bytes(artifact_bytes)
            arms.append(
                {
                    "weapon": weapon,
                    "status": "reviewed",
                    "artifact": str(relative_artifact),
                    "artifact_sha256": sha256(artifact_bytes).hexdigest(),
                    "reviewer": "human-reviewer",
                    "review_note": "reviewed fixed dialogue",
                    "stable_parameters": {"seed": index + 1},
                }
            )
        benchmark: dict[str, object] = {
            "schema_version": 1,
            "kind": "dialogue-weapon-benchmark",
            "status": "planned",
            "duration_sec": 45.0,
            "line_ids": ["line-01", "line-02"],
            "weapons": list(WEAPONS),
            "arms": arms,
            "selection": {
                "status": "approved",
                "reviewer": "human-approver",
                "rationale": "all fixed-line arms reviewed",
                "required_weapons": list(WEAPONS),
                "stable_parameters": {str(arm["weapon"]): arm["stable_parameters"] for arm in arms},
            },
        }
        with patch.dict(
            os.environ,
            {"AIFILM_AUDIO_RECEIPT_KEY": _TEST_RECEIPT_KEY},
            clear=False,
        ):
            sign_receipt(benchmark)
        receipts = root / "receipts"
        receipts.mkdir()
        (receipts / "dialogue-weapon-benchmark.json").write_text(
            json.dumps(benchmark),
            encoding="utf-8",
        )
        return benchmark

    def _assert_fixture(self, root: Path) -> dict[str, object]:
        with (
            patch.dict(
                os.environ,
                {"AIFILM_AUDIO_RECEIPT_KEY": _TEST_RECEIPT_KEY},
                clear=False,
            ),
            patch(
                "dialogue_scene_package.validate_dialogue_scene_package",
                return_value={"ok": True, "errors": []},
            ),
        ):
            return assert_dialogue_drama_production_evidence(root)

    def test_dialogue_final_requires_package_production_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "film-spec.json").write_text('{"vo_mode":"dialogue_drama"}', encoding="utf-8")
            (root / "dialogue-scene-package.json").write_text("{}", encoding="utf-8")
            with patch(
                "dialogue_scene_package.validate_dialogue_scene_package",
                return_value={"ok": False, "errors": [{"code": "LIPSYNC_EVIDENCE_MISSING"}]},
            ):
                with self.assertRaisesRegex(ProductionGateError, "LIPSYNC_EVIDENCE_MISSING"):
                    assert_dialogue_drama_production_evidence(root)

    def test_signed_benchmark_with_current_bound_arms_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_benchmark_fixture(root)
            self.assertTrue(self._assert_fixture(root).get("ok"))

    def test_forged_benchmark_signature_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark = self._write_benchmark_fixture(root)
            benchmark["receipt_hmac_sha256"] = "0" * 64
            (root / "receipts" / "dialogue-weapon-benchmark.json").write_text(
                json.dumps(benchmark),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ProductionGateError, "signed"):
                self._assert_fixture(root)

    def test_validly_signed_receipt_with_foreign_line_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark = self._write_benchmark_fixture(root)
            benchmark["line_ids"] = ["attacker-line"]
            with patch.dict(
                os.environ,
                {"AIFILM_AUDIO_RECEIPT_KEY": _TEST_RECEIPT_KEY},
                clear=False,
            ):
                sign_receipt(benchmark)
            (root / "receipts" / "dialogue-weapon-benchmark.json").write_text(
                json.dumps(benchmark),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ProductionGateError, "same 30"):
                self._assert_fixture(root)

    def test_artifact_changed_after_signed_review_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark = self._write_benchmark_fixture(root)
            first_arm = benchmark["arms"][0]
            (root / first_arm["artifact"]).write_bytes(b"attacker replacement")
            with self.assertRaisesRegex(ProductionGateError, "artifact hashes"):
                self._assert_fixture(root)

    def test_signed_approval_parameters_must_match_reviewed_arms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark = self._write_benchmark_fixture(root)
            first_weapon = WEAPONS[0]
            benchmark["selection"]["stable_parameters"][first_weapon] = {"seed": 999}
            with patch.dict(
                os.environ,
                {"AIFILM_AUDIO_RECEIPT_KEY": _TEST_RECEIPT_KEY},
                clear=False,
            ):
                sign_receipt(benchmark)
            (root / "receipts" / "dialogue-weapon-benchmark.json").write_text(
                json.dumps(benchmark),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ProductionGateError, "stable-parameter"):
                self._assert_fixture(root)

    def test_receipts_parent_symlink_cannot_escape_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside_tmp:
            root = Path(tmp)
            outside = Path(outside_tmp)
            benchmark = self._write_benchmark_fixture(root)
            receipt = root / "receipts" / "dialogue-weapon-benchmark.json"
            outside_receipt = outside / receipt.name
            outside_receipt.write_text(json.dumps(benchmark), encoding="utf-8")
            receipt.unlink()
            (root / "receipts").rmdir()
            (root / "receipts").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ProductionGateError, "unsafe benchmark receipt"):
                self._assert_fixture(root)

    def test_package_changed_during_descriptor_read_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "film-spec.json").write_text(
                '{"vo_mode":"dialogue_drama"}',
                encoding="utf-8",
            )
            package_path = root / "dialogue-scene-package.json"
            package_path.write_text('{"scenes":[]}', encoding="utf-8")
            package_inode = package_path.stat().st_ino
            original_read = os.read
            changed = False

            def racing_read(file_fd: int, size: int) -> bytes:
                nonlocal changed
                chunk = original_read(file_fd, size)
                if chunk and not changed and os.fstat(file_fd).st_ino == package_inode:
                    changed = True
                    package_path.write_text('{"attacker":true}', encoding="utf-8")
                return chunk

            with (
                patch("production_gates.os.read", side_effect=racing_read),
                patch(
                    "dialogue_scene_package.validate_dialogue_scene_package",
                    return_value={"ok": True, "errors": []},
                ),
                self.assertRaisesRegex(ProductionGateError, "unsafe dialogue-scene-package"),
            ):
                assert_dialogue_drama_production_evidence(root)


class LoopRiskGateTests(unittest.TestCase):
    def test_long_nar_is_risk(self) -> None:
        spec = {
            "scenes": [
                {
                    "shots": [
                        {
                            "id": "shot01",
                            "nar": "字" * 40,
                            "duration_sec": 6,
                        }
                    ]
                }
            ]
        }
        risk = loop_risk_shots_from_spec(spec)
        self.assertIn("shot01", risk)

    def test_short_nar_ok(self) -> None:
        spec = {
            "scenes": [
                {
                    "shots": [
                        {
                            "id": "shot01",
                            "nar": "夜深，她推门进来。",
                            "duration_sec": 6,
                        }
                    ]
                }
            ]
        }
        self.assertEqual(loop_risk_shots_from_spec(spec), [])
        self.assertLessEqual(len("夜深，她推门进来。"), RECOMMENDED_NAR_CHARS + 5)

    def test_assert_blocks(self) -> None:
        with tempfile.TemporaryDirectory():
            # minimal invalid for validate — use force path with prebuilt risk via direct assert
            with self.assertRaises(ProductionGateError):
                assert_no_loop_risk(
                    spec={
                        "scenes": [
                            {
                                "shots": [
                                    {
                                        "id": "shot09",
                                        "nar": "旁" * 36,
                                        "duration_sec": 6,
                                    }
                                ]
                            }
                        ]
                    },
                    env_skip=False,
                )


if __name__ == "__main__":
    unittest.main()
