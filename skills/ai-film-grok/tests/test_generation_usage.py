from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from generation_usage import (  # noqa: E402
    GenerationUsageError,
    accept_generation,
    finish_generation,
    manual_record,
    scan_usage,
    start_generation,
    usage_list,
    usage_status,
)


def test_exact_cost_and_tokens_are_aggregated_without_float_rounding(tmp_path: Path) -> None:
    root = tmp_path / "film"
    gid = start_generation(root, operation="t2i", provider="xai", model="image-1")
    finish_generation(
        root,
        gid,
        status="succeeded",
        usage={
            "input_tokens": 11,
            "output_tokens": 7,
            "total_tokens": 18,
            "cost_in_usd_ticks": 200_000_001,
        },
        measurement="provider_exact",
    )

    report = usage_status(root)
    assert report["requests_total"] == 1
    assert report["cost_in_usd_ticks"] == 200_000_001
    assert report["cost_usd"] == "0.0200000001"
    assert report["tokens"] == {"input": 11, "output": 7, "total": 18}
    assert report["token_reported_requests"] == 1
    assert report["unknown_cost_requests"] == 0


def test_async_video_accept_and_finish_count_once(tmp_path: Path) -> None:
    root = tmp_path / "film"
    gid = start_generation(root, operation="i2v", provider="xai", model="video-1")
    accept_generation(root, gid, provider_request_id="rid-1")
    finish_generation(
        root,
        gid,
        status="succeeded",
        provider_request_id="rid-1",
        usage={"cost_in_usd_ticks": 500},
        measurement="provider_exact",
    )
    # A repeated final poll is idempotent.
    finish_generation(
        root,
        gid,
        status="succeeded",
        provider_request_id="rid-1",
        usage={"cost_in_usd_ticks": 500},
        measurement="provider_exact",
    )

    report = usage_status(root)
    assert report["requests_total"] == 1
    assert report["status_counts"] == {"succeeded": 1}
    assert usage_list(root)["records"][0]["provider_request_id"] == "rid-1"


def test_split_provider_usage_merges_token_components_exactly(tmp_path: Path) -> None:
    gid = start_generation(tmp_path, operation="i2v", provider="xai")
    accept_generation(
        tmp_path,
        gid,
        provider_request_id="rid-split",
        usage={"input_tokens": 5, "cost_in_usd_ticks": 10},
    )
    finish_generation(
        tmp_path,
        gid,
        status="succeeded",
        usage={"output_tokens": 7},
        measurement="unknown",
        provider_request_id="rid-split",
    )

    record = usage_list(tmp_path)["records"][0]
    assert record["usage"] == {
        "input_tokens": 5,
        "output_tokens": 7,
        "total_tokens": 12,
        "cost_in_usd_ticks": 10,
    }


def test_terminal_event_requires_started_lifecycle(tmp_path: Path) -> None:
    with pytest.raises(GenerationUsageError, match="requires started"):
        finish_generation(
            tmp_path / "film",
            "gen-orphan",
            status="failed",
            measurement="unknown",
        )


def test_fractional_ticks_are_rejected_instead_of_truncated(tmp_path: Path) -> None:
    gid = start_generation(tmp_path, operation="t2i", provider="xai")
    with pytest.raises(GenerationUsageError, match="must be an integer"):
        finish_generation(
            tmp_path,
            gid,
            status="succeeded",
            usage={"cost_in_usd_ticks": 1.9},
            measurement="provider_exact",
        )


def test_retry_is_a_separate_generation_and_unknown_is_visible(tmp_path: Path) -> None:
    root = tmp_path / "film"
    first = start_generation(root, operation="i2v", provider="xai", model="video-1")
    finish_generation(root, first, status="failed", measurement="unknown")
    second = start_generation(root, operation="i2v", provider="xai", model="video-1")
    finish_generation(
        root,
        second,
        status="succeeded",
        usage={"cost_in_usd_ticks": 1000},
        measurement="provider_exact",
    )

    report = usage_status(root)
    assert report["requests_total"] == 2
    assert report["status_counts"] == {"failed": 1, "succeeded": 1}
    assert report["unknown_cost_requests"] == 1
    assert report["cost_in_usd_ticks"] == 1000


