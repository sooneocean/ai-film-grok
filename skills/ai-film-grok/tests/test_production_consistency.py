"""P2-2~P2-6: production consistency lint — wardrobe/hair/makeup/light/rhythm/lipsync/voice drift.

Covers the "考验三件套" for lint_production_consistency:
  ① schema field   (cast_locks / hair_swatches / makeup / wardrobe_variants)
  ② lint/metric    (lint_production_consistency → 7 drift codes)
  ③ gate           (preflight soft → hard with production_consistency_strict; write-spec raise)
  ④ test           (this file)

This lint was dead code (zero callers, zero tests) before P1 activation.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from continuity import (  # noqa: E402
    CODE_CAMERA_RHYTHM_FLAT,
    CODE_HAIR_DRIFT,
    CODE_LIPSYNC_DRIFT,
    CODE_MAKEUP_DRIFT,
    CODE_SCENE_LIGHT_DRIFT,
    CODE_VOICE_CHARACTER_MISMATCH,
    CODE_WARDROBE_DRIFT,
    lint_production_consistency,
)
from film_spec import FilmSpecError, validate_film_spec  # noqa: E402

# ─── helpers ──────────────────────────────────────────────────────────────


def _shot(
    sid: str,
    *,
    cast: list[str] | None = None,
    wardrobe_state: str = "",
    location: str = "",
    lighting: str = "",
    camera_axis: str = "",
    lipsync: bool = False,
    lipsync_quality_score: int | None = None,
    vo_voice: str = "",
    nar: str = "",
    dramatic_function: str = "approach",
    dsl: dict | None = None,
) -> dict:
    """Build a shot dict with the minimal fields validate_film_spec requires."""
    sh: dict = {
        "id": sid,
        "dramatic_function": dramatic_function,
        "nar": nar or f"旁白{sid[-2:] if sid[-2:].isdigit() else '01'}。",
        "dsl": {
            "subject": "woman",
            "cast": cast if cast is not None else ["heroine"],
            "camera": {"shot_size": "medium"},
            "motion": "slow push-in, blink, idle not speaking",
        },
    }
    if wardrobe_state:
        sh["wardrobe_state"] = wardrobe_state
    if location:
        sh["locationId"] = location
    if lighting:
        sh["lighting"] = lighting
    if camera_axis:
        sh["camera_axis"] = camera_axis
    if lipsync:
        sh["lipsync"] = True
    if lipsync_quality_score is not None:
        sh["lipsync_quality_score"] = lipsync_quality_score
    if vo_voice:
        sh["vo_voice"] = vo_voice
    if dsl:
        sh.setdefault("dsl", {}).update(dsl)
    return sh


def _bible(
    *,
    cast_locks: dict | None = None,
    hair_swatches: dict | None = None,
    makeup: dict | None = None,
    wardrobe_variants: dict | None = None,
) -> dict:
    b: dict = {}
    if cast_locks is not None:
        b["cast_locks"] = cast_locks
    if hair_swatches is not None:
        b["hair_swatches"] = hair_swatches
    if makeup is not None:
        b["makeup"] = makeup
    if wardrobe_variants is not None:
        b["wardrobe_variants"] = wardrobe_variants
    return b


def _minimal_spec(shots: list[dict]) -> dict:
    """Build a minimal film-spec that passes validation up to production_consistency."""
    return {
        "schema_version": 1,
        "title": "test",
        "vo_mode": "storyteller",
        "aspect": "9:16",
        "director_intent": {
            "logline": "A test film about consistency.",
            "tone": "neutral",
            "emotional_arc": ["a", "b", "c"],
        },
        "transition_sec": 0.25,
        "transition_default": "soft",
        "scenes": [
            {
                "shots": shots,
            }
        ],
    }


# ─── ① lint: 7 drift codes ────────────────────────────────────────────────


class TestProductionConsistencyCodes(unittest.TestCase):
    """Each of the 7 codes fires on its drift condition."""

    def test_scene_light_drift_same_location_different_lighting(self):
        """Same locationId, different lighting → SCENE_LIGHT_DRIFT."""
        shots = [
            _shot("shot01", location="alley", lighting="warm sunset"),
            _shot("shot02", location="alley", lighting="cold blue night"),
        ]
        rep = lint_production_consistency(shots)
        self.assertIn(CODE_SCENE_LIGHT_DRIFT, rep["codes"])
        self.assertFalse(rep["ok"])

    def test_scene_light_no_drift_same_lighting(self):
        shots = [
            _shot("shot01", location="alley", lighting="warm sunset"),
            _shot("shot02", location="alley", lighting="warm sunset"),
        ]
        rep = lint_production_consistency(shots)
        self.assertNotIn(CODE_SCENE_LIGHT_DRIFT, rep["codes"])

    def test_camera_rhythm_flat_all_same_axis(self):
        """All ≥4 shots use same camera_axis → CAMERA_RHYTHM_FLAT."""
        shots = [
            _shot("shot01", camera_axis="push-in"),
            _shot("shot02", camera_axis="push-in"),
            _shot("shot03", camera_axis="push-in"),
            _shot("shot04", camera_axis="push-in"),
        ]
        rep = lint_production_consistency(shots)
        self.assertIn(CODE_CAMERA_RHYTHM_FLAT, rep["codes"])

    def test_camera_rhythm_ok_varied(self):
        shots = [
            _shot("shot01", camera_axis="push-in"),
            _shot("shot02", camera_axis="pan-right"),
            _shot("shot03", camera_axis="push-in"),
            _shot("shot04", camera_axis="tilt-down"),
        ]
        rep = lint_production_consistency(shots)
        self.assertNotIn(CODE_CAMERA_RHYTHM_FLAT, rep["codes"])

    def test_camera_rhythm_ok_under_threshold(self):
        """3 shots same axis is OK (threshold is ≥4)."""
        shots = [
            _shot("shot01", camera_axis="push-in"),
            _shot("shot02", camera_axis="push-in"),
            _shot("shot03", camera_axis="push-in"),
        ]
        rep = lint_production_consistency(shots)
        self.assertNotIn(CODE_CAMERA_RHYTHM_FLAT, rep["codes"])

    def test_lipsync_drift_no_quality_score(self):
        """lipsync=True but no lipsync_quality_score → LIPSYNC_DRIFT."""
        shots = [
            _shot("shot01", lipsync=True, lipsync_quality_score=None),
            _shot("shot02", lipsync=True, lipsync_quality_score=85),
        ]
        rep = lint_production_consistency(shots)
        self.assertIn(CODE_LIPSYNC_DRIFT, rep["codes"])
        # shot02 has score → no drift on it
        drift_shots = [i["shot_ids"] for i in rep["issues"] if i["code"] == CODE_LIPSYNC_DRIFT]
        self.assertEqual(drift_shots, [["shot01"]])

    def test_voice_character_mismatch(self):
        """Same character, different vo_voice → VOICE_CHARACTER_MISMATCH."""
        shots = [
            _shot("shot01", cast=["hero"], vo_voice="nanami"),
            _shot("shot02", cast=["hero"], vo_voice="keita"),
        ]
        rep = lint_production_consistency(shots)
        self.assertIn(CODE_VOICE_CHARACTER_MISMATCH, rep["codes"])

    def test_voice_character_ok_same_voice(self):
        shots = [
            _shot("shot01", cast=["hero"], vo_voice="nanami"),
            _shot("shot02", cast=["hero"], vo_voice="nanami"),
        ]
        rep = lint_production_consistency(shots)
        self.assertNotIn(CODE_VOICE_CHARACTER_MISMATCH, rep["codes"])

    def test_wardrobe_drift_code_constant_exists(self):
        """The WARDROBE_DRIFT code is importable (was dead code before P1)."""
        self.assertEqual(CODE_WARDROBE_DRIFT, "WARDROBE_DRIFT")
        self.assertEqual(CODE_HAIR_DRIFT, "HAIR_DRIFT")
        self.assertEqual(CODE_MAKEUP_DRIFT, "MAKEUP_DRIFT")

    def test_clean_shots_no_issues(self):
        """A clean set of shots produces no issues."""
        shots = [
            _shot(
                "shot01",
                cast=["hero"],
                camera_axis="push-in",
                location="alley",
                lighting="warm",
                vo_voice="nanami",
            ),
            _shot(
                "shot02",
                cast=["hero"],
                camera_axis="pan-right",
                location="alley",
                lighting="warm",
                vo_voice="nanami",
            ),
        ]
        rep = lint_production_consistency(shots)
        self.assertTrue(rep["ok"])
        self.assertEqual(rep["warning_count"], 0)
        self.assertEqual(rep["codes"], [])

    def test_empty_shots(self):
        rep = lint_production_consistency([])
        self.assertTrue(rep["ok"])

    def test_returns_expected_shape(self):
        rep = lint_production_consistency([_shot("shot01")])
        for key in ("ok", "issues", "codes", "warning_count", "error_count", "note"):
            self.assertIn(key, rep)


# ─── ② gate: write-spec strict raise ──────────────────────────────────────


class TestWriteSpecGate(unittest.TestCase):
    """production_consistency_strict=True → FilmSpecError when drift detected."""

    def test_strict_raises_on_light_drift(self):
        shots = [
            _shot("shot01", location="alley", lighting="warm"),
            _shot("shot02", location="alley", lighting="cold"),
        ]
        spec = _minimal_spec(shots)
        spec["production_consistency_strict"] = True
        with self.assertRaises(FilmSpecError) as ctx:
            validate_film_spec(spec, assign_missing_ids=False)
        self.assertIn("production_consistency_strict", str(ctx.exception))

    def test_non_strict_no_raise_on_light_drift(self):
        shots = [
            _shot("shot01", location="alley", lighting="warm"),
            _shot("shot02", location="alley", lighting="cold"),
        ]
        spec = _minimal_spec(shots)
        # Default: no production_consistency_strict → should not raise
        validate_film_spec(spec, assign_missing_ids=False)
        # The report is attached to spec (mutated in place)
        pcr = spec.get("_production_consistency") or {}
        self.assertIn(CODE_SCENE_LIGHT_DRIFT, pcr.get("codes", []))
        self.assertFalse(pcr.get("ok", True))

    def test_strict_passes_on_clean_shots(self):
        shots = [
            _shot("shot01", camera_axis="push-in", location="alley", lighting="warm"),
            _shot("shot02", camera_axis="pan-right", location="alley", lighting="warm"),
        ]
        spec = _minimal_spec(shots)
        spec["production_consistency_strict"] = True
        validate_film_spec(spec, assign_missing_ids=False)
        pcr = spec.get("_production_consistency") or {}
        self.assertTrue(pcr.get("ok"))


# ─── ③ gate: preflight soft → hard ────────────────────────────────────────


class TestPreflightGate(unittest.TestCase):
    """preflight reports production_consistency_drift as soft (default) / hard (strict)."""

    def _make_root(self, shots: list[dict], *, strict: bool = False) -> Path:
        import json

        tmp = tempfile.mkdtemp(prefix="aifilm_pc_test_")
        root = Path(tmp)
        spec = _minimal_spec(shots)
        if strict:
            spec["production_consistency_strict"] = True
        (root / "film-spec.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        return root

    def test_preflight_soft_on_light_drift_default(self):
        import preflight

        shots = [
            _shot("shot01", location="alley", lighting="warm"),
            _shot("shot02", location="alley", lighting="cold"),
        ]
        root = self._make_root(shots, strict=False)
        rep = preflight.run_preflight(root)
        soft_codes = [i["code"] for i in rep["soft"]]
        self.assertIn("production_consistency_drift", soft_codes)

    def test_preflight_hard_on_light_drift_strict(self):
        import preflight

        shots = [
            _shot("shot01", location="alley", lighting="warm"),
            _shot("shot02", location="alley", lighting="cold"),
        ]
        root = self._make_root(shots, strict=True)
        rep = preflight.run_preflight(root)
        hard_codes = [i["code"] for i in rep["hard"]]
        self.assertIn("production_consistency_drift", hard_codes)
        self.assertFalse(rep["hard_ok"])

    def test_preflight_clean_no_issue(self):
        import preflight

        shots = [
            _shot("shot01", camera_axis="push-in", location="alley", lighting="warm"),
            _shot("shot02", camera_axis="pan-right", location="alley", lighting="warm"),
        ]
        root = self._make_root(shots, strict=True)
        rep = preflight.run_preflight(root)
        all_codes = [i["code"] for i in rep["hard"]] + [i["code"] for i in rep["soft"]]
        self.assertNotIn("production_consistency_drift", all_codes)


if __name__ == "__main__":
    unittest.main()
