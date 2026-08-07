"""Tests for the agent-style onboarding planner (heuristic fallback).

The planner must produce a usable plan with NO local LLM configured, so
onboarding never blocks. The local-LLM branch is exercised separately in
``test_local_llm`` (it is fail-soft and falls back to the heuristic here).
"""

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.console

HERE = Path(__file__).resolve().parent
SKILL_SCRIPTS = HERE.parent / "scripts"
if str(SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS))

import onboarding_planner  # noqa: E402


def test_heuristic_detects_lead_and_support(tmp_path):
    brief = {"story_text": "林晚说：今晚的雨真大。顾沉道：进来避避吧。", "image_paths": [], "hints": []}
    plan = onboarding_planner.deterministic_decompose(brief)
    names = [c["name"] for c in plan["characters"]]
    assert "林晚" in names and "顾沉" in names
    lead = [c for c in plan["characters"] if c["is_lead"]]
    assert lead and lead[0]["name"] == "林晚"
    # every character has a voice suggestion
    assert plan["voice_suggestions"]
    assert all(v.get("voice") for v in plan["voice_suggestions"])
    assert plan["genre"] and plan["heat_scale"]
    assert plan["bgm_mood"]


def test_heuristic_infers_adult_max(tmp_path):
    brief = {"story_text": "成人肉戏在夜色里展开，两人缠绵。", "hints": []}
    plan = onboarding_planner.deterministic_decompose(brief)
    assert plan["genre"] == "adult"
    assert plan["heat_scale"] == "max"


def test_heuristic_assigns_lead_image(tmp_path):
    brief = {"story_text": "林晚说：你好。", "image_paths": ["intake/characters/abc123.png"], "hints": []}
    plan = onboarding_planner.deterministic_decompose(brief)
    lead = [c for c in plan["characters"] if c["is_lead"]][0]
    assert lead["reference_image"] == "intake/characters/abc123.png"
    # non-lead characters must NOT inherit the lead image
    others = [c for c in plan["characters"] if not c["is_lead"]]
    assert all(not c["reference_image"] for c in others)


def test_decompose_falls_back_to_heuristic_without_llm(tmp_path, monkeypatch):
    monkeypatch.delenv("AIFILM_LOCAL_LLM_BASE_URL", raising=False)
    brief = {"story_text": "林晚说：你好。", "image_paths": [], "hints": []}
    plan, source = onboarding_planner.decompose(tmp_path, brief)
    assert source == "heuristic"
    assert plan["characters"]


def test_heuristic_emits_shot_hints_theme_tone(tmp_path):
    """A usable plan must now carry real shot hints + theme + tone (not empty)."""
    brief = {
        "story_text": "雨夜里，林晚说：我们逃吧。顾沉道：好。两人在窗边靠近，手指交缠。",
        "image_paths": [],
        "hints": [],
    }
    plan = onboarding_planner.deterministic_decompose(brief)
    assert plan["theme"]
    assert plan["tone"]
    assert plan["shot_hints"], "heuristic must derive shot hints from scenes"
    for h in plan["shot_hints"]:
        assert "action" in h and h["action"]
        assert "camera" in h and h["camera"]


def test_heuristic_dialogue_colon_detects_names(tmp_path):
    """Script-style dialogue prefixes (name：) must be picked up as characters."""
    brief = {"story_text": "林晚：今晚的雨真大。顾沉：进来避避吧。", "image_paths": [], "hints": []}
    plan = onboarding_planner.deterministic_decompose(brief)
    names = [c["name"] for c in plan["characters"]]
    assert "林晚" in names and "顾沉" in names


def test_heuristic_no_name_synthesizes_cast(tmp_path):
    """When no explicit name is found, a sensible cast is derived from pronouns."""
    # both 她/他 present -> 女主 + 男主
    both = onboarding_planner.deterministic_decompose(
        {"story_text": "她望着他，心跳漏了一拍。", "image_paths": [], "hints": []}
    )
    names = [c["name"] for c in both["characters"]]
    assert "女主" in names and "男主" in names
    assert both["voice_suggestions"] and all(v.get("voice") for v in both["voice_suggestions"])

    # only 她 -> single 女主
    she = onboarding_planner.deterministic_decompose(
        {"story_text": "她独自坐在窗边。", "image_paths": [], "hints": []}
    )
    assert [c["name"] for c in she["characters"]] == ["女主"]

    # no pronoun at all -> a single 主角 placeholder
    none = onboarding_planner.deterministic_decompose(
        {"story_text": "夜色温柔，海风轻拂。", "image_paths": [], "hints": []}
    )
    assert [c["name"] for c in none["characters"]] == ["主角"]


def test_heuristic_hints_shape_theme_tone(tmp_path):
    brief = {"story_text": "两人并肩看海。", "image_paths": [], "hints": ["治愈"]}
    plan = onboarding_planner.deterministic_decompose(brief)
    # 治愈 hint overrides the genre-default theme/tone to the healing variant.
    assert plan["theme"] == "被生活温柔接住"
    assert plan["tone"] == "温润舒缓"
    assert plan["bgm_mood"]