def test_manual_success_is_deduplicated_by_output_hash(tmp_path: Path) -> None:
    root = tmp_path / "film"
    output = root / "keyframes" / "shot01.png"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"same generated image")

    first = manual_record(
        root,
        operation="t2i",
        provider="grok_native",
        model="image_gen",
        status="succeeded",
        output=output,
        measurement="unknown",
        shot_id="shot01",
    )
    second = manual_record(
        root,
        operation="t2i",
        provider="grok_native",
        model="image_gen",
        status="succeeded",
        output=output,
        measurement="unknown",
        shot_id="shot01",
    )

    assert first["generation_id"] == second["generation_id"]
    assert usage_status(root)["requests_total"] == 1


def test_failed_manual_record_requires_stable_identity(tmp_path: Path) -> None:
    with pytest.raises(GenerationUsageError, match="idempotency"):
        manual_record(
            tmp_path / "film",
            operation="i2v",
            provider="grok_native",
            model="image_to_video",
            status="failed",
            measurement="unknown",
        )


def test_local_zero_cost_is_exactly_known(tmp_path: Path) -> None:
    root = tmp_path / "film"
    manual_record(
        root,
        operation="tts",
        provider="edge",
        model="edge-neural",
        status="succeeded",
        provider_request_id="local-shot01",
        measurement="local_zero",
    )
    report = usage_status(root)
    assert report["cost_in_usd_ticks"] == 0
    assert report["unknown_cost_requests"] == 0
    assert report["measurement_counts"] == {"local_zero": 1}


def test_tts_backend_records_local_zero(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import tts_backend

    monkeypatch.setattr(
        tts_backend,
        "probe",
        lambda: {"active": "edge", "backends": {"edge": True}},
    )

    def fake_edge(_text: str, out: Path, _voice: str, **_kwargs: object) -> Path:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"ID3" + b"x" * 600)
        return out

    monkeypatch.setattr(tts_backend, "tts_edge", fake_edge)
    root = tmp_path / "film"
    out = root / "audio" / "shot01.mp3"
    tts_backend.synthesize(
        "你好",
        out,
        backend="edge",
        usage_root=root,
        shot_id="shot01",
    )

    report = usage_status(root)
    assert report["requests_total"] == 1
    assert report["measurement_counts"] == {"local_zero": 1}
    assert report["cost_in_usd_ticks"] == 0


def test_scan_usage_aggregates_projects_and_warns_on_corrupt_ledger(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    for name, ticks in (("a", 100), ("b", 300)):
        root = projects / name
        manual_record(
            root,
            operation="t2i",
            provider="xai",
            model="image-1",
            status="succeeded",
            provider_request_id=f"rid-{name}",
            measurement="manual_exact",
            cost_in_usd_ticks=ticks,
        )
    corrupt = projects / "broken" / "receipts" / "generation-usage.json"
    corrupt.parent.mkdir(parents=True)
    corrupt.write_text("{broken", encoding="utf-8")

    report = scan_usage(projects)
    assert report["project_count"] == 2
    assert report["requests_total"] == 2
    assert report["cost_in_usd_ticks"] == 400
    assert len(report["warnings"]) == 1


def test_missing_ledger_is_backward_compatible(tmp_path: Path) -> None:
    report = usage_status(tmp_path / "legacy")
    assert report["ok"] is True
    assert report["tracking_status"] == "tracking_not_started"
    assert report["requests_total"] == 0


def test_ledger_never_stores_raw_usage_fields(tmp_path: Path) -> None:
    root = tmp_path / "film"
    gid = start_generation(root, operation="t2i", provider="xai", model="image-1")
    finish_generation(
        root,
        gid,
        status="succeeded",
        usage={
            "cost_in_usd_ticks": 10,
            "authorization": "Bearer secret",
            "prompt": "private prompt",
        },
        measurement="provider_exact",
    )
    raw = json.loads((root / "receipts" / "generation-usage.json").read_text())
    text = json.dumps(raw)
    assert "Bearer secret" not in text
    assert "private prompt" not in text
