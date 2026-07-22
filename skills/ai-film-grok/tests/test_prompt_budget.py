from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from prompt_budget import prompt_budget_report  # noqa: E402


def test_prompt_budget_classifies_repeated_locks_and_keeps_read_only(tmp_path: Path) -> None:
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    for shot_id in ("s1", "s2"):
        (receipts / f"prompt_assembly_{shot_id}.json").write_text(
            json.dumps(
                {
                    "shot_id": shot_id,
                    "prompt_text": "Style: ink wash\nCharacter hero: black hair\nNo labels or watermark",
                    "reference_instruction": "State photo ref: /local-only.png",
                }
            ),
            encoding="utf-8",
        )

    report = prompt_budget_report(tmp_path)

    assert report["read_only"] is True
    assert report["shot_count"] == 2
    assert report["total_estimated_input_tokens"] > 0
    assert report["local_only_reference_instructions"]["count"] == 2
    repeated = {item["line"]: item["classification"] for item in report["repeated_provider_lines"]}
    assert repeated["Style: ink wash"] == "identity_or_style_lock"
    assert report["compression_candidates"][0]["line"] == "No labels or watermark"
    assert report["compression_candidates"][0]["apply_automatically"] is False
    assert report["protected_repeated_lines"][0]["line"] == "Style: ink wash"
    assert not (receipts / "prompt-budget.json").exists()


def test_prompt_budget_write_is_explicit(tmp_path: Path) -> None:
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    (receipts / "prompt_assembly_s1.json").write_text(
        json.dumps({"shot_id": "s1", "prompt_text": "Action: enters"}), encoding="utf-8"
    )

    report = prompt_budget_report(tmp_path, write=True)

    assert report["read_only"] is False
    assert Path(report["path"]).is_file()


def test_prompt_budget_threshold_only_requires_review(tmp_path: Path) -> None:
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    (receipts / "prompt_assembly_s1.json").write_text(
        json.dumps({"shot_id": "s1", "prompt_text": "Action: enters"}), encoding="utf-8"
    )

    report = prompt_budget_report(tmp_path, max_estimated_tokens=1)

    assert report["budget_status"] == "over_budget_review_required"
    assert report["read_only"] is True
