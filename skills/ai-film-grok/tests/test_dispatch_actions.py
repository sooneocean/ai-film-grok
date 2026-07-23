from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from dispatch import structured_next_action  # noqa: E402


def test_structured_next_action_is_directly_executable_and_paid_is_human_required() -> None:
    action = structured_next_action(
        {
            "id": "grok-i2v-bulk",
            "cmd": (
                "aifilm skill run --skill-id image.animate "
                '--payload-file "/film/receipts/animate-request.json"'
            ),
            "stage": "visual",
        },
        context={"input_hashes": {"film-spec": "a" * 64}, "node_refs": ["shot:01"]},
    )
    assert action["skill_id"] == "image.animate"
    assert action["operation"] == "skill"
    assert action["argv"][:2] == ["skill", "run"]
    assert action["approval_class"] == "human_required"
    assert action["transaction_id"].startswith("tx-")


def test_structured_next_action_rejects_comments_and_placeholders() -> None:
    assert structured_next_action({"id": "bulk", "cmd": "# Media: generate"}) is None
    assert (
        structured_next_action({"id": "bulk", "cmd": 'aifilm media --shot-id <id> --prompt "…"'})
        is None
    )
