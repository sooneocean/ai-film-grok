from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import frw_ab  # noqa: E402
from frw_ab import (  # noqa: E402
    FrwABError,
    approve_rank,
    build_plan,
    build_production_plan,
    poll_experiment,
    rank_candidates,
    run_experiment,
)
from i2v_provider import route_after_failure  # noqa: E402
from util import canonical_json_sha256  # noqa: E402


def _catalog() -> dict:
    def capability(
        model: str,
        operation: str,
        *,
        callable_: bool = True,
        source: str = "platform_catalog",
    ) -> dict:
        return {
            "capability_id": f"{operation}:{model}",
            "operation": operation,
            "model_id": model,
            "status": "advertised" if callable_ else "unknown",
            "source": source,
            "invocation": {
                "callable": callable_,
                "command": "newvideo" if callable_ else None,
                "fixed_args": {"model": model} if callable_ else {},
            },
            "allowed_content_classes": ["general", "restricted"],
            "parameters": [
                {"name": "prompt", "type": "string", "required": True},
                {"name": "image_url", "type": "string", "required": True},
            ],
        }

    return {
        "catalog_schema_version": 1,
        "complete": True,
        "usage_policy": {
            "billing_class": "internal_unmetered",
            "fanout_allowed": True,
            "requires_cost_confirmation": False,
            "declared_concurrency_limit": None,
        },
        "trust_domain": "company_internal",
        "allowed_content_classes": ["general", "restricted"],
        "capabilities": [
            capability("seedance-a", "image_to_video"),
            capability("ltx-b", "image_to_video"),
            capability("t2v-only", "text_to_video"),
            capability("broken", "image_to_video", callable_=False),
            capability(
                "classic-provider-managed",
                "image_to_video",
                source="dispatcher_contract",
            ),
        ],
    }


def _inputs() -> dict[str, str]:
    return {
        "prompt": "camera slowly pushes toward the subject",
        "img-url": "https://cdn.example.com/frame.png",
    }


def _terminal_poll_for_run(run: dict) -> dict:
    poll = {
        "schema_version": 1,
        "kind": "frw-ab-poll",
        "experiment_id": run["experiment_id"],
        "operation": run["operation"],
        "run_sha256": run["run_sha256"],
        "results": [
            {
                "model_id": row["model_id"],
                "task_id": row["task_id"],
                "status": "completed",
                "url_sha256": "a" * 64,
                "error_code": None,
            }
            for row in run["submissions"]
            if row.get("status", "submitted") == "submitted"
        ],
        "terminal": True,
        "automatic_resubmit": False,
    }
    poll["poll_sha256"] = canonical_json_sha256(poll)
    return poll


def test_pilot_plan_fans_out_all_callable_platform_models_without_persisting_inputs(
    tmp_path: Path,
) -> None:
    plan = build_plan(
        tmp_path,
        experiment_id="shot01-pilot",
        operation="image_to_video",
        stage="pilot",
        content_class="restricted",
        inputs=_inputs(),
        catalog=_catalog(),
    )
    assert [row["model_id"] for row in plan["candidates"]] == [
        "classic-provider-managed",
        "ltx-b",
        "seedance-a",
    ]
    assert plan["fanout"]["mode"] == "all_eligible"
    assert plan["fanout"]["unmetered"] is True
    assert plan["provider_policy"]["changes_primary_provider"] is False
    serialized = json.dumps(plan)
    assert _inputs()["prompt"] not in serialized
    assert _inputs()["img-url"] not in serialized
    assert plan["input_bindings"]["prompt"]["sha256"]


