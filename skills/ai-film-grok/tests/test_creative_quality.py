from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from creative_quality import validate_premium_vertical  # noqa: E402
from preflight import run_preflight  # noqa: E402
from production_book import init_production_book  # noqa: E402


def test_premium_profile_rejects_placeholder_planning(tmp_path: Path) -> None:
    (tmp_path / "drama-graph.json").write_text(json.dumps({"beats": [{"id": "bt01"}]}))
    (tmp_path / "film-spec.json").write_text(json.dumps({"scenes": []}))
    report = validate_premium_vertical(tmp_path)
    assert report["ok"] is False
    assert {item["code"] for item in report["errors"]} >= {"BEAT_FIELD_MISSING", "SHOTS_MISSING"}


def test_premium_profile_accepts_authored_minimum(tmp_path: Path) -> None:
    (tmp_path / "drama-graph.json").write_text(
        json.dumps(
            {
                "beats": [
                    {
                        "id": "bt01",
                        "obstacle": "门锁住",
                        "tactic": "撬锁",
                        "turn": "灯亮",
                        "outcome": "她后退",
                        "state_delta": "从等待到暴露",
                    }
                ],
            }
        )
    )
    (tmp_path / "film-spec.json").write_text(
        json.dumps(
            {
                "scenes": [
                    {
                        "director_board": {
                            "emotional_turn": "怀疑到恐惧",
                            "visual_strategy": "窄景深",
                            "performance_strategy": "压住呼吸",
                        },
                        "shots": [
                            {
                                "id": "sh01",
                                "performance": {
                                    "subtext": "她知道有人在门后",
                                    "playable_action": "后退一步",
                                    "reaction_trigger": "灯亮",
                                },
                                "dsl": {
                                    "camera_axis": "screen_left",
                                    "shot_size": "close_up",
                                    "lens_mm": 50,
                                    "lighting": "冷顶光",
                                },
                            }
                        ],
                    }
                ]
            }
        )
    )
    report = validate_premium_vertical(tmp_path)
    assert report["ok"] is True, report


def test_preflight_blocks_premium_profile_before_paid_work(tmp_path: Path) -> None:
    init_production_book(tmp_path, quality_target="premium_vertical")
    report = run_preflight(tmp_path)
    assert report["hard_ok"] is False
    assert any(item["code"] == "BEATS_MISSING" for item in report["hard"])
