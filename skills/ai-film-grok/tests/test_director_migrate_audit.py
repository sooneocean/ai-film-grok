from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from director_cli import check, migrate, migrate_audit  # noqa: E402
from production_book import (  # noqa: E402
    init_production_book,
    read_production_book,
    write_production_book,
)


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


def test_migrate_normalizes_revision_zero_legacy_book_before_department_sync(
    tmp_path: Path,
) -> None:
    bible = tmp_path / "bible"
    bible.mkdir()
    (bible / "style-bible.json").write_text('{"schema_version": 3}', encoding="utf-8")
    (tmp_path / "production-book.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "departments": {"style-bible": {"source_file": "bible/style-bible.json"}},
            }
        ),
        encoding="utf-8",
    )

    result = migrate(tmp_path)

    assert result["ok"] is True
    assert result["book"]["revision"] >= 2
    assert (tmp_path / "style-bible.json").exists() is False


def test_check_validates_department_referenced_from_nested_book_path(tmp_path: Path) -> None:
    init_production_book(tmp_path)
    bible = tmp_path / "bible"
    bible.mkdir()
    (bible / "style-bible.json").write_text("{}", encoding="utf-8")
    book = read_production_book(tmp_path)
    book["departments"]["visual"]["source_file"] = "bible/style-bible.json"
    write_production_book(tmp_path, book)

    report = check(tmp_path)

    assert any(item["department_id"] == "visual" for item in report["departments"])
