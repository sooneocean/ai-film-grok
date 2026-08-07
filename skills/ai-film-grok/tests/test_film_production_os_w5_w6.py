"""Film Production OS W5–W6: prompt compiler, takes review, revise, assembly."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from assembly_gate import check_assembly_takes  # noqa: E402
from prompt_compiler import (  # noqa: E402
    compile_for_shot,
    compile_prompt_artifact,
    extract_shot_spec,
    lint_provider_leak,
)
from revise_plan import plan_revision  # noqa: E402
from take_registry import compare_takes, set_take_review  # noqa: E402


def test_prompt_compiler_adapters_differ_same_spec():
    shot = {
        "id": "s1",
        "shot_purpose": "show_reaction",
        "action": "she freezes at the door",
        "shot_size": "cu",
        "spoken_text": "别过来。",
    }
    original = copy.deepcopy(shot)
    h3 = compile_for_shot(shot, adapter="h3")
    grok = compile_for_shot(shot, adapter="grok")
    assert h3["prompt"] != grok["prompt"]
    assert "Vertical 9:16" in h3["prompt"] or "Mandarin" in h3["prompt"]
    assert h3["mutates_project"] is False
    assert shot == original  # project graph unchanged
    assert h3["source_shot_spec"]["shot_id"] == "s1"


def test_provider_leak_lint():
    bad = lint_provider_leak({"action": "use --ar 9:16 minimax style"})
    assert bad["ok"] is False
    assert "PROVIDER_SYNTAX_IN_PROJECT" in bad["codes"]
    clean = lint_provider_leak({"action": "she turns away"})
    assert clean["ok"] is True


def test_extract_shot_spec_no_provider_fields():
    spec = extract_shot_spec(
        {
            "id": "x",
            "shot_purpose": "establish_location",
            "dsl": {"shot_size": "ws", "visible_change": "rain on glass"},
        }
    )
    art = compile_prompt_artifact(spec, adapter="generic")
    assert "rain" in art["prompt"].lower() or "establish" in art["prompt"].lower()


def test_compare_and_review_takes():
    manifest = {
        "clips": {
            "s1": {
                "take_id": "t1",
                "state": "candidate",
                "active": True,
                "director_review": {},
            }
        },
        "take_history": {
            "s1": [
                {
                    "take_id": "t0",
                    "state": "superseded",
                    "active": False,
                    "director_review": {
                        "performance": 3,
                        "continuity": 4,
                        "camera": 3,
                        "artifacts": 5,
                    },
                }
            ]
        },
    }
    cmp = compare_takes(manifest, "s1")
    assert cmp["candidate_count"] == 2
    rev = set_take_review(
        manifest,
        "s1",
        take_id="t1",
        performance=5,
        continuity=4,
        camera=4,
        artifacts=5,
        director_status="selected",
    )
    assert rev["ok"] is True
    assert rev["director_status"] == "selected"
    assert manifest["clips"]["s1"]["active"] is True
    assert manifest["clips"]["s1"]["director_review"]["performance"] == 5
    cmp2 = compare_takes(manifest, "s1")
    selected = [c for c in cmp2["candidates"] if c["take_id"] == "t1"][0]
    assert selected["review_approved"] is True
    assert selected["score_total"] >= 5


def test_revise_plan_never_whole_scene():
    r = plan_revision(defect="face", shot_id="s1")
    assert r["ok"] is True
    assert r["regenerate_whole_scene"] is False
    assert r["unit"] == "shot_region"
    bad = plan_revision(defect="unknown_xyz")
    assert bad["ok"] is False


def test_assembly_blocks_draft():
    man = {
        "clips": {
            "a": {"state": "draft", "active": False},
            "b": {"state": "approved", "active": True, "director_status": "approved"},
        }
    }
    soft = check_assembly_takes(man, strict=False)
    assert "ASSEMBLY_DRAFT_TAKE" in soft["codes"]
    hard = check_assembly_takes(man, strict=True)
    assert hard["ok"] is False
    assert hard["rough_cut_allowed"] is False
    assert "b" in hard["allowed_shot_ids"]
    assert "a" in hard["blocked_shot_ids"]


def test_assembly_allows_selected():
    man = {
        "clips": {
            "a": {"state": "selected", "active": True, "director_status": "selected"},
        }
    }
    rep = check_assembly_takes(man, strict=True)
    assert rep["ok"] is True
    assert rep["rough_cut_allowed"] is True


def test_w7_cine_rules_and_performance_acting_layer():
    from cine_rules import enrich_shot_spec_with_cine, lookup_cine_rule
    from performance_cue import normalize_performance_cue

    look = lookup_cine_rule(purpose="create_tension")
    assert look["matched"] is True
    assert look["key"] == "tension"
    assert look["shot_size"]
    spec = enrich_shot_spec_with_cine(
        {
            "shot_purpose": "establish_location",
            "framing": {},
            "performance": {"emotion": "fearful"},
        }
    )
    assert spec["cine_suggestion"]["matched"] is True
    # fear emotion beats empty framing
    assert spec["framing"].get("shot_size")

    cue = normalize_performance_cue(
        {
            "emotion": "tender",
            "intensity": 0.4,
            "objective": "赢得信任",
            "subtext": "其实害怕离开",
            "eye": "avoid then meet",
            "breath": "shallow then release",
            "tempo": "slow",
        }
    )
    assert cue["objective"] == "赢得信任"
    assert cue["subtext"]
    assert cue["tempo"] == "slow"
