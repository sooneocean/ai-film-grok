from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import aifilm_grok  # noqa: E402
from generation_usage import finish_generation, start_generation  # noqa: E402
from production_book import new_production_book, write_production_book  # noqa: E402
from production_report import emit_production_report  # noqa: E402
from quality_ledger import emit_quality_ledger  # noqa: E402


def _make_reviewable_mp4(path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=64x96:d=0.2",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=stereo",
            "-shortest",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
    )


def _film(root: Path, *, cost_ticks: int = 100, template_id: str = "vertical-v1") -> None:
    (root / "receipts").mkdir(parents=True)
    (root / "out").mkdir()
    (root / "film-spec.json").write_text('{"shots":[{"id":"s1"}]}')
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "gates": {"final_complete": True},
                "clips": {"s1": {"status": "approved", "qa": {"ok": True}}},
                "outputs": {"final_film": {"duration_sec": 60, "sha256": "a" * 64}},
            }
        )
    )
    (root / "out" / "final-review.json").write_text(
        json.dumps({"approved": True, "grades": {}, "scorecard": {"dimensions": {}}})
    )
    book = new_production_book(title=root.name)
    book["optimization"] = {"template_id": template_id}
    write_production_book(root, book)
    for index, operation in enumerate(("t2i", "image_edit", "i2v", "t2v", "tts")):
        gid = start_generation(
            root,
            operation=operation,
            provider="provider",
            model="model",
            shot_id="s1",
            generation_id=f"{root.name}-{operation}",
        )
        finish_generation(
            root,
            gid,
            status="failed" if operation == "t2v" else "succeeded",
            measurement="provider_exact" if operation != "tts" else "local_zero",
            usage={
                "input_tokens": index + 1,
                "output_tokens": index + 2,
                "cost_in_usd_ticks": 0 if operation == "tts" else cost_ticks,
            },
        )
    emit_quality_ledger(root)


def test_report_aggregates_all_operations_and_preserves_unknown_cost(tmp_path: Path) -> None:
    _film(tmp_path / "film")
    report = emit_production_report(tmp_path / "film")
    assert report["generation"]["requests_total"] == 5
    assert {row["label"] for row in report["generation"]["operations"]} == {
        "T2I",
        "I2I",
        "I2V",
        "T2V",
        "TTS",
    }
    assert report["generation"]["status_counts"] == {"failed": 1, "succeeded": 4}
    assert report["generation"]["tokens"]["values"]["total"] == 35
    assert (tmp_path / "film" / "receipts" / "production-report.json").is_file()
    assert (tmp_path / "film" / "out" / "production-report.html").is_file()


def test_report_only_compares_same_completed_template(tmp_path: Path) -> None:
    library = tmp_path / "library"
    earlier = library / "earlier"
    _film(earlier, cost_ticks=50)
    earlier_book = json.loads((earlier / "production-book.json").read_text())
    earlier_book["optimization"]["history_root"] = str(library)
    write_production_book(earlier, earlier_book, expected_revision=1)
    emit_production_report(earlier)

    unrelated = library / "unrelated"
    _film(unrelated, template_id="other")
    emit_production_report(unrelated)

    current = library / "current"
    _film(current, cost_ticks=100)
    report = emit_production_report(current, history_root=library)
    assert report["comparison"]["state"] == "known"
    assert report["comparison"]["sample_count"] == 1
    assert report["comparison"]["metrics"]["usd_per_pass_min"]["difference"] is not None


def test_cli_safely_reports_missing_history_configuration(tmp_path: Path) -> None:
    _film(tmp_path)
    assert aifilm_grok.main(["production-report", "emit", "--root", str(tmp_path)]) == 0
    report = json.loads((tmp_path / "receipts" / "production-report.json").read_text())
    assert report["comparison"]["reason"] == "history_root_missing"


def test_desktop_export_copies_production_report_artifacts(tmp_path: Path) -> None:
    root = tmp_path / "film"
    desktop = tmp_path / "home" / "Desktop"
    desktop.mkdir(parents=True)
    dirs = {name: root / name for name in ("out", "audio", "keyframes", "clips", "canonical")}
    for directory in dirs.values():
        directory.mkdir(parents=True, exist_ok=True)
    (root / "receipts").mkdir()
    (root / "manifest.json").write_text("{}")
    (root / "receipts" / "post-audit.json").write_text('{"delivery_ready":true}')
    (root / "receipts" / "i2v-final-gate.json").write_text(
        '{"ok": true, "schema_version": 1, "kind": "i2v-final-gate"}'
    )
    (root / "receipts" / "cinematic-gate.json").write_text(
        '{"ok": true, "schema_version": 1, "kind": "cinematic-gate", "desktop_export_allowed": true}'
    )
    (dirs["out"] / "production-report.html").write_text("<h1>report</h1>")
    (root / "receipts" / "production-report.json").write_text('{"kind":"production-report"}')
    final = dirs["out"] / "custom-final.mp4"
    _make_reviewable_mp4(final)
    manifest = {
        "title": "film",
        "gates": {"final_complete": True},
        "outputs": {
            "final_film": {
                "path": final.name,
                "sha256": aifilm_grok.sha256(final),
            }
        },
    }

    def gates(_root: Path, target: dict[str, object]) -> dict[str, object]:
        target["gates"] = {"final_complete": True}
        return target

    with (
        patch.object(aifilm_grok.Path, "home", return_value=tmp_path / "home"),
        patch.object(aifilm_grok, "load_manifest", return_value=manifest),
        patch.object(aifilm_grok, "recompute_gates", side_effect=gates),
        patch.object(aifilm_grok, "save_manifest"),
        patch.object(aifilm_grok, "film_dirs", return_value=dirs),
        patch("post_audit.audit_freshness", return_value={"stale": False}),
    ):
        assert (
            aifilm_grok.cmd_export_desktop(
                argparse.Namespace(root=str(root), name="export", force=False)
            )
            == 0
        )

    destination = desktop / "export"
    assert (destination / "成片" / "custom-final.mp4").is_file()
    assert (destination / "成片" / "production-report.html").is_file()
    assert (destination / "项目状态" / "production-report.json").is_file()
