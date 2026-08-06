from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

from sync_project_docs import project_data, status_block


def test_project_data_inventories_every_shipped_skill() -> None:
    data = project_data()

    assert data["shipped_skills"] == ["ai-film-grok", "ai-film-project"]
    assert "skills/ai-film-project/scripts/validate_project_blueprint.py" in data["scripts"]
    assert "skills/ai-film-project/tests/test_validate_project_blueprint.py" in data["tests"]
    assert "tests/test_premium_pipeline_contracts.py" in data["tests"]


def test_status_block_reports_shipped_skill_count() -> None:
    block = status_block(project_data())

    assert "Published skills：`2`" in block
