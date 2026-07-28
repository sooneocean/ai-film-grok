from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from director_cli import migrate_audit  # noqa: E402


def test_migrate_audit_uses_in_root_book_department_source_file(tmp_path: Path) -> None:
    bible = tmp_path / "bible"
    bible.mkdir()
    (bible / "style-bible.json").write_text('{"schema_version": 3}', encoding="utf-8")
    (tmp_path / "production-book.json").write_text(
        json.dumps({"departments": {"style-bible": {"source_file": "bible/style-bible.json"}}}),
        encoding="utf-8",
    )

    items = {item["department"]: item for item in migrate_audit(tmp_path)["departments"]}

    assert items["visual"]["exists"] is True
    assert items["visual"]["status"] == "current"
    assert items["visual"]["path_source"] == "production_book"
    assert items["visual"]["path"] == str(bible / "style-bible.json")


def test_migrate_audit_uses_current_book_department_key(tmp_path: Path) -> None:
    bible = tmp_path / "bible"
    bible.mkdir()
    (bible / "style-bible.json").write_text('{"schema_version": 3}', encoding="utf-8")
    (tmp_path / "production-book.json").write_text(
        json.dumps({"departments": {"visual": {"source_file": "bible/style-bible.json"}}}),
        encoding="utf-8",
    )

    visual = next(
        item for item in migrate_audit(tmp_path)["departments"] if item["department"] == "visual"
    )

    assert visual["exists"] is True
    assert visual["status"] == "current"
    assert visual["path_source"] == "production_book"


def test_migrate_audit_does_not_follow_book_path_outside_root(tmp_path: Path) -> None:
    (tmp_path / "production-book.json").write_text(
        json.dumps({"departments": {"style-bible": {"source_file": "/tmp/not-our-bible.json"}}}),
        encoding="utf-8",
    )

    visual = next(
        item for item in migrate_audit(tmp_path)["departments"] if item["department"] == "visual"
    )

    assert visual["path"] == str(tmp_path / "style-bible.json")
    assert visual["path_source"] == "default"
