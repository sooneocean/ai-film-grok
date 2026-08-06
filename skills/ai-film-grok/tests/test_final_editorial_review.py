from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import final_editorial_review as editorial  # noqa: E402


def test_post_tts_dialogue_contract_requires_suppression() -> None:
    spec = {
        "scenes": [
            {
                "shots": [
                    {
                        "id": "shot01",
                        "dialogue_contracts": [
                            {
                                "lines": [
                                    {
                                        "audio_origin": "post_vo",
                                    }
                                ]
                            }
                        ],
                    }
                ]
            }
        ]
    }
    assert editorial._post_tts_dialogue_shots(spec) == {"shot01"}


def test_currentness_detects_final_or_mix_change(tmp_path: Path) -> None:
    (tmp_path / "out").mkdir()
    (tmp_path / "audio").mkdir()
    (tmp_path / "out" / "film_final.mp4").write_bytes(b"one")
    (tmp_path / "audio" / "mix_report.json").write_text("{}", encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps({"outputs": {"final_film": {"path": "film_final.mp4"}}}), encoding="utf-8"
    )
    receipt = {
        "inputs": editorial._inputs(tmp_path, json.loads((tmp_path / "manifest.json").read_text()))
    }
    assert editorial.is_current(tmp_path, receipt)["ok"] is True
    (tmp_path / "audio" / "mix_report.json").write_text('{"changed": true}', encoding="utf-8")
    stale = editorial.is_current(tmp_path, receipt)
    assert stale["stale"] is True
    assert stale["mismatches"] == ["mix_report"]
