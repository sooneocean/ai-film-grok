"""Tests for P1-1/P1-2/P1-3/P1-4: cast_locks + hair_swatches + makeup + wardrobe sheet.

Verifies:
- cast_locks structured fields override free-text identity_lock
- Hair lock line injected from cast_locks.hair_lock or hair_swatches fallback
- Makeup line injected from cast_locks.makeup_lock or makeup field fallback
- P1-4: structured wardrobe object (garment/accessories/material/color) assembled correctly
- P1-4: legacy string wardrobe still works (backward compat)
- Backward compat: no cast_locks → falls back to identity_lock (unchanged)
- NEVER tokens appended to Hair lock line
"""

from scripts.prompt_injector import PromptInjector


def _make_bible(**kwargs) -> dict:
    bible = {
        "schema_version": 2,
        "signature_block": "Cinematic 8k photorealistic",
        "lighting": "moody dark",
        "characters": {
            "hero": {"identity": "woman with silver hair", "default_wardrobe": "black dress"}
        },
        "wardrobe_variants": {},
        "continuity_states": {},
        "negative_hints": "cartoon, 3d",
    }
    bible.update(kwargs)
    return bible


def _make_shot() -> dict:
    return {
        "id": "shot01",
        "heroine_ids": ["hero"],
        "dsl": {"action": "standing in the rain"},
    }


class TestCastLocksStructured:
    """P1-1: cast_locks structured fields override free-text identity_lock."""

    def test_cast_locks_identity_tokens_override_identity(self, tmp_path):
        bible = _make_bible(
            cast_locks={
                "hero": {
                    "identity_lock_tokens": "pale face, silver-white waist-length hair, purple eyes",
                    "never_tokens": "NEVER pure black hair, NEVER brown eyes",
                }
            }
        )
        shot = _make_shot()
        injector = PromptInjector(bible, template_version="T2I")
        receipt = injector.assemble(shot, tmp_path)
        prompt = receipt["prompt_text"]
        assert "pale face, silver-white waist-length hair, purple eyes" in prompt
        # The free-text identity should be overridden
        assert "woman with silver hair" not in prompt

    def test_hair_lock_line_injected_from_cast_locks(self, tmp_path):
        bible = _make_bible(
            cast_locks={
                "hero": {
                    "identity_lock_tokens": "silver hair",
                    "hair_lock": "dark teal cyan-green; long waist-length",
                    "never_tokens": "NEVER pure black",
                }
            }
        )
        shot = _make_shot()
        injector = PromptInjector(bible, template_version="T2I")
        receipt = injector.assemble(shot, tmp_path)
        prompt = receipt["prompt_text"]
        assert "Hair lock hero: dark teal cyan-green; long waist-length" in prompt
        assert "NEVER pure black" in prompt

    def test_makeup_lock_line_injected_from_cast_locks(self, tmp_path):
        bible = _make_bible(
            cast_locks={
                "hero": {
                    "identity_lock_tokens": "silver hair",
                    "makeup_lock": "natural dewy base, soft pink lips",
                }
            }
        )
        shot = _make_shot()
        injector = PromptInjector(bible, template_version="T2I")
        receipt = injector.assemble(shot, tmp_path)
        prompt = receipt["prompt_text"]
        assert "Makeup hero: natural dewy base, soft pink lips" in prompt


class TestHairSwatchesFallback:
    """P1-2: hair_swatches provides Hair lock when cast_locks.hair_lock is absent."""

    def test_hair_swatches_fallback_builds_hair_lock(self, tmp_path):
        bible = _make_bible(
            hair_swatches={
                "hero": {
                    "color_name": "dark teal cyan-green",
                    "hex": "#1A8B8B",
                    "description": "long waist-length straight hair",
                }
            }
        )
        shot = _make_shot()
        injector = PromptInjector(bible, template_version="T2I")
        receipt = injector.assemble(shot, tmp_path)
        prompt = receipt["prompt_text"]
        assert "Hair lock hero: dark teal cyan-green" in prompt
        assert "long waist-length straight hair" in prompt

    def test_hair_lock_from_cast_locks_takes_precedence_over_swatches(self, tmp_path):
        bible = _make_bible(
            cast_locks={
                "hero": {
                    "identity_lock_tokens": "silver hair",
                    "hair_lock": "platinum blonde; short bob",
                }
            },
            hair_swatches={
                "hero": {
                    "color_name": "dark teal",
                    "description": "long hair",
                }
            },
        )
        shot = _make_shot()
        injector = PromptInjector(bible, template_version="T2I")
        receipt = injector.assemble(shot, tmp_path)
        prompt = receipt["prompt_text"]
        assert "platinum blonde; short bob" in prompt
        assert "dark teal" not in prompt


