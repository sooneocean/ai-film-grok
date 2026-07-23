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
import tempfile
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


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
