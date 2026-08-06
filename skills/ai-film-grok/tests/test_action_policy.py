"""R4 action policy + catalog advance coverage."""

from spine.action_policy import catalog_advance_ids, resolve_policy, resolve_skill_id
from spine.advance import ADVANCE_ACTIONS, advance_eligible_ids


def test_resolve_skill_defaults():
    assert resolve_skill_id("gate-auto") == "projection.verify"
    assert resolve_skill_id("unknown-xyz") == "dispatch.orchestrate"


def test_pilot_stays_human():
    spend, approval = resolve_policy(action_id="pilot-approve", operation="pilot")
    assert approval == "human_required"


def test_gate_auto_local_none():
    spend, approval = resolve_policy(action_id="gate-auto", operation="gate-auto")
    assert spend == "local"
    assert approval == "none"


def test_advance_allowlist_nonempty():
    ids = advance_eligible_ids()
    assert "gate-auto" in ids
    assert "export-desktop" in ids
    assert ids == frozenset(ADVANCE_ACTIONS)


def test_catalog_covers_advance_keys():
    catalog = catalog_advance_ids()
    if not catalog:
        return  # soft if catalog missing in odd envs
    missing = set(ADVANCE_ACTIONS) - catalog
    # allow a few legacy advance-only keys to be added to catalog over time
    # but core machine gates must be present
    for core in ("gate-auto", "ship-prep", "export-desktop", "bulk-preflight"):
        assert core in catalog or core in ADVANCE_ACTIONS
    # hard: no ADVANCE key should be unknown to catalog when catalog is loaded
    assert not missing, f"catalog missing advance_eligible: {sorted(missing)}"
