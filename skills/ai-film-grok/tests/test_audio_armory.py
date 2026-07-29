from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from audio_armory import inspect_audio_armory  # noqa: E402


def test_armory_only_promotes_receipt_backed_audio_weapons(tmp_path: Path) -> None:
    wav = tmp_path / "candidate.wav"
    wav.write_bytes(b"not-a-real-wav")
    # Avoid a media fixture here: seed a minimal catalog through the public
    # shape, keeping this test about route evidence rather than DSP decoding.
    (tmp_path / "catalog.json").write_text(
        '{"schema":"aifilm-bgm-library-v1","revision":1,"assets":{"x":{"status":"pending_human_review","technical":{"ok":true,"duration_sec":20},"parent_asset_id":"master","edit_variant":"dialogue-safe","transition_to_asset_id":"to"}}}',
        encoding="utf-8",
    )
    node = {"ok": True, "models": {"music": True}}
    report = inspect_audio_armory(tmp_path, node=node)
    states = {item["intent"]: item["state"] for item in report["weapons"]}
    assert states["scene_edit"] == "verified"
    assert states["transition_bridge"] == "verified"
    assert states["motif_development"] == "conditional"
    assert any(item["intent"] == "seamless_loop" for item in report["excluded"])
