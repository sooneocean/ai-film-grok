"""Adult-max sensory contract stays projection-first and media-evidence-bound."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from adult_max_director import (  # noqa: E402
    _verified_mix,
    apply_contract,
    build_evidence,
    validate_contract,
)
from heat_check import heat_check  # noqa: E402


def _spec() -> dict:
    return {
        "heat_scale": "max",
        "scenes": [
            {
                "shots": [
                    {"id": "a1", "heat_phase": "act", "coverage_role": "detail"},
                    {"id": "c1", "heat_phase": "climax"},
                ]
            }
        ],
    }


class AdultMaxDirectorTests(unittest.TestCase):
    def test_projection_supplies_sensory_cues_and_validates(self) -> None:
        spec = _spec()
        shots = spec["scenes"][0]["shots"]
        report = apply_contract(spec, shots)
        self.assertTrue(report["active"])
        self.assertEqual(shots[0]["sensory_cues"]["visual_coverage"], "detail")
        self.assertTrue(validate_contract(spec, shots)["ok"])

    def test_projection_never_relabels_action_as_detail(self) -> None:
        spec = _spec()
        shots = spec["scenes"][0]["shots"]
        shots[0]["coverage_role"] = "action"
        apply_contract(spec, shots)
        self.assertEqual(shots[0]["sensory_cues"]["visual_coverage"], "action_progress")
        self.assertIn("ADULT_MAX_DETAIL_COVERAGE_MISSING", validate_contract(spec, shots)["codes"])

    def test_non_max_is_unchanged(self) -> None:
        spec = _spec()
        spec["heat_scale"] = "hot"
        shots = spec["scenes"][0]["shots"]
        self.assertFalse(apply_contract(spec, shots)["active"])
        self.assertNotIn("sensory_cues", shots[0])

    def test_evidence_fails_closed_without_media_or_alignment(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            spec = _spec()
            shots = spec["scenes"][0]["shots"]
            apply_contract(spec, shots)
            (root / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
            (root / "manifest.json").write_text(json.dumps({"clips": {}}), encoding="utf-8")
            report = build_evidence(root, write=True)
        self.assertFalse(report["ok"])
        self.assertIn("ADULT_MAX_MEDIA_MISSING:a1", report["codes"])
        self.assertIn("ADULT_MAX_AV_ALIGNMENT_MISSING", report["codes"])

    def test_evidence_rejects_generic_review_without_adult_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            spec = _spec()
            shots = spec["scenes"][0]["shots"]
            apply_contract(spec, shots)
            clip = root / "a1.mp4"
            clip.write_bytes(b"hashable test media")
            digest = sha256(clip.read_bytes()).hexdigest()
            review = root / "review.json"
            review.write_text(
                json.dumps(
                    {
                        "approved": True,
                        "source": {"sha256": digest},
                        "evidence": {"coitus": {"timestamp_sec": 1.0}},
                    }
                ),
                encoding="utf-8",
            )
            (root / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
            (root / "manifest.json").write_text(
                json.dumps(
                    {"clips": {"a1": {"path": str(clip), "shot_review": {"path": str(review)}}}}
                ),
                encoding="utf-8",
            )
            receipts = root / "receipts"
            receipts.mkdir()
            (receipts / "audio-visual-alignment.json").write_text(
                json.dumps({"av_alignment_score": 90}), encoding="utf-8"
            )
            with patch("adult_max_director._current_quality_evidence", return_value=True):
                report = build_evidence(root, write=False)
        self.assertFalse(report["ok"])
        self.assertIn("ADULT_MAX_PERFORMANCE_EVIDENCE_MISSING:a1", report["codes"])
        self.assertIn("ADULT_MAX_HUMAN_REVIEW_MISSING:a1", report["codes"])

    def test_evidence_requires_current_quality_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            spec = _spec()
            shots = spec["scenes"][0]["shots"]
            apply_contract(spec, shots)
            clip = root / "a1.mp4"
            clip.write_bytes(b"hashable test media")
            (root / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
            (root / "manifest.json").write_text(
                json.dumps({"clips": {"a1": {"path": str(clip)}}}), encoding="utf-8"
            )
            report = build_evidence(root, write=False)
        self.assertIn("ADULT_MAX_QUALITY_EVIDENCE_MISSING:a1", report["codes"])

    def test_heat_check_fails_closed_when_max_media_evidence_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            spec = _spec()
            shots = spec["scenes"][0]["shots"]
            apply_contract(spec, shots)
            (root / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
            (root / "manifest.json").write_text(json.dumps({"clips": {}}), encoding="utf-8")
            report = heat_check(root)
        self.assertFalse(report["ok"])
        self.assertIn("ADULT_MAX_AV_ALIGNMENT_MISSING", report["hard_relevant_codes"])

    def test_mix_evidence_uses_renderer_path_and_checks_artifact_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            audio = root / "audio"
            audio.mkdir()
            artifacts = {}
            for name in ("bgm", "sfx", "mixed"):
                path = audio / f"{name}.wav"
                path.write_bytes(name.encode())
                artifacts[name] = {
                    "path": str(path),
                    "sha256": sha256(path.read_bytes()).hexdigest(),
                }
            report_path = audio / "mix_report.json"
            report_path.write_text(json.dumps({"artifacts": artifacts}), encoding="utf-8")
            path, ok = _verified_mix(root)
            self.assertEqual(path, report_path.resolve())
            self.assertTrue(ok)
            artifacts["mixed"]["sha256"] = "bogus"
            report_path.write_text(json.dumps({"artifacts": artifacts}), encoding="utf-8")
            _, ok = _verified_mix(root)
        self.assertFalse(ok)

    def test_mix_evidence_rejects_legacy_receipt_without_renderer_report(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            legacy = root / "receipts"
            legacy.mkdir()
            (legacy / "mix_report.json").write_text(json.dumps({"artifacts": {}}), encoding="utf-8")
            path, ok = _verified_mix(root)
        self.assertIsNone(path)
        self.assertFalse(ok)
