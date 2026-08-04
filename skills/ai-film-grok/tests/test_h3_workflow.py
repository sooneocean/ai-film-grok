"""H3 film workflow: plan/list + native-audio prefer policy (no GPU)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aifilm_grok import build_parser  # noqa: E402
from h3_workflow import (  # noqa: E402
    ensure_h3_delivery_geometry,
    list_h3_eligible_shots,
    plan_h3_shot,
    resolve_h3_deliver_audio,
)


def _film_root(tmp_path: Path, *, h3_enabled: bool = True) -> Path:
    root = tmp_path / "film"
    root.mkdir()
    (root / "receipts" / "prompts").mkdir(parents=True)
    still = root / "stills" / "s_meat.png"
    still.parent.mkdir(parents=True)
    still.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    spec = {
        "title": "h3-wf",
        "aspect_ratio": "9:16",
        "_i2v_profile": "hybrid_h3",
        "h3": {"enabled": h3_enabled, "audio_policy": "prefer_native"},
        "scenes": [
            {
                "id": "sc1",
                "shots": [
                    {
                        "id": "s_meat",
                        "shot_role": "hero",
                        "heat_phase": "act",
                        "wardrobe_state": "bare",
                        "nar": "body motion",
                    },
                    {
                        "id": "s_setup",
                        "shot_role": "hero",
                        "heat_phase": "setup",
                        "nar": "walk in",
                    },
                ],
            }
        ],
    }
    (root / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "stills": {
                    "s_meat": {"path": str(still), "status": "approved"},
                }
            }
        ),
        encoding="utf-8",
    )
    return root


def test_h3_cli_dispatches(tmp_path: Path) -> None:
    root = _film_root(tmp_path)
    parser = build_parser()
    args = parser.parse_args(["h3", "list", "--root", str(root)])
    assert args.cmd == "h3"
    assert args.h3_action == "list"


def test_plan_h3_shot_defaults_prefer_native(tmp_path: Path) -> None:
    root = _film_root(tmp_path)
    plan = plan_h3_shot(root, "s_meat")
    assert plan["ok"] is True
    assert plan["mode"] == "i2v"
    assert plan["weapon_id"] == "minimax-h3-i2v-pilot"
    assert plan["source_endpoint"] == "local_minimax_h3_i2v"
    assert plan["audio_policy"] == "prefer_native"
    assert plan["still_path"]


def test_list_eligible_includes_restricted(tmp_path: Path) -> None:
    root = _film_root(tmp_path)
    report = list_h3_eligible_shots(root)
    ids = {row["shot_id"] for row in report["shots"]}
    assert "s_meat" in ids
    assert "s_setup" not in ids


def test_prefer_native_keeps_when_usable(tmp_path: Path) -> None:
    raw = tmp_path / "raw.mp4"
    plate = tmp_path / "plate.mp4"
    raw.write_bytes(b"fake")
    with mock.patch("h3_workflow._native_audio_usable", return_value=(True, {"usable": True})):
        decision = resolve_h3_deliver_audio(raw, plate, audio_policy="prefer_native")
    assert decision["deliver_path"] == raw
    assert decision["audio_stripped"] is False
    assert decision["use_clip_audio"] is True
    assert decision["audio_policy_effective"] == "keep_native"
    assert not plate.exists()


def test_prefer_native_strips_when_unusable(tmp_path: Path) -> None:
    raw = tmp_path / "raw.mp4"
    plate = tmp_path / "plate.mp4"
    raw.write_bytes(b"fake")
    with (
        mock.patch("h3_workflow._native_audio_usable", return_value=(False, {"usable": False})),
        mock.patch("h3_workflow._strip_audio", side_effect=lambda s, d: d.write_bytes(b"p") or d),
    ):
        decision = resolve_h3_deliver_audio(raw, plate, audio_policy="prefer_native")
    assert decision["deliver_path"] == plate
    assert decision["audio_stripped"] is True
    assert decision["use_clip_audio"] is False
    assert decision["audio_policy_effective"] == "strip_native_use_tts_bgm"


def test_keep_native_never_strips(tmp_path: Path) -> None:
    raw = tmp_path / "raw.mp4"
    plate = tmp_path / "plate.mp4"
    raw.write_bytes(b"fake")
    decision = resolve_h3_deliver_audio(raw, plate, audio_policy="keep_native")
    assert decision["deliver_path"] == raw
    assert decision["audio_stripped"] is False
    assert decision["use_clip_audio"] is True


def test_explicit_strip_always_strips(tmp_path: Path) -> None:
    raw = tmp_path / "raw.mp4"
    plate = tmp_path / "plate.mp4"
    raw.write_bytes(b"fake")
    with mock.patch("h3_workflow._strip_audio", side_effect=lambda s, d: d.write_bytes(b"p") or d):
        decision = resolve_h3_deliver_audio(raw, plate, audio_policy="strip_native_use_tts_bgm")
    assert decision["audio_stripped"] is True
    assert decision["use_clip_audio"] is False


def test_ensure_geometry_skips_when_floor_met(tmp_path: Path) -> None:
    raw = tmp_path / "ok.mp4"
    dest = tmp_path / "out.mp4"
    raw.write_bytes(b"fake")
    with mock.patch(
        "media_qa.analyze_media",
        return_value={"width": 704, "height": 1280, "ok": True},
    ):
        meta = ensure_h3_delivery_geometry(raw, dest)
    assert meta["upscaled"] is False
    assert meta["deliver_path"] == str(raw.resolve())


def test_ensure_geometry_upscales_small(tmp_path: Path) -> None:
    raw = tmp_path / "small.mp4"
    dest = tmp_path / "out.mp4"
    raw.write_bytes(b"fake")
    calls = {"n": 0}

    def _probe(path, **kwargs):  # noqa: ANN001
        calls["n"] += 1
        p = Path(path)
        if p.name == "out.mp4":
            return {"width": 704, "height": 1280, "ok": True}
        return {"width": 352, "height": 608, "ok": True}

    def _run(*_a, **_k):
        dest.write_bytes(b"up")
        return type("P", (), {"returncode": 0, "stderr": "", "stdout": ""})()

    with (
        mock.patch("media_qa.analyze_media", side_effect=_probe),
        mock.patch("h3_workflow.subprocess.run", side_effect=_run),
    ):
        meta = ensure_h3_delivery_geometry(raw, dest)
    assert meta["upscaled"] is True
    assert meta["deliver_path"] == str(dest.resolve())
    assert dest.is_file()
