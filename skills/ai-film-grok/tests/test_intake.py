from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from intake import create_intake, validate_intake  # noqa: E402


def _png(path: Path, width: int = 720, height: int = 1280) -> None:
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + (13).to_bytes(4, "big")
        + b"IHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x06\x00\x00\x00"
        + b"\x00\x00\x00\x00"
    )


def test_create_intake_stages_hashes_and_paragraph_evidence(tmp_path: Path) -> None:
    story = tmp_path / "novel.md"
    story.write_text("# 第一章\n\n她推开门。\n\n他站在雨里。\n", encoding="utf-8")
    image = tmp_path / "hero.png"
    _png(image)
    root = tmp_path / "film"

    report = create_intake(root, story=story, characters=[("hero", image)])

    assert report["ok"]
    assert report["story"]["paragraph_count"] == 3
    assert (root / "intake-manifest.json").is_file()
    assert (root / "receipts" / "intake-report.json").is_file()
    refs = [item["source_ref"] for item in report["story"]["evidence"]]
    assert all(ref.startswith("novel:") for ref in refs)
    manifest = json.loads((root / "intake-manifest.json").read_text(encoding="utf-8"))
    assert manifest["characters"][0]["reference_image"]["width"] == 720


def test_validate_intake_fails_after_staged_story_tampering(tmp_path: Path) -> None:
    story = tmp_path / "novel.txt"
    story.write_text("她回头。", encoding="utf-8")
    image = tmp_path / "hero.png"
    _png(image)
    root = tmp_path / "film"
    create_intake(root, story=story, characters=[("hero", image)])
    staged = root / "intake" / "story" / story.name
    staged.write_text("她没有回头。", encoding="utf-8")

    report = validate_intake(root)

    assert not report["ok"]
    assert any("sha256 changed" in error for error in report["errors"])


def test_validate_intake_warns_on_small_reference(tmp_path: Path) -> None:
    story = tmp_path / "novel.txt"
    story.write_text("她回头。", encoding="utf-8")
    image = tmp_path / "hero.png"
    _png(image, 256, 256)
    root = tmp_path / "film"
    report = create_intake(root, story=story, characters=[("hero", image)])

    assert report["ok"]
    assert any("below 512px" in warning for warning in report["warnings"])
