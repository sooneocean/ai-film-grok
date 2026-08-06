from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from intake import approve_character, create_intake  # noqa: E402


def _png(path: Path) -> None:
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + (13).to_bytes(4, "big")
        + b"IHDR"
        + (720).to_bytes(4, "big")
        + (1280).to_bytes(4, "big")
        + b"\x08\x06\x00\x00\x00\x00\x00\x00\x00"
    )


def test_binding_requires_review_before_generation(tmp_path: Path) -> None:
    story = tmp_path / "novel.md"
    story.write_text("# 第一章\n\n沈璃推开门。", encoding="utf-8")
    image = tmp_path / "hero.png"
    _png(image)
    root = tmp_path / "film"

    report = create_intake(
        root,
        story=story,
        characters=[("hero", image)],
        character_names={"hero": "沈璃"},
    )

    assert report["character_bindings"][0]["confidence"] == "probable"
    assert not report["quality"]["ready_for_generation"]
    approved = approve_character(root, character_id="hero", user_phrase="确认定妆")
    assert approved["ok"]
    assert approved["report"]["quality"]["ready_for_generation"]