def test_pilot_plan_can_limit_rerun_to_two_explicit_eligible_models(
    tmp_path: Path,
) -> None:
    plan = build_plan(
        tmp_path,
        experiment_id="shot01-remediation",
        operation="image_to_video",
        stage="pilot",
        content_class="restricted",
        inputs=_inputs(),
        catalog=_catalog(),
        selected_models=["seedance-a", "ltx-b"],
    )
    assert [row["model_id"] for row in plan["candidates"]] == [
        "ltx-b",
        "seedance-a",
    ]
    assert plan["fanout"]["mode"] == "selected_eligible"

    for selected_models in (
        ["seedance-a"],
        ["seedance-a", "seedance-a"],
        ["seedance-a", "not-advertised"],
    ):
        with pytest.raises(FrwABError, match="INVALID_MODEL_SELECTION"):
            build_plan(
                tmp_path,
                experiment_id=f"shot01-invalid-{len(selected_models)}",
                operation="image_to_video",
                stage="pilot",
                content_class="restricted",
                inputs=_inputs(),
                catalog=_catalog(),
                selected_models=selected_models,
            )


def test_text_to_image_seed_is_hash_bound_and_forwarded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = _catalog()
    for capability in catalog["capabilities"]:
        if capability["operation"] == "image_to_video":
            capability["operation"] = "text_to_image"
            capability["capability_id"] = capability["capability_id"].replace(
                "image_to_video", "text_to_image"
            )
            capability["invocation"]["command"] = "text2image"
            capability["invocation"]["fixed_args"] = {"model": capability["model_id"]}
    inputs = {"prompt": "empty station", "seed": "340701"}
    plan = build_plan(
        tmp_path,
        experiment_id="seeded-t2i",
        operation="text_to_image",
        stage="pilot",
        content_class="general",
        inputs=inputs,
        catalog=catalog,
        selected_models=["seedance-a", "ltx-b"],
    )
    assert plan["input_bindings"]["seed"]["sha256"]
    assert "340701" not in json.dumps(plan)

    invoked = mock.Mock(return_value={"success": True, "data": {"task_id": "task-1"}})
    monkeypatch.setattr(frw_ab, "invoke_frw", invoked)
    frw_ab._frw_submit_candidate(plan["candidates"][0], inputs)
    argv = invoked.call_args.args[0]
    assert argv[argv.index("--seed") + 1] == "340701"


def test_plan_rejects_missing_operation_inputs(tmp_path: Path) -> None:
    with pytest.raises(FrwABError, match="INVALID_INPUTS"):
        build_plan(
            tmp_path,
            experiment_id="shot01-pilot",
            operation="image_to_video",
            stage="pilot",
            content_class="general",
            inputs={"prompt": "move"},
            catalog=_catalog(),
        )


def test_production_plan_requires_human_promotion_and_keeps_only_two_models(
    tmp_path: Path,
) -> None:
    with pytest.raises(FrwABError, match="PROMOTION_REQUIRED"):
        build_plan(
            tmp_path,
            experiment_id="shot01-production",
            operation="image_to_video",
            stage="production",
            content_class="general",
            inputs=_inputs(),
            catalog=_catalog(),
        )

    promotion = {
        "schema_version": 1,
        "kind": "frw-ab-promotion",
        "approved": True,
        "approved_by": "user",
        "operation": "image_to_video",
        "champion": "seedance-a",
        "challenger": "ltx-b",
        "catalog_sha256": "placeholder",
    }
    plan = build_production_plan(
        tmp_path,
        experiment_id="shot01-production",
        operation="image_to_video",
        content_class="general",
        inputs=_inputs(),
        catalog=_catalog(),
        promotion=promotion,
        shot_id="shot01",
        allow_test_catalog_hash=True,
    )
    assert [row["model_id"] for row in plan["candidates"]] == [
        "seedance-a",
        "ltx-b",
    ]
    assert plan["fanout"]["mode"] == "champion_challenger"
    assert plan["provider_policy"]["requires_provider_switch_receipt"] is True
    assert plan["provider_policy"]["shot_id"] == "shot01"