class TestMakeupFallback:
    """P1-3: makeup field provides Makeup line when cast_locks.makeup_lock is absent."""

    def test_makeup_field_fallback(self, tmp_path):
        bible = _make_bible(
            makeup={
                "hero": {
                    "name": "smoky evening",
                    "lock_tokens": "dark eyeshadow, red lipstick",
                    "cross_scene_consistency": True,
                }
            }
        )
        shot = _make_shot()
        injector = PromptInjector(bible, template_version="T2I")
        receipt = injector.assemble(shot, tmp_path)
        prompt = receipt["prompt_text"]
        assert "Makeup hero: dark eyeshadow, red lipstick" in prompt

    def test_cast_locks_makeup_takes_precedence(self, tmp_path):
        bible = _make_bible(
            cast_locks={
                "hero": {
                    "identity_lock_tokens": "silver hair",
                    "makeup_lock": "natural look",
                }
            },
            makeup={
                "hero": {
                    "lock_tokens": "heavy makeup",
                }
            },
        )
        shot = _make_shot()
        injector = PromptInjector(bible, template_version="T2I")
        receipt = injector.assemble(shot, tmp_path)
        prompt = receipt["prompt_text"]
        assert "Makeup hero: natural look" in prompt
        assert "heavy makeup" not in prompt


class TestBackwardCompat:
    """Without cast_locks/hair_swatches/makeup, behavior is unchanged."""

    def test_no_cast_locks_falls_back_to_identity(self, tmp_path):
        bible = _make_bible()
        shot = _make_shot()
        injector = PromptInjector(bible, template_version="T2I")
        receipt = injector.assemble(shot, tmp_path)
        prompt = receipt["prompt_text"]
        assert "Character hero: woman with silver hair" in prompt
        assert "Hair lock" not in prompt
        assert "Makeup" not in prompt

    def test_no_hair_swatches_no_hair_lock(self, tmp_path):
        bible = _make_bible()
        shot = _make_shot()
        injector = PromptInjector(bible, template_version="T2I")
        receipt = injector.assemble(shot, tmp_path)
        prompt = receipt["prompt_text"]
        assert "Hair lock" not in prompt


class TestWardrobeSheetStructured:
    """P1-4: structured wardrobe object (garment/accessories/material/color)."""

    def test_structured_wardrobe_assembled(self, tmp_path):
        bible = _make_bible(
            wardrobe_variants={
                "hero": {
                    "default": {
                        "garment": "black trench coat, white shirt",
                        "accessories": ["silver watch", "leather gloves"],
                        "material": "wool coat, cotton shirt",
                        "color": "black/white",
                        "state": "full",
                    }
                }
            }
        )
        shot = _make_shot()
        injector = PromptInjector(bible, template_version="T2I")
        receipt = injector.assemble(shot, tmp_path)
        prompt = receipt["prompt_text"]
        assert "black trench coat, white shirt" in prompt
        assert "silver watch" in prompt
        assert "leather gloves" in prompt
        assert "material: wool coat" in prompt
        assert "color: black/white" in prompt

    def test_legacy_string_wardrobe_still_works(self, tmp_path):
        bible = _make_bible(wardrobe_variants={"hero": {"default": "black dress with silver trim"}})
        shot = _make_shot()
        injector = PromptInjector(bible, template_version="T2I")
        receipt = injector.assemble(shot, tmp_path)
        prompt = receipt["prompt_text"]
        assert "black dress with silver trim" in prompt

    def test_structured_wardrobe_no_accessories(self, tmp_path):
        bible = _make_bible(
            wardrobe_variants={
                "hero": {
                    "default": {
                        "garment": "simple white robe",
                        "color": "white",
                    }
                }
            }
        )
        shot = _make_shot()
        injector = PromptInjector(bible, template_version="T2I")
        receipt = injector.assemble(shot, tmp_path)
        prompt = receipt["prompt_text"]
        assert "simple white robe" in prompt
        assert "color: white" in prompt
        assert "accessories" not in prompt
