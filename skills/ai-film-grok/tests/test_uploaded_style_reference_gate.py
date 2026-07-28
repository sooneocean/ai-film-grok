"""Reference-first media must carry and prove the uploaded style image."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import aifilm_grok  # noqa: E402
from aifilm_grok import recompute_gates  # noqa: E402
from media_queue import MediaQueue, QueueError, style_reference_output_evidence  # noqa: E402
from quality_gates import evaluate_clip, evaluate_keyframe  # noqa: E402
from skill_runner import _media_queue_argv  # noqa: E402


def _style_root(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    root = tmp_path / "film"
    source = root / "source" / "style-ref-hero.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"uploaded-style")
    style_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    style = {
        "locked": True,
        "state": "Approved",
        "style_reference": {
            "kind": "uploaded-style-reference",
            "staged_path": str(source),
            "canonical_path": str(source),
            "sha256": style_sha,
        },
    }
    (root / "style-bible.json").write_text(json.dumps(style), encoding="utf-8")
    prompt = root / "prompts" / "shot01.txt"
    prompt.parent.mkdir(parents=True)
    prompt.write_text("locked style prompt", encoding="utf-8")
    prompt_sha = hashlib.sha256(prompt.read_bytes()).hexdigest()
    receipts = root / "receipts"
    receipts.mkdir()
    assembly = receipts / "prompt_assembly_shot01.json"
    assembly.write_text(
        json.dumps(
            {
                "shot_id": "shot01",
                "prompt_hash": prompt_sha,
                "style_reference": style["style_reference"],
                "reference_instruction": "Style reference is attached",
            }
        ),
        encoding="utf-8",
    )
    keyframe = root / "keyframes" / "shot01.png"
    keyframe.parent.mkdir()
    keyframe.write_bytes(b"keyframe")
    return root, source, prompt, assembly


def test_queue_rejects_frame1_only_i2v_for_reference_first_film(tmp_path: Path) -> None:
    root, source, prompt, assembly = _style_root(tmp_path)
    with pytest.raises(QueueError, match="forbids image_to_video"):
        MediaQueue(root).add_job(
            shot_id="shot01",
            operation="image_to_video",
            prompt_file=prompt,
            inputs=[source],
            assembly_receipt=assembly,
            allow_without_pilot=True,
        )


def test_queue_requires_uploaded_reference_and_matching_assembly_receipt(tmp_path: Path) -> None:
    root, source, prompt, assembly = _style_root(tmp_path)
    keyframe = root / "keyframes" / "shot01.png"
    queue = MediaQueue(root)
    with pytest.raises(QueueError, match="must include the uploaded style reference"):
        queue.add_job(
            shot_id="shot01",
            operation="reference_to_video",
            prompt_file=prompt,
            inputs=[keyframe],
            assembly_receipt=assembly,
            allow_without_pilot=True,
        )
    job = queue.add_job(
        shot_id="shot01",
        operation="reference_to_video",
        prompt_file=prompt,
        inputs=[keyframe, source],
        assembly_receipt=assembly,
        allow_without_pilot=True,
    )
    assert job["style_reference_input"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()


def test_keyframe_and_clip_quality_require_same_reference_evidence(tmp_path: Path) -> None:
    root, source, prompt, _assembly = _style_root(tmp_path)
    (root / "film-spec.json").write_text(
        json.dumps({"scenes": [{"shots": [{"id": "shot01", "shot_role": "env"}]}]}),
        encoding="utf-8",
    )
    keyframe = root / "keyframes" / "shot01.png"
    keyframe.write_bytes(b"not-an-image")
    keyframe_report = evaluate_keyframe(
        root,
        shot_id="shot01",
        source=keyframe,
        aspect_ratio="9:16",
        prompt_file=prompt,
        identity_approved=True,
        review_note="style checked",
    )
    assert keyframe_report["style_assembly"]["ok"] is True
    (root / "manifest.json").write_text(
        json.dumps({"stills": {"shot01": {"quality_gate": keyframe_report}}}), encoding="utf-8"
    )
    clip_report = evaluate_clip(
        root,
        shot_id="shot01",
        qa={"ok": True},
        endpoint="reference_to_video",
        identity_approved=False,
        motion_approved=False,
        review=None,
    )
    assert "STYLE_REFERENCE_KEYFRAME_EVIDENCE_MISSING" not in clip_report["codes"]
    source.write_bytes(b"tampered")
    tampered = evaluate_keyframe(
        root,
        shot_id="shot01",
        source=keyframe,
        aspect_ratio="9:16",
        prompt_file=prompt,
        identity_approved=True,
        review_note="style checked",
    )
    assert "STYLE_REFERENCE_STAGED_SHA256_MISMATCH" in tampered["codes"]


def test_registry_runner_auto_binds_reference_and_uses_multi_ref_i2v(tmp_path: Path) -> None:
    root, source, prompt, _assembly = _style_root(tmp_path)
    keyframe = root / "keyframes" / "shot01.png"
    argv = _media_queue_argv(
        {
            "projectRoot": str(root),
            "nodeRef": "shot:shot01",
            "input": {"promptFile": str(prompt), "inputs": [str(keyframe)]},
        },
        skill_id="image.animate",
    )
    assert "reference_to_video" in argv
    assert str(source) in argv
    assert str(root / "receipts" / "prompt_assembly_shot01.json") in argv


def test_completed_still_job_binds_output_and_current_style_sha(tmp_path: Path) -> None:
    root, source, prompt, assembly = _style_root(tmp_path)
    output = root / "keyframes" / "shot01.png"
    output.write_bytes(b"generated-keyframe")
    queue = MediaQueue(root)
    job = queue.add_job(
        shot_id="shot01",
        operation="image_edit",
        prompt_file=prompt,
        inputs=[source],
        assembly_receipt=assembly,
        allow_without_pilot=True,
    )
    claimed = queue.claim()
    queue.complete(
        job["id"],
        claim_token=claimed["claim_token"],
        output=output,
        endpoint="image_edit",
    )
    evidence = style_reference_output_evidence(
        root,
        job_id=job["id"],
        source=output,
        shot_id="shot01",
        allowed_operations=frozenset({"image_edit"}),
    )
    assert evidence["style_reference_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    source.write_bytes(b"tampered")
    with pytest.raises(QueueError, match="integrity validation"):
        style_reference_output_evidence(
            root,
            job_id=job["id"],
            source=output,
            shot_id="shot01",
            allowed_operations=frozenset({"image_edit"}),
        )


def test_gate_recompute_invalidates_locked_style_when_reference_is_tampered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, source, _prompt, _assembly = _style_root(tmp_path)
    (root / "film-spec.json").write_text(
        json.dumps({"scenes": [{"shots": [{"id": "shot01"}]}]}), encoding="utf-8"
    )
    contract_sha = hashlib.sha256((root / "film-spec.json").read_bytes()).hexdigest()
    monkeypatch.setattr(
        aifilm_grok,
        "validate_film_spec",
        lambda _spec, assign_missing_ids=False: [{"id": "shot01"}],
    )
    clip = root / "clips" / "shot01.mp4"
    clip.parent.mkdir()
    clip.write_bytes(b"approved clip")
    clip_sha = hashlib.sha256(clip.read_bytes()).hexdigest()
    style_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest: dict = {
        "stills": {},
        "clips": {
            "shot01": {
                    "status": "approved",
                    "shot_id": "shot01",
                    "path": str(clip),
                    "sha256": clip_sha,
                    "provider": "grok",
                "source_endpoint": "reference_to_video",
                "identity_approved": True,
                "motion_approved": True,
                "review_note": "approved",
                "qa": {"ok": True, "decode_ok": True, "motion_ok": True},
                "quality_gate": {"ok": True},
                "style_reference_job": {"style_reference_sha256": style_sha},
                "uniqueness": {"sha256": clip_sha},
            }
        },
        "outputs": {},
        "schema_version": 2,
        "truth_contract": {
            "source_of_truth": "local-contract-and-receipts",
            "contract_sha256": contract_sha,
        },
    }
    report = recompute_gates(root, manifest)
    assert manifest["gates"]["style_locked"] is True
    assert manifest["gates"]["clips_complete"] is True, report
    source.write_bytes(b"tampered")
    recompute_gates(root, manifest)
    assert manifest["gates"]["style_locked"] is False
    assert manifest["gates"]["clips_complete"] is False
