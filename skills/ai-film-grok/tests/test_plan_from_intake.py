from __future__ import annotations

import sys
from argparse import Namespace
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cli_plan_run import run_from_intake  # noqa: E402
from intake import create_intake  # noqa: E402


def _png(path: Path) -> None:
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + (13).to_bytes(4, "big")
        + b"IHDR"
        + (720).to_bytes(4, "big")
        + (1280).to_bytes(4, "big")
        + b"\x08\x06\x00\x00\x00\x00\x00\x00\x00"
    )


def test_plan_from_intake_preserves_character_id(tmp_path: Path) -> None:
    story = tmp_path / "novel.md"
    story.write_text("沈璃走进雨里。", encoding="utf-8")
    image = tmp_path / "hero.png"
    _png(image)
    root = tmp_path / "film"
    create_intake(root, story=story, characters=[("hero", image)], character_names={"hero": "沈璃"})
    report, code = run_from_intake(
        Namespace(
            title="雨夜",
            target_duration=30,
            apply_film_spec=False,
            no_film_spec=False,
            force=True,
            no_bible=False,
        ),
        root,
    )
    assert code == 0, report
    assert report["ok"]
    assert report["intake"]["quality"]["ready_for_planning"]
