from __future__ import annotations

from pathlib import Path

import pytest
import render_final as render_mod
from compose_render import (
    ComposeRenderError,
    assert_underlay_not_double_burn,
    duration_advisory,
    plate_subtitles_burned_in,
    probe_remotion_readiness,
)
from render_final import (
    RenderError,
    _ensure_caption_density,
    build_subtitle_cues_for_shots,
    caption_text_for_shot,
    narration_for_shot,
    split_units,
    spoken_text_for_shot,
    tts_backend_for_shot,
    unit_timings,
    validate_linear_narration,
    validate_voice_language_locks,
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


def test_metadata_is_not_promoted_to_spoken_narration() -> None:
    assert narration_for_shot({"title": "角色表", "purpose": "格式说明"}) == ""
    with pytest.raises(RenderError, match="metadata is not playable VO"):
        validate_linear_narration(
            [{"id": "metadata", "title": "角色表"}],
            vo_mode="storyteller",
            dialogue_spoken_lang="ja",
            narration_spoken_lang="zh",
        )


def test_linear_narration_rejects_replayed_causal_beat() -> None:
    with pytest.raises(RenderError, match="repeats narration from shot01"):
        validate_linear_narration(
            [
                {"id": "shot01", "nar": "她推开门，雨声扑面而来。"},
                {"id": "shot02", "nar": "她 推开门，雨声扑面而来！"},
            ],
            vo_mode="storyteller",
            dialogue_spoken_lang="ja",
            narration_spoken_lang="zh",
        )


def test_linear_narration_uses_actual_character_tts_text() -> None:
    with pytest.raises(RenderError, match="repeats narration from shot01"):
        validate_linear_narration(
            [
                {"id": "shot01", "speaker": "heroine", "nar": "她点头", "dialogue_ja": "行く"},
                {"id": "shot02", "speaker": "heroine", "nar": "她转身", "dialogue_ja": "行く"},
            ],
            vo_mode="character",
            dialogue_spoken_lang="ja",
            narration_spoken_lang="zh",
        )


def test_linear_narration_allows_silent_dialogue_coverage() -> None:
    validate_linear_narration(
        [
            {"id": "reaction", "screen_mode": "reaction", "audio_cues": []},
            {"id": "cover", "coverage_role": "action_cover"},
            {"id": "silence", "screen_mode": "silence"},
        ],
        vo_mode="dialogue_drama",
        dialogue_spoken_lang="ja",
        narration_spoken_lang="zh",
    )


def test_linear_narration_does_not_hide_authored_coverage_voice() -> None:
    with pytest.raises(RenderError, match="repeats narration from cover01"):
        validate_linear_narration(
            [
                {"id": "cover01", "screen_mode": "action_cover", "nar": "门外传来脚步声。"},
                {"id": "cover02", "screen_mode": "reaction", "nar": "门外传来脚步声。"},
            ],
            vo_mode="dialogue_drama",
            dialogue_spoken_lang="ja",
            narration_spoken_lang="zh",
        )


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


def test_render_subprocess_contract_adds_noninteractive_flags(monkeypatch) -> None:
    calls = {}

    def fake_run(argv, **kwargs):
        calls["argv"] = argv
        calls["kwargs"] = kwargs
        return type("Completed", (), {"stdout": "", "stderr": "", "returncode": 0})()

    monkeypatch.setattr(render_mod.subprocess, "run", fake_run)
    render_mod.run(["ffmpeg", "-i", "input.mp4"], check=False)
    assert calls["argv"][1] == "-nostdin"
    assert calls["kwargs"]["timeout"] == 1800
    assert calls["kwargs"]["stdin"] is render_mod.subprocess.DEVNULL


def test_render_json_and_font_fail_closed(tmp_path: Path, monkeypatch) -> None:
    with pytest.raises(FileNotFoundError, match="Missing JSON"):
        render_mod.read_json(tmp_path / "missing.json")
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid JSON"):
        render_mod.read_json(invalid)
    monkeypatch.setattr(render_mod, "FONT_CANDIDATES", [str(tmp_path / "missing.ttf")])
    with pytest.raises(RenderError, match="Chinese-capable"):
        render_mod.resolve_font()


def test_voice_resolution_keeps_character_and_storyteller_defaults_distinct() -> None:
    cast = {"partner": "partner-voice", "storyteller": "narrator-voice"}
    assert (
        voice_for_shot(
            {"speaker": "partner", "dialogue_ja": "行く"},
            default_voice="default",
            cast_voices=cast,
            vo_mode="storyteller",
        )
        == "partner-voice"
    )
    assert (
        voice_for_shot(
            {"speaker": "narrator", "nar": "中文"},
            default_voice="default",
            cast_voices=cast,
            vo_mode="storyteller",
        )
        == "narrator-voice"
    )


def test_locked_voice_roles_ignore_per_shot_override() -> None:
    cast = {
        "storyteller": "zh-CN-XiaoxiaoNeural",
        "heroine": "ja-JP-NanamiNeural",
        "partner": "ja-JP-KeitaNeural",
    }
    assert (
        voice_for_shot(
            {"speaker": "narrator", "nar": "中文", "vo_voice": "other-voice"},
            default_voice="default",
            cast_voices=cast,
            vo_mode="hybrid",
        )
        == "zh-CN-XiaoxiaoNeural"
    )
    assert (
        voice_for_shot(
            {"speaker": "heroine", "dialogue_ja": "行く", "vo_voice": "other-voice"},
            default_voice="default",
            cast_voices=cast,
            vo_mode="hybrid",
        )
        == "ja-JP-NanamiNeural"
    )
    assert (
        voice_for_shot(
            {"speaker": "male_hero", "dialogue_ja": "行く", "vo_voice": "other-voice"},
            default_voice="default",
            cast_voices=cast,
            vo_mode="hybrid",
        )
        == "ja-JP-KeitaNeural"
    )


def test_lead_dialogue_locks_require_japanese_script_and_language() -> None:
    with pytest.raises(RenderError, match="not per-shot vo_voice"):
        validate_voice_language_locks(
            [{"id": "n02", "speaker": "narrator", "nar": "中文", "vo_voice": "other"}],
            dialogue_spoken_lang="ja",
        )
    with pytest.raises(RenderError, match="not per-shot tts_backend"):
        validate_voice_language_locks(
            [
                {
                    "id": "m02",
                    "speaker": "male_hero",
                    "dialogue_ja": "行く",
                    "tts_backend": "edge",
                }
            ],
            dialogue_spoken_lang="ja",
        )
    with pytest.raises(RenderError, match="dialogue_spoken_lang=ja"):
        validate_voice_language_locks(
            [{"id": "f01", "speaker": "heroine", "nar": "中文"}],
            dialogue_spoken_lang="zh",
        )
    with pytest.raises(RenderError, match="needs nar_ja/dialogue_ja/spoken_ja"):
        validate_voice_language_locks(
            [{"id": "m01", "speaker": "male_hero", "nar": "中文"}],
            dialogue_spoken_lang="ja",
        )
    with pytest.raises(RenderError, match="not per-shot vo_voice"):
        validate_voice_language_locks(
            [
                {
                    "id": "f02",
                    "speaker": "heroine",
                    "dialogue_ja": "行く",
                    "vo_voice": "ja-JP-OtherNeural",
                }
            ],
            dialogue_spoken_lang="ja",
        )
    with pytest.raises(RenderError, match="must contain Japanese kana"):
        validate_voice_language_locks(
            [{"id": "f04", "speaker": "heroine", "dialogue_ja": "中文"}],
            dialogue_spoken_lang="ja",
        )
    validate_voice_language_locks(
        [
            {"id": "n01", "speaker": "narrator", "nar": "中文"},
            {"id": "f03", "speaker": "heroine", "dialogue_ja": "行く"},
            {"id": "m03", "speaker": "male_hero", "dialogue_ja": "待って"},
        ],
        dialogue_spoken_lang="ja",
    )


def test_named_roles_can_lock_different_tts_providers_without_shot_switching() -> None:
    providers = {"storyteller": "edge", "heroine": "fish", "partner": "grok"}
    assert (
        tts_backend_for_shot(
            {"speaker": "narrator", "tts_backend": "other"},
            default_backend="edge",
            cast_tts_backends=providers,
        )
        == "edge"
    )
    assert (
        tts_backend_for_shot(
            {"speaker": "heroine", "tts_backend": "edge"},
            default_backend="edge",
            cast_tts_backends=providers,
        )
        == "fish"
    )
    assert (
        tts_backend_for_shot(
            {"speaker": "male_hero", "tts_backend": "edge"},
            default_backend="edge",
            cast_tts_backends=providers,
        )
        == "grok"
    )
    with pytest.raises(RenderError, match="not auto"):
        tts_backend_for_shot(
            {"speaker": "heroine"},
            default_backend="edge",
            cast_tts_backends={"heroine": "auto"},
        )
    assert (
        tts_backend_for_shot({"speaker": "heroine"}, default_backend="auto", cast_tts_backends={})
        == "edge"
    )
