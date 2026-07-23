from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from drama_graph import build_jobs_summary, derive_graph  # noqa: E402
from skill_registry import validate_execution_graph  # noqa: E402


def test_every_execution_job_resolves_complete_registry_contract(tmp_path: Path) -> None:
    spec = {
        "title": "registry-contract",
        "scenes": [
            {
                "title": "main",
                "shots": [
                    {
                        "id": "shot01",
                        "dramatic_function": "hook",
                        "duration_sec": 3,
                        "dsl": {"subject": "hero", "action": "turns"},
                    }
                ],
            }
        ],
    }
    (tmp_path / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
    (tmp_path / "style-bible.json").write_text(json.dumps({"locked": True}), encoding="utf-8")
    derive_graph(tmp_path, write=True)

    summary = build_jobs_summary(tmp_path, craft_stage="shots")
    report = validate_execution_graph(summary["jobs"])

    assert report["ok"], report
    for job in summary["jobs"]:
        contract = job["executionContract"]
        assert contract["input"]
        assert contract["output"]
        assert contract["validator"]
        assert contract["runner"]
