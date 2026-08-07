"""R2 stage projection."""

from spine.stage_model import (
    CRAFT_EIGHT,
    INTERNAL_PIPELINE,
    PUBLIC_CRAFT,
    project_stages,
    to_pipeline_stage,
    to_public_craft,
)


def test_public_craft_five():
    assert PUBLIC_CRAFT == ("agent", "visual", "voice", "post", "deliver")


def test_design_aliases_to_post():
    assert to_public_craft("design") == "post"
    assert to_pipeline_stage("design") == "design"


def test_craft_eight_projects():
    assert to_public_craft("idea", source="craft_eight") == "agent"
    assert to_public_craft("media", source="craft_eight") == "visual"
    assert to_public_craft("rough", source="craft_eight") == "post"
    assert to_public_craft("verified", source="craft_eight") == "deliver"
    assert set(CRAFT_EIGHT) <= set(CRAFT_EIGHT)


def test_project_stages_packet_keys():
    p = project_stages(craft_stage="media", pipeline_stage="visual")
    assert p["craft_stage"] == "media"
    assert p["pipeline_stage"] == "visual"
    assert p["stage_public"] == "visual"
    assert p["pipeline_stage"] in INTERNAL_PIPELINE


def test_craft_spine_rings_are_stage_model_single_source():
    """C3: craft_spine must not fork CRAFT_EIGHT."""
    from craft_spine import CRAFT_STAGES

    assert CRAFT_STAGES is CRAFT_EIGHT or tuple(CRAFT_STAGES) == tuple(CRAFT_EIGHT)
