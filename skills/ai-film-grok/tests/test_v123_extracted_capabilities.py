"""Tests for v1.23 extracted capabilities (quality_check / reference_audit / subtitle_srt / product_brief / vo_lint).

These 5 modules were inspired by the reference-driven-cinematic-video skill
and adapted to ai-film-grok's conventions.

Verifies:
- quality_check_video: gate scoring + report structure
- reference_audit: shot-grammar extraction + aspect classification
- subtitle_srt: segment validation + SRT text generation + overlap detection
- product_brief: brief expansion + brochure phrase detection + scene plan
- vo_lint: brochure phrase / AI cadence / long sentence warnings
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from product_brief import BROCHURE_PHRASES, expand_product_brief
from quality_check_video import GATE_WEIGHTS, score_gates
from reference_audit import _aspect_ratio, _audio_reality, _classify_aspect
from subtitle_srt import SrtError, segments_to_srt_text, validate_segments, write_srt_file
from vo_lint import lint_film_spec_vo, lint_nar_text


# ---------------------------------------------------------------------------
# quality_check_video
# ---------------------------------------------------------------------------


class TestQualityCheckScoring:
    """Gate scoring logic (no FFmpeg needed)."""

    def test_all_pass_scores_100(self):
        gates = {name: {"status": "pass", "message": ""} for name in GATE_WEIGHTS}
        assert score_gates(gates) == 100

    def test_all_fail_scores_0(self):
        gates = {name: {"status": "fail", "message": ""} for name in GATE_WEIGHTS}
        assert score_gates(gates) == 0

    def test_all_warn_scores_half(self):
        gates = {name: {"status": "warn", "message": ""} for name in GATE_WEIGHTS}
        expected = sum(w * 0.5 for w in GATE_WEIGHTS.values())
        assert score_gates(gates) == round(expected)

    def test_weights_sum_to_100(self):
        assert sum(GATE_WEIGHTS.values()) == 100

    def test_missing_gate_treated_as_warn(self):
        gates = {"decode": {"status": "pass", "message": ""}}
        # Missing gates → warn → 0.5 * weight each
        score = score_gates(gates)
        expected = GATE_WEIGHTS["decode"] + sum(
            w * 0.5 for name, w in GATE_WEIGHTS.items() if name != "decode"
        )
        assert score == round(expected)


# ---------------------------------------------------------------------------
# reference_audit
# ---------------------------------------------------------------------------


class TestReferenceAuditHelpers:
    """Pure-function helpers (no FFmpeg needed)."""

    def test_aspect_ratio_9_16(self):
        assert _aspect_ratio(720, 1280) == (9, 16)

    def test_aspect_ratio_16_9(self):
        assert _aspect_ratio(1920, 1080) == (16, 9)

    def test_aspect_ratio_square(self):
        assert _aspect_ratio(1080, 1080) == (1, 1)

    def test_classify_vertical(self):
        assert _classify_aspect((9, 16)) == "vertical"

    def test_classify_horizontal(self):
        assert _classify_aspect((16, 9)) == "horizontal"

    def test_classify_square(self):
        assert _classify_aspect((1, 1)) == "square"

    def test_classify_unknown(self):
        assert _classify_aspect(None) == "unknown"

    def test_audio_reality_silent(self):
        result = _audio_reality("mean_volume: -70.0 dB\n", "")
        assert result["kind"] == "silent"

    def test_audio_reality_speech(self):
        result = _audio_reality("mean_volume: -15.0 dB\n", "")
        assert result["kind"] == "speech"

    def test_audio_reality_music_only(self):
        result = _audio_reality(
            "mean_volume: -30.0 dB\n", "silence_start: 1.5\nsilence_end: 2.0\n"
        )
        assert result["kind"] == "music_only"


# ---------------------------------------------------------------------------
# subtitle_srt
# ---------------------------------------------------------------------------


class TestSubtitleSrt:
    """SRT generation + validation."""

    def test_valid_segments(self):
        segments = [
            {"start": 0.0, "end": 2.5, "text": "你好"},
            {"start": 2.5, "end": 5.0, "text": "世界"},
        ]
        cleaned = validate_segments(segments)
        assert len(cleaned) == 2

    def test_empty_text_rejected(self):
        segments = [{"start": 0.0, "end": 2.0, "text": "  "}]
        try:
            validate_segments(segments)
            assert False, "should have raised"
        except SrtError as exc:
            assert "empty text" in str(exc)

    def test_end_before_start_rejected(self):
        segments = [{"start": 5.0, "end": 2.0, "text": "反转"}]
        try:
            validate_segments(segments)
            assert False, "should have raised"
        except SrtError as exc:
            assert "after start" in str(exc)

    def test_overlap_rejected(self):
        segments = [
            {"start": 0.0, "end": 3.0, "text": "第一句"},
            {"start": 2.0, "end": 4.0, "text": "重叠"},
        ]
        try:
            validate_segments(segments)
            assert False, "should have raised"
        except SrtError as exc:
            assert "before previous" in str(exc)

    def test_srt_text_format(self):
        segments = [{"start": 0.0, "end": 1.5, "text": "测试"}]
        text = segments_to_srt_text(segments)
        assert "1\n00:00:00,000 --> 00:00:01,500\n测试" in text

    def test_timestamp_formatting(self):
        from subtitle_srt import timestamp

        assert timestamp(0.0) == "00:00:00,000"
        assert timestamp(1.5) == "00:00:01,500"
        assert timestamp(3661.5) == "01:01:01,500"

    def test_write_srt_file(self, tmp_path):
        segments = [
            {"start": 0.0, "end": 2.0, "text": "第一句"},
            {"start": 2.0, "end": 4.0, "text": "第二句"},
        ]
        out = tmp_path / "test.srt"
        write_srt_file(out, segments)
        assert out.is_file()
        content = out.read_text(encoding="utf-8")
        assert "第一句" in content
        assert "第二句" in content
        assert "00:00:00,000" in content

    def test_non_list_input_rejected(self):
        try:
            validate_segments("not a list")  # type: ignore[arg-type]
            assert False, "should have raised"
        except SrtError as exc:
            assert "must be a list" in str(exc)


# ---------------------------------------------------------------------------
# product_brief
# ---------------------------------------------------------------------------


class TestProductBrief:
    """Product brief expansion logic."""

    def test_expand_basic(self):
        packet = expand_product_brief(
            "这是 AI 编辑器。\n它帮开发者写代码更快。\n速度提升 3 倍。",
            title="AI编辑器",
            target_duration=40.0,
        )
        assert packet["product_name"] == "AI编辑器"
        assert packet["target_duration_sec"] == 40.0
        assert packet["language"] == "zh"
        assert len(packet["scene_plan"]) == 5
        assert packet["scene_plan"][0]["purpose"] == "hook"
        assert packet["scene_plan"][-1]["purpose"] == "close"

    def test_scene_plan_durations_sum_to_target(self):
        packet = expand_product_brief("产品介绍", target_duration=50.0)
        total = sum(s["duration_sec"] for s in packet["scene_plan"])
        assert abs(total - 50.0) < 2.0  # rounding tolerance

    def test_proof_markers_detected(self):
        packet = expand_product_brief(
            "产品速度提升 3 倍。官网有截图。开源在 GitHub。"
        )
        assert "stats" in packet["proof_markers"]
        assert "screenshot" in packet["proof_markers"]
        assert "repo" in packet["proof_markers"]

    def test_brochure_phrase_warnings(self):
        packet = expand_product_brief("这是一款赋能开发者的革命性产品。")
        assert "赋能" in packet["brochure_phrase_warnings"]
        assert "革命性" in packet["brochure_phrase_warnings"]

    def test_empty_brief_rejected(self):
        try:
            expand_product_brief("")
            assert False, "should have raised"
        except Exception:
            pass

    def test_narrative_angle_demo_first(self):
        packet = expand_product_brief("产品有 demo 演示。截图如下。")
        assert packet["narrative_angle"] == "demo_first"

    def test_missing_assets_detected(self):
        packet = expand_product_brief("这是一个产品。")
        assert "product_screenshots" in packet["missing_assets"]


# ---------------------------------------------------------------------------
# vo_lint
# ---------------------------------------------------------------------------


class TestVoLint:
    """VO script lint for brochure phrases and AI cadence."""

    def test_clean_text_no_warnings(self):
        warnings = lint_nar_text("雨夜，出租车的灯在玻璃上散开。", shot_id="shot01")
        assert len(warnings) == 0

    def test_brochure_phrase_detected(self):
        warnings = lint_nar_text("这款产品赋能开发者，实现无缝体验。", shot_id="shot01")
        codes = [w.code for w in warnings]
        assert "VO_BROCHURE_PHRASE" in codes

    def test_ai_cadence_starter_detected(self):
        warnings = lint_nar_text("众所周知，这款产品很好。", shot_id="shot01")
        codes = [w.code for w in warnings]
        assert "VO_AI_CADENCE_STARTER" in codes

    def test_long_sentence_detected(self):
        long_sentence = "这是一段非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常长的旁白句子" * 2
        warnings = lint_nar_text(long_sentence, shot_id="shot01")
        codes = [w.code for w in warnings]
        assert "VO_SENTENCE_TOO_LONG" in codes

    def test_paragraph_not_spoken_detected(self):
        # Single block with no sentence breaks and long
        long_block = "这是一个没有任何句号断开的超长旁白文本块它会让配音听起来像在念稿子而不是说话" * 2
        warnings = lint_nar_text(long_block, shot_id="shot01")
        codes = [w.code for w in warnings]
        assert "VO_PARAGRAPH_NOT_SPOKEN" in codes

    def test_empty_text_no_warnings(self):
        assert lint_nar_text("", shot_id="shot01") == []
        assert lint_nar_text("   ", shot_id="shot01") == []

    def test_lint_film_spec(self):
        spec = {
            "scenes": [
                {
                    "shots": [
                        {"id": "shot01", "nar": "雨夜，街灯亮起。"},
                        {"id": "shot02", "nar": "这款产品赋能用户，实现无缝体验。"},
                    ]
                }
            ],
            "director_intent": {"logline": "一个关于选择的故事。"},
        }
        result = lint_film_spec_vo(spec)
        assert result["ok"] is False
        assert result["shot_count"] == 2
        assert "VO_BROCHURE_PHRASE" in result["codes"]

    def test_lint_film_spec_clean(self):
        spec = {
            "scenes": [
                {"shots": [{"id": "shot01", "nar": "雨夜，街灯亮起。"}]}
            ],
            "director_intent": {"logline": "一个关于选择的故事。"},
        }
        result = lint_film_spec_vo(spec)
        assert result["ok"] is True
        assert result["warning_count"] == 0
