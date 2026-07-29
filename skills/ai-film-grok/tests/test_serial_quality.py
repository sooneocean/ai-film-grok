from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from export_composition import build_platform_ending_html  # noqa: E402
from serial_quality import validate_serial  # noqa: E402


def _write(root: Path, name: str, data: dict) -> None:
    (root / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _valid(root: Path, *, duplicate: bool = False) -> None:
    _write(
        root,
        "series-bible.json",
        {
            "series_id": "night",
            "title": "夜航",
            "season_arc": "信任变质",
            "release_cadence": "每周两集",
            "mature_content": {"adult_only": True, "explicit_consent": True},
            "characters": [
                {
                    "id": "a",
                    "adult_confirmed": True,
                    "relationship": "搭档",
                    "motivation": "寻找真相",
                    "contrast": "冷静外表下冲动",
                    "rights": {"source_type": "original"},
                }
            ],
            "episodes": [
                {"episode_id": "ep01", "episode_number": 1, "novelty_signature": "office-secret"},
                {
                    "episode_id": "ep02",
                    "episode_number": 2,
                    "responds_to_hook_id": "ep01-ending",
                    "novelty_signature": "office-secret" if duplicate else "museum-alibi",
                },
            ],
        },
    )
    _write(
        root,
        "drama-graph.json",
        {
            "beats": [
                {"id": "b1", "event_relation": "introduces"},
                {"id": "b2", "event_relation": "complicates"},
            ]
        },
    )
    _write(
        root,
        "film-spec.json",
        {
            "serial": {"enabled": True, "series_id": "night"},
            "episode_contract": {
                "episode_id": "ep02",
                "primary_event": "交换证据",
                "event_turn": "证据被调包",
                "visible_outcome": "主角发现标记",
                "opening_hook": "门外有人",
                "ending_question": "谁调包了证据",
                "expected_next_payoff": "追查标记",
                "title": "证据被调包",
                "synopsis": "搭档在办公室交换证据时发现真相",
                "conflict_basis": "证据被调包",
                "relationship_basis": "搭档互不信任",
                "opening_promise": {
                    "characters": "两位搭档",
                    "setting": "办公室",
                    "conflict": "证据被调包",
                    "evidence_shot_ids": ["s1"],
                },
                "novelty": {
                    "genre_tags": ["悬疑"],
                    "setting": "办公室",
                    "differentiator": "证据交换",
                    "signature": "office-secret",
                },
            },
            "scenes": [
                {"shots": [{"id": "s1", "duration_sec": 12}, {"id": "s2", "duration_sec": 12}]}
            ],
        },
    )


def test_serial_contract_validates_and_writes_receipt(tmp_path: Path) -> None:
    _valid(tmp_path)
    report = validate_serial(tmp_path, write_receipt=True)
    assert report["ok"] is True, report
    assert (tmp_path / "receipts" / "serial-quality.json").is_file()


def test_serial_rejects_missing_opening_and_adult_rights(tmp_path: Path) -> None:
    _valid(tmp_path)
    bible = json.loads((tmp_path / "series-bible.json").read_text())
    bible["characters"][0]["adult_confirmed"] = False
    _write(tmp_path, "series-bible.json", bible)
    spec = json.loads((tmp_path / "film-spec.json").read_text())
    spec["episode_contract"]["opening_promise"]["evidence_shot_ids"] = ["missing"]
    _write(tmp_path, "film-spec.json", spec)
    codes = {item["code"] for item in validate_serial(tmp_path)["errors"]}
    assert {"SERIES_CHARACTER_ADULT_UNCONFIRMED", "OPENING_EVIDENCE_UNKNOWN"} <= codes


def test_serial_reports_duplicate_signature_without_blocking(tmp_path: Path) -> None:
    _valid(tmp_path, duplicate=True)
    report = validate_serial(tmp_path)
    assert report["ok"] is True
    assert report["warnings"][0]["code"] == "NOVELTY_SIGNATURE_COLLISION"


def test_show_ending_prefers_verified_episode_question() -> None:
    html = build_platform_ending_html(
        {
            "film_timeline": {"output_duration": 10},
            "episode_contract": {"ending_question": "谁换走了证据？"},
        },
        {"ending": {"duration_sec": 1, "next_episode_hook": "旧钩子", "cta": "追更"}},
        end_dur=1,
    )
    assert "谁换走了证据？" in html
    assert "旧钩子" not in html
