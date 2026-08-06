"""W3a RED→GREEN: heat_spice.py references constants that live only in
heat_wardrobe / heat_phase, plus missing `re` import → NameError at runtime.

Product rule (IRON): 办事 = 卸甲/脱衣 → 裸露可读. These lints must not crash
when run under the real scripts package layout.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from narrative.heat_spice import (  # noqa: E402
    lint_sex_wardrobe,
    lint_user_source_fidelity,
    normalize_wardrobe_state,
)


def test_normalize_wardrobe_state_uses_wardrobe_states() -> None:
    """WARDROBE_STATES must be resolvable (not NameError) on hot paths."""
    assert normalize_wardrobe_state("full") == "full"
    assert normalize_wardrobe_state("裸") == "bare"
    assert normalize_wardrobe_state(None) is None


def test_lint_sex_wardrobe_happy_path_no_internal_error() -> None:
    """lint_sex_wardrobe touches SEX_WARDROBE_* / PHASE_WARDROBE_FLOOR /
    DEFAULT_BARE_PEAK_REQUIRED — must not raise NameError for an empty film."""
    result = lint_sex_wardrobe([], heat_scale="max")
    assert isinstance(result, dict)
    assert result.get("issues", []) == []


def test_lint_user_source_fidelity_uses_regex() -> None:
    """Missing `import re` should not blow up adult-source-fidelity linting."""
    result = lint_user_source_fidelity(
        shots=[],
        source_excerpt="成人 短剧 办事",
        heat_scale="max",
    )
    assert isinstance(result, dict)