def test_production_i2v_run_requires_valid_technical_switch_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIFILM_PROVIDER_SWITCH_RECEIPT_KEY", "k" * 32)
    promotion = {
        "schema_version": 1,
        "kind": "frw-ab-promotion",
        "approved": True,
        "approved_by": "user",
        "operation": "image_to_video",
        "champion": "seedance-a",
        "challenger": "ltx-b",
        "catalog_sha256": "placeholder",
    }
    plan = build_production_plan(
        tmp_path,
        experiment_id="shot01-production",
        operation="image_to_video",
        content_class="general",
        inputs=_inputs(),
        catalog=_catalog(),
        promotion=promotion,
        shot_id="shot01",
        allow_test_catalog_hash=True,
    )
    submit = mock.Mock()
    with pytest.raises(FrwABError, match="PROVIDER_SWITCH_REQUIRED"):
        run_experiment(tmp_path, plan=plan, inputs=_inputs(), submit=submit)
    submit.assert_not_called()

    receipts = tmp_path / "receipts"
    switch_path = receipts / "provider-switch-shot01.json"
    switch_receipt = {
        "schema_version": 1,
        "kind": "provider-switch",
        "shot_id": "shot01",
        "primary_provider": "grok",
        "fallback_provider": "seedance",
        "reason_class": "technical_failure",
        "error": "upstream timeout",
        "fallback_fixed_for_shot": True,
    }
    switch_receipt["switch_sha256"] = "tampered"
    switch_path.write_text(json.dumps(switch_receipt), encoding="utf-8")
    with pytest.raises(FrwABError, match="PROVIDER_SWITCH_REQUIRED"):
        run_experiment(tmp_path, plan=plan, inputs=_inputs(), submit=submit)
    submit.assert_not_called()

    switch_receipt["switch_sha256"] = canonical_json_sha256(
        {
            key: value
            for key, value in switch_receipt.items()
            if key not in {"switch_sha256", "switch_hmac_sha256"}
        }
    )
    switch_receipt["switch_hmac_sha256"] = "0" * 64
    switch_path.write_text(json.dumps(switch_receipt), encoding="utf-8")
    with pytest.raises(FrwABError, match="PROVIDER_SWITCH_REQUIRED"):
        run_experiment(tmp_path, plan=plan, inputs=_inputs(), submit=submit)
    submit.assert_not_called()

    route_after_failure(
        root=tmp_path,
        shot_id="shot01",
        primary="grok",
        error="HTTP 503 service unavailable",
        plan_sha256=plan["plan_sha256"],
    )
    replay_inputs = {**_inputs(), "prompt": "different plan must not reuse the switch receipt"}
    replay_plan = build_production_plan(
        tmp_path,
        experiment_id="shot01-production-replay",
        operation="image_to_video",
        content_class="general",
        inputs=replay_inputs,
        catalog=_catalog(),
        promotion=promotion,
        shot_id="shot01",
        allow_test_catalog_hash=True,
    )
    with pytest.raises(FrwABError, match="PROVIDER_SWITCH_REQUIRED"):
        run_experiment(tmp_path, plan=replay_plan, inputs=replay_inputs, submit=submit)
    submit.assert_not_called()
    receipt = run_experiment(
        tmp_path,
        plan=plan,
        inputs=_inputs(),
        submit=lambda candidate, _inputs: {
            "success": True,
            "data": {"task_id": f"task-{candidate['model_id']}"},
        },
    )
    assert receipt["ok"] is True


def test_receipt_loader_rejects_symbolic_links(tmp_path: Path) -> None:
    from frw_ab import _load_required

    target = tmp_path / "target.json"
    target.write_text(json.dumps({"kind": "frw-ab-plan"}), encoding="utf-8")
    link = tmp_path / "linked.json"
    link.symlink_to(target)
    with pytest.raises(FrwABError, match="INVALID_RECEIPT_PATH"):
        _load_required(link, kind="frw-ab-plan")


