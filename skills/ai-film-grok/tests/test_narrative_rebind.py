"""Narrative rebind + adult arc closeout gate (v2.40.5)."""

from __future__ import annotations

import json
from pathlib import Path

from narrative_rebind import check_narrative_rebind


def test_legacy_no_graph_soft_ok(tmp_path: Path):
    (tmp_path / "film-spec.json").write_text(
        json.dumps(
            {
                "title": "t",
                "heat_scale": "soft",
                "scenes": [{"id": "s1", "shots": [{"id": "a", "duration_sec": 5}]}],
            }
        ),
        encoding="utf-8",
    )
    rep = check_narrative_rebind(tmp_path, write=True)
    assert rep["ok"] is True  # graph missing is soft
    assert (tmp_path / "receipts" / "narrative-rebind.json").is_file()


def test_max_sex_arc_missing_hard(tmp_path: Path):
    # heat max with only setup — no foreplay/penetration/release
    (tmp_path / "film-spec.json").write_text(
        json.dumps(
            {
                "title": "t",
                "heat_scale": "max",
                "sex_arc_strict": True,
                "scenes": [
                    {
                        "id": "s1",
                        "shots": [
                            {
                                "id": "a",
                                "heat_phase": "act",
                                "duration_sec": 5,
                                "dsl": {"motion": "soft lean only"},
                                "nar": "轻轻拥抱",
                            },
                            {
                                "id": "b",
                                "heat_phase": "climax",
                                "duration_sec": 5,
                                "dsl": {"motion": "gentle hug"},
                                "nar": "对视",
                            },
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    rep = check_narrative_rebind(tmp_path, write=True)
    codes = {i["code"] for i in rep["issues"] if i.get("severity") == "hard"}
    assert codes & {
        "SEX_ARC_FOREPLAY_MISSING",
        "SEX_ARC_PENETRATION_MISSING",
        "SEX_ARC_CLIMAX_RELEASE_MISSING",
    }
    assert rep["ok"] is False


def test_stale_projection_hard(tmp_path: Path):
    (tmp_path / "film-spec.json").write_text(
        json.dumps({"title": "t", "heat_scale": "soft", "scenes": []}),
        encoding="utf-8",
    )
    (tmp_path / "drama-graph.json").write_text(
        json.dumps(
            {
                "narrative": {
                    "projection": {
                        "ok": False,
                        "stale": True,
                        "source_revision": "abc",
                        "actual_sha256": "deadbeef",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    rep = check_narrative_rebind(tmp_path, write=False)
    codes = {i["code"] for i in rep["issues"] if i.get("severity") == "hard"}
    assert "NARRATIVE_PROJECTION_STALE" in codes or "NARRATIVE_PROJECTION_NOT_OK" in codes
    assert rep["ok"] is False
