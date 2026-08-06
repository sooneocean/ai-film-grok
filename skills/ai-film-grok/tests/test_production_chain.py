from __future__ import annotations

import json
from pathlib import Path

import pytest
from media_queue import MediaQueue, QueueError
from production_chain import build_shot_contract, queue_contract_is_current
from production_evidence import build_evidence
from production_truth import audit_production_truth


def test_queue_contract_detects_plan_or_asset_drift(tmp_path: Path) -> None:
    spec = tmp_path / "film-spec.json"
    assets = tmp_path / "assets-registry.json"
    spec.write_text('{"title":"first","scenes":[]}', encoding="utf-8")
    assets.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "asset-registry",
                "characterStatesTimeline": [{"shotId": "shot01", "characterId": "hero"}],
            }
        ),
        encoding="utf-8",
    )

    contract = build_shot_contract(tmp_path, "shot01")

    assert contract["ok"]
    assert contract["plan"]["film_spec_sha256"]
    assert contract["assets"]["registry_sha256"]
    assert queue_contract_is_current(tmp_path, contract)["ok"]

    spec.write_text('{"title":"changed","scenes":[]}', encoding="utf-8")
    report = queue_contract_is_current(tmp_path, contract)
    assert not report["ok"]
    assert "FILM_SPEC_CHANGED" in report["errors"]

    spec.write_text('{"title":"first","scenes":[]}', encoding="utf-8")
    assets.write_text(
        '{"schema_version":1,"kind":"asset-registry","characters":[]}', encoding="utf-8"
    )
    report = queue_contract_is_current(tmp_path, contract)
    assert not report["ok"]
    assert "ASSET_REGISTRY_CHANGED" in report["errors"]


def test_legacy_queue_contract_is_explicitly_unbound(tmp_path: Path) -> None:
    contract = build_shot_contract(tmp_path, "shot01")

    assert contract["ok"]
    assert contract["mode"] == "legacy-unbound"
    assert queue_contract_is_current(tmp_path, contract)["ok"]


def test_evidence_reports_a_stale_queue_contract(tmp_path: Path) -> None:
    spec = tmp_path / "film-spec.json"
    spec.write_text('{"title":"first","scenes":[]}', encoding="utf-8")
    contract = build_shot_contract(tmp_path, "shot01")
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    (receipts / "media-queue.json").write_text(
        json.dumps({"jobs": [{"id": "job-1", "source_contract": contract}]}),
        encoding="utf-8",
    )
    spec.write_text('{"title":"changed","scenes":[]}', encoding="utf-8")

    report = build_evidence(tmp_path)

    queue = report["evidence"]["queue"]
    assert not queue["contracts_current"]
    assert queue["stale_job_ids"] == ["job-1"]


def test_queue_refuses_to_complete_after_its_plan_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIFILM_SKIP_HEAT_QUEUE_GATE", "1")
    monkeypatch.setattr("media_queue.assert_pilot_allows_add", lambda *_args, **_kwargs: None)
    root = tmp_path / "film"
    root.mkdir()
    spec = root / "film-spec.json"
    spec.write_text('{"title":"first","scenes":[]}', encoding="utf-8")
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("a still", encoding="utf-8")
    source = tmp_path / "input.png"
    source.write_bytes(b"input")
    output = tmp_path / "output.png"
    output.write_bytes(b"output")

    queue = MediaQueue(root)
    job = queue.add_job(
        shot_id="shot01",
        operation="image_gen",
        prompt_file=prompt,
        inputs=[source],
        allow_without_pilot=True,
    )
    assert job["source_contract"]["plan"]["film_spec_sha256"]
    claimed = queue.claim()
    assert claimed is not None

    spec.write_text('{"title":"changed","scenes":[]}', encoding="utf-8")

    with pytest.raises(QueueError, match="FILM_SPEC_CHANGED"):
        queue.complete(
            str(job["id"]),
            claim_token=str(claimed["claim_token"]),
            output=output,
            endpoint="image_gen",
        )
    assert queue.state()["jobs"][0]["status"] == "running"


def test_canonical_chain_rejects_asset_drift_before_evidence_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asset_registry
    import narrative_control
    from aifilm_grok import empty_manifest
    from manifest_truth import migrate_manifest

    root = tmp_path / "film"
    root.mkdir()
    (root / "film-spec.json").write_text('{"title":"first","scenes":[]}', encoding="utf-8")
    (root / "drama-graph.json").write_text("{}", encoding="utf-8")
    assets = root / "assets-registry.json"
    assets.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "asset-registry",
                "characterStatesTimeline": [{"shotId": "shot01", "characterId": "hero"}],
            }
        ),
        encoding="utf-8",
    )
    (root / "manifest.json").write_text(
        json.dumps(empty_manifest(title="Truth", theme="audit", aspect="9:16")), encoding="utf-8"
    )
    assert migrate_manifest(root, write=True)["ok"]
    ready = {
        "ok": True,
        "canonical": True,
        "semantic": {"ok": True},
        "projection": {"ok": True, "stale": False},
    }
    monkeypatch.setattr(narrative_control, "control_status", lambda _root: ready)
    monkeypatch.setattr(
        narrative_control, "assert_projection_ready", lambda *_args, **_kwargs: ready
    )
    monkeypatch.setattr(asset_registry, "assets_check", lambda *_args, **_kwargs: {"ok": True})
    monkeypatch.setattr("media_queue.assert_pilot_allows_add", lambda *_args, **_kwargs: None)
    monkeypatch.setenv("AIFILM_SKIP_HEAT_QUEUE_GATE", "1")
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("a still", encoding="utf-8")
    source = tmp_path / "input.png"
    source.write_bytes(b"input")
    output = tmp_path / "output.png"
    output.write_bytes(b"output")

    queue = MediaQueue(root)
    job = queue.add_job(
        shot_id="shot01",
        operation="image_gen",
        prompt_file=prompt,
        inputs=[source],
        allow_without_pilot=True,
    )
    claimed = queue.claim()
    assert job["source_contract"]["mode"] == "canonical"

    queue_path = root / "receipts" / "media-queue.json"
    corrupt = json.loads(queue_path.read_text(encoding="utf-8"))
    corrupt["jobs"][0].pop("source_contract")
    queue_path.write_text(json.dumps(corrupt), encoding="utf-8")
    with pytest.raises(QueueError, match="source contract is missing"):
        queue.complete(
            str(job["id"]),
            claim_token=str(claimed["claim_token"]),
            output=output,
            endpoint="image_gen",
        )

    repaired = json.loads(queue_path.read_text(encoding="utf-8"))
    repaired["jobs"][0]["source_contract"] = job["source_contract"]
    queue_path.write_text(json.dumps(repaired), encoding="utf-8")

    assets.write_text('{"schema_version":1,"kind":"asset-registry"}', encoding="utf-8")

    with pytest.raises(QueueError, match="ASSET_REGISTRY_CHANGED"):
        queue.complete(
            str(job["id"]),
            claim_token=str(claimed["claim_token"]),
            output=output,
            endpoint="image_gen",
        )
    assert not build_evidence(root)["evidence"]["queue"]["contracts_current"]
    assert "QUEUE_CONTRACT_STALE" in audit_production_truth(root)["blockers"]
