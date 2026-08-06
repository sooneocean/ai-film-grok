"""R1: route-catalog structural consistency."""

from __future__ import annotations

import json
from pathlib import Path

import route_catalog
from route_catalog import catalog_path, load_catalog, validate_catalog


def test_catalog_file_exists_and_schema():
    path = catalog_path()
    assert path.is_file(), path
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("schema_version") == 1
    assert data.get("kind") == "ai-film-route-catalog"
    assert isinstance(data.get("routes"), list)
    assert len(data["routes"]) >= 50


def test_validate_catalog_ok():
    report = validate_catalog()
    assert report["ok"] is True, report.get("errors")
    assert report["counts"]["routes"] >= 50
    assert report["counts"]["advance_eligible"] >= 20


def test_load_catalog_ok_flag():
    cat = load_catalog()
    assert cat.get("ok") is True, cat.get("validation")
    assert Path(cat["path"]).is_file()


def test_no_duplicate_ids():
    cat = load_catalog()
    ids = [r["id"] for r in cat["routes"] if isinstance(r, dict)]
    assert len(ids) == len(set(ids))


def test_advance_actions_are_kind_action():
    for route in route_catalog.list_routes(advance_only=True):
        assert route["kind"] == "action", route


def test_if_ladder_cmds_tagged_in_catalog():
    """Hub residual if-ladder must appear so R3 can close them out."""
    cat = load_catalog()
    meta = cat.get("meta") or {}
    if_ladder = set(meta.get("if_ladder") or [])
    if not if_ladder:
        # meta optional after hand-edit; derive from tags
        tagged = {
            r["cli_cmd"]
            for r in cat["routes"]
            if isinstance(r, dict) and r.get("hub_if_ladder") and r.get("cli_cmd")
        }
        assert len(tagged) >= 20
        return
    tagged = {
        r.get("cli_cmd") or r.get("id")
        for r in cat["routes"]
        if isinstance(r, dict) and r.get("hub_if_ladder")
    }
    missing = if_ladder - tagged
    # allow cli: prefix rows
    tagged_cmds = {
        r["cli_cmd"]
        for r in cat["routes"]
        if isinstance(r, dict) and r.get("cli_cmd") and r.get("hub_if_ladder")
    }
    missing = if_ladder - tagged_cmds
    assert not missing, f"if_ladder not tagged in catalog: {sorted(missing)[:10]}"
