from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from benchmark import run_benchmark  # noqa: E402
from production_book import init_production_book  # noqa: E402


def test_contract_has_four_premium_cases(tmp_path: Path) -> None:
    init_production_book(tmp_path, quality_target="premium_vertical")
    report = run_benchmark(tmp_path, suite="premium-vertical", mode="contract")
    assert report["ok"] is True
    assert [item["duration_sec"] for item in report["cases"]] == [45, 45, 45, 90]
    assert (tmp_path / "receipts" / "premium-benchmark.json").is_file()


def test_live_mode_fails_closed_without_spend(tmp_path: Path) -> None:
    report = run_benchmark(tmp_path, suite="premium-vertical", mode="live")
    assert report["ok"] is False
    assert report["blockers"][0]["code"] == "LIVE_CANARY_APPROVAL_REQUIRED"
