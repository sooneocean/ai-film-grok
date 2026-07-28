from __future__ import annotations

import json
from pathlib import Path

from manifest_truth import migrate_manifest, preflight_manifest


def test_legacy_manifest_is_not_production_truth(tmp_path: Path) -> None:
    (tmp_path / "film-spec.json").write_text("{}", encoding="utf-8")
    manifest = {"schema_version": 1, "stills": {}, "clips": {}}
    report = preflight_manifest(tmp_path, manifest)
    assert not report["ok"]
    assert any("legacy" in error for error in report["errors"])


def test_migration_is_explicit_and_dry_by_default(tmp_path: Path) -> None:
    (tmp_path / "film-spec.json").write_text("{}", encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps({"schema_version": 1, "stills": {}, "clips": {}}), encoding="utf-8"
    )
    result = migrate_manifest(tmp_path, write=False)
    assert result["ok"]
    assert not result["changed"]
    assert json.loads((tmp_path / "manifest.json").read_text())["schema_version"] == 1
