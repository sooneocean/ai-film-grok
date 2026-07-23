"""Tests for P3-1: color grading parameterization (from 0/10).

Verifies:
- grade schema field exists in film-spec with LUT/temperature/saturation/contrast/etc.
- COLOR_GRADE_MISSING warning when no grade in spec
- COLOR_GRADE_MISSING hard failure when color_grade_strict=true but grade missing
- No warning when grade.color_temperature is present
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from post_audit import audit


def _make_film_root(tmp_path: Path, *, spec=None):
    if spec is not None:
        (tmp_path / "film-spec.json").write_text(json.dumps(spec, ensure_ascii=False))
    outdir = tmp_path / "out"
    outdir.mkdir(exist_ok=True)
    (outdir / "film_final.mp4").write_bytes(b"fake mp4")


class TestGradeSchema:
    """grade field exists in film-spec schema."""

    def test_grade_field_exists(self):
        schema_path = Path(__file__).resolve().parent.parent / "schemas" / "film-spec.schema.json"
        schema = json.loads(schema_path.read_text())
        props = schema.get("properties", {})
        assert "grade" in props
        grade = props["grade"]
        assert grade["type"] == "object"
        gprops = grade.get("properties", {})
        assert "lut_path" in gprops
        assert "color_temperature" in gprops
        assert "saturation" in gprops
        assert "contrast" in gprops
        assert "brightness" in gprops
        assert "skin_tone_protection" in gprops
        assert "gamma" in gprops

    def test_color_grade_strict_flag_exists(self):
        schema_path = Path(__file__).resolve().parent.parent / "schemas" / "film-spec.schema.json"
        schema = json.loads(schema_path.read_text())
        props = schema.get("properties", {})
        assert "color_grade_strict" in props


class TestColorGradeMissing:
    """COLOR_GRADE_MISSING in post_audit."""

    def test_warning_when_no_grade(self, tmp_path):
        spec = {"title": "t", "vo_mode": "storyteller", "scenes": []}
        _make_film_root(tmp_path, spec=spec)
        result = audit(tmp_path, write=False)
        warning_codes = [w["code"] for w in result.get("warnings", [])]
        assert "COLOR_GRADE_MISSING" in warning_codes

    def test_no_warning_when_grade_present(self, tmp_path):
        spec = {
            "title": "t",
            "vo_mode": "storyteller",
            "scenes": [],
            "grade": {"color_temperature": "warm 3200K", "saturation": 1.1},
        }
        _make_film_root(tmp_path, spec=spec)
        result = audit(tmp_path, write=False)
        warning_codes = [w["code"] for w in result.get("warnings", [])]
        assert "COLOR_GRADE_MISSING" not in warning_codes

    def test_hard_failure_when_strict_and_missing(self, tmp_path):
        spec = {
            "title": "t",
            "vo_mode": "storyteller",
            "scenes": [],
            "color_grade_strict": True,
        }
        _make_film_root(tmp_path, spec=spec)
        result = audit(tmp_path, write=False)
        hard_codes = [h["code"] for h in result.get("hard_failures", [])]
        assert "COLOR_GRADE_MISSING" in hard_codes

    def test_no_hard_failure_when_strict_and_grade_present(self, tmp_path):
        spec = {
            "title": "t",
            "vo_mode": "storyteller",
            "scenes": [],
            "color_grade_strict": True,
            "grade": {"color_temperature": "cool 5600K"},
        }
        _make_film_root(tmp_path, spec=spec)
        result = audit(tmp_path, write=False)
        hard_codes = [h["code"] for h in result.get("hard_failures", [])]
        assert "COLOR_GRADE_MISSING" not in hard_codes