def test_status_rejects_symbolic_link_receipts_directory(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from frw_ab import main

    film = tmp_path / "film"
    outside = tmp_path / "outside"
    film.mkdir()
    outside.mkdir()
    (film / "receipts").symlink_to(outside, target_is_directory=True)
    assert main(["status", "--root", str(film)]) == 2
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["success"] is False
    assert envelope["data"]["error_code"] == "INVALID_RECEIPT_PATH"


def test_run_submits_candidates_concurrently_once_and_persists_no_prompt(
    tmp_path: Path,
) -> None:
    plan = build_plan(
        tmp_path,
        experiment_id="shot01-pilot",
        operation="image_to_video",
        stage="pilot",
        content_class="general",
        inputs=_inputs(),
        catalog=_catalog(),
    )
    calls = []

    def submit(candidate: dict, inputs: dict[str, str]) -> dict:
        model = candidate["model_id"]
        calls.append((model, dict(inputs)))
        return {"success": True, "data": {"task_id": f"task-{model}", "model": model}}

    receipt = run_experiment(tmp_path, plan=plan, inputs=_inputs(), submit=submit)
    assert receipt["ok"] is True
    assert receipt["fanout_count"] == 3
    assert {row["task_id"] for row in receipt["submissions"]} == {
        "task-classic-provider-managed",
        "task-ltx-b",
        "task-seedance-a",
    }
    assert _inputs()["prompt"] not in json.dumps(receipt)
    with pytest.raises(FrwABError, match="RUN_ALREADY_EXISTS"):
        run_experiment(tmp_path, plan=plan, inputs=_inputs(), submit=submit)
    assert len(calls) == 3


def test_concurrent_run_claims_experiment_before_any_submission(tmp_path: Path) -> None:
    plan = build_plan(
        tmp_path,
        experiment_id="shot01-race",
        operation="image_to_video",
        stage="pilot",
        content_class="general",
        inputs=_inputs(),
        catalog=_catalog(),
    )
    calls: list[str] = []

    def submit(candidate: dict, _inputs: dict[str, str]) -> dict:
        calls.append(str(candidate["model_id"]))
        time.sleep(0.05)
        return {
            "success": True,
            "data": {"task_id": f"task-{candidate['model_id']}"},
        }

    def run_once() -> str:
        try:
            run_experiment(tmp_path, plan=plan, inputs=_inputs(), submit=submit)
        except FrwABError as exc:
            return str(exc)
        return "ok"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: run_once(), range(2)))

    assert results.count("ok") == 1
    assert sum("RUN_ALREADY_EXISTS" in result for result in results) == 1
    assert len(calls) == 3


def test_run_receipt_failure_leaves_fail_closed_submission_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = build_plan(
        tmp_path,
        experiment_id="shot01-receipt-failure",
        operation="image_to_video",
        stage="pilot",
        content_class="general",
        inputs=_inputs(),
        catalog=_catalog(),
    )
    calls: list[str] = []

    def submit(candidate: dict, _inputs: dict[str, str]) -> dict:
        calls.append(str(candidate["model_id"]))
        return {
            "success": True,
            "data": {"task_id": f"task-{candidate['model_id']}"},
        }

    monkeypatch.setattr(
        frw_ab,
        "_write_receipt",
        mock.Mock(side_effect=OSError("simulated receipt failure")),
    )
    with pytest.raises(OSError, match="simulated receipt failure"):
        run_experiment(tmp_path, plan=plan, inputs=_inputs(), submit=submit)
    with pytest.raises(FrwABError, match="RUN_ALREADY_EXISTS"):
        run_experiment(tmp_path, plan=plan, inputs=_inputs(), submit=submit)
    assert len(calls) == 3


def test_run_rejects_tampered_plan_before_submission(tmp_path: Path) -> None:
    plan = build_plan(
        tmp_path,
        experiment_id="shot01-pilot",
        operation="image_to_video",
        stage="pilot",
        content_class="general",
        inputs=_inputs(),
        catalog=_catalog(),
    )
    plan["candidates"] = [plan["candidates"][0]]
    submit = mock.Mock()
    with pytest.raises(FrwABError, match="PLAN_TAMPERED"):
        run_experiment(tmp_path, plan=plan, inputs=_inputs(), submit=submit)
    submit.assert_not_called()


