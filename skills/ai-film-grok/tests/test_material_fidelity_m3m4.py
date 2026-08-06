"""Material Fidelity M3 (asset hints) + M4 (shot evidence feedback)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from asset_registry import build_asset_prompt_hints  # noqa: E402
from generation_request import build_generation_request  # noqa: E402
from shot_evidence import (  # noqa: E402
    list_still_challenge_suggestions,
    load_shot_evidence,
    prior_evidence_lines,
    write_shot_evidence,
)


def _png(path: Path, tag: bytes = b"A") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + tag * 24)
    return path


def _film(tmp_path: Path) -> Path:
    root = tmp_path / "film"
    root.mkdir()
    still = _png(root / "stills" / "s01.png")
    (root / "film-spec.json").write_text(
        json.dumps(
            {
                "title": "m3m4",
                "director_intent": {
                    "logline": "t",
                    "theme": "t",
                    "protagonist_want": "escape",
                },
                "scenes": [
                    {
                        "id": "sc1",
                        "shots": [
                            {
                                "id": "s01",
                                "locationId": "cave",
                                "propIds": ["lantern"],
                                "wardrobe_state": "full",
                                "heat_phase": "setup",
                                "dramatic_function": "hook",
                                "visible_change": "steps into torch light",
                                "dsl": {
                                    "action": "steps into torch light",
                                    "motion": "walk two steps forward",
                                    "camera": {"shot_size": "ms"},
                                },
                                "duration_sec": 4,
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (root / "manifest.json").write_text(
        json.dumps({"stills": {"s01": {"path": str(still), "status": "approved"}}}),
        encoding="utf-8",
    )
    (root / "style-bible.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "signature_block": "cel anime clean line vertical drama medium lock",
                "medium": "anime",
                "style_fingerprint": {"medium_key": "anime", "medium": "cel anime"},
            }
        ),
        encoding="utf-8",
    )
    (root / "assets-registry.json").write_text(
        json.dumps(
            {
                "locations": {
                    "cave": {
                        "id": "cave",
                        "description": "damp stone cave",
                        "structure": "low ceiling",
                        "lighting": "warm torch",
                        "palette": "ochre",
                        "timeOfDay": "night",
                        "immutableRules": ["no daylight"],
                        "recurringObjects": ["lantern"],
                    }
                },
                "props": {
                    "lantern": {
                        "id": "lantern",
                        "description": "brass oil lantern",
                        "condition": "lit",
                        "storyFunction": "hope light",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return root


def test_asset_hints_location_and_prop(tmp_path: Path) -> None:
    root = _film(tmp_path)
    shot = json.loads((root / "film-spec.json").read_text())["scenes"][0]["shots"][0]
    rep = build_asset_prompt_hints(root, shot)
    assert rep["registry_present"] is True
    joined = "\n".join(rep["lines"])
    assert "Location lock" in joined
    assert "damp stone" in joined or "warm torch" in joined
    assert "lantern" in joined.lower()
    assert "hope light" in joined or "lit" in joined


def test_generation_request_includes_location_lock(tmp_path: Path) -> None:
    root = _film(tmp_path)
    req = build_generation_request(root, "s01", kind="i2v", write=False)
    assert "Location lock" in req["text_prompt"] or "damp stone" in req["text_prompt"]


def test_prior_evidence_weak_mean_suggests_still_challenge(tmp_path: Path) -> None:
    root = _film(tmp_path)
    write_shot_evidence(
        root,
        "s01",
        mean=6.0,
        identity_ok=True,
        motion_ok=False,
        source="test",
    )
    ev = load_shot_evidence(root, "s01")
    assert ev and ev.get("suggest_still_challenge") is True
    lines = prior_evidence_lines(root, "s01")
    assert any("PRIOR_EVIDENCE" in ln for ln in lines)
    assert any("still-challenge" in ln or "WEAK" in ln for ln in lines)
    sug = list_still_challenge_suggestions(root)
    assert sug["count"] == 1
    assert "still-challenge" in (sug.get("next_cmd") or "")


def test_generation_request_prepends_prior_evidence(tmp_path: Path) -> None:
    root = _film(tmp_path)
    write_shot_evidence(root, "s01", mean=5.5, identity_ok=True, source="test")
    req = build_generation_request(root, "s01", kind="i2v", write=True)
    assert req["text_prompt"].startswith("PRIOR_EVIDENCE") or "PRIOR_EVIDENCE" in req[
        "text_prompt"
    ][:200]
    assert req.get("prior_evidence")
