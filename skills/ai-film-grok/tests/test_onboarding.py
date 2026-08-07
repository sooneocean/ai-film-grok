"""Tests for the onboarding wizard core (stdlib, no web framework needed)."""

import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.console

HERE = Path(__file__).resolve().parent
SKILL_SCRIPTS = HERE.parent / "scripts"
if str(SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS))

from onboarding import (  # noqa: E402
    WebConsoleConflict,
    WebConsoleError,
    get_state,
    go,
    submit_step,
)


def test_fresh_state_is_empty(tmp_path):
    st = get_state(tmp_path)
    assert st["revision"] == 0
    assert all(
        not st["steps"][s]["done"] for s in ("references", "story", "characters")
    )


def test_submit_references_requires_items(tmp_path):
    with pytest.raises(WebConsoleError):
        submit_step(tmp_path, "references", {"items": []})


def test_submit_all_three_steps(tmp_path):
    submit_step(tmp_path, "references", {"items": [{"url": "http://x/a.png", "note": "mood"}]})
    submit_step(tmp_path, "story", {"text": "从前有座山。"})
    submit_step(tmp_path, "characters", {"items": [{"id": "hero", "name": "阿强", "description": "高大"}]})
    st = get_state(tmp_path)
    assert all(st["steps"][s]["done"] for s in ("references", "story", "characters"))
    assert st["revision"] == 3


def test_submit_stale_revision_conflict(tmp_path):
    submit_step(tmp_path, "references", {"items": [{"url": "http://x/a.png"}]})
    with pytest.raises(WebConsoleConflict):
        submit_step(tmp_path, "story", {"text": "x"}, expected_revision=99)


def test_go_rejected_when_incomplete(tmp_path):
    with pytest.raises(WebConsoleError):
        go(tmp_path)


def test_go_persists_canonical_files(tmp_path, monkeypatch):
    monkeypatch.setattr("onboarding._try_advance", lambda base: (True, "advanced: ok"))
    submit_step(tmp_path, "references", {"items": [{"url": "http://x/a.png", "note": "mood"}]})
    submit_step(tmp_path, "story", {"text": "从前有座山。"})
    submit_step(tmp_path, "characters", {"items": [{"id": "hero", "name": "阿强", "description": "高大"}]})

    res = go(tmp_path)
    assert res["ok"] is True
    assert res["advanced"] is True

    refs = json.loads((tmp_path / "references.json").read_text(encoding="utf-8"))
    assert refs["items"][0]["url"] == "http://x/a.png"

    story = (tmp_path / "intake" / "story" / "story.md").read_text(encoding="utf-8")
    assert "从前有座山" in story

    manifest = json.loads((tmp_path / "intake-manifest.json").read_text(encoding="utf-8"))
    assert manifest["characters"][0]["id"] == "hero"

    bible = json.loads((tmp_path / "style-bible.json").read_text(encoding="utf-8"))
    assert "hero" in bible["characters"]
    assert "hero" in bible["cast_masters"]


def test_go_stale_revision_conflict(tmp_path, monkeypatch):
    monkeypatch.setattr("onboarding._try_advance", lambda base: (False, "skip"))
    submit_step(tmp_path, "references", {"items": [{"url": "http://x/a.png"}]})
    submit_step(tmp_path, "story", {"text": "x"})
    submit_step(tmp_path, "characters", {"items": [{"id": "h"}]})
    with pytest.raises(WebConsoleConflict):
        go(tmp_path, expected_revision=1)
