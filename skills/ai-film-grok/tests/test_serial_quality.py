from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from director_cli import validate_native_stage_evidence  # noqa: E402
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
                {
                    "episode_id": "ep01",
                    "episode_number": 1,
                    "ending_hook_id": "ep01-ending",
                    "novelty_signature": "office-secret",
                },
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
        "show-package.json",
        {"id": "night.v1", "version": "1", "ending": {"cta": "追更"}},
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


def test_serial_rejects_unbound_series_and_invented_prior_hook(tmp_path: Path) -> None:
    _valid(tmp_path)
    spec = json.loads((tmp_path / "film-spec.json").read_text())
    spec["serial"] = True
    _write(tmp_path, "film-spec.json", spec)
    bible = json.loads((tmp_path / "series-bible.json").read_text())
    bible["episodes"][1]["responds_to_hook_id"] = "invented-hook"
    _write(tmp_path, "series-bible.json", bible)
    codes = {item["code"] for item in validate_serial(tmp_path)["errors"]}
    assert {"SERIAL_CONFIG_INVALID", "SERIES_ID_MISSING", "PREVIOUS_HOOK_UNRESOLVED"} <= codes


def test_serial_rejects_suppressed_ending_and_bad_duration(tmp_path: Path) -> None:
    _valid(tmp_path)
    spec = json.loads((tmp_path / "film-spec.json").read_text())
    spec["end_roll"] = {"mode": "none"}
    spec["scenes"][0]["shots"][0]["duration_sec"] = "not-a-number"
    _write(tmp_path, "film-spec.json", spec)
    codes = {item["code"] for item in validate_serial(tmp_path)["errors"]}
    assert {"SERIAL_ENDING_CARD_SUPPRESSED", "SHOT_DURATION_INVALID"} <= codes


@pytest.mark.parametrize("bad_duration", ["NaN", "inf"])
def test_serial_rejects_nonfinite_duration(tmp_path: Path, bad_duration: str) -> None:
    _valid(tmp_path)
    spec = json.loads((tmp_path / "film-spec.json").read_text())
    spec["scenes"][0]["shots"][0]["duration_sec"] = bad_duration
    _write(tmp_path, "film-spec.json", spec)
    assert "SHOT_DURATION_INVALID" in {item["code"] for item in validate_serial(tmp_path)["errors"]}


@pytest.mark.parametrize("bad_number", [None, False, 1.5, "bad"])
def test_serial_rejects_invalid_episode_number(tmp_path: Path, bad_number: object) -> None:
    _valid(tmp_path)
    bible = json.loads((tmp_path / "series-bible.json").read_text())
    bible["episodes"][1]["episode_number"] = bad_number
    _write(tmp_path, "series-bible.json", bible)
    assert "EPISODE_NUMBER_INVALID" in {
        item["code"] for item in validate_serial(tmp_path)["errors"]
    }


def test_show_ending_prefers_verified_episode_question() -> None:
    html = build_platform_ending_html(
        {
            "film_timeline": {"output_duration": 10},
            "serial": {"enabled": True, "series_id": "night"},
            "episode_contract": {"ending_question": "谁换走了证据？"},
        },
        {"ending": {"duration_sec": 1, "next_episode_hook": "旧钩子", "cta": "追更"}},
        end_dur=1,
    )
    assert "谁换走了证据？" in html
    assert "旧钩子" not in html


def test_non_serial_show_ending_keeps_show_package_hook() -> None:
    html = build_platform_ending_html(
        {"film_timeline": {"output_duration": 10}, "episode_contract": {"ending_question": "草稿"}},
        {"ending": {"duration_sec": 1, "next_episode_hook": "标准钩子", "cta": "追更"}},
        end_dur=1,
    )
    assert "标准钩子" in html
    assert "草稿" not in html


def test_concept_lock_rejects_invalid_serial_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _valid(tmp_path)
    _write(tmp_path, "brief.json", {"title": "夜航"})
    bible = json.loads((tmp_path / "series-bible.json").read_text())
    bible["characters"][0]["adult_confirmed"] = False
    _write(tmp_path, "series-bible.json", bible)
    monkeypatch.setattr(
        "narrative_control.control_status",
        lambda _root: {"canonical": True, "semantic": {"ok": True}},
    )
    with pytest.raises(ValueError, match="serial quality gate failed"):
        validate_native_stage_evidence(tmp_path, "concept_lock")
