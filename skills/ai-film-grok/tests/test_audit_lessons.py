from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from audit_lessons import build_report, markdown


def test_lessons_audit_reports_compatibility_surfaces() -> None:
    report = build_report()
    assert report["lesson_count"] > 0
    assert report["entries"]
    assert report["compatibility_surfaces"]["legacy_story_graph"]
    assert "Classification" in markdown(report)