def test_poll_queries_every_task_without_resubmission(tmp_path: Path) -> None:
    plan = build_plan(
        tmp_path,
        experiment_id="shot01-pilot",
        operation="image_to_video",
        stage="pilot",
        content_class="general",
        inputs=_inputs(),
        catalog=_catalog(),
    )
    run = run_experiment(
        tmp_path,
        plan=plan,
        inputs=_inputs(),
        submit=lambda candidate, _inputs: {
            "success": True,
            "data": {
                "task_id": f"task-{candidate['model_id']}",
                "model": candidate["model_id"],
            },
        },
    )
    queried = []

    def query(submission: dict) -> dict:
        task_id = submission["task_id"]
        queried.append(task_id)
        return {
            "success": True,
            "data": {
                "task_id": task_id,
                "status": "completed",
                "url": f"https://cdn.example.com/{task_id}.mp4",
            },
        }

    receipt = poll_experiment(tmp_path, run=run, query=query)
    assert receipt["terminal"] is True
    assert len(receipt["results"]) == 3
    assert sorted(queried) == [
        "task-classic-provider-managed",
        "task-ltx-b",
        "task-seedance-a",
    ]
    serialized = json.dumps(receipt)
    assert "https://cdn.example.com/" not in serialized
    assert all(row["url_sha256"] for row in receipt["results"])
    assert len(receipt["poll_sha256"]) == 64


def test_poll_sanitizes_untrusted_status_and_declared_url_hash(tmp_path: Path) -> None:
    plan = build_plan(
        tmp_path,
        experiment_id="shot01-malicious-poll",
        operation="image_to_video",
        stage="pilot",
        content_class="general",
        inputs=_inputs(),
        catalog=_catalog(),
    )
    run = run_experiment(
        tmp_path,
        plan=plan,
        inputs=_inputs(),
        submit=lambda candidate, _inputs: {
            "success": True,
            "data": {"task_id": f"task-{candidate['model_id']}"},
        },
    )
    secret_url = "https://signed.example/SECRET?token=RAW"
    receipt = poll_experiment(
        tmp_path,
        run=run,
        query=lambda _submission: {
            "success": True,
            "data": {
                "status": f"failed {secret_url}",
                "url": secret_url,
                "url_sha256": secret_url,
            },
        },
    )
    serialized = json.dumps(receipt)
    assert secret_url not in serialized
    assert all(row["status"] == "unknown" for row in receipt["results"])
    assert all(
        len(row["url_sha256"]) == 64
        and all(char in "0123456789abcdef" for char in row["url_sha256"])
        for row in receipt["results"]
    )


