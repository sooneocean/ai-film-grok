"""P4-16/17/18: fulfillment gate path tests — act structure, pace chart, music spotting.

These verify functions already existed in rhythm.py but were only called from
director_cli.py (display only, not enforced). P4 wires them into preflight as
soft (default) / hard (strict) gates.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _shot(sid, *, dur=6.0, df="approach"):
    return {
        "id": sid,
        "dramatic_function": df,
        "nar": f"旁白{sid}。",
        "duration_sec": dur,
        "dsl": {
            "subject": "woman",
            "cast": ["heroine"],
            "camera": {"shot_size": "medium"},
            "motion": "idle",
        },
    }


def _spec(shots, *, act_structure=None, pace_chart=None, music_spotting=None, strict=False):
    intent = {"logline": "Test fulfillment.", "tone": "neutral", "emotional_arc": ["a", "b"]}
    if act_structure:
        intent["act_structure"] = act_structure
    if pace_chart:
        intent["pace_chart"] = pace_chart
    spec = {
        "schema_version": 1,
        "title": "p4-test",
        "vo_mode": "storyteller",
        "aspect": "9:16",
        "director_intent": intent,
        "transition_sec": 0.25,
        "transition_default": "soft",
        "scenes": [{"shots": shots}],
    }
    if music_spotting:
        spec["sound_plan"] = {"music_spotting": music_spotting}
    if strict:
        spec["act_structure_strict"] = True
        spec["pace_chart_strict"] = True
    return spec


def _make_root(spec):
    tmp = tempfile.mkdtemp(prefix="aifilm_p4_test_")
    root = Path(tmp)
    (root / "film-spec.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    return root


class TestActStructureFulfillmentGate(unittest.TestCase):
    """P4-16: act_structure fulfillment checked in preflight."""

    def test_mismatch_soft_by_default(self):
        import preflight

        # 5 shots all "afterglow" (act3) but declared 40% setup → mismatch
        shots = [_shot(f"sh{i}", df="afterglow", dur=6.0) for i in range(5)]
        act = {"setup_ratio": 0.4, "confrontation_ratio": 0.4, "resolution_ratio": 0.2}
        root = _make_root(_spec(shots, act_structure=act, strict=False))
        rep = preflight.run_preflight(root)
        soft_codes = [i["code"] for i in rep["soft"]]
        self.assertIn("act_structure_fulfillment", soft_codes)

    def test_mismatch_hard_when_strict(self):
        import preflight

        shots = [_shot(f"sh{i}", df="afterglow", dur=6.0) for i in range(5)]
        act = {"setup_ratio": 0.4, "confrontation_ratio": 0.4, "resolution_ratio": 0.2}
        root = _make_root(_spec(shots, act_structure=act, strict=True))
        rep = preflight.run_preflight(root)
        hard_codes = [i["code"] for i in rep["hard"]]
        self.assertIn("act_structure_fulfillment", hard_codes)

    def test_matched_no_issue(self):
        import preflight

        # 2 setup + 4 confrontation + 2 resolution = 0.2/0.4/0.2 → ~0.25/0.5/0.25
        shots = (
            [_shot(f"s{i}", df="hook", dur=5.0) for i in range(2)]
            + [_shot(f"c{i}", df="action", dur=5.0) for i in range(4)]
            + [_shot(f"r{i}", df="afterglow", dur=5.0) for i in range(2)]
        )
        act = {"setup_ratio": 0.25, "confrontation_ratio": 0.5, "resolution_ratio": 0.25}
        root = _make_root(_spec(shots, act_structure=act, strict=True))
        rep = preflight.run_preflight(root)
        all_codes = [i["code"] for i in rep["hard"]] + [i["code"] for i in rep["soft"]]
        self.assertNotIn("act_structure_fulfillment", all_codes)


class TestPaceChartFulfillmentGate(unittest.TestCase):
    """P4-17: pace_chart fulfillment checked in preflight."""

    def test_mismatch_soft_by_default(self):
        import preflight

        # Declare "rapid" but shots are all 10s each → very slow
        shots = [_shot(f"sh{i}", dur=10.0) for i in range(4)]
        pace = [{"label": "all", "start_ratio": 0.0, "end_ratio": 1.0, "cut_freq": "rapid"}]
        root = _make_root(_spec(shots, pace_chart=pace, strict=False))
        rep = preflight.run_preflight(root)
        soft_codes = [i["code"] for i in rep["soft"]]
        self.assertIn("pace_chart_fulfillment", soft_codes)

    def test_mismatch_hard_when_strict(self):
        import preflight

        shots = [_shot(f"sh{i}", dur=10.0) for i in range(4)]
        pace = [{"label": "all", "start_ratio": 0.0, "end_ratio": 1.0, "cut_freq": "rapid"}]
        root = _make_root(_spec(shots, pace_chart=pace, strict=True))
        rep = preflight.run_preflight(root)
        hard_codes = [i["code"] for i in rep["hard"]]
        self.assertIn("pace_chart_fulfillment", hard_codes)


class TestMusicSpottingAlignmentGate(unittest.TestCase):
    """P4-18: music_spotting beat alignment checked in preflight."""

    def test_invalid_range_soft_issue(self):
        import preflight

        shots = [_shot(f"sh{i}", dur=6.0) for i in range(3)]
        spotting = [{"label": "theme", "start_sec": 10.0, "end_sec": 5.0}]  # end < start
        root = _make_root(_spec(shots, music_spotting=spotting, strict=False))
        rep = preflight.run_preflight(root)
        soft_codes = [i["code"] for i in rep["soft"]]
        self.assertIn("music_spotting_alignment", soft_codes)

    def test_valid_spotting_no_issue(self):
        import preflight

        shots = [_shot(f"sh{i}", dur=6.0) for i in range(3)]
        spotting = [{"label": "theme", "start_sec": 0.0, "end_sec": 18.0}]
        root = _make_root(_spec(shots, music_spotting=spotting, strict=True))
        rep = preflight.run_preflight(root)
        all_codes = [i["code"] for i in rep["hard"]] + [i["code"] for i in rep["soft"]]
        self.assertNotIn("music_spotting_alignment", all_codes)


if __name__ == "__main__":
    unittest.main()
