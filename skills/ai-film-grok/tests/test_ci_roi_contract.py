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
    """Every Python CI job should reuse the same pip cache key (not fork more)."""
    text = CI.read_text(encoding="utf-8")

    # Jobs grow (typecheck, console, …); require cache on each, not a fixed count=2.
    n_pip = text.count("cache: pip")
    n_lock = text.count("cache-dependency-path: skills/ai-film-grok/requirements.lock")
    assert n_pip >= 2
    assert n_lock >= 2
    assert n_pip == n_lock


def test_repository_instructions_resolve_the_current_source_checkout() -> None:
    text = AGENTS.read_text(encoding="utf-8")

    assert "/Users/asd/YOLO/ai-film-grok" not in text
    assert 'ROOT="$(git rev-parse --show-toplevel)"' in text


def test_capability_expansion_is_frozen_until_roi_evidence_is_complete() -> None:
    text = ROI_GATE.read_text(encoding="utf-8")

    assert "3 个" in text
    assert "data_quality" in text
    assert "禁止设为默认" in text


FORBIDDEN_FLOOR_KEYS = {
    "media_qa.py": "media/media_qa.py",
    "quality_evidence.py": "gates/quality_evidence.py",
    "continuity.py": "assets/continuity.py",
}


def test_ci_coverage_floors_target_real_package_implementations() -> None:
    """Floor keys must point at the package impl, never the top-level shim.

    After the W3/W6 package move the implementations live in media/ gates/
    assets/, while the top-level ``<name>.py`` files are ~0-LOC ``sys.modules``
    alias shims that always report 100% covered. A floor keyed on the bare
    ``scripts/<name>.py`` therefore gates nothing real.
    """
    text = CI.read_text(encoding="utf-8")
    block = text[text.index("floors = {") : text.index("coverage row missing")]

    for shim_key, real_path in FORBIDDEN_FLOOR_KEYS.items():
        assert f"\"{shim_key}\"" not in block, (
            f"floor key {shim_key} targets the shim; use the real package path"
        )
        assert f"\"{real_path}\"" in block, (
            f"floor key for {shim_key} missing; expected {real_path}"
        )


def test_ci_floor_real_package_files_exist() -> None:
    """Each floored real implementation file must exist under scripts/."""
    scripts_dir = ROOT / "skills" / "ai-film-grok" / "scripts"
    for real_path in FORBIDDEN_FLOOR_KEYS.values():
        origin = scripts_dir / real_path
        assert origin.is_file(), f"real impl missing: {origin}"
        lines = sum(1 for _ in origin.open(encoding="utf-8"))
        assert lines > 100, f"{origin} is only {lines} lines (shim, not real impl)"
