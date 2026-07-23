from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from department_cli import migrate_department  # noqa: E402
from director_cli import rebuild  # noqa: E402
from production_book import (  # noqa: E402
    apply_stale_propagation,
    impact_dry_run,
    init_production_book,
)
from util import read_json  # noqa: E402


def test_impact_is_only_transitive_dependency_closure_and_dry_run_is_pure(tmp_path: Path) -> None:
    book = init_production_book(tmp_path)
    before = book.copy()

    impact = impact_dry_run(book, ["story"], reason="story hash changed")

    assert impact["affected"] == [
        "story",
        "editorial",
        "visual",
        "performance",
        "sound",
        "post",
        "delivery",
    ]
    assert "legal" not in impact["affected"]
    assert book == before


def test_apply_marks_only_closure_stale_and_never_deletes_assets(tmp_path: Path) -> None:
    book = init_production_book(tmp_path)
    book["assets"] = ["keyframes/shot01.png", "clips/shot01.mp4"]
    impact = impact_dry_run(book, ["sound"], reason="mix changed")

    changed = apply_stale_propagation(book, impact, expected_revision=1)

    assert impact["affected"] == ["sound", "post", "delivery"]
    assert changed["departments"]["sound"]["state"] == "stale"
    assert changed["departments"]["post"]["state"] == "stale"
    assert changed["departments"]["visual"]["state"] == "draft"
    assert changed["assets"] == book["assets"]
    assert changed["revision"] == 2
    assert changed["stale_reasons"][-1]["reason"] == "mix changed"


def test_director_rebuild_stales_department_bibles_and_book_together(tmp_path: Path) -> None:
    init_production_book(tmp_path)
    for department, filename in (
        ("visual", "style-bible.json"),
        ("audio", "audio-bible.json"),
        ("post", "post-bible.json"),
    ):
        (tmp_path / filename).write_text(json.dumps({"revision": 1}), encoding="utf-8")
        migrate_department(tmp_path, department)
    revision = int(read_json(tmp_path / "production-book.json")["revision"])

    report = rebuild(
        tmp_path,
        changed_refs=["visual"],
        reason="hair color changed",
        expected_revision=revision,
    )

    assert report["book"]["departments"]["visual"]["state"] == "stale"
    assert read_json(tmp_path / "style-bible.json")["state"] == "stale"
    assert read_json(tmp_path / "audio-bible.json")["state"] == "stale"
    assert read_json(tmp_path / "post-bible.json")["state"] == "stale"
