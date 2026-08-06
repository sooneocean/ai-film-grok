from __future__ import annotations

import json
from pathlib import Path

from production_truth import audit_production_truth


def test_truth_audit_reports_a_current_manifest_and_optional_control_records(
    tmp_path: Path,
) -> None:
    from aifilm_grok import empty_manifest
    from manifest_truth import migrate_manifest
    from production_book import init_production_book

    (tmp_path / "film-spec.json").write_text('{"production_mode":"shortform"}', encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps(empty_manifest(title="Truth", theme="audit", aspect="9:16")), encoding="utf-8"
    )
    assert migrate_manifest(tmp_path, write=True)["ok"]
    init_production_book(tmp_path)

    report = audit_production_truth(tmp_path)

    assert report["ok"]
    assert report["authority"]["creative_contract"] == "film-spec.json"
    assert report["authority"]["asset_and_delivery_receipts"] == "manifest.json"
    assert report["checks"]["manifest"]["ok"]
    assert report["checks"]["production_book"]["present"]


def test_truth_audit_fails_closed_for_stale_manifest_contract(tmp_path: Path) -> None:
    (tmp_path / "film-spec.json").write_text('{"production_mode":"shortform"}', encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "stills": {},
                "clips": {},
                "truth_contract": {
                    "source_of_truth": "local-contract-and-receipts",
                    "contract_sha256": "stale",
                },
            }
        ),
        encoding="utf-8",
    )

    report = audit_production_truth(tmp_path)

    assert not report["ok"]
    assert "MANIFEST_TRUTH_INVALID" in report["blockers"]


def test_truth_audit_surfaces_a_stale_queue_contract(tmp_path: Path) -> None:
    from aifilm_grok import empty_manifest
    from manifest_truth import migrate_manifest
    from production_chain import build_shot_contract

    spec = tmp_path / "film-spec.json"
    spec.write_text('{"title":"first","scenes":[]}', encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps(empty_manifest(title="Truth", theme="audit", aspect="9:16")), encoding="utf-8"
    )
    contract = build_shot_contract(tmp_path, "shot01")
    spec.write_text('{"title":"changed","scenes":[]}', encoding="utf-8")
    assert migrate_manifest(tmp_path, write=True)["ok"]
    receipts = tmp_path / "receipts"
    receipts.mkdir(exist_ok=True)
    (receipts / "media-queue.json").write_text(
        json.dumps({"jobs": [{"id": "job-1", "source_contract": contract}]}),
        encoding="utf-8",
    )

    report = audit_production_truth(tmp_path)

    assert not report["ok"]
    assert "QUEUE_CONTRACT_STALE" in report["blockers"]


def test_truth_audit_blocks_a_canonical_graph_that_is_not_ready(
    tmp_path: Path, monkeypatch
) -> None:
    import narrative_control
    from aifilm_grok import empty_manifest
    from manifest_truth import migrate_manifest

    (tmp_path / "film-spec.json").write_text('{"production_mode":"shortform"}', encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps(empty_manifest(title="Truth", theme="audit", aspect="9:16")), encoding="utf-8"
    )
    (tmp_path / "drama-graph.json").write_text("{}", encoding="utf-8")
    assert migrate_manifest(tmp_path, write=True)["ok"]
    monkeypatch.setattr(
        narrative_control,
        "control_status",
        lambda _root: {
            "ok": False,
            "canonical": True,
            "projection": {"ok": True, "stale": False},
        },
    )

    report = audit_production_truth(tmp_path)

    assert not report["ok"]
    assert "CANONICAL_GRAPH_NOT_READY" in report["blockers"]


def test_truth_audit_is_exposed_as_a_read_only_cli(tmp_path: Path, capsys) -> None:
    import aifilm_grok

    (tmp_path / "film-spec.json").write_text('{"production_mode":"shortform"}', encoding="utf-8")

    assert aifilm_grok.main(["truth", "audit", "--root", str(tmp_path)]) == 2

    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "production-truth-audit"
    assert "MANIFEST_TRUTH_INVALID" in payload["blockers"]


def test_canonical_truth_blocks_final_and_review_before_media_work(
    tmp_path: Path, monkeypatch
) -> None:
    import argparse

    import aifilm_grok
    import production_truth

    monkeypatch.setattr(
        production_truth,
        "audit_production_truth",
        lambda _root: {
            "ok": False,
            "checks": {"canonical_graph": {"canonical": True}},
            "blockers": ["QUEUE_CONTRACT_STALE"],
        },
    )
    args = argparse.Namespace(root=str(tmp_path))

    import pytest

    with pytest.raises(aifilm_grok.FilmError, match="QUEUE_CONTRACT_STALE"):
        aifilm_grok.cmd_final(args)
    with pytest.raises(aifilm_grok.FilmError, match="QUEUE_CONTRACT_STALE"):
        aifilm_grok.cmd_review_final(args)


def test_legacy_truth_remains_delivery_compatible(tmp_path: Path, monkeypatch) -> None:
    import production_truth

    monkeypatch.setattr(
        production_truth,
        "audit_production_truth",
        lambda _root: {
            "ok": False,
            "checks": {"canonical_graph": {"canonical": False}},
            "blockers": ["MANIFEST_TRUTH_INVALID"],
        },
    )

    assert production_truth.require_current_canonical_truth(tmp_path)["ok"] is False


def test_skip_canonical_truth_contract_default_off() -> None:
    """S1.2: skip is opt-in; default off for locked series safety."""
    import production_truth

    c = production_truth.resolve_skip_canonical_truth(flag=False, env={})
    assert c["skip"] is False
    assert c["default"] == "off"
    c2 = production_truth.resolve_skip_canonical_truth(
        flag=False, env={"AIFILM_SKIP_CANONICAL_TRUTH": "1"}
    )
    assert c2["skip"] is True
    assert c2["via_env"] is True
    c3 = production_truth.resolve_skip_canonical_truth(flag=True, env={})
    assert c3["skip"] is True
    assert c3["via_flag"] is True
    assert "locked_canonical_series_default" in c3["not_for"]


def test_skip_canonical_truth_receipt_writes(tmp_path: Path) -> None:
    import production_truth

    c = production_truth.resolve_skip_canonical_truth(flag=True, env={})
    path = production_truth.write_skip_canonical_truth_receipt(tmp_path, c)
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("skip") is True
