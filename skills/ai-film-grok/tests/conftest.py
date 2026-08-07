"""Shared pytest configuration for the ai-film-grok test suite.

This conftest ensures ``scripts/`` is on ``sys.path`` for every test collected
by pytest, so individual test files no longer need to repeat the
``sys.path.insert(...)`` boilerplate. Existing unittest-style tests that
inject the path themselves are unaffected (idempotent insert).

New tests: prefer ``from aifilm_grok import ...`` directly — the path is set
up here. Use the ``film_root`` fixture below instead of hand-rolling a tmp dir.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_ROOT / "scripts"
for import_root in (SKILL_ROOT, SCRIPTS):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))


def pytest_configure(config):
    # Register the web review-console marker so `pytest -m console` works
    # regardless of the invocation directory (CI runs from the skill subdir).
    config.addinivalue_line(
        "markers", "console: web review console (web_core / asset_picker / gateways / onboarding)"
    )


@pytest.fixture()
def film_root(tmp_path: Path) -> Path:
    """A temporary film root directory with an ``out/`` subdir.

    Use for tests that need a throwaway film project root without the full
    ``init`` ceremony. Cleans up automatically via ``tmp_path``.
    """
    root = tmp_path / "film"
    (root / "out").mkdir(parents=True, exist_ok=True)
    (root / "receipts").mkdir(parents=True, exist_ok=True)
    return root
