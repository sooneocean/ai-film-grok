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
