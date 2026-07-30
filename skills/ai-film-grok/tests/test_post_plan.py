"""Post-plan is the one handoff between editorial and a chosen post engine."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from post_plan import (  # noqa: E402
    PostPlanError,
    delivery_status,
    ensure_post_plan,
    load_post_plan,
    new_post_plan,
    record_render_evidence,
    validate_post_plan,
    validate_render_owner,
    write_post_plan,
)
from util.errors import FilmError  # noqa: E402


def test_new_plan_captures_video_use_hard_rules_and_default_owner(tmp_path: Path) -> None:
    plan = new_post_plan(tmp_path)
    assert plan["post_owner"] == "hyperframes"
    assert plan["caption_owner"] == "hyperframes"
    assert plan["editorial"]["rules"] == {
        "subtitles_last": True,
        "word_boundary_cuts": True,
        "segment_audio_fades_ms": 30,
    }
    assert validate_post_plan(tmp_path, plan)["ok"] is True


def test_new_plan_allows_ffmpeg_as_the_single_post_owner(tmp_path: Path) -> None:
    plan = new_post_plan(tmp_path, owner="ffmpeg")

    assert plan["post_owner"] == "ffmpeg"
    assert plan["caption_owner"] == "ffmpeg"
    assert validate_post_plan(tmp_path, plan)["ok"] is True


def test_edl_source_types_are_preserved(tmp_path: Path) -> None:
    edit = tmp_path / "edit"
    edit.mkdir()
    (edit / "edl.json").write_text(
        json.dumps({"ranges": [{"source_type": "generated"}, {"source_type": "real_footage"}]}),
        encoding="utf-8",
    )
    plan = new_post_plan(tmp_path, edl_path="edit/edl.json", owner="remotion")
    assert plan["editorial"]["source_types"] == ["generated_clip", "real_footage"]
    assert plan["render"]["engine"] == "remotion"


def test_plan_rejects_double_caption_owner_and_unsafe_paths(tmp_path: Path) -> None:
    plan = new_post_plan(tmp_path)
    plan["caption_owner"] = "remotion"
    plan["artifacts"]["master_subtitles"] = "../outside.srt"
    issues = validate_post_plan(tmp_path, plan)["issues"]
    assert any("captions are burned exactly once" in issue for issue in issues)
    assert any("workspace-relative" in issue for issue in issues)


def test_existing_plan_gates_compose_engine_and_records_only_technical_evidence(
    tmp_path: Path,
) -> None:
    plan = new_post_plan(tmp_path, owner="remotion")
    write_post_plan(tmp_path, plan)
    with pytest.raises(PostPlanError, match="post_owner=remotion"):
        validate_render_owner(tmp_path, "hyperframes")
    assert validate_render_owner(tmp_path, "remotion")["post_owner"] == "remotion"
    receipt = tmp_path / "out" / "final-delivery.json"
    receipt.parent.mkdir()
    receipt.write_text('{"technical_qa":{"ok":true}}', encoding="utf-8")
    record_render_evidence(
        tmp_path,
        engine="remotion",
        output="out/film_remotion.mp4",
        composition_checked=True,
        ffprobe_readback=True,
        technical_qa_report=str(receipt),
    )
    acceptance = load_post_plan(tmp_path, required=True)["acceptance"]
    assert acceptance["composition_check"] is True
    assert acceptance["ffprobe_readback"] is True
    assert acceptance["human_review"] is False


def test_plan_rejects_fake_human_review_and_non_object_json(tmp_path: Path) -> None:
    plan = new_post_plan(tmp_path)
    plan["acceptance"]["human_review"] = True
    assert "never post-plan" in " ".join(validate_post_plan(tmp_path, plan)["issues"])
    assert validate_post_plan(tmp_path, []) == {
        "ok": False,
        "issues": ["post-plan must be a JSON object"],
        "post_owner": None,
    }


def test_plan_rejects_claimed_ffprobe_without_a_passing_receipt(tmp_path: Path) -> None:
    plan = new_post_plan(tmp_path)
    plan["acceptance"]["ffprobe_readback"] = True
    plan["acceptance"]["technical_qa_report"] = "out/final-delivery.json"
    assert "lacks passing technical_qa" in " ".join(validate_post_plan(tmp_path, plan)["issues"])


def test_render_evidence_normalizes_a_tmp_alias_root() -> None:
    with tempfile.TemporaryDirectory(dir="/tmp", prefix="aifilm-post-plan-") as temporary:
        root = Path(temporary)
        write_post_plan(root, new_post_plan(root))
        receipt = root / "out" / "final-delivery.json"
        receipt.parent.mkdir()
        receipt.write_text('{"technical_qa":{"ok":true}}', encoding="utf-8")
        record_render_evidence(
            root,
            engine="hyperframes",
            output="out/film.mp4",
            ffprobe_readback=True,
            technical_qa_report=str(receipt),
        )
        assert load_post_plan(root, required=True)["acceptance"]["ffprobe_readback"] is True


def test_ensure_post_plan_creates_once_and_never_replaces_existing_owner(tmp_path: Path) -> None:
    first, created = ensure_post_plan(tmp_path, owner="remotion")
    second, recreated = ensure_post_plan(tmp_path, owner="hyperframes")
    assert created is True
    assert recreated is False
    assert first["post_owner"] == second["post_owner"] == "remotion"


def test_export_compose_bootstraps_owner_from_selected_engine(tmp_path: Path, monkeypatch) -> None:
    import aifilm_grok as cli
    import export_composition as export_module

    emitted: list[dict] = []
    monkeypatch.setattr(cli, "load_manifest", lambda _root: {})
    monkeypatch.setattr(
        cli, "recompute_gates", lambda _root, _manifest: {"gates": {"clips_complete": True}}
    )
    monkeypatch.setattr(export_module, "export_composition", lambda *_args, **_kwargs: {"ok": True})
    monkeypatch.setattr(cli, "emit", emitted.append)
    args = type(
        "Args",
        (),
        {
            "root": str(tmp_path),
            "engine": "remotion",
            "post_owner": None,
            "title_dur": 1.5,
            "end_dur": 1.5,
            "force": False,
            "layout": "auto",
            "compose_preset": "auto",
            "title_sequence": None,
            "end_roll": None,
        },
    )()
    assert cli.cmd_export_compose(args) == 0
    assert emitted[0]["post_plan"] == {
        "path": str(tmp_path / "post-plan.json"),
        "post_owner": "remotion",
        "created": True,
    }
    assert load_post_plan(tmp_path, required=True)["post_owner"] == "remotion"


def test_export_compose_rejects_an_engine_that_conflicts_with_existing_owner(
    tmp_path: Path, monkeypatch
) -> None:
    import aifilm_grok as cli

    write_post_plan(tmp_path, new_post_plan(tmp_path, owner="remotion"))
    monkeypatch.setattr(cli, "load_manifest", lambda _root: {})
    monkeypatch.setattr(
        cli, "recompute_gates", lambda _root, _manifest: {"gates": {"clips_complete": True}}
    )
    args = type(
        "Args",
        (),
        {
            "root": str(tmp_path),
            "engine": "hyperframes",
            "post_owner": None,
        },
    )()
    with pytest.raises(FilmError, match="post_owner=remotion"):
        cli.cmd_export_compose(args)


def test_delivery_status_requires_matching_engine_technical_receipt_and_hash_bound_review(
    tmp_path: Path,
) -> None:
    receipt = tmp_path / "out" / "final-delivery.json"
    receipt.parent.mkdir()
    receipt.write_text('{"technical_qa":{"ok":true}}', encoding="utf-8")
    plan = new_post_plan(tmp_path, owner="hyperframes")
    write_post_plan(tmp_path, plan)
    record_render_evidence(
        tmp_path,
        engine="hyperframes",
        output="out/film.mp4",
        ffprobe_readback=True,
        technical_qa_report=str(receipt),
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "outputs": {
                    "final_film": {"post_engine": "hyperframes", "sha256": "final-sha"},
                    "final_review": {"approved": True, "output_sha256": "final-sha"},
                }
            }
        ),
        encoding="utf-8",
    )
    assert delivery_status(tmp_path)["release_ready"] is True


def test_render_output_alone_does_not_claim_ffprobe_readback(tmp_path: Path) -> None:
    write_post_plan(tmp_path, new_post_plan(tmp_path))
    record_render_evidence(tmp_path, engine="hyperframes", output="out/film_hyperframes.mp4")
    acceptance = load_post_plan(tmp_path, required=True)["acceptance"]
    assert acceptance["rendered_media"] is True
    assert acceptance["ffprobe_readback"] is False


def test_cli_parser_uses_root_before_post_plan_action() -> None:
    from aifilm_grok import build_parser

    args = build_parser().parse_args(["post-plan", "--root", "/tmp/film", "init"])
    assert args.post_plan_action == "init"
    assert args.root == "/tmp/film"


def test_final_designed_post_obeys_existing_post_owner(tmp_path: Path) -> None:
    from aifilm_grok import cmd_final

    write_post_plan(tmp_path, new_post_plan(tmp_path, owner="remotion"))
    args = type("Args", (), {"root": str(tmp_path), "post_engine": "hyperframes"})()
    with pytest.raises(FilmError, match="post_owner=remotion"):
        cmd_final(args)


def test_final_ffmpeg_cannot_bypass_existing_designed_post_owner(tmp_path: Path) -> None:
    from aifilm_grok import cmd_final

    write_post_plan(tmp_path, new_post_plan(tmp_path, owner="hyperframes"))
    args = type("Args", (), {"root": str(tmp_path), "post_engine": "ffmpeg"})()
    with pytest.raises(FilmError, match="post_owner=hyperframes"):
        cmd_final(args)
