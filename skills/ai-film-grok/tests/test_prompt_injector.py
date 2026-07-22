import pytest

from scripts.prompt_injector import PromptConflictError, PromptInjector


def test_prompt_assembly_priority(tmp_path):
    bible = {
        "schema_version": 2,
        "signature_block": "Cinematic 8k, photorealistic",
        "lighting": "moody dark lighting",
        "characters": {
            "hero": {"identity": "tall man with short black hair", "default_wardrobe": "black suit"}
        },
        "wardrobe_variants": {},
        "continuity_states": {"weather": "raining heavily"},
        "negative_hints": "cartoon, 3d, ugly",
    }

    shot = {"id": "shot01", "heroine_ids": ["hero"], "dsl": {"action": "walking down the street"}}

    injector = PromptInjector(bible, template_version="T2I")
    receipt = injector.assemble(shot, tmp_path)

    prompt = receipt["prompt_text"]

    # Priority check: Style -> Lighting -> Character -> Continuity -> Action -> Negative
    assert "Style: Cinematic 8k" in prompt
    assert "Lighting: moody" in prompt
    assert "Character hero: tall man with short black hair" in prompt
    assert "Wardrobe hero: black suit" in prompt
    assert "Continuity: raining heavily" in prompt
    assert "Action: walking down the street" in prompt
    assert "--no cartoon, 3d, ugly" in prompt


def test_prompt_conflict_detection(tmp_path):
    bible = {
        "schema_version": 2,
        "characters": {
            "hero": {
                "identity": "woman with silver hair",
            }
        },
    }

    shot = {
        "id": "shot01",
        "heroine_ids": ["hero"],
        "dsl": {"action": "woman with blonde hair walking"},
    }

    injector = PromptInjector(bible)

    with pytest.raises(PromptConflictError) as excinfo:
        injector.assemble(shot, tmp_path)

    assert "conflicts with locked trait" in str(excinfo.value)


def test_state_photo_path_stays_in_receipt_not_provider_prompt(tmp_path):
    state_photo = "/private/production/cast/hero-undressed.png"
    bible = {
        "characters": {"hero": {"identity": "short black hair"}},
        "cast_state_masters": {"hero": {"undressed": state_photo}},
        "negative_hints": "no text, NO TEXT, watermark",
    }
    shot = {
        "id": "shot02",
        "heroine_ids": ["hero"],
        "wardrobe_state": "undressed",
        "dsl": {"action": "turns toward the door"},
    }

    receipt = PromptInjector(bible, template_version="I2V").assemble(shot, tmp_path)

    assert state_photo not in receipt["prompt_text"]
    assert receipt["reference_instruction"].startswith("State photo ref: " + state_photo)
    assert receipt["prompt_metrics"]["estimated_input_tokens"] > 0
    assert receipt["prompt_text"].count("no text") == 1
