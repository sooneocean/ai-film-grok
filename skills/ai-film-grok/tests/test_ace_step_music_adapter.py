from __future__ import annotations

import argparse
import json
import sys
import types
from pathlib import Path


def test_adapter_passes_repaint_window_to_ace(tmp_path: Path, monkeypatch) -> None:
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    sys.path.insert(0, str(scripts))
    from adapters import ace_step_music

    checkpoints = tmp_path / "checkpoints"
    for name in (
        "acestep-v15-turbo",
        "acestep-5Hz-lm-1.7B",
        "vae",
        "Qwen3-Embedding-0.6B",
    ):
        folder = checkpoints / name
        folder.mkdir(parents=True)
        (folder / "model.safetensors").write_bytes(b"x")
    reference = tmp_path / "reference.wav"
    reference.write_bytes(b"RIFF" + b"\0" * 1024)
    output_source = tmp_path / "generated.wav"
    output_source.write_bytes(b"RIFF" + b"\0" * 1024)
    output_dir = tmp_path / "out"
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "prompt": "repair ending",
                "duration": 20,
                "batch_size": 1,
                "seeds": [7],
                "task_type": "repaint",
                "reference_audio": str(reference),
                "repainting_start": 12,
                "repainting_end": 20,
            }
        )
    )
    captured: dict[str, object] = {}

    class FakeHandler:
        def initialize_service(self, **_kwargs):
            return "ok", True

    class FakeLM:
        def initialize(self, **_kwargs):
            return None

    class FakeParams:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    class FakeConfig:
        def __init__(self, **_kwargs):
            pass

    result = types.SimpleNamespace(
        success=True,
        error=None,
        audios=[{"path": str(output_source)}],
    )
    package = types.ModuleType("acestep")
    handler = types.ModuleType("acestep.handler")
    inference = types.ModuleType("acestep.inference")
    lm = types.ModuleType("acestep.llm_inference")
    handler.AceStepHandler = FakeHandler
    inference.GenerationParams = FakeParams
    inference.GenerationConfig = FakeConfig
    inference.generate_music = lambda *_args, **_kwargs: result
    lm.LLMHandler = FakeLM
    monkeypatch.setitem(sys.modules, "acestep", package)
    monkeypatch.setitem(sys.modules, "acestep.handler", handler)
    monkeypatch.setitem(sys.modules, "acestep.inference", inference)
    monkeypatch.setitem(sys.modules, "acestep.llm_inference", lm)
    monkeypatch.setenv("ACESTEP_CHECKPOINTS_DIR", str(checkpoints))
    monkeypatch.setattr(
        ace_step_music,
        "_args",
        lambda: argparse.Namespace(
            prompt=None,
            duration=None,
            seed=None,
            out=None,
            request_json=request,
            out_dir=output_dir,
        ),
    )

    ace_step_music.main()

    assert captured["repainting_start"] == 12
    assert captured["repainting_end"] == 20
    assert (output_dir / "00.wav").is_file()
