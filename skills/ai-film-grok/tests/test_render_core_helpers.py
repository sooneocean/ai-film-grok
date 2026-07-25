from __future__ import annotations

import pytest
from compose_render import (
    ComposeRenderError,
    assert_underlay_not_double_burn,
    duration_advisory,
    plate_subtitles_burned_in,
    probe_remotion_readiness,
)
from render_final import (
    _ensure_caption_density,
    build_subtitle_cues_for_shots,
    caption_text_for_shot,
    split_units,
    spoken_text_for_shot,
    unit_timings,
    voice_for_shot,
)
from util import write_json


def test_caption_helpers_keep_short_phrases_readable() -> None:
    assert split_units("") == []
    units = split_units("她转身。雨还在下，但他没有追上去。")
    assert units
    assert all(len(unit) <= 13 for unit in units)
    assert len(_ensure_caption_density(["这是一个需要拆开的很长中文字幕短句"], max_len=8)) > 1


def test_unit_timings_are_continuous_and_bounded() -> None:
    timings = unit_timings(["短句", "这是一个较长的句子"], 3.0)
    assert timings[0][1] == pytest.approx(0.0)
    assert timings[-1][2] == pytest.approx(3.0)
    assert all(begin < end for _, begin, end in timings)
    assert all(timings[i][2] <= timings[i + 1][1] for i in range(len(timings) - 1))


def test_shot_text_and_voice_follow_language_contract() -> None:
    character = {
        "shot_type": "dialogue",
        "speaker": "heroine",
        "nar": "中文",
        "dialogue_ja": "行く",
    }
    assert caption_text_for_shot(character) == "中文"
    assert spoken_text_for_shot(character) == "行く"
    assert voice_for_shot(character, default_voice="default", cast_voices={}, vo_mode="character")
    assert caption_text_for_shot({"nar": "中文", "nar_ja": "日本語"}, caption_lang="ja") == "日本語"


def test_subtitle_cues_stop_at_raw_speech_not_padding() -> None:
    cues, timeline = build_subtitle_cues_for_shots(
        [{"target": 3.0, "raw_vo_dur": 1.0, "units": ["第一句", "第二句"]}],
        title_duration=0.0,
        end_duration=0.0,
        transition_sec=0.0,
    )
    assert timeline["output_duration"] == pytest.approx(3.0)
    assert cues
    assert max(cue["end"] for cue in cues) <= 1.05


def test_compose_advisories_and_burn_gate(film_root) -> None:
    assert duration_advisory(90)["advisory"] is False
    assert duration_advisory(120)["segment_count"] == 2
    assert duration_advisory(200)["segment_count"] == 3
    assert plate_subtitles_burned_in(film_root) is None
    (film_root / "out" / "film_final.mp4").write_bytes(b"placeholder")
    write_json(film_root / "out" / "final-delivery.json", {"subtitles": {"burned_in": True}})
    with pytest.raises(ComposeRenderError, match="double-burn"):
        assert_underlay_not_double_burn(film_root, layout="underlay")
    assert (
        assert_underlay_not_double_burn(film_root, layout="underlay", allow_burned_underlay=True)[
            "skipped"
        ]
        is True
    )


def test_remotion_readiness_reports_actionable_missing_state(film_root) -> None:
    report = probe_remotion_readiness(film_root)
    assert report["ready"] is False
    assert "compose/remotion/" in report["missing"][0]
