from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from production_book import (  # noqa: E402
    ProductionBookConflict,
    ProductionBookError,
    init_production_book,
    read_production_book,
    stable_content_hash,
    update_department,
)


def test_new_init_defaults_to_professional_and_writes_canonical_book(tmp_path: Path) -> None:
    book = init_production_book(
        tmp_path, title="雨夜", format_pack="vertical-short", genre_pack="drama"
    )

    assert book["rigor"] == "professional"
    assert book["state"] == "draft"
    assert book["phase"] == "development"
    assert book["stage"] == "idea"
    assert book["packs"] == {"format": "vertical-short", "genre": "drama"}
    assert set(book["departments"]) >= {"story", "visual", "sound", "post", "delivery"}
    assert book["content_sha256"] == stable_content_hash(book)
    assert json.loads((tmp_path / "production-book.json").read_text())["title"] == "雨夜"


def test_legacy_book_without_rigor_reads_as_legacy(tmp_path: Path) -> None:
    (tmp_path / "production-book.json").write_text(
        json.dumps({"title": "旧片", "phase": "production", "assets": ["clips/keep.mp4"]}),
        encoding="utf-8",
    )

    book = read_production_book(tmp_path)

    assert book["rigor"] == "legacy"
    assert book["assets"] == ["clips/keep.mp4"]


def test_read_rejects_tampered_book_instead_of_repairing_hash(tmp_path: Path) -> None:
    init_production_book(tmp_path, rigor="professional")
    path = tmp_path / "production-book.json"
    value = json.loads(path.read_text())
    value["rigor"] = "legacy"
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ProductionBookError, match="tampered"):
        read_production_book(tmp_path)


def test_expected_revision_prevents_lost_update(tmp_path: Path) -> None:
    init_production_book(tmp_path)
    update_department(tmp_path, "story", revision=2, content_sha256="a" * 64, expected_revision=1)

    with pytest.raises(ProductionBookConflict, match="expected revision 1"):
        update_department(
            tmp_path, "visual", revision=2, content_sha256="b" * 64, expected_revision=1
        )
