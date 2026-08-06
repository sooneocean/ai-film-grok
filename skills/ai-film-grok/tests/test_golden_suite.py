from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from gates.golden_suite import validate_golden_contract  # noqa: E402


def _valid_contract() -> dict:
    return {
        "format": {"aspect": "9:16", "duration_sec": 45},
        "characters": {},
        "shots": [],
        "dialogue": {},
        "approvals": [
            {
                "input_hash": "h",
                "current_hash": "h",
                "approver_type": "human",
                "scope": "film",
            }
        ],
    }


def test_valid_contract_ok():
    rep = validate_golden_contract(_valid_contract())
    assert rep["ok"] is True
    assert rep["issues"] == []
    assert rep["human_approval_required"] is True
    assert rep["automated_result"] == "advisory"


def test_invalid_format_reports_issue():
    c = _valid_contract()
    c["format"] = {"aspect": "16:9", "duration_sec": 30}
    rep = validate_golden_contract(c)
    assert rep["ok"] is False
    assert "GOLDEN_FORMAT_INVALID" in {i["code"] for i in rep["issues"]}


def test_missing_human_approval_reports_issue():
    c = _valid_contract()
    c["approvals"] = []
    rep = validate_golden_contract(c)
    assert rep["ok"] is False
    assert "HUMAN_APPROVAL_MISSING" in {i["code"] for i in rep["issues"]}


def test_key_dialogue_checksum_invalid():
    c = _valid_contract()
    c["dialogue"] = {"d1": {"text": "hello", "checksum": "deadbeef", "required": True}}
    rep = validate_golden_contract(c)
    assert rep["ok"] is False
    assert "KEY_DIALOGUE_CHECKSUM_INVALID" in {i["code"] for i in rep["issues"]}
