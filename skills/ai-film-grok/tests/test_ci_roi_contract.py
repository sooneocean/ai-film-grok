from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CI = ROOT / ".github" / "workflows" / "ci.yml"
AGENTS = ROOT / "AGENTS.md"
ROI_GATE = ROOT / "skills" / "ai-film-grok" / "references" / "capability-expansion-roi-gate.md"


def test_ci_fast_and_slow_jobs_do_not_duplicate_the_full_suite() -> None:
    text = CI.read_text(encoding="utf-8")

    assert '-m "not slow"' in text
    assert '-m "slow"' in text
    assert "Full pytest suite" not in text


def test_ci_reuses_pip_download_cache_in_both_jobs() -> None:
    text = CI.read_text(encoding="utf-8")

    assert text.count("cache: pip") == 2
    assert text.count("cache-dependency-path: skills/ai-film-grok/requirements.lock") == 2


def test_repository_instructions_resolve_the_current_source_checkout() -> None:
    text = AGENTS.read_text(encoding="utf-8")

    assert "/Users/asd/YOLO/ai-film-grok" not in text
    assert 'ROOT="$(git rev-parse --show-toplevel)"' in text


def test_capability_expansion_is_frozen_until_roi_evidence_is_complete() -> None:
    text = ROI_GATE.read_text(encoding="utf-8")

    assert "3 个" in text
    assert "data_quality" in text
    assert "禁止设为默认" in text
