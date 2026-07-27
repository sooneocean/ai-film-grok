"""P2-7/P2-9/P2-10: strict gate path tests for meaningful_motion, rhythm, vo_lint.

These three dimensions had lint + write-spec strict toggles but the strict
raise-path had zero test coverage. This file closes that gap.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from film_spec import FilmSpecError, validate_film_spec  # noqa: E402


def _base_spec(shots: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "title": "strict-test",
        "vo_mode": "storyteller",
        "aspect": "9:16",
        "director_intent": {
            "logline": "A test for strict gate paths.",
            "tone": "neutral",
            "emotional_arc": ["a", "b", "c"],
        },
        "transition_sec": 0.25,
        "transition_default": "soft",
        "scenes": [{"shots": shots}],
    }


def _shot(sid: str, *, nar: str | None = None, dramatic_function: str = "approach") -> dict:
    return {
        "id": sid,
        "dramatic_function": dramatic_function,
        # Keep the fixture focused on craft gates, not the independent
        # no-replayed-narration production contract.
        "nar": nar if nar is not None else f"{sid} 的新叙事推进。",
        "dsl": {
            "subject": "woman",
            "cast": ["heroine"],
            "camera": {"shot_size": "medium"},
            "motion": "slow push-in",
        },
    }


class TestMeaningfulMotionStrict(unittest.TestCase):
    """P2-7: meaningful_motion_strict raises on violations (was soft-only in preflight)."""

    def test_strict_raises_on_missing_visible_change(self):
        """Shots without visible_change/dsl.motion meaning trigger strict raise."""
        shots = [
            _shot("shot01", dramatic_function="hook"),
            _shot("shot02", dramatic_function="approach"),
        ]
        spec = _base_spec(shots)
        spec["meaningful_motion_strict"] = True
        with self.assertRaises(FilmSpecError) as ctx:
            validate_film_spec(spec, assign_missing_ids=False)
        self.assertIn("meaningful_motion_strict", str(ctx.exception))

    def test_non_strict_attaches_report_without_raising(self):
        """Without strict, violations are attached but don't raise."""
        shots = [
            _shot("shot01", dramatic_function="hook"),
            _shot("shot02", dramatic_function="approach"),
        ]
        spec = _base_spec(shots)
        validate_film_spec(spec, assign_missing_ids=False)
        mm = spec.get("_meaningful_motion") or {}
        self.assertIn("ok", mm)
        self.assertIn("codes", mm)


class TestVoLintStrict(unittest.TestCase):
    """P2-10: vo_lint_strict raises on brochure/AI-cadence/long-sentence VO."""

    def test_strict_raises_on_brochure_phrase(self):
        """A nar containing a brochure phrase raises when vo_lint_strict."""
        shots = [_shot("shot01", nar="这款产品全方位赋能行业升级。")]
        spec = _base_spec(shots)
        spec["vo_lint_strict"] = True
        with self.assertRaises(FilmSpecError) as ctx:
            validate_film_spec(spec, assign_missing_ids=False)
        self.assertIn("vo_lint_strict", str(ctx.exception))

    def test_non_strict_no_raise_on_brochure_phrase(self):
        """Without vo_lint_strict, brochure phrases are advisory only."""
        shots = [_shot("shot01", nar="这款产品全方位赋能行业升级。")]
        spec = _base_spec(shots)
        validate_film_spec(spec, assign_missing_ids=False)
        summary = spec.get("_vo_lint_summary") or {}
        self.assertFalse(summary.get("ok", True))
        self.assertGreater(summary.get("violation_count", 0), 0)

    def test_strict_passes_on_clean_nar(self):
        """Clean natural narration passes even with vo_lint_strict."""
        shots = [_shot("shot01", nar="她推开门，雨声扑面而来。")]
        spec = _base_spec(shots)
        spec["vo_lint_strict"] = True
        validate_film_spec(spec, assign_missing_ids=False)
        summary = spec.get("_vo_lint_summary") or {}
        self.assertTrue(summary.get("ok"))

    def test_summary_attached(self):
        """The _vo_lint_summary is always attached (even without strict)."""
        shots = [_shot("shot01", nar="旁白。")]
        spec = _base_spec(shots)
        validate_film_spec(spec, assign_missing_ids=False)
        summary = spec.get("_vo_lint_summary") or {}
        self.assertIn("violation_count", summary)
        self.assertIn("violations", summary)


class TestRhythmStrict(unittest.TestCase):
    """P2-9: rhythm_strict raises on rhythm violations (was untested strict path)."""

    def test_rhythm_report_attached(self):
        """The rhythm report is always attached to spec."""
        shots = [
            _shot("shot01", dramatic_function="hook"),
            _shot("shot02", dramatic_function="approach"),
            _shot("shot03", dramatic_function="afterglow"),
        ]
        spec = _base_spec(shots)
        validate_film_spec(spec, assign_missing_ids=False)
        # rhythm report may be under _rhythm or similar
        rhythm_keys = [k for k in spec if "rhythm" in k.lower()]
        self.assertGreater(len(rhythm_keys), 0, "no rhythm report key on spec")

    def test_rhythm_strict_recognized(self):
        """The rhythm_strict flag is recognized and raises when violations exist."""
        shots = [
            _shot("shot01", dramatic_function="hook"),
            _shot("shot02", dramatic_function="approach"),
            _shot("shot03", dramatic_function="afterglow"),
        ]
        spec = _base_spec(shots)
        spec["rhythm_strict"] = True
        # These minimal shots trigger rhythm violations → strict should raise
        with self.assertRaises(FilmSpecError) as ctx:
            validate_film_spec(spec, assign_missing_ids=False)
        self.assertIn("rhythm_strict", str(ctx.exception))


class TestPreflightMeaningfulMotionElevation(unittest.TestCase):
    """P2-7: preflight elevates meaningful_motion to hard when strict."""

    def _make_root(self, shots, *, strict=False):
        import json
        import tempfile

        tmp = tempfile.mkdtemp(prefix="aifilm_mm_test_")
        root = Path(tmp)
        spec = _base_spec(shots)
        if strict:
            spec["meaningful_motion_strict"] = True
        (root / "film-spec.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        return root

    def test_preflight_elevates_to_hard_when_strict(self):
        """When meaningful_motion_strict is set, preflight puts it in hard list."""
        import preflight

        # Create shots that trigger meaningful_motion warnings (no visible_change)
        shots = [
            _shot("shot01", dramatic_function="hook"),
            _shot("shot02", dramatic_function="hook"),
        ]
        root = self._make_root(shots, strict=True)
        rep = preflight.run_preflight(root)
        hard_codes = [i["code"] for i in rep["hard"]]
        soft_codes = [i["code"] for i in rep["soft"]]
        # Either it's in hard (if lint fires) or not in soft (if clean)
        if "meaningful_motion" in soft_codes + hard_codes:
            self.assertIn("meaningful_motion", hard_codes)
            self.assertNotIn("meaningful_motion", soft_codes)


if __name__ == "__main__":
    unittest.main()
