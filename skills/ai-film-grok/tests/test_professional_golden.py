from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from gates.golden_suite import validate_golden_contract  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "professional-director-golden"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_non_adult_golden_has_full_professional_contract() -> None:
    report = validate_golden_contract(_fixture("non_adult_45s.json"))
    assert report["ok"], report["issues"]
    assert report["human_approval_required"] is True


def test_adult_rules_are_isolated_from_core() -> None:
    drama = _fixture("non_adult_45s.json")
    adult = _fixture("adult_genre_regression.json")
    assert not set(adult["genre_rules"]) & set(drama["core_rules"])
    assert validate_golden_contract(adult)["genre_pack"] == "adult"
    assert not validate_golden_contract(drama)["adult_rules_active"]


def test_injected_director_failures_are_machine_detected() -> None:
    base = _fixture("non_adult_45s.json")
    mutations = {
        "FACE_DRIFT": lambda c: c["shots"][0]["characters"]["mei"].update(face_hash="f" * 64),
        "HAIR_COLOR_DRIFT": lambda c: c["shots"][0]["characters"]["mei"].update(hair_color="blue"),
        "WARDROBE_REGRESSION": lambda c: c["shots"][2]["characters"]["mei"].update(
            wardrobe_state="coat"
        ),
        "PROP_STATE_REGRESSION": lambda c: c["shots"][2]["props"].update(
            {"red-umbrella": "closed"}
        ),
        "AXIS_CROSSING": lambda c: c["shots"][2].update(axis_bridge=False),
        "VOICE_DRIFT": lambda c: c["shots"][1]["characters"]["mei"].update(voice_id="other"),
        "KEY_DIALOGUE_MISSING": lambda c: c["shots"][1].update(dialogue_events=[]),
        "BGM_OVER_DIALOGUE": lambda c: c["shots"][1]["music_cues"][0].update(duck_db=2),
        "CAPTION_OUT_OF_WINDOW": lambda c: c["shots"][1]["caption_events"][0].update(end=21),
        "APPROVAL_HASH_MISMATCH": lambda c: c["approvals"][0].update(current_hash="changed"),
    }
    for expected, mutate in mutations.items():
        contract = copy.deepcopy(base)
        mutate(contract)
        codes = {issue["code"] for issue in validate_golden_contract(contract)["issues"]}
        assert expected in codes, (expected, codes)


def test_automated_scores_never_become_human_pass() -> None:
    contract = _fixture("non_adult_45s.json")
    contract["approvals"] = [{"scope": "golden", "approver_type": "model", "pass": True}]
    report = validate_golden_contract(contract)
    assert not report["ok"]
    assert "HUMAN_APPROVAL_MISSING" in {item["code"] for item in report["issues"]}