def test_machine_rank_is_provisional_and_human_approval_is_hash_bound(
    tmp_path: Path,
) -> None:
    clips = tmp_path / "clips"
    clips.mkdir()
    first = clips / "ltx.mp4"
    second = clips / "seedance.mp4"
    first.write_bytes(b"ltx")
    second.write_bytes(b"seedance")
    run = {
        "schema_version": 1,
        "kind": "frw-ab-run",
        "experiment_id": "shot01-pilot",
        "operation": "image_to_video",
        "submissions": [
            {"model_id": "ltx-b", "task_id": "task-ltx"},
            {"model_id": "seedance-a", "task_id": "task-seedance"},
        ],
    }
    run["run_sha256"] = canonical_json_sha256(run)

    def analyze(path: Path, **_kwargs: object) -> dict:
        score = 8.0 if path.name == "seedance.mp4" else 5.0
        return {
            "ok": True,
            "decode_ok": True,
            "motion_ok": True,
            "motion_score": score,
            "motion_continuity": 0.9,
            "width": 720,
            "height": 1280,
            "fps": 24.0,
            "duration_sec": 5.0,
            "errors": [],
        }

    ranked = rank_candidates(
        tmp_path,
        run=run,
        poll=_terminal_poll_for_run(run),
        candidate_paths={"ltx-b": first, "seedance-a": second},
        analyze=analyze,
    )
    assert ranked["status"] == "pending_human_approval"
    assert ranked["provisional"]["champion"] == "seedance-a"
    assert ranked["provisional"]["challenger"] == "ltx-b"
    assert ranked["approved"] is False

    with pytest.raises(FrwABError, match="HUMAN_APPROVAL_REQUIRED"):
        approve_rank(
            tmp_path,
            rank=ranked,
            champion="seedance-a",
            challenger="ltx-b",
            user_phrase="agent chose these",
        )

    approved = approve_rank(
        tmp_path,
        rank=ranked,
        champion="seedance-a",
        challenger="ltx-b",
        user_phrase="批准 seedance-a 为 champion，ltx-b 为 challenger",
    )
    assert approved["approved_by"] == "user"
    assert approved["champion"] == "seedance-a"
    assert approved["challenger"] == "ltx-b"
    assert approved["rank_sha256"]

    with pytest.raises(FrwABError, match="HUMAN_APPROVAL_REQUIRED"):
        approve_rank(
            tmp_path,
            rank=ranked,
            champion="seedance-a",
            challenger="ltx-b",
            user_phrase="pilot 过，可以量产",
        )
    with pytest.raises(FrwABError, match="HUMAN_APPROVAL_REQUIRED"):
        approve_rank(
            tmp_path,
            rank=ranked,
            champion="seedance-a",
            challenger="ltx-b",
            user_phrase="批准 ltx-b 为 champion，seedance-a 为 challenger",
        )


def test_approval_rejects_injected_or_same_candidate(tmp_path: Path) -> None:
    ranked = {
        "schema_version": 1,
        "kind": "frw-ab-rank",
        "experiment_id": "shot01-pilot",
        "operation": "image_to_video",
        "ranked": [{"model_id": "a"}, {"model_id": "b"}],
    }
    ranked["rank_sha256"] = canonical_json_sha256(ranked)
    for champion, challenger in (("x", "b"), ("a", "a")):
        with pytest.raises(FrwABError, match="INVALID_PROMOTION"):
            approve_rank(
                tmp_path,
                rank=ranked,
                champion=champion,
                challenger=challenger,
                user_phrase="pilot 过",
            )


def test_approval_requires_hash_bound_rank_receipt(tmp_path: Path) -> None:
    with pytest.raises(FrwABError, match="RANK_TAMPERED"):
        approve_rank(
            tmp_path,
            rank={
                "schema_version": 1,
                "kind": "frw-ab-rank",
                "operation": "image_to_video",
                "ranked": [{"model_id": "a"}, {"model_id": "b"}],
            },
            champion="a",
            challenger="b",
            user_phrase="pilot 过",
        )


def test_still_models_rank_with_geometry_adapter(tmp_path: Path) -> None:
    outputs = tmp_path / "stills"
    outputs.mkdir()
    paths = {}
    for model, content in (("flux", b"large-still"), ("qwen", b"small")):
        path = outputs / f"{model}.png"
        path.write_bytes(content)
        paths[model] = path
    run = {
        "schema_version": 1,
        "kind": "frw-ab-run",
        "experiment_id": "still-pilot",
        "operation": "text_to_image",
        "catalog_sha256": "d" * 64,
        "submissions": [
            {"model_id": "flux", "task_id": "task-flux"},
            {"model_id": "qwen", "task_id": "task-qwen"},
        ],
    }
    run["run_sha256"] = canonical_json_sha256(run)

    def analyze(path: Path, **kwargs: object) -> dict:
        assert kwargs["aspect_ratio"] == "9:16"
        return {
            "ok": True,
            "width": 720 if path.name == "flux.png" else 704,
            "height": 1280,
            "aspect": 0.5625,
            "codes": [],
            "soft_codes": [],
            "errors": [],
        }

    ranked = rank_candidates(
        tmp_path,
        run=run,
        poll=_terminal_poll_for_run(run),
        candidate_paths=paths,
        analyze=analyze,
    )
    assert ranked["provisional"]["champion"] == "flux"
    assert ranked["provisional"]["challenger"] == "qwen"


