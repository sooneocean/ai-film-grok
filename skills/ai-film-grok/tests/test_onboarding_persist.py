"""Closure test: a v2 decomposed plan actually lands in canonical pipeline files.

This guards the promise from the comprehensive optimization round: voice /
BGM / scenes / shot-hints must be written to disk at ``go`` (not dropped).
"""

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.console

HERE = Path(__file__).resolve().parent
SKILL_SCRIPTS = HERE.parent / "scripts"
if str(SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS))

import onboarding  # noqa: E402
from util import read_json  # noqa: E402


def _sample_plan():
    return {
        "title": "雨夜靠近",
        "genre": "adult",
        "heat_scale": "max",
        "theme": "欲望与亲密关系的试探",
        "tone": "暧昧拉扯",
        "characters": [
            {"id": "linwan", "name": "林晚", "role": "主角", "is_lead": True, "reference_image": ""},
            {"id": "guchen", "name": "顾沉", "role": "配角", "is_lead": False, "reference_image": ""},
        ],
        "scenes": [{"title": "雨夜书店", "summary": "两人在窗边靠近。"}],
        "shot_hints": [
            {"action": "呈现「雨夜书店」的情绪与节奏", "camera": "特写 · 面部与手部微表情"}
        ],
        "voice_suggestions": [
            {"character_id": "linwan", "voice": "zh-CN-XiaoyiNeural"},
            {"character_id": "guchen", "voice": "zh-CN-YunxiNeural"},
        ],
        "bgm_mood": "慵懒 R&B",
    }


def test_persist_writes_cast_voices_and_bgm(tmp_path):
    base = tmp_path
    plan = _sample_plan()
    brief = {"story_text": "雨夜书店，两人靠近。", "image_paths": [], "hints": []}
    out = onboarding._persist_canonical_v2(base, plan, brief)

    spec = read_json(base / "film-spec.json")
    assert spec["cast_voices"] == {
        "linwan": "zh-CN-XiaoyiNeural",
        "guchen": "zh-CN-YunxiNeural",
    }
    assert spec["bgm_mood"] == "慵懒 R&B"
    assert spec["genre"] == "adult" and spec["heat_scale"] == "max"
    assert "cast_voices" in out["film-spec"]


def test_persist_writes_scenes_and_shot_hints(tmp_path):
    base = tmp_path
    plan = _sample_plan()
    brief = {"story_text": "x", "image_paths": [], "hints": []}
    out = onboarding._persist_canonical_v2(base, plan, brief)

    scenes_doc = read_json(base / "intake" / "scenes.json")
    assert scenes_doc["kind"] == "ai-film-scenes"
    assert scenes_doc["scenes"][0]["title"] == "雨夜书店"

    hints_doc = read_json(base / "intake" / "shot-hints.json")
    assert hints_doc["kind"] == "ai-film-shot-hints"
    assert hints_doc["shot_hints"][0]["camera"]

    assert "scenes" in out and "shot_hints" in out


def test_persist_merges_existing_cast_voices(tmp_path):
    """go must merge, never clobber, an existing cast_voices dict."""
    base = tmp_path
    (base / "film-spec.json").write_text(
        '{"genre":"drama","heat_scale":"mild","cast_voices":{"existing":"zh-CN-XiaoxiaoNeural"}}',
        encoding="utf-8",
    )
    plan = _sample_plan()
    brief = {"story_text": "x", "image_paths": [], "hints": []}
    onboarding._persist_canonical_v2(base, plan, brief)
    spec = read_json(base / "film-spec.json")
    assert spec["cast_voices"]["existing"] == "zh-CN-XiaoxiaoNeural"
    assert spec["cast_voices"]["linwan"] == "zh-CN-XiaoyiNeural"
