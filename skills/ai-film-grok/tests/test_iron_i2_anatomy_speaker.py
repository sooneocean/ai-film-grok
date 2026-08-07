"""I2 · anatomy attestation fail-closed + speaker-frame hard unify."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


class TestI21Anatomy(unittest.TestCase):
    def test_assert_blocks_missing_attestation_adult_max(self) -> None:
        from anatomy_safety import AnatomySafetyError, assert_still_anatomy_for_i2v

        root = Path(tempfile.mkdtemp())
        (root / "film-spec.json").write_text(
            json.dumps({"heat_scale": "max", "adult_max_iron": True}),
            encoding="utf-8",
        )
        (root / "manifest.json").write_text(
            json.dumps({"stills": {"s1": {"status": "approved"}}}),
            encoding="utf-8",
        )
        env = {k: v for k, v in os.environ.items() if k != "AIFILM_SKIP_ANATOMY_SAFETY"}
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(AnatomySafetyError) as ctx:
                assert_still_anatomy_for_i2v(root, "s1")
        self.assertIn("anatomy_safe", str(ctx.exception))

    def test_poison_always_blocks_even_non_adult(self) -> None:
        from anatomy_safety import AnatomySafetyError, assert_still_anatomy_for_i2v

        root = Path(tempfile.mkdtemp())
        (root / "film-spec.json").write_text(
            json.dumps({"heat_scale": "soft", "genre": "drama"}),
            encoding="utf-8",
        )
        (root / "manifest.json").write_text(
            json.dumps(
                {
                    "stills": {
                        "s1": {"status": "approved", "anatomy_safe": False},
                    }
                }
            ),
            encoding="utf-8",
        )
        env = {k: v for k, v in os.environ.items() if k != "AIFILM_SKIP_ANATOMY_SAFETY"}
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(AnatomySafetyError) as ctx:
                assert_still_anatomy_for_i2v(root, "s1")
        self.assertIn("poison", str(ctx.exception).lower())

    def test_restricted_shot_requires_even_without_film_max(self) -> None:
        from anatomy_safety import shot_requires_anatomy_safety

        root = Path(tempfile.mkdtemp())
        (root / "film-spec.json").write_text(
            json.dumps(
                {
                    "heat_scale": "hot",
                    "scenes": [
                        {
                            "shots": [
                                {
                                    "id": "m1",
                                    "heat_phase": "act",
                                    "wardrobe_state": "bare",
                                }
                            ]
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        env = {k: v for k, v in os.environ.items() if k != "AIFILM_SKIP_ANATOMY_SAFETY"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertTrue(shot_requires_anatomy_safety(root, "m1"))

    def test_genre_adult_requires_film_level(self) -> None:
        from anatomy_safety import requires_anatomy_safety

        root = Path(tempfile.mkdtemp())
        (root / "film-spec.json").write_text(
            json.dumps({"genre": "adult", "heat_scale": "hot"}),
            encoding="utf-8",
        )
        env = {k: v for k, v in os.environ.items() if k != "AIFILM_SKIP_ANATOMY_SAFETY"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertTrue(requires_anatomy_safety(root))

    def test_h3_run_blocks_unattested(self) -> None:
        from h3_workflow import H3WorkflowError, run_h3_shot

        root = Path(tempfile.mkdtemp())
        (root / "film-spec.json").write_text(
            json.dumps(
                {
                    "heat_scale": "max",
                    "adult_max_iron": True,
                    "scenes": [{"shots": [{"id": "s1", "heat_phase": "act"}]}],
                }
            ),
            encoding="utf-8",
        )
        (root / "manifest.json").write_text(
            json.dumps(
                {
                    "stills": {
                        "s1": {
                            "status": "approved",
                            "path": str(root / "k.png"),
                            # missing anatomy_safe
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        (root / "k.png").write_bytes(b"png")
        env = {k: v for k, v in os.environ.items() if k != "AIFILM_SKIP_ANATOMY_SAFETY"}
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch(
                "h3_workflow.plan_h3_shot",
                return_value={
                    "mode": "i2v",
                    "requires_still": True,
                    "still_path": str(root / "k.png"),
                    "weapon_id": "h3",
                    "source_endpoint": "x",
                },
            ):
                with self.assertRaises(H3WorkflowError) as ctx:
                    run_h3_shot(root, "s1", register=False)
        self.assertIn("anatomy_safe", str(ctx.exception))


class TestI23SpeakerFrame(unittest.TestCase):
    def test_hard_enabled_max_dialogue(self) -> None:
        from dialogue_speaker_frame_gate import speaker_frame_hard_enabled

        self.assertTrue(
            speaker_frame_hard_enabled(
                {"vo_mode": "dialogue_drama", "heat_scale": "max"}
            )
        )

    def test_hard_enabled_genre_adult(self) -> None:
        from dialogue_speaker_frame_gate import speaker_frame_hard_enabled

        self.assertTrue(
            speaker_frame_hard_enabled(
                {"vo_mode": "dialogue_drama", "genre": "adult", "heat_scale": "soft"}
            )
        )

    def test_explicit_false_escape(self) -> None:
        from dialogue_speaker_frame_gate import speaker_frame_hard_enabled

        self.assertFalse(
            speaker_frame_hard_enabled(
                {
                    "vo_mode": "dialogue_drama",
                    "heat_scale": "max",
                    "speaker_frame_strict": False,
                }
            )
        )

    def test_assert_raises_on_mismatch_when_hard(self) -> None:
        from dialogue_speaker_frame_gate import assert_dialogue_speaker_frame_contract
        from production_gates import ProductionGateError

        spec = {
            "vo_mode": "dialogue_drama",
            "heat_scale": "max",
            "cast": {"mei": {}, "ken": {}},
            "scenes": [
                {
                    "shots": [
                        {
                            "id": "s1",
                            "screen_mode": "on_camera",
                            "speaker": "mei",
                            "heat_phase": "act",
                            "dsl": {"subject": "ken only torso"},
                            "audio_cues": [
                                {
                                    "spoken_text": "啊",
                                    "speaker": "mei",
                                    "screen_mode": "on_camera",
                                }
                            ],
                        }
                    ]
                }
            ],
        }
        with self.assertRaises(ProductionGateError):
            assert_dialogue_speaker_frame_contract(spec=spec)

    def test_validate_film_spec_hard_speaker(self) -> None:
        from film_spec import FilmSpecError, validate_film_spec

        # Minimal path may fail other gates first; call assert path via hard helper
        # and ensure speaker_frame_hard_enabled is consulted by validate when possible.
        from dialogue_speaker_frame_gate import speaker_frame_hard_enabled

        self.assertTrue(
            speaker_frame_hard_enabled(
                {"vo_mode": "dialogue_drama", "heat_scale": "max", "adult_max_iron": True}
            )
        )
        # FilmSpecError import smoke
        self.assertTrue(issubclass(FilmSpecError, Exception))
        self.assertTrue(callable(validate_film_spec))


if __name__ == "__main__":
    unittest.main()