def test_approval_rejects_tampered_rank_receipt(tmp_path: Path) -> None:
    clips = tmp_path / "clips"
    clips.mkdir()
    paths = {}
    for model in ("a", "b"):
        path = clips / f"{model}.mp4"
        path.write_bytes(model.encode())
        paths[model] = path
    run = {
        "schema_version": 1,
        "kind": "frw-ab-run",
        "experiment_id": "shot01-pilot",
        "operation": "image_to_video",
        "catalog_sha256": "c" * 64,
        "submissions": [
            {"model_id": "a", "task_id": "task-a"},
            {"model_id": "b", "task_id": "task-b"},
        ],
    }
    run["run_sha256"] = canonical_json_sha256(run)
    ranked = rank_candidates(
        tmp_path,
        run=run,
        poll=_terminal_poll_for_run(run),
        candidate_paths=paths,
        analyze=lambda path, **_kwargs: {
            "ok": True,
            "decode_ok": True,
            "motion_ok": True,
            "motion_score": 5.0 if path.name == "a.mp4" else 4.0,
            "motion_continuity": 0.9,
            "width": 720,
            "height": 1280,
            "fps": 24.0,
            "duration_sec": 5.0,
            "errors": [],
        },
    )
    ranked["ranked"][0]["machine_score"]["motion_score"] = 999
    with pytest.raises(FrwABError, match="RANK_TAMPERED"):
        approve_rank(
            tmp_path,
            rank=ranked,
            champion="a",
            challenger="b",
            user_phrase="pilot 过",
        )


def test_rank_rejects_tampered_or_incomplete_poll(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    paths = {}
    for model in ("a", "b"):
        media = outputs / f"{model}.png"
        media.write_bytes(model.encode())
        paths[model] = media
    run = {
        "schema_version": 1,
        "kind": "frw-ab-run",
        "experiment_id": "poll-chain-pilot",
        "operation": "text_to_image",
        "submissions": [
            {"model_id": "a", "task_id": "task-a", "status": "submitted"},
            {"model_id": "b", "task_id": "task-b", "status": "submitted"},
        ],
    }
    run["run_sha256"] = canonical_json_sha256(run)
    poll = _terminal_poll_for_run(run)
    poll["results"][0]["status"] = "processing"
    analyze = mock.Mock()
    with pytest.raises(FrwABError, match="POLL_TAMPERED"):
        rank_candidates(
            tmp_path,
            run=run,
            poll=poll,
            candidate_paths=paths,
            analyze=analyze,
        )
    analyze.assert_not_called()

    poll = _terminal_poll_for_run(run)
    poll["results"][0]["status"] = "processing"
    poll["terminal"] = False
    poll["poll_sha256"] = canonical_json_sha256(
        {key: value for key, value in poll.items() if key != "poll_sha256"}
    )
    with pytest.raises(FrwABError, match="POLL_NOT_READY"):
        rank_candidates(
            tmp_path,
            run=run,
            poll=poll,
            candidate_paths=paths,
            analyze=analyze,
        )
    analyze.assert_not_called()

    poll = _terminal_poll_for_run(run)
    poll["results"].append(dict(poll["results"][0]))
    poll["poll_sha256"] = canonical_json_sha256(
        {key: value for key, value in poll.items() if key != "poll_sha256"}
    )
    with pytest.raises(FrwABError, match="POLL_NOT_READY"):
        rank_candidates(
            tmp_path,
            run=run,
            poll=poll,
            candidate_paths=paths,
            analyze=analyze,
        )
    analyze.assert_not_called()


def test_frw_dispatch_routes_ab_to_local_control_plane() -> None:
    import frw_dispatch

    with mock.patch.object(frw_dispatch, "run_ab", return_value=0) as run_ab:
        assert frw_dispatch.main(["ab", "status", "--root", "/tmp/film"]) == 0
    run_ab.assert_called_once_with(["status", "--root", "/tmp/film"])
