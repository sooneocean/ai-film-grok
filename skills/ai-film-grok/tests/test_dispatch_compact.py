from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from context_routing import select_context_refs  # noqa: E402
from dispatch import _capability_report_cached, build_dispatch  # noqa: E402
from dispatch_compact import (  # noqa: E402
    compact_dispatch,
    compute_state_hash,
    record_orchestration_metrics,
)


def _film(root: Path) -> None:
    (root / "brief.json").write_text('{"title":"t","theme":"x"}\n', encoding="utf-8")
    (root / "film-spec.json").write_text(
        json.dumps(
            {
                "title": "t",
                "tts_backend": "edge",
                "shots": [{"id": "shot01", "nar": "话说", "dramatic_function": "hook"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_compact_packet_is_small_and_keeps_execution_contract(tmp_path: Path) -> None:
    _film(tmp_path)
    full = build_dispatch(
        tmp_path,
        include_capability=False,
        write_receipt=True,
        use_state_cache=False,
    )
    compact = compact_dispatch(full)
    body = json.dumps(compact, ensure_ascii=False).encode("utf-8")

    assert len(body) <= 5000
    assert compact["schema_version"] == 3
    assert compact["mode"] == "compact"
    for key in (
        "skill_id",
        "operation",
        "argv",
        "spend_class",
        "approval_class",
        "responsibility",
        "verification",
        "transaction_id",
        "state_hash",
    ):
        assert compact["next_action"][key] == full["next_action"][key]
    assert compact["state_hash"] == full["state_hash"]
    assert len(compact["context_refs"]) <= 3
    assert "generation_usage" not in compact
    assert "jobs_summary" not in compact
    assert "routing" not in compact
    assert "production_evidence" not in compact
    assert "agent_instruction" not in compact
    assert compact["responsibility"] == full["responsibility"]


def test_compact_packet_bounds_untrusted_human_readable_fields() -> None:
    packet = {
        "ok": True,
        "schema_version": 2,
        "at": "2026-07-24T00:00:00+00:00",
        "root": "/tmp/film",
        "craft_stage": "media",
        "pipeline_stage": "visual",
        "next_id": "quality-gate-repair",
        "next_cmd": 'aifilm preflight --root "/tmp/film"',
        "next_why": "shot-" + ("x" * 6000),
        "next_action": {
            "skill_id": "dispatch.orchestrate",
            "operation": "preflight",
            "argv": ["preflight", "--root", "/tmp/film"],
            "node_refs": ["shot-" + ("x" * 6000)],
            "input_hashes": {"job": "hash"},
            "dependencies": [],
            "spend_class": "local",
            "approval_class": "none",
            "expected_outputs": [],
            "verification": ["preflight"],
            "transaction_id": "tx-123",
            "state_hash": "state",
        },
        "state_hash": "state",
        "metrics": {"build_elapsed_ms": 1.0},
    }
    compact = compact_dispatch(packet)
    without_action = {**compact, "next_action": {}}
    assert len(json.dumps(without_action, ensure_ascii=False).encode("utf-8")) <= 5000
    assert len(compact["next_why"].encode("utf-8")) <= 768
    assert compact["next_action"]["transaction_id"] == "tx-123"
    assert compact["next_action"]["verification"] == ["preflight"]
    assert compact["next_action"]["node_refs"] == packet["next_action"]["node_refs"]
    assert compact["next_action"] == packet["next_action"]


def test_full_packet_preserves_pre_compaction_golden_semantics(tmp_path: Path) -> None:
    _film(tmp_path)
    full = build_dispatch(
        tmp_path,
        include_capability=False,
        write_receipt=False,
        use_state_cache=False,
    )
    compact = compact_dispatch(full)
    golden = json.loads(
        (Path(__file__).resolve().parent / "fixtures" / "dispatch-full-v1-golden.json").read_text(
            encoding="utf-8"
        )
    )

    assert full["schema_version"] == golden["schema_version"]
    assert full["next_id"] == golden["next"]["id"]
    for key in golden["required_full_sections"]:
        assert key in full
    for key in golden["required_action_fields"]:
        assert key in full["next_action"]
    for key in ("skill_id", "operation", "spend_class", "approval_class"):
        assert full["next_action"][key] == golden["next"][key]
    assert full["graph"]["exists"] is golden["graph"]["exists"]
    assert full["quality"]["ok"] is golden["quality"]["ok"]
    assert full["quality"]["failed_count"] == golden["quality"]["failed_count"]
    assert (
        full["production_evidence"]["ready_for_bulk"]
        is golden["production_evidence"]["ready_for_bulk"]
    )
    assert full["hard_gates"] == golden["hard_gates"]
    assert compact["hard_gate_codes"] == golden["hard_gate_codes"]


def test_state_hash_ignores_dispatch_telemetry_but_tracks_control_inputs(
    tmp_path: Path,
) -> None:
    _film(tmp_path)
    first = compute_state_hash(tmp_path)
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    (receipts / "dispatch.json").write_text('{"noise":1}', encoding="utf-8")
    (receipts / "orchestration-usage.jsonl").write_text("{}\n", encoding="utf-8")
    assert compute_state_hash(tmp_path) == first
    (tmp_path / "film-spec.json").write_text('{"title":"changed"}\n', encoding="utf-8")
    assert compute_state_hash(tmp_path) != first


def test_context_router_enforces_count_and_byte_budgets() -> None:
    refs = select_context_refs(
        craft_stage="media",
        pipeline_stage="visual",
        skill_id="image.animate",
        issue_codes=["HUMAN_APPROVAL_REQUIRED"],
    )
    assert 1 <= len(refs) <= 3
    assert sum(int(item["bytes"]) for item in refs) <= 8192
    assert all((Path(__file__).resolve().parents[1] / item["path"]).is_file() for item in refs)


def test_capability_cache_reuses_safe_projection(tmp_path: Path) -> None:
    _film(tmp_path)
    report = {
        "ok": True,
        "recommendations": ["x"],
        "tts": {"edge": True},
        "frw": {"present": False},
    }
    with patch("capability_report.build_capability_report", return_value=report) as probe:
        first, first_meta = _capability_report_cached(
            tmp_path,
            i2v_profile="grok_primary",
            refresh=False,
            write_cache=True,
        )
        second, second_meta = _capability_report_cached(
            tmp_path,
            i2v_profile="grok_primary",
            refresh=False,
            write_cache=True,
        )
    assert first == second
    assert first_meta["hit"] is False
    assert second_meta["hit"] is True
    assert probe.call_count == 1


def test_unchanged_local_dispatch_uses_state_cache(tmp_path: Path) -> None:
    _film(tmp_path)
    build_dispatch(tmp_path, include_capability=False, write_receipt=True)
    build_dispatch(tmp_path, include_capability=False, write_receipt=True)
    cached = build_dispatch(tmp_path, include_capability=False, write_receipt=True)
    assert cached["metrics"]["state_cache_hit"] is True


def test_dispatch_does_not_derive_graph_as_a_read_side_effect(tmp_path: Path) -> None:
    _film(tmp_path)
    assert not (tmp_path / "drama-graph.json").exists()
    packet = build_dispatch(
        tmp_path,
        include_capability=False,
        write_receipt=False,
        use_state_cache=False,
    )
    assert packet["next_id"] == "write-spec"
    assert not (tmp_path / "drama-graph.json").exists()


def test_orchestration_metrics_are_separate_from_generation_usage(tmp_path: Path) -> None:
    _film(tmp_path)
    full = build_dispatch(tmp_path, include_capability=False, write_receipt=True)
    compact = compact_dispatch(full)
    path = record_orchestration_metrics(tmp_path, compact)
    record = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
    assert record["kind"] == "orchestration-usage"
    assert "cost_usd" not in record
    assert "prompt" not in record


def test_skill_entry_and_compact_context_stay_inside_token_budgets() -> None:
    skill_root = Path(__file__).resolve().parents[1]
    assert (skill_root / "SKILL.md").stat().st_size <= 6000
    routing = json.loads((skill_root / "registry" / "context-routing.json").read_text())
    assert routing["max_refs"] == 3
    assert routing["max_bytes"] == 8192
    for stage in ("agent", "visual", "voice", "post", "deliver", "approval"):
        assert (skill_root / "references" / "stages" / f"{stage}.md").is_file()


def test_dispatch_cli_defaults_compact_and_supports_full_rollback(tmp_path: Path) -> None:
    _film(tmp_path)
    script = SCRIPTS / "aifilm_grok.py"
    base = [
        sys.executable,
        str(script),
        "dispatch",
        "--root",
        str(tmp_path),
        "--no-capability",
        "--no-write",
    ]
    compact_run = subprocess.run(base, check=False, capture_output=True, text=True)
    assert compact_run.returncode == 0, compact_run.stderr
    assert json.loads(compact_run.stdout)["mode"] == "compact"

    full_run = subprocess.run(
        [*base, "--format", "full"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert full_run.returncode == 0, full_run.stderr
    assert json.loads(full_run.stdout)["schema_version"] == 2

    env = dict(os.environ)
    env["AIFILM_DISPATCH_FORMAT"] = "full"
    env_run = subprocess.run(base, check=False, capture_output=True, text=True, env=env)
    assert env_run.returncode == 0, env_run.stderr
    assert json.loads(env_run.stdout)["schema_version"] == 2
