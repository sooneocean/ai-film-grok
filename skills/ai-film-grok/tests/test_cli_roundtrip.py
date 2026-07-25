from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AIFILM = ROOT / "scripts" / "aifilm"


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(AIFILM), *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def test_plan_validate_roundtrip_preserves_projection_and_fails_closed(tmp_path: Path) -> None:
    plan = _run(
        "plan",
        "run",
        "--root",
        str(tmp_path),
        "--text",
        "A courier discovers a hidden letter before sunset.",
        "--title",
        "Roundtrip",
        "--apply-film-spec",
        "--no-bible",
        cwd=ROOT,
    )
    assert plan.returncode == 0, plan.stdout + plan.stderr
    assert (tmp_path / "drama-graph.json").is_file()
    assert (tmp_path / "film-spec.json").is_file()

    validate = _run("plan", "validate", "--root", str(tmp_path), "--strict", cwd=ROOT)
    assert validate.returncode == 1, validate.stdout + validate.stderr
    report = json.loads(validate.stdout)
    projection = json.loads((tmp_path / "film-spec.json").read_text())["_projection"]
    assert projection["source"] == "drama-graph.json"
    assert projection["source_revision"] == 1
    assert report["ok"] is False
    assert "DIRECTOR_BOARD_FIELD_MISSING" in report["issue_codes"]
