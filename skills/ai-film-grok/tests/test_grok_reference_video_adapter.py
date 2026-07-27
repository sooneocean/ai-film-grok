"""Batch Grok I2V must forward the uploaded style image as a real reference."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from i2v_provider import GrokI2VProvider  # noqa: E402


def test_grok_batch_command_uses_video_adapter_and_forwards_style_ref(tmp_path: Path) -> None:
    keyframe = tmp_path / "keyframe.png"
    style = tmp_path / "style.png"
    keyframe.write_bytes(b"keyframe")
    style.write_bytes(b"style")
    output = tmp_path / "clip.mp4"
    command = GrokI2VProvider().build_command(
        keyframe=keyframe,
        prompt="keep the locked visual language",
        duration_sec=6,
        reference_images=[style],
        out=output,
    )
    assert command[1].endswith("grok_oauth_video.py")
    assert command.count("--ref") == 1
    assert str(style.resolve()) in command
    assert "--wait" not in command
    assert command[command.index("--out") + 1] == str(output.resolve())


def test_grok_batch_command_requires_output_path(tmp_path: Path) -> None:
    keyframe = tmp_path / "keyframe.png"
    keyframe.write_bytes(b"keyframe")
    try:
        GrokI2VProvider().build_command(keyframe=keyframe, prompt="locked")
    except Exception as exc:
        assert "explicit output path" in str(exc)
    else:  # pragma: no cover - the test must fail if the adapter contract weakens
        raise AssertionError("missing output path unexpectedly compiled")
